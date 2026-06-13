import json
import uuid
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

from apps.accounts.models import User, OTPToken, KYCRequest, KYCSettings, ActivityLog
from apps.accounts.services import send_brevo_email
from apps.catalog.models import Category, Product, ProductVariant
from apps.common.models import Currency, SocialMediaLink, SiteAnnouncement
from apps.notifications.models import Notification, NotificationSetting
from apps.notifications.services import notify_bulk, notify_user
from apps.orders.models import Order, OrderLog, Coupon, OrderItem
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest
from apps.site.forms import (
    LoginForm, RegisterForm, PaymentMethodForm, CurrencyForm, ModerateUserForm, 
    ProductForm, KYCRequestForm, KYCSettingsForm, ChangePasswordForm, 
    CouponForm, SendNotificationForm, AdminChatForm, SiteAnnouncementForm, 
    ChatCannedReplyForm, SupportSettingsForm
)
from apps.support.models import ChatRoom, ChatMessage, ChatCannedReply, SupportSettings
from apps.wallets.models import Wallet
from apps.wallets.services import (
    get_or_create_wallet, track_pending_deposit, freeze_funds, credit_wallet,
    debit_wallet, finalize_withdrawal, release_funds
)
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

def v3_security_redirect(methods):
    if not methods: return redirect("dashboard")
    m = methods[0]
    if m == "APP": return redirect("site_2fa_verify")
    if m == "SP": return redirect("site_sp_verify")
    return redirect("site_verify_otp")

def v3_get_required_methods(user, action_type):
    method_map = {
        "login": user.security_login_method,
        "deposit": user.security_deposit_method,
        "purchase": user.security_purchase_method,
        "withdraw": user.security_withdraw_method,
        "settings": "SP" if user.security_password_enabled else "NONE"
    }
    pref = method_map.get(action_type, "NONE")
    if pref == "NONE": return []
    if pref == "EMAIL": return ["EMAIL"]
    if pref == "APP":
        return ["APP"] if user.totp_enabled else ["EMAIL"]
    if pref == "BOTH":
        return ["APP", "EMAIL"] if user.totp_enabled else ["EMAIL"]
    if pref == "SP":
        return ["SP"] if user.security_password else ["EMAIL"]
    return []

def v3_init_verification(request, user, action_type):
    # Check if user has any security methods enabled
    methods = v3_get_required_methods(user, action_type)
    if not methods: 
        return True # No security methods configured, bypass
    
    # Check for 5-minute cooldown
    last_verified = request.session.get("v3_action_verified_at")
    if last_verified:
        try:
            if (timezone.now() - timezone.datetime.fromisoformat(last_verified)).total_seconds() < 300:
                return True # Within 5-minute cooldown, bypass
        except:
            pass
            
    # Proceed with verification
    request.session["v3_auth_uid"] = str(user.id)
    request.session["v3_auth_methods"] = methods
    request.session["v3_auth_purpose"] = action_type
    
    first_method = methods[0]
    if first_method == "EMAIL":
        v3_send_otp_email(user, v3_generate_otp(user, action_type))
        return False # Stay for redirect or handle in caller
    elif first_method == "SP":
        # Handled by redirect in caller or here
        pass
    
    return False

def v3_redirect_to_verification(request, methods):
    if not methods: return redirect("dashboard")
    first = methods[0]
    if first == "EMAIL": return redirect("site_verify_otp")
    if first == "APP": return redirect("site_2fa_verify")
    if first == "SP": return redirect("site_sp_verify")
    return redirect("dashboard")

def v3_verify_sp_view(request):
    uid, purpose = request.session.get("v3_auth_uid"), request.session.get("v3_auth_purpose")
    if not uid: return redirect("site_login")
    user = get_object_or_404(User, id=uid)
    methods = request.session.get("v3_auth_methods", ["SP"])
    
    if request.method == "POST":
        password = request.POST.get("password")
        if user.security_password and check_password_hash(password, user.security_password):
            remaining = [m for m in methods if m != "SP"]
            request.session["v3_auth_methods"] = remaining
            
            if remaining:
                next_method = remaining[0]
                if next_method == "EMAIL":
                    v3_send_otp_email(user, v3_generate_otp(user, purpose))
                    return redirect("site_verify_otp")
                elif next_method == "APP":
                    return redirect("site_2fa_verify")
            
            # All verified
            if not request.user.is_authenticated:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            
            request.session["v3_action_verified_at"] = timezone.now().isoformat()
            
            # Completion logic for pending actions
            pending_action_id = request.session.get("v3_pending_action_id")
            if pending_action_id:
                from apps.payments.models import DepositRequest, WithdrawalRequest
                deposit = DepositRequest.objects.filter(id=pending_action_id, user=user).first()
                if deposit:
                    deposit.is_verified = True; deposit.save(update_fields=["is_verified"])
                    messages.success(request, "تم التحقق والموافقة على الإيداع.")
                    del request.session["v3_pending_action_id"]
                    return redirect("dashboard_deposits")
                
                withdrawal = WithdrawalRequest.objects.filter(id=pending_action_id, user=user).first()
                if withdrawal:
                    withdrawal.is_verified = True; withdrawal.save(update_fields=["is_verified"])
                    messages.success(request, "تم التحقق والموافقة على السحب.")
                    del request.session["v3_pending_action_id"]
                    return redirect("dashboard_withdrawals")

            keys = ["v3_auth_uid", "v3_auth_methods", "v3_auth_purpose", "v3_new_email", "v3_pending_action_id"]
            for k in keys:
                if k in request.session: del request.session[k]
            return redirect("control_dashboard" if user.is_staff else "dashboard")
            
        messages.error(request, "كلمة مرور الحماية غير صحيحة.")
        
    return render(request, "site/v3/v3_sp_verify.html", {"purpose": purpose})

# ==========================================
# --- AUTH VIEWS (V3) ---
# ==========================================

def v3_login_view(request):
    if request.user.is_authenticated:
        return redirect("control_dashboard" if request.user.is_staff else "dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(request, username=form.cleaned_data["email"], password=form.cleaned_data["password"])
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

            # Check for pending action (Deposit/Withdrawal)
            pending_action_id = request.session.get("v3_pending_action_id")
            if pending_action_id:
                from apps.payments.models import DepositRequest, WithdrawalRequest
                # Try deposit first
                deposit = DepositRequest.objects.filter(id=pending_action_id, user=user).first()
                if deposit:
                    deposit.is_verified = True
                    deposit.save(update_fields=["is_verified"])
                    messages.success(request, "تم التحقق وإرسال طلب الإيداع بنجاح.")
                    del request.session["v3_pending_action_id"]
                    return redirect("dashboard_deposits")

                # Then withdrawal
                withdrawal = WithdrawalRequest.objects.filter(id=pending_action_id, user=user).first()
                if withdrawal:
                    withdrawal.is_verified = True
                    withdrawal.save(update_fields=["is_verified"])
                    messages.success(request, "تم التحقق وإرسال طلب السحب بنجاح.")
                    del request.session["v3_pending_action_id"]
                    return redirect("dashboard_withdrawals")

            keys = ["v3_auth_uid", "v3_auth_methods", "v3_auth_purpose", "v3_new_email", "v3_pending_action_id"]
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
    if not v3_init_verification(request, request.user, "settings"):
        return v3_security_redirect(request.session.get("v3_auth_methods", []))
        
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
    uid = request.GET.get("uid") or request.POST.get("uid")
    if not token or not uid: return redirect("site_forgot_password")
    user = get_object_or_404(User, id=uid)
    from django.contrib.auth.tokens import default_token_generator
    if not default_token_generator.check_token(user, token):
        messages.error(request, "الرابط غير صالح أو منتهي الصلاحية."); return redirect("site_forgot_password")
    if request.method == "POST":
        p1, p2 = request.POST.get("password"), request.POST.get("confirm_password")
        if p1 and p1 == p2 and len(p1) >= 10:
            user.set_password(p1); user.save(); 
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, "تم تغيير كلمة المرور بنجاح. تم تسجيل دخولك تلقائياً.")
            return redirect("dashboard")
        messages.error(request, "كلمات المرور غير متطابقة أو لا تستوفي شروط الطول (10 خانات على الأقل).")
    return render(request, "site/v3/v3_reset_password.html", {"user_email": user.email, "token": token, "uid": uid})

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
    recent_withdrawals = WithdrawalRequest.objects.filter(user=request.user).order_by('-created_at')[:5]
    kyc_request = KYCRequest.objects.filter(user=request.user).first(); notifications = Notification.objects.filter(user=request.user, is_read=False)[:5]
    return render(request, "site/v3/v3_dashboard.html", {
        "wallet": wallet, "digital_deliveries": digital_deliveries, 
        "orders": recent_orders, "deposits": recent_deposits, 
        "withdrawals": recent_withdrawals, "kyc_request": kyc_request, 
        "notifications": notifications
    })

@login_required
def wallet_page(request):
    request.user.reset_daily_limits_if_needed()
    wallet = Wallet.objects.filter(user=request.user).select_related("currency").first() or get_or_create_wallet(request.user)
    
    show_all = request.GET.get("show_all") == "1"
    ledger_entries = wallet.ledger_entries.all()
    if not show_all:
        ledger_entries = ledger_entries[:20]
        
    return render(request, "site/wallet.html", {
        "wallet": wallet, 
        "ledger_entries": ledger_entries,
        "show_all": show_all
    })

@login_required
def orders_list(request): return render(request, "site/orders_list.html", {"orders": request.user.orders.all().prefetch_related('items__variant__product')})

@login_required
def order_detail(request, pk): return render(request, "site/order_detail.html", {"order": get_object_or_404(request.user.orders.prefetch_related('items__variant__product', 'logs'), pk=pk)})

from django.contrib.auth.hashers import make_password, check_password as check_password_hash

# ... (rest of imports)

@login_required
def deposits(request):
    if request.method == "POST":
        method_id = request.POST.get("payment_method")
        currency_id = request.POST.get("currency")
        amount_str = request.POST.get("amount", "0")
        proof_image = request.FILES.get("proof_image")
        
        # Validation
        if not method_id or not currency_id:
            messages.error(request, "بيانات وسيلة الدفع أو العملة ناقصة.")
            return redirect("dashboard_deposits")
            
        method = get_object_or_404(PaymentMethod, id=method_id, is_active=True, can_deposit=True)
        currency = get_object_or_404(Currency, id=currency_id, is_active=True)
        
        # Security check: Does currency belong to method?
        if not method.supported_currencies.filter(id=currency.id).exists():
            messages.error(request, "العملة المختارة غير مدعومة لهذه الوسيلة.")
            return redirect("dashboard_deposits")

        try:
            amount = Decimal(amount_str)
            if amount <= 0: raise ValueError()
        except:
            messages.error(request, "يرجى إدخال مبلغ صحيح.")
            return redirect("dashboard_deposits")

        # Extract metadata from custom fields
        metadata = {}
        schema = method.deposit_form_schema
        for field in schema.get("fields", []) if isinstance(schema, dict) else []:
            field_name = field.get("name") or field.get("id") or field.get("key") or field.get("label")
            
            if field.get("type") == "image":
                val_file = request.FILES.get(f"custom_{field_name}")
                if val_file:
                    from django.core.files.storage import default_storage
                    path = default_storage.save(f"deposit-proofs/metadata/{val_file.name}", val_file)
                    val = f"{settings.MEDIA_URL}{path}"
                else:
                    val = ""
            else:
                val = request.POST.get(f"custom_{field_name}")

            if field.get("required") and not val:
                messages.error(request, f"الحقل {field.get('label')} مطلوب.")
                return redirect("dashboard_deposits")
            metadata[field_name] = val

        # Create the request (unverified first)
        with transaction.atomic():
            deposit = DepositRequest.objects.create(
                user=request.user,
                payment_method=method,
                currency=currency,
                amount=amount,
                proof_image=proof_image,
                metadata=metadata,
                status=DepositRequest.Status.PENDING,
                is_verified=False
            )
            # Log pending activity safely
            try:
                ActivityLog.objects.create(user=request.user, action="deposit_requested", description=f"Requested {amount} {currency.code} via {method.name}")
            except:
                pass

        # Notify user about the request submission
        send_financial_notification(
            user=request.user,
            title="تم استلام طلب الإيداع",
            body=f"تم استلام طلب الإيداع الخاص بك رقم {deposit.id} بقيمة {deposit.amount} {deposit.currency.code}. سيتم مراجعته من قبل الإدارة قريباً."
        )

        # AFTER creation: Check if verification is needed
        if v3_init_verification(request, request.user, "deposit"):
            # If no security method enabled, auto-verify
            deposit.is_verified = True
            deposit.save(update_fields=["is_verified"])
            messages.success(request, "تم تقديم طلب الإيداع بنجاح.")
            return redirect("dashboard_deposits")
        else:
            # Save request ID in session for verification callback
            request.session["v3_pending_action_id"] = str(deposit.id)
            messages.info(request, "يرجى التحقق لإكمال الطلب.")
            methods = request.session.get("v3_auth_methods", [])
            return redirect("site_2fa_verify" if methods[0] == "APP" else "site_verify_otp")

    return render(request, "site/v3/v3_deposits.html", {
        "payment_methods": PaymentMethod.objects.filter(is_active=True, can_deposit=True), 
        "requests": DepositRequest.objects.filter(user=request.user).order_by('-created_at'),
        "daily_limit": request.user.daily_deposit_limit,
        "remaining_limit": request.user.remaining_deposit_limit,
        "kyc_request": KYCRequest.objects.filter(user=request.user).order_by('-created_at').first(),
    })

@login_required
def withdrawals(request):
    if request.method == "POST":
        method_id = request.POST.get("payment_method")
        currency_id = request.POST.get("currency")
        amount_str = request.POST.get("amount", "0")
        
        if not method_id or not currency_id:
            messages.error(request, "بيانات ناقصة.")
            return redirect("dashboard_withdrawals")

        method = get_object_or_404(PaymentMethod, id=method_id, is_active=True, can_withdraw=True)
        currency = get_object_or_404(Currency, id=currency_id, is_active=True)
        
        if not method.supported_currencies.filter(id=currency.id).exists():
            messages.error(request, "العملة المختارة غير مدعومة.")
            return redirect("dashboard_withdrawals")

        try:
            amount = Decimal(amount_str)
            if amount <= 0: raise ValueError()
        except:
            messages.error(request, "مبلغ غير صحيح.")
            return redirect("dashboard_withdrawals")

        # Limit checks (pre-request)
        amount_in_usd = currency.to_base(amount, "withdraw")
        if amount_in_usd > request.user.remaining_withdrawal_limit:
            messages.error(request, f"لقد تجاوزت حد السحب اليومي المتبقي ({request.user.remaining_withdrawal_limit:,.2f} USD).")
            return redirect("dashboard_withdrawals")

        # Extract payout details
        payout_details = {"dynamic": {}}
        schema = method.withdrawal_form_schema
        for field in schema.get("fields", []) if isinstance(schema, dict) else []:
            field_name = field.get("name") or field.get("id") or field.get("key") or field.get("label")
            
            if field.get("type") == "image":
                val_file = request.FILES.get(f"custom_{field_name}")
                if val_file:
                    # Save file manually to media/withdrawal-proofs/customer/
                    from django.core.files.storage import default_storage
                    path = default_storage.save(f"withdrawal-proofs/customer/{val_file.name}", val_file)
                    val = f"{settings.MEDIA_URL}{path}"
                else:
                    val = ""
            else:
                val = request.POST.get(f"custom_{field_name}")
            
            if field.get("required") and not val:
                messages.error(request, f"الحقل {field.get('label')} مطلوب.")
                return redirect("dashboard_withdrawals")
            payout_details["dynamic"][field_name] = val

        # Create unverified request
        try:
            with transaction.atomic():
                # Correctly convert the withdrawal amount to the wallet's currency (usually USD)
                # wallet_amount is the actual amount to be frozen from the balance
                wallet_amount = currency.to_base(amount, "withdraw")
                
                # Wallet check happens in freeze_funds
                freeze_funds(
                    request.user.wallet.id, 
                    wallet_amount, 
                    reference=f"with_req_{timezone.now().timestamp()}", 
                    reason=f"سحب {amount} {currency.code} عبر {method.name}"
                )
                
                withdrawal = WithdrawalRequest.objects.create(
                    user=request.user,
                    payment_method=method,
                    currency=currency,
                    amount=amount,
                    wallet_amount=wallet_amount, # Important: store the base amount
                    payout_details=payout_details,
                    status=WithdrawalRequest.Status.PENDING,
                    is_verified=False
                )
            
            # Notify user about the request submission
            send_financial_notification(
                user=request.user,
                title="تم استلام طلب السحب",
                body=f"تم استلام طلب السحب الخاص بك رقم {withdrawal.id} بقيمة {withdrawal.amount} {withdrawal.currency.code}. سيتم مراجعته من قبل الإدارة قريباً."
            )
        except Exception as e:
            messages.error(request, str(e))
            return redirect("dashboard_withdrawals")

        # AFTER creation: Verification
        if v3_init_verification(request, request.user, "withdraw"):
            withdrawal.is_verified = True
            withdrawal.save(update_fields=["is_verified"])
            messages.success(request, "تم تقديم طلب السحب بنجاح.")
            return redirect("dashboard_withdrawals")
        else:
            request.session["v3_pending_action_id"] = str(withdrawal.id)
            messages.info(request, "يرجى التحقق لإكمال طلب السحب.")
            methods = request.session.get("v3_auth_methods", [])
            return redirect("site_2fa_verify" if methods[0] == "APP" else "site_verify_otp")

    return render(request, "site/v3/v3_withdrawals.html", {
        "payment_methods": PaymentMethod.objects.filter(is_active=True, can_withdraw=True), 
        "requests": WithdrawalRequest.objects.filter(user=request.user).order_by('-created_at'),
        "daily_limit": request.user.daily_withdrawal_limit,
        "remaining_limit": request.user.remaining_withdrawal_limit,
        "kyc_request": KYCRequest.objects.filter(user=request.user).order_by('-created_at').first(),
    })

@login_required
def kyc_request_view(request):
    existing = KYCRequest.objects.filter(user=request.user).first()
    if existing and existing.status in [KYCRequest.Status.PENDING, KYCRequest.Status.APPROVED]: 
        return render(request, "site/v3/v3_kyc_status.html", {"kyc": existing})

    form = KYCRequestForm(request.POST or None, request.FILES or None, instance=existing)
    if request.method == "POST" and form.is_valid():
        kyc = form.save(commit=False); kyc.user, kyc.status = request.user, KYCRequest.Status.PENDING; kyc.save()
        notify_bulk(User.objects.filter(role=User.Role.ADMIN), title="طلب توثيق جديد", body=f"مستخدم: {request.user.email}", action_url=f"/control/kyc/{kyc.id}/")
        
        # Send Email Notification
        from apps.accounts.services import send_kyc_status_email
        send_kyc_status_email(request.user, 'pending')
        
        messages.success(request, "تم تقديم الطلب."); return redirect("dashboard")
    return render(request, "site/v3/v3_kyc_form.html", {"form": form})

@login_required
def notifications_list(request):
    notifications = Notification.objects.filter(user=request.user).order_by("-created_at")
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True, read_at=timezone.now())
    return render(request, "site/notifications_list.html", {"notifications": notifications})

@login_required
def notification_settings(request):
    settings_obj, _ = NotificationSetting.objects.get_or_create(user=request.user)
    if request.method == "POST":
        for field in ['in_app_orders', 'push_orders', 'in_app_financial', 'push_financial', 'in_app_support', 'push_support', 'in_app_promotions', 'push_promotions']: setattr(settings_obj, field, request.POST.get(field) == "on")
        settings_obj.save(); messages.success(request, "تم الحفظ."); return redirect("notification_settings")
    return render(request, "site/notification_settings.html", {"settings": settings_obj})

@login_required
def v3_change_password_view(request):
    if not v3_init_verification(request, request.user, "settings"):
        return v3_security_redirect(request.session.get("v3_auth_methods", []))
        
    form = ChangePasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if request.user.check_password(form.cleaned_data["current_password"]):
            request.user.set_password(form.cleaned_data["new_password"]); request.user.save(); update_session_auth_hash(request, request.user)
            messages.success(request, "تم تغيير كلمة المرور بنجاح."); return redirect("dashboard")
        else: messages.error(request, "كلمة المرور الحالية غير صحيحة.")
    return render(request, "site/v3/v3_change_password.html", {"form": form})

@login_required
def v3_change_email_view(request):
    if not v3_init_verification(request, request.user, "settings"):
        return v3_security_redirect(request.session.get("v3_auth_methods", []))
        
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
    if not v3_init_verification(request, request.user, "settings"):
        return v3_security_redirect(request.session.get("v3_auth_methods", []))
        
    user = request.user
    if request.method == "POST":
        action = request.POST.get("action")
        
        # 1. Update Security Password Logic
        if action == "update_security_password":
            current_sp = request.POST.get("current_security_password")
            new_sp = request.POST.get("new_security_password")
            confirm_sp = request.POST.get("confirm_security_password")
            
            # If already has one, verify it
            if user.security_password:
                if not check_password_hash(current_sp, user.security_password):
                    messages.error(request, "كلمة مرور الحماية الحالية غير صحيحة.")
                    return redirect("site_security_triggers")
            
            if new_sp and new_sp == confirm_sp:
                if len(new_sp) < 6:
                    messages.error(request, "كلمة المرور يجب أن تكون 6 خانات على الأقل.")
                else:
                    user.security_password = make_password(new_sp)
                    user.security_password_enabled = True
                    user.save()
                    messages.success(request, "تم تحديث كلمة مرور الحماية وتفعيل الحماية بنجاح.")
            else:
                messages.error(request, "كلمات المرور غير متطابقة.")
            return redirect("site_security_triggers")

        # 2. Toggle Protection
        if action == "toggle_protection":
            sp = request.POST.get("security_password")
            if not user.security_password or not check_password_hash(sp, user.security_password):
                messages.error(request, "كلمة مرور الحماية غير صحيحة.")
            else:
                user.security_password_enabled = not user.security_password_enabled
                user.save()
                messages.success(request, "تم تغيير حالة حماية الإعدادات.")
            return redirect("site_security_triggers")

        # 3. Update Triggers (Requires SP if enabled)
        if user.security_password_enabled:
            sp = request.POST.get("security_password_verify")
            if not sp or not check_password_hash(sp, user.security_password):
                messages.error(request, "يرجى إدخال كلمة مرور الحماية لتغيير هذه الإعدادات.")
                return redirect("site_security_triggers")

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
        
        # Verification check
        if not v3_init_verification(request, request.user, "purchase"):
            last_verified = request.session.get("v3_action_verified_at")
            if not last_verified or (timezone.now() - timezone.datetime.fromisoformat(last_verified)).total_seconds() > 300:
                methods = request.session.get("v3_auth_methods", [])
                return redirect("site_2fa_verify" if methods[0] == "APP" else "site_verify_otp")

        # Purchase Logic
        variant_id = request.POST.get("variant_id")
        variant = get_object_or_404(ProductVariant, id=variant_id, product=product)
        
        # Collect custom fields
        metadata = {}
        for key in request.POST:
            if key.startswith("custom_"):
                metadata[key.replace("custom_", "")] = request.POST.get(key)
        
        # Deduct balance & create order
        price = variant.get_price_for_user(request.user)
        
        # Apply Coupon if present
        coupon_code = request.POST.get("coupon_code")
        coupon = None
        discount_amount = Decimal("0.00")
        if coupon_code:
            coupon = Coupon.objects.filter(code__iexact=coupon_code, is_active=True).first()
            if coupon:
                # Validate coupon again before processing
                is_valid = True
                if not coupon.apply_to_all_products and coupon.limit_to_product_id != product.id:
                    is_valid = False
                if coupon.max_uses > 0 and coupon.used_count >= coupon.max_uses:
                    is_valid = False
                if coupon.expires_at and coupon.expires_at < timezone.now():
                    is_valid = False
                
                # New Restrictions Check in Purchase Logic
                if coupon.limit_to_users.exists() and not coupon.limit_to_users.filter(id=request.user.id).exists():
                    is_valid = False
                if coupon.limit_to_tiers and request.user.tier not in coupon.limit_to_tiers:
                    is_valid = False
                if coupon.limit_to_area:
                    kyc = getattr(request.user, 'kyc_request', None)
                    if not kyc or coupon.limit_to_area not in kyc.current_residence:
                        is_valid = False
                
                if is_valid:
                    if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
                        discount_amount = (price * (coupon.discount_percent / 100)).quantize(Decimal("0.01"))
                    else:
                        discount_amount = min(coupon.discount_amount, price)
                    price -= discount_amount
                else:
                    coupon = None

        if request.user.wallet.available_balance >= price:
            with transaction.atomic():
                from apps.orders.models import Order, OrderItem
                from apps.wallets.services import credit_wallet
                
                # Create order
                order = Order.objects.create(
                    customer=request.user,
                    total_amount=price,
                    original_total=price + discount_amount,
                    status=Order.Status.PROCESSING,
                    coupon=coupon,
                    metadata=metadata
                )
                
                # Create OrderItem
                OrderItem.objects.create(
                    order=order,
                    variant=variant,
                    unit_price=price,
                    total_price=price
                )
                
                # Update Coupon used count
                if coupon:
                    coupon.used_count += 1
                    coupon.save(update_fields=["used_count"])
                
                # Charge wallet
                description = f"شراء منتج: {product.name} ({variant.name})"
                if coupon:
                    description += f" [تم استخدام كوبون: {coupon.code}]"
                
                debit_wallet(request.user.wallet.id, price, f"order:{order.id}", description, request.user)
                
                messages.success(request, "تم إتمام الطلب بنجاح.")
                return redirect("dashboard_orders")
        else:
            missing_amount = price - request.user.wallet.available_balance
            # Convert missing amount to wallet currency if needed
            wallet = request.user.wallet
            display_missing = missing_amount
            if wallet.currency.code != "USD":
                display_missing = wallet.currency.from_base(missing_amount)
            
            currency_symbol = wallet.currency.symbol
            messages.error(request, f"رصيد غير كافٍ. تحتاج إلى {display_missing:,.2f} {currency_symbol} إضافية لإتمام الطلب.")
            request.session['missing_amount'] = str(display_missing)
            request.session['missing_currency'] = wallet.currency.code
            return redirect("product_detail", pk=pk)

    variants = product.variants.filter(is_active=True).order_by('sort_order')
    related_products = Product.objects.filter(category=product.category, is_active=True).exclude(pk=product.pk)[:3]
    
    missing_amount = request.session.pop('missing_amount', None)
    missing_currency = request.session.pop('missing_currency', None)
    
    return render(request, "site/product_detail.html", {
        "product": product, 
        "variants": variants, 
        "related_products": related_products,
        "missing_amount": missing_amount,
        "missing_currency": missing_currency
    })

def ajax_validate_coupon(request):
    try:
        variant_id = request.GET.get("variant_id")
        code = request.GET.get("code", "").strip()
        
        if not variant_id or not code:
            return JsonResponse({"valid": False, "error": "بيانات ناقصة"})
            
        variant = ProductVariant.objects.select_related("product").get(id=variant_id)
        coupon = Coupon.objects.filter(code__iexact=code, is_active=True).first()
        
        if not coupon:
            return JsonResponse({"valid": False, "error": "الكوبون غير صحيح أو منتهي الصلاحية"})
            
        # Check product limits
        if not coupon.apply_to_all_products:
            if coupon.limit_to_product_id and variant.product_id != coupon.limit_to_product_id:
                return JsonResponse({"valid": False, "error": f"هذا الكوبون مخصص لمنتج {coupon.limit_to_product.name} فقط"})

        # Check total usage limits
        if coupon.max_uses > 0 and coupon.used_count >= coupon.max_uses:
            return JsonResponse({"valid": False, "error": "عذراً، وصل هذا الكوبون للحد الأقصى من الاستخدام"})
            
        # Check per-user usage limits
        if request.user.is_authenticated:
            user_usage = Order.objects.filter(customer=request.user, coupon=coupon).count()
            if coupon.max_uses_per_user > 0 and user_usage >= coupon.max_uses_per_user:
                return JsonResponse({"valid": False, "error": "لقد استخدمت هذا الكوبون مسبقاً"})
            
            # New Restrictions Check
            # 1. Specific Users
            if coupon.limit_to_users.exists():
                if not coupon.limit_to_users.filter(id=request.user.id).exists():
                    return JsonResponse({"valid": False, "error": "هذا الكوبون غير مخصص لحسابك"})
            
            # 2. Specific Tiers
            if coupon.limit_to_tiers:
                if request.user.tier not in coupon.limit_to_tiers:
                    tier_display = dict(User.Tier.choices).get(request.user.tier, request.user.tier)
                    return JsonResponse({"valid": False, "error": f"هذا الكوبون غير متاح لفئة {tier_display}"})
            
            # 3. Specific Area (Residence or Birth)
            if coupon.limit_to_area or coupon.limit_to_place_of_birth:
                kyc = getattr(request.user, 'kyc_request', None)
                if not kyc:
                    return JsonResponse({"valid": False, "error": "هذا الكوبون يتطلب حساباً موثقاً وتأكيد عنوان السكن"})
                
                area_valid = True
                if coupon.limit_to_area:
                    match_res = coupon.limit_to_area.lower() in kyc.current_residence.lower()
                    if coupon.allow_area_type == Coupon.AreaType.RESIDENCE and not match_res:
                        area_valid = False
                    elif coupon.allow_area_type == Coupon.AreaType.BOTH and not match_res:
                        # Will check birth below
                        pass
                    elif coupon.allow_area_type == Coupon.AreaType.BIRTH:
                        # Handled by separate field check
                        pass
                
                if coupon.limit_to_place_of_birth:
                    match_birth = coupon.limit_to_place_of_birth.lower() in kyc.place_of_birth.lower()
                    if coupon.allow_area_type == Coupon.AreaType.BIRTH and not match_birth:
                        area_valid = False
                    elif coupon.allow_area_type == Coupon.AreaType.BOTH:
                        # If residence matched, we are good. If not, check birth.
                        match_res = coupon.limit_to_area.lower() in kyc.current_residence.lower() if coupon.limit_to_area else False
                        if not match_res and not match_birth:
                            area_valid = False

                if not area_valid:
                    return JsonResponse({"valid": False, "error": "هذا الكوبون غير متاح لمنطقتك الجغرافية الحالية أو مكان ولادتك"})

        # Check expiration
        if coupon.expires_at and coupon.expires_at < timezone.now():
            return JsonResponse({"valid": False, "error": "هذا الكوبون منتهي الصلاحية"})

        # Check verified only
        if coupon.is_verified_only:
            # You might need to check if user is KYC verified here
            # For now, let's assume request.user.is_verified is a field or check
            pass

        # Calculate discount
        price = variant.get_price_for_user(request.user)
        discount_amount = Decimal("0.00")
        
        if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
            discount_amount = (price * (coupon.discount_percent / 100)).quantize(Decimal("0.01"))
        else:
            discount_amount = min(coupon.discount_amount, price)
            
        new_total = price - discount_amount
        
        return JsonResponse({
            "valid": True, 
            "message": f"تم تطبيق الكوبون بنجاح! خصم {discount_amount} USD",
            "discount_amount": float(discount_amount), 
            "new_total": float(new_total)
        })
    except Exception as e:
        return JsonResponse({"valid": False, "error": str(e)})

# ==========================================
# --- ADMINISTRATIVE VIEWS (V4) ---
# ==========================================

@staff_required
def control_dashboard(request):
    from apps.payments.models import DepositRequest, WithdrawalRequest
    stats = {"users": User.objects.count(), "pending_deposits": DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).count(), "pending_withdrawals": WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PENDING).count(), "open_tickets": ChatRoom.objects.exclude(status=ChatRoom.Status.CLOSED).count()}
    return render(request, "site/control_dashboard.html", {"stats": stats, "recent_orders": Order.objects.select_related('customer').order_by('-created_at')[:5], "recent_deposits": DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).order_by('-created_at')[:5], "recent_users": User.objects.order_by('-date_joined')[:5]})

@finance_required
def control_deposits(request): return render(request, "site/control_deposits.html", {"deposits": DepositRequest.objects.select_related('user', 'payment_method').all().order_by('-created_at')})

@finance_required
def control_withdrawals(request): return render(request, "site/control_withdrawals.html", {"withdrawals": WithdrawalRequest.objects.select_related('user', 'payment_method').all().order_by('-created_at')})

# ==========================================
# --- FINANCIAL NOTIFICATION HELPERS ---
# ==========================================

from urllib.parse import urljoin

def send_financial_notification(user, title, body, action_url="/dashboard/wallet/"):
    # 1. In-App/Push Notification
    try:
        notify_user(user=user, title=title, body=body, action_url=action_url, category='financial', priority="high")
    except: pass

    # 2. Email Notification with Modern Design
    subject = f"{title} | Raqamiyat"
    # Ensure no double slashes in URL
    full_url = urljoin(settings.SITE_URL, action_url)

    html_content = f"""
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <style>
            .container {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 600px;
                margin: 0 auto;
                padding: 40px 20px;
                background-color: #f8fafc;
            }}
            .card {{
                background-color: #ffffff;
                border-radius: 24px;
                overflow: hidden;
                box-shadow: 0 10px 25px rgba(0,0,0,0.05);
                border: 1px solid #e2e8f0;
            }}
            .header {{
                background: linear-gradient(135deg, #0891b2 0%, #06b6d4 100%);
                padding: 40px 20px;
                text-align: center;
                color: #ffffff;
            }}
            .logo {{
                font-size: 28px;
                font-weight: 900;
                letter-spacing: 1px;
                margin: 0;
                text-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .content {{
                padding: 40px;
            }}
            .title {{
                color: #0f172a;
                font-size: 22px;
                font-weight: 800;
                margin-top: 0;
                margin-bottom: 20px;
                text-align: center;
            }}
            .message {{
                font-size: 16px;
                line-height: 1.8;
                color: #334155;
                margin-bottom: 30px;
                text-align: right;
            }}
            .cta-container {{
                text-align: center;
                margin-bottom: 20px;
            }}
            .cta-button {{
                display: inline-block;
                padding: 14px 32px;
                background-color: #0891b2;
                color: #ffffff !important;
                text-decoration: none;
                border-radius: 12px;
                font-weight: 700;
                font-size: 16px;
                transition: background-color 0.2s;
            }}
            .security-notice {{
                margin-top: 40px;
                padding: 20px;
                background-color: #fff1f2;
                border-radius: 16px;
                border: 1px solid #fecdd3;
            }}
            .security-title {{
                margin: 0 0 8px 0;
                font-size: 14px;
                color: #be123c;
                font-weight: 800;
                display: flex;
                align-items: center;
            }}
            .security-text {{
                margin: 0;
                font-size: 13px;
                color: #e11d48;
                line-height: 1.6;
            }}
            .footer {{
                margin-top: 30px;
                text-align: center;
                color: #94a3b8;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <div class="header">
                    <h1 class="logo">رقميات | RAQAMIYAT</h1>
                </div>
                <div class="content">
                    <h2 class="title">{title}</h2>
                    <div class="message">{body}</div>

                    <div class="cta-container">
                        <a href="{full_url}" class="cta-button">عرض في المنصة</a>
                    </div>

                    <div class="security-notice">
                        <p class="security-title">⚠️ تنبيه أمني:</p>
                        <p class="security-text">
                            إذا لم تكن قد قمت بهذه العملية بنفسك، يرجى تغيير كلمة مرور حسابك فوراً والتواصل مع فريق الدعم الفني لحماية حسابك.
                        </p>
                    </div>
                </div>
            </div>
            <div class="footer">
                <p>© 2026 رقميات لخدمات الوساطة الرقمية. جميع الحقوق محفوظة.</p>
                <p>تم إرسال هذا البريد تلقائياً، يرجى عدم الرد عليه.</p>
            </div>
        </div>
    </body>
    </html>
    """
    try:
        from apps.accounts.services import send_brevo_email
        send_brevo_email(to_email=user.email, to_name=user.get_full_name() or user.email, subject=subject, html_content=html_content)
    except: pass

@finance_required
def control_deposit_detail(request, pk):
    from apps.payments.models import DepositRequest
    deposit = get_object_or_404(DepositRequest.objects.select_related('user', 'currency', 'payment_method'), pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        admin_note = request.POST.get("admin_note", "")

        try:
            with transaction.atomic():
                if action == "approve":
                    if deposit.status == DepositRequest.Status.COMPLETED:
                        raise ValueError("تم اعتماد هذا الطلب مسبقاً.")

                    original_requested_amount = deposit.amount
                    override_amount = request.POST.get("amount")
                    if override_amount:
                        # Admin is specifying the FINAL amount to credit
                        final_amount = Decimal(str(override_amount))
                        deposit.final_amount = final_amount
                        deposit.amount = final_amount # Treat as gross if they want it exact
                        deposit.fee_amount = Decimal("0.00")
                        deposit._fees_calculated = True
                    else:
                        final_amount = deposit.final_amount

                    wallet = get_or_create_wallet(deposit.user)
                    if deposit.currency.code == wallet.currency.code:
                        wallet_final_amount = final_amount
                    else:
                        base_val = deposit.currency.to_base(final_amount, "deposit")
                        wallet_final_amount = wallet.currency.from_base(base_val, "deposit")

                    if wallet_final_amount <= 0:
                        raise ValueError("يجب أن يكون المبلغ أكبر من صفر.")

                    credit_wallet(
                        wallet_id=wallet.id,
                        amount=wallet_final_amount,
                        reference=f"deposit:{deposit.id}",
                        description=f"إيداع عبر {deposit.payment_method.name}",
                        created_by=request.user,
                        metadata={
                            "from_pending": True,
                            "pending_amount": str(deposit.wallet_amount),
                            "source_amount": str(deposit.amount),
                            "source_currency": deposit.currency.code,
                            "final_amount": str(final_amount),
                            "transaction_id": deposit.transaction_id
                        }
                    )

                    # Ensure record reflects what was actually credited
                    deposit.wallet_amount = wallet_final_amount
                    deposit.status = DepositRequest.Status.COMPLETED
                    deposit.reviewed_by = request.user
                    deposit.reviewed_at = timezone.now()
                    if admin_note:
                        deposit.admin_note = admin_note
                    deposit.save()

                    # Update daily usage for the user (in base currency/USD)
                    try:
                        amount_in_usd = deposit.currency.to_base(deposit.final_amount, "deposit")
                        deposit.user.add_deposit_usage(amount_in_usd)
                    except: pass

                    # Transparent body showing original vs approved if changed
                    amount_text = f"{deposit.final_amount:,.2f} {deposit.currency.code}"
                    if override_amount and Decimal(str(override_amount)) != original_requested_amount:
                        body_msg = f"تمت مراجعة طلب الإيداع رقم {deposit.id}. تم اعتماد مبلغ {amount_text} بدلاً من المبلغ المطلوب {original_requested_amount:,.2f} {deposit.currency.code}. تم إضافة {deposit.wallet_amount:,.2f} {wallet.currency.code} إلى رصيد محفظتك."
                    else:
                        body_msg = f"تم قبول طلب الإيداع رقم {deposit.id} بنجاح. المبلغ المعتمد: {amount_text}. تم إضافة {deposit.wallet_amount:,.2f} {wallet.currency.code} إلى رصيد محفظتك."

                    send_financial_notification(
                        user=deposit.user,
                        title="تم قبول طلب الإيداع",
                        body=body_msg
                    )
                    messages.success(request, "تم قبول طلب الإيداع بنجاح.")

                elif action == "reject":
                    if deposit.status == DepositRequest.Status.COMPLETED:
                        raise ValueError("لا يمكن رفض طلب مكتمل.")
                    
                    if deposit.status != DepositRequest.Status.REJECTED:
                        wallet = get_or_create_wallet(deposit.user)
                        from apps.wallets.services import cancel_pending_deposit
                        cancel_pending_deposit(
                            wallet_id=wallet.id,
                            amount=deposit.wallet_amount,
                            reference=f"deposit_reject:{deposit.id}",
                            description=f"إلغاء إيداع معلق مرفوض عبر {deposit.payment_method.name}",
                            created_by=request.user
                        )

                    deposit.status = DepositRequest.Status.REJECTED
                    deposit.admin_note = admin_note
                    deposit.reviewed_by = request.user
                    deposit.reviewed_at = timezone.now()
                    deposit.save()
                    
                    send_financial_notification(
                        user=deposit.user,
                        title="تم رفض طلب الإيداع",
                        body=f"نعتذر، تم رفض طلب الإيداع رقم {deposit.id}. السبب: {admin_note}"
                    )
                    messages.warning(request, "تم رفض طلب الإيداع.")

                elif action == "correct":
                    if deposit.status != DepositRequest.Status.COMPLETED:
                        raise ValueError("يمكن تصحيح الطلبات المكتملة فقط.")

                    new_amount_str = request.POST.get("new_amount")
                    if not new_amount_str:
                        raise ValueError("المبلغ الجديد مطلوب.")
                    
                    new_amount = Decimal(str(new_amount_str))
                    old_amount = deposit.final_amount
                    diff_amount = new_amount - old_amount
                    
                    if diff_amount == 0:
                        raise ValueError("لم يتم تغيير المبلغ.")

                    wallet = get_or_create_wallet(deposit.user)
                    if deposit.currency.code == wallet.currency.code:
                        wallet_diff = diff_amount
                    else:
                        base_diff = deposit.currency.to_base(diff_amount, "deposit")
                        wallet_diff = wallet.currency.from_base(base_diff, "deposit")

                    if wallet_diff > 0:
                        credit_wallet(
                            wallet_id=wallet.id,
                            amount=wallet_diff,
                            reference=f"deposit_adj:{deposit.id}",
                            description=f"تصحيح مبلغ الإيداع (زيادة): {admin_note}",
                            created_by=request.user,
                            source="admin_adjustment",
                            metadata={
                                "source_amount": str(diff_amount),
                                "source_currency": deposit.currency.code,
                                "transaction_id": deposit.transaction_id,
                                "is_adjustment": True
                            }
                        )
                    else:
                        debit_wallet(
                            wallet_id=wallet.id,
                            amount=abs(wallet_diff),
                            reference=f"deposit_adj:{deposit.id}",
                            description=f"تصحيح مبلغ الإيداع (نقص): {admin_note}",
                            created_by=request.user,
                            source="admin_adjustment",
                            metadata={
                                "source_amount": str(diff_amount),
                                "source_currency": deposit.currency.code
                            }
                        )

                    deposit.final_amount = new_amount
                    deposit.wallet_amount += wallet_diff
                    if admin_note:
                        deposit.admin_note = f"{deposit.admin_note or ''}\n[تصحيح {timezone.now().strftime('%Y-%m-%d %H:%M')}]: {admin_note}"
                    deposit.save()
                    
                    send_financial_notification(
                        user=deposit.user,
                        title="تعديل في مبلغ إيداع سابق",
                        body=f"تم تعديل المبلغ المعتمد للإيداع رقم {deposit.id}. القيمة الجديدة: {deposit.final_amount:,.2f} {deposit.currency.code}. تم تعديل رصيد محفظتك بفرق: {wallet_diff:,.2f} {wallet.currency.code}."
                    )
                    
                    messages.success(request, f"تم تصحيح المبلغ بنجاح. الفرق: {wallet_diff:,.2f} {wallet.currency.code}")
        except Exception as e:
            messages.error(request, f"خطأ: {str(e)}")
            
        return redirect("control_deposit_detail", pk=pk)
        
    return render(request, "site/control_deposit_detail.html", {"deposit": deposit})

@finance_required
def control_withdrawal_detail(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest.objects.select_related('user', 'user__wallet', 'user__wallet__currency', 'payment_method'), pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        admin_note = request.POST.get("admin_note", "")
        proof_image = request.FILES.get("proof_image")
        proof_file = request.FILES.get("proof_file")
        
        try:
            with transaction.atomic():
                if action == "process":
                    withdrawal.status = WithdrawalRequest.Status.PROCESSING
                elif action == "approve":
                    withdrawal.status = WithdrawalRequest.Status.APPROVED
                elif action == "complete":
                    if withdrawal.status != WithdrawalRequest.Status.COMPLETED:
                        finalize_withdrawal(
                            wallet_id=withdrawal.user.wallet.id,
                            amount=withdrawal.wallet_amount,
                            reference=f"with:{withdrawal.id}",
                            description=f"Withdrawal completed via {withdrawal.payment_method.name}",
                            created_by=request.user
                        )
                        withdrawal.status = WithdrawalRequest.Status.COMPLETED
                        withdrawal.reviewed_at = timezone.now()
                elif action == "reject":
                    if withdrawal.status in [WithdrawalRequest.Status.COMPLETED, WithdrawalRequest.Status.CANCELLED, WithdrawalRequest.Status.REJECTED]:
                        raise ValueError("لا يمكن رفض طلب منتهي.")
                    
                    if withdrawal.status != WithdrawalRequest.Status.REJECTED:
                        release_funds(
                            wallet_id=withdrawal.user.wallet.id,
                            amount=withdrawal.wallet_amount,
                            reference=f"with:{withdrawal.id}",
                            description="Withdrawal rejected",
                            created_by=request.user
                        )
                        
                        # Reverse daily usage on rejection
                        try:
                            amount_in_usd = withdrawal.currency.to_base(withdrawal.amount, "withdraw")
                            withdrawal.user.add_withdrawal_usage(-amount_in_usd)
                        except: pass

                        withdrawal.status = WithdrawalRequest.Status.REJECTED
                        withdrawal.reviewed_at = timezone.now()

                elif action == "correct":
                    if withdrawal.status != WithdrawalRequest.Status.COMPLETED:
                        raise ValueError("يمكن تصحيح الطلبات المكتملة فقط.")

                    new_amount_str = request.POST.get("new_amount")
                    if not new_amount_str:
                        raise ValueError("المبلغ الجديد مطلوب.")

                    new_amount = Decimal(str(new_amount_str))
                    old_amount = withdrawal.amount
                    diff_amount = new_amount - old_amount

                    if diff_amount == 0:
                        raise ValueError("لم يتم تغيير المبلغ.")

                    wallet = get_or_create_wallet(withdrawal.user)
                    # Calculate wallet difference (how much MORE or LESS to debit)
                    wallet_diff = withdrawal.currency.to_base(diff_amount, "withdraw")

                    if wallet_diff > 0:
                        # User withdrew MORE than originally thought -> debit MORE
                        debit_wallet(
                            wallet_id=wallet.id,
                            amount=wallet_diff,
                            reference=f"with_adj:{withdrawal.id}",
                            description=f"تصحيح مبلغ السحب (زيادة): {admin_note}",
                            created_by=request.user,
                            source="admin_adjustment"
                        )
                    else:
                        # User withdrew LESS than originally thought -> credit BACK
                        credit_wallet(
                            wallet_id=wallet.id,
                            amount=abs(wallet_diff),
                            reference=f"with_adj:{withdrawal.id}",
                            description=f"تصحيح مبلغ السحب (نقص): {admin_note}",
                            created_by=request.user,
                            source="admin_adjustment"
                        )

                    withdrawal.amount = new_amount
                    withdrawal.wallet_amount += wallet_diff
                    if admin_note:
                        withdrawal.admin_note = f"{withdrawal.admin_note or ''}\n[تصحيح {timezone.now().strftime('%Y-%m-%d %H:%M')}]: {admin_note}"
                    withdrawal.save()

                    send_financial_notification(
                        user=withdrawal.user,
                        title="تعديل في مبلغ سحب مكتمل",
                        body=f"تم تعديل المبلغ المرسل للسحب رقم {withdrawal.id}. القيمة النهائية: {withdrawal.amount:,.2f} {withdrawal.currency.code}. تم تعديل رصيد محفظتك بفرق: {-wallet_diff:,.2f} {wallet.currency.code}."
                    )
                    messages.success(request, f"تم تصحيح السحب بنجاح. الفرق: {-wallet_diff:,.2f} {wallet.currency.code}")
                
                if admin_note: withdrawal.admin_note = admin_note
                if proof_image: withdrawal.proof_image = proof_image
                if proof_file: withdrawal.proof_file = proof_file
                withdrawal.reviewed_by = request.user
                withdrawal.save()
                messages.success(request, f"تم تحديث حالة الطلب إلى {withdrawal.get_status_display()}")
                
                # Send Notification
                send_financial_notification(
                    user=withdrawal.user,
                    title=f"تحديث طلب السحب #{withdrawal.id}",
                    body=f"تم تغيير حالة طلب السحب الخاص بك إلى: {withdrawal.get_status_display()}. ملاحظة الإدارة: {withdrawal.admin_note or 'لا يوجد'}",
                    action_url="/dashboard/withdrawals/"
                )
                
        except Exception as e:
            messages.error(request, f"خطأ: {str(e)}")
            
        return redirect("control_withdrawal_detail", pk=pk)
        
    return render(request, "site/control_withdrawal_detail.html", {"withdrawal": withdrawal})

@support_required
def control_kycs_list(request):
    q = request.GET.get('q', '')
    status = request.GET.get('status', '') # This will refer to user.is_kyc_verified or kyc_request.status
    
    users = User.objects.filter(role=User.Role.CUSTOMER).select_related('kyc_request').all().order_by('-date_joined')
    
    if q:
        users = users.filter(
            Q(email__icontains=q) | 
            Q(first_name__icontains=q) | 
            Q(last_name__icontains=q) |
            Q(kyc_request__id_number__icontains=q)
        )
    
    if status == "verified":
        users = users.filter(is_kyc_verified=True)
    elif status == "pending":
        users = users.filter(kyc_request__status=KYCRequest.Status.PENDING)
    elif status == "unverified":
        users = users.filter(is_kyc_verified=False).exclude(kyc_request__status=KYCRequest.Status.PENDING)
    elif status == "rejected":
        users = users.filter(kyc_request__status=KYCRequest.Status.REJECTED)
        
    return render(request, "site/control_kycs_list.html", {
        "users": users, 
        "query": q, 
        "status_filter": status,
    })

@support_required
def control_kyc_detail(request, pk):
    kyc = get_object_or_404(KYCRequest.objects.select_related('user'), pk=pk)
    form = KYCRequestForm(request.POST or None, instance=kyc)
    payment_methods = PaymentMethod.objects.filter(is_active=True).order_by("display_order")

    if request.method == "POST":
        action = request.POST.get("action")

        # 1. Update Personal Info
        if action == "update_info" and form.is_valid():
            form.save()
            messages.success(request, "تم تحديث البيانات الشخصية بنجاح.")
            return redirect("control_kyc_detail", pk=pk)

        # 2. Update Limits
        if action == "update_limits":
            u = kyc.user
            u.daily_deposit_limit = Decimal(request.POST.get("global_deposit_limit", u.daily_deposit_limit))
            u.daily_withdrawal_limit = Decimal(request.POST.get("global_withdrawal_limit", u.daily_withdrawal_limit))

            # Custom per-method limits
            limits = u.custom_payment_limits or {}
            for method in payment_methods:
                m_id = str(method.id)
                dep = request.POST.get(f"method_dep_{m_id}")
                withd = request.POST.get(f"method_with_{m_id}")

                if dep or withd:
                    limits[m_id] = {
                        "deposit": dep if dep else None,
                        "withdraw": withd if withd else None
                    }
                elif m_id in limits:
                    del limits[m_id]

            u.custom_payment_limits = limits
            u.has_custom_limits = True if limits else False
            u.save()
            messages.success(request, "تم تحديث الحدود المالية بنجاح.")
            return redirect("control_kyc_detail", pk=pk)

        # 3. Final Decisions
        admin_note = request.POST.get("rejection_reason", "")
        if action == "approve":
            kyc.status = KYCRequest.Status.APPROVED
            kyc.user.is_kyc_verified = True
            
            # Apply global limits if user doesn't have custom ones
            if not kyc.user.has_custom_limits:
                kyc_settings = KYCSettings.get_settings()
                kyc.user.daily_deposit_limit = kyc_settings.verified_daily_deposit_limit
                kyc.user.daily_withdrawal_limit = kyc_settings.verified_daily_withdrawal_limit
            
            kyc.user.save()
            
            # Send Email Notification
            from apps.accounts.services import send_kyc_status_email
            send_kyc_status_email(kyc.user, 'approved')
            
            messages.success(request, f"تم توثيق حساب {kyc.user.email} بنجاح وتم تحديث الحدود المالية.")
        elif action == "reject":
            kyc.status = KYCRequest.Status.REJECTED
            kyc.rejection_reason = admin_note
            kyc.user.is_kyc_verified = False
            
            # Reset to unverified limits if no custom limits
            if not kyc.user.has_custom_limits:
                kyc_settings = KYCSettings.get_settings()
                kyc.user.daily_deposit_limit = kyc_settings.unverified_daily_deposit_limit
                kyc.user.daily_withdrawal_limit = kyc_settings.unverified_daily_withdrawal_limit
            
            kyc.user.save()

            # Send Email Notification
            from apps.accounts.services import send_kyc_status_email
            send_kyc_status_email(kyc.user, 'rejected', reason=admin_note)

            messages.warning(request, f"تم رفض طلب توثيق {kyc.user.email}.")
        elif action == "unverify":
            kyc.status = KYCRequest.Status.REJECTED
            kyc.user.is_kyc_verified = False
            
            # Reset to unverified limits
            if not kyc.user.has_custom_limits:
                kyc_settings = KYCSettings.get_settings()
                kyc.user.daily_deposit_limit = kyc_settings.unverified_daily_deposit_limit
                kyc.user.daily_withdrawal_limit = kyc_settings.unverified_daily_withdrawal_limit
                
            kyc.user.save()
            messages.info(request, "تم إلغاء توثيق الحساب وإعادة الحدود للمستوى الأساسي.")
        elif action == "revert":
            kyc.status = KYCRequest.Status.PENDING
            kyc.save()
            messages.info(request, "تمت إعادة الطلب لحالة قيد المراجعة.")

        kyc.reviewed_by = request.user
        kyc.reviewed_at = timezone.now()
        kyc.save()
        return redirect("control_kycs_list")

    return render(request, "site/control_kyc_detail.html", {
        "kyc": kyc, 
        "form": form,
        "payment_methods": payment_methods
    })

@kyc_required
def control_kyc_settings(request):
    obj = KYCSettings.get_settings()
    form = KYCSettingsForm(request.POST or None, instance=obj)
    
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "unblock_country":
            code = request.POST.get("country_code")
            if code and code in obj.restricted_countries:
                new_list = [c for c in obj.restricted_countries if c != code]
                obj.restricted_countries = new_list
                obj.save()
                messages.success(request, f"تم إلغاء حظر الدولة ({code}) بنجاح.")
            return redirect("control_kyc_settings")
        
        elif action == "block_country":
            code = request.POST.get("country_code")
            if code:
                current_list = list(obj.restricted_countries or [])
                if code not in current_list:
                    current_list.append(code)
                    obj.restricted_countries = current_list
                    obj.save()
                    messages.success(request, "تمت إضافة الدولة لقائمة الحظر.")
            return redirect("control_kyc_settings")
            
        if form.is_valid():
            form.save()
            messages.success(request, "تم حفظ الإعدادات بنجاح.")
            return redirect("control_kyc_settings")
            
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
        action = request.POST.get("action")
        if action == "update_status":
            old_status = order.status
            order.status = request.POST.get("status")
            order.save()
            OrderLog.objects.create(order=order, status=order.status, note=request.POST.get("admin_note", ""), created_by=request.user)
            
            if order.status in [Order.Status.REFUNDED, Order.Status.CANCELLED] and old_status not in [Order.Status.REFUNDED, Order.Status.CANCELLED]: 
                credit_wallet(order.customer.wallet.id, order.total_amount, f"refund:{order.id}", f"استرداد مبلغ الطلب رقم #{order.number}", request.user)
            
            messages.success(request, f"تم تحديث حالة الطلب إلى: {order.get_status_display()}")
            
            # Notify user
            try:
                notify_user(
                    user=order.customer,
                    title="تحديث حالة الطلب",
                    body=f"تم تغيير حالة طلبك رقم #{order.number} إلى: {order.get_status_display()}",
                    action_url=f"/dashboard/orders/{order.id}/",
                    category="orders"
                )
            except: pass
        elif action == "update_fulfillment":
            keys = request.POST.getlist("ff_key[]")
            vals = request.POST.getlist("ff_value[]")
            fulfillment_data = {}
            for k, v in zip(keys, vals):
                if k.strip(): fulfillment_data[k.strip()] = v
            order.fulfillment_data = fulfillment_data
            order.save()
            messages.success(request, "تم تحديث بيانات التنفيذ.")
        elif action == "update_price":
            new_total = Decimal(request.POST.get("total_amount", "0"))
            old_total = order.total_amount
            diff = new_total - old_total
            
            if diff != 0:
                wallet = order.customer.wallet
                # Convert diff (USD) to wallet currency
                adj_amount = diff
                if wallet.currency.code != "USD":
                    adj_amount = wallet.currency.from_base(diff)
                
                try:
                    with transaction.atomic():
                        if diff > 0:
                            # Price increased, debit user
                            debit_wallet(wallet.id, adj_amount, reference=f"order_adj:{order.id}", 
                                         description=f"Adjustment for order #{order.number} (Price Increase)", 
                                         created_by=request.user)
                        else:
                            # Price decreased, credit user
                            credit_wallet(wallet.id, abs(adj_amount), reference=f"order_adj:{order.id}", 
                                          description=f"Adjustment for order #{order.number} (Price Decrease)", 
                                          created_by=request.user)
                        
                        if not order.original_total:
                            order.original_total = old_total
                        
                        order.total_amount = new_total
                        order.price_adjustment_reason = request.POST.get("adjustment_reason", "")
                        order.save()
                        
                        # Update order items
                        if order.items.count() == 1:
                            item = order.items.first()
                            item.total_price = new_total
                            if item.quantity == 1:
                                item.unit_price = new_total
                            item.save()

                        OrderLog.objects.create(
                            order=order, 
                            status=order.status, 
                            note=f"تعديل السعر من {old_total} إلى {new_total}. السبب: {order.price_adjustment_reason}", 
                            created_by=request.user
                        )

                        # Notify user about price adjustment
                        try:
                            notify_user(
                                user=order.customer,
                                title="تعديل سعر الطلب",
                                body=f"تم تعديل سعر طلبك رقم #{order.number}. السعر الجديد: {new_total} USD. السبب: {order.price_adjustment_reason}",
                                action_url=f"/dashboard/orders/{order.id}/",
                                category="orders"
                            )
                        except: pass
                    messages.success(request, "تم تحديث سعر الطلب وتعديل رصيد المحفظة.")
                except Exception as e:
                    messages.error(request, f"فشل في تعديل الرصيد: {str(e)}")
            else:
                order.price_adjustment_reason = request.POST.get("adjustment_reason", "")
                order.save()
                messages.success(request, "تم تحديث ملاحظات تعديل السعر.")
            
        return redirect("control_order_detail", pk=pk)
    
    ctx = {
        "order": order,
        "mapped_metadata": order.formatted_metadata(),
        "readable_fulfillment": order.fulfillment_data or {}
    }
    return render(request, "site/control_order_detail.html", ctx)

@admin_required
def control_users_list(request):
    if request.method == "POST":
        action = request.POST.get("action")
        user_ids = request.POST.getlist("user_ids")
        
        if not user_ids:
            messages.warning(request, "يرجى اختيار مستخدمين لتنفيذ العملية.")
            return redirect("control_users_list")

        if action == "bulk_tier":
            target_tier = request.POST.get("target_tier")
            if target_tier:
                User.objects.filter(id__in=user_ids).update(tier=target_tier)
                messages.success(request, f"تم تحديث فئة {len(user_ids)} مستخدم بنجاح.")
        
        elif action == "bulk_role":
            target_role = request.POST.get("target_role")
            if target_role:
                User.objects.filter(id__in=user_ids).update(role=target_role)
                messages.success(request, f"تم تحديث دور {len(user_ids)} مستخدم بنجاح.")
                
        return redirect("control_users_list")

    users = User.objects.select_related("wallet").order_by("-date_joined")
    
    # Handle search
    q = request.GET.get('q', '')
    if q:
        users = users.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(phone__icontains=q))

    return render(request, "site/control_users_list.html", {
        "users": users,
        "query": q,
        "tiers": User.Tier.choices,
        "roles": User.Role.choices
    })

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
        elif action == "reset_password":
            from django.contrib.auth.tokens import default_token_generator
            from apps.accounts.services import send_brevo_email
            
            token = default_token_generator.make_token(user)
            uid = user.id
            reset_url = request.build_absolute_uri(reverse('site_reset_password')) + f"?token={token}&uid={uid}"
            
            # Professional Email Template
            html_content = f"""
            <div dir="rtl" style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; color: #1e293b; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h2 style="color: #06b6d4; margin: 0; font-size: 24px; font-weight: 900;">رقميات | RAQAMIYAT</h2>
                </div>
                <div style="background-color: #f8fafc; padding: 30px; border-radius: 12px;">
                    <h3 style="margin-top: 0; color: #0f172a;">مرحباً {user.get_full_name() or user.username}،</h3>
                    <p style="font-size: 16px; color: #64748b;">لقد تلقينا طلباً لإعادة تعيين كلمة المرور لحسابك.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_url}" style="padding: 14px 28px; background-color: #06b6d4; color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">إعادة تعيين كلمة المرور</a>
                    </div>
                    <p style="font-size: 14px; color: #94a3b8;">إذا لم تطلب ذلك، يمكنك تجاهل هذا البريد الإلكتروني بأمان. الرابط صالح لفترة محدودة.</p>
                </div>
                <div style="margin-top: 30px; text-align: center; font-size: 12px; color: #94a3b8;">
                    <p>© 2026 رقميات لخدمات الوساطة الرقمية.</p>
                </div>
            </div>
            """
            
            if send_brevo_email(user.email, user.get_full_name() or user.email, "إعادة تعيين كلمة المرور | رقميات", html_content):
                messages.success(request, "تم إرسال رابط إعادة تعيين كلمة المرور بنجاح.")
            else:
                messages.error(request, "فشل إرسال البريد الإلكتروني.")
            return redirect("control_user_moderate", public_uuid=public_uuid)
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
            for v in json.loads(v_json): 
                ProductVariant.objects.create(
                    product=product, 
                    name=v.get('name'), 
                    sku=v.get('sku'), 
                    price=Decimal(str(v.get('price', '0'))), 
                    wholesale_price=Decimal(str(v.get('wholesale_price', '0'))),
                    vip_price=Decimal(str(v.get('vip_price', '0'))),
                    cost=Decimal(str(v.get('cost', '0'))), 
                    estimated_delivery_minutes=int(v.get('estimated_delivery_minutes', 0)),
                    sort_order=int(v.get('sort_order', 0)), 
                    is_active=v.get('is_active', True)
                )
        return redirect("control_products_list")
    return render(request, "site/control_product_builder.html", {"form": form, "variants_json_data": [], "title": "إنشاء منتج جديد"})

@support_required
@transaction.atomic
def control_product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk); form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        product = form.save(); v_json = request.POST.get("variants_json")
        if v_json:
            v_data = json.loads(v_json); product.variants.exclude(sku__in=[v.get('sku') for v in v_data if v.get('sku')]).delete()
            for v in v_data: 
                ProductVariant.objects.update_or_create(
                    product=product, 
                    sku=v.get('sku'), 
                    defaults={
                        "name": v.get('name'), 
                        "price": Decimal(str(v.get('price', '0'))), 
                        "wholesale_price": Decimal(str(v.get('wholesale_price', '0'))),
                        "vip_price": Decimal(str(v.get('vip_price', '0'))),
                        "cost": Decimal(str(v.get('cost', '0'))), 
                        "estimated_delivery_minutes": int(v.get('estimated_delivery_minutes', 0)),
                        "sort_order": int(v.get('sort_order', 0)), 
                        "is_active": v.get('is_active', True)
                    }
                )
        return redirect("control_products_list")
    v_list = [
        {
            "name": v.name, "sku": v.sku, "price": str(v.price), 
            "wholesale_price": str(v.wholesale_price), "vip_price": str(v.vip_price),
            "cost": str(v.cost), "estimated_delivery_minutes": v.estimated_delivery_minutes,
            "sort_order": v.sort_order, "is_active": v.is_active
        } for v in product.variants.all().order_by('sort_order')
    ]
    return render(request, "site/control_product_builder.html", {"form": form, "product": product, "variants_json_data": v_list, "title": f"تعديل: {product.name}"})

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
    q = request.GET.get('q', '')
    users = User.objects.select_related('wallet').filter(Q(email__icontains=q) | Q(phone__icontains=q)) if q else User.objects.select_related('wallet').all()
    
    if request.method == "POST":
        target = get_object_or_404(User, id=request.POST.get("user_id"))
        amt = Decimal(request.POST.get("amount", "0"))
        action = request.POST.get("action")
        reason = request.POST.get("reason", "")
        
        if action == "add_debt":
            from apps.wallets.services import add_debt
            add_debt(target.wallet.id, amt, f"admin_debt_{timezone.now().timestamp()}", reason, request.user)
            messages.success(request, f"تم إضافة دين بقيمة {amt} للمستخدم {target.email}")
            
        elif action == "pay_debt":
            from apps.wallets.services import pay_debt
            pay_mode = request.POST.get("pay_mode", "balance") # balance or cash
            
            # If cash, we don't deduct from balance, just reduce debt_balance
            deduct = True if pay_mode == "balance" else False
            
            try:
                pay_debt(
                    target.wallet.id, 
                    amt, 
                    f"admin_pay_{timezone.now().timestamp()}", 
                    reason, 
                    request.user, 
                    deduct_from_balance=deduct,
                    source="admin_cash" if pay_mode == "cash" else "admin"
                )
                messages.success(request, f"تم تسجيل سداد بقيمة {amt} للمستخدم {target.email} ({'نقداً' if pay_mode == 'cash' else 'من الرصيد'})")
            except Exception as e:
                messages.error(request, str(e))
                
        return redirect(f"{request.path}?q={q}")

    # Stats for the sidebar
    from django.db.models import Sum
    from apps.wallets.models import LedgerEntry
    total_debt = Wallet.objects.aggregate(total=Sum('debt_balance'))['total'] or 0
    today_payments = LedgerEntry.objects.filter(
        entry_type=LedgerEntry.EntryType.DEBT_PAYMENT,
        created_at__date=timezone.now().date()
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    recent_logs = LedgerEntry.objects.filter(
        entry_type__in=[LedgerEntry.EntryType.DEBT_ADD, LedgerEntry.EntryType.DEBT_PAYMENT]
    ).select_related('wallet__user').order_by('-created_at')[:10]
    
    ctx = {
        "users": users, 
        "query": q,
        "total_debt_balance": total_debt,
        "today_debt_payments": today_payments,
        "recent_debt_logs": recent_logs
    }
    return render(request, "site/control_debts.html", ctx)

@support_required
def control_send_notification(request):
    form = SendNotificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        users = User.objects.filter(is_active=True)
        if form.cleaned_data["target"] == "tier": users = users.filter(tier=form.cleaned_data["tier"])
        elif form.cleaned_data["target"] == "individual": users = users.filter(email=form.cleaned_data["user_email"])
        
        if users.exists():
            channel = form.cleaned_data["channels"]
            title = form.cleaned_data["title"]
            body = form.cleaned_data["body"]
            action_url = form.cleaned_data["action_url"]
            
            for user in users:
                # 1. In-App Notification
                if channel in ['all', 'in_app']:
                    Notification.objects.create(
                        user=user, title=title, body=body, action_url=action_url,
                        channel=Notification.Channel.IN_APP
                    )
                
                # 2. Push Notification
                if channel in ['all', 'push']:
                    notify_user(user, title, body, action_url=action_url, category='system')
                
                # 3. Email Notification
                if channel in ['all', 'email']:
                    send_brevo_email(user.email, user.get_full_name() or user.email, title, body)
            
            messages.success(request, "تم الإرسال عبر القنوات المحددة.")
            return redirect("control_send_notification")
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

import csv
from django.http import HttpResponse

@admin_required
def export_coupon_usage_csv(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="coupon_usage_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['التاريخ', 'العميل', 'الكوبون', 'المنتج', 'الباقة', 'المبلغ الأصلي', 'المبلغ النهائي', 'رقم الطلب'])
    
    orders = Order.objects.filter(coupon__isnull=False).select_related('customer', 'coupon').prefetch_related('items__variant__product')
    
    for o in orders:
        item = o.items.first()
        writer.writerow([
            o.created_at.strftime("%Y-%m-%d %H:%M"),
            o.customer.email,
            o.coupon.code,
            item.variant.product.name if item else "N/A",
            item.variant.name if item else "N/A",
            o.original_total,
            o.total_amount,
            o.number
        ])
    return response

@admin_required
def control_coupon_usage(request):
    q = request.GET.get('q', '')
    coupon_filter = request.GET.get('coupon', '')
    
    orders = Order.objects.filter(coupon__isnull=False).select_related('customer', 'coupon').prefetch_related('items__variant__product').order_by('-created_at')
    
    if q:
        orders = orders.filter(Q(customer__email__icontains=q) | Q(number__icontains=q))
    if coupon_filter:
        orders = orders.filter(coupon__code__iexact=coupon_filter)
        
    return render(request, "site/control_coupon_usage.html", {
        "orders": orders, 
        "query": q, 
        "coupon_filter": coupon_filter
    })

@admin_required
def control_reports(request):
    from apps.site.analytics_services import FinancialAnalyticsService
    
    # Process GET parameters into filters
    filters = {
        "date_preset": request.GET.get("date_preset", "all"),
        "start_date": request.GET.get("start_date"),
        "end_date": request.GET.get("end_date"),
        "currency_id": request.GET.get("currency_id"),
        "payment_method_id": request.GET.get("payment_method_id"),
        "tier": request.GET.get("tier"),
        "user_id": request.GET.get("user_id"),
        "include_pending": request.GET.get("include_pending") == "on",
        "reporting_currency_code": request.GET.get("reporting_currency", "USD"),
    }
    
    # Clean empty strings
    clean_filters = {k: v for k, v in filters.items() if v}
    
    analytics = FinancialAnalyticsService(clean_filters)
    
    ctx = {
        "kpis": analytics.get_dashboard_kpis(),
        "pnl": analytics.get_pnl_statement(),
        "treasury": analytics.get_treasury_status(),
        "payment_performance": analytics.get_payment_method_performance(),
        "debt_aging": analytics.get_debt_aging(),
        "trends": analytics.get_trends(),
        "cash_logs": analytics.get_cash_collection_logs(),
        "filters": filters,
        "currencies": Currency.objects.filter(is_active=True),
        "payment_methods": PaymentMethod.objects.filter(is_active=True),
        "tiers": User.Tier.choices
    }
    
    export_format = request.GET.get("export")
    if export_format == "excel":
        return export_financial_report_xlsx(ctx, clean_filters)
        
    return render(request, "site/control_reports.html", ctx)

import logging
logger = logging.getLogger(__name__)

@admin_required
def control_db_maintenance(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "cleanup":
            targets = request.POST.getlist("targets")
            deleted_counts = {}
            
            with transaction.atomic():
                if "orders" in targets:
                    from apps.orders.models import Order, OrderItem, OrderLog
                    c1 = OrderItem.objects.all().delete()[0]
                    c2 = OrderLog.objects.all().delete()[0]
                    c3 = Order.objects.all().delete()[0]
                    deleted_counts["الطلبات والمبيعات"] = c1 + c2 + c3
                    
                if "financials" in targets:
                    from apps.payments.models import DepositRequest, WithdrawalRequest
                    from apps.wallets.models import WalletTransaction, LedgerEntry
                    c1 = DepositRequest.objects.all().delete()[0]
                    c2 = WithdrawalRequest.objects.all().delete()[0]
                    c3 = WalletTransaction.objects.all().delete()[0]
                    c4 = LedgerEntry.objects.all().delete()[0]
                    deleted_counts["العمليات المالية"] = c1 + c2 + c3 + c4
                    
                if "kyc" in targets:
                    from apps.accounts.models import KYCRequest
                    c1 = KYCRequest.objects.all().delete()[0]
                    deleted_counts["طلبات التوثيق"] = c1
                    
                if "logs" in targets:
                    from apps.accounts.models import ActivityLog
                    from apps.notifications.models import Notification
                    c1 = ActivityLog.objects.all().delete()[0]
                    c2 = Notification.objects.all().delete()[0]
                    deleted_counts["سجلات النشاط والتنبيهات"] = c1 + c2
                    
                if "users" in targets:
                    # Delete ONLY customers, keep staff/admins
                    c1 = User.objects.filter(role=User.Role.CUSTOMER).delete()[0]
                    deleted_counts["المستخدمين (غير المدراء)"] = c1
                    
                if "catalog" in targets:
                    from apps.catalog.models import Product, Category, ProductVariant
                    c1 = ProductVariant.objects.all().delete()[0]
                    c2 = Product.objects.all().delete()[0]
                    c3 = Category.objects.all().delete()[0]
                    deleted_counts["الكتالوج (المنتجات والأصناف)"] = c1 + c2 + c3

            msg = "تم تصفير البيانات المختارة بنجاح: " + ", ".join([f"{k} ({v})" for k, v in deleted_counts.items()])
            messages.success(request, msg)
            return redirect("control_db_maintenance")
            
    return render(request, "site/control_db_maintenance.html")

def export_financial_report_xlsx(ctx, filters):
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        from io import BytesIO

        wb = openpyxl.Workbook()
        # ... rest of export logic ...
    except Exception as e:
        logger.exception("Excel export failed")
        return HttpResponse(
            "خدمة تصدير Excel غير متوفرة حالياً (تأكد من تثبيت openpyxl). يرجى التواصل مع المسؤول.",
            status=503,
            content_type="text/plain; charset=utf-8"
        )

    # --- Sheet 1: الملخص المالي ---
    ws = wb.active
    ws.title = "الملخص المالي"
    ws.sheet_view.rightToLeft = True
    
    # Styles
    header_font = Font(name='Arial', bold=True, color="FFFFFF", size=12)
    header_fill = PatternFill(start_color="06b6d4", end_color="06b6d4", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    # Branding & Header
    ws.merge_cells('A1:D1')
    ws['A1'] = "تقرير رقميات المالي - Raqamiyat Financial Report"
    ws['A1'].font = Font(bold=True, size=16)
    ws['A1'].alignment = center_align
    
    ws['A2'] = "تاريخ الاستخراج:"
    ws['B2'] = timezone.now().strftime("%Y-%m-%d %H:%M")
    
    ws['A3'] = "عملة التقرير:"
    ws['B3'] = ctx['kpis']['reporting_currency']

    # KPIs Section
    ws['A5'] = "المؤشر"
    ws['B5'] = "القيمة"
    for cell in ['A5', 'B5']:
        ws[cell].font = header_font
        ws[cell].fill = header_fill
        ws[cell].alignment = center_align

    kpis_data = [
        ("إجمالي الإيداعات", ctx['kpis']['total_deposits']),
        ("إجمالي السحوبات", ctx['kpis']['total_withdrawals']),
        ("صافي التدفق النقدي", ctx['kpis']['net_cashflow']),
        ("رسوم العمليات", ctx['kpis']['total_fees_earned']),
        ("أرباح المنتجات الصافية", ctx['kpis']['product_net_profit']),
        ("المقبوضات النقدية (Cash)", ctx['kpis']['total_cash_collections']),
        ("الديون المستحقة", ctx['kpis']['total_outstanding_debt']),
        ("التزامات المحافظ", ctx['kpis']['total_liabilities']),
    ]
    
    row = 6
    for label, val in kpis_data:
        ws.cell(row=row, column=1, value=label).border = border
        ws.cell(row=row, column=2, value=float(val or 0)).border = border
        ws.cell(row=row, column=2).number_format = '#,##0.00'
        row += 1

    # --- Sheet 2: الأداء والسيولة ---
    ws2 = wb.create_sheet("أداء وسائل الدفع")
    ws2.sheet_view.rightToLeft = True
    
    headers = ["الوسيلة", "حجم الإيداعات", "حجم السحوبات", "الصافي", "الرسوم", "الرصيد التقديري"]
    for col, h in enumerate(headers, 1):
        cell = ws2.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        
    row = 2
    for pm in ctx['payment_performance']:
        ws2.cell(row=row, column=1, value=pm['name']).border = border
        ws2.cell(row=row, column=2, value=float(pm['deposits_volume'] or 0)).border = border
        ws2.cell(row=row, column=3, value=float(pm['withdrawals_volume'] or 0)).border = border
        ws2.cell(row=row, column=4, value=float(pm['net_movement'] or 0)).border = border
        ws2.cell(row=row, column=5, value=float(pm['fees_generated'] or 0)).border = border
        ws2.cell(row=row, column=6, value=float(pm['real_balance'] or 0)).border = border
        row += 1

    # Auto-adjust column widths
    for sheet in wb.worksheets:
        for column in sheet.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except: pass
            sheet.column_dimensions[column_letter].width = max_length + 2

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="Raqamiyat_Financial_{timezone.now().strftime("%Y%m%d")}.xlsx"'
    return response
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
    method = get_object_or_404(PaymentMethod, pk=pk)
    old_rate = method.capital_exchange_rate
    form = PaymentMethodForm(request.POST or None, request.FILES or None, instance=method)
    if request.method == "POST" and form.is_valid():
        saved_method = form.save()
        if saved_method.capital_exchange_rate != old_rate:
            from apps.payments.models import PaymentMethodExchangeRateLog
            PaymentMethodExchangeRateLog.objects.create(
                payment_method=saved_method,
                old_rate=old_rate,
                new_rate=saved_method.capital_exchange_rate,
                changed_by=request.user,
                reason="Admin Manual Update"
            )
        return redirect("payment_methods_list")
    return render(request, "site/payment_method_builder.html", {"form": form, "method": method})
