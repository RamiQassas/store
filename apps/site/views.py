import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.contrib.auth.tokens import default_token_generator
from datetime import timedelta

from apps.accounts.models import User, ModerationLog, ActivityLog
from apps.accounts.services import send_verification_email
from apps.catalog.models import Category, Product, ProductVariant
from apps.common.models import Currency
from apps.notifications.models import Notification
from apps.notifications.services import notify_user
from apps.orders.models import Order, OrderItem, OrderLog, Coupon
from apps.payments.models import DepositRequest, PaymentMethod, WithdrawalRequest
from apps.site.forms import LoginForm, RegisterForm, TicketForm, PaymentMethodForm, CurrencyForm, ModerateUserForm, ProductForm, VariantForm
from apps.support.models import ChatRoom, ChatMessage, ChatCannedReply
from apps.wallets.models import LedgerEntry, Wallet, WalletTransaction
from apps.wallets.services import get_or_create_wallet


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
    return render(
        request,
        "site/home.html",
        {
            "featured_products": featured_products,
            "top_products": top_products,
            "categories": categories,
            "stats": stats,
        },
    )


def catalog(request):
    category_id = request.GET.get("category")
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "newest")
    
    categories = Category.objects.filter(is_active=True).annotate(product_count=Count('products', filter=Q(products__is_active=True))).order_by("sort_order", "name")
    products = Product.objects.filter(is_active=True).select_related("category").prefetch_related("variants")
    
    if category_id:
        products = products.filter(category_id=category_id)
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(category__name__icontains=query))
    
    # Sorting Logic
    if sort == "price_low":
        products = products.order_by("variants__price")
    elif sort == "price_high":
        products = products.order_by("-variants__price")
    elif sort == "popular":
        products = products.annotate(order_count=Count('orderitem')).order_by("-order_count")
    else: # newest
        products = products.order_by("-created_at")
        
    return render(request, "site/catalog.html", {
        "categories": categories, 
        "products": products.distinct(), 
        "active_category": category_id, 
        "query": query,
        "sort": sort
    })


def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related("category").prefetch_related("variants"), pk=pk, is_active=True)
    variants = product.variants.filter(is_active=True).order_by("sort_order", "price")
    selected_variant = variants.first()
    wallet = get_or_create_wallet(request.user) if request.user.is_authenticated else None
    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.info(request, "سجّل الدخول أولاً لإتمام الطلب.")
            return redirect("site_login")
        
        # Check if email is verified
        if not request.user.email_verified:
            messages.error(request, "يرجى تفعيل بريدك الإلكتروني أولاً لتتمكن من الشراء.")
            return redirect("dashboard")

        # Check if user is restricted from purchases
        if request.user.status != User.Status.ACTIVE and request.user.restriction_purchases:
            messages.error(request, "حسابك مقيد من عمليات الشراء. يرجى التواصل مع الدعم.")
            return redirect("dashboard")

        variant_id = request.POST.get("variant_id")
        quantity = max(int(request.POST.get("quantity", 1)), 1)
        
        # New Dynamic Form Logic
        fulfillment_data = {}
        schema = product.form_schema or {}
        fields = schema.get("fields", [])
        for field in fields:
            name = field.get("name") or field.get("label")
            if value := request.POST.get(f"custom_{name}"):
                fulfillment_data[name] = value

        if not variant_id:
            messages.error(request, "اختر باقة قبل المتابعة.")
        else:
            try:
                variant = variants.get(id=variant_id)
                total = variant.price * Decimal(quantity)
                wallet = get_or_create_wallet(request.user)
                
                from apps.orders.services import create_order
                from apps.wallets.services import WalletError

                try:
                    order = create_order(request.user, variant.id, quantity=quantity, fulfillment_data=fulfillment_data)
                    messages.success(request, f"تم إنشاء الطلب {order.number} بنجاح. رصيدك الحالي: {request.user.wallet.available_balance} SYP")

                    notify_user(
                        user=request.user,
                        title="تم إنشاء الطلب بنجاح",
                        body=f"طلبك رقم {order.number} قيد المعالجة الآن.",
                        action_url="/dashboard/",
                        priority="high"
                    )
                    
                    ActivityLog.objects.create(
                        user=request.user,
                        action="Order Created",
                        description=f"Created order {order.number} for {total} SYP",
                        metadata={"order_id": str(order.id)}
                    )
                    return redirect("dashboard")
                except WalletError as e:
                    messages.error(request, f"فشل الطلب: {str(e)}")
                except ValueError as e:
                    messages.error(request, str(e))
                except Exception as e:
                    messages.error(request, f"حدث خطأ غير متوقع: {str(e)}")

            except ProductVariant.DoesNotExist:
                messages.error(request, "الباقة المختارة غير متوفرة.")
    return render(
        request,
        "site/product_detail.html",
        {
            "product": product,
            "variants": variants,
            "selected_variant": selected_variant,
        },
    )


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(username=form.cleaned_data["email"], password=form.cleaned_data["password"])
        if user:
            if not user.is_account_active:
                messages.error(request, f"هذا الحساب معطل أو موقوف. السبب: {user.suspension_reason or 'غير محدد'}")
                return render(request, "site/auth_login.html", {"form": form})
            
            login(request, user)
            messages.success(request, "مرحبًا بك مرة أخرى.")
            
            ActivityLog.objects.create(
                user=user,
                action="Login",
                description="User logged into the platform",
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            if not user.email_verified:
                messages.warning(request, "حسابك غير مفعل بعد. يرجى تفعيل البريد الإلكتروني للوصول لكافة الميزات.")
            
            return redirect("dashboard")
        messages.error(request, "بيانات الدخول غير صحيحة.")
    return render(request, "site/auth_login.html", {"form": form})


def register_view(request):
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
            
            ActivityLog.objects.create(
                user=user,
                action="Register",
                description="New account registered"
            )
            
            success = send_verification_email(request, user)
            
            login(request, user)
            if success:
                messages.success(request, "تم إنشاء الحساب بنجاح. يرجى تفعيل بريدك الإلكتروني.")
            else:
                messages.warning(request, "تم إنشاء الحساب، ولكن تعذر إرسال بريد التفعيل حالياً. يمكنك إعادة المحاولة من لوحة التحكم.")
            return redirect("dashboard")
            
    return render(request, "site/auth_register.html", {"form": form})


def logout_view(request):
    if request.user.is_authenticated:
        ActivityLog.objects.create(
            user=request.user,
            action="Logout",
            description="User logged out"
        )
    logout(request)
    messages.info(request, "تم تسجيل الخروج.")
    return redirect("home")


def email_verify(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None:
        try:
            token_obj = EmailVerificationToken.objects.get(user=user, token=token)
            if token_obj.is_used:
                messages.warning(request, "رابط التفعيل هذا تم استخدامه مسبقاً.")
                return redirect("site_login")
            
            if token_obj.is_expired():
                messages.error(request, "رابط التفعيل انتهت صلاحيته. يمكنك طلب رابط جديد.")
                return render(request, "site/email_verify_expired.html", {"user_id": user.id})
                
            with transaction.atomic():
                user.email_verified = True
                user.save(update_fields=["email_verified"])
                token_obj.is_used = True
                token_obj.save(update_fields=["is_used"])
                
                ActivityLog.objects.create(user=user, action="Email Verified", description="User verified their email address")
                
            messages.success(request, "تم تفعيل بريدك الإلكتروني بنجاح!")
            if request.user.is_authenticated:
                return redirect("dashboard")
            return redirect("site_login")
        except EmailVerificationToken.DoesNotExist:
            messages.error(request, "رابط التفعيل غير صالح.")
            return redirect("home")
    else:
        messages.error(request, "المستخدم غير موجود.")
        return redirect("home")


@login_required
def resend_verification(request):
    if request.user.email_verified:
        messages.info(request, "بريدك الإلكتروني مفعل بالفعل.")
        return redirect("dashboard")

    # Cooldown check: 5 minutes
    last_token = EmailVerificationToken.objects.filter(user=request.user).order_by("-created_at").first()
    if last_token and (timezone.now() - last_token.created_at) < timedelta(minutes=5):
        messages.warning(request, "يرجى الانتظار قليلاً قبل طلب رابط تفعيل جديد.")
        return redirect("dashboard")

    success = send_verification_email(request, request.user)
    if success:
        messages.success(request, "تم إعادة إرسال رابط التفعيل إلى بريدك الإلكتروني بنجاح.")
    else:
        messages.error(request, "تعذر إرسال البريد حالياً. يرجى المحاولة مرة أخرى لاحقاً أو التواصل مع الدعم.")
    return redirect("dashboard")


@login_required
def dashboard(request):
    if not request.user.email_verified:
        messages.warning(request, "حسابك غير مفعل. يرجى تفعيل البريد الإلكتروني.")
        
    if request.user.status != User.Status.ACTIVE:
        messages.warning(request, f"تنبيه: حسابك في حالة ({request.user.get_status_display()}). بعض الميزات قد تكون مقيدة.")
    
    wallet = get_or_create_wallet(request.user)
    recent_ledger = wallet.ledger_entries.select_related("created_by")[:8]
    recent_transactions = wallet.transactions.all()[:8]
    orders = request.user.orders.select_related("invoice", "coupon").prefetch_related("items__variant__product")[:6]
    deposits_list = request.user.deposits.select_related("payment_method", "currency")[:6]
    notifications_list = request.user.notifications.all()[:8]
    tickets_list = request.user.tickets.all()[:5]
    stats = {
        "orders": request.user.orders.count(),
        "deposits": request.user.deposits.count(),
        "tickets": request.user.tickets.count(),
        "notifications": request.user.notifications.filter(is_read=False).count(),
    }
    return render(
        request,
        "site/dashboard.html",
        {
            "wallet": wallet,
            "recent_ledger": recent_ledger,
            "recent_transactions": recent_transactions,
            "orders": orders,
            "deposits": deposits_list,
            "notifications": notifications_list,
            "tickets": tickets_list,
            "stats": stats,
        },
    )


@login_required
def wallet_page(request):
    wallet = get_or_create_wallet(request.user)
    return render(
        request,
        "site/wallet.html",
        {
            "wallet": wallet,
            "ledger_entries": wallet.ledger_entries.select_related("created_by")[:20],
            "transactions": wallet.transactions.all()[:20],
        },
    )


@login_required
def deposits(request):
    if not request.user.email_verified:
        messages.error(request, "يرجى تفعيل بريدك الإلكتروني أولاً لتتمكن من الإيداع.")
        return redirect("dashboard")

    if request.user.status != User.Status.ACTIVE and request.user.restriction_deposits:
        messages.error(request, "حسابك مقيد من عمليات الإيداع. يرجى التواصل مع الدعم.")
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
        
        if amount < method.deposit_min_amount or amount > method.deposit_max_amount:
            messages.error(request, f"المبلغ يجب أن يكون بين {method.deposit_min_amount} و {method.deposit_max_amount}.")
        elif method.is_maintenance_mode:
            messages.error(request, "وسيلة الدفع هذه حالياً في وضع الصيانة.")
        elif not method.supported_currencies.filter(id=currency.id).exists():
             messages.error(request, "هذه العملة غير مدعومة لوسيلة الدفع المختارة.")
        else:
            # Handle Dynamic Fields
            dynamic_data = {}
            for key, value in request.POST.items():
                if key.startswith("custom_"):
                    field_name = key.replace("custom_", "")
                    dynamic_data[field_name] = value

            wallet = get_or_create_wallet(request.user)
            base_amount = currency.to_base(amount, "deposit")
            wallet_amount = wallet.currency.from_base(base_amount, "deposit")

            with transaction.atomic():
                deposit = DepositRequest.objects.create(
                    user=request.user,
                    payment_method=method,
                    amount=amount,
                    wallet_amount=wallet_amount,
                    currency=currency,
                    transaction_id=dynamic_data.get("ref_id", ""),
                    proof_image=proof,
                    metadata={"dynamic_fields": dynamic_data, "source": "multi_step_ui"},
                    status=DepositRequest.Status.PENDING
                )
                from apps.wallets.services import track_pending_deposit
                track_pending_deposit(
                    wallet_id=wallet.id,
                    amount=wallet_amount,
                    reference=f"deposit:{deposit.id}",
                    description=f"إيداع معلق عبر {method.name}",
                    created_by=request.user,
                    source="user_deposit",
                    reason="Verification pending"
                )
                
                ActivityLog.objects.create(
                    user=request.user,
                    action="Deposit Requested",
                    description=f"Requested deposit of {amount} {currency.code} via {method.name}",
                    metadata={"deposit_id": str(deposit.id)}
                )
                
                messages.success(request, f"تم استلام طلب الإيداع وهو قيد المراجعة حالياً.")
                return redirect("dashboard")
            
    return render(request, "site/deposits.html", {"payment_methods": methods})


@login_required
def tickets(request):
    if request.method == "POST":
        subject = request.POST.get("subject")
        message = request.POST.get("message")
        priority = request.POST.get("priority", "normal")
        attachment = request.FILES.get("attachment")
        
        if not subject or not message:
            messages.error(request, "يرجى إدخال العنوان والرسالة.")
        else:
            with transaction.atomic():
                ticket = Ticket.objects.create(
                    user=request.user,
                    subject=subject,
                    priority=priority,
                    is_read_by_user=True,
                    is_read_by_staff=False
                )
                TicketMessage.objects.create(
                    ticket=ticket,
                    sender=request.user,
                    message=message,
                    attachment=attachment
                )
                messages.success(request, "تم إنشاء التذكرة بنجاح.")
                return redirect("ticket_detail", pk=ticket.pk)
                
    tickets_list = request.user.tickets.all()
    return render(request, "site/tickets.html", {"tickets": tickets_list})


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related("user"), pk=pk)
    if not request.user.is_staff and ticket.user != request.user:
        raise Http404
        
    if request.method == "POST":
        message_text = request.POST.get("message")
        attachment = request.FILES.get("attachment")
        
        if message_text:
            with transaction.atomic():
                TicketMessage.objects.create(
                    ticket=ticket,
                    sender=request.user,
                    message=message_text,
                    attachment=attachment,
                    is_staff_reply=request.user.is_staff
                )
                ticket.last_reply_at = timezone.now()
                if request.user.is_staff:
                    ticket.status = Ticket.Status.ANSWERED
                    ticket.is_read_by_user = False
                    ticket.is_read_by_staff = True
                    
                    notify_user(
                        user=ticket.user,
                        title="رد جديد على تذكرة الدعم",
                        body=f"لقد قام فريق الدعم بالرد على تذكرتك: {ticket.subject}",
                        action_url=f"/dashboard/tickets/{ticket.pk}/",
                        priority="high"
                    )
                else:
                    ticket.status = Ticket.Status.OPEN
                    ticket.is_read_by_user = True
                    ticket.is_read_by_staff = False
                ticket.save()
                
            return redirect("ticket_detail", pk=ticket.pk)

    if not request.user.is_staff:
        ticket.is_read_by_user = True
        ticket.save(update_fields=["is_read_by_user"])
    else:
        ticket.is_read_by_staff = True
        ticket.save(update_fields=["is_read_by_staff"])
        
    messages_list = ticket.messages.select_related("sender").all()
    canned_replies = CannedReply.objects.filter(is_active=True) if request.user.is_staff else None
    
    template = "site/control_ticket_detail.html" if request.user.is_staff else "site/ticket_detail.html"
    return render(request, template, {
        "ticket": ticket, 
        "messages_list": messages_list,
        "canned_replies": canned_replies
    })


from apps.support.models import ChatRoom, ChatMessage, ChatCannedReply

@staff_member_required
def control_dashboard(request):
    recent_orders = Order.objects.select_related("customer").order_by("-created_at")[:8]
    recent_deposits = DepositRequest.objects.select_related("user", "payment_method", "currency").order_by("-created_at")[:8]
    recent_users = User.objects.select_related("wallet").order_by("-date_joined")[:8]
    
    from apps.support.models import ChatRoom
    
    stats = {
        "users": User.objects.count(),
        "products": Product.objects.count(),
        "orders": Order.objects.count(),
        "deposits": DepositRequest.objects.count(),
        "pending_deposits": DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).count(),
        "pending_withdrawals": WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PENDING).count(),
        "open_tickets": ChatRoom.objects.exclude(status=ChatRoom.Status.CLOSED).count(),
    }
    return render(
        request,
        "site/control_dashboard.html",
        {"recent_orders": recent_orders, "recent_deposits": recent_deposits, "recent_users": recent_users, "stats": stats},
    )


@permission_required("payments.view_depositrequest", raise_exception=True)
def control_deposits(request):
    status_filter = request.GET.get("status")
    query = request.GET.get("q", "").strip()
    
    deposits = DepositRequest.objects.select_related("user", "payment_method", "currency").all()
    
    if status_filter:
        deposits = deposits.filter(status=status_filter)
    if query:
        deposits = deposits.filter(Q(transaction_id__icontains=query) | Q(user__email__icontains=query))
        
    return render(request, "site/control_deposits.html", {
        "deposits": deposits,
        "current_status": status_filter,
        "query": query
    })


@staff_member_required
def payment_methods_list(request):
    methods = PaymentMethod.objects.all().order_by("display_order", "name")
    return render(request, "site/payment_methods_list.html", {"methods": methods})


@staff_member_required
def payment_method_create(request):
    form = PaymentMethodForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تمت إضافة وسيلة الدفع بنجاح.")
        return redirect("payment_methods_list")
    return render(request, "site/payment_method_builder.html", {"form": form, "title": "إضافة وسيلة دفع جديدة"})


@staff_member_required
def payment_method_edit(request, pk):
    method = get_object_or_404(PaymentMethod, pk=pk)
    form = PaymentMethodForm(request.POST or None, request.FILES or None, instance=method)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم تحديث وسيلة الدفع بنجاح.")
        return redirect("payment_methods_list")
    return render(request, "site/payment_method_builder.html", {"form": form, "title": f"تعديل وسيلة: {method.name}", "method": method})


@staff_member_required
def currencies_list(request):
    currencies = Currency.objects.all().order_by("display_order", "code")
    return render(request, "site/currencies_list.html", {"currencies": currencies})


@staff_member_required
def currency_create(request):
    form = CurrencyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تمت إضافة العملة بنجاح.")
        return redirect("currencies_list")
    return render(request, "site/currency_form.html", {"form": form, "title": "إضافة عملة جديدة"})


@staff_member_required
def currency_edit(request, pk):
    currency = get_object_or_404(Currency, pk=pk)
    form = CurrencyForm(request.POST or None, instance=currency)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم تحديث بيانات العملة بنجاح.")
        return redirect("currencies_list")
    return render(request, "site/currency_form.html", {"form": form, "title": "تعديل العملة", "currency": currency})


@login_required
def withdrawals(request):
    if not request.user.email_verified:
        messages.error(request, "يرجى تفعيل بريدك الإلكتروني أولاً لتتمكن من السحب.")
        return redirect("dashboard")

    if request.user.status != User.Status.ACTIVE and request.user.restriction_withdrawals:
        messages.error(request, "حسابك مقيد من عمليات السحب. يرجى التواصل مع الدعم.")
        return redirect("dashboard")

    methods = PaymentMethod.objects.filter(is_active=True, can_withdraw=True).prefetch_related("supported_currencies")
    if request.method == "POST":
        method_id = request.POST.get("payment_method")
        currency_id = request.POST.get("currency")
        amount = Decimal(request.POST.get("amount", "0"))
        
        method = get_object_or_404(methods, id=method_id)
        currency = get_object_or_404(Currency, id=currency_id)
        wallet = get_or_create_wallet(request.user)
        
        if amount < method.withdrawal_min_amount or amount > method.withdrawal_max_amount:
            messages.error(request, f"المبلغ يجب أن يكون بين {method.withdrawal_min_amount} و {method.withdrawal_max_amount}.")
        elif method.is_maintenance_mode:
            messages.error(request, "وسيلة السحب هذه حالياً في وضع الصيانة.")
        elif not method.supported_currencies.filter(id=currency.id).exists():
             messages.error(request, "هذه العملة غير مدعومة لوسيلة السحب المختارة.")
        else:
            base_amount = currency.to_base(amount, "withdrawal")
            wallet_amount = wallet.currency.from_base(base_amount, "withdrawal")

            if wallet.available_balance < wallet_amount:
                messages.error(request, "الرصيد غير كافٍ لإجراء عملية السحب بعد التحويل.")
                return redirect("dashboard_withdrawals")

            # Handle Dynamic Fields
            dynamic_data = {}
            for key, value in request.POST.items():
                if key.startswith("custom_"):
                    field_name = key.replace("custom_", "")
                    dynamic_data[field_name] = value

            with transaction.atomic():
                withdrawal = WithdrawalRequest.objects.create(
                    user=request.user,
                    payment_method=method,
                    amount=amount,
                    wallet_amount=wallet_amount,
                    currency=currency,
                    payout_details={"address": dynamic_data.get("address", ""), "dynamic": dynamic_data},
                    metadata={"dynamic_fields": dynamic_data, "source": "multi_step_ui"},
                    status=WithdrawalRequest.Status.PENDING
                )
                from apps.wallets.services import freeze_funds
                freeze_funds(
                    wallet_id=wallet.id,
                    amount=wallet_amount,
                    reference=f"with:{withdrawal.id}",
                    description=f"سحب رصيد معلق عبر {method.name}",
                    created_by=request.user,
                    source="user_withdrawal",
                    reason="Verification pending"
                )
                
                ActivityLog.objects.create(
                    user=request.user,
                    action="Withdrawal Request",
                    description=f"Requested withdrawal of {amount} {currency.code} via {method.name}",
                    metadata={"withdrawal_id": str(withdrawal.id)}
                )
                
                messages.success(request, f"تم استلام طلب السحب بنجاح وهو قيد المراجعة حالياً.")
                return redirect("dashboard")

    recent_withdrawals = WithdrawalRequest.objects.filter(user=request.user).order_by("-created_at")[:5]
    return render(request, "site/withdrawals.html", {
        "payment_methods": methods,
        "recent_withdrawals": recent_withdrawals
    })


@staff_member_required
def control_withdrawals(request):
    withdrawals = WithdrawalRequest.objects.select_related("user", "payment_method", "currency").order_by("-created_at")
    return render(request, "site/control_withdrawals.html", {"withdrawals": withdrawals})


@permission_required("accounts.view_user", raise_exception=True)
def control_users_list(request):
    query = request.GET.get("q", "").strip()
    users = User.objects.select_related("wallet").order_by("-date_joined")
    
    if request.method == "POST" and request.POST.get("action") == "bulk_tier":
        target_tier = request.POST.get("target_tier")
        user_ids = request.POST.getlist("user_ids")
        if target_tier in User.Tier.values and user_ids:
            with transaction.atomic():
                updated_count = User.objects.filter(id__in=user_ids).update(tier=target_tier)
                messages.success(request, f"تم تحديث فئة {updated_count} مستخدم بنجاح.")
                
                # Audit log for bulk action
                from apps.common.services import log_system_action
                log_system_action(
                    actor=request.user,
                    action_type="BULK_TIER_UPDATE",
                    description=f"Bulk updated {updated_count} users to {target_tier}",
                    ip_address=request.META.get('REMOTE_ADDR'),
                    metadata={"user_ids": user_ids, "new_tier": target_tier}
                )
            return redirect("control_users_list")

    if query:
        users = users.filter(Q(email__icontains=query) | Q(phone__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
    
    return render(request, "site/control_users_list.html", {
        "users": users, 
        "query": query,
        "tiers": User.Tier.choices
    })


@staff_member_required
def control_user_moderate(request, public_uuid):
    user_to_moderate = get_object_or_404(User.objects.select_related("wallet"), public_uuid=public_uuid)
    previous_state = {
        "status": user_to_moderate.status,
        "tier": user_to_moderate.tier,
        "restriction_withdrawals": user_to_moderate.restriction_withdrawals,
        "restriction_deposits": user_to_moderate.restriction_deposits,
        "restriction_purchases": user_to_moderate.restriction_purchases,
    }

    form = ModerateUserForm(request.POST or None, instance=user_to_moderate)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user_to_moderate = form.save()
            new_state = {
                "status": user_to_moderate.status,
                "tier": user_to_moderate.tier,
                "restriction_withdrawals": user_to_moderate.restriction_withdrawals,
                "restriction_deposits": user_to_moderate.restriction_deposits,
                "restriction_purchases": user_to_moderate.restriction_purchases,
            }

            # Local moderation log
            ModerationLog.objects.create(
                user=user_to_moderate,
                moderator=request.user,
                action="Account Moderation Update",
                previous_state=previous_state,
                new_state=new_state,
                reason=user_to_moderate.suspension_reason,
                internal_notes=user_to_moderate.admin_notes
            )

            # Universal System Audit Log
            from apps.common.services import log_system_action
            log_system_action(
                actor=request.user,
                action_type="USER_MODERATION",
                target=user_to_moderate,
                description=f"Updated account settings for {user_to_moderate.email}",
                before_state=previous_state,
                after_state=new_state,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                reason=user_to_moderate.suspension_reason
            )

            messages.success(request, f"تم تحديث حالة حساب {user_to_moderate.email} بنجاح.")
            return redirect("control_users_list")

    # Fetch both logs for comprehensive view
    from apps.common.models import SystemAuditLog
    from django.contrib.contenttypes.models import ContentType

    user_ct = ContentType.objects.get_for_model(User)
    audit_logs = SystemAuditLog.objects.filter(content_type=user_ct, object_id=str(user_to_moderate.id))
    moderation_logs = user_to_moderate.moderation_history.select_related("moderator").all()

    return render(request, "site/control_user_moderate.html", {
        "form": form,
        "user_to_moderate": user_to_moderate,
        "moderation_logs": moderation_logs,
        "audit_logs": audit_logs
    })

from django.http import JsonResponse

@staff_member_required
def control_category_create_ajax(request):
    if request.method == "POST":
        name = request.POST.get("name")
        if name:
            category = Category.objects.create(name=name)
            return JsonResponse({"status": "success", "id": str(category.id), "name": category.name})
    return JsonResponse({"status": "error", "message": "Invalid request"}, status=400)

@permission_required("catalog.view_product", raise_exception=True)
def control_products_list(request):
    query = request.GET.get("q", "").strip()
    products = Product.objects.select_related("category").prefetch_related("variants").order_by("sort_order", "name")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(slug__icontains=query) | Q(category__name__icontains=query))
    return render(request, "site/control_products_list.html", {"products": products, "query": query})


@staff_member_required
def control_product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    product = form.save()
                    
                    # Handle Packages (Variants)
                    variants_data = json.loads(request.POST.get("variants_json", "[]"))
                    for v_data in variants_data:
                        ProductVariant.objects.create(
                            product=product,
                            name=v_data.get("name"),
                            sku=v_data.get("sku") or f"{product.id[:8]}-{v_data.get('name')[:10]}",
                            price=Decimal(v_data.get("price", 0)),
                            wholesale_price=Decimal(v_data.get("wholesale_price", 0)),
                            vip_price=Decimal(v_data.get("vip_price", 0)),
                            cost=Decimal(v_data.get("cost", 0)),
                            sort_order=int(v_data.get("sort_order", 0)),
                            is_active=True
                        )
                    
                    messages.success(request, f"تم إنشاء المنتج {product.name} بنجاح.")
                    return redirect("control_product_edit", pk=product.pk)
            except Exception as e:
                messages.error(request, f"حدث خطأ أثناء الحفظ: {str(e)}")
    else:
        form = ProductForm()
    
    return render(request, "site/control_product_builder.html", {
        "form": form,
        "title": "إنشاء منتج جديد",
        "is_create": True
    })


@staff_member_required
def control_product_edit(request, pk):
    product = get_object_or_404(Product.objects.prefetch_related("variants"), pk=pk)
    
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            try:
                with transaction.atomic():
                    product = form.save()
                    
                    # Handle Packages (Variants) - Delete and Re-create for simplicity in builder
                    # In production with high traffic, a sync logic would be better
                    variants_data = json.loads(request.POST.get("variants_json", "[]"))
                    
                    # Keep track of existing IDs to not break orders if possible, 
                    # but for this visual builder requirements, we'll sync by name/sku or just refresh.
                    # Let's do a basic sync.
                    incoming_skus = [v.get("sku") for v in variants_data if v.get("sku")]
                    product.variants.exclude(sku__in=incoming_skus).delete()
                    
                    for v_data in variants_data:
                        ProductVariant.objects.update_or_create(
                            product=product,
                            sku=v_data.get("sku"),
                            defaults={
                                "name": v_data.get("name"),
                                "price": Decimal(v_data.get("price", 0)),
                                "wholesale_price": Decimal(v_data.get("wholesale_price", 0)),
                                "vip_price": Decimal(v_data.get("vip_price", 0)),
                                "cost": Decimal(v_data.get("cost", 0)),
                                "sort_order": int(v_data.get("sort_order", 0)),
                                "is_active": v_data.get("is_active", True)
                            }
                        )
                    
                    messages.success(request, "تم تحديث بيانات المنتج بنجاح.")
                    return redirect("control_products_list")
            except Exception as e:
                messages.error(request, f"خطأ في معالجة البيانات: {str(e)}")
    else:
        form = ProductForm(instance=product)
    
    variants = product.variants.all().order_by("sort_order")
    # Pass variants to JS as JSON
    variants_list = []
    for v in variants:
        variants_list.append({
            "name": v.name,
            "sku": v.sku,
            "price": str(v.price),
            "wholesale_price": str(v.wholesale_price),
            "vip_price": str(v.vip_price),
            "cost": str(v.cost),
            "sort_order": v.sort_order,
            "is_active": v.is_active
        })

    return render(request, "site/control_product_builder.html", {
        "form": form, 
        "title": f"تعديل منتج: {product.name}", 
        "product": product,
        "variants_json_data": json.dumps(variants_list)
    })


@staff_member_required
def control_variant_create(request, product_pk):
    product = get_object_or_404(Product, pk=product_pk)
    form = VariantForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        variant = form.save(commit=False)
        variant.product = product
        variant.save()
        messages.success(request, "تمت إضافة الباقة بنجاح.")
        return redirect("control_product_edit", pk=product.pk)
    return render(request, "site/control_variant_form.html", {"form": form, "product": product, "title": "إضافة باقة جديدة"})


@staff_member_required
def control_variant_edit(request, pk):
    variant = get_object_or_404(ProductVariant, pk=pk)
    form = VariantForm(request.POST or None, instance=variant)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم تحديث الباقة بنجاح.")
        return redirect("control_product_edit", pk=variant.product.pk)
    return render(request, "site/control_variant_form.html", {"form": form, "product": variant.product, "title": "تعديل باقة"})


@staff_member_required
def control_tickets_list(request):
    status_filter = request.GET.get("status")
    tickets_qs = Ticket.objects.select_related("user").all()
    if status_filter:
        tickets_qs = tickets_qs.filter(status=status_filter)
    
    return render(request, "site/control_tickets_list.html", {"tickets": tickets_qs, "current_status": status_filter})


@staff_member_required
def control_orders_list(request):
    status_filter = request.GET.get("status")
    query = request.GET.get("q", "").strip()
    orders = Order.objects.select_related("customer", "invoice").prefetch_related("items__variant__product").all()
    
    if status_filter:
        orders = orders.filter(status=status_filter)
    if query:
        orders = orders.filter(Q(number__icontains=query) | Q(customer__email__icontains=query))
        
    return render(request, "site/control_orders_list.html", {"orders": orders, "current_status": status_filter, "query": query})


@staff_member_required
def control_order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer", "invoice").prefetch_related("items__variant__product", "logs__created_by"), pk=pk)
    
    if request.method == "POST":
        new_status = request.POST.get("status")
        admin_note = request.POST.get("admin_note", "")
        
        if new_status in Order.Status.values:
            with transaction.atomic():
                order.status = new_status
                if admin_note:
                    order.admin_note = admin_note
                order.save()
                OrderLog.objects.create(order=order, status=new_status, note=f"Status updated to {new_status}. {admin_note}", created_by=request.user)
                
                # Notifications
                if new_status == Order.Status.DELIVERED:
                    notify_user(
                        user=order.customer,
                        title="تم تسليم طلبك",
                        body=f"طلبك رقم {order.number} متاح الآن للتنزيل أو الاستخدام.",
                        action_url="/dashboard/",
                        priority="high"
                    )
                elif new_status == Order.Status.COMPLETED:
                    notify_user(
                        user=order.customer,
                        title="تم اكتمال الطلب",
                        body=f"تم إغلاق طلبك رقم {order.number} بنجاح. شكراً لثقتك بنا.",
                        priority="normal"
                    )

                # Handle refund logic if status is REFUNDED
                if new_status == Order.Status.REFUNDED:
                    wallet = get_or_create_wallet(order.customer)
                    from apps.wallets.services import credit_wallet
                    credit_wallet(wallet.id, order.total_amount, reference=f"refund:{order.id}", description=f"استرداد ثمن الطلب {order.number}", created_by=request.user)
                    
                    notify_user(
                        user=order.customer,
                        title="تم استرداد مبلغ الطلب",
                        body=f"تمت إعادة {order.total_amount} {wallet.currency.code} إلى محفظتك للطلب رقم {order.number}.",
                        action_url="/dashboard/wallet/",
                        priority="high"
                    )
                
            messages.success(request, f"تم تحديث الطلب {order.number} بنجاح.")
            return redirect("control_order_detail", pk=order.pk)

    return render(request, "site/control_order_detail.html", {"order": order})


@permission_required("wallets.view_wallet", raise_exception=True)
def control_wallets_list(request):
    query = request.GET.get("q", "").strip()
    wallets = Wallet.objects.select_related("user", "currency").all()
    if query:
        wallets = wallets.filter(Q(user__email__icontains=query) | Q(user__phone__icontains=query))
    return render(request, "site/control_wallets_list.html", {"wallets": wallets, "query": query})


@staff_member_required
@permission_required("notifications.add_notification", raise_exception=True)
def control_send_notification(request):
    if request.method == "POST":
        target_type = request.POST.get("target_type") # all, single, tier
        title = request.POST.get("title")
        body = request.POST.get("body")
        action_url = request.POST.get("action_url")
        image_url = request.POST.get("image_url")
        
        users = User.objects.none()
        if target_type == "all":
            users = User.objects.filter(is_active=True)
        elif target_type == "tier":
            tier = request.POST.get("tier")
            users = User.objects.filter(tier=tier, is_active=True)
        elif target_type == "single":
            user_email = request.POST.get("user_email")
            users = User.objects.filter(email=user_email, is_active=True)
            
        from apps.notifications.services import notify_bulk
        notify_bulk(users, title, body, action_url=action_url, image_url=image_url)
        
        messages.success(request, f"تم إرسال الإشعار لـ {users.count()} مستخدم بنجاح.")
        return redirect("control_reports") # For now, or create a dedicated panel
    
    return render(request, "site/control_notification_form.html", {
        "tiers": User.Tier.choices
    })

@staff_member_required
def control_reports(request):
    today = timezone.now().date()
    last_30_days = today - timedelta(days=30)
    
    # Revenue data
    revenue_30 = Order.objects.filter(
        status__in=[Order.Status.COMPLETED, Order.Status.DELIVERED], 
        created_at__date__gte=last_30_days
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Deposits/Withdrawals
    deposits_30 = DepositRequest.objects.filter(status=DepositRequest.Status.COMPLETED, created_at__date__gte=last_30_days).aggregate(total=Sum('amount'))['total'] or 0
    withdrawals_30 = WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.COMPLETED, created_at__date__gte=last_30_days).aggregate(total=Sum('amount'))['total'] or 0
    
    # Growth
    users_30 = User.objects.filter(date_joined__date__gte=last_30_days).count()
    orders_30 = Order.objects.filter(created_at__date__gte=last_30_days).count()
    
    # Wallet Balances System-wide
    wallet_stats = Wallet.objects.aggregate(
        total_available=Sum('available_balance'),
        total_frozen=Sum('frozen_balance'),
        total_held=Sum('held_balance')
    )
    
    # Top Products
    top_products = Product.objects.filter(is_active=True).annotate(
        order_count=Count('variants__order_items')
    ).order_by('-order_count')[:5]
    
    stats = {
        "revenue_30": revenue_30,
        "deposits_30": deposits_30,
        "withdrawals_30": withdrawals_30,
        "users_30": users_30,
        "orders_30": orders_30,
        "total_users": User.objects.count(),
        "total_orders": Order.objects.count(),
        "wallet_stats": wallet_stats,
        "top_products": top_products
    }
    
    return render(request, "site/control_reports.html", {"stats": stats})


def privacy_policy(request):
    return render(request, "site/privacy_policy.html")

def terms_of_service(request):
    return render(request, "site/terms_of_service.html")

def refund_policy(request):
    return render(request, "site/refund_policy.html")

def contact_page(request):
    return render(request, "site/contact.html")


def service_worker(request):
    """Serves the service worker from the root for correct scoping."""
    from django.http import HttpResponse
    from django.conf import settings
    import os
    
    sw_path = os.path.join(settings.BASE_DIR, 'apps', 'site', 'static', 'site', 'js', 'sw.js')
    with open(sw_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return HttpResponse(content, content_type='application/javascript')
