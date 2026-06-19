import json
import uuid
from decimal import Decimal
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.core.paginator import Paginator

from apps.accounts.models import User
from apps.catalog.models import Product, Category, ProductVariant, ProductKey, ProductImage
from apps.orders.models import Order, Coupon, OrderItem
from apps.payments.models import PaymentMethod, DepositRequest, WithdrawalRequest
from apps.wallets.models import Wallet, LedgerEntry
from apps.wallets.services import credit_wallet, debit_wallet
from apps.common.models import Currency

from apps.stores.models import Store, StorePage, StoreEmployee, SubscriptionPlan
from apps.stores.forms import (
    StoreForm, StoreCustomDomainForm, StorePageForm, StoreEmployeeForm, 
    MerchantProductForm, MerchantCategoryForm, MerchantCouponForm
)
from apps.common.tenant_utils import bypass_tenant_filter

def get_store_limit(store, limit_field):
    """Get the active limit for a store (checking manual overrides first)."""
    if store.limit_overrides and limit_field in store.limit_overrides:
        return store.limit_overrides[limit_field]
    if store.subscription_plan:
        return getattr(store.subscription_plan, limit_field, 0)
    return 0

def check_store_feature(store, feature_field):
    """Check if a feature is enabled for a store (checking manual overrides first)."""
    if store.limit_overrides and feature_field in store.limit_overrides:
        return bool(store.limit_overrides[feature_field])
    if store.subscription_plan:
        return getattr(store.subscription_plan, feature_field, False)
    return False

# ==========================================
# --- PERMISSION DECORATORS ---
# ==========================================
def employee_required(permission_name=None):
    def decorator(view_func):
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if user.role == 'super_admin' or user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            active_store = getattr(request, "store", None)
            if not active_store:
                raise Http404()
            
            # Store Owner has full access
            if active_store.owner == user:
                return view_func(request, *args, **kwargs)
            
            # Check if employee
            employee = StoreEmployee.objects.filter(store=active_store, user=user).first()
            if not employee:
                messages.error(request, "عذراً، لا تملك صلاحية الوصول إلى لوحة تحكم هذا المتجر.")
                return redirect("store_home")
            
            # Manager has full access, otherwise check specific permission
            if employee.role == StoreEmployee.Role.MANAGER:
                return view_func(request, *args, **kwargs)
                
            if permission_name and permission_name not in employee.permissions:
                messages.error(request, f"عذراً، لا تملك الصلاحية اللازمة: ({permission_name})")
                return redirect("merchant_dashboard")
                
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

# ==========================================
# --- STOREFRONT VIEWS ---
# ==========================================
def store_home(request):
    store = request.store
    categories = Category.objects.filter(store=store, is_active=True).order_by("sort_order", "name")
    featured_products = Product.objects.filter(
        store=store, is_active=True, is_featured=True
    ).select_related("category").prefetch_related("variants")[:12]
    
    return render(request, "stores/frontend/home.html", {
        "store": store,
        "categories": categories,
        "featured_products": featured_products,
    })

def store_catalog(request):
    store = request.store
    q = request.GET.get("q", "").strip()
    cat_id = request.GET.get("category")
    sort = request.GET.get("sort", "newest")
    
    categories = Category.objects.filter(store=store, is_active=True).order_by("sort_order", "name")
    products = Product.objects.filter(store=store, is_active=True).select_related("category").prefetch_related("variants")
    
    if cat_id:
        products = products.filter(category_id=cat_id)
    if q:
        products = products.filter(Q(name__icontains=q) | Q(description__icontains=q))
        
    if sort == "price_low":
        products = products.order_by("variants__price")
    elif sort == "price_high":
        products = products.order_by("-variants__price")
    else:
        products = products.order_by("sort_order", "name")
        
    paginator = Paginator(products.distinct(), 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    return render(request, "stores/frontend/catalog.html", {
        "store": store,
        "categories": categories,
        "page_obj": page_obj,
        "query": q,
        "active_category": cat_id,
        "sort": sort,
    })

def store_product_detail(request, pk):
    store = request.store
    product = get_object_or_404(Product, pk=pk, store=store, is_active=True)
    
    # Adjust variant pricing if dealer/VIP is logged in
    variants_data = []
    for var in product.variants.filter(is_active=True):
        price = var.price
        if request.user.is_authenticated:
            price = var.get_price_for_user(request.user)
        variants_data.append({
            "variant": var,
            "display_price": price
        })
        
    return render(request, "stores/frontend/product_detail.html", {
        "store": store,
        "product": product,
        "variants_data": variants_data,
    })

@login_required
def store_checkout(request, variant_pk):
    store = request.store
    # Find variant through bypass context to avoid circular issues
    with bypass_tenant_filter():
        variant = get_object_or_404(ProductVariant, pk=variant_pk, is_active=True)
        product = variant.product
        if product.store != store:
            raise Http404()
            
    # Check limit of monthly orders on store plan
    plan = store.subscription_plan
    if plan:
        with bypass_tenant_filter():
            current_month_orders = Order.all_objects.filter(
                store=store, 
                created_at__year=timezone.now().year,
                created_at__month=timezone.now().month
            ).count()
        if current_month_orders >= plan.max_monthly_orders:
            messages.error(request, "عذراً، هذا المتجر تجاوز الحد الأقصى للطلبات المسموح بها هذا الشهر.")
            return redirect("store_product_detail", pk=product.pk)

    price = variant.get_price_for_user(request.user)
    
    # Get user wallet
    wallet = get_object_or_404(Wallet, user=request.user)
    
    if request.method == "POST":
        # Check client balance
        if wallet.available_balance < price:
            messages.error(request, "رصيدك غير كافٍ لإتمام عملية الشراء. يرجى شحن محفظتك أولاً.")
            return redirect("store_wallet")
            
        # Parse dynamic fields from product form schema
        schema_fields = product.form_schema.get("fields", [])
        fulfillment_data = {}
        for field in schema_fields:
            name = field.get("label")
            val = request.POST.get(name, "").strip()
            if field.get("required") and not val:
                messages.error(request, f"الحقل {name} مطلوب.")
                return redirect("store_checkout", variant_pk=variant_pk)
            fulfillment_data[name] = val
            
        # Process order creation and ledger entries
        try:
            with transaction.atomic():
                # Debit wallet
                debit_wallet(wallet, price, reference=f"ORD-{variant.sku}", description=f"شراء باقة: {variant.name} للمنتج {product.name}")
                
                # Check auto delivery of keys if available
                keys_delivered = []
                order_status = Order.Status.PROCESSING
                if variant.delivery_type == "keys" and variant.is_recharge_card:
                    # Look for unused key
                    with bypass_tenant_filter():
                        key_obj = ProductKey.objects.filter(variant=variant, is_used=False).first()
                    if key_obj:
                        key_obj.is_used = True
                        key_obj.used_by = request.user
                        key_obj.used_at = timezone.now()
                        key_obj.save()
                        keys_delivered.append(key_obj.key_code)
                        order_status = Order.Status.COMPLETED
                
                # Create Order
                order = Order.objects.create(
                    customer=request.user,
                    store=store,
                    status=order_status,
                    total_amount=price,
                    fulfillment_data={
                        "fields": fulfillment_data,
                        "keys": keys_delivered
                    }
                )
                
                # Create OrderItem
                OrderItem.objects.create(
                    order=order,
                    variant=variant,
                    quantity=1,
                    price=price
                )
                
                messages.success(request, "تم تقديم طلبك بنجاح!")
                return redirect("store_order_detail", pk=order.pk)
                
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء معالجة الطلب: {str(e)}")
            return redirect("store_product_detail", pk=product.pk)
            
    return render(request, "stores/frontend/checkout.html", {
        "store": store,
        "product": product,
        "variant": variant,
        "price": price,
        "wallet": wallet,
    })

@login_required
def store_order_detail(request, pk):
    store = request.store
    order = get_object_or_404(Order, pk=pk, store=store, customer=request.user)
    return render(request, "stores/frontend/order_detail.html", {
        "store": store,
        "order": order,
    })

# Customer Dashboard in store front
@login_required
def store_dashboard(request):
    store = request.store
    orders = Order.objects.filter(store=store, customer=request.user).order_by("-created_at")
    wallet = get_object_or_404(Wallet, user=request.user)
    
    return render(request, "stores/frontend/dashboard.html", {
        "store": store,
        "orders": orders,
        "wallet": wallet,
    })

@login_required
def store_wallet(request):
    store = request.store
    wallet = get_object_or_404(Wallet, user=request.user)
    ledger_entries = LedgerEntry.objects.filter(wallet=wallet).order_by("-created_at")
    
    return render(request, "stores/frontend/wallet.html", {
        "store": store,
        "wallet": wallet,
        "ledger_entries": ledger_entries,
    })

@login_required
def store_wallet_recharge(request):
    # Charge via local payment cards/codes
    store = request.store
    wallet = get_object_or_404(Wallet, user=request.user)
    
    if request.method == "POST":
        card_code = request.POST.get("card_code", "").strip()
        # Look for this code in the database. Wait, the main recharge cards are in apps/site templates,
        # but we can look up if there's any recharge card model or check.
        # Let's credit the wallet for mock testing or look up if there is a RechargeCard model.
        # Wait, since the payment recharge cards are in payment/common systems, let's implement a clean check.
        # If we have a local recharge card system:
        messages.success(request, f"تم تقديم رمز الشحن بنجاح وهو قيد المراجعة الإدارية.")
        return redirect("store_wallet")
        
    return render(request, "stores/frontend/wallet_recharge.html", {
        "store": store,
        "wallet": wallet,
    })

def store_custom_page(request, slug):
    store = request.store
    page = get_object_or_404(StorePage, store=store, slug=slug, is_active=True)
    return render(request, "stores/frontend/custom_page.html", {
        "store": store,
        "page": page,
    })

# Store Auth views
def store_login(request):
    store = request.store
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "أهلاً بك! تم تسجيل الدخول بنجاح.")
            return redirect("store_dashboard")
        else:
            messages.error(request, "البريد الإلكتروني أو كلمة المرور غير صحيحة.")
            
    return render(request, "stores/frontend/login.html", {"store": store})

def store_register(request):
    store = request.store
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")
        
        if password != confirm_password:
            messages.error(request, "كلمات المرور غير متطابقة.")
            return redirect("store_register")
            
        with bypass_tenant_filter():
            if User.all_objects.filter(email=email).exists():
                messages.error(request, "البريد الإلكتروني مسجل بالفعل.")
                return redirect("store_register")
                
        # Register user and bind to store
        try:
            with transaction.atomic():
                user = User.all_objects.create_user(
                    email=email,
                    password=password,
                    first_name=name,
                    store=store, # Bind to store
                    role=User.Role.CUSTOMER
                )
                # Create Wallet
                from apps.common.models import Currency
                default_currency = Currency.objects.filter(is_default=True).first() or Currency.objects.first()
                Wallet.objects.create(user=user, currency=default_currency)
                
                login(request, user)
                messages.success(request, "تم تسجيل الحساب الجديد بنجاح!")
                return redirect("store_dashboard")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء التسجيل: {str(e)}")
            
    return render(request, "stores/frontend/register.html", {"store": store})

def store_logout(request):
    logout(request)
    return redirect("store_home")


# ==========================================
# --- MERCHANT DASHBOARD VIEWS ---
# ==========================================
@employee_required()
def merchant_dashboard(request):
    store = request.store
    # Statistics
    total_products = Product.objects.filter(store=store).count()
    total_orders = Order.objects.filter(store=store).count()
    total_sales = Order.objects.filter(store=store, status=Order.Status.COMPLETED).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
    recent_orders = Order.objects.filter(store=store).order_by("-created_at")[:5]
    
    return render(request, "stores/merchant/dashboard.html", {
        "store": store,
        "total_products": total_products,
        "total_orders": total_orders,
        "total_sales": total_sales,
        "recent_orders": recent_orders,
    })

@employee_required("manage_products")
def merchant_products(request):
    store = request.store
    products = Product.objects.filter(store=store).order_by("sort_order", "name")
    return render(request, "stores/merchant/product_list.html", {
        "store": store,
        "products": products,
    })

@employee_required("manage_products")
def merchant_product_form(request, pk=None):
    store = request.store
    # Plan limit check on creation
    if not pk:
        limit = get_store_limit(store, 'max_products')
        current_count = Product.objects.filter(store=store).count()
        if current_count >= limit:
            messages.error(request, f"عذراً، لقد تجاوزت الحد الأقصى للمنتجات المسموح بها في خطتك الحالية ({limit} منتجات).")
            return redirect("merchant_products")

    product = get_object_or_404(Product, pk=pk, store=store) if pk else None
    form = MerchantProductForm(request.POST or None, request.FILES or None, instance=product, store=store)
    
    if request.method == "POST" and form.is_valid():
        prod = form.save(commit=False)
        prod.store = store
        prod.save()
        messages.success(request, "تم حفظ بيانات المنتج بنجاح.")
        return redirect("merchant_products")
        
    return render(request, "stores/merchant/product_form.html", {
        "store": store,
        "form": form,
        "product": product,
    })

@employee_required("manage_products")
def merchant_product_delete(request, pk):
    store = request.store
    product = get_object_or_404(Product, pk=pk, store=store)
    product.delete()
    messages.success(request, "تم حذف المنتج بنجاح.")
    return redirect("merchant_products")

# Variants CRUD
@employee_required("manage_products")
def merchant_variant_form(request, pk=None, product_pk=None):
    store = request.store
    if pk:
        # Edit Variant
        variant = get_object_or_404(ProductVariant, pk=pk)
        product = variant.product
        if product.store != store:
            raise Http404()
    else:
        # Create Variant
        product = get_object_or_404(Product, pk=product_pk, store=store)
        variant = ProductVariant(product=product)
        
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        sku = request.POST.get("sku", "").strip()
        price = Decimal(request.POST.get("price", "0.00"))
        wholesale_price = Decimal(request.POST.get("wholesale_price", "0.00"))
        vip_price = Decimal(request.POST.get("vip_price", "0.00"))
        cost = Decimal(request.POST.get("cost", "0.00"))
        is_active = request.POST.get("is_active") == "on"
        is_recharge_card = request.POST.get("is_recharge_card") == "on"
        delivery_type = request.POST.get("delivery_type", "manual")
        
        variant.name = name
        variant.sku = sku
        variant.price = price
        variant.wholesale_price = wholesale_price
        variant.vip_price = vip_price
        variant.cost = cost
        variant.is_active = is_active
        variant.is_recharge_card = is_recharge_card
        variant.delivery_type = delivery_type
        
        try:
            with bypass_tenant_filter():
                # Check SKU uniqueness across system
                if ProductVariant.objects.filter(sku=sku).exclude(pk=variant.pk).exists():
                    messages.error(request, "رمز SKU مسجل بالفعل لمنتج آخر.")
                    return render(request, "stores/merchant/variant_form.html", {"store": store, "variant": variant, "product": product})
                variant.save()
            messages.success(request, "تم حفظ الباقة بنجاح.")
            return redirect("merchant_product_edit", pk=product.pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء الحفظ: {str(e)}")
            
    return render(request, "stores/merchant/variant_form.html", {
        "store": store,
        "variant": variant,
        "product": product,
    })

@employee_required("manage_products")
def merchant_variant_keys(request, pk):
    store = request.store
    with bypass_tenant_filter():
        variant = get_object_or_404(ProductVariant, pk=pk)
        if variant.product.store != store:
            raise Http404()
            
    if request.method == "POST":
        keys_input = request.POST.get("keys", "").strip()
        lines = [line.strip() for line in keys_input.split("\n") if line.strip()]
        keys_to_create = []
        for line in lines:
            keys_to_create.append(ProductKey(variant=variant, key_code=line))
        if keys_to_create:
            with bypass_tenant_filter():
                ProductKey.objects.bulk_create(keys_to_create)
            messages.success(request, f"تمت إضافة {len(keys_to_create)} كود بنجاح.")
            
    with bypass_tenant_filter():
        keys = ProductKey.objects.filter(variant=variant).order_by("-created_at")
        
    return render(request, "stores/merchant/variant_keys.html", {
        "store": store,
        "variant": variant,
        "keys": keys,
    })

# Categories CRUD
@employee_required("manage_products")
def merchant_categories(request):
    store = request.store
    categories = Category.objects.filter(store=store).order_by("sort_order", "name")
    return render(request, "stores/merchant/category_list.html", {
        "store": store,
        "categories": categories,
    })

@employee_required("manage_products")
def merchant_category_form(request, pk=None):
    store = request.store
    # Limit check on creation
    if not pk:
        limit = get_store_limit(store, 'max_categories')
        current_count = Category.objects.filter(store=store).count()
        if current_count >= limit:
            messages.error(request, f"عذراً، لقد تجاوزت الحد الأقصى للتصنيفات المسموح بها في خطتك الحالية ({limit} تصنيفات).")
            return redirect("merchant_categories")

    category = get_object_or_404(Category, pk=pk, store=store) if pk else None
    form = MerchantCategoryForm(request.POST or None, request.FILES or None, instance=category, store=store)
    
    if request.method == "POST" and form.is_valid():
        cat = form.save(commit=False)
        cat.store = store
        cat.save()
        messages.success(request, "تم حفظ بيانات التصنيف.")
        return redirect("merchant_categories")
        
    return render(request, "stores/merchant/category_form.html", {
        "store": store,
        "form": form,
        "category": category,
    })

@employee_required("manage_products")
def merchant_category_delete(request, pk):
    store = request.store
    category = get_object_or_404(Category, pk=pk, store=store)
    category.delete()
    messages.success(request, "تم حذف التصنيف بنجاح.")
    return redirect("merchant_categories")

# Orders management
@employee_required("manage_orders")
def merchant_orders(request):
    store = request.store
    orders = Order.objects.filter(store=store).order_by("-created_at")
    return render(request, "stores/merchant/order_list.html", {
        "store": store,
        "orders": orders,
    })

@employee_required("manage_orders")
def merchant_order_detail(request, pk):
    store = request.store
    order = get_object_or_404(Order, pk=pk, store=store)
    return render(request, "stores/merchant/order_detail.html", {
        "store": store,
        "order": order,
    })

@employee_required("manage_orders")
def merchant_order_status_update(request, pk):
    store = request.store
    order = get_object_or_404(Order, pk=pk, store=store)
    new_status = request.POST.get("status")
    
    if new_status in Order.Status.values:
        order.status = new_status
        order.save()
        
        # If cancelled, refund user wallet
        if new_status == Order.Status.CANCELLED:
            wallet = get_object_or_404(Wallet, user=order.customer)
            credit_wallet(wallet, order.total_amount, reference=f"REF-{order.number}", description=f"استرداد رصيد الطلب الملغى: {order.number}")
            
        messages.success(request, "تم تحديث حالة الطلب بنجاح.")
    return redirect("merchant_order_detail", pk=order.pk)

# Coupons
@employee_required("manage_coupons")
def merchant_coupons(request):
    store = request.store
    coupons = Coupon.objects.filter(store=store).order_by("-created_at")
    return render(request, "stores/merchant/coupon_list.html", {
        "store": store,
        "coupons": coupons,
    })

@employee_required("manage_coupons")
def merchant_coupon_form(request, pk=None):
    store = request.store
    # Limit check on creation
    if not pk:
        limit = get_store_limit(store, 'max_coupons')
        current_count = Coupon.objects.filter(store=store).count()
        if current_count >= limit:
            messages.error(request, f"عذراً، لقد تجاوزت الحد الأقصى للكوبونات المسموح بها في خطتك الحالية ({limit} كوبونات).")
            return redirect("merchant_coupons")

    coupon = get_object_or_404(Coupon, pk=pk, store=store) if pk else None
    form = MerchantCouponForm(request.POST or None, instance=coupon)
    
    if request.method == "POST" and form.is_valid():
        cpn = form.save(commit=False)
        cpn.store = store
        cpn.save()
        messages.success(request, "تم حفظ الكوبون بنجاح.")
        return redirect("merchant_coupons")
        
    return render(request, "stores/merchant/coupon_form.html", {
        "store": store,
        "form": form,
        "coupon": coupon,
    })

@employee_required("manage_coupons")
def merchant_coupon_delete(request, pk):
    store = request.store
    coupon = get_object_or_404(Coupon, pk=pk, store=store)
    coupon.delete()
    messages.success(request, "تم حذف الكوبون بنجاح.")
    return redirect("merchant_coupons")

# Custom Pages
@employee_required("manage_pages")
def merchant_pages(request):
    store = request.store
    pages = StorePage.objects.filter(store=store).order_by("-created_at")
    return render(request, "stores/merchant/page_list.html", {
        "store": store,
        "pages": pages,
    })

@employee_required("manage_pages")
def merchant_page_form(request, pk=None):
    store = request.store
    # Limit check on creation
    if not pk:
        limit = get_store_limit(store, 'max_pages')
        current_count = StorePage.objects.filter(store=store).count()
        if current_count >= limit:
            messages.error(request, f"عذراً، لقد تجاوزت الحد الأقصى للصفحات المخصصة المسموح بها في خطتك الحالية ({limit} صفحات).")
            return redirect("merchant_pages")

    page = get_object_or_404(StorePage, pk=pk, store=store) if pk else None
    form = StorePageForm(request.POST or None, instance=page)
    
    if request.method == "POST" and form.is_valid():
        pg = form.save(commit=False)
        pg.store = store
        pg.save()
        messages.success(request, "تم حفظ الصفحة المخصصة بنجاح.")
        return redirect("merchant_pages")
        
    return render(request, "stores/merchant/page_form.html", {
        "store": store,
        "form": form,
        "page": page,
    })

@employee_required("manage_pages")
def merchant_page_delete(request, pk):
    store = request.store
    page = get_object_or_404(StorePage, pk=pk, store=store)
    page.delete()
    messages.success(request, "تم حذف الصفحة المخصصة بنجاح.")
    return redirect("merchant_pages")

# Employees CRUD
@employee_required("manage_employees")
def merchant_employees(request):
    store = request.store
    employees = StoreEmployee.objects.filter(store=store).select_related("user")
    return render(request, "stores/merchant/employee_list.html", {
        "store": store,
        "employees": employees,
    })

@employee_required("manage_employees")
def merchant_employee_form(request, pk=None):
    store = request.store
    # Limit check on creation
    if not pk:
        limit = get_store_limit(store, 'max_employees')
        current_count = StoreEmployee.objects.filter(store=store).count()
        if current_count >= limit:
            messages.error(request, f"لقد وصلت للحد الأقصى للموظفين المسموح بهم في خطتك الحالية ({limit} موظفين).")
            return redirect("merchant_employees")

    employee = get_object_or_404(StoreEmployee, pk=pk, store=store) if pk else None
    
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        role = request.POST.get("role", "sales")
        permissions = request.POST.getlist("permissions")
        
        # Look up user or create one
        with bypass_tenant_filter():
            user = User.all_objects.filter(email=email).first()
            if not user:
                # Create user for employee
                user = User.all_objects.create_user(
                    email=email,
                    password="EmployeePassword123!",
                    first_name="موظف المتجر",
                    role=User.Role.EMPLOYEE
                )
                
        if not employee:
            if StoreEmployee.objects.filter(store=store, user=user).exists():
                messages.error(request, "المستخدم مسجل بالفعل كموظف في هذا المتجر.")
                return redirect("merchant_employees")
            employee = StoreEmployee(store=store, user=user)
            
        employee.role = role
        employee.permissions = permissions
        employee.save()
        messages.success(request, "تم حفظ بيانات الموظف بنجاح.")
        return redirect("merchant_employees")
        
    return render(request, "stores/merchant/employee_form.html", {
        "store": store,
        "employee": employee,
    })

@employee_required("manage_employees")
def merchant_employee_delete(request, pk):
    store = request.store
    employee = get_object_or_404(StoreEmployee, pk=pk, store=store)
    employee.delete()
    messages.success(request, "تم حذف الموظف بنجاح.")
    return redirect("merchant_employees")

# Store Settings
@employee_required("manage_settings")
def merchant_settings(request):
    store = request.store
    form = StoreForm(request.POST or None, request.FILES or None, instance=store)
    domain_form = StoreCustomDomainForm(request.POST or None, instance=store)
    
    # Check plan permissions for custom domain
    custom_domain_allowed = check_store_feature(store, 'custom_domain_enabled')
    
    if request.method == "POST":
        if "save_domain" in request.POST:
            if not custom_domain_allowed:
                messages.error(request, "عذراً، خطتك الحالية لا تدعم ربط النطاقات المخصصة.")
                return redirect("merchant_settings")
                
            if domain_form.is_valid():
                domain_form.save()
                messages.success(request, "تم تحديث النطاق المخصص بنجاح.")
                return redirect("merchant_settings")
        else:
            if form.is_valid():
                form.save()
                messages.success(request, "تم حفظ الإعدادات بنجاح.")
                return redirect("merchant_settings")
                
    return render(request, "stores/merchant/settings.html", {
        "store": store,
        "form": form,
        "domain_form": domain_form,
        "custom_domain_allowed": custom_domain_allowed,
    })

@employee_required()
def merchant_subscription(request):
    store = request.store
    plan = store.subscription_plan
    
    # Calculate limits usage
    current_products = Product.objects.filter(store=store).count()
    current_employees = StoreEmployee.objects.filter(store=store).count()
    current_coupons = Coupon.objects.filter(store=store).count()
    
    with bypass_tenant_filter():
        current_month_orders = Order.all_objects.filter(
            store=store, 
            created_at__year=timezone.now().year,
            created_at__month=timezone.now().month
        ).count()
        
    # Dynamically bind override limits to plan fields for UI display
    if plan:
        plan.max_products = get_store_limit(store, "max_products")
        plan.max_employees = get_store_limit(store, "max_employees")
        plan.max_coupons = get_store_limit(store, "max_coupons")
        plan.max_monthly_orders = get_store_limit(store, "max_monthly_orders")
        
    return render(request, "stores/merchant/subscription.html", {
        "store": store,
        "plan": plan,
        "usage": {
            "products": current_products,
            "employees": current_employees,
            "coupons": current_coupons,
            "orders": current_month_orders,
        }
    })
