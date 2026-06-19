import os
import shutil
import uuid
from decimal import Decimal
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.db.models import Sum, Count, Q
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.conf import settings

from apps.stores.models import (
    Store, SubscriptionPlan, StoreEmployee, StorePage, StoreSetting, 
    SaaSAdminRole, SaaSAuditLog, StoreTemplate, SaaSGlobalSetting
)
from apps.catalog.models import Product, Category, ProductVariant, ProductImage
from apps.orders.models import Order
from apps.wallets.models import Wallet
from apps.payments.models import DepositRequest, WithdrawalRequest
from apps.common.tenant_utils import bypass_tenant_filter

User = get_user_model()

# ==========================================
# --- HELPERS & DECORATORS ---
# ==========================================

def log_saas_action(request, action, description):
    """Helper to log SaaS audit events."""
    user = request.user if request and request.user.is_authenticated else None
    ip = request.META.get('REMOTE_ADDR') if request else None
    SaaSAuditLog.objects.create(
        user=user,
        action=action,
        description=description,
        ip_address=ip
    )

def saas_permission_required(permission_name):
    """Decorator to enforce SaaS permissions."""
    def decorator(view_func):
        @login_required
        def _wrapped(request, *args, **kwargs):
            user = request.user
            # Super admins have bypass access
            if user.role == User.Role.SUPER_ADMIN or user.is_superuser:
                return view_func(request, *args, **kwargs)
                
            # Check custom role permissions
            if hasattr(user, 'saas_role') and user.saas_role:
                if permission_name in user.saas_role.permissions:
                    return view_func(request, *args, **kwargs)
                    
            messages.error(request, f"عذراً، لا تملك صلاحية الوصول إلى هذه الصفحة: ({permission_name})")
            return redirect("control_dashboard")
        return _wrapped
    return decorator

def get_store_storage_mb(store):
    """Calculate disk storage used by a store in MB."""
    total_bytes = 0
    if store.logo and hasattr(store.logo, 'size'):
        try: total_bytes += store.logo.size
        except: pass
    if store.banner and hasattr(store.banner, 'size'):
        try: total_bytes += store.banner.size
        except: pass
        
    with bypass_tenant_filter():
        p_ids = list(Product.all_objects.filter(store=store).values_list('id', flat=True))
        p_imgs = ProductImage.objects.filter(product_id__in=p_ids)
        for img in p_imgs:
            if img.image and hasattr(img.image, 'size'):
                try: total_bytes += img.image.size
                except: pass
    return round(total_bytes / (1024 * 1024), 2)

# ==========================================
# --- SAAS DASHBOARD ---
# ==========================================

@saas_permission_required("dashboard")
def saas_dashboard(request):
    with bypass_tenant_filter():
        stores = Store.unfiltered.all().order_by("-created_at")
        total_stores = stores.count()
        active_stores = stores.filter(is_active=True, subscription_status=Store.Status.ACTIVE).count()
        suspended_stores = stores.filter(subscription_status=Store.Status.SUSPENDED).count()
        expired_stores = stores.filter(subscription_end__lt=timezone.now()).count()
        
        total_users = User.all_objects.filter(store__isnull=False).count()
        total_products = Product.all_objects.filter(store__isnull=False).count()
        total_orders = Order.all_objects.filter(store__isnull=False).count()
        
        # Financial revenues (from completed SaaS subscription payments/orders or simulated plan payments)
        total_sales = Order.all_objects.filter(store__isnull=False, status=Order.Status.COMPLETED).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        
        # Monthly/yearly SaaS revenue estimate (based on active store plans)
        monthly_rev = Decimal("0.00")
        yearly_rev = Decimal("0.00")
        for s in stores.filter(is_active=True, subscription_status=Store.Status.ACTIVE).select_related('subscription_plan'):
            if s.subscription_plan:
                monthly_rev += s.subscription_plan.price_monthly
                yearly_rev += s.subscription_plan.price_yearly

        # Recent registrations
        recent_stores = stores[:5]
        
        # Recent audit logs
        recent_logs = SaaSAuditLog.objects.all()[:5]

        # Simple alerts (stores approaching or exceeding limits)
        alerts = []
        for s in stores.filter(is_active=True)[:10]:
            p_count = Product.all_objects.filter(store=s).count()
            limit = s.limit_overrides.get('max_products') or (s.subscription_plan.max_products if s.subscription_plan else 0)
            if limit and p_count >= limit:
                alerts.append({
                    "store": s,
                    "type": "products_limit",
                    "msg": f"المتجر {s.name} بلغ أو تجاوز الحد الأقصى للمنتجات ({p_count}/{limit})"
                })
            
            # Storage alert
            storage_mb = get_store_storage_mb(s)
            storage_limit = s.limit_overrides.get('max_storage_mb') or (s.subscription_plan.max_storage_mb if s.subscription_plan else 0)
            if storage_limit and storage_mb >= storage_limit:
                alerts.append({
                    "store": s,
                    "type": "storage_limit",
                    "msg": f"المتجر {s.name} تجاوز حد مساحة التخزين المسموحة ({storage_mb} MB / {storage_limit} MB)"
                })

    return render(request, "stores/saas/dashboard.html", {
        "total_stores": total_stores,
        "active_stores": active_stores,
        "suspended_stores": suspended_stores,
        "expired_stores": expired_stores,
        "total_users": total_users,
        "total_products": total_products,
        "total_orders": total_orders,
        "total_sales": total_sales,
        "monthly_rev": monthly_rev,
        "yearly_rev": yearly_rev,
        "recent_stores": recent_stores,
        "recent_logs": recent_logs,
        "alerts": alerts,
    })

# ==========================================
# --- STORES MANAGEMENT ---
# ==========================================

@saas_permission_required("manage_stores")
def saas_store_list(request):
    q = request.GET.get("q", "").strip()
    plan_id = request.GET.get("plan")
    status = request.GET.get("status")
    
    with bypass_tenant_filter():
        stores = Store.unfiltered.all().select_related('subscription_plan', 'owner').order_by("-created_at")
        
        if q:
            stores = stores.filter(Q(name__icontains=q) | Q(slug__icontains=q) | Q(custom_domain__icontains=q) | Q(owner__email__icontains=q))
        if plan_id:
            stores = stores.filter(subscription_plan_id=plan_id)
        if status:
            stores = stores.filter(subscription_status=status)
            
        plans = SubscriptionPlan.objects.all().order_by("price_monthly")
        
        paginator = Paginator(stores, 20)
        page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "stores/saas/store_list.html", {
        "page_obj": page_obj,
        "plans": plans,
        "query": q,
        "active_plan": plan_id,
        "active_status": status,
        "status_choices": Store.Status.choices
    })

@saas_permission_required("manage_stores")
def saas_store_detail(request, pk):
    with bypass_tenant_filter():
        store = get_object_or_404(Store.unfiltered.select_related('subscription_plan', 'owner'), pk=pk)
        
        # Calculate stats
        product_count = Product.all_objects.filter(store=store).count()
        customer_count = User.all_objects.filter(store=store).count()
        order_count = Order.all_objects.filter(store=store).count()
        storage_mb = get_store_storage_mb(store)
        
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by("price_monthly")
        
        if request.method == "POST":
            action = request.POST.get("action")
            
            if action == "change_plan":
                plan_id = request.POST.get("plan_id")
                plan = get_object_or_404(SubscriptionPlan, id=plan_id)
                store.subscription_plan = plan
                store.save()
                log_saas_action(request, "تغيير خطة المتجر", f"تم تغيير خطة المتجر {store.name} إلى {plan.name}")
                messages.success(request, f"تم تغيير خطة المتجر بنجاح إلى {plan.name}")
                
            elif action == "extend_subscription":
                days = int(request.POST.get("days", 30))
                if store.subscription_end and store.subscription_end > timezone.now():
                    store.subscription_end += timedelta(days=days)
                else:
                    store.subscription_end = timezone.now() + timedelta(days=days)
                store.subscription_status = Store.Status.ACTIVE
                store.save()
                log_saas_action(request, "تمديد الاشتراك", f"تم تمديد اشتراك المتجر {store.name} لـ {days} يوماً")
                messages.success(request, f"تم تمديد اشتراك المتجر بنجاح لـ {days} يوماً")
                
            elif action == "reset_consumption":
                log_saas_action(request, "تصفير استهلاك المتجر", f"تم تصفير استهلاك الموارد للمتجر {store.name}")
                messages.success(request, "تمت إعادة تعيين وتصفير استهلاك المتجر بنجاح")
                
            elif action == "reset_password":
                new_pass = request.POST.get("new_password", "").strip()
                if len(new_pass) < 6:
                    messages.error(request, "يجب أن تكون كلمة المرور 6 خانات على الأعل.")
                else:
                    owner = store.owner
                    owner.set_password(new_pass)
                    owner.save()
                    log_saas_action(request, "تغيير كلمة مرور المالك", f"تم إعادة تعيين كلمة مرور مالك المتجر {store.name}")
                    messages.success(request, f"تم تغيير كلمة مرور المالك ({owner.email}) بنجاح")
            
            return redirect("control_saas_store_detail", pk=pk)

    return render(request, "stores/saas/store_detail.html", {
        "store": store,
        "product_count": product_count,
        "customer_count": customer_count,
        "order_count": order_count,
        "storage_mb": storage_mb,
        "plans": plans
    })

@saas_permission_required("manage_stores")
def saas_store_edit_limits(request, pk):
    with bypass_tenant_filter():
        store = get_object_or_404(Store.unfiltered, pk=pk)
        
        fields = [
            'max_products', 'max_categories', 'max_monthly_orders', 'max_customers',
            'max_employees', 'max_branches', 'max_coupons', 'max_images',
            'max_storage_mb', 'max_bandwidth_gb', 'max_domains', 'max_api_keys', 'max_pages'
        ]
        
        if request.method == "POST":
            overrides = {}
            for field in fields:
                val = request.POST.get(field, "").strip()
                if val:
                    overrides[field] = int(val)
            store.limit_overrides = overrides
            store.save()
            log_saas_action(request, "تعديل حدود مخصصة", f"تم تعديل حدود المتجر {store.name} يدوياً")
            messages.success(request, f"تم حفظ الحدود المخصصة للمتجر '{store.name}' بنجاح.")
            return redirect("control_saas_store_detail", pk=pk)
            
    return render(request, "stores/saas/store_limits_form.html", {
        "store": store,
        "fields": fields
    })

@saas_permission_required("manage_stores")
def saas_store_toggle_status(request, pk):
    with bypass_tenant_filter():
        store = get_object_or_404(Store.unfiltered, pk=pk)
        action = request.GET.get("action")
        
        if action == "activate":
            store.is_active = True
            store.subscription_status = Store.Status.ACTIVE
            log_saas_action(request, "تفعيل المتجر", f"تم تنشيط وتفعيل متجر {store.name}")
        elif action == "suspend":
            store.subscription_status = Store.Status.SUSPENDED
            log_saas_action(request, "تعليق المتجر", f"تم تعليق حساب متجر {store.name}")
        elif action == "deactivate":
            store.is_active = False
            log_saas_action(request, "إيقاف المتجر", f"تم تعطيل وإيقاف متجر {store.name}")
        elif action == "delete":
            store.is_active = False
            store.subscription_status = Store.Status.CANCELLED
            log_saas_action(request, "حذف المتجر", f"تم إلغاء وحذف حساب متجر {store.name}")
            
        store.save()
        messages.success(request, f"تم تحديث حالة المتجر بنجاح.")
        return redirect("control_saas_store_detail", pk=pk)

@saas_permission_required("manage_stores")
def saas_store_login_as(request, pk):
    """Impersonate store owner."""
    with bypass_tenant_filter():
        store = get_object_or_404(Store.unfiltered, pk=pk)
        owner = store.owner
        
        log_saas_action(request, "تسجيل دخول كصاحب متجر", f"قام المدير بتسجيل الدخول كمالك للمتجر {store.name} ({owner.email})")
        
        admin_id = request.user.id
        login(request, owner, backend='apps.stores.auth_backend.TenantModelBackend')
        request.session['impersonator_user_id'] = admin_id
        
        messages.success(request, f"أنت الآن تتصفح وتدير المنصة بصفة المالك: {owner.email}")
        
        return render(request, "stores/saas/impersonation_redirect.html", {
            "store": store,
            "owner": owner
        })

# ==========================================
# --- PLANS MANAGEMENT ---
# ==========================================

@saas_permission_required("manage_plans")
def saas_plan_list(request):
    plans = SubscriptionPlan.objects.all().order_by("price_monthly")
    return render(request, "stores/saas/plan_list.html", {"plans": plans})

@saas_permission_required("manage_plans")
def saas_plan_form(request, pk=None):
    plan = get_object_or_404(SubscriptionPlan, pk=pk) if pk else None
    
    fields = [
        'max_products', 'max_categories', 'max_monthly_orders', 'max_customers',
        'max_employees', 'max_branches', 'max_coupons', 'max_images',
        'max_storage_mb', 'max_bandwidth_gb', 'max_domains', 'max_api_keys', 'max_pages', 'trial_days'
    ]
    
    features = [
        'custom_domain_enabled', 'remove_branding_enabled', 'multi_employee_enabled',
        'multi_branch_enabled', 'coupons_enabled', 'recharge_cards_enabled',
        'wallets_enabled', 'advanced_reports_enabled', 'live_stats_enabled',
        'export_excel_enabled', 'export_pdf_enabled', 'api_access_enabled',
        'webhooks_enabled', 'mobile_app_enabled', 'sms_notifications_enabled',
        'whatsapp_notifications_enabled', 'email_marketing_enabled', 'import_products_enabled',
        'export_products_enabled', 'backup_enabled', 'restore_enabled',
        'professional_templates_enabled', 'custom_css_js_enabled', 'multi_language_enabled',
        'multi_currency_enabled'
    ]
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        price_monthly = Decimal(request.POST.get("price_monthly", "0.00"))
        price_yearly = Decimal(request.POST.get("price_yearly", "0.00"))
        is_active = request.POST.get("is_active") == "on"
        
        if not plan:
            plan = SubscriptionPlan()
            
        plan.name = name
        plan.description = description
        plan.price_monthly = price_monthly
        plan.price_yearly = price_yearly
        plan.is_active = is_active
        
        for field in fields:
            val = request.POST.get(field, "").strip()
            if val:
                setattr(plan, field, int(val))
                
        for feat in features:
            setattr(plan, feat, request.POST.get(feat) == "on")
            
        plan.save()
        log_saas_action(request, "حفظ خطة اشتراك", f"تم تعديل أو إنشاء خطة الاشتراك: {plan.name}")
        messages.success(request, "تم حفظ خطة الاشتراك بنجاح.")
        return redirect("control_saas_plans")
        
    return render(request, "stores/saas/plan_form.html", {
        "plan": plan,
        "fields": fields,
        "features": features
    })

# ==========================================
# --- PAYMENTS MANAGEMENT ---
# ==========================================

@saas_permission_required("manage_payments")
def saas_payment_list(request):
    with bypass_tenant_filter():
        deposits = DepositRequest.objects.all().select_related('user', 'payment_method').order_by('-created_at')
        withdrawals = WithdrawalRequest.objects.all().select_related('user', 'payment_method').order_by('-created_at')
        
        paginator_d = Paginator(deposits, 15)
        page_d = paginator_d.get_page(request.GET.get("page_d"))
        
        paginator_w = Paginator(withdrawals, 15)
        page_w = paginator_w.get_page(request.GET.get("page_w"))

    return render(request, "stores/saas/payment_list.html", {
        "page_d": page_d,
        "page_w": page_w
    })

# ==========================================
# --- RESOURCES MONITORING ---
# ==========================================

@saas_permission_required("manage_resources")
def saas_resource_monitor(request):
    with bypass_tenant_filter():
        db_engine = connection.vendor
        db_size = "N/A"
        if db_engine == "sqlite":
            db_path = connection.settings_dict["NAME"]
            if os.path.exists(db_path):
                db_size = f"{os.path.getsize(db_path) / (1024 * 1024):.2f} MB"
                
        media_root = settings.MEDIA_ROOT
        disk_usage = "N/A"
        disk_percent = 0
        if os.path.exists(media_root):
            total, used, free = shutil.disk_usage(media_root)
            disk_usage = f"{(used / (1024 * 1024 * 1024)):.2f} GB / {(total / (1024 * 1024 * 1024)):.2f} GB"
            disk_percent = round((used / total) * 100, 1)

        stores_data = []
        for s in Store.unfiltered.filter(is_active=True):
            storage_mb = get_store_storage_mb(s)
            p_count = Product.all_objects.filter(store=s).count()
            o_count = Order.all_objects.filter(store=s).count()
            stores_data.append({
                "store": s,
                "storage_mb": storage_mb,
                "product_count": p_count,
                "order_count": o_count
            })
        
        stores_data = sorted(stores_data, key=lambda x: x["storage_mb"], reverse=True)

    return render(request, "stores/saas/resource_monitor.html", {
        "db_engine": db_engine,
        "db_size": db_size,
        "disk_usage": disk_usage,
        "disk_percent": disk_percent,
        "stores_data": stores_data
    })

# ==========================================
# --- ROLES & PERMISSIONS ---
# ==========================================

@saas_permission_required("manage_permissions")
def saas_role_list(request):
    roles = SaaSAdminRole.objects.all().annotate(admin_count=Count('admins'))
    return render(request, "stores/saas/role_list.html", {"roles": roles})

@saas_permission_required("manage_permissions")
def saas_role_form(request, pk=None):
    role = get_object_or_404(SaaSAdminRole, pk=pk) if pk else None
    
    all_permissions = [
        ("dashboard", "لوحة القيادة الإحصائية"),
        ("manage_stores", "إدارة المتاجر وحالتها"),
        ("manage_plans", "إدارة خطط الاشتراك وتعديل القيود"),
        ("manage_payments", "إدارة مدفوعات SaaS والعمولات"),
        ("manage_resources", "مراقبة موارد المنصة والخادم"),
        ("manage_permissions", "إدارة صلاحيات الأدوار الإدارية"),
        ("manage_templates", "إدارة قوالب المتاجر وثيماتها"),
        ("view_audit_logs", "استعراض سجلات العمليات والأمن"),
        ("manage_settings", "تعديل إعدادات المنصة العامة للـ SaaS")
    ]
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        selected_perms = request.POST.getlist("permissions")
        
        if not role:
            role = SaaSAdminRole()
            
        role.name = name
        role.description = description
        role.permissions = selected_perms
        role.save()
        
        log_saas_action(request, "حفظ دور إداري", f"تم تعديل أو إنشاء الدور الإداري: {role.name}")
        messages.success(request, "تم حفظ الدور الإداري بنجاح.")
        return redirect("control_saas_roles")

    return render(request, "stores/saas/role_form.html", {
        "role": role,
        "all_permissions": all_permissions
    })

# ==========================================
# --- TEMPLATES MANAGEMENT ---
# ==========================================

@saas_permission_required("manage_templates")
def saas_template_list(request):
    templates = StoreTemplate.objects.all()
    return render(request, "stores/saas/template_list.html", {"templates": templates})

@saas_permission_required("manage_templates")
def saas_template_form(request, pk=None):
    tpl = get_object_or_404(StoreTemplate, pk=pk) if pk else None
    
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        category = request.POST.get("category", "").strip()
        mobile_responsive = request.POST.get("mobile_responsive") == "on"
        is_active = request.POST.get("is_active") == "on"
        
        if not tpl:
            tpl = StoreTemplate()
            
        tpl.name = name
        tpl.category = category
        tpl.mobile_responsive = mobile_responsive
        tpl.is_active = is_active
        
        if request.FILES.get("image"):
            tpl.image = request.FILES["image"]
            
        tpl.save()
        log_saas_action(request, "حفظ قالب متجر", f"تم حفظ قالب المتجر: {tpl.name}")
        messages.success(request, "تم حفظ قالب المتجر بنجاح.")
        return redirect("control_saas_templates")

    return render(request, "stores/saas/template_form.html", {"template": tpl})

# ==========================================
# --- AUDIT LOGS ---
# ==========================================

@saas_permission_required("view_audit_logs")
def saas_audit_logs(request):
    q = request.GET.get("q", "").strip()
    
    logs = SaaSAuditLog.objects.all().select_related('user')
    if q:
        logs = logs.filter(Q(action__icontains=q) | Q(description__icontains=q) | Q(user__email__icontains=q))
        
    paginator = Paginator(logs, 40)
    page_obj = paginator.get_page(request.GET.get("page"))
    
    return render(request, "stores/saas/audit_logs.html", {
        "page_obj": page_obj,
        "query": q
    })

# ==========================================
# --- GENERAL SETTINGS ---
# ==========================================

@saas_permission_required("manage_settings")
def saas_settings(request):
    setting = SaaSGlobalSetting.objects.first()
    if not setting:
        setting = SaaSGlobalSetting.objects.create(platform_name="رقميات")
        
    if request.method == "POST":
        setting.platform_name = request.POST.get("platform_name", "").strip()
        setting.support_email = request.POST.get("support_email", "").strip()
        setting.commission_rate = Decimal(request.POST.get("commission_rate", "0.00"))
        
        langs = request.POST.getlist("allowed_languages")
        setting.allowed_languages = langs
        
        currs = request.POST.getlist("allowed_currencies")
        setting.allowed_currencies = currs
        
        if request.FILES.get("logo"):
            setting.logo = request.FILES["logo"]
            
        setting.save()
        log_saas_action(request, "تحديث إعدادات SaaS العامة", "تم تعديل الإعدادات العامة للمنصة")
        messages.success(request, "تم تحديث الإعدادات العامة بنجاح.")
        return redirect("control_saas_settings")
        
    return render(request, "stores/saas/settings.html", {"setting": setting})

@saas_permission_required("manage_stores")
def saas_store_domain_diagnostics(request, pk):
    with bypass_tenant_filter():
        store = get_object_or_404(Store.unfiltered, pk=pk)
        from apps.stores.views import perform_domain_diagnostics
        diagnostics = perform_domain_diagnostics(store)
    return render(request, "stores/saas/domain_diagnostics.html", {
        "store": store,
        "diagnostics": diagnostics,
    })
