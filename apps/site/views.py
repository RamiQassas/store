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

from apps.accounts.models import User, ModerationLog, ActivityLog, EmailVerificationToken, OTPToken, KYCRequest, KYCSettings
from apps.accounts.services import send_brevo_email, send_verification_email
from apps.common.countries import COUNTRIES
from apps.catalog.models import Category, Product, ProductVariant
from apps.common.models import Currency
from apps.notifications.models import Notification, NotificationSetting
from apps.notifications.services import notify_user, notify_bulk
from apps.orders.models import Order, OrderItem, OrderLog, Coupon
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest
from apps.site.forms import LoginForm, RegisterForm, TicketForm, PaymentMethodForm, CurrencyForm, ModerateUserForm, ProductForm, VariantForm, KYCRequestForm, KYCSettingsForm
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
        phone = request.POST.get("phone") # Value from iti.getNumber() hidden input
        
        with transaction.atomic():
            user = User.objects.create_user(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                phone=phone,
            )
            get_or_create_wallet(user)
            
            ActivityLog.objects.create(user=user, action="V3 Register", description="User registered via V3 flow with enhanced validation")

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
                return redirect("v3_reset_password")
            
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
    request.user.reset_daily_limits_if_needed()
    wallet = Wallet.objects.filter(user=request.user).select_related("currency").first() or get_or_create_wallet(request.user)
    kyc_request = getattr(request.user, 'kyc_request', None)
    return render(request, "site/dashboard.html", {
        "wallet": wallet, "orders": request.user.orders.all()[:6],
        "deposits": request.user.deposits.all()[:6], "stats": {"orders": request.user.orders.count()},
        "kyc_request": kyc_request
    })


@login_required
def wallet_page(request):
    request.user.reset_daily_limits_if_needed()
    wallet = Wallet.objects.filter(user=request.user).select_related("currency").first() or get_or_create_wallet(request.user)
    return render(request, "site/wallet.html", {"wallet": wallet, "ledger_entries": wallet.ledger_entries.all()[:20]})


@login_required
def deposits(request):
    if request.user.restriction_deposits:
        messages.error(request, "حسابك مقيد من الإيداع.")
        return redirect("dashboard")
    
    request.user.reset_daily_limits_if_needed()
    remaining_limit = request.user.remaining_deposit_limit
    
    methods = PaymentMethod.objects.filter(is_active=True, can_deposit=True).prefetch_related("supported_currencies")
    if request.method == "POST":
        method_id = request.POST.get("payment_method")
        currency_id = request.POST.get("currency")
        amount_str = request.POST.get("amount", "0")
        amount = Decimal(amount_str) if amount_str else Decimal("0")
        proof = request.FILES.get("proof_image")
        
        currency = get_object_or_404(Currency, id=currency_id)
        # amount is in local currency (e.g., SYP). Convert to base (USD) for limits and wallet.
        amount_base = currency.to_base(amount, operation="deposit")
        
        if amount_base > remaining_limit:
            messages.error(
                request, 
                f"تجاوزت الحد اليومي للإيداع. حدك المتبقي هو {remaining_limit:.2f} USD، "
                f"بينما تبلغ قيمة هذه العملية {amount_base:.2f} USD."
            )
            return redirect("dashboard_deposits")
            
        method = get_object_or_404(methods, id=method_id)
        user_custom = request.user.custom_payment_limits.get(str(method.id), {})
        method_limit = Decimal(str(user_custom['deposit'])) if user_custom.get('deposit') else method.daily_deposit_limit

        method_usage_today = Decimal("0.00")
        today_deposits = DepositRequest.objects.filter(
            user=request.user, payment_method=method, created_at__date=timezone.now().date()
        ).exclude(status=DepositRequest.Status.REJECTED).select_related("currency")
        
        for d in today_deposits:
            method_usage_today += d.currency.to_base(d.amount, operation="deposit")
        
        method_remaining = max(Decimal("0.00"), method_limit - method_usage_today)
        if amount_base > method_remaining:
            messages.error(
                request, 
                f"تجاوزت حد الإيداع لهذه الوسيلة. الحد المتبقي للوسيلة هو {method_remaining:.2f} USD، "
                f"بينما تبلغ قيمة هذه العملية {amount_base:.2f} USD."
            )
            return redirect("dashboard_deposits")

        wallet = get_or_create_wallet(request.user)
        # wallet_amount is the base USD amount.
        wallet_amount = amount_base

        with transaction.atomic():
            deposit = DepositRequest.objects.create(
                user=request.user, payment_method=method, amount=amount,
                currency=currency, wallet_amount=wallet_amount, proof_image=proof, status=DepositRequest.Status.PENDING
            )
            track_pending_deposit(wallet.id, wallet_amount, reference=f"deposit:{deposit.id}")
            request.user.daily_deposit_usage += amount_base
            request.user.save(update_fields=["daily_deposit_usage"])
            messages.success(request, "طلب الإيداع قيد المراجعة.")
            return redirect("dashboard")
            
    return render(request, "site/deposits.html", {
        "payment_methods": methods, "remaining_limit": remaining_limit, "daily_limit": request.user.daily_deposit_limit
    })


@login_required
def withdrawals(request):
    if request.user.restriction_withdrawals:
        messages.error(request, "حسابك مقيد من السحب.")
        return redirect("dashboard")
    
    request.user.reset_daily_limits_if_needed()
    remaining_limit = request.user.remaining_withdrawal_limit
    
    methods = PaymentMethod.objects.filter(is_active=True, can_withdraw=True).prefetch_related("supported_currencies")
    if request.method == "POST":
        method_id = request.POST.get("payment_method")
        currency_id = request.POST.get("currency")
        amount = Decimal(request.POST.get("amount", "0"))
        
        currency = get_object_or_404(Currency, id=currency_id)
        amount_base = currency.to_base(amount, operation="withdraw")
        
        if amount_base > remaining_limit:
            messages.error(
                request, 
                f"تجاوزت الحد اليومي للسحب. حدك المتبقي هو {remaining_limit:.2f} USD، "
                f"بينما تبلغ قيمة هذه العملية {amount_base:.2f} USD."
            )
            return redirect("dashboard_withdrawals")
            
        method = get_object_or_404(methods, id=method_id)
        user_custom = request.user.custom_payment_limits.get(str(method.id), {})
        method_limit = Decimal(str(user_custom['withdraw'])) if user_custom.get('withdraw') else method.daily_withdrawal_limit
        
        method_usage_today = Decimal("0.00")
        today_withdrawals = WithdrawalRequest.objects.filter(
            user=request.user, payment_method=method, created_at__date=timezone.now().date()
        ).exclude(status=WithdrawalRequest.Status.REJECTED).select_related("currency")

        for w in today_withdrawals:
            method_usage_today += w.currency.to_base(w.amount, operation="withdraw")
        
        method_remaining = max(Decimal("0.00"), method_limit - method_usage_today)
        if amount_base > method_remaining:
            messages.error(
                request, 
                f"تجاوزت حد السحب لهذه الوسيلة. الحد المتبقي للوسيلة هو {method_remaining:.2f} USD، "
                f"بينما تبلغ قيمة هذه العملية {amount_base:.2f} USD."
            )
            return redirect("dashboard_withdrawals")

        wallet = get_or_create_wallet(request.user)
        wallet_amount = amount_base
        
        if wallet.available_balance >= wallet_amount:
            with transaction.atomic():
                withdrawal = WithdrawalRequest.objects.create(
                    user=request.user, payment_method=method, amount=amount,
                    currency=currency, wallet_amount=wallet_amount, status=WithdrawalRequest.Status.PENDING
                )
                freeze_funds(wallet.id, wallet_amount, reference=f"with:{withdrawal.id}")
                request.user.daily_withdrawal_usage += amount_base
                request.user.save(update_fields=["daily_withdrawal_usage"])
                messages.success(request, "طلب السحب قيد المراجعة.")
                return redirect("dashboard")
        else:
            messages.error(request, "رصيد غير كافٍ.")
            
    return render(request, "site/withdrawals.html", {
        "payment_methods": methods, "remaining_limit": remaining_limit, "daily_limit": request.user.daily_withdrawal_limit
    })


@login_required
def kyc_request_view(request):
    existing = getattr(request.user, 'kyc_request', None)
    settings_obj = KYCSettings.get_settings()
    kyc_status = existing.status if existing else 'none'
    kyc_rejection_reason = existing.rejection_reason if existing else ''

    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')).split(',')[0].strip()
    default_country = "SY"
    if client_ip and client_ip not in ['127.0.0.1', 'localhost']:
        try:
            import requests
            response = requests.get(f"https://ipapi.co/{client_ip}/json/", timeout=3)
            if response.status_code == 200:
                default_country = response.json().get("country_code", "SY")
        except: pass

    initial_data = {"nationality": default_country, "issuing_country": default_country} if not existing else None
    form = KYCRequestForm(request.POST or None, request.FILES or None, 
                          instance=existing if existing and existing.status == KYCRequest.Status.REJECTED else None,
                          initial=initial_data, is_admin=False)
    
    if request.method == "POST" and form.is_valid():
        if existing and existing.status in [KYCRequest.Status.PENDING, KYCRequest.Status.APPROVED]:
            messages.error(request, "طلب قيد المعالجة.")
            return redirect("dashboard")
            
        kyc = form.save(commit=False)
        blocked = False
        if settings_obj.restricted_countries:
            if (settings_obj.block_by_nationality and kyc.nationality in settings_obj.restricted_countries) or \
               (settings_obj.block_by_issuing_country and kyc.issuing_country in settings_obj.restricted_countries):
                blocked = True
                
        if blocked:
            messages.error(request, "دولتك غير مدعومة حالياً.")
            return redirect("site_kyc_request")

        kyc.user = request.user
        kyc.status = KYCRequest.Status.PENDING
        kyc.save()
        messages.success(request, "تم تقديم الطلب.")
        return redirect("dashboard")
        
    return render(request, "site/v3/v3_kyc_form.html", {
        "form": form, "kyc_status": kyc_status, "kyc_rejection_reason": kyc_rejection_reason,
        "restricted_countries": settings_obj.restricted_countries, "all_countries": COUNTRIES
    })


from apps.common.decorators import finance_required, support_required, kyc_required, admin_required
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest

@admin_required
def control_dashboard(request):
    stats = {"users": User.objects.count(), "products": Product.objects.count(), "orders": Order.objects.count(), "deposits": DepositRequest.objects.count(), "pending_kycs": KYCRequest.objects.filter(status=KYCRequest.Status.PENDING).count()}
    return render(request, "site/control_dashboard.html", {"stats": stats})

@kyc_required
def control_kycs_list(request):
    kycs = KYCRequest.objects.select_related("user").all().order_by("-created_at")
    return render(request, "site/control_kycs_list.html", {"kycs": kycs})

@kyc_required
def control_kyc_detail(request, pk):
    kyc = get_object_or_404(KYCRequest.objects.select_related("user"), pk=pk)
    global_settings = KYCSettings.get_settings()
    
    # Use is_admin=True to make images optional for editing text data
    form = KYCRequestForm(request.POST or None, request.FILES or None, instance=kyc, is_admin=True)
    payment_methods = PaymentMethod.objects.filter(is_active=True)
    
    if request.method == "POST":
        action = request.POST.get("action")
        
        # 1. Update/Edit Information (Including image replacement)
        if action == "update_info":
            if form.is_valid():
                form.save()
                messages.success(request, "تم تحديث بيانات وصور التوثيق بنجاح.")
                return redirect("control_kyc_detail", pk=pk)
        elif action == "update_limits":
            user = kyc.user
            
            def parse_decimal(val, default="0.00"):
                if not val: return Decimal(default)
                # Handle Arabic commas or other separators
                sanitized = str(val).replace(',', '.')
                try:
                    return Decimal(sanitized)
                except:
                    return Decimal(default)

            user.daily_deposit_limit = parse_decimal(request.POST.get("global_deposit_limit"), "100.00")
            user.daily_withdrawal_limit = parse_decimal(request.POST.get("global_withdrawal_limit"), "100.00")
            user.has_custom_limits = True
            
            custom_limits = {}
            for method in payment_methods:
                dep_raw = request.POST.get(f"method_dep_{method.id}")
                withd_raw = request.POST.get(f"method_with_{method.id}")
                
                if dep_raw or withd_raw:
                    # Sanitize for storage to ensure dot is used as decimal separator
                    dep = str(dep_raw).replace(',', '.') if dep_raw else ""
                    withd = str(withd_raw).replace(',', '.') if withd_raw else ""
                    custom_limits[str(method.id)] = {"deposit": dep, "withdraw": withd}
            
            user.custom_payment_limits = custom_limits
            user.save()
            messages.success(request, "تم تحديث الحدود بنجاح.")
            return redirect("control_kyc_detail", pk=pk)
        elif action == "approve":
            with transaction.atomic():
                kyc.status = KYCRequest.Status.APPROVED
                kyc.reviewed_by = request.user
                kyc.reviewed_at = timezone.now()
                kyc.save()
                user = kyc.user
                user.is_kyc_verified = True
                if not user.has_custom_limits:
                    user.daily_deposit_limit = global_settings.verified_daily_deposit_limit
                    user.daily_withdrawal_limit = global_settings.verified_daily_withdrawal_limit
                user.first_name = kyc.first_name
                user.last_name = f"{kyc.father_name} {kyc.last_name}"
                user.save()
                messages.success(request, "تم القبول.")
                return redirect("control_kyc_detail", pk=pk)
        elif action == "reject":
            with transaction.atomic():
                kyc.status = KYCRequest.Status.REJECTED
                kyc.rejection_reason = request.POST.get("rejection_reason", "")
                kyc.reviewed_by = request.user
                kyc.reviewed_at = timezone.now()
                kyc.save()
                user = kyc.user
                user.is_kyc_verified = False
                user.daily_deposit_limit = global_settings.unverified_daily_deposit_limit
                user.daily_withdrawal_limit = global_settings.unverified_daily_withdrawal_limit
                user.has_custom_limits = False
                user.save()
                messages.warning(request, "تم الرفض.")
                return redirect("control_kyc_detail", pk=pk)
        elif action == "revert":
            with transaction.atomic():
                kyc.status = KYCRequest.Status.PENDING
                kyc.save(update_fields=["status"])
                user = kyc.user
                user.is_kyc_verified = False
                user.daily_deposit_limit = global_settings.unverified_daily_deposit_limit
                user.daily_withdrawal_limit = global_settings.unverified_daily_withdrawal_limit
                user.save()
                messages.info(request, "تمت الإعادة.")
                return redirect("control_kyc_detail", pk=pk)
        elif action == "unverify":
            with transaction.atomic():
                user = kyc.user
                user.is_kyc_verified = False
                user.has_custom_limits = False
                user.daily_deposit_limit = global_settings.unverified_daily_deposit_limit
                user.daily_withdrawal_limit = global_settings.unverified_daily_withdrawal_limit
                user.save()
                kyc.status = KYCRequest.Status.REJECTED
                kyc.rejection_reason = "تم إلغاء التوثيق."
                kyc.save()
                messages.error(request, "تم إلغاء التوثيق.")
                return redirect("control_kycs_list")
            
    return render(request, "site/control_kyc_detail.html", {"kyc": kyc, "form": form, "payment_methods": payment_methods})

@kyc_required
def control_kyc_settings(request):
    settings_obj = KYCSettings.get_settings()
    form = KYCSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "unblock_country":
            code = request.POST.get("country_code")
            if code in settings_obj.restricted_countries:
                settings_obj.restricted_countries.remove(code)
                settings_obj.save()
                messages.success(request, f"فك الحظر عن {code}.")
            return redirect("control_kyc_settings")
        elif form.is_valid():
            form.save()
            messages.success(request, "تم الحفظ.")
            return redirect("control_kyc_settings")
    return render(request, "site/control_kyc_settings.html", {"form": form, "settings": settings_obj, "stats_verified_count": User.objects.filter(is_kyc_verified=True).count()})

@admin_required
def control_user_moderate(request, public_uuid):
    user = get_object_or_404(User, public_uuid=public_uuid)
    form = ModerateUserForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if not user.is_account_active:
             from django.contrib.sessions.models import Session
             sessions = Session.objects.filter(expire_date__gte=timezone.now())
             for s in sessions:
                 if str(user.id) == s.get_decoded().get('_auth_user_id'): s.delete()
        messages.success(request, "تم التحديث.")
        return redirect("control_users_list")
    return render(request, "site/control_user_moderate.html", {"form": form, "user_to_moderate": user})

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
    form = PaymentMethodForm(request.POST or None, request.FILES or None, instance=method)
    if request.method == "POST" and form.is_valid(): form.save(); return redirect("payment_methods_list")
    return render(request, "site/payment_method_builder.html", {"form": form, "method": method})
@admin_required
def control_users_list(request): return render(request, "site/control_users_list.html", {"users": User.objects.select_related("wallet").order_by("-date_joined"), "tiers": User.Tier.choices, "roles": User.Role.choices})
def privacy_policy(request): return render(request, "site/privacy_policy.html")
def terms_of_service(request): return render(request, "site/terms_of_service.html")
def refund_policy(request): return render(request, "site/refund_policy.html")
def contact_page(request): return render(request, "site/contact.html")
def set_currency(request):
    currency_id = request.GET.get("currency") or request.POST.get("currency")
    if currency_id:
        currency = Currency.objects.filter(id=currency_id, is_active=True).first()
        if currency:
            request.session["preferred_currency_id"] = str(currency.id)
            if request.user.is_authenticated:
                request.user.preferred_currency = currency
                request.user.save(update_fields=["preferred_currency"])
            messages.success(request, f"تم تغيير العملة المفضلة إلى {currency.name}.")
    
    # Redirect back to referring page or home
    next_url = request.META.get('HTTP_REFERER', 'home')
    return redirect(next_url)
def email_verify(request, uidb64, token): return redirect("site_login")
def resend_verification(request): return redirect("dashboard")
@login_required
def notification_settings(request):
    from apps.notifications.models import NotificationSetting
    settings_obj, created = NotificationSetting.objects.get_or_create(user=request.user)
    
    if request.method == "POST":
        settings_obj.in_app_orders = request.POST.get("in_app_orders") == "on"
        settings_obj.push_orders = request.POST.get("push_orders") == "on"
        settings_obj.in_app_financial = request.POST.get("in_app_financial") == "on"
        settings_obj.push_financial = request.POST.get("push_financial") == "on"
        settings_obj.in_app_support = request.POST.get("in_app_support") == "on"
        settings_obj.push_support = request.POST.get("push_support") == "on"
        settings_obj.in_app_promotions = request.POST.get("in_app_promotions") == "on"
        settings_obj.push_promotions = request.POST.get("push_promotions") == "on"
        settings_obj.save()
        messages.success(request, "تم حفظ إعدادات الإشعارات بنجاح.")
        return redirect("notification_settings")
        
    return render(request, "site/notification_settings.html", {"settings": settings_obj})
def tickets(request): return render(request, "site/tickets.html")
def ticket_detail(request, pk): return render(request, "site/ticket_detail.html")

@finance_required
def control_deposits(request):
    status_filter = request.GET.get('status')
    deposits = DepositRequest.objects.select_related('user', 'currency', 'payment_method').all().order_by('-created_at')
    if status_filter:
        deposits = deposits.filter(status=status_filter)
    
    return render(request, "site/control_deposits.html", {
        "deposits": deposits,
        "status_choices": DepositRequest.Status.choices,
        "current_status": status_filter
    })

@finance_required
def control_withdrawals(request):
    status_filter = request.GET.get('status')
    withdrawals = WithdrawalRequest.objects.select_related('user', 'currency', 'payment_method').all().order_by('-created_at')
    if status_filter:
        withdrawals = withdrawals.filter(status=status_filter)
        
    return render(request, "site/control_withdrawals.html", {
        "withdrawals": withdrawals,
        "status_choices": WithdrawalRequest.Status.choices,
        "current_status": status_filter
    })

@finance_required
def control_withdrawal_detail(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest.objects.select_related('user', 'user__wallet'), pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        admin_note = request.POST.get("admin_note", "")
        
        from apps.wallets.services import release_funds, finalize_withdrawal
        
        if action == "approve":
            withdrawal.status = WithdrawalRequest.Status.APPROVED
            withdrawal.admin_note = admin_note
            messages.success(request, "تمت الموافقة المبدئية على الطلب.")
        elif action == "process":
            withdrawal.status = WithdrawalRequest.Status.PROCESSING
            withdrawal.admin_note = admin_note
            messages.info(request, "بدأت معالجة الطلب.")
        elif action == "complete":
            finalize_withdrawal(
                withdrawal.user.wallet.id, 
                withdrawal.amount, 
                reference=f"with_complete:{withdrawal.id}", 
                description=f"Withdrawal completed. {admin_note}",
                created_by=request.user
            )
            withdrawal.status = WithdrawalRequest.Status.COMPLETED
            withdrawal.admin_note = admin_note
            withdrawal.reviewed_by = request.user
            withdrawal.reviewed_at = timezone.now()
            withdrawal.save()
            messages.success(request, "تم إتمام عملية السحب بنجاح.")
            return redirect("control_withdrawals")
        elif action == "reject":
            release_funds(
                withdrawal.user.wallet.id, 
                withdrawal.amount, 
                reference=f"with_rej:{withdrawal.id}", 
                description=f"Withdrawal rejected: {admin_note}",
                created_by=request.user
            )
            withdrawal.status = WithdrawalRequest.Status.REJECTED
            withdrawal.admin_note = admin_note
            withdrawal.reviewed_by = request.user
            withdrawal.reviewed_at = timezone.now()
            withdrawal.save()
            messages.error(request, "تم رفض طلب السحب وإعادة الرصيد للمستخدم.")
            return redirect("control_withdrawals")
        
        withdrawal.save()
        return redirect("control_withdrawal_detail", pk=pk)

    return render(request, "site/control_withdrawal_detail.html", {"withdrawal": withdrawal})

@finance_required
def control_debts(request):
    from django.db.models import Q
    q = request.GET.get('q', '')
    users = User.objects.select_related('wallet').all()
    if q:
        users = users.filter(Q(email__icontains=q) | Q(phone__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    
    if request.method == "POST":
        user_id = request.POST.get("user_id")
        action = request.POST.get("action")
        amount = Decimal(request.POST.get("amount", "0"))
        reason = request.POST.get("reason", "")
        
        target_user = get_object_or_404(User, id=user_id)
        wallet = target_user.wallet
        
        try:
            if action == "add_debt":
                from apps.wallets.services import add_debt
                add_debt(wallet.id, amount, reference=f"admin_debt_{timezone.now().timestamp()}", reason=reason, created_by=request.user)
                messages.success(request, f"تم إضافة دين بقيمة {amount} للمستخدم {target_user.email}")
            elif action == "pay_debt":
                from apps.wallets.services import pay_debt
                pay_debt(wallet.id, amount, reference=f"admin_pay_{timezone.now().timestamp()}", reason=reason, created_by=request.user, deduct_from_balance=False)
                messages.success(request, f"تم تسجيل سداد بقيمة {amount} للمستخدم {target_user.email}")
        except Exception as e:
            messages.error(request, str(e))
            
        return redirect(f"{request.path}?q={q}")

    return render(request, "site/control_debts.html", {"users": users, "query": q})

@admin_required
def currencies_list(request):
    from apps.common.models import Currency
    currencies = Currency.objects.all().order_by('display_order', 'code')
    return render(request, "site/currencies_list.html", {"currencies": currencies})
@admin_required
def currency_create(request): return render(request, "site/currency_form.html")
@admin_required
def currency_edit(request, pk): return render(request, "site/currency_form.html")

@support_required
def control_products_list(request): return render(request, "site/control_products_list.html")
@support_required
def control_product_create(request): return render(request, "site/control_product_builder.html")
@support_required
def control_category_create_ajax(request): return JsonResponse({"status":"ok"})
@support_required
def control_product_edit(request, pk): return render(request, "site/control_product_builder.html")
@support_required
def control_variant_create(request, product_pk): return render(request, "site/control_variant_form.html")
@support_required
def control_variant_edit(request, pk): return render(request, "site/control_variant_form.html")

@support_required
def control_orders_list(request): return render(request, "site/control_orders_list.html")
@support_required
def control_order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related('customer', 'customer__wallet').prefetch_related('items__variant__product', 'logs'), pk=pk)
    
    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "update_status":
            new_status = request.POST.get("status")
            admin_note = request.POST.get("admin_note", "")
            if new_status and new_status != order.status:
                order.status = new_status
                order.save()
                OrderLog.objects.create(order=order, status=new_status, note=admin_note, created_by=request.user)
                messages.success(request, "تم تحديث حالة الطلب بنجاح.")
        
        elif action == "update_fulfillment":
            # Extract dynamic key-value pairs
            keys = request.POST.getlist("ff_key[]")
            values = request.POST.getlist("ff_value[]")
            
            new_fulfillment = {}
            for k, v in zip(keys, values):
                if k.strip():
                    new_fulfillment[k.strip()] = v.strip()
                    
            order.fulfillment_data = new_fulfillment
            order.save(update_fields=["fulfillment_data"])
            messages.success(request, "تم تحديث بيانات التنفيذ.")
            
        return redirect("control_order_detail", pk=pk)
        
    return render(request, "site/control_order_detail.html", {"order": order, "readable_fulfillment": order.fulfillment_data})

@finance_required
def control_wallets_list(request):
    q = request.GET.get('q', '')
    wallets = Wallet.objects.select_related('user', 'currency').all().order_by('-updated_at')
    if q:
        wallets = wallets.filter(Q(user__email__icontains=q) | Q(user__first_name__icontains=q))
    return render(request, "site/control_wallets_list.html", {"wallets": wallets, "query": q})
@finance_required
def control_reports(request): return render(request, "site/control_reports.html")

@support_required
def control_send_notification(request): return render(request, "site/control_notification_form.html")
