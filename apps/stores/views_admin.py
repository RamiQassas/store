import shutil
import os
import uuid
from datetime import timedelta
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.db.models import Sum, Count
from django.http import Http404
from django.utils import timezone
from apps.common.decorators import admin_required

from apps.stores.models import Store, SubscriptionPlan, StoreEmployee, SubscriptionInvoice
from apps.stores.forms import StoreCreateForm
from apps.catalog.models import Product
from apps.orders.models import Order
from apps.accounts.models import User
from apps.wallets.models import Wallet
from apps.wallets.services import get_or_create_wallet, debit_wallet
from apps.common.tenant_utils import bypass_tenant_filter

@login_required
def store_registration_landing(request):
    """Landing page for store registration on the main site."""
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by("price_monthly")
    
    if request.method == "POST":
        form = StoreCreateForm(request.POST, request.FILES)
        if form.is_valid():
            # Save selection to session and redirect to payment
            request.session["store_reg_data"] = {
                "name": form.cleaned_data["name"],
                "subdomain": form.cleaned_data["subdomain"],
                "description": form.cleaned_data["description"],
                "plan_id": str(form.cleaned_data["subscription_plan"].id),
                "billing_cycle": form.cleaned_data["billing_cycle"],
            }
            # Handle logo upload separately
            if request.FILES.get("logo"):
                logo_file = request.FILES["logo"]
                from django.core.files.storage import default_storage
                path = default_storage.save(f"temp/{uuid.uuid4().hex}_{logo_file.name}", logo_file)
                request.session["store_reg_logo_path"] = path
                
            return redirect("store_registration_payment")
    else:
        form = StoreCreateForm()
        
    return render(request, "stores/super_admin/registration_landing.html", {
        "form": form,
        "plans": plans,
    })

@login_required
def store_registration_payment(request):
    """Mock payment simulation for store subscription via wallet balance."""
    reg_data = request.session.get("store_reg_data")
    if not reg_data:
        messages.error(request, "يرجى ملء بيانات المتجر أولاً.")
        return redirect("store_registration")
        
    plan = get_object_or_404(SubscriptionPlan, id=reg_data["plan_id"])
    billing_cycle = reg_data.get("billing_cycle", "monthly")
    
    # Wallet balance verification
    wallet = get_or_create_wallet(request.user)
    plan_price_usd = plan.price_monthly if billing_cycle == "monthly" else plan.price_yearly
    plan_price_wallet = wallet.currency.from_base(plan_price_usd, "withdraw")
    plan_price_wallet = Decimal(plan_price_wallet).quantize(Decimal("0.01"))
    
    insufficient_balance = wallet.available_balance < plan_price_wallet
    
    balance_display = f"{wallet.available_balance:,.2f} {wallet.currency.symbol}"
    price_display = f"{plan_price_wallet:,.2f} {wallet.currency.symbol}"
    
    if request.method == "POST":
        if insufficient_balance:
            messages.error(request, f"عذراً، رصيدك غير كافٍ لإتمام الدفع. الرصيد الحالي: {balance_display}، التكلفة المطلوبة: {price_display}.")
            return redirect("store_registration_payment")
            
        logo_path = request.session.get("store_reg_logo_path")
        
        try:
            with transaction.atomic():
                with bypass_tenant_filter():
                    # Double check subdomain uniqueness case-insensitively
                    if Store.unfiltered.filter(subdomain__iexact=reg_data["subdomain"]).exists():
                        messages.error(request, "رابط المتجر هذا محجوز بالفعل. يرجى اختيار رابط آخر.")
                        return redirect("store_registration")
                        
                    # Lock wallet to prevent race conditions
                    user_wallet = Wallet.objects.select_for_update().get(id=wallet.id)
                    if user_wallet.available_balance < plan_price_wallet:
                        messages.error(request, "رصيد المحفظة غير كافٍ لإتمام العملية.")
                        return redirect("store_registration_payment")
                        
                    # Deduct balance from wallet
                    invoice_ref = f"INV-SUB-{uuid.uuid4().hex[:8].upper()}"
                    debit_wallet(
                        wallet_id=user_wallet.id,
                        amount=plan_price_wallet,
                        source="Store Subscription",
                        reason=f"اشتراك متجر '{reg_data['name']}' في باقة {plan.name} ({'سنوي' if billing_cycle == 'yearly' else 'شهري'})",
                        reference=invoice_ref,
                        created_by=request.user
                    )
                    
                    # Create Store
                    duration_days = 365 if billing_cycle == "yearly" else 30
                    store = Store.objects.create(
                        owner=request.user,
                        name=reg_data["name"],
                        subdomain=reg_data["subdomain"].lower(),
                        custom_domain=None,
                        description=reg_data["description"],
                        subscription_plan=plan,
                        subscription_status=Store.Status.ACTIVE,
                        subscription_start=timezone.now(),
                        subscription_end=timezone.now() + timedelta(days=duration_days),
                        billing_cycle=billing_cycle,
                        is_active=True
                    )
                    
                    if logo_path:
                        store.logo = logo_path
                        store.save()
                        
                    # Update request.user role and link to store
                    user = request.user
                    user.role = User.Role.VERIFIED_MERCHANT
                    user.store = store
                    user.save()
                        
                    # Create Owner as first employee with full permissions
                    permissions_list = [
                        "manage_products", 
                        "manage_orders", 
                        "manage_coupons", 
                        "manage_pages", 
                        "manage_settings", 
                        "manage_employees", 
                        "view_reports"
                    ]
                    StoreEmployee.objects.create(
                        store=store,
                        user=user,
                        role=StoreEmployee.Role.OWNER,
                        permissions=permissions_list
                    )
                    
                    # Create Subscription Invoice
                    SubscriptionInvoice.objects.create(
                        user=request.user,
                        store=store,
                        plan=plan,
                        invoice_number=invoice_ref,
                        amount=plan_price_wallet,
                        currency=wallet.currency,
                        status="paid"
                    )
                    
            # Clear session
            request.session.pop("store_reg_data", None)
            request.session.pop("store_reg_logo_path", None)
            
            messages.success(request, f"تهانينا! تم إنشاء متجرك '{store.name}' بنجاح. استخدم حسابك الحالي لتسجيل الدخول إلى لوحة تحكم المتجر.")
            return render(request, "stores/super_admin/registration_success.html", {"store": store})
            
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء معالجة الدفع وإنشاء المتجر: {str(e)}")
            return redirect("store_registration")
            
    return render(request, "stores/super_admin/registration_payment.html", {
        "reg_data": reg_data,
        "plan": plan,
        "wallet": wallet,
        "plan_price_wallet": plan_price_wallet,
        "insufficient_balance": insufficient_balance,
        "balance_display": balance_display,
        "price_display": price_display,
    })


@admin_required
def platform_super_admin_dashboard(request):
    """Dashboard for Platform Owner (Raqamiyat Owner) to manage SaaS."""
    with bypass_tenant_filter():
        stores = Store.unfiltered.all().order_by("-created_at")
        total_stores = stores.count()
        active_stores_count = stores.filter(is_active=True).count()
        total_products = Product.all_objects.count()
        total_orders = Order.all_objects.count()
        
        # Calculate revenue/profit
        total_payments = Order.all_objects.filter(status=Order.Status.COMPLETED).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        
        # Database monitoring
        db_engine = connection.vendor
        db_size = "N/A"
        if db_engine == "sqlite":
            db_path = connection.settings_dict["NAME"]
            if os.path.exists(db_path):
                db_size = f"{os.path.getsize(db_path) / (1024 * 1024):.2f} MB"
                
        # Resource consumption
        # Disk usage of media directory
        media_root = settings.MEDIA_ROOT
        disk_usage = "N/A"
        if os.path.exists(media_root):
            total, used, free = shutil.disk_usage(media_root)
            disk_usage = f"{(used / (1024 * 1024 * 1024)):.2f} GB / {(total / (1024 * 1024 * 1024)):.2f} GB"
            
    return render(request, "stores/super_admin/dashboard.html", {
        "stores": stores,
        "total_stores": total_stores,
        "active_stores_count": active_stores_count,
        "total_products": total_products,
        "total_orders": total_orders,
        "total_payments": total_payments,
        "db_engine": db_engine,
        "db_size": db_size,
        "disk_usage": disk_usage,
    })

@admin_required
def platform_toggle_store_status(request, pk):
    """Platform owner can suspend or activate any store."""
    with bypass_tenant_filter():
        store = get_object_or_404(Store.unfiltered, pk=pk)
        store.is_active = not store.is_active
        store.save()
        status_text = "تفعيل" if store.is_active else "إيقاف"
        messages.success(request, f"تم {status_text} المتجر '{store.name}' بنجاح.")
    return redirect("platform_super_admin_dashboard")

@admin_required
def platform_plan_list(request):
    """List subscription plans for editing."""
    plans = SubscriptionPlan.objects.all().order_by("price_monthly")
    return render(request, "stores/super_admin/plan_list.html", {"plans": plans})

@admin_required
def platform_plan_form(request, pk=None):
    """Create or edit subscription plan limits and prices."""
    plan = get_object_or_404(SubscriptionPlan, pk=pk) if pk else None
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        price_monthly = Decimal(request.POST.get("price_monthly", "0.00"))
        price_yearly = Decimal(request.POST.get("price_yearly", "0.00"))
        max_products = int(request.POST.get("max_products", 10))
        max_employees = int(request.POST.get("max_employees", 1))
        max_monthly_orders = int(request.POST.get("max_monthly_orders", 100))
        max_storage_mb = int(request.POST.get("max_storage_mb", 100))
        max_coupons = int(request.POST.get("max_coupons", 5))
        custom_domain_enabled = request.POST.get("custom_domain_enabled") == "on"
        remove_branding_enabled = request.POST.get("remove_branding_enabled") == "on"
        api_access_enabled = request.POST.get("api_access_enabled") == "on"
        advanced_reports_enabled = request.POST.get("advanced_reports_enabled") == "on"
        is_active = request.POST.get("is_active") == "on"
        
        if not plan:
            plan = SubscriptionPlan()
            
        plan.name = name
        plan.description = description
        plan.price_monthly = price_monthly
        plan.price_yearly = price_yearly
        plan.max_products = max_products
        plan.max_employees = max_employees
        plan.max_monthly_orders = max_monthly_orders
        plan.max_storage_mb = max_storage_mb
        plan.max_coupons = max_coupons
        plan.custom_domain_enabled = custom_domain_enabled
        plan.remove_branding_enabled = remove_branding_enabled
        plan.api_access_enabled = api_access_enabled
        plan.advanced_reports_enabled = advanced_reports_enabled
        plan.is_active = is_active
        
        plan.save()
        messages.success(request, "تم حفظ باقة الاشتراك بنجاح.")
        return redirect("platform_plan_list")
        
    return render(request, "stores/super_admin/plan_form.html", {
        "plan": plan,
    })
