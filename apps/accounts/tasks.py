from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from apps.accounts.models import User, ActivityLog
from apps.accounts.services import send_brevo_email

@shared_task
def cleanup_unverified_users_task():
    """
    Deletes users who haven't verified their email within 24 hours.
    Sends a reminder email to users who haven't verified within 12 hours.
    """
    now = timezone.now()
    
    # 1. Cleanup: Older than 24 hours
    threshold_delete = now - timedelta(hours=24)
    unverified_to_delete = User.objects.filter(
        email_verified=False, 
        is_staff=False,
        is_superuser=False,
        date_joined__lt=threshold_delete
    )
    
    count_deleted = 0
    for user in unverified_to_delete:
        email = user.email
        name = user.get_full_name() or email
        subject = "إشعار حذف الحساب لعدم التفعيل | Raqamiyat"
        html_content = f"""
        <div dir="rtl" style="font-family: sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
            <h2 style="color: #ef4444;">رقميات | RAQAMIYAT</h2>
            <p>مرحباً {name}،</p>
            <p>نحيطك علماً بأنه تم حذف حسابك ({email}) نظراً لعدم إتمام عملية تفعيل البريد الإلكتروني خلال المهلة المحددة (24 ساعة).</p>
            <p>إذا كنت لا تزال ترغب في استخدام خدماتنا، يمكنك إنشاء حساب جديد في أي وقت.</p>
            <hr>
            <p style="font-size: 12px; color: #999;">© 2026 مؤسسة رامي قصاص بن ماهر لخدمات الوساطة الرقمية.</p>
        </div>
        """
        send_brevo_email(email, name, subject, html_content)
        user.delete()
        count_deleted += 1
    
    # 2. Reminders: Between 12 and 24 hours
    threshold_remind = now - timedelta(hours=12)
    
    users_to_remind = User.objects.filter(
        email_verified=False,
        is_staff=False,
        date_joined__lt=threshold_remind,
        date_joined__gt=threshold_delete
    ).exclude(activities__action="deletion_reminder_sent")
    
    count_reminded = 0
    for user in users_to_remind:
        subject = "تنبيه: تبقت 12 ساعة لتفعيل حسابك | Raqamiyat"
        html_content = f"""
        <div dir="rtl" style="font-family: sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
            <h2 style="color: #f59e0b;">رقميات | RAQAMIYAT</h2>
            <p>مرحباً {user.get_full_name() or user.email}،</p>
            <p>نلاحظ أنك لم تقم بتفعيل حسابك بعد. يرجى العلم أنه سيتم حذف الحساب تلقائياً خلال 12 ساعة إذا لم يتم التحقق من البريد الإلكتروني.</p>
            <p style="font-weight: bold;">يرجى تسجيل الدخول وإدخال رمز التحقق لتجنب حذف بياناتك.</p>
            <hr>
            <p style="font-size: 12px; color: #999;">إذا قمت بالتفعيل بالفعل، يرجى تجاهل هذا البريد.</p>
        </div>
        """
        if send_brevo_email(user.email, user.get_full_name() or user.email, subject, html_content):
            ActivityLog.objects.create(user=user, action="deletion_reminder_sent", description="Sent 12h deletion warning")
            count_reminded += 1
            
    return f"Deleted {count_deleted} users, Reminded {count_reminded} users."

@shared_task
def reset_daily_limits_task():
    """
    Resets daily deposit and withdrawal usage for all users.
    Should be scheduled to run at 12:00 AM Syria time (9:00 PM UTC).
    """
    now = timezone.now()
    updated_count = User.objects.all().update(
        daily_deposit_usage=Decimal("0.00"),
        daily_withdrawal_usage=Decimal("0.00"),
        last_limit_reset=now
    )
    return f"Reset daily limits for {updated_count} users at {now}."


@shared_task
def scheduled_backup_task():
    """
    Hourly scheduled backup task.
    Reads configuration from Django cache (set via control_backup view).
    Generates a ZIP with the configured models and sends it to the configured email.
    """
    import io
    import json
    import zipfile
    import base64
    import datetime
    from django.core import serializers
    from django.apps import apps as django_apps
    from django.core.cache import cache

    schedule_enabled = cache.get("backup_schedule_enabled", False)
    if not schedule_enabled:
        return "Scheduled backup is disabled. Skipping."

    schedule_frequency = cache.get("backup_schedule_frequency", "hourly")
    last_run_timestamp = cache.get("backup_last_run_timestamp", 0)
    import time
    now_ts = time.time()

    freq_intervals = {
        "hourly": 3600,
        "every_3_hours": 10800,
        "every_6_hours": 21600,
        "every_12_hours": 43200,
        "daily": 86400,
        "weekly": 604800,
    }
    interval = freq_intervals.get(schedule_frequency, 3600)
    if last_run_timestamp and (now_ts - last_run_timestamp) < (interval - 300):
        return f"Skipping backup: frequency '{schedule_frequency}' interval not elapsed yet."

    email_address = cache.get("backup_schedule_email", "")
    backup_targets = cache.get("backup_schedule_targets", [])

    if not email_address:
        return "No email configured for scheduled backup. Skipping."

    BACKUP_MODELS = {
        "users": ("accounts", "User", "المستخدمون"),
        "wallets": ("wallets", "Wallet", "المحافظ"),
        "deposits": ("payments", "DepositRequest", "طلبات الإيداع"),
        "withdrawals": ("payments", "WithdrawalRequest", "طلبات السحب"),
        "orders": ("orders", "Order", "الطلبات"),
        "products": ("catalog", "Product", "المنتجات"),
        "categories": ("catalog", "Category", "التصنيفات"),
        "currencies": ("common", "Currency", "العملات"),
        "coupons": ("orders", "Coupon", "الكوبونات"),
        "payment_methods": ("payments", "PaymentMethod", "وسائل الدفع"),
        "transfers": ("wallets", "BalanceTransfer", "التحويلات"),
        "kyc": ("accounts", "KYCRequest", "طلبات التوثيق"),
        "audit_logs": ("common", "SystemAuditLog", "سجلات التدقيق"),
        "announcements": ("common", "SiteAnnouncement", "الإعلانات"),
    }

    try:
        zip_buffer = io.BytesIO()
        total_records = 0
        manifest = {
            "backup_time": datetime.datetime.now().isoformat(),
            "initiated_by": "scheduled_task",
            "targets": [],
        }

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for key, (app_label, model_name, label) in BACKUP_MODELS.items():
                if key not in backup_targets:
                    continue
                try:
                    Model = django_apps.get_model(app_label, model_name)
                    qs = Model.objects.all()
                    data = serializers.serialize("json", qs)
                    count = qs.count()
                    total_records += count
                    zf.writestr(f"{key}.json", data)
                    manifest["targets"].append({"key": key, "label": label, "count": count})
                except Exception as model_err:
                    manifest["targets"].append({"key": key, "label": label, "error": str(model_err)})

            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        zip_buffer.seek(0)
        zip_b64 = base64.b64encode(zip_buffer.read()).decode("utf-8")

        now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"backup_{now_str}.zip"

        included_labels = [BACKUP_MODELS[t][2] for t in backup_targets if t in BACKUP_MODELS]
        html_content = f"""
        <div dir="rtl" style="font-family: Arial, sans-serif; max-width: 600px; margin: auto;">
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from apps.accounts.models import User, ActivityLog
from apps.accounts.services import send_brevo_email

@shared_task
def cleanup_unverified_users_task():
    """
    Deletes users who haven't verified their email within 24 hours.
    Sends a reminder email to users who haven't verified within 12 hours.
    """
    now = timezone.now()
    
    # 1. Cleanup: Older than 24 hours
    threshold_delete = now - timedelta(hours=24)
    unverified_to_delete = User.objects.filter(
        email_verified=False, 
        is_staff=False,
        is_superuser=False,
        date_joined__lt=threshold_delete
    )
    
    count_deleted = 0
    for user in unverified_to_delete:
        email = user.email
        name = user.get_full_name() or email
        subject = "إشعار حذف الحساب لعدم التفعيل | Raqamiyat"
        html_content = f"""
        <div dir="rtl" style="font-family: sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
            <h2 style="color: #ef4444;">رقميات | RAQAMIYAT</h2>
            <p>مرحباً {name}،</p>
            <p>نحيطك علماً بأنه تم حذف حسابك ({email}) نظراً لعدم إتمام عملية تفعيل البريد الإلكتروني خلال المهلة المحددة (24 ساعة).</p>
            <p>إذا كنت لا تزال ترغب في استخدام خدماتنا، يمكنك إنشاء حساب جديد في أي وقت.</p>
            <hr>
            <p style="font-size: 12px; color: #999;">© 2026 مؤسسة رامي قصاص بن ماهر لخدمات الوساطة الرقمية.</p>
        </div>
        """
        send_brevo_email(email, name, subject, html_content)
        user.delete()
        count_deleted += 1
    
    # 2. Reminders: Between 12 and 24 hours
    threshold_remind = now - timedelta(hours=12)
    
    users_to_remind = User.objects.filter(
        email_verified=False,
        is_staff=False,
        date_joined__lt=threshold_remind,
        date_joined__gt=threshold_delete
    ).exclude(activities__action="deletion_reminder_sent")
    
    count_reminded = 0
    for user in users_to_remind:
        subject = "تنبيه: تبقت 12 ساعة لتفعيل حسابك | Raqamiyat"
        html_content = f"""
        <div dir="rtl" style="font-family: sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
            <h2 style="color: #f59e0b;">رقميات | RAQAMIYAT</h2>
            <p>مرحباً {user.get_full_name() or user.email}،</p>
            <p>نلاحظ أنك لم تقم بتفعيل حسابك بعد. يرجى العلم أنه سيتم حذف الحساب تلقائياً خلال 12 ساعة إذا لم يتم التحقق من البريد الإلكتروني.</p>
            <p style="font-weight: bold;">يرجى تسجيل الدخول وإدخال رمز التحقق لتجنب حذف بياناتك.</p>
            <hr>
            <p style="font-size: 12px; color: #999;">إذا قمت بالتفعيل بالفعل، يرجى تجاهل هذا البريد.</p>
        </div>
        """
        if send_brevo_email(user.email, user.get_full_name() or user.email, subject, html_content):
            ActivityLog.objects.create(user=user, action="deletion_reminder_sent", description="Sent 12h deletion warning")
            count_reminded += 1
            
    return f"Deleted {count_deleted} users, Reminded {count_reminded} users."

@shared_task
def reset_daily_limits_task():
    """
    Resets daily deposit and withdrawal usage for all users.
    Should be scheduled to run at 12:00 AM Syria time (9:00 PM UTC).
    """
    now = timezone.now()
    updated_count = User.objects.all().update(
        daily_deposit_usage=Decimal("0.00"),
        daily_withdrawal_usage=Decimal("0.00"),
        last_limit_reset=now
    )
    return f"Reset daily limits for {updated_count} users at {now}."


@shared_task
def scheduled_backup_task():
    """
    Hourly scheduled backup task.
    Reads configuration from Django cache (set via control_backup view).
    Generates a ZIP with the configured models and sends it to the configured email.
    """
    import io
    import json
    import zipfile
    import base64
    import datetime
    from django.core import serializers
    from django.apps import apps as django_apps
    from django.core.cache import cache

    schedule_enabled = cache.get("backup_schedule_enabled", False)
    if not schedule_enabled:
        return "Scheduled backup is disabled. Skipping."

    schedule_frequency = cache.get("backup_schedule_frequency", "hourly")
    last_run_timestamp = cache.get("backup_last_run_timestamp", 0)
    import time
    now_ts = time.time()

    freq_intervals = {
        "hourly": 3600,
        "every_3_hours": 10800,
        "every_6_hours": 21600,
        "every_12_hours": 43200,
        "daily": 86400,
        "weekly": 604800,
    }
    interval = freq_intervals.get(schedule_frequency, 3600)
    if last_run_timestamp and (now_ts - last_run_timestamp) < (interval - 300):
        return f"Skipping backup: frequency '{schedule_frequency}' interval not elapsed yet."

    email_address = cache.get("backup_schedule_email", "")
    backup_targets = cache.get("backup_schedule_targets", [])

    if not email_address:
        return "No email configured for scheduled backup. Skipping."

    BACKUP_MODELS = {
        "users": ("accounts", "User", "المستخدمون"),
        "wallets": ("wallets", "Wallet", "المحافظ"),
        "deposits": ("payments", "DepositRequest", "طلبات الإيداع"),
        "withdrawals": ("payments", "WithdrawalRequest", "طلبات السحب"),
        "orders": ("orders", "Order", "الطلبات"),
        "products": ("catalog", "Product", "المنتجات"),
        "categories": ("catalog", "Category", "التصنيفات"),
        "currencies": ("common", "Currency", "العملات"),
        "coupons": ("orders", "Coupon", "الكوبونات"),
        "payment_methods": ("payments", "PaymentMethod", "وسائل الدفع"),
        "transfers": ("wallets", "BalanceTransfer", "التحويلات"),
        "kyc": ("accounts", "KYCRequest", "طلبات التوثيق"),
        "audit_logs": ("common", "SystemAuditLog", "سجلات التدقيق"),
        "announcements": ("common", "SiteAnnouncement", "الإعلانات"),
    }

    try:
        zip_buffer = io.BytesIO()
        total_records = 0
        manifest = {
            "backup_time": datetime.datetime.now().isoformat(),
            "initiated_by": "scheduled_task",
            "targets": [],
        }

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for key, (app_label, model_name, label) in BACKUP_MODELS.items():
                if key not in backup_targets:
                    continue
                try:
                    Model = django_apps.get_model(app_label, model_name)
                    qs = Model.objects.all()
                    data = serializers.serialize("json", qs)
                    count = qs.count()
                    total_records += count
                    zf.writestr(f"{key}.json", data)
                    manifest["targets"].append({"key": key, "label": label, "count": count})
                except Exception as model_err:
                    manifest["targets"].append({"key": key, "label": label, "error": str(model_err)})

            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        zip_buffer.seek(0)
        zip_b64 = base64.b64encode(zip_buffer.read()).decode("utf-8")

        now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"backup_{now_str}.zip"

        included_labels = [BACKUP_MODELS[t][2] for t in backup_targets if t in BACKUP_MODELS]
        html_content = f"""
        <div dir="rtl" style="font-family: Arial, sans-serif; max-width: 600px; margin: auto;">
            <h2 style="color: #06b6d4;">📦 نسخة احتياطية مجدولة — كل ساعة</h2>
            <p>تم إنشاء النسخة الاحتياطية التلقائية بنجاح في <strong>{now_str}</strong>.</p>
            <ul>
                <li>عدد السجلات المُصدَّرة: <strong>{total_records:,}</strong></li>
                <li>البيانات المُضمَّنة: {', '.join(included_labels)}</li>
            </ul>
            <p style="font-size: 12px; color: #999;">هذا البريد يُرسل تلقائياً كل ساعة. الملف المرفق بصيغة ZIP.</p>
        </div>
        """

        send_brevo_email(
            to_email=email_address,
            to_name="مدير الموقع",
            subject=f"📦 نسخة احتياطية مجدولة — {now_str}",
            html_content=html_content,
            attachments=[{
                "name": filename,
                "content": zip_b64,
                "type": "application/zip",
            }]
        )

        cache.set("backup_last_run_timestamp", now_ts, timeout=None)
        return f"Scheduled backup sent to {email_address}. Records: {total_records}"

    except Exception as e:
        return f"Scheduled backup FAILED: {str(e)}"


@shared_task
def sync_pending_api_orders_task():
    """
    Periodically checks pending and processing API orders against providers using ProviderManager.
    Updates order statuses (COMPLETED, CANCELLED) and automatically refunds customer wallets
    if the order is rejected or cancelled by the provider.
    """
    from apps.orders.models import Order
    from apps.orders.provider_status import apply_provider_status
    from services.provider.manager import ProviderManager

    orders = (
        Order.objects
        .filter(
            status=Order.Status.PROCESSING,
            items__variant__api_product_id__isnull=False,
        )
        .select_related("customer")
        .prefetch_related("provider_orders__profile")
        .distinct()[:100]
    )

    checked = 0
    updated = 0
    errors = 0

    for order in orders:
        provider_order = order.provider_orders.select_related("profile").first()
        if not provider_order or not provider_order.profile:
            continue
        try:
            identifiers = [str(order.api_order_uuid)] if order.api_order_uuid else ([str(order.api_order_id)] if order.api_order_id else [])
            if not identifiers:
                continue
            data_list = ProviderManager.check_orders(
                provider_order.profile,
                identifiers,
                is_uuid=bool(order.api_order_uuid)
            )
            checked += 1
            if not data_list:
                continue
            old_status = order.status
            order = apply_provider_status(
                order,
                data_list[0].get("status"),
                raw_response=data_list[0],
                actor=None,
                note_prefix="فحص تلقائي",
            )
            if order.status != old_status:
                updated += 1
        except Exception:
            errors += 1

    return f"Checked {checked} API orders, updated {updated}, errors {errors}."
