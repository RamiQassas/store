import json
import logging
import hashlib
from pywebpush import webpush, WebPushException
from django.conf import settings
from django.utils import timezone
from django.db import models
from apps.notifications.models import Notification, NotificationSetting, PushSubscription

logger = logging.getLogger(__name__)

def generate_deduplication_hash(user_id, title, body, metadata):
    """Generates a unique hash for a notification to prevent spam within a short window."""
    raw_str = f"{user_id}:{title}:{body}:{json.dumps(metadata or {}, sort_keys=True)}"
    return hashlib.md5(raw_str.encode()).hexdigest()

def send_web_push(subscription, payload):
    """Internal helper to deliver a single push via pywebpush."""
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh": subscription.p256dh,
                    "auth": subscription.auth
                }
            },
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={
                "sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"
            }
        )
        return True
    except WebPushException as e:
        logger.error(f"WebPush Error: {str(e)}")
        if e.response and e.response.status_code in [404, 410]:
            subscription.delete()
        return False
    except Exception as e:
        logger.error(f"Unexpected Push Error: {str(e)}")
        return False

def notify_user(user, title, body, action_url=None, image_url=None, category='system', priority=Notification.Priority.NORMAL, metadata=None, exclude_user=None):
    """
    Centralized service to notify users via multiple channels.
    category: 'orders', 'financial', 'support', 'promotions', 'kyc', 'system'
    """
    if not user.is_active or (exclude_user and user.id == exclude_user.id):
        return False

    # 1. Deduplication (Short window: 1 minute)
    dedup_hash = generate_deduplication_hash(user.id, title, body, metadata)
    one_minute_ago = timezone.now() - timezone.timedelta(minutes=1)
    if Notification.objects.filter(user=user, metadata__dedup_hash=dedup_hash, created_at__gte=one_minute_ago).exists():
        return False

    if metadata is None: metadata = {}
    metadata['dedup_hash'] = dedup_hash

    # 2. Check User Preferences
    settings_obj, _ = NotificationSetting.objects.get_or_create(user=user)
    
    if not settings_obj.is_enabled:
        return False

    send_in_app = False
    send_push = False
    send_email = False

    if category == 'orders':
        send_in_app = settings_obj.in_app_orders
        send_push = settings_obj.push_orders
        send_email = settings_obj.email_orders
    elif category == 'financial':
        send_in_app = settings_obj.in_app_financial
        send_push = settings_obj.push_financial
        send_email = settings_obj.email_financial
    elif category == 'support':
        send_in_app = settings_obj.in_app_support
        send_push = settings_obj.push_support
        send_email = settings_obj.email_support
    elif category == 'kyc':
        send_in_app = settings_obj.in_app_kyc
        send_push = settings_obj.push_kyc
        send_email = settings_obj.email_kyc
    elif category == 'promotions':
        send_in_app = settings_obj.in_app_promotions
        send_push = settings_obj.push_promotions
        send_email = settings_obj.email_promotions
    else: # system
        send_in_app = True
        send_push = True
        send_email = True

    # 3. Create In-App Notification
    if send_in_app:
        Notification.objects.create(
            user=user,
            title=title,
            body=body,
            action_url=action_url,
            image_url=image_url,
            channel=Notification.Channel.IN_APP,
            priority=priority,
            metadata=metadata
        )

    # 4. Trigger Web Push
    if send_push:
        subscriptions = PushSubscription.objects.filter(user=user)
        if subscriptions.exists():
            payload = {
                "title": title,
                "body": body,
                "action_url": action_url or "/dashboard/",
                "image": image_url,
                "tag": dedup_hash # For browser-side dedup
            }
            for sub in subscriptions:
                send_web_push(sub, payload)
                
    # 5. Trigger Email
    if send_email:
        try:
            from apps.accounts.services import send_brevo_email
            html_content = f"""
            <div dir="rtl" style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; color: #1e293b; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h2 style="color: #06b6d4; margin: 0; font-size: 24px; font-weight: 900;">رقميات | RAQAMIYAT</h2>
                </div>
                <div style="background-color: #f8fafc; padding: 30px; border-radius: 12px; text-align: center;">
                    <p style="font-size: 16px; margin-bottom: 10px; color: #64748b;">{title}</p>
                    <h1 style="font-size: 18px; font-weight: bold; color: #0f172a; margin: 0;">{body}</h1>
                </div>
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #f1f5f9; text-align: center;">
                    <p style="font-size: 12px; color: #94a3b8; line-height: 1.6;">هذه الرسالة تم إنشاؤها تلقائياً.<br>يمكنك تغيير تفضيلات الإشعارات من حسابك.</p>
                </div>
            </div>
            """
            send_brevo_email(to_email=user.email, to_name=user.get_full_name() or user.email, subject=title, html_content=html_content)
        except Exception as e:
            logger.error(f"Failed to send email notification to {user.email}: {e}")
    
    return True

def notify_bulk(users, title, body, **kwargs):
    """Sends notification to multiple users at once."""
    for user in users:
        notify_user(user, title, body, **kwargs)

def notify_staff(title, body, action_url=None, category='admin_new_support', roles=None, priority=Notification.Priority.NORMAL, metadata=None, exclude_user=None):
    """
    Sends notification to staff members based on their preferences.
    category: 'admin_new_deposit', 'admin_new_withdrawal', 'admin_new_order', 'admin_new_support', 'admin_new_kyc'
    """
    from apps.accounts.models import User
    
    # 1. Get all eligible staff
    staff_query = User.objects.filter(is_active=True)
    if roles:
        staff_query = staff_query.filter(role__in=roles)
    else:
        staff_roles = [User.Role.SUPER_ADMIN, User.Role.ADMIN, User.Role.MODERATOR, User.Role.FINANCE, User.Role.SUPPORT, User.Role.EMPLOYEE]
        staff_query = staff_query.filter(models.Q(role__in=staff_roles) | models.Q(is_staff=True) | models.Q(is_superuser=True))
    
    staff_users = staff_query.distinct()
    
    # 2. Filter and notify each staff member based on their settings
    for staff in staff_users:
        if exclude_user and staff.id == exclude_user.id:
            continue
            
        settings_obj, _ = NotificationSetting.objects.get_or_create(user=staff)
        
        # Check if this specific category is enabled for this staff member
        is_category_enabled = getattr(settings_obj, category, True)
        
        if is_category_enabled and settings_obj.is_enabled:
            # Send In-App
            Notification.objects.create(
                user=staff,
                title=title,
                body=body,
                action_url=action_url,
                channel=Notification.Channel.IN_APP,
                priority=priority,
                metadata=metadata or {}
            )
            
            # Send Email if enabled
            if settings_obj.admin_email_notifications:
                try:
                    from apps.accounts.services import send_brevo_email
                    html_content = f"""
                    <div dir="rtl" style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; color: #1e293b; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0;">
                        <div style="text-align: center; margin-bottom: 30px;">
                            <h2 style="color: #06b6d4; margin: 0; font-size: 20px; font-weight: 900;">إشعار إداري | رقميات</h2>
                        </div>
                        <div style="background-color: #f8fafc; padding: 30px; border-radius: 12px; text-align: center;">
                            <p style="font-size: 14px; margin-bottom: 10px; color: #64748b;">إشعار جديد للنظام:</p>
                            <h1 style="font-size: 18px; font-weight: bold; color: #0f172a; margin: 0;">{title}</h1>
                            <p style="margin-top: 15px; font-size: 14px; color: #334155;">{body}</p>
                            {f'<a href="{settings.SITE_URL}{action_url}" style="display: inline-block; margin-top: 25px; padding: 12px 25px; background-color: #06b6d4; color: white; text-decoration: none; border-radius: 8px; font-weight: bold;">فتح في لوحة التحكم</a>' if action_url else ''}
                        </div>
                    </div>
                    """
                    send_brevo_email(to_email=staff.email, to_name=staff.get_full_name() or staff.email, subject=f"إشعار إداري: {title}", html_content=html_content)
                except Exception as e:
                    logger.error(f"Failed to send staff email notification to {staff.email}: {e}")
    
    return True

def notify_provider_error(error_code, provider_name, product_id=None, detail=None, store=None):
    """
    Sends an urgent notification to all admin/staff when a provider returns an error.
    Especially important for error code 100 (insufficient balance).
    """
    alkasr_error_labels = {
        100: "رصيد غير كافٍ لدى المزود",
        101: "حساب موقوف",
        105: "الكمية غير متوفرة",
        106: "الكمية غير مسموح بها",
        107: "معرّف اللاعب محظور",
        108: "يتطلب التحقق بخطوتين",
        109: "المنتج محذوف أو غير موجود",
        110: "المنتج غير متاح حالياً",
        111: "حاول مرة أخرى بعد دقيقة",
        120: "مفتاح API مطلوب",
        121: "مفتاح API خاطئ",
        122: "الاستخدام غير مسموح",
        123: "IP غير مسموح",
        130: "المزود تحت الصيانة",
        500: "خطأ داخلي في المزود",
    }
    label = alkasr_error_labels.get(error_code, f"خطأ {error_code}")
    is_critical = error_code in (100, 120, 121, 122, 123, 130)
    
    priority = Notification.Priority.HIGH if is_critical else Notification.Priority.NORMAL
    
    title = f"⚠️ تنبيه مزود الخدمة: {label}"
    body_parts = [
        f"المزود: {provider_name}",
        f"كود الخطأ: ERR-{error_code}",
    ]
    if product_id:
        body_parts.append(f"رقم المنتج: {product_id}")
    if detail:
        body_parts.append(f"التفاصيل: {detail}")
    if store:
        body_parts.append(f"المتجر: {store}")
    
    body = " | ".join(body_parts)
    
    logger.warning(f"[Provider Alert] {title}: {body}")
    
    notify_staff(
        title=title,
        body=body,
        action_url="/control/alkasr/",
        category="admin_provider_alert",
        priority=priority,
        metadata={
            "error_code": error_code,
            "provider": provider_name,
            "product_id": product_id,
        }
    )
