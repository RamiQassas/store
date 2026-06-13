from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from apps.accounts.models import User
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
        date_joined__lt=threshold_delete
    )
    count_deleted = unverified_to_delete.count()
    unverified_to_delete.delete()
    
    # 2. Reminders: Between 12 and 13 hours (to avoid multiple reminders)
    threshold_remind_start = now - timedelta(hours=13)
    threshold_remind_end = now - timedelta(hours=12)
    
    # We use a flag or check if metadata already has reminded
    users_to_remind = User.objects.filter(
        email_verified=False,
        is_staff=False,
        date_joined__range=(threshold_remind_start, threshold_remind_end)
    )
    
    count_reminded = 0
    for user in users_to_remind:
        subject = "تنبيه: تبقت 12 ساعة لتفعيل حسابك | Raqamiyat"
        html_content = f"""
        <div dir="rtl" style="font-family: sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
            <h2 style="color: #06b6d4;">رقميات | RAQAMIYAT</h2>
            <p>مرحباً {user.get_full_name() or user.email}،</p>
            <p>نلاحظ أنك لم تقم بتفعيل حسابك بعد. يرجى العلم أنه سيتم حذف الحساب تلقائياً خلال 12 ساعة إذا لم يتم التحقق من البريد الإلكتروني.</p>
            <p style="font-weight: bold;">يرجى تسجيل الدخول وإدخال رمز التحقق لتجنب حذف بياناتك.</p>
            <hr>
            <p style="font-size: 12px; color: #999;">إذا قمت بالتفعيل بالفعل، يرجى تجاهل هذا البريد.</p>
        </div>
        """
        if send_brevo_email(user.email, user.get_full_name() or user.email, subject, html_content):
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
