import requests
import json
import logging
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from apps.notifications.services import notify_user

logger = logging.getLogger(__name__)

def send_brevo_email(to_email, to_name, subject, html_content, text_content=None):
    """
    Sends an email using Brevo Transactional Email API.
    """
    if not settings.BREVO_API_KEY:
        logger.warning("BREVO_API_KEY is not set. Email not sent.")
        return False

    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json",
    }

    payload = {
        "sender": {
            "name": settings.DEFAULT_FROM_NAME,
            "email": settings.DEFAULT_FROM_EMAIL
        },
        "to": [
            {
                "email": to_email,
                "name": to_name
            }
        ],
        "subject": subject,
        "htmlContent": html_content
    }
    
    if text_content:
        payload["textContent"] = text_content

    try:
        response = requests.post(
            settings.BREVO_API_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=10
        )
        if response.status_code in [200, 201, 202]:
            return True
        else:
            logger.error(f"Brevo API error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Brevo connection error: {str(e)}")
        return False


import secrets
from datetime import timedelta
from django.utils import timezone
from apps.accounts.models import EmailVerificationToken

def send_verification_email(request, user):
    """
    Generates a secure verification link and sends a branded HTML email via Brevo API.
    Uses EmailVerificationToken model to decouple from session state.
    """
    # Invalidate previous unused tokens
    EmailVerificationToken.objects.filter(user=user, is_used=False).update(is_used=True)
    
    token_str = secrets.token_urlsafe(64)
    expires_at = timezone.now() + timedelta(hours=24)
    
    EmailVerificationToken.objects.create(
        user=user,
        token=token_str,
        expires_at=expires_at
    )
    
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    path = reverse('email_verify', kwargs={'uidb64': uid, 'token': token_str})
    protocol = 'https' if request.is_secure() else 'http'
    domain = request.get_host()
    link = f"{protocol}://{domain}{path}"
    
    subject = "تفعيل حسابك في رقميات | Raqamiyat"
    
    html_content = f"""
    <div dir="rtl" style="font-family: 'Cairo', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #06b6d4; margin: 0; font-size: 28px;">رقميات | Raqamiyat</h1>
        </div>
        <p style="font-size: 16px;">مرحباً <strong>{user.first_name}</strong>،</p>
        <p style="font-size: 16px; line-height: 1.6;">شكراً لتسجيلك في منصة رقميات. نحن متحمسون لانضمامك إلينا لتجربة أفضل الخدمات الرقمية.</p>
        <p style="font-size: 16px; line-height: 1.6;">يرجى تفعيل حسابك من خلال الضغط على الزر أدناه:</p>
        
        <div style="text-align: center; margin: 40px 0;">
            <a href="{link}" style="background-color: #06b6d4; color: #ffffff; padding: 14px 40px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 18px; display: inline-block;">تفعيل الحساب الآن</a>
        </div>
        
        <p style="font-size: 14px; color: #64748b;">إذا واجهت مشكلة في الضغط على الزر، يمكنك نسخ الرابط التالي ولصقه في متصفحك:</p>
        <p style="font-size: 12px; word-break: break-all; color: #06b6d4;">{link}</p>
        
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 30px 0;">
        <p style="font-size: 12px; color: #94a3b8; text-align: center;">إذا لم تقم بإنشاء هذا الحساب، يرجى تجاهل هذا البريد.<br>© 2024 رقميات - Raqamiyat. جميع الحقوق محفوظة.</p>
    </div>
    """
    
    success = send_brevo_email(
        to_email=user.email,
        to_name=f"{user.first_name} {user.last_name}",
        subject=subject,
        html_content=html_content
    )
    
    if not success:
        from apps.accounts.models import ActivityLog
        ActivityLog.objects.create(
            user=user, 
            action="Email Failed", 
            description="Verification email failed to send via Brevo API."
        )

    # Always notify in-app
    notify_user(
        user=user,
        title="تفعيل البريد الإلكتروني",
        body="يرجى مراجعة بريدك الإلكتروني لتفعيل الحساب. إذا لم يصلك البريد، يمكنك إعادة الإرسال من لوحة التحكم.",
        action_url=path,
        priority="high"
    )
    
    return success
