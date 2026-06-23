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

def send_brevo_email(to_email, to_name, subject, html_content, text_content=None, store=None):
    """
    Sends an email using Brevo Transactional Email API.
    """
    if not settings.BREVO_API_KEY:
        logger.warning("BREVO_API_KEY is not set. Email not sent.")
        return False

    from apps.common.tenant_utils import get_current_store
    active_store = store or get_current_store()
    
    sender_name = settings.DEFAULT_FROM_NAME
    reply_to_name = "Raqamiyat Support | دعم رقميات"
    
    if active_store:
        store_name = active_store if isinstance(active_store, str) else getattr(active_store, 'name', '')
        if store_name:
            sender_name = store_name
            reply_to_name = f"{store_name} Support | دعم {store_name}"

    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json",
    }

    payload = {
        "sender": {
            "name": sender_name,
            "email": settings.DEFAULT_FROM_EMAIL
        },
        "replyTo": {
            "name": reply_to_name,
            "email": settings.REPLY_TO_EMAIL
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

    import time
    max_retries = 3
    for attempt in range(max_retries):
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
                logger.warning(f"Brevo API error (attempt {attempt + 1}/{max_retries}): {response.status_code} - {response.text}")
        except Exception as e:
            logger.warning(f"Brevo connection error (attempt {attempt + 1}/{max_retries}): {str(e)}")
        
        if attempt < max_retries - 1:
            time.sleep(1)
            
    logger.error("Brevo API failed after maximum retries.")
    return False


def send_verification_email(request, user):
    """
    Sends an OTP verification email using Brevo API.
    """
    try:
        from apps.accounts.otp_services import generate_otp, send_otp_email
        from apps.accounts.models import OTPToken
        otp = generate_otp(user, OTPToken.Purpose.REGISTRATION)
        return send_otp_email(user, otp)
    except Exception as e:
        logger.error(f"Failed to send verification OTP: {str(e)}")
        return False

from django.urls import reverse
from urllib.parse import urljoin

def send_kyc_status_email(user, status, reason=None):
    """
    Sends an email regarding KYC status change.
    """
    subjects = {
        'approved': "🎉 مبروك! تم توثيق حسابك بنجاح | Raqamiyat",
        'rejected': "⚠️ تحديث بخصوص طلب توثيق حسابك | Raqamiyat",
        'pending': "📥 استلمنا طلب توثيق حسابك | Raqamiyat"
    }
    
    subject = subjects.get(status, "تحديث حالة الحساب | Raqamiyat")
    
    # Securely build URLs
    dashboard_url = urljoin(settings.SITE_URL, reverse('dashboard'))
    kyc_request_url = urljoin(settings.SITE_URL, reverse('site_kyc_request'))
    
    # Unique reference to prevent Gmail collapsing (quoted text)
    import time
    ref_id = f"REF-{int(time.time())}-{user.id}"
    
    user_display_name = f"{user.first_name} {user.last_name}".strip() or user.email

    if status == 'approved':
        content = f"""
        <div dir="rtl" style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #1e293b; background-color: #ffffff; border-radius: 20px; border: 1px solid #e2e8f0;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h2 style="color: #06b6d4; margin: 0; font-size: 28px; font-weight: 900;">رقميات | RAQAMIYAT</h2>
                <p style="color: #64748b; font-size: 14px;">نظام التوثيق والامتثال</p>
            </div>
            
            <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 30px; border-radius: 16px; text-align: center; margin-bottom: 25px;">
                <div style="font-size: 50px; margin-bottom: 10px;">✅</div>
                <h1 style="font-size: 24px; font-weight: 900; color: #166534; margin: 0;">تم توثيق حسابك بنجاح!</h1>
            </div>

            <p style="font-size: 16px; line-height: 1.8; color: #334155; margin-bottom: 20px;">
                أهلاً بك <strong>{user_display_name}</strong>، يسعدنا إبلاغك بأن فريقنا قام بمراجعة بياناتك واعتماد توثيق حسابك.
            </p>

            <div style="background-color: #f8fafc; padding: 20px; border-radius: 12px; margin-bottom: 25px;">
                <h3 style="color: #06b6d4; font-size: 14px; text-transform: uppercase; margin-top: 0;">حدودك المالية الجديدة:</h3>
                <ul style="list-style: none; padding: 0; margin: 0;">
                    <li style="padding: 10px 0; border-bottom: 1px solid #e2e8f0; font-size: 14px;">
                        <span>حد الإيداع اليومي:</span>
                        <strong style="float: left; color: #0f172a;">{user.daily_deposit_limit:,.2f} USD</strong>
                    </li>
                    <li style="padding: 10px 0; font-size: 14px;">
                        <span>حد السحب اليومي:</span>
                        <strong style="float: left; color: #0f172a;">{user.daily_withdrawal_limit:,.2f} USD</strong>
                    </li>
                </ul>
            </div>

            <div style="border-right: 4px solid #06b6d4; padding-right: 15px; margin-bottom: 25px;">
                <h4 style="margin: 0 0 10px 0; color: #0f172a;">مميزات العضو الموثق:</h4>
                <p style="font-size: 13px; color: #64748b; margin: 0; line-height: 1.6;">
                    • الأولوية في معالجة طلبات السحب والإيداع.<br>
                    • الوصول إلى عروض وكوبونات حصرية للأعضاء الموثقين.<br>
                    • دعم فني مخصص للعمليات الكبيرة.
                </p>
            </div>

            <div style="text-align: center;">
                <a href="{dashboard_url}" style="display: inline-block; background-color: #06b6d4; color: #ffffff; padding: 14px 35px; border-radius: 12px; text-decoration: none; font-weight: bold; font-size: 16px;">ابدأ التسوق الآن</a>
            </div>

            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #f1f5f9; text-align: center; font-size: 12px; color: #94a3b8;">
                فريق رقميات لخدمات الوساطة الرقمية<br>© 2026 Raqamiyat Services.
                <div style="margin-top: 10px; color: #f1f5f9; font-size: 8px;">ID: {ref_id}</div>
            </div>
        </div>
        """
    elif status == 'rejected':
        content = f"""
        <div dir="rtl" style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #1e293b; background-color: #ffffff; border-radius: 20px; border: 1px solid #e2e8f0;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h2 style="color: #06b6d4; margin: 0; font-size: 28px; font-weight: 900;">رقميات | RAQAMIYAT</h2>
            </div>
            
            <div style="background-color: #fff1f2; border: 1px solid #fecdd3; padding: 30px; border-radius: 16px; text-align: center; margin-bottom: 25px;">
                <div style="font-size: 50px; margin-bottom: 10px;">⚠️</div>
                <h1 style="font-size: 22px; font-weight: 900; color: #9f1239; margin: 0;">نأسف، تم رفض طلب التوثيق</h1>
            </div>

            <p style="font-size: 16px; line-height: 1.8; color: #334155; margin-bottom: 20px;">
                أهلاً <strong>{user_display_name}</strong>، نود إخبارك بأنه لم يتم قبول طلب توثيق حسابك حالياً للسبب التالي:
            </p>

            <div style="background-color: #f8fafc; padding: 20px; border-radius: 12px; border-right: 4px solid #f43f5e; margin-bottom: 25px;">
                <p style="font-size: 15px; color: #0f172a; margin: 0; font-weight: bold;">{reason or 'لم يتم ذكر سبب محدد من قبل الإدارة.'}</p>
            </div>

            <p style="font-size: 14px; color: #64748b; margin-bottom: 25px;">
                بإمكانك دائماً تقديم طلب جديد بعد تصحيح البيانات أو رفع صور أكثر وضوحاً للوثائق المطلوبة.
            </p>

            <div style="text-align: center;">
                <a href="{kyc_request_url}" style="display: inline-block; background-color: #0f172a; color: #ffffff; padding: 12px 30px; border-radius: 12px; text-decoration: none; font-weight: bold;">تقديم طلب جديد</a>
            </div>

            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #f1f5f9; text-align: center; font-size: 12px; color: #94a3b8;">
                إذا كان لديك أي استفسار، يرجى التواصل مع الدعم الفني.<br>© 2026 Raqamiyat Services.
                <div style="margin-top: 10px; color: #f1f5f9; font-size: 8px;">ID: {ref_id}</div>
            </div>
        </div>
        """
    else: # pending
        content = f"""
        <div dir="rtl" style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #1e293b; background-color: #ffffff; border-radius: 20px; border: 1px solid #e2e8f0;">
            <div style="text-align: center; margin-bottom: 30px;">
                <h2 style="color: #06b6d4; margin: 0; font-size: 28px; font-weight: 900;">رقميات | RAQAMIYAT</h2>
            </div>
            
            <div style="background-color: #eff6ff; border: 1px solid #bfdbfe; padding: 30px; border-radius: 16px; text-align: center; margin-bottom: 25px;">
                <div style="font-size: 50px; margin-bottom: 10px;">📥</div>
                <h1 style="font-size: 22px; font-weight: 900; color: #1e40af; margin: 0;">استلمنا بياناتك بنجاح</h1>
            </div>

            <p style="font-size: 16px; line-height: 1.8; color: #334155; margin-bottom: 20px;">
                أهلاً <strong>{user.get_full_name() or user.email}</strong>، شكراً لتقديمك طلب التوثيق. طلبك الآن في قائمة الانتظار وسيتم مراجعته من قبل فريقنا في أسرع وقت ممكن (عادةً خلال 24 ساعة).
            </p>

            <div style="background-color: #f8fafc; padding: 15px; border-radius: 12px; margin-bottom: 25px; text-align: center;">
                <p style="font-size: 13px; color: #64748b; margin: 0;">يرجى عدم إرسال طلبات مكررة لتسريع عملية المراجعة.</p>
            </div>

            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #f1f5f9; text-align: center; font-size: 12px; color: #94a3b8;">
                سنقوم بإخطارك فور تحديث حالة طلبك.<br>© 2026 Raqamiyat Services.
            </div>
        </div>
        """

    return send_brevo_email(to_email=user.email, to_name=user.get_full_name() or user.email, subject=subject, html_content=content)
