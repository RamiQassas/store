from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import User
from apps.catalog.models import Category, Product, ProductVariant
from apps.notifications.models import Notification
from apps.orders.models import Order
from apps.payments.models import DepositRequest, PaymentProvider
from apps.site.forms import LoginForm, RegisterForm, TicketForm
from apps.support.models import Ticket
from apps.wallets.models import LedgerEntry, Wallet, WalletTransaction


def home(request):
    featured_products = Product.objects.filter(is_active=True, is_featured=True).select_related("category").prefetch_related("variants")[:6]
    top_products = Product.objects.filter(is_active=True).select_related("category").prefetch_related("variants").order_by("sort_order", "name")[:8]
    categories = Category.objects.filter(is_active=True).order_by("sort_order", "name")
    stats = {
        "products": Product.objects.filter(is_active=True).count(),
        "categories": categories.count(),
        "orders": Order.objects.count(),
        "tickets": Ticket.objects.count(),
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
    category_slug = request.GET.get("category")
    categories = Category.objects.filter(is_active=True).order_by("sort_order", "name")
    products = Product.objects.filter(is_active=True).select_related("category").prefetch_related("variants")
    if category_slug:
        products = products.filter(category__slug=category_slug)
    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(category__name__icontains=query))
    return render(request, "site/catalog.html", {"categories": categories, "products": products.order_by("sort_order", "name"), "active_category": category_slug, "query": query})


def product_detail(request, slug):
    product = get_object_or_404(Product.objects.select_related("category").prefetch_related("variants", "form_fields"), slug=slug, is_active=True)
    variants = product.variants.filter(is_active=True).order_by("sort_order", "price")
    selected_variant = variants.first()
    wallet, _ = Wallet.objects.get_or_create(user=request.user) if request.user.is_authenticated else (None, False)
    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.info(request, "سجّل الدخول أولاً لإتمام الطلب.")
            return redirect("site_login")
        variant_id = request.POST.get("variant_id")
        quantity = max(int(request.POST.get("quantity", 1)), 1)
        fulfillment_data = {}
        for field in product.form_fields.all():
            if value := request.POST.get(field.key):
                fulfillment_data[field.key] = value
        if not variant_id:
            messages.error(request, "اختر باقة قبل المتابعة.")
        else:
            try:
                variant = variants.get(id=variant_id)
                total = variant.price * Decimal(quantity)
                wallet, _ = Wallet.objects.get_or_create(user=request.user)
                if wallet.available_balance < total:
                    messages.error(request, "الرصيد غير كافٍ. أضف رصيدًا أولًا.")
                else:
                    from apps.orders.services import create_order

                    order = create_order(request.user, variant.id, quantity=quantity, fulfillment_data=fulfillment_data)
                    messages.success(request, f"تم إنشاء الطلب {order.number} بنجاح.")
                    return redirect("dashboard")
            except ProductVariant.DoesNotExist:
                messages.error(request, "الباقة المختارة غير موجودة.")
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
            login(request, user)
            messages.success(request, "مرحبًا بك مرة أخرى.")
            return redirect("dashboard")
        messages.error(request, "بيانات الدخول غير صحيحة.")
    return render(request, "site/auth_login.html", {"form": form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            phone=form.cleaned_data["phone"],
        )
        login(request, user)
        messages.success(request, "تم إنشاء الحساب وربطه بمحفظة تلقائيًا.")
        return redirect("dashboard")
    return render(request, "site/auth_register.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "تم تسجيل الخروج.")
    return redirect("home")


@login_required
def dashboard(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    recent_ledger = wallet.ledger_entries.select_related("created_by")[:8]
    recent_transactions = wallet.transactions.all()[:8]
    orders = request.user.orders.select_related("invoice", "coupon").prefetch_related("items__variant__product")[:6]
    deposits = request.user.deposits.select_related("provider")[:6]
    notifications = request.user.notifications.order_by("-created_at")[:8]
    tickets = request.user.tickets.prefetch_related("messages")[:5]
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
            "deposits": deposits,
            "notifications": notifications,
            "tickets": tickets,
            "stats": stats,
        },
    )


@login_required
def wallet_page(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
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
    providers = PaymentProvider.objects.filter(is_active=True)
    if request.method == "POST":
        provider_id = request.POST.get("provider")
        amount = request.POST.get("amount")
        proof = request.FILES.get("proof_image")
        customer_note = request.POST.get("customer_note", "")
        provider = get_object_or_404(providers, id=provider_id)
        deposit = DepositRequest.objects.create(
            user=request.user,
            provider=provider,
            amount=amount,
            currency="SYP",
            proof_image=proof,
            customer_note=customer_note,
            metadata={"source": "site"},
        )
        messages.success(request, f"تم إنشاء طلب الإيداع رقم {deposit.id}.")
        return redirect("dashboard")
    return render(request, "site/deposits.html", {"providers": providers})


@login_required
def tickets(request):
    form = TicketForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ticket = Ticket.objects.create(
            user=request.user,
            subject=form.cleaned_data["subject"],
            priority=form.cleaned_data["priority"],
        )
        ticket.messages.create(sender=request.user, message=form.cleaned_data["initial_message"])
        messages.success(request, "تم إنشاء التذكرة بنجاح.")
        return redirect("dashboard_tickets")
    return render(request, "site/tickets.html", {"tickets": request.user.tickets.prefetch_related("messages"), "form": form})


@staff_member_required
def control_dashboard(request):
    recent_orders = Order.objects.select_related("customer").order_by("-created_at")[:8]
    recent_deposits = DepositRequest.objects.select_related("user", "provider").order_by("-created_at")[:8]
    recent_users = User.objects.order_by("-date_joined")[:8]
    stats = {
        "users": User.objects.count(),
        "products": Product.objects.count(),
        "orders": Order.objects.count(),
        "deposits": DepositRequest.objects.count(),
        "pending_deposits": DepositRequest.objects.filter(status=DepositRequest.Status.PENDING).count(),
        "open_tickets": Ticket.objects.filter(status=Ticket.Status.OPEN).count(),
    }
    return render(
        request,
        "site/control_dashboard.html",
        {"recent_orders": recent_orders, "recent_deposits": recent_deposits, "recent_users": recent_users, "stats": stats},
    )
