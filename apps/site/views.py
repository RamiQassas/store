import json
from decimal import Decimal
import os
import random
import string
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.conf import settings

from apps.accounts.models import User, ModerationLog, ActivityLog, EmailVerificationToken, OTPToken
from apps.accounts.services import send_brevo_email, send_verification_email
from apps.catalog.models import Category, Product, ProductVariant
from apps.common.models import Currency
from apps.notifications.models import Notification, NotificationSetting
from apps.notifications.services import notify_user, notify_bulk
from apps.orders.models import Order, OrderItem, OrderLog, Coupon
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest
from apps.site.forms import LoginForm, RegisterForm, TicketForm, PaymentMethodForm, CurrencyForm, ModerateUserForm, ProductForm, VariantForm
from apps.support.models import ChatRoom, ChatMessage, ChatCannedReply
from apps.wallets.models import LedgerEntry, Wallet, WalletTransaction
from apps.wallets.services import get_or_create_wallet, track_pending_deposit, freeze_funds, credit_wallet, release_funds, finalize_withdrawal


# ==========================================
# --- AUTHENTICATION HELPERS (V3) ---
# ==========================================

def v3_generate_otp(user, purpose):
    """Generates a 6-digit OTP code and invalidates previous ones."""
    OTPToken.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    code = ''.join(random.choices(string.digits, k=6))
    expires_at = timezone.now() + timedelta(minutes=10)
    return OTPToken.objects.create(user=user, code=code, purpose=purpose, expires_at=expires_at)

def v3_send_otp_email(user, otp_token):
    """Sends OTP via Brevo API."""
    subject = "رمز التحقق | Raqamiyat"
    purpose_text = "لتفعيل حسابك" if otp_token.purpose == OTPToken.Purpose.REGISTRATION else \
                   "لتسجيل الدخول" if otp_token.purpose == OTPToken.Purpose.LOGIN else \
                   "لإعادة تعيين كلمة المرور"
    
    html_content = f"""
    <div dir="rtl" style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff;">
        <h1 style="color: #06b6d4; text-align: center;">رقميات | Raqamiyat</h1>
        <p>مرحباً،</p>
        <p>رمز التحقق الخاص بك {purpose_text} هو:</p>
        <div style="text-align: center; margin: 40px 0;">
            <div style="background-color: #f1f5f9; padding: 20px; border-radius: 12px; font-weight: bold; font-size: 32px; letter-spacing: 10px; display: inline-block; border: 1px solid #e2e8f0;">
                {otp_token.code}
            </div>
        </div>
        <p style="font-size: 12px; color: #64748b; text-align: center;">هذا الرمز صالح لمدة 10 دقائق فقط. لا تشارك هذا الرمز مع أي شخص.</p>
    </div>
    """
    return send_brevo_email(to_email=user.email, to_name=user.get_full_name() or user.email, subject=subject, html_content=html_content)

def v3_verify_otp_logic(user, code, purpose):
    """Validates OTP code."""
    otp = OTPToken.objects.filter(user=user, code=code, purpose=purpose, is_used=False, expires_at__gt=timezone.now()).first()
    if otp:
        otp.is_used = True
        otp.save(update_fields=["is_used", "updated_at"])
        return True
    return False


# ==========================================
# --- REBUILT AUTH FLOW (V3 - FINAL) ---
# ==========================================

def v3_login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(username=form.cleaned_data["email"], password=form.cleaned_data["password"])
        if user:
            if not user.is_account_active:
                messages.error(request, f"الحساب معطل أو موقوف. السبب: {user.suspension_reason or 'غير محدد'}")
                return render(request, "site/v3/v3_login.html", {"form": form})

            # Start OTP verification for Login
            otp = v3_generate_otp(user, OTPToken.Purpose.LOGIN)
            if v3_send_otp_email(user, otp):
                request.session["v3_auth_uid"] = str(user.id)
                request.session["v3_auth_purpose"] = OTPToken.Purpose.LOGIN
                return redirect("site_verify_otp")
            else:
                messages.error(request, "فشل إرسال رمز التحقق. يرجى المحاولة لاحقاً.")
        else:
            messages.error(request, "بيانات الدخول غير صحيحة.")
    
    return render(request, "site/v3/v3_login.html", {"form": form})


def v3_register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = User.objects.create_user(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                phone=form.cleaned_data["phone"],
            )
            get_or_create_wallet(user)
            
            ActivityLog.objects.create(user=user, action="V3 Register", description="User registered via V3 flow")

            # Send OTP for registration verification
            otp = v3_generate_otp(user, OTPToken.Purpose.REGISTRATION)
            if v3_send_otp_email(user, otp):
                request.session["v3_auth_uid"] = str(user.id)
                request.session["v3_auth_purpose"] = OTPToken.Purpose.REGISTRATION
                return redirect("site_verify_otp")
            else:
                messages.warning(request, "تم إنشاء الحساب، ولكن تعذر إرسال رمز التحقق حالياً. يرجى تسجيل الدخول.")
                return redirect("site_login")

    return render(request, "site/v3/v3_register.html", {"form": form})


def v3_verify_otp_view(request):
    uid = request.session.get("v3_auth_uid")
    purpose = request.session.get("v3_auth_purpose")
    
    if not uid or not purpose:
        messages.error(request, "انتهت جلسة التحقق. يرجى البدء من جديد.")
        return redirect("site_login")
        
    user = get_object_or_404(User, id=uid)
    
    if request.method == "POST":
        if request.POST.get("action") == "resend":
            otp = v3_generate_otp(user, purpose)
            v3_send_otp_email(user, otp)
            messages.success(request, "تم إعادة إرسال رمز التحقق.")
            return redirect("site_verify_otp")
            
        code = request.POST.get("code")
        if v3_verify_otp_logic(user, code, purpose):
            if purpose == OTPToken.Purpose.REGISTRATION:
                user.email_verified = True
                user.save(update_fields=["email_verified"])
            
            if purpose == OTPToken.Purpose.PASSWORD_RESET:
                request.session["v3_recovery_verified"] = True
                return redirect("site_reset_password")
            
            # Login for Registration and standard Login flows
            login(request, user)
            messages.success(request, "مرحبًا بك في رقميات.")
            request.session.pop("v3_auth_uid", None)
            request.session.pop("v3_auth_purpose", None)
            return redirect("dashboard")
        else:
            messages.error(request, "رمز التحقق غير صحيح أو منتهي الصلاحية.")
            
    return render(request, "site/v3/v3_verify_otp.html", {"user": user, "purpose": purpose})


def v3_forgot_password_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").lower().strip()
        user = User.objects.filter(email=email).first()
        
        if user:
            otp = v3_generate_otp(user, OTPToken.Purpose.PASSWORD_RESET)
            if v3_send_otp_email(user, otp):
                request.session["v3_auth_uid"] = str(user.id)
                request.session["v3_auth_purpose"] = OTPToken.Purpose.PASSWORD_RESET
                messages.success(request, "تم إرسال رمز التحقق لإعادة تعيين كلمة المرور.")
                return redirect("site_verify_otp")
            else:
                messages.error(request, "فشل إرسال الرمز. يرجى المحاولة لاحقاً.")
        else:
            messages.error(request, "عذراً، هذا البريد الإلكتروني غير مسجل لدينا.")
            
    return render(request, "site/v3/v3_forgot_password.html")


def v3_reset_password_view(request):
    uid = request.session.get("v3_auth_uid")
    is_verified = request.session.get("v3_recovery_verified") == True
    
    if not uid or not is_verified:
        messages.error(request, "يرجى التحقق من هويتك أولاً.")
        return redirect("site_forgot_password")
        
    user = get_object_or_404(User, id=uid)
    
    if request.method == "POST":
        p1 = request.POST.get("password")
        p2 = request.POST.get("confirm_password")
        
        if not p1 or len(p1) < 10:
            messages.error(request, "يجب أن تكون كلمة المرور 10 خانات على الأقل.")
        elif p1 != p2:
            messages.error(request, "كلمات المرور غير متطابقة.")
        else:
            user.set_password(p1)
            user.save()
            
            # Clean up all auth sessions
            request.session.flush()
            
            ActivityLog.objects.create(user=user, action="Password Reset Success", description="User reset password via V3 OTP flow")
            messages.success(request, "تم تغيير كلمة المرور بنجاح. يمكنك الآن تسجيل الدخول.")
            return redirect("site_login")
            
    return render(request, "site/v3/v3_reset_password.html", {"user_email": user.email})


def v3_logout_view(request):
    logout(request)
    messages.info(request, "تم تسجيل الخروج بنجاح.")
    return redirect("home")


# ==========================================
# --- CORE APPLICATION VIEWS ---
# ==========================================

def service_worker(request):
    sw_path = os.path.join(settings.BASE_DIR, 'apps', 'site', 'static', 'site', 'js', 'sw.js')
    try:
        with open(sw_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return HttpResponse(content, content_type='application/javascript')
    except FileNotFoundError:
        return HttpResponse("// Service worker file not found", content_type='application/javascript', status=404)


def home(request):
    featured_products = Product.objects.filter(is_active=True, is_featured=True).select_related("category").prefetch_related("variants")[:6]
    top_products = Product.objects.filter(is_active=True).select_related("category").prefetch_related("variants").order_by("sort_order", "name")[:8]
    categories = Category.objects.filter(is_active=True).order_by("sort_order", "name")
    stats = {
        "products": Product.objects.filter(is_active=True).count(),
        "categories": categories.count(),
        "orders": Order.objects.count(),
        "tickets": ChatRoom.objects.exclude(status=ChatRoom.Status.CLOSED).count(),
        "users": User.objects.count(),
    }
    return render(request, "site/home.html", {"featured_products": featured_products, "top_products": top_products, "categories": categories, "stats": stats})


def catalog(request):
    cat_id = request.GET.get("category")
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "newest")
    
    categories = Category.objects.filter(is_active=True).annotate(product_count=Count('products', filter=Q(products__is_active=True))).order_by("sort_order", "name")
    products = Product.objects.filter(is_active=True).select_related("category").prefetch_related("variants")
    
    if cat_id: products = products.filter(category_id=cat_id)
    if q: products = products.filter(Q(name__icontains=q) | Q(description__icontains=q))
    
    if sort == "price_low": products = products.order_by("variants__price")
    elif sort == "price_high": products = products.order_by("-variants__price")
    else: products = products.order_by("-created_at")
        
    return render(request, "site/catalog.html", {"categories": categories, "products": products.distinct(), "active_category": cat_id, "query": q, "sort": sort})


def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related("category").prefetch_related("variants"), pk=pk, is_active=True)
    variants = product.variants.filter(is_active=True).order_by("sort_order", "price")
    
    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect("site_login")
        if not request.user.email_verified:
            messages.error(request, "يرجى تفعيل بريدك الإلكتروني أولاً.")
            return redirect("dashboard")
        if request.user.restriction_purchases:
            messages.error(request, "حسابك مقيد من الشراء.")
            return redirect("dashboard")

        vid = request.POST.get("variant_id")
        qty = max(int(request.POST.get("quantity", 1)), 1)
        
        if vid:
            try:
                from apps.orders.services import create_order
                create_order(request.user, vid, quantity=qty)
                messages.success(request, "تم إنشاء الطلب بنجاح.")
                return redirect("dashboard")
            except Exception as e:
                messages.error(request, str(e))
                
    return render(request, "site/product_detail.html", {"product": product, "variants": variants})


@login_required
def dashboard(request):
    wallet = Wallet.objects.filter(user=request.user).select_related("currency").first() or get_or_create_wallet(request.user)
    return render(request, "site/dashboard.html", {
        "wallet": wallet,
        "orders": request.user.orders.all()[:6],
        "deposits": request.user.deposits.all()[:6],
        "stats": {"orders": request.user.orders.count()}
    })


@login_required
def wallet_page(request):
    wallet = Wallet.objects.filter(user=request.user).select_related("currency").first() or get_or_create_wallet(request.user)
    return render(request, "site/wallet.html", {
        "wallet": wallet,
        "ledger_entries": wallet.ledger_entries.all()[:20]
    })


@login_required
def deposits(request):
    if request.user.restriction_deposits:
        messages.error(request, "حسابك مقيد من الإيداع.")
        return redirect("dashboard")
    methods = PaymentMethod.objects.filter(is_active=True, can_deposit=True).prefetch_related("supported_currencies")
    if request.method == "POST":
        method_id = request.POST.get("payment_method")
        currency_id = request.POST.get("currency")
        amount_str = request.POST.get("amount", "0")
        amount = Decimal(amount_str) if amount_str else Decimal("0")
        proof = request.FILES.get("proof_image")
        
        method = get_object_or_404(methods, id=method_id)
        currency = get_object_or_404(Currency, id=currency_id)
        wallet = get_or_create_wallet(request.user)

        with transaction.atomic():
            deposit = DepositRequest.objects.create(
                user=request.user, payment_method=method, amount=amount,
                currency=currency, proof_image=proof, status=DepositRequest.Status.PENDING
            )
            track_pending_deposit(wallet.id, amount, reference=f"deposit:{deposit.id}")
            messages.success(request, "طلب الإيداع قيد المراجعة.")
            return redirect("dashboard")
            
    return render(request, "site/deposits.html", {"payment_methods": methods})


@login_required
def withdrawals(request):
    if request.user.restriction_withdrawals:
        messages.error(request, "حسابك مقيد من السحب.")
        return redirect("dashboard")
    methods = PaymentMethod.objects.filter(is_active=True, can_withdraw=True).prefetch_related("supported_currencies")
    if request.method == "POST":
        method_id = request.POST.get("payment_method")
        currency_id = request.POST.get("currency")
        amount = Decimal(request.POST.get("amount", "0"))
        
        method = get_object_or_404(methods, id=method_id)
        currency = get_object_or_404(Currency, id=currency_id)
        wallet = get_or_create_wallet(request.user)
        
        if wallet.available_balance >= amount:
            with transaction.atomic():
                withdrawal = WithdrawalRequest.objects.create(
                    user=request.user, payment_method=method, amount=amount,
                    currency=currency, status=WithdrawalRequest.Status.PENDING
                )
                freeze_funds(wallet.id, amount, reference=f"with:{withdrawal.id}")
                messages.success(request, "طلب السحب قيد المراجعة.")
                return redirect("dashboard")
        else:
            messages.error(request, "رصيد غير كافٍ.")
            
    return render(request, "site/withdrawals.html", {"payment_methods": methods})


# ==========================================
# --- ADMIN CONTROL PANEL VIEWS ---
# ==========================================

@staff_member_required
def control_dashboard(request):
    stats = {
        "users": User.objects.count(),
        "products": Product.objects.count(),
        "orders": Order.objects.count(),
        "deposits": DepositRequest.objects.count(),
    }
    return render(request, "site/control_dashboard.html", {"stats": stats})

@staff_member_required
def control_users_list(request):
    users = User.objects.select_related("wallet").order_by("-date_joined")
    return render(request, "site/control_users_list.html", {"users": users, "tiers": User.Tier.choices, "roles": User.Role.choices})

@staff_member_required
def control_user_moderate(request, public_uuid):
    target_user = get_object_or_404(User, public_uuid=public_uuid)
    form = ModerateUserForm(request.POST or None, instance=target_user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if not user.is_account_active:
             from django.contrib.sessions.models import Session
             sessions = Session.objects.filter(expire_date__gte=timezone.now())
             for s in sessions:
                 if str(user.id) == s.get_decoded().get('_auth_user_id'): s.delete()
        messages.success(request, "تم تحديث بيانات المستخدم.")
        return redirect("control_users_list")
    return render(request, "site/control_user_moderate.html", {"form": form, "user_to_moderate": target_user})

@staff_member_required
def control_deposits(request):
    deposits = DepositRequest.objects.select_related("user", "payment_method", "currency").all()
    return render(request, "site/control_deposits.html", {"deposits": deposits})

@staff_member_required
def control_withdrawals(request):
    withdrawals = WithdrawalRequest.objects.select_related("user", "payment_method", "currency").all()
    return render(request, "site/control_withdrawals.html", {"withdrawals": withdrawals})

@staff_member_required
def control_withdrawal_detail(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest.objects.select_related("user"), pk=pk)
    return render(request, "site/control_withdrawal_detail.html", {"withdrawal": withdrawal})

@staff_member_required
def payment_methods_list(request):
    methods = PaymentMethod.objects.all().order_by("display_order")
    return render(request, "site/payment_methods_list.html", {"methods": methods})

@staff_member_required
def payment_method_create(request):
    form = PaymentMethodForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("payment_methods_list")
    return render(request, "site/payment_method_builder.html", {"form": form})

@staff_member_required
def payment_method_edit(request, pk):
    method = get_object_or_404(PaymentMethod, pk=pk)
    form = PaymentMethodForm(request.POST or None, request.FILES or None, instance=method)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("payment_methods_list")
    return render(request, "site/payment_method_builder.html", {"form": form, "method": method})

@staff_member_required
def currencies_list(request):
    currencies = Currency.objects.all()
    return render(request, "site/currencies_list.html", {"currencies": currencies})

@staff_member_required
def currency_create(request):
    form = CurrencyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("currencies_list")
    return render(request, "site/currency_form.html", {"form": form})

@staff_member_required
def currency_edit(request, pk):
    currency = get_object_or_404(Currency, pk=pk)
    form = CurrencyForm(request.POST or None, instance=currency)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("currencies_list")
    return render(request, "site/currency_form.html", {"form": form, "currency": currency})

@staff_member_required
def control_products_list(request):
    products = Product.objects.all()
    return render(request, "site/control_products_list.html", {"products": products})

@staff_member_required
def control_product_create(request):
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("control_products_list")
    return render(request, "site/control_product_builder.html", {"form": form})

@staff_member_required
def control_product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("control_products_list")
    return render(request, "site/control_product_builder.html", {"form": form, "product": product})

@staff_member_required
def control_variant_create(request, product_pk):
    product = get_object_or_404(Product, pk=product_pk)
    form = VariantForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        v = form.save(commit=False)
        v.product = product
        v.save()
        return redirect("control_product_edit", pk=product.pk)
    return render(request, "site/control_variant_form.html", {"form": form, "product": product})

@staff_member_required
def control_variant_edit(request, pk):
    variant = get_object_or_404(ProductVariant, pk=pk)
    form = VariantForm(request.POST or None, instance=variant)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("control_product_edit", pk=variant.product.pk)
    return render(request, "site/control_variant_form.html", {"form": form})

@staff_member_required
def control_orders_list(request):
    orders = Order.objects.all()
    return render(request, "site/control_orders_list.html", {"orders": orders})

@staff_member_required
def control_order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    return render(request, "site/control_order_detail.html", {"order": order})

@staff_member_required
def control_wallets_list(request):
    wallets = Wallet.objects.all()
    return render(request, "site/control_wallets_list.html", {"wallets": wallets})

@staff_member_required
def control_reports(request):
    return render(request, "site/control_reports.html")

@staff_member_required
def control_send_notification(request):
    if request.method == "POST":
        notify_bulk(User.objects.filter(is_active=True), request.POST.get("title"), request.POST.get("body"))
        return redirect("control_send_notification")
    return render(request, "site/control_notification_form.html")

@staff_member_required
def control_category_create_ajax(request):
    if request.method == "POST":
        c = Category.objects.create(name=request.POST.get("name"))
        return JsonResponse({"status":"ok", "id": str(c.id), "name": c.name})
    return JsonResponse({"status":"error"}, status=400)


# --- ADDITIONAL SITE VIEWS ---
def privacy_policy(request): return render(request, "site/privacy_policy.html")
def terms_of_service(request): return render(request, "site/terms_of_service.html")
def refund_policy(request): return render(request, "site/refund_policy.html")
def contact_page(request): return render(request, "site/contact.html")
def set_currency(request): return redirect("home")
def email_verify(request, uidb64, token): return redirect("site_login")
def resend_verification(request): return redirect("dashboard")
def notification_settings(request): return render(request, "site/notification_settings.html")
def tickets(request): return render(request, "site/tickets.html")
def ticket_detail(request, pk): return render(request, "site/ticket_detail.html")
