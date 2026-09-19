from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.models import UserSession

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "phone", "role", "email_verified", "two_factor_enabled")
        read_only_fields = ("id", "role", "email_verified")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "phone", "password")
        read_only_fields = ("id",)

    def create(self, validated_data):
        password = validated_data.pop("password")
        request = self.context.get("request")
        store = getattr(request, "store", None) if request else None
        user = User(**validated_data)
        user.store = store
        user.set_password(password)
        user.save()
        try:
            from apps.wallets.services import get_or_create_wallet
            get_or_create_wallet(user)
        except Exception:
            pass
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    code = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs["email"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError("بيانات تسجيل الدخول غير صحيحة.")
        if not user.is_active:
            raise serializers.ValidationError("هذا الحساب غير مفعل.")

        # Check if user requires 2FA or Email OTP
        requires_otp = False
        requires_totp = False
        
        if not user.email_verified:
            requires_otp = True
        elif getattr(user, "security_login_method", None) in ("EMAIL", "BOTH"):
            requires_otp = True
        
        if getattr(user, "totp_enabled", False) or getattr(user, "security_login_method", None) in ("APP", "BOTH"):
            requires_totp = True

        code = (attrs.get("code") or "").strip()
        
        if requires_totp or requires_otp:
            if not code:
                # If Email OTP is needed, trigger sending the OTP code
                if requires_otp and not requires_totp:
                    try:
                        from apps.accounts.otp_services import generate_otp, send_otp_email
                        from apps.accounts.models import OTPToken
                        token = generate_otp(user, OTPToken.Purpose.LOGIN)
                        send_otp_email(user, token)
                    except Exception:
                        pass
                    raise serializers.ValidationError({
                        "requires_2fa": True,
                        "method": "EMAIL",
                        "detail": "رمز التحقق مطلوب. تم إرسال رمز التحقق إلى بريدك الإلكتروني."
                    })
                elif requires_totp:
                    raise serializers.ValidationError({
                        "requires_2fa": True,
                        "method": "APP",
                        "detail": "كود المصادقة الثنائية (TOTP/Google Authenticator) مطلوب."
                    })

            # If code is provided, verify it
            verified = False
            if requires_totp and getattr(user, "totp_secret", None):
                try:
                    import pyotp
                    if pyotp.TOTP(user.totp_secret).verify(code):
                        verified = True
                except Exception:
                    pass
            
            from django.utils import timezone
            from datetime import timedelta
            from apps.accounts.models import KYCSettings
            
            if user.otp_lockout_until and user.otp_lockout_until > timezone.now():
                raise serializers.ValidationError({"code": "تم قفل محاولات التحقق مؤقتاً بسبب تكرار إدخال رمز خاطئ. يرجى المحاولة لاحقاً."})

            if not verified and requires_otp:
                try:
                    from apps.accounts.otp_services import verify_otp
                    from apps.accounts.models import OTPToken
                    if verify_otp(user, code, OTPToken.Purpose.LOGIN) or verify_otp(user, code, OTPToken.Purpose.REGISTRATION):
                        verified = True
                        if not user.email_verified:
                            user.email_verified = True
                            user.save(update_fields=["email_verified"])
                except Exception:
                    pass
            
            if not verified:
                user.otp_failed_attempts = (user.otp_failed_attempts or 0) + 1
                kyc_settings = KYCSettings.get_settings()
                max_attempts = getattr(kyc_settings, 'otp_max_attempts', 5) or 5
                if user.otp_failed_attempts >= max_attempts:
                    user.otp_lockout_until = timezone.now() + timedelta(minutes=15)
                    user.otp_failed_attempts = 0
                user.save(update_fields=["otp_failed_attempts", "otp_lockout_until"])
                raise serializers.ValidationError({"code": "رمز التحقق غير صحيح أو انتهت صلاحيته."})
            else:
                if user.otp_failed_attempts or user.otp_lockout_until:
                    user.otp_failed_attempts = 0
                    user.otp_lockout_until = None
                    user.save(update_fields=["otp_failed_attempts", "otp_lockout_until"])

        attrs["user"] = user
        return attrs


class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = ("id", "ip_address", "user_agent", "is_active", "last_seen_at", "created_at")
        read_only_fields = fields
