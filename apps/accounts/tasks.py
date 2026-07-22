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
            <p style="color: #64748b; font-size: 12px;">هذا البريد يُرسل تلقائياً كل ساعة. الملف المرفق بصيغة ZIP.</p>
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
    Periodically checks pending and processing API orders against Alkasr VIP / API providers.
    Updates order statuses (COMPLETED, CANCELLED) and automatically refunds customer wallets
    if the order is rejected or cancelled by the provider.
    """
    from django.db.models import Q
    from django.db import transaction
    from apps.orders.models import Order, OrderLog
    from apps.orders.alkasr_api import check_alkasr_orders
    from apps.wallets.services import get_or_create_wallet, credit_wallet
    from apps.notifications.services import notify_user

    pending_orders = Order.objects.filter(
        status__in=[Order.Status.PENDING, Order.Status.PROCESSING]
    ).filter(
        Q(api_order_uuid__isnull=False) | Q(api_order_id__isnull=False)
    )

    checked_count = 0
    updated_count = 0

    for order in pending_orders:
        checked_count += 1
        try:
            if order.api_order_uuid:
                res = check_alkasr_orders(str(order.api_order_uuid), is_uuid=True, store=order.store)
            else:
                res = check_alkasr_orders([order.api_order_id], is_uuid=False, store=order.store)

            if not res or res.get("status") != "OK" or not isinstance(res.get("data"), list) or not res["data"]:
                continue

            order_data = res["data"][0]
            api_status = str(order_data.get("status", "")).lower()

            old_status = order.status
            new_status = None

            # Extract delivered keys/codes if available
            keys_delivered = []
            possible_key_fields = ["card", "code", "serial", "pin", "key", "keys", "cards", "serial_number"]
            for field in possible_key_fields:
                val = order_data.get(field)
                if val:
                    if isinstance(val, list):
                        keys_delivered.extend([str(x) for x in val])
                    else:
                        keys_delivered.append(str(val))

            if api_status in ["accept", "completed", "success"]:
                new_status = Order.Status.COMPLETED
            elif api_status in ["reject", "cancelled", "canceled", "failed", "refused"]:
                new_status = Order.Status.CANCELLED
            elif api_status in ["wait", "pending", "processing"]:
                new_status = Order.Status.PROCESSING

            if new_status and (new_status != old_status or keys_delivered):
                with transaction.atomic():
                    order.status = new_status
                    if keys_delivered:
                        order.fulfillment_data["الرموز المسلمة (API)"] = ", ".join(keys_delivered)
                    order.fulfillment_data["api_last_auto_check"] = api_status
                    order.save(update_fields=["status", "fulfillment_data", "updated_at"])

                    note = f"تحديث تلقائي من المزود: {api_status}"
                    if new_status == Order.Status.CANCELLED:
                        note = "تم رفض/إلغاء الطلب من المزود تلقائياً. تم إرجاع المبلغ لمحفظة المستلم."
                        # Refund customer wallet
                        wallet = get_or_create_wallet(order.customer)
                        refund_amount = order.total_amount
                        if wallet.currency and wallet.currency.code != "USD":
                            refund_amount = wallet.currency.from_base(order.total_amount)

                        credit_wallet(
                            wallet_id=wallet.id,
                            amount=refund_amount,
                            reference=f"refund:{order.id}",
                            description=f"استرداد تلقائي لإلغاء/رفض الطلب #{order.number} من المزود",
                            created_by=None,
                            source="system",
                            reason="فشل تنفيذ الطلب من المزود تلقائياً"
                        )
                    elif new_status == Order.Status.COMPLETED and keys_delivered:
                        note += f" | الأكواد المستلمة: {', '.join(keys_delivered)}"

                    OrderLog.objects.create(
                        order=order,
                        status=new_status,
                        note=note,
                        created_by=None
                    )

                    try:
                        notify_user(
                            user=order.customer,
                            title=f"تحديث حالة الطلب #{order.number}",
                            body=f"تم تغيير حالة طلبك رقم #{order.number} إلى: {order.get_status_display()}",
                            action_url=f"/dashboard/orders/{order.id}/",
                            category="orders"
                        )
                    except Exception:
                        pass

                    updated_count += 1

        except Exception as e:
            continue

    return f"Checked {checked_count} API orders, updated {updated_count} orders."
