import random
import string
from datetime import timedelta
from django.utils import timezone
from apps.accounts.models import OTPToken
from apps.accounts.services import send_brevo_email

def generate_otp(user, purpose):
    """Generates a 6-digit OTP code and saves it."""
    # Invalidate old OTPs for this purpose
    OTPToken.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    
    code = ''.join(random.choices(string.digits, k=6))
    expires_at = timezone.now() + timedelta(minutes=10)
    
    return OTPToken.objects.create(
        user=user,
        code=code,
        purpose=purpose,
        expires_at=expires_at
    )

def send_otp_email(user, otp_token):
    """Sends the OTP code via email."""
    subject = "رمز التحقق | Raqamiyat"
    
    purpose_text = "لتفعيل حسابك" if otp_token.purpose == OTPToken.Purpose.REGISTRATION else \
                   "لتسجيل الدخول" if otp_token.purpose == OTPToken.Purpose.LOGIN else \
                   "لإعادة تعيين كلمة المرور"
    
    html_content = f"""
    <div dir="rtl" style="font-family: 'Cairo', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #06b6d4; margin: 0; font-size: 28px;">رقميات | Raqamiyat</h1>
        </div>
        <p style="font-size: 16px;">مرحباً <strong>{user.first_name or user.email}</strong>،</p>
        <p style="font-size: 16px; line-height: 1.6;">رمز التحقق الخاص بك {purpose_text} هو:</p>
        
        <div style="text-align: center; margin: 40px 0;">
            <div style="background-color: #f1f5f9; color: #0f172a; padding: 20px; border-radius: 12px; font-weight: bold; font-size: 32px; letter-spacing: 10px; display: inline-block; border: 1px solid #e2e8f0;">
                {otp_token.code}
            </div>
        </div>
        
        <p style="font-size: 14px; color: #64748b; text-align: center;">هذا الرمز صالح لمدة 10 دقائق فقط. لا تشارك هذا الرمز مع أي شخص.</p>
        
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 30px 0;">
        <p style="font-size: 12px; color: #94a3b8; text-align: center;">© 2024 رقميات - Raqamiyat. جميع الحقوق محفوظة.</p>
    </div>
    """
    
    return send_brevo_email(
        to_email=user.email,
        to_name=f"{user.first_name} {user.last_name}",
        subject=subject,
        html_content=html_content
    )

def verify_otp(user, code, purpose):
    """Verifies the OTP code."""
    otp = OTPToken.objects.filter(
        user=user, 
        code=code, 
        purpose=purpose, 
        is_used=False,
        expires_at__gt=timezone.now()
    ).first()
    
    if otp:
        otp.is_used = True
        otp.save(update_fields=["is_used", "updated_at"])
        return True
    return False
