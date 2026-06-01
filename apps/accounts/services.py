from apps.notifications.services import notify_user
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.conf import settings
from django.core.mail import send_mail
import logging

logger = logging.getLogger(__name__)

def send_verification_email(request, user):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    path = reverse('email_verify', kwargs={'uidb64': uid, 'token': token})
    protocol = 'https' if request.is_secure() else 'http'
    domain = request.get_host()
    link = f"{protocol}://{domain}{path}"
    
    subject = "تفعيل حسابك في رقميات"
    body = f"""
    مرحباً {user.first_name}،
    
    شكراً لتسجيلك في منصة رقميات. يرجى الضغط على الرابط أدناه لتفعيل بريدك الإلكتروني:
    
    {link}
    
    إذا لم تقم بإنشاء هذا الحساب، يرجى تجاهل هذا البريد.
    
    فريق رقميات.
    """
    
    success = False
    try:
        # Standard practice is send_mail with a timeout from settings
        send_mail(
            subject, 
            body, 
            settings.DEFAULT_FROM_EMAIL, 
            [user.email], 
            fail_silently=False
        )
        success = True
    except Exception as e:
        logger.error(f"SMTP delivery failed for {user.email}: {str(e)}")
        # Log to activity for admin review
        from apps.accounts.models import ActivityLog
        ActivityLog.objects.create(
            user=user, 
            action="Email Failed", 
            description=f"Verification email failed to send (SMTP error). {str(e)[:200]}"
        )

    # Always notify in-app so they see the link even if SMTP is acting up
    notify_user(
        user=user,
        title="تفعيل البريد الإلكتروني",
        body="يرجى مراجعة بريدك الإلكتروني لتفعيل الحساب. إذا لم يصلك البريد، يمكنك إعادة الإرسال من لوحة التحكم.",
        action_url=path,
        priority="high"
    )
    return success
