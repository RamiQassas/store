from apps.notifications.services import notify_user
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.conf import settings

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
    
    # We will use Django's core send_mail if configured, 
    # but for now we log it and send an in-app notification as fallback 
    # since we want to keep it "FREE" and the user might not have SMTP yet.
    # However, standard practice is send_mail.
    
    from django.core.mail import send_mail
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
    except Exception as e:
        print(f"Mail delivery failed: {e}")
        # Log to activity for admin review
        from apps.accounts.models import ActivityLog
        ActivityLog.objects.create(user=user, action="Email Failed", description=f"Verification email failed to send: {str(e)}")

    # Also notify in-app so they see the link if email fails in dev/free environment
    notify_user(
        user=user,
        title="تفعيل البريد الإلكتروني",
        body="يرجى مراجعة بريدك الإلكتروني لتفعيل الحساب والتمكن من الوصول لجميع الميزات.",
        action_url=path,
        priority="high"
    )
