from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
from apps.accounts.services import send_brevo_email
from apps.orders.models import Order, Coupon

class CustomPasswordResetForm(PasswordResetForm):
    def save(self, domain_override=None, subject_template_name=None,
             email_template_name=None, use_https=False, token_generator=default_token_generator,
             from_email=None, request=None, html_email_template_name=None,
             extra_email_context=None):
        """
        Custom save method to use Brevo API for sending password reset emails.
        """
        email = self.cleaned_data["email"]
        active_users = User.objects.filter(email__iexact=email, is_active=True)
        
        for user in active_users:
            if not user.has_usable_password():
                continue
            
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_generator.make_token(user)
            protocol = 'https' if use_https else 'http'
            domain = domain_override or (request.get_host() if request else 'raqamiyat.onrender.com')
            
            reset_url = f"{protocol}://{domain}{reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})}"
            
            subject = "إعادة تعيين كلمة المرور | Raqamiyat"
            
            html_content = f"""
            <div dir="rtl" style="font-family: 'Cairo', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #06b6d4; margin: 0; font-size: 28px;">رقميات | Raqamiyat</h1>
                </div>
                <p style="font-size: 16px;">مرحباً <strong>{user.first_name or user.email}</strong>،</p>
                <p style="font-size: 16px; line-height: 1.6;">لقد طلبت إعادة تعيين كلمة المرور لحسابك في رقميات.</p>
                <p style="font-size: 16px; line-height: 1.6;">يرجى الضغط على الزر أدناه لتعيين كلمة مرور جديدة:</p>
                
                <div style="text-align: center; margin: 40px 0;">
                    <a href="{reset_url}" style="background-color: #06b6d4; color: #ffffff; padding: 14px 40px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 18px; display: inline-block;">إعادة تعيين كلمة المرور</a>
                </div>
                
                <p style="font-size: 14px; color: #64748b;">إذا لم تطلب هذا التغيير، يمكنك تجاهل هذا البريد بأمان.</p>
                <p style="font-size: 12px; word-break: break-all; color: #06b6d4;">{reset_url}</p>
                
                <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                <p style="font-size: 12px; color: #94a3b8; text-align: center;">© 2024 رقميات - Raqamiyat. جميع الحقوق محفوظة.</p>
            </div>
            """
            
            send_brevo_email(
                to_email=user.email,
                to_name=f"{user.first_name} {user.last_name}",
                subject=subject,
                html_content=html_content
            )


class LoginForm(forms.Form):
    email = forms.EmailField(label="البريد الإلكتروني", widget=forms.EmailInput(attrs={"placeholder": "name@example.com"}))
    password = forms.CharField(label="كلمة المرور", widget=forms.PasswordInput(attrs={"placeholder": "********"}))


class RegisterForm(forms.Form):
    first_name = forms.CharField(label="الاسم الأول", max_length=150, widget=forms.TextInput(attrs={"placeholder": "الاسم الأول"}))
    last_name = forms.CharField(label="الاسم الأخير", max_length=150, required=False, widget=forms.TextInput(attrs={"placeholder": "الاسم الأخير"}))
    email = forms.EmailField(label="البريد الإلكتروني", widget=forms.EmailInput(attrs={"placeholder": "name@example.com"}))
    phone = forms.CharField(label="الهاتف", max_length=32, widget=forms.TextInput(attrs={"placeholder": "05xxxxxxxx"}))
    password = forms.CharField(label="كلمة المرور", widget=forms.PasswordInput(attrs={"placeholder": "كلمة مرور قوية"}), min_length=10)
    confirm_password = forms.CharField(label="تأكيد كلمة المرور", widget=forms.PasswordInput(attrs={"placeholder": "تأكيد كلمة المرور"}))

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("هذا البريد الإلكتروني مسجل مسبقاً.")
        return email

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if not phone:
            raise forms.ValidationError("رقم الهاتف مطلوب.")
        
        # Prevent non-numeric chars (except leading +)
        import re
        if not re.match(r'^\+?\d+$', phone):
            raise forms.ValidationError("رقم الهاتف يجب أن يحتوي على أرقام فقط.")

        # Check for duplicates
        if User.objects.filter(phone=phone).exists():
            raise forms.ValidationError("رقم الهاتف هذا مسجل مسبقاً.")

        # Country-specific length validation (Syria example)
        # Syria international format: +963 9xx xxx xxx (13 chars total including +)
        # Turkey international format: +90 5xx xxx xxxx (13 chars total including +)
        if phone.startswith('+963'):
            if len(phone) != 13:
                raise forms.ValidationError("رقم الهاتف السوري يجب أن يكون 10 أرقام بعد رمز الدولة.")
        elif phone.startswith('+90'):
            if len(phone) != 13:
                raise forms.ValidationError("رقم الهاتف التركي يجب أن يكون 10 أرقام بعد رمز الدولة.")
        
        return phone

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "كلمات المرور غير متطابقة.")
        
        # Basic strength check if not already handled by min_length
        if password:
            if not any(char.isdigit() for char in password):
                self.add_error("password", "يجب أن تحتوي كلمة المرور على رقم واحد على الأقل.")
            if not any(char.isupper() for char in password):
                self.add_error("password", "يجب أن تحتوي كلمة المرور على حرف كبير واحد على الأقل.")
        
        return cleaned_data


from apps.common.models import Currency
from apps.payments.models import PaymentMethod

class CurrencyForm(forms.ModelForm):
    class Meta:
        model = Currency
        fields = ["name", "code", "symbol", "buy_rate", "sell_rate", "conversion_method", "decimal_places", "display_order", "is_active", "is_default"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "builder-input"}),
            "code": forms.TextInput(attrs={"class": "builder-input"}),
            "symbol": forms.TextInput(attrs={"class": "builder-input"}),
            "buy_rate": forms.NumberInput(attrs={"class": "builder-input", "step": "0.000001"}),
            "sell_rate": forms.NumberInput(attrs={"class": "builder-input", "step": "0.000001"}),
            "conversion_method": forms.Select(attrs={"class": "builder-input"}),
            "decimal_places": forms.NumberInput(attrs={"class": "builder-input"}),
            "display_order": forms.NumberInput(attrs={"class": "builder-input"}),
        }


class PaymentMethodForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['capital_exchange_rate'].required = False
        self.fields['capital_exchange_rate'].initial = '1.000000'

    class Meta:
        model = PaymentMethod
        fields = [
            "name", "method_type", "logo", "description",
            "display_order", "is_active", "is_maintenance_mode", "requires_kyc",
            "can_deposit", "can_withdraw", "supported_currencies",
            "deposit_min_amount", "deposit_max_amount", "deposit_instructions", "deposit_qr_image",
            "withdrawal_min_amount", "withdrawal_max_amount", "withdrawal_instructions",
            "daily_deposit_limit", "daily_withdrawal_limit",
            "global_deposit_cap", "global_deposit_usage",
            "global_withdrawal_cap", "global_withdrawal_usage",
            "deposit_info_schema", "withdrawal_info_schema",
            "deposit_form_schema", "withdrawal_form_schema",
            "deposit_fee_settings", "withdrawal_fee_settings",
            "capital_exchange_rate", "deposit_exchange_rate", "withdrawal_exchange_rate"
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "builder-input"}),
            "method_type": forms.TextInput(attrs={"class": "builder-input"}),
            "display_order": forms.NumberInput(attrs={"class": "builder-input"}),
            "deposit_min_amount": forms.NumberInput(attrs={"class": "builder-input"}),
            "deposit_max_amount": forms.NumberInput(attrs={"class": "builder-input"}),
            "withdrawal_min_amount": forms.NumberInput(attrs={"class": "builder-input"}),
            "withdrawal_max_amount": forms.NumberInput(attrs={"class": "builder-input"}),
            "daily_deposit_limit": forms.NumberInput(attrs={"class": "builder-input"}),
            "daily_withdrawal_limit": forms.NumberInput(attrs={"class": "builder-input"}),
            "global_deposit_cap": forms.NumberInput(attrs={"class": "builder-input"}),
            "global_deposit_usage": forms.NumberInput(attrs={"class": "builder-input"}),
            "global_withdrawal_cap": forms.NumberInput(attrs={"class": "builder-input"}),
            "global_withdrawal_usage": forms.NumberInput(attrs={"class": "builder-input"}),
            "capital_exchange_rate": forms.NumberInput(attrs={"class": "builder-input", "step": "0.000001"}),
            "deposit_exchange_rate": forms.NumberInput(attrs={"class": "builder-input", "step": "0.000001"}),
            "withdrawal_exchange_rate": forms.NumberInput(attrs={"class": "builder-input", "step": "0.000001"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": "builder-input"}),
            "deposit_instructions": forms.Textarea(attrs={"rows": 3, "class": "builder-input"}),
            "withdrawal_instructions": forms.Textarea(attrs={"rows": 3, "class": "builder-input"}),
            "deposit_info_schema": forms.Textarea(attrs={"rows": 5, "class": "font-mono text-xs builder-input"}),
            "withdrawal_info_schema": forms.Textarea(attrs={"rows": 5, "class": "font-mono text-xs builder-input"}),
            "deposit_form_schema": forms.Textarea(attrs={"rows": 5, "class": "font-mono text-xs builder-input"}),
            "withdrawal_form_schema": forms.Textarea(attrs={"rows": 5, "class": "font-mono text-xs builder-input"}),
            "deposit_fee_settings": forms.Textarea(attrs={"rows": 3, "class": "font-mono text-xs builder-input"}),
            "withdrawal_fee_settings": forms.Textarea(attrs={"rows": 3, "class": "font-mono text-xs builder-input"}),
            "supported_currencies": forms.CheckboxSelectMultiple(),
        }


class ModerateUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "role", "status", "tier", "phone", "is_kyc_verified",
            "daily_deposit_limit", "daily_withdrawal_limit",
            "restriction_withdrawals", "restriction_deposits", "restriction_purchases",
            "suspension_reason", "admin_notes", "suspension_expires_at", "is_permanently_suspended"
        ]
        widgets = {
            "suspension_expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "suspension_reason": forms.Textarea(attrs={"rows": 3}),
            "admin_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        if phone:
            qs = User.objects.filter(phone=phone)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("رقم الهاتف هذا مسجل مسبقاً لمستخدم آخر.")
        return phone


from apps.accounts.models import KYCRequest, KYCSettings
from apps.common.countries import COUNTRIES

from apps.common.models import SocialMediaLink

class SocialMediaLinkForm(forms.ModelForm):
    class Meta:
        model = SocialMediaLink
        fields = ["name", "url", "icon_image", "icon_class", "is_active", "display_order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "builder-input"}),
            "url": forms.URLInput(attrs={"class": "builder-input", "placeholder": "https://..."}),
            "icon_class": forms.TextInput(attrs={"class": "builder-input", "placeholder": "fab fa-facebook"}),
            "display_order": forms.NumberInput(attrs={"class": "builder-input"}),
        }

class KYCSettingsForm(forms.ModelForm):
    restricted_countries_list = forms.MultipleChoiceField(
        label="الدول المحظورة",
        choices=COUNTRIES,
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "builder-input select2", "style": "height: 200px;"}),
        help_text="اختر دولة أو أكثر لمنع التوثيق منها."
    )

    class Meta:
        model = KYCSettings
        fields = [
            "unverified_daily_deposit_limit", "unverified_daily_withdrawal_limit",
            "verified_daily_deposit_limit", "verified_daily_withdrawal_limit",
            "block_by_nationality", "block_by_issuing_country",
            "otp_max_attempts", "otp_base_cooldown"
        ]
        widgets = {
            "unverified_daily_deposit_limit": forms.NumberInput(attrs={"class": "builder-input"}),
            "unverified_daily_withdrawal_limit": forms.NumberInput(attrs={"class": "builder-input"}),
            "verified_daily_deposit_limit": forms.NumberInput(attrs={"class": "builder-input"}),
            "verified_daily_withdrawal_limit": forms.NumberInput(attrs={"class": "builder-input"}),
            "otp_max_attempts": forms.NumberInput(attrs={"class": "builder-input"}),
            "otp_base_cooldown": forms.NumberInput(attrs={"class": "builder-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.restricted_countries:
            self.fields["restricted_countries_list"].initial = self.instance.restricted_countries

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.restricted_countries = self.cleaned_data.get("restricted_countries_list", [])
        if commit:
            instance.save()
        return instance


class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(label="كلمة المرور الحالية", required=False, widget=forms.PasswordInput(attrs={"class": "builder-input", "placeholder": "********"}))
    new_password = forms.CharField(label="كلمة المرور الجديدة", widget=forms.PasswordInput(attrs={"class": "builder-input", "placeholder": "********"}), min_length=10)
    confirm_password = forms.CharField(label="تأكيد كلمة المرور الجديدة", widget=forms.PasswordInput(attrs={"class": "builder-input", "placeholder": "********"}))

    def __init__(self, *args, **kwargs):
        self.has_password = kwargs.pop('has_password', True)
        super().__init__(*args, **kwargs)
        if not self.has_password:
            self.fields['current_password'].required = False
            self.fields['current_password'].widget = forms.HiddenInput()

    def clean_new_password(self):
        password = self.cleaned_data.get("new_password")
        if not any(char.isdigit() for char in password):
            raise forms.ValidationError("يجب أن تحتوي كلمة المرور على رقم واحد على الأقل.")
        if not any(char.isupper() for char in password):
            raise forms.ValidationError("يجب أن تحتوي كلمة المرور على حرف كبير واحد على الأقل.")
        return password

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        if new_password and confirm_password and new_password != confirm_password:
            self.add_error("confirm_password", "كلمات المرور غير متطابقة.")
        return cleaned_data


class KYCRequestForm(forms.ModelForm):
    class Meta:
        model = KYCRequest
        fields = [
            "nationality", "issuing_country", "document_type", "id_number",
            "first_name", "father_name", "last_name",
            "mother_name", "gender", "date_of_birth", "place_of_birth", "current_residence",
            "identity_front", "identity_back", "selfie_verification"
        ]
        widgets = {
            "nationality": forms.Select(attrs={"class": "builder-input searchable-select"}),
            "issuing_country": forms.Select(attrs={"class": "builder-input searchable-select"}),
            "date_of_birth": forms.DateInput(attrs={"type": "date", "class": "builder-input"}),
            "current_residence": forms.Textarea(attrs={"rows": 3, "class": "builder-input"}),
            "id_number": forms.TextInput(attrs={"class": "builder-input"}),
            "first_name": forms.TextInput(attrs={"class": "builder-input"}),
            "father_name": forms.TextInput(attrs={"class": "builder-input"}),
            "last_name": forms.TextInput(attrs={"class": "builder-input"}),
            "mother_name": forms.TextInput(attrs={"class": "builder-input", "placeholder": "الاسم الثلاثي للأم"}),
            "place_of_birth": forms.TextInput(attrs={"class": "builder-input"}),
            "document_type": forms.Select(attrs={"class": "builder-input"}),
            "gender": forms.Select(attrs={"class": "builder-input"}),
        }

    def clean_id_number(self):
        id_number = self.cleaned_data.get("id_number", "").strip()
        if id_number:
            # Check for duplicate ID number across all accounts (excluding current instance)
            qs = KYCRequest.objects.filter(id_number__iexact=id_number)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise forms.ValidationError("هذا الرقم الوطني موجود سابقاً، إذا كنت تعتقد أن هذا خطأ تواصل مع الإدارة.")
        return id_number

    def __init__(self, *args, **kwargs):
        is_admin = kwargs.pop('is_admin', False)
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Add phone field if missing on user
        if user and not user.phone:
            self.fields['phone'] = forms.CharField(
                label="رقم الهاتف",
                max_length=32,
                widget=forms.TextInput(attrs={"class": "builder-input", "placeholder": "05xxxxxxxx"}),
                required=True
            )

        # Add password fields if user doesn't have a password (social signup)
        if user and not user.has_usable_password():
            self.fields['password'] = forms.CharField(
                label="تعيين كلمة مرور",
                min_length=10,
                widget=forms.PasswordInput(attrs={"class": "builder-input", "placeholder": "********"}),
                required=True,
                help_text="يرجى تعيين كلمة مرور لحسابك للمتابعة."
            )
            self.fields['confirm_password'] = forms.CharField(
                label="تأكيد كلمة المرور",
                widget=forms.PasswordInput(attrs={"class": "builder-input", "placeholder": "********"}),
                required=True
            )

        # Ensure all fields are required for users, but allow optional images for admin updates
        # OR if the user already has images uploaded (persistent images)
        for field_name, field in self.fields.items():
            if field_name in ["identity_front", "identity_back", "selfie_verification"]:
                if is_admin or (self.instance and self.instance.pk and getattr(self.instance, field_name)):
                    field.required = False
                else:
                    field.required = True
            elif field_name in ['phone', 'password', 'confirm_password']:
                field.required = True
            else:
                field.required = True

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "كلمات المرور غير متطابقة.")
        
        if password:
            if not any(char.isdigit() for char in password):
                self.add_error("password", "يجب أن تحتوي كلمة المرور على رقم واحد على الأقل.")
            if not any(char.isupper() for char in password):
                self.add_error("password", "يجب أن تحتوي كلمة المرور على حرف كبير واحد على الأقل.")
        
        return cleaned_data

from apps.catalog.models import Category, Product, ProductVariant, ProductSuggestion

class ProductSuggestionForm(forms.ModelForm):
    class Meta:
        model = ProductSuggestion
        fields = ["product_name", "category_name", "description"]
        widgets = {
            "product_name": forms.TextInput(attrs={"class": "builder-input", "placeholder": "مثال: شحن رصيد بلايستيشن سعودي"}),
            "category_name": forms.TextInput(attrs={"class": "builder-input", "placeholder": "مثال: بطاقات الألعاب"}),
            "description": forms.Textarea(attrs={"class": "builder-input", "rows": 4, "placeholder": "صف الخدمة بوضوح أو ضع رابطاً لمثال عليها..."}),
        }

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "parent", "image", "is_active", "sort_order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "builder-input"}),
            "parent": forms.Select(attrs={"class": "builder-input"}),
            "image": forms.FileInput(attrs={"class": "builder-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "builder-input"}),
        }

class CouponForm(forms.ModelForm):
    limit_to_tiers_list = forms.MultipleChoiceField(
        label="محدد لفئات معينة",
        choices=User.Tier.choices,
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "builder-input", "style": "height: 100px;"})
    )

    class Meta:
        model = Coupon
        fields = [
            "code", "match_mode", "discount_type", "discount_percent", "discount_amount", "min_order_amount", "max_uses", "max_uses_per_user",
            "is_active", "is_verified_only", "expires_at",
            "limit_to_products", "apply_to_all_products",
            "limit_to_users", "limit_to_area", "allow_area_type", "limit_to_place_of_birth",
            "limit_to_ip_countries", "limit_to_ip_cities"
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": "builder-input", "placeholder": "WELCOME2026"}),
            "match_mode": forms.Select(attrs={"class": "builder-input"}),
            "discount_type": forms.Select(attrs={"class": "builder-input", "onchange": "toggleDiscountFields()"}),
            "discount_percent": forms.NumberInput(attrs={"class": "builder-input", "step": "0.01"}),
            "discount_amount": forms.NumberInput(attrs={"class": "builder-input", "step": "0.01"}),
            "min_order_amount": forms.NumberInput(attrs={"class": "builder-input", "step": "0.01"}),
            "max_uses": forms.NumberInput(attrs={"class": "builder-input"}),
            "max_uses_per_user": forms.NumberInput(attrs={"class": "builder-input"}),
            "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "builder-input"}),
            "limit_to_products": forms.SelectMultiple(attrs={"class": "builder-input searchable-select"}),
            "limit_to_users": forms.SelectMultiple(attrs={"class": "builder-input searchable-select", "style": "height: 150px;"}),
            "limit_to_area": forms.TextInput(attrs={"class": "builder-input", "placeholder": "كلمة دلالية للبحث في العنوان"}),
            "allow_area_type": forms.Select(attrs={"class": "builder-input"}),
            "limit_to_place_of_birth": forms.TextInput(attrs={"class": "builder-input", "placeholder": "كلمة دلالية للبحث في محل الولادة"}),
            "limit_to_ip_countries": forms.SelectMultiple(choices=COUNTRIES, attrs={"class": "builder-input select2", "style": "height: 100px;"}),
            "limit_to_ip_cities": forms.SelectMultiple(attrs={"class": "builder-input select2-tags"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.limit_to_tiers:
            self.fields["limit_to_tiers_list"].initial = self.instance.limit_to_tiers
        
        # Make limit_to_ip_cities support arbitrary dynamic choices 
        # since it's a tagging select.
        self.fields['limit_to_ip_cities'].choices = [
            (c, c) for c in (self.instance.limit_to_ip_cities if self.instance and self.instance.limit_to_ip_cities else [])
        ]
        self.fields['limit_to_ip_cities'].required = False

    def clean_limit_to_ip_countries(self):
        val = self.cleaned_data.get("limit_to_ip_countries")
        return val if val is not None else []

    def clean_limit_to_ip_cities(self):
        # We need to grab it directly from POST because dynamic choices might fail validation
        if self.data:
            val = self.data.getlist("limit_to_ip_cities")
            return [v.strip() for v in val if v.strip()]
        
        val = self.cleaned_data.get("limit_to_ip_cities", [])
        if isinstance(val, str):
            return [v.strip() for v in val.split(",") if v.strip()]
        return val if val is not None else []

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.limit_to_tiers = self.cleaned_data.get("limit_to_tiers_list", [])
        
        # Ensure list fields are never None
        if instance.limit_to_ip_countries is None:
            instance.limit_to_ip_countries = []
        if instance.limit_to_ip_cities is None:
            instance.limit_to_ip_cities = []
            
        if commit:
            instance.save()
            self.save_m2m() # Required for ManyToManyField limit_to_users
        return instance


class ProductForm(forms.ModelForm):
    sort_order = forms.IntegerField(required=False, initial=0, label="ترتيب العرض", widget=forms.NumberInput(attrs={"class": "builder-input"}))
    
    class Meta:
        model = Product
        fields = [
            "name", "category", "image", "cover_image", "thumbnail",
            "description", "instructions", "is_active", "is_featured", "is_out_of_stock", "is_sale", "sort_order", "delivery_time_display", "form_schema"
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "builder-input"}),
            "category": forms.Select(attrs={"class": "builder-input"}),
            "description": forms.Textarea(attrs={"rows": 4, "class": "builder-input"}),
            "instructions": forms.Textarea(attrs={"rows": 4, "class": "builder-input"}),
            "delivery_time_display": forms.TextInput(attrs={"class": "builder-input", "placeholder": "مثال: 5-15 دقيقة"}),
            "form_schema": forms.Textarea(attrs={"rows": 5, "placeholder": '{"version": 1, "fields": []}', "class": "builder-input font-mono text-xs"}),
            "image": forms.FileInput(attrs={"class": "builder-input"}),
            "cover_image": forms.FileInput(attrs={"class": "builder-input"}),
            "thumbnail": forms.FileInput(attrs={"class": "builder-input"}),
        }


class VariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["name", "sku", "price", "cost", "discount_percent", "is_sale", "estimated_delivery_minutes", "is_active", "is_temporarily_disabled", "sort_order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "builder-input"}),
            "sku": forms.TextInput(attrs={"class": "builder-input"}),
            "price": forms.NumberInput(attrs={"class": "builder-input", "step": "0.01"}),
            "cost": forms.NumberInput(attrs={"class": "builder-input", "step": "0.01"}),
            "discount_percent": forms.NumberInput(attrs={"class": "builder-input", "step": "0.01"}),
            "estimated_delivery_minutes": forms.NumberInput(attrs={"class": "builder-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "builder-input"}),
        }

from apps.support.models import SupportSettings, ChatCannedReply

class SupportSettingsForm(forms.ModelForm):
    class Meta:
        model = SupportSettings
        fields = ["welcome_message"]
        widgets = {
            "welcome_message": forms.Textarea(attrs={"class": "builder-input", "rows": 3}),
        }

class ChatCannedReplyForm(forms.ModelForm):
    class Meta:
        model = ChatCannedReply
        fields = ["title", "body", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "builder-input"}),
            "body": forms.Textarea(attrs={"class": "builder-input", "rows": 4}),
        }

from apps.common.models import SiteAnnouncement

class SendNotificationForm(forms.Form):
    TARGET_CHOICES = [
        ("all", "الجميع"),
        ("tier", "فئة محددة"),
        ("individual", "مستخدم محدد (بريد، اسم، هاتف)"),
    ]
    TIER_CHOICES = User.Tier.choices

    target = forms.ChoiceField(label="المستهدف", choices=TARGET_CHOICES, initial="all", widget=forms.RadioSelect(attrs={"class": "flex gap-4"}))
    tier = forms.ChoiceField(label="الفئة", choices=TIER_CHOICES, required=False, widget=forms.Select(attrs={"class": "builder-input"}))
    user_identifier = forms.CharField(label="معرف المستخدم", required=False, widget=forms.TextInput(attrs={"class": "builder-input", "placeholder": "البريد أو الاسم أو الهاتف", "autocomplete": "off"}))
    
    CHANNEL_CHOICES = [
        ("all", "الكل (إشعار داخلي + دفع + بريد)"),
        ("in_app", "إشعار داخلي فقط"),
        ("push", "إشعار دفع (Push) فقط"),
        ("email", "بريد إلكتروني فقط"),
    ]
    channels = forms.ChoiceField(label="وسيلة الإرسال", choices=CHANNEL_CHOICES, initial="all", widget=forms.Select(attrs={"class": "builder-input"}))
    
    title = forms.CharField(label="العنوان", max_length=150, widget=forms.TextInput(attrs={"class": "builder-input", "placeholder": "عنوان الإشعار"}))
    body = forms.CharField(label="المحتوى", widget=forms.Textarea(attrs={"class": "builder-input", "rows": 4, "placeholder": "نص الإشعار"}))
    action_url = forms.CharField(label="رابط (اختياري)", required=False, widget=forms.TextInput(attrs={"class": "builder-input", "placeholder": "/dashboard/"}))

class SiteAnnouncementForm(forms.ModelForm):
    class Meta:
        model = SiteAnnouncement
        fields = ["text", "link", "is_active", "background_color", "text_color"]
        widgets = {
            "text": forms.Textarea(attrs={"class": "builder-input", "rows": 3}),
            "link": forms.URLInput(attrs={"class": "builder-input"}),
            "background_color": forms.TextInput(attrs={"class": "builder-input", "type": "color"}),
            "text_color": forms.TextInput(attrs={"class": "builder-input", "type": "color"}),
        }

class AdminChatForm(forms.Form):
    user_identifier = forms.CharField(label="معرف المستخدم", widget=forms.TextInput(attrs={"class": "builder-input", "placeholder": "البريد أو الاسم أو الهاتف", "autocomplete": "off"}))
    subject = forms.CharField(label="الموضوع", max_length=180, widget=forms.TextInput(attrs={"class": "builder-input", "placeholder": "موضوع التذكرة"}))
    message = forms.CharField(label="الرسالة الأولى", widget=forms.Textarea(attrs={"class": "builder-input", "rows": 5, "placeholder": "اكتب رسالتك للعميل هنا..."}))
