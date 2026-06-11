import json
from decimal import Decimal
import os
import random
import string
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
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
from apps.common.models import Currency, SocialMediaLink
from apps.notifications.models import Notification, NotificationSetting
from apps.notifications.services import notify_user, notify_bulk
from apps.orders.models import Order, OrderItem, OrderLog, Coupon
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest
from apps.site.forms import LoginForm, RegisterForm, TicketForm, PaymentMethodForm, CurrencyForm, ModerateUserForm, ProductForm, VariantForm, KYCRequestForm, KYCSettingsForm, ChangePasswordForm, CouponForm
from apps.support.models import ChatRoom, ChatMessage, ChatCannedReply
from apps.wallets.models import LedgerEntry, Wallet, WalletTransaction
from apps.wallets.services import get_or_create_wallet, track_pending_deposit, freeze_funds, credit_wallet, release_funds, finalize_withdrawal, debit_wallet


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
        if request.user.role in [User.Role.ADMIN, User.Role.SUPPORT, User.Role.FINANCE]:
            return redirect("control_dashboard")
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
                phone=phone,
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                is_account_active=True
            )
            # Create wallet
            get_or_create_wallet(user)
            
            # Start OTP verification for Activation
            otp = v3_generate_otp(user, OTPToken.Purpose.REGISTRATION)
            if v3_send_otp_email(user, otp):
                request.session["v3_auth_uid"] = str(user.id)
                request.session["v3_auth_purpose"] = OTPToken.Purpose.REGISTRATION
                return redirect("site_verify_otp")
    
    return render(request, "site/v3/v3_register.html", {"form": form})


def v3_verify_otp_view(request):
    uid = request.session.get("v3_auth_uid")
    purpose = request.session.get("v3_auth_purpose")
    
    if not uid or not purpose:
        return redirect("site_login")
    
    user = get_object_or_404(User, id=uid)
    
    if request.method == "POST":
        code = request.POST.get("otp_code")
        if v3_verify_otp_logic(user, code, purpose):
            if purpose == OTPToken.Purpose.REGISTRATION:
                user.is_email_verified = True
                user.save(update_fields=["is_email_verified", "updated_at"])
            
            login(request, user)
            # Cleanup session
            del request.session["v3_auth_uid"]
            del request.session["v3_auth_purpose"]
            
            if user.role in [User.Role.ADMIN, User.Role.SUPPORT, User.Role.FINANCE]:
                return redirect("control_dashboard")
            return redirect("dashboard")
        else:
            messages.error(request, "رمز التحقق غير صحيح أو منتهي الصلاحية.")
            
    return render(request, "site/v3/v3_otp_verify.html", {"user_email": user.email})


@login_required
def v3_logout_view(request):
    logout(request)
    return redirect("site_login")


# ==========================================
# --- CORE USER VIEWS (V3) ---
# ==========================================

@login_required
def dashboard(request):
    wallet = get_or_create_wallet(request.user)
    
    # Fetch needed data for v3_dashboard.html
    digital_deliveries = Order.objects.filter(
        customer=request.user,
        status=Order.Status.COMPLETED,
        is_delivery_read=False
    ).exclude(fulfillment_data={})
    
    recent_orders = Order.objects.filter(customer=request.user).order_by(\'-created_at\')[:5]
    
    # Get recent deposits
    recent_deposits = DepositRequest.objects.filter(user=request.user).order_by(\'-created_at\')[:5]
    
    # Get KYC request
    kyc_request = KYCRequest.objects.filter(user=request.user).first()
    
    # Get notifications
    notifications = Notification.objects.filter(user=request.user, is_read=False)[:5]

    return render(request, "site/v3/v3_dashboard.html", {
        "wallet": wallet,
        "digital_deliveries": digital_deliveries,
        "orders": recent_orders, # Template uses \'orders\'
        "deposits": recent_deposits, # Template uses \'deposits\'
        "kyc_request": kyc_request,
        "notifications": notifications,
    })

@login_required
def deposits(request):
    methods = PaymentMethod.objects.filter(is_active=True)
    requests = DepositRequest.objects.filter(user=request.user).order_by('-created_at')
    
    if request.method == "POST":
        method_id = request.POST.get("method_id")
        amount = Decimal(request.POST.get("amount", "0"))
        if method_id and amount > 0:
            method = get_object_or_404(PaymentMethod, id=method_id)
            track_pending_deposit(request.user.wallet.id, amount, reference=f"dep_req_{timezone.now().timestamp()}", reason=f"Deposit via {method.name}")
            DepositRequest.objects.create(
                user=request.user,
                payment_method=method,
                amount=amount,
                status=DepositRequest.Status.PENDING
            )
            messages.success(request, "تم تقديم طلب الإيداع بنجاح.")
            return redirect("deposits")

    return render(request, "site/v3/v3_deposits.html", {"methods": methods, "requests": requests})

@login_required
def withdrawals(request):
    methods = PaymentMethod.objects.filter(is_active=True, allow_withdrawal=True)
    requests = WithdrawalRequest.objects.filter(user=request.user).order_by('-created_at')
    
    if request.method == "POST":
        method_id = request.POST.get("method_id")
        amount = Decimal(request.POST.get("amount", "0"))
        address = request.POST.get("address")
        if method_id and amount > 0:
            method = get_object_or_404(PaymentMethod, id=method_id)
            try:
                freeze_funds(request.user.wallet.id, amount, reference=f"with_req_{timezone.now().timestamp()}", reason=f"Withdrawal via {method.name}")
                WithdrawalRequest.objects.create(
                    user=request.user,
                    payment_method=method,
                    amount=amount,
                    withdrawal_address=address,
                    status=WithdrawalRequest.Status.PENDING
                )
                messages.success(request, "تم تقديم طلب السحب بنجاح.")
                return redirect("withdrawals")
            except Exception as e:
                messages.error(request, str(e))

    return render(request, "site/v3/v3_withdrawals.html", {"methods": methods, "requests": requests})

@login_required
def kyc_request_view(request):
    existing = KYCRequest.objects.filter(user=request.user).first()
    if existing and existing.status in [KYCRequest.Status.PENDING, KYCRequest.Status.VERIFIED]:
        return render(request, "site/v3/v3_kyc_status.html", {"kyc": existing})
    
    form = KYCRequestForm(request.POST or None, request.FILES or None, instance=existing)
    if request.method == "POST" and form.is_valid():
        kyc = form.save(commit=False)
        kyc.user = request.user
        kyc.status = KYCRequest.Status.PENDING
        kyc.save()
        
        notify_bulk(
            role=User.Role.ADMIN,
            title="طلب توثيق جديد",
            body=f"قام المستخدم {request.user.email} بتقديم طلب توثيق الهوية.",
            action_url=f"/control/kyc/{kyc.id}/"
        )

        messages.success(request, "تم تقديم الطلب.")
        return redirect("dashboard")
        
    return render(request, "site/v3/v3_kyc_form.html", {"form": form})


# ==========================================
# --- CATALOG & ORDERS (V3) ---
# ==========================================

def index_view(request):
    categories = Category.objects.all().order_by('sort_order')
    return render(request, "site/v3/v3_index.html", {"categories": categories})

def category_detail(request, pk):
    category = get_object_or_404(Category, pk=pk)
    products = Product.objects.filter(category=category, is_active=True).order_by('sort_order')
    return render(request, "site/v3/v3_category.html", {"category": category, "products": products})

def product_detail(request, pk):
    product = get_object_or_404(Product.objects.prefetch_related('variants'), pk=pk, is_active=True)
    variants = product.variants.filter(is_active=True).order_by('sort_order')
    
    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect("site_login")
            
        vid = request.POST.get("variant_id")
        qty = max(int(request.POST.get("quantity", 1)), 1)
        coupon_code = request.POST.get("coupon_code", "").strip()

        # Capture custom metadata from the form
        metadata = {}
        for key, value in request.POST.items():
            if key.startswith("custom_"):
                field_name = key.replace("custom_", "", 1)
                metadata[field_name] = value

        if vid:
            try:
                from apps.orders.services import create_order
                coupon = None
                if coupon_code:
                    from apps.orders.models import Coupon
                    coupon = Coupon.objects.filter(code__iexact=coupon_code, is_active=True).first()
                    if not coupon:
                         messages.error(request, "الكوبون المدخل غير صالح أو منتهي.")
                         return render(request, "site/product_detail.html", {"product": product, "variants": variants})

                create_order(request.user, vid, quantity=qty, metadata=metadata, coupon=coupon)
                messages.success(request, "تم إنشاء الطلب بنجاح.")
                return redirect("dashboard")
            except Exception as e:
                messages.error(request, str(e))
                
    return render(request, "site/product_detail.html", {"product": product, "variants": variants})


# ==========================================
# --- AJAX VIEWS ---
# ==========================================

def ajax_validate_coupon(request):
    code = request.GET.get("code", "").strip()
    variant_id = request.GET.get("variant_id")
    
    if not code or not variant_id:
        return JsonResponse({"valid": False, "error": "بيانات غير مكتملة."})
        
    try:
        from apps.catalog.models import ProductVariant
        variant = ProductVariant.objects.get(id=variant_id)
        coupon = Coupon.objects.filter(code__iexact=code, is_active=True).first()
        
        if not coupon:
            return JsonResponse({"valid": False, "error": "الكوبون غير موجود أو معطل."})
            
        from apps.orders.services import validate_coupon
        subtotal = variant.get_price_for_user(request.user)
        discount = validate_coupon(coupon, request.user, variant, subtotal=subtotal)
        
        return JsonResponse({
            "valid": True,
            "discount_amount": float(discount),
            "new_total": float(subtotal - discount),
            "message": f"تم تطبيق الخصم بنجاح: {discount} USD"
        })
    except ValueError as e:
        return JsonResponse({"valid": False, "error": str(e)})
    except Exception as e:
        return JsonResponse({"valid": False, "error": "حدث خطأ غير متوقع."})


# ==========================================
# --- ADMINISTRATIVE & FINANCE (V3) ---
# ==========================================

def staff_required(view_func):
    return permission_required("accounts.can_view_control")(view_func)

def admin_required(view_func):
    return permission_required("accounts.can_manage_system")(view_func)

def support_required(view_func):
    return permission_required("accounts.can_manage_support")(view_func)

def finance_required(view_func):
    return permission_required("accounts.can_manage_finance")(view_func)

@staff_required
def control_dashboard(request):
    return render(request, "site/control_dashboard.html")

@finance_required
def control_deposits(request):
    requests = DepositRequest.objects.select_related('user', 'payment_method').all().order_by('-created_at')
    return render(request, "site/control_deposits.html", {"requests": requests})

@finance_required
def control_withdrawals(request):
    requests = WithdrawalRequest.objects.select_related('user', 'payment_method').all().order_by('-created_at')
    return render(request, "site/control_withdrawals.html", {"requests": requests})

@support_required
def control_kycs_list(request):
    requests = KYCRequest.objects.select_related('user').all().order_by('-created_at')
    return render(request, "site/control_kycs_list.html", {"requests": requests})

@support_required
def control_kyc_detail(request, pk):
    kyc = get_object_or_404(KYCRequest.objects.select_related('user'), pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        admin_note = request.POST.get("admin_note", "")
        if action == "approve":
            kyc.status = KYCRequest.Status.VERIFIED
            kyc.admin_note = admin_note
            kyc.save()
            kyc.user.is_kyc_verified = True
            kyc.user.save(update_fields=["is_kyc_verified", "updated_at"])
            notify_user(kyc.user, "تم توثيق الحساب", "مبروك! تم قبول طلب توثيق هويتك بنجاح.")
        elif action == "reject":
            kyc.status = KYCRequest.Status.REJECTED
            kyc.admin_note = admin_note
            kyc.save()
            kyc.user.is_kyc_verified = False
            kyc.user.save(update_fields=["is_kyc_verified", "updated_at"])
            notify_user(kyc.user, "تم رفض توثيق الحساب", f"للأسف تم رفض طلب توثيق هويتك. السبب: {admin_note}")
        return redirect("control_kyc_list")
    return render(request, "site/control_kyc_detail.html", {"kyc": kyc})


@support_required
def control_orders_list(request):
    status_filter = request.GET.get('status')
    q = request.GET.get('q', '')
    orders = Order.objects.select_related('customer').prefetch_related('items__variant__product').all().order_by('-created_at')
    if status_filter:
        orders = orders.filter(status=status_filter)
    if q:
        orders = orders.filter(Q(number__icontains=q) | Q(customer__email__icontains=q))
    return render(request, "site/control_orders_list.html", {
        "orders": orders, 
        "query": q, 
        "current_status": status_filter,
        "order_status_choices": Order.Status.choices
    })

@support_required
def control_order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related('customer', 'customer__wallet').prefetch_related('items__variant__product', 'logs'), pk=pk)
    
    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "update_status":
            new_status = request.POST.get("status")
            admin_note = request.POST.get("admin_note", "")
            if new_status and new_status != order.status:
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(pk=pk)
                    old_status = order.status
                    order.status = new_status
                    order.save()
                    OrderLog.objects.create(order=order, status=new_status, note=admin_note, created_by=request.user)
                    
                    # Handle Automatic Refund
                    if new_status in [Order.Status.REFUNDED, Order.Status.CANCELLED]:
                        refund_ref = f"refund:order:{order.id}"
                        if not LedgerEntry.objects.filter(reference=refund_ref).exists():
                            # Convert USD order total back to wallet currency for refund
                            refund_amount = order.total_amount
                            if order.customer.wallet.currency.code != "USD":
                                refund_amount = order.customer.wallet.currency.from_base(order.total_amount)

                            credit_wallet(
                                wallet_id=order.customer.wallet.id,
                                amount=refund_amount,
                                reference=refund_ref,
                                description=f"Refund for order #{order.number}. Reason: {admin_note or 'Order ' + new_status}",
                                created_by=request.user,
                                source="order_refund",
                                reason=f"Order {new_status}"
                            )
                            messages.success(request, f"تم تحديث الحالة وإعادة مبلغ {refund_amount} لمحفظة العميل.")
                        else:
                            messages.info(request, "تم تحديث الحالة (المبلغ مسترد مسبقاً).")
                    else:
                        messages.success(request, "تم تحديث حالة الطلب بنجاح.")
        
        elif action == "update_fulfillment":
            keys = request.POST.getlist("ff_key[]")
            values = request.POST.getlist("ff_value[]")
            new_fulfillment = {k.strip(): v.strip() for k, v in zip(keys, values) if k.strip()}
            order.fulfillment_data = new_fulfillment
            order.save(update_fields=["fulfillment_data"])
            messages.success(request, "تم تحديث بيانات التنفيذ.")

        elif action == "update_price":
            new_total = request.POST.get("total_amount")
            reason = request.POST.get("adjustment_reason", "")
            if new_total:
                try:
                    new_total = Decimal(new_total.replace(',', '.')) # Handle comma decimal separator
                    old_total = order.total_amount
                    
                    if new_total != old_total:
                        with transaction.atomic():
                            if not order.original_total:
                                order.original_total = old_total
                            order.total_amount = new_total
                            order.price_adjustment_reason = reason
                            order.save(update_fields=["total_amount", "original_total", "price_adjustment_reason"])
                            
                            diff = new_total - old_total 
                            wallet = order.customer.wallet
                            adj_ref = f"adj:order:{order.id}:{timezone.now().timestamp()}"
                            
                            if diff > 0:
                                wallet.available_balance -= diff
                                wallet.save(update_fields=["available_balance", "updated_at"])
                                LedgerEntry.objects.create(
                                    wallet=wallet, amount=-diff, entry_type=LedgerEntry.EntryType.DEBIT,
                                    balance_after=wallet.available_balance, reference=adj_ref,
                                    description=f"تعديل سعر الطلب #{order.number} (زيادة). السبب: {reason}",
                                    created_by=request.user
                                )
                                notify_user(order.customer, "تعديل سعر الطلب", f"تم زيادة سعر طلبك #{order.number} بمقدار {diff} USD. السبب: {reason}")
                            else:
                                credit_wallet(
                                    wallet_id=wallet.id, amount=abs(diff), reference=adj_ref,
                                    description=f"تعديل سعر الطلب #{order.number} (تخفيض). السبب: {reason}",
                                    created_by=request.user, source="order_adjustment", reason="Price reduction"
                                )
                                notify_user(order.customer, "تعديل سعر الطلب", f"تم تخفيض سعر طلبك #{order.number} بمقدار {abs(diff)} USD.")

                            OrderLog.objects.create(order=order, status=order.status, note=f"تعديل السعر من {old_total} إلى {new_total}. السبب: {reason}", created_by=request.user)
                            messages.success(request, f"تم تعديل السعر وإجراء التسوية المالية ({diff} USD).")
                except Exception as e:
                    messages.error(request, f"خطأ في تعديل السعر: {str(e)}")
            
        return redirect("control_order_detail", pk=pk)
    
    return render(request, "site/control_order_detail.html", {
        "order": order, 
        "readable_fulfillment": order.fulfillment_data,
        "mapped_metadata": order.formatted_metadata
    })


@finance_required
def control_wallets_list(request):
    q = request.GET.get('q', '')
    wallets = Wallet.objects.select_related('user', 'currency').all().order_by('-updated_at')
    if q:
        wallets = wallets.filter(Q(user__email__icontains=q) | Q(user__first_name__icontains=q))
    return render(request, "site/control_wallets_list.html", {"wallets": wallets, "query": q})


@finance_required
def control_reports(request):
    today = timezone.now().date()
    last_30_days = today - timedelta(days=30)
    
    # Financial Stats
    deposit_fees = DepositRequest.objects.filter(status=DepositRequest.Status.COMPLETED, created_at__date__gte=last_30_days).aggregate(total=Sum('fee_amount'))['total'] or Decimal("0.00")
    withdrawal_fees = WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.COMPLETED, created_at__date__gte=last_30_days).aggregate(total=Sum('fee_amount'))['total'] or Decimal("0.00")
    
    product_stats = OrderItem.objects.filter(order__status__in=[Order.Status.COMPLETED, Order.Status.PROCESSING], created_at__date__gte=last_30_days).aggregate(
        revenue=Sum('total_price'),
        cost=Sum(F('unit_cost') * F('quantity'))
    )
    revenue = product_stats['revenue'] or Decimal("0.00")
    profit = revenue - (product_stats['cost'] or Decimal("0.00")) + deposit_fees + withdrawal_fees
    
    return render(request, "site/control_reports.html", {
        "stats": {
            "total_profit_30": profit,
            "orders_30": Order.objects.filter(created_at__date__gte=last_30_days).count(),
            "new_users_30": User.objects.filter(date_joined__date__gte=last_30_days).count()
        }
    })


@admin_required
def control_coupons_list(request):
    coupons = Coupon.objects.all().order_by("-created_at")
    return render(request, "site/control_coupons_list.html", {"coupons": coupons})

@admin_required
def control_coupon_create(request):
    form = CouponForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إنشاء الكوبون بنجاح.")
        return redirect("control_coupons_list")
    return render(request, "site/control_coupon_form.html", {"form": form, "title": "إنشاء كوبون جديد"})

@admin_required
def control_coupon_edit(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    form = CouponForm(request.POST or None, instance=coupon)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم تحديث الكوبون بنجاح.")
        return redirect("control_coupons_list")
    return render(request, "site/control_coupon_form.html", {"form": form, "title": "تعديل الكوبون", "coupon": coupon})

@admin_required
def control_coupon_delete(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    if request.method == "POST":
        coupon.delete()
        messages.success(request, "تم حذف الكوبون بنجاح.")
        return redirect("control_coupons_list")
    return render(request, "site/control_confirm_delete.html", {"object": coupon, "type": "كوبون"})


@admin_required
def control_social_media(request):
    from apps.site.forms import SocialMediaLinkForm
    links = SocialMediaLink.objects.all()
    form = SocialMediaLinkForm()
    if request.method == "POST":
        pk = request.POST.get("pk")
        instance = get_object_or_404(SocialMediaLink, pk=pk) if pk else None
        form = SocialMediaLinkForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "تم حفظ الرابط بنجاح.")
            return redirect("control_social_media")
    return render(request, "site/control_social_media.html", {"links": links, "form": form})

@admin_required
def control_social_media_delete(request, pk):
    get_object_or_404(SocialMediaLink, pk=pk).delete()
    messages.success(request, "تم حذف الرابط.")
    return redirect("control_social_media")

@support_required
def control_products_list(request):
    products = Product.objects.select_related('category').prefetch_related('variants').all().order_by('sort_order', 'name')
    return render(request, "site/control_products_list.html", {"products": products})

@admin_required
def currencies_list(request):
    currencies = Currency.objects.all().order_by('display_order', 'code')
    if request.method == "POST":
        for c in currencies:
            buy = request.POST.get(f"buy_rate_{c.id}")
            sell = request.POST.get(f"sell_rate_{c.id}")
            if buy and sell:
                c.buy_rate, c.sell_rate = Decimal(buy), Decimal(sell)
                c.save()
        messages.success(request, "تم تحديث أسعار الصرف.")
        return redirect("currencies_list")
    return render(request, "site/currencies_list.html", {"currencies": currencies})

@admin_required
def currency_create(request):
    form = CurrencyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("currencies_list")
    return render(request, "site/currency_form.html", {"form": form, "title": "إضافة عملة"})

@admin_required
def currency_edit(request, pk):
    currency = get_object_or_404(Currency, pk=pk)
    form = CurrencyForm(request.POST or None, instance=currency)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("currencies_list")
    return render(request, "site/currency_form.html", {"form": form, "title": "تعديل عملة"})

@staff_member_required
def set_currency(request):
    code = request.POST.get("currency")
    if code:
        request.session["currency_code"] = code
    return redirect(request.META.get("HTTP_REFERER", "/"))

@staff_member_required
def service_worker(request):
    return HttpResponse(open("apps/site/static/site/js/sw.js").read(), content_type="application/javascript")

def terms_of_service(request): return render(request, "site/terms_of_service.html")
def refund_policy(request): return render(request, "site/refund_policy.html")
def contact_page(request): return render(request, "site/contact.html")


@login_required
def wallet_page(request):
    """
    Displays the user's wallet dashboard and recent ledger entries.
    """
    request.user.reset_daily_limits_if_needed()
    wallet = Wallet.objects.filter(user=request.user).select_related("currency").first() or get_or_create_wallet(request.user)
    return render(request, "site/wallet.html", {"wallet": wallet, "ledger_entries": wallet.ledger_entries.all()[:20]})




@login_required
def orders_list(request):
    orders = request.user.orders.all().prefetch_related('items__variant__product')
    return render(request, "site/orders_list.html", {"orders": orders})



@login_required
def order_detail(request, pk):
    order = get_object_or_404(request.user.orders.prefetch_related('items__variant__product', 'logs'), pk=pk)
    return render(request, "site/order_detail.html", {"order": order})




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
        messages.success(request, "╪ز┘à ╪ص┘╪╕ ╪ح╪╣╪»╪د╪»╪د╪ز ╪د┘╪ح╪┤╪╣╪د╪▒╪د╪ز ╪ذ┘╪ش╪د╪ص.")
        return redirect("notification_settings")
        
    return render(request, "site/notification_settings.html", {"settings": settings_obj})


@login_required
def v3_change_password_view(request):
    form = ChangePasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = request.user
        current_password = form.cleaned_data["current_password"]
        new_password = form.cleaned_data["new_password"]
        
        if user.check_password(current_password):
            with transaction.atomic():
                user.set_password(new_password)
                user.save()
                
                # Update session to prevent logout of current session
                update_session_auth_hash(request, user)
                
                # Invalidate other sessions
                from django.contrib.sessions.models import Session
                for session in Session.objects.all():
                    decoded = session.get_decoded()
                    if decoded.get('_auth_user_id') == str(user.id):
                        if session.session_key != request.session.session_key:
                            session.delete()
                
                ActivityLog.objects.create(user=user, action="Password Change", description="User changed password and invalidated other sessions")
                messages.success(request, "تم تغيير كلمة المرور بنجاح وتم تسجيل الخروج من الأجهزة الأخرى.")
                return redirect("dashboard")
        else:
            messages.error(request, "كلمة المرور الحالية غير صحيحة.")
            
    return render(request, "site/v3/v3_change_password.html", {"form": form})


from apps.common.decorators import finance_required, support_required, kyc_required, admin_required
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest



def v3_forgot_password_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").lower().strip()
        user = User.objects.filter(email=email).first()
        
        if user:
            otp = v3_generate_otp(user, OTPToken.Purpose.PASSWORD_RESET)
            if v3_send_otp_email(user, otp):
                request.session["v3_auth_uid"] = str(user.id)
                request.session["v3_auth_purpose"] = OTPToken.Purpose.PASSWORD_RESET
                messages.success(request, "╪ز┘à ╪ح╪▒╪│╪د┘ ╪▒┘à╪▓ ╪د┘╪ز╪ص┘é┘é ┘╪ح╪╣╪د╪»╪ر ╪ز╪╣┘è┘è┘ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒.")
                return redirect("site_verify_otp")
            else:
                messages.error(request, "┘╪┤┘ ╪ح╪▒╪│╪د┘ ╪د┘╪▒┘à╪▓. ┘è╪▒╪ش┘ë ╪د┘┘à╪ص╪د┘ê┘╪ر ┘╪د╪ص┘é╪د┘ï.")
        else:
            messages.error(request, "╪╣╪░╪▒╪د┘ï╪î ┘ç╪░╪د ╪د┘╪ذ╪▒┘è╪» ╪د┘╪ح┘┘â╪ز╪▒┘ê┘┘è ╪║┘è╪▒ ┘à╪│╪ش┘ ┘╪»┘è┘╪د.")
            
    return render(request, "site/v3/v3_forgot_password.html")




def v3_reset_password_view(request):
    uid = request.session.get("v3_auth_uid")
    is_verified = request.session.get("v3_recovery_verified") == True
    
    if not uid or not is_verified:
        messages.error(request, "┘è╪▒╪ش┘ë ╪د┘╪ز╪ص┘é┘é ┘à┘ ┘ç┘ê┘è╪ز┘â ╪ث┘ê┘╪د┘ï.")
        return redirect("site_forgot_password")
        
    user = get_object_or_404(User, id=uid)
    
    if request.method == "POST":
        p1 = request.POST.get("password")
        p2 = request.POST.get("confirm_password")
        
        if not p1 or len(p1) < 10:
            messages.error(request, "┘è╪ش╪ذ ╪ث┘ ╪ز┘â┘ê┘ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒ 10 ╪«╪د┘╪د╪ز ╪╣┘┘ë ╪د┘╪ث┘é┘.")
        elif p1 != p2:
            messages.error(request, "┘â┘┘à╪د╪ز ╪د┘┘à╪▒┘ê╪▒ ╪║┘è╪▒ ┘à╪ز╪╖╪د╪ذ┘é╪ر.")
        else:
            user.set_password(p1)
            user.save()
            
            # Clean up all auth sessions
            request.session.flush()
            
            ActivityLog.objects.create(user=user, action="Password Reset Success", description="User reset password via V3 OTP flow")
            messages.success(request, "╪ز┘à ╪ز╪║┘è┘è╪▒ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒ ╪ذ┘╪ش╪د╪ص. ┘è┘à┘â┘┘â ╪د┘╪ت┘ ╪ز╪│╪ش┘è┘ ╪د┘╪»╪«┘ê┘.")
            return redirect("site_login")
            
    return render(request, "site/v3/v3_reset_password.html", {"user_email": user.email})




def resend_verification(request): return redirect("dashboard")


def email_verify(request, uidb64, token): return redirect("site_login")


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
                messages.success(request, f"┘┘â ╪د┘╪ص╪╕╪▒ ╪╣┘ {code}.")
            return redirect("control_kyc_settings")
        elif form.is_valid():
            form.save()
            messages.success(request, "╪ز┘à ╪د┘╪ص┘╪╕.")
            return redirect("control_kyc_settings")
    return render(request, "site/control_kyc_settings.html", {"form": form, "settings": settings_obj, "stats_verified_count": User.objects.filter(is_kyc_verified=True).count()})



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


@finance_required
def control_deposit_detail(request, pk):
    deposit = get_object_or_404(DepositRequest.objects.select_related('user', 'currency', 'payment_method'), pk=pk)
    return render(request, "site/control_deposit_detail.html", {
        "deposit": deposit,
    })



@finance_required
def control_withdrawal_detail(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest.objects.select_related('user', 'user__wallet'), pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=pk)
            action = request.POST.get("action")
            admin_note = request.POST.get("admin_note", "")
            
            from apps.wallets.services import release_funds, finalize_withdrawal
            
            if action == "approve":
                withdrawal.status = WithdrawalRequest.Status.APPROVED
                withdrawal.admin_note = admin_note
                messages.success(request, "╪ز┘à╪ز ╪د┘┘à┘ê╪د┘┘é╪ر ╪د┘┘à╪ذ╪»╪خ┘è╪ر ╪╣┘┘ë ╪د┘╪╖┘╪ذ.")
            elif action == "process":
                withdrawal.status = WithdrawalRequest.Status.PROCESSING
                withdrawal.admin_note = admin_note
                messages.info(request, "╪ذ╪»╪ث╪ز ┘à╪╣╪د┘╪ش╪ر ╪د┘╪╖┘╪ذ.")
            elif action == "complete":
                if withdrawal.status == WithdrawalRequest.Status.COMPLETED:
                     messages.error(request, "┘ç╪░╪د ╪د┘╪╖┘╪ذ ┘à┘â╪ز┘à┘ ┘à╪│╪ذ┘é╪د┘ï.")
                     return redirect("control_withdrawals")

                finalize_withdrawal(
                    withdrawal.user.wallet.id,
                    withdrawal.wallet_amount,
                    reference=f"with_complete:{withdrawal.id}",
                    description=f"Withdrawal completed. {admin_note}",
                    created_by=request.user
                )
                withdrawal.status = WithdrawalRequest.Status.COMPLETED
                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.success(request, "╪ز┘à ╪ح╪ز┘à╪د┘à ╪╣┘à┘┘è╪ر ╪د┘╪│╪ص╪ذ ╪ذ┘╪ش╪د╪ص.")
                return redirect("control_withdrawals")
            elif action == "reject":
                if withdrawal.status in [WithdrawalRequest.Status.COMPLETED, WithdrawalRequest.Status.REJECTED, WithdrawalRequest.Status.CANCELLED]:
                     messages.error(request, "┘╪د ┘è┘à┘â┘ ╪▒┘╪╢ ╪╖┘╪ذ ┘à┘╪ز┘ç┘è.")
                     return redirect("control_withdrawals")

                release_funds(
                    withdrawal.user.wallet.id,
                    withdrawal.wallet_amount,
                    reference=f"with_rej:{withdrawal.id}",
                    description=f"Withdrawal rejected: {admin_note}",
                    created_by=request.user
                )
                withdrawal.status = WithdrawalRequest.Status.REJECTED

                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.error(request, "╪ز┘à ╪▒┘╪╢ ╪╖┘╪ذ ╪د┘╪│╪ص╪ذ ┘ê╪ح╪╣╪د╪»╪ر ╪د┘╪▒╪╡┘è╪» ┘┘┘à╪│╪ز╪«╪»┘à.")
                return redirect("control_withdrawals")
            elif action == "cancel_completed":
                if withdrawal.status != WithdrawalRequest.Status.COMPLETED:
                    messages.error(request, "┘╪د ┘è┘à┘â┘ ╪ح┘╪║╪د╪ة ┘ç╪░╪د ╪د┘╪╖┘╪ذ ┘╪ث┘┘ç ┘┘è╪│ ┘à┘â╪ز┘à┘.")
                    return redirect("control_withdrawal_detail", pk=pk)
                
                from apps.wallets.services import credit_wallet
                credit_wallet(
                    wallet_id=withdrawal.user.wallet.id,
                    amount=withdrawal.wallet_amount,
                    reference=f"with_rev:{withdrawal.id}",
                    description=f"Withdrawal reversed/cancelled: {admin_note}",
                    created_by=request.user,
                    reason="Admin reversal of completed withdrawal"
                )
                withdrawal.status = WithdrawalRequest.Status.CANCELLED
                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.warning(request, "╪ز┘à ╪ح┘╪║╪د╪ة ╪د┘╪│╪ص╪ذ ╪د┘┘à┘â╪ز┘à┘ ┘ê╪ح╪╣╪د╪»╪ر ╪د┘┘à╪ذ┘╪║ ┘┘┘à╪ص┘╪╕╪ر ╪ذ┘╪ش╪د╪ص.")
                return redirect("control_withdrawals")
            
            withdrawal.save()
            return redirect("control_withdrawal_detail", pk=pk)

    return render(request, "site/control_withdrawal_detail.html", {"withdrawal": withdrawal})



@admin_required
def control_users_list(request): return render(request, "site/control_users_list.html", {"users": User.objects.select_related("wallet").order_by("-date_joined"), "tiers": User.Tier.choices, "roles": User.Role.choices})


@support_required
@transaction.atomic
def control_product_create(request):
    from apps.site.forms import ProductForm
    from apps.catalog.models import Product, ProductVariant
    import json
    
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        
        # Handle variants
        variants_json = request.POST.get("variants_json")
        if variants_json:
            variants_data = json.loads(variants_json)
            for v_data in variants_data:
                ProductVariant.objects.create(
                    product=product,
                    name=v_data.get('name'),
                    sku=v_data.get('sku'),
                    price=Decimal(str(v_data.get('price', '0'))),
                    wholesale_price=Decimal(str(v_data.get('wholesale_price', '0'))),
                    vip_price=Decimal(str(v_data.get('vip_price', '0'))),
                    cost=Decimal(str(v_data.get('cost', '0'))),
                    sort_order=int(v_data.get('sort_order', 0)),
                    is_active=v_data.get('is_active', True)
                )
        
        messages.success(request, "╪ز┘à ╪ح┘╪┤╪د╪ة ╪د┘┘à┘╪ز╪ش ╪ذ┘╪ش╪د╪ص.")
        return redirect("control_products_list")
        
    return render(request, "site/control_product_builder.html", {
        "form": form, "title": "╪ح╪╢╪د┘╪ر ┘à┘╪ز╪ش ╪ش╪»┘è╪»", "variants_json_data": []
    })



@support_required
def control_category_create_ajax(request):
    from apps.catalog.models import Category
    name = request.POST.get('name')
    if name:
        cat = Category.objects.create(name=name)
        return JsonResponse({"id": str(cat.id), "name": cat.name})
    return JsonResponse({"error": "Name required"}, status=400)



@admin_required
def control_support_settings(request):
    settings_obj, created = SupportSettings.objects.get_or_create(id=1)
    form = SupportSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ إعدادات الدعم بنجاح.")
        return redirect("control_support_settings")
    return render(request, "site/control_support_settings.html", {"form": form})



@support_required
def control_quick_replies(request):
    replies = ChatCannedReply.objects.all().order_by("-created_at")
    return render(request, "site/control_quick_replies.html", {"replies": replies})



@support_required
def control_quick_reply_create(request):
    form = ChatCannedReplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إضافة الرد الجاهز بنجاح.")
        return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})



@support_required
def control_quick_reply_edit(request, pk):
    reply = get_object_or_404(ChatCannedReply, pk=pk)
    form = ChatCannedReplyForm(request.POST or None, instance=reply)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم تعديل الرد الجاهز بنجاح.")
        return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})



@support_required
def control_quick_reply_delete(request, pk):
    reply = get_object_or_404(ChatCannedReply, pk=pk)
    reply.delete()
    messages.success(request, "تم حذف الرد الجاهز بنجاح.")
    return redirect("control_quick_replies")



def privacy_policy(request): return render(request, "site/privacy_policy.html")


@login_required
def wallet_page(request):
    """
    Displays the user's wallet dashboard and recent ledger entries.
    """
    request.user.reset_daily_limits_if_needed()
    wallet = Wallet.objects.filter(user=request.user).select_related("currency").first() or get_or_create_wallet(request.user)
    return render(request, "site/wallet.html", {"wallet": wallet, "ledger_entries": wallet.ledger_entries.all()[:20]})




@login_required
def orders_list(request):
    orders = request.user.orders.all().prefetch_related('items__variant__product')
    return render(request, "site/orders_list.html", {"orders": orders})



@login_required
def order_detail(request, pk):
    order = get_object_or_404(request.user.orders.prefetch_related('items__variant__product', 'logs'), pk=pk)
    return render(request, "site/order_detail.html", {"order": order})




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
        messages.success(request, "╪ز┘à ╪ص┘╪╕ ╪ح╪╣╪»╪د╪»╪د╪ز ╪د┘╪ح╪┤╪╣╪د╪▒╪د╪ز ╪ذ┘╪ش╪د╪ص.")
        return redirect("notification_settings")
        
    return render(request, "site/notification_settings.html", {"settings": settings_obj})


@login_required
def v3_change_password_view(request):
    form = ChangePasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = request.user
        current_password = form.cleaned_data["current_password"]
        new_password = form.cleaned_data["new_password"]
        
        if user.check_password(current_password):
            with transaction.atomic():
                user.set_password(new_password)
                user.save()
                
                # Update session to prevent logout of current session
                update_session_auth_hash(request, user)
                
                # Invalidate other sessions
                from django.contrib.sessions.models import Session
                for session in Session.objects.all():
                    decoded = session.get_decoded()
                    if decoded.get('_auth_user_id') == str(user.id):
                        if session.session_key != request.session.session_key:
                            session.delete()
                
                ActivityLog.objects.create(user=user, action="Password Change", description="User changed password and invalidated other sessions")
                messages.success(request, "تم تغيير كلمة المرور بنجاح وتم تسجيل الخروج من الأجهزة الأخرى.")
                return redirect("dashboard")
        else:
            messages.error(request, "كلمة المرور الحالية غير صحيحة.")
            
    return render(request, "site/v3/v3_change_password.html", {"form": form})


from apps.common.decorators import finance_required, support_required, kyc_required, admin_required
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest



def v3_forgot_password_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").lower().strip()
        user = User.objects.filter(email=email).first()
        
        if user:
            otp = v3_generate_otp(user, OTPToken.Purpose.PASSWORD_RESET)
            if v3_send_otp_email(user, otp):
                request.session["v3_auth_uid"] = str(user.id)
                request.session["v3_auth_purpose"] = OTPToken.Purpose.PASSWORD_RESET
                messages.success(request, "╪ز┘à ╪ح╪▒╪│╪د┘ ╪▒┘à╪▓ ╪د┘╪ز╪ص┘é┘é ┘╪ح╪╣╪د╪»╪ر ╪ز╪╣┘è┘è┘ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒.")
                return redirect("site_verify_otp")
            else:
                messages.error(request, "┘╪┤┘ ╪ح╪▒╪│╪د┘ ╪د┘╪▒┘à╪▓. ┘è╪▒╪ش┘ë ╪د┘┘à╪ص╪د┘ê┘╪ر ┘╪د╪ص┘é╪د┘ï.")
        else:
            messages.error(request, "╪╣╪░╪▒╪د┘ï╪î ┘ç╪░╪د ╪د┘╪ذ╪▒┘è╪» ╪د┘╪ح┘┘â╪ز╪▒┘ê┘┘è ╪║┘è╪▒ ┘à╪│╪ش┘ ┘╪»┘è┘╪د.")
            
    return render(request, "site/v3/v3_forgot_password.html")




def v3_reset_password_view(request):
    uid = request.session.get("v3_auth_uid")
    is_verified = request.session.get("v3_recovery_verified") == True
    
    if not uid or not is_verified:
        messages.error(request, "┘è╪▒╪ش┘ë ╪د┘╪ز╪ص┘é┘é ┘à┘ ┘ç┘ê┘è╪ز┘â ╪ث┘ê┘╪د┘ï.")
        return redirect("site_forgot_password")
        
    user = get_object_or_404(User, id=uid)
    
    if request.method == "POST":
        p1 = request.POST.get("password")
        p2 = request.POST.get("confirm_password")
        
        if not p1 or len(p1) < 10:
            messages.error(request, "┘è╪ش╪ذ ╪ث┘ ╪ز┘â┘ê┘ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒ 10 ╪«╪د┘╪د╪ز ╪╣┘┘ë ╪د┘╪ث┘é┘.")
        elif p1 != p2:
            messages.error(request, "┘â┘┘à╪د╪ز ╪د┘┘à╪▒┘ê╪▒ ╪║┘è╪▒ ┘à╪ز╪╖╪د╪ذ┘é╪ر.")
        else:
            user.set_password(p1)
            user.save()
            
            # Clean up all auth sessions
            request.session.flush()
            
            ActivityLog.objects.create(user=user, action="Password Reset Success", description="User reset password via V3 OTP flow")
            messages.success(request, "╪ز┘à ╪ز╪║┘è┘è╪▒ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒ ╪ذ┘╪ش╪د╪ص. ┘è┘à┘â┘┘â ╪د┘╪ت┘ ╪ز╪│╪ش┘è┘ ╪د┘╪»╪«┘ê┘.")
            return redirect("site_login")
            
    return render(request, "site/v3/v3_reset_password.html", {"user_email": user.email})




def resend_verification(request): return redirect("dashboard")


def email_verify(request, uidb64, token): return redirect("site_login")


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
                messages.success(request, f"┘┘â ╪د┘╪ص╪╕╪▒ ╪╣┘ {code}.")
            return redirect("control_kyc_settings")
        elif form.is_valid():
            form.save()
            messages.success(request, "╪ز┘à ╪د┘╪ص┘╪╕.")
            return redirect("control_kyc_settings")
    return render(request, "site/control_kyc_settings.html", {"form": form, "settings": settings_obj, "stats_verified_count": User.objects.filter(is_kyc_verified=True).count()})



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


@finance_required
def control_deposit_detail(request, pk):
    deposit = get_object_or_404(DepositRequest.objects.select_related('user', 'currency', 'payment_method'), pk=pk)
    return render(request, "site/control_deposit_detail.html", {
        "deposit": deposit,
    })



@finance_required
def control_withdrawal_detail(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest.objects.select_related('user', 'user__wallet'), pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=pk)
            action = request.POST.get("action")
            admin_note = request.POST.get("admin_note", "")
            
            from apps.wallets.services import release_funds, finalize_withdrawal
            
            if action == "approve":
                withdrawal.status = WithdrawalRequest.Status.APPROVED
                withdrawal.admin_note = admin_note
                messages.success(request, "╪ز┘à╪ز ╪د┘┘à┘ê╪د┘┘é╪ر ╪د┘┘à╪ذ╪»╪خ┘è╪ر ╪╣┘┘ë ╪د┘╪╖┘╪ذ.")
            elif action == "process":
                withdrawal.status = WithdrawalRequest.Status.PROCESSING
                withdrawal.admin_note = admin_note
                messages.info(request, "╪ذ╪»╪ث╪ز ┘à╪╣╪د┘╪ش╪ر ╪د┘╪╖┘╪ذ.")
            elif action == "complete":
                if withdrawal.status == WithdrawalRequest.Status.COMPLETED:
                     messages.error(request, "┘ç╪░╪د ╪د┘╪╖┘╪ذ ┘à┘â╪ز┘à┘ ┘à╪│╪ذ┘é╪د┘ï.")
                     return redirect("control_withdrawals")

                finalize_withdrawal(
                    withdrawal.user.wallet.id,
                    withdrawal.wallet_amount,
                    reference=f"with_complete:{withdrawal.id}",
                    description=f"Withdrawal completed. {admin_note}",
                    created_by=request.user
                )
                withdrawal.status = WithdrawalRequest.Status.COMPLETED
                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.success(request, "╪ز┘à ╪ح╪ز┘à╪د┘à ╪╣┘à┘┘è╪ر ╪د┘╪│╪ص╪ذ ╪ذ┘╪ش╪د╪ص.")
                return redirect("control_withdrawals")
            elif action == "reject":
                if withdrawal.status in [WithdrawalRequest.Status.COMPLETED, WithdrawalRequest.Status.REJECTED, WithdrawalRequest.Status.CANCELLED]:
                     messages.error(request, "┘╪د ┘è┘à┘â┘ ╪▒┘╪╢ ╪╖┘╪ذ ┘à┘╪ز┘ç┘è.")
                     return redirect("control_withdrawals")

                release_funds(
                    withdrawal.user.wallet.id,
                    withdrawal.wallet_amount,
                    reference=f"with_rej:{withdrawal.id}",
                    description=f"Withdrawal rejected: {admin_note}",
                    created_by=request.user
                )
                withdrawal.status = WithdrawalRequest.Status.REJECTED

                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.error(request, "╪ز┘à ╪▒┘╪╢ ╪╖┘╪ذ ╪د┘╪│╪ص╪ذ ┘ê╪ح╪╣╪د╪»╪ر ╪د┘╪▒╪╡┘è╪» ┘┘┘à╪│╪ز╪«╪»┘à.")
                return redirect("control_withdrawals")
            elif action == "cancel_completed":
                if withdrawal.status != WithdrawalRequest.Status.COMPLETED:
                    messages.error(request, "┘╪د ┘è┘à┘â┘ ╪ح┘╪║╪د╪ة ┘ç╪░╪د ╪د┘╪╖┘╪ذ ┘╪ث┘┘ç ┘┘è╪│ ┘à┘â╪ز┘à┘.")
                    return redirect("control_withdrawal_detail", pk=pk)
                
                from apps.wallets.services import credit_wallet
                credit_wallet(
                    wallet_id=withdrawal.user.wallet.id,
                    amount=withdrawal.wallet_amount,
                    reference=f"with_rev:{withdrawal.id}",
                    description=f"Withdrawal reversed/cancelled: {admin_note}",
                    created_by=request.user,
                    reason="Admin reversal of completed withdrawal"
                )
                withdrawal.status = WithdrawalRequest.Status.CANCELLED
                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.warning(request, "╪ز┘à ╪ح┘╪║╪د╪ة ╪د┘╪│╪ص╪ذ ╪د┘┘à┘â╪ز┘à┘ ┘ê╪ح╪╣╪د╪»╪ر ╪د┘┘à╪ذ┘╪║ ┘┘┘à╪ص┘╪╕╪ر ╪ذ┘╪ش╪د╪ص.")
                return redirect("control_withdrawals")
            
            withdrawal.save()
            return redirect("control_withdrawal_detail", pk=pk)

    return render(request, "site/control_withdrawal_detail.html", {"withdrawal": withdrawal})



@admin_required
def control_users_list(request): return render(request, "site/control_users_list.html", {"users": User.objects.select_related("wallet").order_by("-date_joined"), "tiers": User.Tier.choices, "roles": User.Role.choices})


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
        messages.success(request, "╪ز┘à ╪د┘╪ز╪ص╪»┘è╪س.")
        return redirect("control_users_list")
    return render(request, "site/control_user_moderate.html", {"form": form, "user_to_moderate": user})



@support_required
@transaction.atomic
def control_product_create(request):
    from apps.site.forms import ProductForm
    from apps.catalog.models import Product, ProductVariant
    import json
    
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        
        # Handle variants
        variants_json = request.POST.get("variants_json")
        if variants_json:
            variants_data = json.loads(variants_json)
            for v_data in variants_data:
                ProductVariant.objects.create(
                    product=product,
                    name=v_data.get('name'),
                    sku=v_data.get('sku'),
                    price=Decimal(str(v_data.get('price', '0'))),
                    wholesale_price=Decimal(str(v_data.get('wholesale_price', '0'))),
                    vip_price=Decimal(str(v_data.get('vip_price', '0'))),
                    cost=Decimal(str(v_data.get('cost', '0'))),
                    sort_order=int(v_data.get('sort_order', 0)),
                    is_active=v_data.get('is_active', True)
                )
        
        messages.success(request, "╪ز┘à ╪ح┘╪┤╪د╪ة ╪د┘┘à┘╪ز╪ش ╪ذ┘╪ش╪د╪ص.")
        return redirect("control_products_list")
        
    return render(request, "site/control_product_builder.html", {
        "form": form, "title": "╪ح╪╢╪د┘╪ر ┘à┘╪ز╪ش ╪ش╪»┘è╪»", "variants_json_data": []
    })



@support_required
def control_category_create_ajax(request):
    from apps.catalog.models import Category
    name = request.POST.get('name')
    if name:
        cat = Category.objects.create(name=name)
        return JsonResponse({"id": str(cat.id), "name": cat.name})
    return JsonResponse({"error": "Name required"}, status=400)



@admin_required
def control_support_settings(request):
    settings_obj, created = SupportSettings.objects.get_or_create(id=1)
    form = SupportSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ إعدادات الدعم بنجاح.")
        return redirect("control_support_settings")
    return render(request, "site/control_support_settings.html", {"form": form})



@support_required
def control_quick_replies(request):
    replies = ChatCannedReply.objects.all().order_by("-created_at")
    return render(request, "site/control_quick_replies.html", {"replies": replies})



@support_required
def control_quick_reply_create(request):
    form = ChatCannedReplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إضافة الرد الجاهز بنجاح.")
        return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})



@support_required
def control_quick_reply_edit(request, pk):
    reply = get_object_or_404(ChatCannedReply, pk=pk)
    form = ChatCannedReplyForm(request.POST or None, instance=reply)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم تعديل الرد الجاهز بنجاح.")
        return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})



@support_required
def control_quick_reply_delete(request, pk):
    reply = get_object_or_404(ChatCannedReply, pk=pk)
    reply.delete()
    messages.success(request, "تم حذف الرد الجاهز بنجاح.")
    return redirect("control_quick_replies")



def privacy_policy(request): return render(request, "site/privacy_policy.html")


@login_required
def wallet_page(request):
    """
    Displays the user's wallet dashboard and recent ledger entries.
    """
    request.user.reset_daily_limits_if_needed()
    wallet = Wallet.objects.filter(user=request.user).select_related("currency").first() or get_or_create_wallet(request.user)
    return render(request, "site/wallet.html", {"wallet": wallet, "ledger_entries": wallet.ledger_entries.all()[:20]})




@login_required
def orders_list(request):
    orders = request.user.orders.all().prefetch_related('items__variant__product')
    return render(request, "site/orders_list.html", {"orders": orders})



@login_required
def order_detail(request, pk):
    order = get_object_or_404(request.user.orders.prefetch_related('items__variant__product', 'logs'), pk=pk)
    return render(request, "site/order_detail.html", {"order": order})




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
        messages.success(request, "╪ز┘à ╪ص┘╪╕ ╪ح╪╣╪»╪د╪»╪د╪ز ╪د┘╪ح╪┤╪╣╪د╪▒╪د╪ز ╪ذ┘╪ش╪د╪ص.")
        return redirect("notification_settings")
        
    return render(request, "site/notification_settings.html", {"settings": settings_obj})


@login_required
def v3_change_password_view(request):
    form = ChangePasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = request.user
        current_password = form.cleaned_data["current_password"]
        new_password = form.cleaned_data["new_password"]
        
        if user.check_password(current_password):
            with transaction.atomic():
                user.set_password(new_password)
                user.save()
                
                # Update session to prevent logout of current session
                update_session_auth_hash(request, user)
                
                # Invalidate other sessions
                from django.contrib.sessions.models import Session
                for session in Session.objects.all():
                    decoded = session.get_decoded()
                    if decoded.get('_auth_user_id') == str(user.id):
                        if session.session_key != request.session.session_key:
                            session.delete()
                
                ActivityLog.objects.create(user=user, action="Password Change", description="User changed password and invalidated other sessions")
                messages.success(request, "تم تغيير كلمة المرور بنجاح وتم تسجيل الخروج من الأجهزة الأخرى.")
                return redirect("dashboard")
        else:
            messages.error(request, "كلمة المرور الحالية غير صحيحة.")
            
    return render(request, "site/v3/v3_change_password.html", {"form": form})


from apps.common.decorators import finance_required, support_required, kyc_required, admin_required
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest



def v3_forgot_password_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").lower().strip()
        user = User.objects.filter(email=email).first()
        
        if user:
            otp = v3_generate_otp(user, OTPToken.Purpose.PASSWORD_RESET)
            if v3_send_otp_email(user, otp):
                request.session["v3_auth_uid"] = str(user.id)
                request.session["v3_auth_purpose"] = OTPToken.Purpose.PASSWORD_RESET
                messages.success(request, "╪ز┘à ╪ح╪▒╪│╪د┘ ╪▒┘à╪▓ ╪د┘╪ز╪ص┘é┘é ┘╪ح╪╣╪د╪»╪ر ╪ز╪╣┘è┘è┘ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒.")
                return redirect("site_verify_otp")
            else:
                messages.error(request, "┘╪┤┘ ╪ح╪▒╪│╪د┘ ╪د┘╪▒┘à╪▓. ┘è╪▒╪ش┘ë ╪د┘┘à╪ص╪د┘ê┘╪ر ┘╪د╪ص┘é╪د┘ï.")
        else:
            messages.error(request, "╪╣╪░╪▒╪د┘ï╪î ┘ç╪░╪د ╪د┘╪ذ╪▒┘è╪» ╪د┘╪ح┘┘â╪ز╪▒┘ê┘┘è ╪║┘è╪▒ ┘à╪│╪ش┘ ┘╪»┘è┘╪د.")
            
    return render(request, "site/v3/v3_forgot_password.html")




def v3_reset_password_view(request):
    uid = request.session.get("v3_auth_uid")
    is_verified = request.session.get("v3_recovery_verified") == True
    
    if not uid or not is_verified:
        messages.error(request, "┘è╪▒╪ش┘ë ╪د┘╪ز╪ص┘é┘é ┘à┘ ┘ç┘ê┘è╪ز┘â ╪ث┘ê┘╪د┘ï.")
        return redirect("site_forgot_password")
        
    user = get_object_or_404(User, id=uid)
    
    if request.method == "POST":
        p1 = request.POST.get("password")
        p2 = request.POST.get("confirm_password")
        
        if not p1 or len(p1) < 10:
            messages.error(request, "┘è╪ش╪ذ ╪ث┘ ╪ز┘â┘ê┘ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒ 10 ╪«╪د┘╪د╪ز ╪╣┘┘ë ╪د┘╪ث┘é┘.")
        elif p1 != p2:
            messages.error(request, "┘â┘┘à╪د╪ز ╪د┘┘à╪▒┘ê╪▒ ╪║┘è╪▒ ┘à╪ز╪╖╪د╪ذ┘é╪ر.")
        else:
            user.set_password(p1)
            user.save()
            
            # Clean up all auth sessions
            request.session.flush()
            
            ActivityLog.objects.create(user=user, action="Password Reset Success", description="User reset password via V3 OTP flow")
            messages.success(request, "╪ز┘à ╪ز╪║┘è┘è╪▒ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒ ╪ذ┘╪ش╪د╪ص. ┘è┘à┘â┘┘â ╪د┘╪ت┘ ╪ز╪│╪ش┘è┘ ╪د┘╪»╪«┘ê┘.")
            return redirect("site_login")
            
    return render(request, "site/v3/v3_reset_password.html", {"user_email": user.email})




def resend_verification(request): return redirect("dashboard")


def email_verify(request, uidb64, token): return redirect("site_login")


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
                messages.success(request, f"┘┘â ╪د┘╪ص╪╕╪▒ ╪╣┘ {code}.")
            return redirect("control_kyc_settings")
        elif form.is_valid():
            form.save()
            messages.success(request, "╪ز┘à ╪د┘╪ص┘╪╕.")
            return redirect("control_kyc_settings")
    return render(request, "site/control_kyc_settings.html", {"form": form, "settings": settings_obj, "stats_verified_count": User.objects.filter(is_kyc_verified=True).count()})



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


@finance_required
def control_deposit_detail(request, pk):
    deposit = get_object_or_404(DepositRequest.objects.select_related('user', 'currency', 'payment_method'), pk=pk)
    return render(request, "site/control_deposit_detail.html", {
        "deposit": deposit,
    })



@finance_required
def control_withdrawal_detail(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest.objects.select_related('user', 'user__wallet'), pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=pk)
            action = request.POST.get("action")
            admin_note = request.POST.get("admin_note", "")
            
            from apps.wallets.services import release_funds, finalize_withdrawal
            
            if action == "approve":
                withdrawal.status = WithdrawalRequest.Status.APPROVED
                withdrawal.admin_note = admin_note
                messages.success(request, "╪ز┘à╪ز ╪د┘┘à┘ê╪د┘┘é╪ر ╪د┘┘à╪ذ╪»╪خ┘è╪ر ╪╣┘┘ë ╪د┘╪╖┘╪ذ.")
            elif action == "process":
                withdrawal.status = WithdrawalRequest.Status.PROCESSING
                withdrawal.admin_note = admin_note
                messages.info(request, "╪ذ╪»╪ث╪ز ┘à╪╣╪د┘╪ش╪ر ╪د┘╪╖┘╪ذ.")
            elif action == "complete":
                if withdrawal.status == WithdrawalRequest.Status.COMPLETED:
                     messages.error(request, "┘ç╪░╪د ╪د┘╪╖┘╪ذ ┘à┘â╪ز┘à┘ ┘à╪│╪ذ┘é╪د┘ï.")
                     return redirect("control_withdrawals")

                finalize_withdrawal(
                    withdrawal.user.wallet.id,
                    withdrawal.wallet_amount,
                    reference=f"with_complete:{withdrawal.id}",
                    description=f"Withdrawal completed. {admin_note}",
                    created_by=request.user
                )
                withdrawal.status = WithdrawalRequest.Status.COMPLETED
                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.success(request, "╪ز┘à ╪ح╪ز┘à╪د┘à ╪╣┘à┘┘è╪ر ╪د┘╪│╪ص╪ذ ╪ذ┘╪ش╪د╪ص.")
                return redirect("control_withdrawals")
            elif action == "reject":
                if withdrawal.status in [WithdrawalRequest.Status.COMPLETED, WithdrawalRequest.Status.REJECTED, WithdrawalRequest.Status.CANCELLED]:
                     messages.error(request, "┘╪د ┘è┘à┘â┘ ╪▒┘╪╢ ╪╖┘╪ذ ┘à┘╪ز┘ç┘è.")
                     return redirect("control_withdrawals")

                release_funds(
                    withdrawal.user.wallet.id,
                    withdrawal.wallet_amount,
                    reference=f"with_rej:{withdrawal.id}",
                    description=f"Withdrawal rejected: {admin_note}",
                    created_by=request.user
                )
                withdrawal.status = WithdrawalRequest.Status.REJECTED

                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.error(request, "╪ز┘à ╪▒┘╪╢ ╪╖┘╪ذ ╪د┘╪│╪ص╪ذ ┘ê╪ح╪╣╪د╪»╪ر ╪د┘╪▒╪╡┘è╪» ┘┘┘à╪│╪ز╪«╪»┘à.")
                return redirect("control_withdrawals")
            elif action == "cancel_completed":
                if withdrawal.status != WithdrawalRequest.Status.COMPLETED:
                    messages.error(request, "┘╪د ┘è┘à┘â┘ ╪ح┘╪║╪د╪ة ┘ç╪░╪د ╪د┘╪╖┘╪ذ ┘╪ث┘┘ç ┘┘è╪│ ┘à┘â╪ز┘à┘.")
                    return redirect("control_withdrawal_detail", pk=pk)
                
                from apps.wallets.services import credit_wallet
                credit_wallet(
                    wallet_id=withdrawal.user.wallet.id,
                    amount=withdrawal.wallet_amount,
                    reference=f"with_rev:{withdrawal.id}",
                    description=f"Withdrawal reversed/cancelled: {admin_note}",
                    created_by=request.user,
                    reason="Admin reversal of completed withdrawal"
                )
                withdrawal.status = WithdrawalRequest.Status.CANCELLED
                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.warning(request, "╪ز┘à ╪ح┘╪║╪د╪ة ╪د┘╪│╪ص╪ذ ╪د┘┘à┘â╪ز┘à┘ ┘ê╪ح╪╣╪د╪»╪ر ╪د┘┘à╪ذ┘╪║ ┘┘┘à╪ص┘╪╕╪ر ╪ذ┘╪ش╪د╪ص.")
                return redirect("control_withdrawals")
            
            withdrawal.save()
            return redirect("control_withdrawal_detail", pk=pk)

    return render(request, "site/control_withdrawal_detail.html", {"withdrawal": withdrawal})



@admin_required
def control_users_list(request): return render(request, "site/control_users_list.html", {"users": User.objects.select_related("wallet").order_by("-date_joined"), "tiers": User.Tier.choices, "roles": User.Role.choices})


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
        messages.success(request, "╪ز┘à ╪د┘╪ز╪ص╪»┘è╪س.")
        return redirect("control_users_list")
    return render(request, "site/control_user_moderate.html", {"form": form, "user_to_moderate": user})



@support_required
@transaction.atomic
def control_product_create(request):
    from apps.site.forms import ProductForm
    from apps.catalog.models import Product, ProductVariant
    import json
    
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        
        # Handle variants
        variants_json = request.POST.get("variants_json")
        if variants_json:
            variants_data = json.loads(variants_json)
            for v_data in variants_data:
                ProductVariant.objects.create(
                    product=product,
                    name=v_data.get('name'),
                    sku=v_data.get('sku'),
                    price=Decimal(str(v_data.get('price', '0'))),
                    wholesale_price=Decimal(str(v_data.get('wholesale_price', '0'))),
                    vip_price=Decimal(str(v_data.get('vip_price', '0'))),
                    cost=Decimal(str(v_data.get('cost', '0'))),
                    sort_order=int(v_data.get('sort_order', 0)),
                    is_active=v_data.get('is_active', True)
                )
        
        messages.success(request, "╪ز┘à ╪ح┘╪┤╪د╪ة ╪د┘┘à┘╪ز╪ش ╪ذ┘╪ش╪د╪ص.")
        return redirect("control_products_list")
        
    return render(request, "site/control_product_builder.html", {
        "form": form, "title": "╪ح╪╢╪د┘╪ر ┘à┘╪ز╪ش ╪ش╪»┘è╪»", "variants_json_data": []
    })



@support_required
@transaction.atomic
def control_product_edit(request, pk):
    from apps.site.forms import ProductForm
    from apps.catalog.models import Product, ProductVariant
    import json
    
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    
    if request.method == "POST" and form.is_valid():
        product = form.save()
        
        # Handle variants (Sync strategy)
        variants_json = request.POST.get("variants_json")
        if variants_json:
            variants_data = json.loads(variants_json)
            incoming_skus = set(v.get('sku') for v in variants_data if v.get('sku'))
            
            # Delete removed ones
            product.variants.exclude(sku__in=incoming_skus).delete()
            
            for v_data in variants_data:
                sku = v_data.get('sku')
                ProductVariant.objects.update_or_create(
                    product=product, sku=sku,
                    defaults={
                        "name": v_data.get('name'),
                        "price": Decimal(str(v_data.get('price', '0'))),
                        "wholesale_price": Decimal(str(v_data.get('wholesale_price', '0'))),
                        "vip_price": Decimal(str(v_data.get('vip_price', '0'))),
                        "cost": Decimal(str(v_data.get('cost', '0'))),
                        "sort_order": int(v_data.get('sort_order', 0)),
                        "is_active": v_data.get('is_active', True)
                    }
                )
        
        messages.success(request, "╪ز┘à ╪ز╪ص╪»┘è╪س ╪د┘┘à┘╪ز╪ش ╪ذ┘╪ش╪د╪ص.")
        return redirect("control_products_list")
    
    # Prepare variants for JSON script
    variants = product.variants.all().order_by('sort_order')
    variants_json_data = []
    for v in variants:
        variants_json_data.append({
            "name": v.name, "sku": v.sku, "price": str(v.price),
            "wholesale_price": str(v.wholesale_price), "vip_price": str(v.vip_price),
            "cost": str(v.cost), "sort_order": v.sort_order, "is_active": v.is_active
        })
        
    return render(request, "site/control_product_builder.html", {
        "form": form, "product": product, "title": f"╪ز╪╣╪»┘è┘ ╪د┘┘à┘╪ز╪ش: {product.name}",
        "variants_json_data": variants_json_data
    })


@support_required
def control_category_create_ajax(request):
    from apps.catalog.models import Category
    name = request.POST.get('name')
    if name:
        cat = Category.objects.create(name=name)
        return JsonResponse({"id": str(cat.id), "name": cat.name})
    return JsonResponse({"error": "Name required"}, status=400)



@admin_required
def control_support_settings(request):
    settings_obj, created = SupportSettings.objects.get_or_create(id=1)
    form = SupportSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ إعدادات الدعم بنجاح.")
        return redirect("control_support_settings")
    return render(request, "site/control_support_settings.html", {"form": form})



@support_required
def control_quick_replies(request):
    replies = ChatCannedReply.objects.all().order_by("-created_at")
    return render(request, "site/control_quick_replies.html", {"replies": replies})



@support_required
def control_quick_reply_create(request):
    form = ChatCannedReplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إضافة الرد الجاهز بنجاح.")
        return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})



@support_required
def control_quick_reply_edit(request, pk):
    reply = get_object_or_404(ChatCannedReply, pk=pk)
    form = ChatCannedReplyForm(request.POST or None, instance=reply)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم تعديل الرد الجاهز بنجاح.")
        return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})



@support_required
def control_quick_reply_delete(request, pk):
    reply = get_object_or_404(ChatCannedReply, pk=pk)
    reply.delete()
    messages.success(request, "تم حذف الرد الجاهز بنجاح.")
    return redirect("control_quick_replies")



def privacy_policy(request): return render(request, "site/privacy_policy.html")


@login_required
def wallet_page(request):
    """
    Displays the user's wallet dashboard and recent ledger entries.
    """
    request.user.reset_daily_limits_if_needed()
    wallet = Wallet.objects.filter(user=request.user).select_related("currency").first() or get_or_create_wallet(request.user)
    return render(request, "site/wallet.html", {"wallet": wallet, "ledger_entries": wallet.ledger_entries.all()[:20]})




@login_required
def orders_list(request):
    orders = request.user.orders.all().prefetch_related('items__variant__product')
    return render(request, "site/orders_list.html", {"orders": orders})



@login_required
def order_detail(request, pk):
    order = get_object_or_404(request.user.orders.prefetch_related('items__variant__product', 'logs'), pk=pk)
    return render(request, "site/order_detail.html", {"order": order})




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
        messages.success(request, "╪ز┘à ╪ص┘╪╕ ╪ح╪╣╪»╪د╪»╪د╪ز ╪د┘╪ح╪┤╪╣╪د╪▒╪د╪ز ╪ذ┘╪ش╪د╪ص.")
        return redirect("notification_settings")
        
    return render(request, "site/notification_settings.html", {"settings": settings_obj})


@login_required
def v3_change_password_view(request):
    form = ChangePasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = request.user
        current_password = form.cleaned_data["current_password"]
        new_password = form.cleaned_data["new_password"]
        
        if user.check_password(current_password):
            with transaction.atomic():
                user.set_password(new_password)
                user.save()
                
                # Update session to prevent logout of current session
                update_session_auth_hash(request, user)
                
                # Invalidate other sessions
                from django.contrib.sessions.models import Session
                for session in Session.objects.all():
                    decoded = session.get_decoded()
                    if decoded.get('_auth_user_id') == str(user.id):
                        if session.session_key != request.session.session_key:
                            session.delete()
                
                ActivityLog.objects.create(user=user, action="Password Change", description="User changed password and invalidated other sessions")
                messages.success(request, "تم تغيير كلمة المرور بنجاح وتم تسجيل الخروج من الأجهزة الأخرى.")
                return redirect("dashboard")
        else:
            messages.error(request, "كلمة المرور الحالية غير صحيحة.")
            
    return render(request, "site/v3/v3_change_password.html", {"form": form})


from apps.common.decorators import finance_required, support_required, kyc_required, admin_required
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest



def v3_forgot_password_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").lower().strip()
        user = User.objects.filter(email=email).first()
        
        if user:
            otp = v3_generate_otp(user, OTPToken.Purpose.PASSWORD_RESET)
            if v3_send_otp_email(user, otp):
                request.session["v3_auth_uid"] = str(user.id)
                request.session["v3_auth_purpose"] = OTPToken.Purpose.PASSWORD_RESET
                messages.success(request, "╪ز┘à ╪ح╪▒╪│╪د┘ ╪▒┘à╪▓ ╪د┘╪ز╪ص┘é┘é ┘╪ح╪╣╪د╪»╪ر ╪ز╪╣┘è┘è┘ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒.")
                return redirect("site_verify_otp")
            else:
                messages.error(request, "┘╪┤┘ ╪ح╪▒╪│╪د┘ ╪د┘╪▒┘à╪▓. ┘è╪▒╪ش┘ë ╪د┘┘à╪ص╪د┘ê┘╪ر ┘╪د╪ص┘é╪د┘ï.")
        else:
            messages.error(request, "╪╣╪░╪▒╪د┘ï╪î ┘ç╪░╪د ╪د┘╪ذ╪▒┘è╪» ╪د┘╪ح┘┘â╪ز╪▒┘ê┘┘è ╪║┘è╪▒ ┘à╪│╪ش┘ ┘╪»┘è┘╪د.")
            
    return render(request, "site/v3/v3_forgot_password.html")




def v3_reset_password_view(request):
    uid = request.session.get("v3_auth_uid")
    is_verified = request.session.get("v3_recovery_verified") == True
    
    if not uid or not is_verified:
        messages.error(request, "┘è╪▒╪ش┘ë ╪د┘╪ز╪ص┘é┘é ┘à┘ ┘ç┘ê┘è╪ز┘â ╪ث┘ê┘╪د┘ï.")
        return redirect("site_forgot_password")
        
    user = get_object_or_404(User, id=uid)
    
    if request.method == "POST":
        p1 = request.POST.get("password")
        p2 = request.POST.get("confirm_password")
        
        if not p1 or len(p1) < 10:
            messages.error(request, "┘è╪ش╪ذ ╪ث┘ ╪ز┘â┘ê┘ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒ 10 ╪«╪د┘╪د╪ز ╪╣┘┘ë ╪د┘╪ث┘é┘.")
        elif p1 != p2:
            messages.error(request, "┘â┘┘à╪د╪ز ╪د┘┘à╪▒┘ê╪▒ ╪║┘è╪▒ ┘à╪ز╪╖╪د╪ذ┘é╪ر.")
        else:
            user.set_password(p1)
            user.save()
            
            # Clean up all auth sessions
            request.session.flush()
            
            ActivityLog.objects.create(user=user, action="Password Reset Success", description="User reset password via V3 OTP flow")
            messages.success(request, "╪ز┘à ╪ز╪║┘è┘è╪▒ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒ ╪ذ┘╪ش╪د╪ص. ┘è┘à┘â┘┘â ╪د┘╪ت┘ ╪ز╪│╪ش┘è┘ ╪د┘╪»╪«┘ê┘.")
            return redirect("site_login")
            
    return render(request, "site/v3/v3_reset_password.html", {"user_email": user.email})




def resend_verification(request): return redirect("dashboard")


def email_verify(request, uidb64, token): return redirect("site_login")


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
                messages.success(request, f"┘┘â ╪د┘╪ص╪╕╪▒ ╪╣┘ {code}.")
            return redirect("control_kyc_settings")
        elif form.is_valid():
            form.save()
            messages.success(request, "╪ز┘à ╪د┘╪ص┘╪╕.")
            return redirect("control_kyc_settings")
    return render(request, "site/control_kyc_settings.html", {"form": form, "settings": settings_obj, "stats_verified_count": User.objects.filter(is_kyc_verified=True).count()})



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


@finance_required
def control_deposit_detail(request, pk):
    deposit = get_object_or_404(DepositRequest.objects.select_related('user', 'currency', 'payment_method'), pk=pk)
    return render(request, "site/control_deposit_detail.html", {
        "deposit": deposit,
    })



@finance_required
def control_withdrawal_detail(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest.objects.select_related('user', 'user__wallet'), pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=pk)
            action = request.POST.get("action")
            admin_note = request.POST.get("admin_note", "")
            
            from apps.wallets.services import release_funds, finalize_withdrawal
            
            if action == "approve":
                withdrawal.status = WithdrawalRequest.Status.APPROVED
                withdrawal.admin_note = admin_note
                messages.success(request, "╪ز┘à╪ز ╪د┘┘à┘ê╪د┘┘é╪ر ╪د┘┘à╪ذ╪»╪خ┘è╪ر ╪╣┘┘ë ╪د┘╪╖┘╪ذ.")
            elif action == "process":
                withdrawal.status = WithdrawalRequest.Status.PROCESSING
                withdrawal.admin_note = admin_note
                messages.info(request, "╪ذ╪»╪ث╪ز ┘à╪╣╪د┘╪ش╪ر ╪د┘╪╖┘╪ذ.")
            elif action == "complete":
                if withdrawal.status == WithdrawalRequest.Status.COMPLETED:
                     messages.error(request, "┘ç╪░╪د ╪د┘╪╖┘╪ذ ┘à┘â╪ز┘à┘ ┘à╪│╪ذ┘é╪د┘ï.")
                     return redirect("control_withdrawals")

                finalize_withdrawal(
                    withdrawal.user.wallet.id,
                    withdrawal.wallet_amount,
                    reference=f"with_complete:{withdrawal.id}",
                    description=f"Withdrawal completed. {admin_note}",
                    created_by=request.user
                )
                withdrawal.status = WithdrawalRequest.Status.COMPLETED
                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.success(request, "╪ز┘à ╪ح╪ز┘à╪د┘à ╪╣┘à┘┘è╪ر ╪د┘╪│╪ص╪ذ ╪ذ┘╪ش╪د╪ص.")
                return redirect("control_withdrawals")
            elif action == "reject":
                if withdrawal.status in [WithdrawalRequest.Status.COMPLETED, WithdrawalRequest.Status.REJECTED, WithdrawalRequest.Status.CANCELLED]:
                     messages.error(request, "┘╪د ┘è┘à┘â┘ ╪▒┘╪╢ ╪╖┘╪ذ ┘à┘╪ز┘ç┘è.")
                     return redirect("control_withdrawals")

                release_funds(
                    withdrawal.user.wallet.id,
                    withdrawal.wallet_amount,
                    reference=f"with_rej:{withdrawal.id}",
                    description=f"Withdrawal rejected: {admin_note}",
                    created_by=request.user
                )
                withdrawal.status = WithdrawalRequest.Status.REJECTED

                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.error(request, "╪ز┘à ╪▒┘╪╢ ╪╖┘╪ذ ╪د┘╪│╪ص╪ذ ┘ê╪ح╪╣╪د╪»╪ر ╪د┘╪▒╪╡┘è╪» ┘┘┘à╪│╪ز╪«╪»┘à.")
                return redirect("control_withdrawals")
            elif action == "cancel_completed":
                if withdrawal.status != WithdrawalRequest.Status.COMPLETED:
                    messages.error(request, "┘╪د ┘è┘à┘â┘ ╪ح┘╪║╪د╪ة ┘ç╪░╪د ╪د┘╪╖┘╪ذ ┘╪ث┘┘ç ┘┘è╪│ ┘à┘â╪ز┘à┘.")
                    return redirect("control_withdrawal_detail", pk=pk)
                
                from apps.wallets.services import credit_wallet
                credit_wallet(
                    wallet_id=withdrawal.user.wallet.id,
                    amount=withdrawal.wallet_amount,
                    reference=f"with_rev:{withdrawal.id}",
                    description=f"Withdrawal reversed/cancelled: {admin_note}",
                    created_by=request.user,
                    reason="Admin reversal of completed withdrawal"
                )
                withdrawal.status = WithdrawalRequest.Status.CANCELLED
                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.warning(request, "╪ز┘à ╪ح┘╪║╪د╪ة ╪د┘╪│╪ص╪ذ ╪د┘┘à┘â╪ز┘à┘ ┘ê╪ح╪╣╪د╪»╪ر ╪د┘┘à╪ذ┘╪║ ┘┘┘à╪ص┘╪╕╪ر ╪ذ┘╪ش╪د╪ص.")
                return redirect("control_withdrawals")
            
            withdrawal.save()
            return redirect("control_withdrawal_detail", pk=pk)

    return render(request, "site/control_withdrawal_detail.html", {"withdrawal": withdrawal})



@admin_required
def control_users_list(request): return render(request, "site/control_users_list.html", {"users": User.objects.select_related("wallet").order_by("-date_joined"), "tiers": User.Tier.choices, "roles": User.Role.choices})


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
        messages.success(request, "╪ز┘à ╪د┘╪ز╪ص╪»┘è╪س.")
        return redirect("control_users_list")
    return render(request, "site/control_user_moderate.html", {"form": form, "user_to_moderate": user})



@support_required
@transaction.atomic
def control_product_create(request):
    from apps.site.forms import ProductForm
    from apps.catalog.models import Product, ProductVariant
    import json
    
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        
        # Handle variants
        variants_json = request.POST.get("variants_json")
        if variants_json:
            variants_data = json.loads(variants_json)
            for v_data in variants_data:
                ProductVariant.objects.create(
                    product=product,
                    name=v_data.get('name'),
                    sku=v_data.get('sku'),
                    price=Decimal(str(v_data.get('price', '0'))),
                    wholesale_price=Decimal(str(v_data.get('wholesale_price', '0'))),
                    vip_price=Decimal(str(v_data.get('vip_price', '0'))),
                    cost=Decimal(str(v_data.get('cost', '0'))),
                    sort_order=int(v_data.get('sort_order', 0)),
                    is_active=v_data.get('is_active', True)
                )
        
        messages.success(request, "╪ز┘à ╪ح┘╪┤╪د╪ة ╪د┘┘à┘╪ز╪ش ╪ذ┘╪ش╪د╪ص.")
        return redirect("control_products_list")
        
    return render(request, "site/control_product_builder.html", {
        "form": form, "title": "╪ح╪╢╪د┘╪ر ┘à┘╪ز╪ش ╪ش╪»┘è╪»", "variants_json_data": []
    })



@support_required
@transaction.atomic
def control_product_edit(request, pk):
    from apps.site.forms import ProductForm
    from apps.catalog.models import Product, ProductVariant
    import json
    
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    
    if request.method == "POST" and form.is_valid():
        product = form.save()
        
        # Handle variants (Sync strategy)
        variants_json = request.POST.get("variants_json")
        if variants_json:
            variants_data = json.loads(variants_json)
            incoming_skus = set(v.get('sku') for v in variants_data if v.get('sku'))
            
            # Delete removed ones
            product.variants.exclude(sku__in=incoming_skus).delete()
            
            for v_data in variants_data:
                sku = v_data.get('sku')
                ProductVariant.objects.update_or_create(
                    product=product, sku=sku,
                    defaults={
                        "name": v_data.get('name'),
                        "price": Decimal(str(v_data.get('price', '0'))),
                        "wholesale_price": Decimal(str(v_data.get('wholesale_price', '0'))),
                        "vip_price": Decimal(str(v_data.get('vip_price', '0'))),
                        "cost": Decimal(str(v_data.get('cost', '0'))),
                        "sort_order": int(v_data.get('sort_order', 0)),
                        "is_active": v_data.get('is_active', True)
                    }
                )
        
        messages.success(request, "╪ز┘à ╪ز╪ص╪»┘è╪س ╪د┘┘à┘╪ز╪ش ╪ذ┘╪ش╪د╪ص.")
        return redirect("control_products_list")
    
    # Prepare variants for JSON script
    variants = product.variants.all().order_by('sort_order')
    variants_json_data = []
    for v in variants:
        variants_json_data.append({
            "name": v.name, "sku": v.sku, "price": str(v.price),
            "wholesale_price": str(v.wholesale_price), "vip_price": str(v.vip_price),
            "cost": str(v.cost), "sort_order": v.sort_order, "is_active": v.is_active
        })
        
    return render(request, "site/control_product_builder.html", {
        "form": form, "product": product, "title": f"╪ز╪╣╪»┘è┘ ╪د┘┘à┘╪ز╪ش: {product.name}",
        "variants_json_data": variants_json_data
    })


@support_required
def control_variant_create(request, product_pk): return render(request, "site/control_variant_form.html")


@support_required
def control_variant_edit(request, pk): return render(request, "site/control_variant_form.html")



@finance_required
def control_wallets_list(request):
    q = request.GET.get('q', '')
    wallets = Wallet.objects.select_related('user', 'currency').all().order_by('-updated_at')
    if q:
        wallets = wallets.filter(Q(user__email__icontains=q) | Q(user__first_name__icontains=q))
    return render(request, "site/control_wallets_list.html", {"wallets": wallets, "query": q})


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
                messages.success(request, f"╪ز┘à ╪ح╪╢╪د┘╪ر ╪»┘è┘ ╪ذ┘é┘è┘à╪ر {amount} ┘┘┘à╪│╪ز╪«╪»┘à {target_user.email}")
            elif action == "pay_debt":
                from apps.wallets.services import pay_debt
                pay_debt(wallet.id, amount, reference=f"admin_pay_{timezone.now().timestamp()}", reason=reason, created_by=request.user, deduct_from_balance=False)
                messages.success(request, f"╪ز┘à ╪ز╪│╪ش┘è┘ ╪│╪»╪د╪» ╪ذ┘é┘è┘à╪ر {amount} ┘┘┘à╪│╪ز╪«╪»┘à {target_user.email}")
        except Exception as e:
            messages.error(request, str(e))
            
        return redirect(f"{request.path}?q={q}")

    return render(request, "site/control_debts.html", {"users": users, "query": q})



def set_currency(request):
    currency_id = request.GET.get("currency") or request.POST.get("currency")
    if currency_id:
        currency = Currency.objects.filter(id=currency_id, is_active=True).first()
        if currency:
            request.session["preferred_currency_id"] = str(currency.id)
            if request.user.is_authenticated:
                request.user.preferred_currency = currency
                request.user.save(update_fields=["preferred_currency"])
            messages.success(request, f"╪ز┘à ╪ز╪║┘è┘è╪▒ ╪د┘╪╣┘à┘╪ر ╪د┘┘à┘╪╢┘╪ر ╪ح┘┘ë {currency.name}.")
    
    # Redirect back to referring page or home
    next_url = request.META.get('HTTP_REFERER', 'home')
    return redirect(next_url)


def tickets(request): return render(request, "site/tickets.html")


def ticket_detail(request, pk): return render(request, "site/ticket_detail.html")



@support_required
def control_category_create_ajax(request):
    from apps.catalog.models import Category
    name = request.POST.get('name')
    if name:
        cat = Category.objects.create(name=name)
        return JsonResponse({"id": str(cat.id), "name": cat.name})
    return JsonResponse({"error": "Name required"}, status=400)



@admin_required
def control_support_settings(request):
    settings_obj, created = SupportSettings.objects.get_or_create(id=1)
    form = SupportSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ إعدادات الدعم بنجاح.")
        return redirect("control_support_settings")
    return render(request, "site/control_support_settings.html", {"form": form})



@support_required
def control_quick_replies(request):
    replies = ChatCannedReply.objects.all().order_by("-created_at")
    return render(request, "site/control_quick_replies.html", {"replies": replies})



@support_required
def control_quick_reply_create(request):
    form = ChatCannedReplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إضافة الرد الجاهز بنجاح.")
        return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})



@support_required
def control_quick_reply_edit(request, pk):
    reply = get_object_or_404(ChatCannedReply, pk=pk)
    form = ChatCannedReplyForm(request.POST or None, instance=reply)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم تعديل الرد الجاهز بنجاح.")
        return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})



@support_required
def control_quick_reply_delete(request, pk):
    reply = get_object_or_404(ChatCannedReply, pk=pk)
    reply.delete()
    messages.success(request, "تم حذف الرد الجاهز بنجاح.")
    return redirect("control_quick_replies")



def privacy_policy(request): return render(request, "site/privacy_policy.html")


@login_required
def wallet_page(request):
    """
    Displays the user's wallet dashboard and recent ledger entries.
    """
    request.user.reset_daily_limits_if_needed()
    wallet = Wallet.objects.filter(user=request.user).select_related("currency").first() or get_or_create_wallet(request.user)
    return render(request, "site/wallet.html", {"wallet": wallet, "ledger_entries": wallet.ledger_entries.all()[:20]})




@login_required
def orders_list(request):
    orders = request.user.orders.all().prefetch_related('items__variant__product')
    return render(request, "site/orders_list.html", {"orders": orders})



@login_required
def order_detail(request, pk):
    order = get_object_or_404(request.user.orders.prefetch_related('items__variant__product', 'logs'), pk=pk)
    return render(request, "site/order_detail.html", {"order": order})




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
        messages.success(request, "╪ز┘à ╪ص┘╪╕ ╪ح╪╣╪»╪د╪»╪د╪ز ╪د┘╪ح╪┤╪╣╪د╪▒╪د╪ز ╪ذ┘╪ش╪د╪ص.")
        return redirect("notification_settings")
        
    return render(request, "site/notification_settings.html", {"settings": settings_obj})


@login_required
def v3_change_password_view(request):
    form = ChangePasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = request.user
        current_password = form.cleaned_data["current_password"]
        new_password = form.cleaned_data["new_password"]
        
        if user.check_password(current_password):
            with transaction.atomic():
                user.set_password(new_password)
                user.save()
                
                # Update session to prevent logout of current session
                update_session_auth_hash(request, user)
                
                # Invalidate other sessions
                from django.contrib.sessions.models import Session
                for session in Session.objects.all():
                    decoded = session.get_decoded()
                    if decoded.get('_auth_user_id') == str(user.id):
                        if session.session_key != request.session.session_key:
                            session.delete()
                
                ActivityLog.objects.create(user=user, action="Password Change", description="User changed password and invalidated other sessions")
                messages.success(request, "تم تغيير كلمة المرور بنجاح وتم تسجيل الخروج من الأجهزة الأخرى.")
                return redirect("dashboard")
        else:
            messages.error(request, "كلمة المرور الحالية غير صحيحة.")
            
    return render(request, "site/v3/v3_change_password.html", {"form": form})


from apps.common.decorators import finance_required, support_required, kyc_required, admin_required
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest



def v3_forgot_password_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").lower().strip()
        user = User.objects.filter(email=email).first()
        
        if user:
            otp = v3_generate_otp(user, OTPToken.Purpose.PASSWORD_RESET)
            if v3_send_otp_email(user, otp):
                request.session["v3_auth_uid"] = str(user.id)
                request.session["v3_auth_purpose"] = OTPToken.Purpose.PASSWORD_RESET
                messages.success(request, "╪ز┘à ╪ح╪▒╪│╪د┘ ╪▒┘à╪▓ ╪د┘╪ز╪ص┘é┘é ┘╪ح╪╣╪د╪»╪ر ╪ز╪╣┘è┘è┘ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒.")
                return redirect("site_verify_otp")
            else:
                messages.error(request, "┘╪┤┘ ╪ح╪▒╪│╪د┘ ╪د┘╪▒┘à╪▓. ┘è╪▒╪ش┘ë ╪د┘┘à╪ص╪د┘ê┘╪ر ┘╪د╪ص┘é╪د┘ï.")
        else:
            messages.error(request, "╪╣╪░╪▒╪د┘ï╪î ┘ç╪░╪د ╪د┘╪ذ╪▒┘è╪» ╪د┘╪ح┘┘â╪ز╪▒┘ê┘┘è ╪║┘è╪▒ ┘à╪│╪ش┘ ┘╪»┘è┘╪د.")
            
    return render(request, "site/v3/v3_forgot_password.html")




def v3_reset_password_view(request):
    uid = request.session.get("v3_auth_uid")
    is_verified = request.session.get("v3_recovery_verified") == True
    
    if not uid or not is_verified:
        messages.error(request, "┘è╪▒╪ش┘ë ╪د┘╪ز╪ص┘é┘é ┘à┘ ┘ç┘ê┘è╪ز┘â ╪ث┘ê┘╪د┘ï.")
        return redirect("site_forgot_password")
        
    user = get_object_or_404(User, id=uid)
    
    if request.method == "POST":
        p1 = request.POST.get("password")
        p2 = request.POST.get("confirm_password")
        
        if not p1 or len(p1) < 10:
            messages.error(request, "┘è╪ش╪ذ ╪ث┘ ╪ز┘â┘ê┘ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒ 10 ╪«╪د┘╪د╪ز ╪╣┘┘ë ╪د┘╪ث┘é┘.")
        elif p1 != p2:
            messages.error(request, "┘â┘┘à╪د╪ز ╪د┘┘à╪▒┘ê╪▒ ╪║┘è╪▒ ┘à╪ز╪╖╪د╪ذ┘é╪ر.")
        else:
            user.set_password(p1)
            user.save()
            
            # Clean up all auth sessions
            request.session.flush()
            
            ActivityLog.objects.create(user=user, action="Password Reset Success", description="User reset password via V3 OTP flow")
            messages.success(request, "╪ز┘à ╪ز╪║┘è┘è╪▒ ┘â┘┘à╪ر ╪د┘┘à╪▒┘ê╪▒ ╪ذ┘╪ش╪د╪ص. ┘è┘à┘â┘┘â ╪د┘╪ت┘ ╪ز╪│╪ش┘è┘ ╪د┘╪»╪«┘ê┘.")
            return redirect("site_login")
            
    return render(request, "site/v3/v3_reset_password.html", {"user_email": user.email})




def resend_verification(request): return redirect("dashboard")


def email_verify(request, uidb64, token): return redirect("site_login")


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
                messages.success(request, f"┘┘â ╪د┘╪ص╪╕╪▒ ╪╣┘ {code}.")
            return redirect("control_kyc_settings")
        elif form.is_valid():
            form.save()
            messages.success(request, "╪ز┘à ╪د┘╪ص┘╪╕.")
            return redirect("control_kyc_settings")
    return render(request, "site/control_kyc_settings.html", {"form": form, "settings": settings_obj, "stats_verified_count": User.objects.filter(is_kyc_verified=True).count()})



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


@finance_required
def control_deposit_detail(request, pk):
    deposit = get_object_or_404(DepositRequest.objects.select_related('user', 'currency', 'payment_method'), pk=pk)
    return render(request, "site/control_deposit_detail.html", {
        "deposit": deposit,
    })



@finance_required
def control_withdrawal_detail(request, pk):
    withdrawal = get_object_or_404(WithdrawalRequest.objects.select_related('user', 'user__wallet'), pk=pk)
    if request.method == "POST":
        with transaction.atomic():
            withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=pk)
            action = request.POST.get("action")
            admin_note = request.POST.get("admin_note", "")
            
            from apps.wallets.services import release_funds, finalize_withdrawal
            
            if action == "approve":
                withdrawal.status = WithdrawalRequest.Status.APPROVED
                withdrawal.admin_note = admin_note
                messages.success(request, "╪ز┘à╪ز ╪د┘┘à┘ê╪د┘┘é╪ر ╪د┘┘à╪ذ╪»╪خ┘è╪ر ╪╣┘┘ë ╪د┘╪╖┘╪ذ.")
            elif action == "process":
                withdrawal.status = WithdrawalRequest.Status.PROCESSING
                withdrawal.admin_note = admin_note
                messages.info(request, "╪ذ╪»╪ث╪ز ┘à╪╣╪د┘╪ش╪ر ╪د┘╪╖┘╪ذ.")
            elif action == "complete":
                if withdrawal.status == WithdrawalRequest.Status.COMPLETED:
                     messages.error(request, "┘ç╪░╪د ╪د┘╪╖┘╪ذ ┘à┘â╪ز┘à┘ ┘à╪│╪ذ┘é╪د┘ï.")
                     return redirect("control_withdrawals")

                finalize_withdrawal(
                    withdrawal.user.wallet.id,
                    withdrawal.wallet_amount,
                    reference=f"with_complete:{withdrawal.id}",
                    description=f"Withdrawal completed. {admin_note}",
                    created_by=request.user
                )
                withdrawal.status = WithdrawalRequest.Status.COMPLETED
                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.success(request, "╪ز┘à ╪ح╪ز┘à╪د┘à ╪╣┘à┘┘è╪ر ╪د┘╪│╪ص╪ذ ╪ذ┘╪ش╪د╪ص.")
                return redirect("control_withdrawals")
            elif action == "reject":
                if withdrawal.status in [WithdrawalRequest.Status.COMPLETED, WithdrawalRequest.Status.REJECTED, WithdrawalRequest.Status.CANCELLED]:
                     messages.error(request, "┘╪د ┘è┘à┘â┘ ╪▒┘╪╢ ╪╖┘╪ذ ┘à┘╪ز┘ç┘è.")
                     return redirect("control_withdrawals")

                release_funds(
                    withdrawal.user.wallet.id,
                    withdrawal.wallet_amount,
                    reference=f"with_rej:{withdrawal.id}",
                    description=f"Withdrawal rejected: {admin_note}",
                    created_by=request.user
                )
                withdrawal.status = WithdrawalRequest.Status.REJECTED

                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.error(request, "╪ز┘à ╪▒┘╪╢ ╪╖┘╪ذ ╪د┘╪│╪ص╪ذ ┘ê╪ح╪╣╪د╪»╪ر ╪د┘╪▒╪╡┘è╪» ┘┘┘à╪│╪ز╪«╪»┘à.")
                return redirect("control_withdrawals")
            elif action == "cancel_completed":
                if withdrawal.status != WithdrawalRequest.Status.COMPLETED:
                    messages.error(request, "┘╪د ┘è┘à┘â┘ ╪ح┘╪║╪د╪ة ┘ç╪░╪د ╪د┘╪╖┘╪ذ ┘╪ث┘┘ç ┘┘è╪│ ┘à┘â╪ز┘à┘.")
                    return redirect("control_withdrawal_detail", pk=pk)
                
                from apps.wallets.services import credit_wallet
                credit_wallet(
                    wallet_id=withdrawal.user.wallet.id,
                    amount=withdrawal.wallet_amount,
                    reference=f"with_rev:{withdrawal.id}",
                    description=f"Withdrawal reversed/cancelled: {admin_note}",
                    created_by=request.user,
                    reason="Admin reversal of completed withdrawal"
                )
                withdrawal.status = WithdrawalRequest.Status.CANCELLED
                withdrawal.admin_note = admin_note
                withdrawal.reviewed_by = request.user
                withdrawal.reviewed_at = timezone.now()
                withdrawal.save()
                messages.warning(request, "╪ز┘à ╪ح┘╪║╪د╪ة ╪د┘╪│╪ص╪ذ ╪د┘┘à┘â╪ز┘à┘ ┘ê╪ح╪╣╪د╪»╪ر ╪د┘┘à╪ذ┘╪║ ┘┘┘à╪ص┘╪╕╪ر ╪ذ┘╪ش╪د╪ص.")
                return redirect("control_withdrawals")
            
            withdrawal.save()
            return redirect("control_withdrawal_detail", pk=pk)

    return render(request, "site/control_withdrawal_detail.html", {"withdrawal": withdrawal})



@admin_required
def control_users_list(request): return render(request, "site/control_users_list.html", {"users": User.objects.select_related("wallet").order_by("-date_joined"), "tiers": User.Tier.choices, "roles": User.Role.choices})


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
        messages.success(request, "╪ز┘à ╪د┘╪ز╪ص╪»┘è╪س.")
        return redirect("control_users_list")
    return render(request, "site/control_user_moderate.html", {"form": form, "user_to_moderate": user})



@support_required
@transaction.atomic
def control_product_create(request):
    from apps.site.forms import ProductForm
    from apps.catalog.models import Product, ProductVariant
    import json
    
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save()
        
        # Handle variants
        variants_json = request.POST.get("variants_json")
        if variants_json:
            variants_data = json.loads(variants_json)
            for v_data in variants_data:
                ProductVariant.objects.create(
                    product=product,
                    name=v_data.get('name'),
                    sku=v_data.get('sku'),
                    price=Decimal(str(v_data.get('price', '0'))),
                    wholesale_price=Decimal(str(v_data.get('wholesale_price', '0'))),
                    vip_price=Decimal(str(v_data.get('vip_price', '0'))),
                    cost=Decimal(str(v_data.get('cost', '0'))),
                    sort_order=int(v_data.get('sort_order', 0)),
                    is_active=v_data.get('is_active', True)
                )
        
        messages.success(request, "╪ز┘à ╪ح┘╪┤╪د╪ة ╪د┘┘à┘╪ز╪ش ╪ذ┘╪ش╪د╪ص.")
        return redirect("control_products_list")
        
    return render(request, "site/control_product_builder.html", {
        "form": form, "title": "╪ح╪╢╪د┘╪ر ┘à┘╪ز╪ش ╪ش╪»┘è╪»", "variants_json_data": []
    })



@support_required
@transaction.atomic
def control_product_edit(request, pk):
    from apps.site.forms import ProductForm
    from apps.catalog.models import Product, ProductVariant
    import json
    
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    
    if request.method == "POST" and form.is_valid():
        product = form.save()
        
        # Handle variants (Sync strategy)
        variants_json = request.POST.get("variants_json")
        if variants_json:
            variants_data = json.loads(variants_json)
            incoming_skus = set(v.get('sku') for v in variants_data if v.get('sku'))
            
            # Delete removed ones
            product.variants.exclude(sku__in=incoming_skus).delete()
            
            for v_data in variants_data:
                sku = v_data.get('sku')
                ProductVariant.objects.update_or_create(
                    product=product, sku=sku,
                    defaults={
                        "name": v_data.get('name'),
                        "price": Decimal(str(v_data.get('price', '0'))),
                        "wholesale_price": Decimal(str(v_data.get('wholesale_price', '0'))),
                        "vip_price": Decimal(str(v_data.get('vip_price', '0'))),
                        "cost": Decimal(str(v_data.get('cost', '0'))),
                        "sort_order": int(v_data.get('sort_order', 0)),
                        "is_active": v_data.get('is_active', True)
                    }
                )
        
        messages.success(request, "╪ز┘à ╪ز╪ص╪»┘è╪س ╪د┘┘à┘╪ز╪ش ╪ذ┘╪ش╪د╪ص.")
        return redirect("control_products_list")
    
    # Prepare variants for JSON script
    variants = product.variants.all().order_by('sort_order')
    variants_json_data = []
    for v in variants:
        variants_json_data.append({
            "name": v.name, "sku": v.sku, "price": str(v.price),
            "wholesale_price": str(v.wholesale_price), "vip_price": str(v.vip_price),
            "cost": str(v.cost), "sort_order": v.sort_order, "is_active": v.is_active
        })
        
    return render(request, "site/control_product_builder.html", {
        "form": form, "product": product, "title": f"╪ز╪╣╪»┘è┘ ╪د┘┘à┘╪ز╪ش: {product.name}",
        "variants_json_data": variants_json_data
    })


@support_required
def control_variant_create(request, product_pk): return render(request, "site/control_variant_form.html")


@support_required
def control_variant_edit(request, pk): return render(request, "site/control_variant_form.html")



@finance_required
def control_wallets_list(request):
    q = request.GET.get('q', '')
    wallets = Wallet.objects.select_related('user', 'currency').all().order_by('-updated_at')
    if q:
        wallets = wallets.filter(Q(user__email__icontains=q) | Q(user__first_name__icontains=q))
    return render(request, "site/control_wallets_list.html", {"wallets": wallets, "query": q})


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
                messages.success(request, f"╪ز┘à ╪ح╪╢╪د┘╪ر ╪»┘è┘ ╪ذ┘é┘è┘à╪ر {amount} ┘┘┘à╪│╪ز╪«╪»┘à {target_user.email}")
            elif action == "pay_debt":
                from apps.wallets.services import pay_debt
                pay_debt(wallet.id, amount, reference=f"admin_pay_{timezone.now().timestamp()}", reason=reason, created_by=request.user, deduct_from_balance=False)
                messages.success(request, f"╪ز┘à ╪ز╪│╪ش┘è┘ ╪│╪»╪د╪» ╪ذ┘é┘è┘à╪ر {amount} ┘┘┘à╪│╪ز╪«╪»┘à {target_user.email}")
        except Exception as e:
            messages.error(request, str(e))
            
        return redirect(f"{request.path}?q={q}")

    return render(request, "site/control_debts.html", {"users": users, "query": q})



def set_currency(request):
    currency_id = request.GET.get("currency") or request.POST.get("currency")
    if currency_id:
        currency = Currency.objects.filter(id=currency_id, is_active=True).first()
        if currency:
            request.session["preferred_currency_id"] = str(currency.id)
            if request.user.is_authenticated:
                request.user.preferred_currency = currency
                request.user.save(update_fields=["preferred_currency"])
            messages.success(request, f"╪ز┘à ╪ز╪║┘è┘è╪▒ ╪د┘╪╣┘à┘╪ر ╪د┘┘à┘╪╢┘╪ر ╪ح┘┘ë {currency.name}.")
    
    # Redirect back to referring page or home
    next_url = request.META.get('HTTP_REFERER', 'home')
    return redirect(next_url)


def tickets(request): return render(request, "site/tickets.html")


def ticket_detail(request, pk): return render(request, "site/ticket_detail.html")



@support_required
def control_category_create_ajax(request):
    from apps.catalog.models import Category
    name = request.POST.get('name')
    if name:
        cat = Category.objects.create(name=name)
        return JsonResponse({"id": str(cat.id), "name": cat.name})
    return JsonResponse({"error": "Name required"}, status=400)



@support_required
def control_send_notification(request): return render(request, "site/control_notification_form.html")


@admin_required
def control_support_settings(request):
    settings_obj, created = SupportSettings.objects.get_or_create(id=1)
    form = SupportSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ إعدادات الدعم بنجاح.")
        return redirect("control_support_settings")
    return render(request, "site/control_support_settings.html", {"form": form})



@support_required
def control_quick_replies(request):
    replies = ChatCannedReply.objects.all().order_by("-created_at")
    return render(request, "site/control_quick_replies.html", {"replies": replies})



@support_required
def control_quick_reply_create(request):
    form = ChatCannedReplyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إضافة الرد الجاهز بنجاح.")
        return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})



@support_required
def control_quick_reply_edit(request, pk):
    reply = get_object_or_404(ChatCannedReply, pk=pk)
    form = ChatCannedReplyForm(request.POST or None, instance=reply)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم تعديل الرد الجاهز بنجاح.")
        return redirect("control_quick_replies")
    return render(request, "site/control_quick_reply_form.html", {"form": form})



@support_required
def control_quick_reply_delete(request, pk):
    reply = get_object_or_404(ChatCannedReply, pk=pk)
    reply.delete()
    messages.success(request, "تم حذف الرد الجاهز بنجاح.")
    return redirect("control_quick_replies")



def privacy_policy(request): return render(request, "site/privacy_policy.html")
