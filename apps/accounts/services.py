import requests
import json
import logging
from django.conf import settings
from django.urls import reverse
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes, force_str
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
            data=json.dumps(payload, default=force_str),
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
