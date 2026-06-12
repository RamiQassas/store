import json
from decimal import Decimal
import os
import random
import string
import pyotp
import qrcode
import io
import base64
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from django.core.signing import TimestampSigner, SignatureExpired, BadSignature

from apps.accounts.models import User, OTPToken, KYCRequest, KYCSettings
from apps.accounts.services import send_brevo_email
from apps.catalog.models import Category, Product, ProductVariant
from apps.common.models import Currency, SocialMediaLink, SiteAnnouncement
from apps.notifications.models import Notification, NotificationSetting
from apps.notifications.services import notify_bulk, notify_user
from apps.orders.models import Order, OrderLog, Coupon
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest
from apps.site.forms import (
    LoginForm, RegisterForm, PaymentMethodForm, CurrencyForm, ModerateUserForm, 
    ProductForm, KYCRequestForm, KYCSettingsForm, ChangePasswordForm, 
    CouponForm, SendNotificationForm, AdminChatForm, SiteAnnouncementForm, 
    ChatCannedReplyForm, SupportSettingsForm
)
from apps.support.models import ChatRoom, ChatMessage, ChatCannedReply, SupportSettings
from apps.wallets.models import Wallet
from apps.wallets.services import get_or_create_wallet, track_pending_deposit, freeze_funds, credit_wallet
from apps.common.decorators import staff_required, admin_required, support_required, finance_required, kyc_required

signer = TimestampSigner()

# ==========================================
# --- AUTHENTICATION HELPERS (V3) ---
# ==========================================

def v3_generate_otp(user, purpose):
    OTPToken.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    code = ''.join(random.choices(string.digits, k=6))
    expires_at = timezone.now() + timedelta(minutes=10)
    return OTPToken.objects.create(user=user, code=code, purpose=purpose, expires_at=expires_at)

def v3_send_otp_email(user, otp_token):
    subject = f"{otp_token.code} هو رمز التحقق الخاص بك | Raqamiyat"
    purpose_text = "لتفعيل حسابك" if otp_token.purpose == OTPToken.Purpose.REGISTRATION else \
                   "لتسجيل الدخول" if otp_token.purpose == OTPToken.Purpose.LOGIN else \
                   "لإتمام العملية"
    
    html_content = f"""
    <div dir="rtl" style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; color: #1e293b; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h2 style="color: #06b6d4; margin: 0; font-size: 24px; font-weight: 900;">رقميات | RAQAMIYAT</h2>
        </div>
        <div style="background-color: #f8fafc; padding: 30px; border-radius: 12px; text-align: center;">
            <p style="font-size: 16px; margin-bottom: 10px; color: #64748b;">رمز التحقق الخاص بك {purpose_text}:</p>
            <h1 style="font-size: 42px; font-weight: 900; color: #0f172a; margin: 0; letter-spacing: 10px;">{otp_token.code}</h1>
            <p style="font-size: 12px; margin-top: 20px; color: #94a3b8;">هذا الرمز صالح لمدة 10 دقائق فقط. لا تشارك هذا الرمز مع أي شخص.</p>
        </div>
        <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #f1f5f9; text-align: center;">
            <p style="font-size: 12px; color: #94a3b8; line-height: 1.6;">إذا لم تطلب هذا الرمز، يمكنك تجاهل هذا البريد الإلكتروني.<br>© 2026 رقميات لخدمات الوساطة الرقمية.</p>
        </div>
    </div>
    """
    return send_brevo_email(to_email=user.email, to_name=user.get_full_name() or user.email, subject=subject, html_content=html_content)

def v3_verify_otp_logic(user, code, purpose):
    otp = OTPToken.objects.filter(user=user, code=code, purpose=purpose, is_used=False, expires_at__gt=timezone.now()).first()
    if otp:
        otp.is_used = True; otp.save(update_fields=["is_used", "updated_at"]); return True
    return False

def v3_get_required_methods(user, action_type):
    method_map = {
        "login": user.security_login_method,
        "deposit": user.security_deposit_method,
        "purchase": user.security_purchase_method,
        "withdraw": user.security_withdraw_method
    }
    pref = method_map.get(action_type, "NONE")
    if pref == "NONE": return []
    if pref == "EMAIL": return ["EMAIL"]
    if pref == "APP":
        return ["APP"] if user.totp_enabled else ["EMAIL"]
    if pref == "BOTH":
        return ["APP", "EMAIL"] if user.totp_enabled else ["EMAIL"]
    return []

def v3_init_verification(request, user, action_type):
    methods = v3_get_required_methods(user, action_type)
    if not methods: return True
    request.session["v3_auth_uid"] = str(user.id)
    request.session["v3_auth_methods"] = methods
    request.session["v3_auth_purpose"] = action_type
    if methods[0] == "EMAIL":
        v3_send_otp_email(user, v3_generate_otp(user, action_type))
    return False

# ==========================================
# --- AUTH VIEWS (V3) ---
# ==========================================

def v3_login_view(request):
    if request.user.is_authenticated:
        return redirect("control_dashboard" if request.user.is_staff else "dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(request, username=form.cleaned_data["username"], password=form.cleaned_data["password"])
        if user:
            if not user.is_active:
                messages.error(request, "الحساب معطل.")
                return render(request, "site/v3/v3_login.html", {"form": form})
            
            # Ensure backend is set for session authentication
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            
            # Check security settings only if user exists
            if v3_init_verification(request, user, "login"):
                login(request, user)
                return redirect("control_dashboard" if user.is_staff else "dashboard")
            
            methods = request.session.get("v3_auth_methods", [])
            # Fallback if no specific security methods defined
            if not methods:
                login(request, user)
                return redirect("dashboard")
                
            return redirect("site_2fa_verify" if methods[0] == "APP" else "site_verify_otp")
        messages.error(request, "بيانات الدخول غير صحيحة.")
        messages.error(request, "بيانات الدخول غير صحيحة.")
    return render(request, "site/v3/v3_login.html", {"form": form})

def v3_register_view(request):
    if request.user.is_authenticated: return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = User.objects.create_user(email=form.cleaned_data["email"], password=form.cleaned_data["password"], phone=request.POST.get("phone"), first_name=form.cleaned_data["first_name"], last_name=form.cleaned_data["last_name"])
                get_or_create_wallet(user)
                otp = v3_generate_otp(user, OTPToken.Purpose.REGISTRATION)
                if v3_send_otp_email(user, otp):
                    request.session["v3_auth_uid"], request.session["v3_auth_purpose"] = str(user.id), OTPToken.Purpose.REGISTRATION
                    return redirect("site_verify_otp")
                else: raise Exception("فشل إرسال البريد الإلكتروني.")
        except Exception as e: form.add_error(None, str(e))
    return render(request, "site/v3/v3_register.html", {"form": form})

def v3_verify_otp_view(request):
    uid, purpose = request.session.get("v3_auth_uid"), request.session.get("v3_auth_purpose")
    if not uid: return redirect("site_login")
    user = get_object_or_404(User, id=uid)
    methods = request.session.get("v3_auth_methods", ["EMAIL"])
    settings_obj = KYCSettings.get_settings()
    current_cooldown_limit = min(settings_obj.otp_base_cooldown * (2 ** user.otp_resend_count), 600)
    last_otp = OTPToken.objects.filter(user=user, purpose=purpose).order_by("-created_at").first()
    remaining_cooldown = 0
    if last_otp:
        seconds_passed = (timezone.now() - last_otp.created_at).total_seconds()
        if seconds_passed < current_cooldown_limit: remaining_cooldown = int(current_cooldown_limit - seconds_passed)
    is_locked = False
    if user.otp_lockout_until and user.otp_lockout_until > timezone.now(): is_locked = True
    if request.method == "POST":
        if is_locked: return render(request, "site/v3/v3_otp_verify.html", {"user_email": user.email, "remaining_cooldown": remaining_cooldown, "is_locked": True})
        action = request.POST.get("action")
        if action == "resend":
            if remaining_cooldown > 0:
                messages.error(request, f"يرجى الانتظار {remaining_cooldown} ثانية.")
                return render(request, "site/v3/v3_otp_verify.html", {"user_email": user.email, "remaining_cooldown": remaining_cooldown})
            otp = v3_generate_otp(user, purpose)
            if v3_send_otp_email(user, otp):
                user.otp_resend_count += 1; user.save()
                messages.success(request, "تم إعادة إرسال الرمز.")
                return redirect("site_verify_otp")
        code = request.POST.get("code")
        if v3_verify_otp_logic(user, code, purpose):
            user.otp_failed_attempts = 0; user.otp_lockout_until = None; user.otp_resend_count = 0; user.save()
            if purpose == OTPToken.Purpose.REGISTRATION: user.email_verified = True; user.save()
            if purpose == "email_change":
                new_email = request.session.get("v3_new_email")
                if new_email:
                    user.email = new_email; user.username = new_email; user.save()
                    messages.success(request, "تم تغيير البريد الإلكتروني بنجاح.")
            
            remaining = [m for m in methods if m != "EMAIL"]
            request.session["v3_auth_methods"] = remaining
            if remaining and remaining[0] == "APP": return redirect("site_2fa_verify")
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            request.session["v3_action_verified_at"] = timezone.now().isoformat()
            keys = ["v3_auth_uid", "v3_auth_methods", "v3_auth_purpose", "v3_new_email"]
            for k in keys: 
                if k in request.session: del request.session[k]
            return redirect("control_dashboard" if user.is_staff else "dashboard")
        user.otp_failed_attempts += 1
        if user.otp_failed_attempts >= settings_obj.otp_max_attempts:
            user.otp_lockout_until = timezone.now() + timedelta(minutes=15)
            user.otp_failed_attempts = 0 
        user.save()
        messages.error(request, "رمز التحقق غير صحيح.")
    return render(request, "site/v3/v3_otp_verify.html", {"user_email": user.email, "remaining_cooldown": remaining_cooldown, "is_locked": is_locked})

def v3_2fa_verify_view(request):
    uid, purpose = request.session.get("v3_auth_uid"), request.session.get("v3_auth_purpose")
    if not uid: return redirect("site_login")
    user = get_object_or_404(User, id=uid)
    methods = request.session.get("v3_auth_methods", ["APP"])
    if request.method == "POST":
        code = request.POST.get("code")
        if user.totp_secret and pyotp.TOTP(user.totp_secret).verify(code):
            remaining = [m for m in methods if m != "APP"]
            request.session["v3_auth_methods"] = remaining
            if remaining and remaining[0] == "EMAIL":
                v3_send_otp_email(user, v3_generate_otp(user, purpose))
                return redirect("site_verify_otp")
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            request.session["v3_action_verified_at"] = timezone.now().isoformat()
            keys = ["v3_auth_uid", "v3_auth_methods", "v3_auth_purpose"]
            for k in keys: 
                if k in request.session: del request.session[k]
            return redirect("control_dashboard" if user.is_staff else "dashboard")
        messages.error(request, "الرمز غير صحيح.")
    return render(request, "site/v3/v3_2fa_verify.html")

@login_required
def v3_2fa_setup_view(request):
    user = request.user
    if user.totp_enabled:
        if request.method == "POST" and request.POST.get("action") == "disable":
            user.totp_enabled = False; user.totp_secret = None; user.save()
            messages.success(request, "تم تعطيل المصادقة الثنائية."); return redirect("site_2fa_setup")
        return render(request, "site/v3/v3_2fa_setup.html", {"enabled": True})
    if not user.totp_secret: user.totp_secret = pyotp.random_base32(); user.save()
    totp = pyotp.TOTP(user.totp_secret); provisioning_url = totp.provisioning_uri(name=user.email, issuer_name="Raqamiyat")
    qr = qrcode.QRCode(version=1, box_size=10, border=5); qr.add_data(provisioning_url); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white"); buffered = io.BytesIO(); img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()
    if request.method == "POST":
        if totp.verify(request.POST.get("code")):
            user.totp_enabled = True; user.save(); messages.success(request, "تم تفعيل المصادقة الثنائية بنجاح."); return redirect("dashboard")
        messages.error(request, "الرمز غير صحيح.")
    return render(request, "site/v3/v3_2fa_setup.html", {"qr_base64": qr_base64, "secret": user.totp_secret, "enabled": False})

def v3_forgot_password_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").lower().strip()
        user = User.objects.filter(email=email).first()
        if user:
            token = signer.sign(str(user.id))
            reset_url = request.build_absolute_uri(reverse('site_reset_password')) + f"?token={token}"
            subject = "رابط استعادة كلمة المرور | Raqamiyat"
            html_content = f"""
            <div dir="rtl" style="font-family: sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                <h2 style="color: #06b6d4;">رقميات | RAQAMIYAT</h2>
                <p>مرحباً،</p>
                <p>لقد طلبت إعادة تعيين كلمة المرور لحسابك. يرجى الضغط على الزر أدناه للمتابعة:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" style="display: inline-block; padding: 12px 25px; background-color: #06b6d4; color: white; text-decoration: none; border-radius: 8px; font-weight: bold;">إعادة تعيين كلمة المرور</a>
                </div>
                <p style="font-size: 12px; color: #999;">هذا الرابط صالح لمدة 10 دقائق فقط.</p>
            </div>
            """
            if send_brevo_email(user.email, user.get_full_name() or user.email, subject, html_content):
                return render(request, "site/v3/v3_forgot_password.html", {"sent": True})
            else:
                messages.error(request, "فشل إرسال البريد الإلكتروني. يرجى المحاولة لاحقاً.")
        else:
            messages.error(request, "البريد الإلكتروني غير مسجل لدينا.")
    return render(request, "site/v3/v3_forgot_password.html")

def v3_reset_password_view(request):
    token = request.GET.get("token") or request.POST.get("token")
    if not token: return redirect("site_forgot_password")
    try: uid = signer.unsign(token, max_age=600); user = get_object_or_404(User, id=uid)
    except Exception: messages.error(request, "الرابط منتهي الصلاحية."); return redirect("site_forgot_password")
    if request.method == "POST":
        p1, p2 = request.POST.get("password"), request.POST.get("confirm_password")
        if p1 and p1 == p2 and len(p1) >= 10:
            user.set_password(p1); user.save(); login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, "تم تغيير كلمة المرور."); return redirect("dashboard")
        messages.error(request, "كلمات المرور غير متطابقة.")
    return render(request, "site/v3/v3_reset_password.html", {"user_email": user.email, "token": token})

@login_required
def v3_logout_view(request):
    logout(request); return redirect("site_login")

def resend_verification(request): return redirect("dashboard")
def email_verify(request, uidb64, token): return redirect("site_login")

# ==========================================
# --- USER VIEWS (V3) ---
# ==========================================

@login_required
def dashboard(request):
    wallet = get_or_create_wallet(request.user)
    digital_deliveries = Order.objects.filter(customer=request.user, status=Order.Status.COMPLETED, is_delivery_read=False).exclude(fulfillment_data={})
    recent_orders = Order.objects.filter(customer=request.user).order_by('-created_at')[:5]
    recent_deposits = DepositRequest.objects.filter(user=request.user).order_by('-created_at')[:5]
    kyc_request = KYCRequest.objects.filter(user=request.user).first(); notifications = Notification.objects.filter(user=request.user, is_read=False)[:5]
    return render(request, "site/v3/v3_dashboard.html", {"wallet": wallet, "digital_deliveries": digital_deliveries, "orders": recent_orders, "deposits": recent_deposits, "kyc_request": kyc_request, "notifications": notifications})

@login_required
def wallet_page(request):
    request.user.reset_daily_limits_if_needed()
    wallet = Wallet.objects.filter(user=request.user).select_related("currency").first() or get_or_create_wallet(request.user)
    if request.method == "POST":
        if not v3_init_verification(request, request.user, "deposit"):
            last_verified = request.session.get("v3_action_verified_at")
            if not last_verified or (timezone.now() - timezone.datetime.fromisoformat(last_verified)).total_seconds() > 300:
                methods = request.session.get("v3_auth_methods", [])
                return redirect("site_2fa_verify" if methods[0] == "APP" else "site_verify_otp")
    return render(request, "site/wallet.html", {"wallet": wallet, "ledger_entries": wallet.ledger_entries.all()[:20]})

@login_required
def orders_list(request): return render(request, "site/orders_list.html", {"orders": request.user.orders.all().prefetch_related('items__variant__product')})

@login_required
def order_detail(request, pk): return render(request, "site/order_detail.html", {"order": get_object_or_404(request.user.orders.prefetch_related('items__variant__product', 'logs'), pk=pk)})

@login_required
def deposits(request):
    if request.method == "POST":
        method_id, amount = request.POST.get("method_id"), Decimal(request.POST.get("amount", "0"))
        if method_id and amount > 0:
            method = get_object_or_404(PaymentMethod, id=method_id)
            track_pending_deposit(request.user.wallet.id, amount, reference=f"dep_req_{timezone.now().timestamp()}", reason=f"Deposit via {method.name}")
            DepositRequest.objects.create(user=request.user, payment_method=method, amount=amount, status=DepositRequest.Status.PENDING)
            messages.success(request, "تم تقديم الطلب."); return redirect("dashboard_deposits")
    return render(request, "site/v3/v3_deposits.html", {"methods": PaymentMethod.objects.filter(is_active=True), "requests": DepositRequest.objects.filter(user=request.user).order_by('-created_at')})

@login_required
def withdrawals(request):
    if request.method == "POST":
        method_id, amount, address = request.POST.get("method_id"), Decimal(request.POST.get("amount", "0")), request.POST.get("address")
        if method_id and amount > 0:
            if not v3_init_verification(request, request.user, "withdraw"):
                last_verified = request.session.get("v3_action_verified_at")
                if not last_verified or (timezone.now() - timezone.datetime.fromisoformat(last_verified)).total_seconds() > 300:
                    methods = request.session.get("v3_auth_methods", [])
                    return redirect("site_2fa_verify" if methods[0] == "APP" else "site_verify_otp")
            method = get_object_or_404(PaymentMethod, id=method_id)
            try:
                freeze_funds(request.user.wallet.id, amount, reference=f"with_req_{timezone.now().timestamp()}", reason=f"Withdrawal via {method.name}")
                WithdrawalRequest.objects.create(user=request.user, payment_method=method, amount=amount, withdrawal_address=address, status=WithdrawalRequest.Status.PENDING)
                messages.success(request, "تم تقديم طلب السحب."); return redirect("dashboard_withdrawals")
            except Exception as e: messages.error(request, str(e))
    return render(request, "site/v3/v3_withdrawals.html", {"methods": PaymentMethod.objects.filter(is_active=True, allow_withdrawal=True), "requests": WithdrawalRequest.objects.filter(user=request.user).order_by('-created_at')})

@login_required
def kyc_request_view(request):
    existing = KYCRequest.objects.filter(user=request.user).first()
    if existing and existing.status in [KYCRequest.Status.PENDING, KYCRequest.Status.VERIFIED]: return render(request, "site/v3/v3_kyc_status.html", {"kyc": existing})
    form = KYCRequestForm(request.POST or None, request.FILES or None, instance=existing)
    if request.method == "POST" and form.is_valid():
        kyc = form.save(commit=False); kyc.user, kyc.status = request.user, KYCRequest.Status.PENDING; kyc.save()
        notify_bulk(User.objects.filter(role=User.Role.ADMIN), title="طلب توثيق جديد", body=f"مستخدم: {request.user.email}", action_url=f"/control/kyc/{kyc.id}/")
        messages.success(request, "تم تقديم الطلب."); return redirect("dashboard")
    return render(request, "site/v3/v3_kyc_form.html", {"form": form})

@login_required
def notification_settings(request):
    settings_obj, _ = NotificationSetting.objects.get_or_create(user=request.user)
    if request.method == "POST":
        for field in ['in_app_orders', 'push_orders', 'in_app_financial', 'push_financial', 'in_app_support', 'push_support', 'in_app_promotions', 'push_promotions']: setattr(settings_obj, field, request.POST.get(field) == "on")
        settings_obj.save(); messages.success(request, "تم الحفظ."); return redirect("notification_settings")
    return render(request, "site/notification_settings.html", {"settings": settings_obj})

@login_required
def v3_change_password_view(request):
    form = ChangePasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if request.user.check_password(form.cleaned_data["current_password"]):
            request.user.set_password(form.cleaned_data["new_password"]); request.user.save(); update_session_auth_hash(request, request.user)
            messages.success(request, "تم تغيير كلمة المرور بنجاح."); return redirect("dashboard")
        else: messages.error(request, "كلمة المرور الحالية غير صحيحة.")
    return render(request, "site/v3/v3_change_password.html", {"form": form})

@login_required
def v3_change_email_view(request):
    if request.method == "POST":
        new_email = request.POST.get("new_email", "").lower().strip()
        if User.objects.filter(email=new_email).exists(): messages.error(request, "البريد الإلكتروني مستخدم بالفعل.")
        else:
            otp = v3_generate_otp(request.user, "email_change")
            if v3_send_otp_email(request.user, otp):
                request.session["v3_auth_uid"], request.session["v3_auth_purpose"] = str(request.user.id), "email_change"; request.session["v3_new_email"] = new_email
                return redirect("site_verify_otp")
            messages.error(request, "فشل إرسال الرمز.")
    return render(request, "site/v3/v3_change_email.html")

# ==========================================
# --- CATALOG & AJAX ---
# ==========================================

def home(request):
    categories = Category.objects.filter(is_active=True).order_by("sort_order", "name")
    stats = {"products": Product.objects.filter(is_active=True).count(), "categories": categories.count(), "orders": Order.objects.count(), "tickets": ChatRoom.objects.exclude(status=ChatRoom.Status.CLOSED).count(), "users": User.objects.count()}
    return render(request, "site/home.html", {"featured_products": Product.objects.filter(is_active=True, is_featured=True).select_related("category")[:6], "top_products": Product.objects.filter(is_active=True).order_by("sort_order")[:8], "categories": categories, "stats": stats})

def catalog(request):
    cat_id, q, sort = request.GET.get("category"), request.GET.get("q", "").strip(), request.GET.get("sort", "newest")
    products = Product.objects.filter(is_active=True).select_related("category").prefetch_related("variants")
    if cat_id: products = products.filter(category_id=cat_id)
    if q: products = products.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if sort == "price_low": products = products.order_by("variants__price")
    elif sort == "price_high": products = products.order_by("-variants__price")
    else: products = products.order_by("-created_at")
    return render(request, "site/catalog.html", {"categories": Category.objects.filter(is_active=True).annotate(product_count=Count('products', filter=Q(products__is_active=True))).order_by("sort_order"), "products": products.distinct(), "active_category": cat_id, "query": q, "sort": sort})

@login_required
def v3_security_triggers_view(request):
    user = request.user
    if request.method == "POST":
        user.security_login_method = request.POST.get("login_method")
        user.security_deposit_method = request.POST.get("deposit_method")
        user.security_purchase_method = request.POST.get("purchase_method")
        user.security_withdraw_method = request.POST.get("withdraw_method")
        user.save(); messages.success(request, "تم تحديث إعدادات الأمان بنجاح."); return redirect("site_security_triggers")
    return render(request, "site/v3/v3_security_triggers.html")

def product_detail(request, pk):
    product = get_object_or_404(Product.objects.prefetch_related('variants'), pk=pk, is_active=True)
    if request.method == "POST":
        if not request.user.is_authenticated: return redirect("site_login")
        if not v3_init_verification(request, request.user, "purchase"):
            last_verified = request.session.get("v3_action_verified_at")
            if not last_verified or (timezone.now() - timezone.datetime.fromisoformat(last_verified)).total_seconds() > 300:
                methods = request.session.get("v3_auth_methods", [])
                return redirect("site_2fa_verify" if methods[0] == "APP" else "site_verify_otp")
    return render(request, "site/product_detail.html", {"product": product})

def ajax_validate_coupon(request):
    try:
        variant = ProductVariant.objects.get(id=request.GET.get("variant_id"))
        coupon = Coupon.objects.filter(code__iexact=request.GET.get("code", ""), is_active=True).first()
        if not coupon: return JsonResponse({"valid": False, "error": "غير صالح"})
        price = variant.price; return JsonResponse({"valid": True, "discount_amount": 0, "new_total": float(price)})
    except Exception as e: return JsonResponse({"valid": False, "error": str(e)})

# ==========================================
# --- ADMINISTRATIVE VIEWS (V4) ---
# ==========================================

@staff_required
def control_dashboard(request):
    from apps.payments.models import DepositRequest, WithdrawalRequest
    stats = {"users": User.objects.count(), "pending_deposits": DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).count(), "pending_withdrawals": WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PENDING).count(), "open_tickets": ChatRoom.objects.exclude(status=ChatRoom.Status.CLOSED).count()}
    return render(request, "site/control_dashboard.html", {"stats": stats, "recent_orders": Order.objects.select_related('customer').order_by('-created_at')[:5], "recent_deposits": DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).order_by('-created_at')[:5], "recent_users": User.objects.order_by('-date_joined')[:5]})

@finance_required
def control_deposits(request): return render(request, "site/control_deposits.html", {"requests": DepositRequest.objects.select_related('user', 'payment_method').all().order_by('-created_at')})

@finance_required
def control_withdrawals(request): return render(request, "site/control_withdrawals.html", {"requests": WithdrawalRequest.objects.select_related('user', 'payment_method').all().order_by('-created_at')})

@finance_required
def control_deposit_detail(request, pk): return render(request, "site/control_deposit_detail.html", {"deposit": get_object_or_404(DepositRequest.objects.select_related('user', 'currency', 'payment_method'), pk=pk)})

@finance_required
def control_withdrawal_detail(request, pk): return render(request, "site/control_withdrawal_detail.html", {"withdrawal": get_object_or_404(WithdrawalRequest.objects.select_related('user'), pk=pk)})

@support_required
def control_kycs_list(request): return render(request, "site/control_kycs_list.html", {"requests": KYCRequest.objects.select_related('user').all().order_by('-created_at')})

@support_required
def control_kyc_detail(request, pk):
    kyc = get_object_or_404(KYCRequest.objects.select_related('user'), pk=pk)
    if request.method == "POST":
        if request.POST.get("action") == "approve": kyc.status = KYCRequest.Status.VERIFIED; kyc.user.is_kyc_verified = True; kyc.user.save(); kyc.save()
        return redirect("control_kycs_list")
    return render(request, "site/control_kyc_detail.html", {"kyc": kyc})

@kyc_required
def control_kyc_settings(request):
    obj = KYCSettings.get_settings(); form = KYCSettingsForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid(): form.save(); messages.success(request, "تم الحفظ."); return redirect("control_kyc_settings")
    return render(request, "site/control_kyc_settings.html", {"form": form, "settings": obj})

@support_required
def control_orders_list(request):
    orders = Order.objects.select_related('customer').all().order_by('-created_at')
    if request.GET.get('status'): orders = orders.filter(status=request.GET.get('status'))
    if request.GET.get('q'): orders = orders.filter(Q(number__icontains=request.GET.get('q')) | Q(customer__email__icontains=request.GET.get('q')))
    return render(request, "site/control_orders_list.html", {"orders": orders, "order_status_choices": Order.Status.choices})

@support_required
def control_order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related('customer'), pk=pk)
    if request.method == "POST":
        if request.POST.get("action") == "update_status":
            order.status = request.POST.get("status"); order.save(); OrderLog.objects.create(order=order, status=order.status, note=request.POST.get("admin_note", ""), created_by=request.user)
            if order.status in [Order.Status.REFUNDED, Order.Status.CANCELLED]: credit_wallet(order.customer.wallet.id, order.total_amount, f"refund:{order.id}", f"Refund for #{order.number}", request.user)
        return redirect("control_order_detail", pk=pk)
    return render(request, "site/control_order_detail.html", {"order": order})

@admin_required
def control_users_list(request): return render(request, "site/control_users_list.html", {"users": User.objects.select_related("wallet").order_by("-date_joined")})

@admin_required
def control_user_moderate(request, public_uuid):
    user = get_object_or_404(User, public_uuid=public_uuid); form = ModerateUserForm(request.POST or None, instance=user)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "change_email":
            new_email = request.POST.get("new_email", "").strip().lower()
            if new_email and "@" in new_email:
                if User.objects.filter(email=new_email).exclude(id=user.id).exists(): messages.error(request, "هذا البريد مستخدم بالفعل.")
                else: user.email = new_email; user.username = new_email; user.save(); messages.success(request, f"تم تغيير البريد إلى {new_email}")
            return redirect("control_user_moderate", public_uuid=public_uuid)
        elif action == "reset_otp": user.otp_failed_attempts = 0; user.otp_lockout_until = None; user.otp_resend_count = 0; user.save(); messages.success(request, "تم إعادة ضبط قيود الرمز."); return redirect("control_user_moderate", public_uuid=public_uuid)
        elif action == "reset_2fa": user.totp_enabled = False; user.totp_secret = None; user.save(); messages.success(request, "تم تعطيل 2FA للمستخدم."); return redirect("control_user_moderate", public_uuid=public_uuid)
        elif form.is_valid(): form.save(); messages.success(request, "تم التحديث."); return redirect("control_users_list")
    return render(request, "site/control_user_moderate.html", {"form": form, "user_to_moderate": user})

@admin_required
def currencies_list(request):
    if request.method == "POST":
        for c in Currency.objects.all():
            buy, sell = request.POST.get(f"buy_rate_{c.id}"), request.POST.get(f"sell_rate_{c.id}")
            if buy and sell: c.buy_rate, c.sell_rate = Decimal(buy), Decimal(sell); c.save()
        return redirect("currencies_list")
    return render(request, "site/currencies_list.html", {"currencies": Currency.objects.all().order_by('display_order')})

@admin_required
def currency_create(request):
    form = CurrencyForm(request.POST or None)
    if request.method == "POST" and form.is_valid(): form.save(); return redirect("currencies_list")
    return render(request, "site/currency_form.html", {"form": form})

@admin_required
def currency_edit(request, pk):
    c = get_object_or_404(Currency, pk=pk); form = CurrencyForm(request.POST or None, instance=c)
    if request.method == "POST" and form.is_valid(): form.save(); return redirect("currencies_list")
    return render(request, "site/currency_form.html", {"form": form, "currency": c})

@support_required
def control_products_list(request): return render(request, "site/control_products_list.html", {"products": Product.objects.select_related('category').prefetch_related('variants').all().order_by('sort_order', 'name')})

@support_required
@transaction.atomic
def control_product_create(request):
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save(); v_json = request.POST.get("variants_json")
        if v_json:
            for v in json.loads(v_json): ProductVariant.objects.create(product=product, name=v.get('name'), sku=v.get('sku'), price=Decimal(str(v.get('price', '0'))), cost=Decimal(str(v.get('cost', '0'))), sort_order=int(v.get('sort_order', 0)), is_active=v.get('is_active', True))
        return redirect("control_products_list")
    return render(request, "site/control_product_builder.html", {"form": form, "variants_json_data": []})

@support_required
@transaction.atomic
def control_product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk); form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        product = form.save(); v_json = request.POST.get("variants_json")
        if v_json:
            v_data = json.loads(v_json); product.variants.exclude(sku__in=[v.get('sku') for v in v_data if v.get('sku')]).delete()
            for v in v_data: ProductVariant.objects.update_or_create(product=product, sku=v.get('sku'), defaults={"name": v.get('name'), "price": Decimal(str(v.get('price', '0'))), "cost": Decimal(str(v.get('cost', '0'))), "sort_order": int(v.get('sort_order', 0)), "is_active": v.get('is_active', True)})
        return redirect("control_products_list")
    v_list = [{"name": v.name, "sku": v.sku, "price": str(v.price), "cost": str(v.cost), "sort_order": v.sort_order, "is_active": v.is_active} for v in product.variants.all().order_by('sort_order')]
    return render(request, "site/control_product_builder.html", {"form": form, "product": product, "variants_json_data": v_list})

@admin_required
def control_announcements(request): return render(request, "site/control_announcements.html", {"announcements": SiteAnnouncement.objects.all().order_by("-created_at")})

@admin_required
def control_announcement_create(request):
    form = SiteAnnouncementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data.get("is_active"): SiteAnnouncement.objects.filter(is_active=True).update(is_active=False)
        form.save(); return redirect("control_announcements")
    return render(request, "site/control_announcement_form.html", {"form": form})

@admin_required
def control_announcement_edit(request, pk):
    ann = get_object_or_404(SiteAnnouncement, pk=pk); form = SiteAnnouncementForm(request.POST or None, instance=ann)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data.get("is_active"): SiteAnnouncement.objects.filter(is_active=True).exclude(pk=pk).update(is_active=False)
        form.save(); return redirect("control_announcements")
    return render(request, "site/control_announcement_form.html", {"form": form})

@admin_required
def control_announcement_delete(request, pk): get_object_or_404(SiteAnnouncement, pk=pk).delete(); return redirect("control_announcements")

@admin_required
def control_social_media(request):
    from apps.site.forms import SocialMediaLinkForm
    if request.method == "POST":
        f = SocialMediaLinkForm(request.POST, request.FILES, instance=SocialMediaLink.objects.filter(pk=request.POST.get("pk")).first())
        if f.is_valid(): f.save(); messages.success(request, "تم الحفظ."); return redirect("control_social_media")
    return render(request, "site/control_social_media.html", {"links": SocialMediaLink.objects.all(), "form": SocialMediaLinkForm()})

@admin_required
def control_social_media_delete(request, pk): get_object_or_404(SocialMediaLink, pk=pk).delete(); return redirect("control_social_media")

@support_required
def control_category_create_ajax(request):
    if request.POST.get('name'): cat = Category.objects.create(name=request.POST.get('name')); return JsonResponse({"id": str(cat.id), "name": cat.name})
    return JsonResponse({"error": "Name required"}, status=400)

@finance_required
def control_wallets_list(request):
    q = request.GET.get('q', ''); wallets = Wallet.objects.select_related('user', 'currency').all().order_by('-updated_at')
    if q: wallets = wallets.filter(Q(user__email__icontains=q) | Q(user__first_name__icontains=q))
    return render(request, "site/control_wallets_list.html", {"wallets": wallets, "query": q})

@finance_required
def control_debts(request):
    q = request.GET.get('q', ''); users = User.objects.select_related('wallet').filter(Q(email__icontains=q) | Q(phone__icontains=q)) if q else User.objects.select_related('wallet').all()
    if request.method == "POST":
        target = get_object_or_404(User, id=request.POST.get("user_id")); amt = Decimal(request.POST.get("amount", "0"))
        if request.POST.get("action") == "add_debt":
            from apps.wallets.services import add_debt; add_debt(target.wallet.id, amt, f"admin_debt_{timezone.now().timestamp()}", request.POST.get("reason", ""), request.user)
        return redirect(f"{request.path}?q={q}")
    return render(request, "site/control_debts.html", {"users": users, "query": q})

@support_required
def control_send_notification(request):
    form = SendNotificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        users = User.objects.filter(is_active=True)
        if form.cleaned_data["target"] == "tier": users = users.filter(tier=form.cleaned_data["tier"])
        elif form.cleaned_data["target"] == "individual": users = users.filter(email=form.cleaned_data["user_email"])
        if users.exists(): notify_bulk(users, form.cleaned_data["title"], form.cleaned_data["body"], action_url=form.cleaned_data["action_url"]); messages.success(request, "تم الإرسال."); return redirect("control_send_notification")
    return render(request, "site/control_notification_form.html", {"form": form})

@admin_required
def control_support_settings(request):
    obj, _ = SupportSettings.objects.get_or_create(id=1); form = SupportSettingsForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid(): form.save(); messages.success(request, "تم الحفظ."); return redirect("control_support_settings")
    return render(request, "site/control_support_settings.html", {"form": form})

@support_required
def control_quick_replies(request): return render(request, "site/control_quick_replies.html", {"replies": ChatCannedReply.objects.all().order_by("-created_at")})

@support_required
def control_quick_reply_create(request):
    form = ChatCannedReplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid(): form.save(); return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})

@support_required
def control_quick_reply_edit(request, pk):
    reply = get_object_or_404(ChatCannedReply, pk=pk); form = ChatCannedReplyForm(request.POST or None, instance=reply)
    if request.method == "POST" and form.is_valid(): form.save(); return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})

@support_required
def control_quick_reply_delete(request, pk): get_object_or_404(ChatCannedReply, pk=pk).delete(); return redirect("control_quick_replies")

@support_required
def control_support_chat_open(request):
    form = AdminChatForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.filter(email=form.cleaned_data["user_email"]).first()
        if user:
            with transaction.atomic():
                room = ChatRoom.objects.create(user=user, assigned_agent=request.user, subject=form.cleaned_data["subject"], status=ChatRoom.Status.ASSIGNED)
                ChatMessage.objects.create(room=room, sender=request.user, text=form.cleaned_data["message"], is_staff_reply=True); room.unread_user_count = 1; room.save()
                notify_user(user, title="رسالة من الدعم", body=room.subject, action_url=reverse("dashboard"), category='support')
            return redirect("dashboard")
        messages.error(request, "المستخدم غير موجود.")
    return render(request, "site/control_support_chat_open.html", {"form": form})

@admin_required
def control_coupons_list(request): return render(request, "site/control_coupons_list.html", {"coupons": Coupon.objects.all().order_by("-created_at")})
@admin_required
def control_coupon_create(request):
    form = CouponForm(request.POST or None)
    if request.method == "POST" and form.is_valid(): form.save(); return redirect("control_coupons_list")
    return render(request, "site/control_coupon_form.html", {"form": form})
@admin_required
def control_coupon_edit(request, pk):
    c = get_object_or_404(Coupon, pk=pk); form = CouponForm(request.POST or None, instance=c)
    if request.method == "POST" and form.is_valid(): form.save(); return redirect("control_coupons_list")
    return render(request, "site/control_coupon_form.html", {"form": form})
@admin_required
def control_coupon_delete(request, pk): get_object_or_404(Coupon, pk=pk).delete(); return redirect("control_coupons_list")

@admin_required
def control_reports(request): return render(request, "site/control_reports.html")
@support_required
def control_variant_create(request, product_pk): return redirect("control_product_edit", pk=product_pk)
@support_required
def control_variant_edit(request, pk): v = get_object_or_404(ProductVariant, pk=pk); return redirect("control_product_edit", pk=v.product.id)

def terms_of_service(request): return render(request, "site/terms_of_service.html")
def refund_policy(request): return render(request, "site/refund_policy.html")
def contact_page(request): return render(request, "site/contact.html")
def privacy_policy(request): return render(request, "site/privacy_policy.html")
def service_worker(request): return HttpResponse(open("apps/site/static/site/js/sw.js").read() if os.path.exists("apps/site/static/site/js/sw.js") else "", content_type="application/javascript")
def set_currency(request):
    curr = Currency.objects.filter(id=request.GET.get("currency") or request.POST.get("currency"), is_active=True).first()
    if curr:
        request.session["preferred_currency_id"] = str(curr.id)
        if request.user.is_authenticated: request.user.preferred_currency = curr; request.user.save(update_fields=["preferred_currency"])
    return redirect(request.META.get('HTTP_REFERER', 'home'))

@admin_required
def payment_methods_list(request): return render(request, "site/payment_methods_list.html", {"methods": PaymentMethod.objects.all().order_by("display_order")})
@admin_required
def payment_method_create(request):
    form = PaymentMethodForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid(): form.save(); return redirect("payment_methods_list")
    return render(request, "site/payment_method_builder.html", {"form": form})
@admin_required
def payment_method_edit(request, pk):
    method = get_object_or_404(PaymentMethod, pk=pk); form = PaymentMethodForm(request.POST or None, request.FILES or None, instance=method)
    if request.method == "POST" and form.is_valid(): form.save(); return redirect("payment_methods_list")
    return render(request, "site/payment_method_builder.html", {"form": form, "method": method})
