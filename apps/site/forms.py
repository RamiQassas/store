from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()


from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
from apps.accounts.services import send_brevo_email

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
            
            subject = _("Password Reset | Raqamiyat")
            
            html_content = f"""
            <div dir="rtl" style="font-family: 'Cairo', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #06b6d4; margin: 0; font-size: 28px;">{_("Raqamiyat")}</h1>
                </div>
                <p style="font-size: 16px;">{_("Hello")} <strong>{user.first_name or user.email}</strong>،</p>
                <p style="font-size: 16px; line-height: 1.6;">{_("You requested a password reset for your account.")}</p>
                <p style="font-size: 16px; line-height: 1.6;">{_("Please click the button below to set a new password:")}</p>
                
                <div style="text-align: center; margin: 40px 0;">
                    <a href="{reset_url}" style="background-color: #06b6d4; color: #ffffff; padding: 14px 40px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 18px; display: inline-block;">{_("Reset Password")}</a>
                </div>
                
                <p style="font-size: 14px; color: #64748b;">{_("If you did not request this change, you can safely ignore this email.")}</p>
                <p style="font-size: 12px; word-break: break-all; color: #06b6d4;">{reset_url}</p>
                
                <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 30px 0;">
                <p style="font-size: 12px; color: #94a3b8; text-align: center;">© 2024 {_("Raqamiyat - All rights reserved.")}</p>
            </div>
            """
            
            send_brevo_email(
                to_email=user.email,
                to_name=f"{user.first_name} {user.last_name}",
                subject=subject,
                html_content=html_content
            )


class LoginForm(forms.Form):
    email = forms.EmailField(label=_("Email Address"), widget=forms.EmailInput(attrs={"placeholder": "name@example.com"}))
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput(attrs={"placeholder": "********"}))


class RegisterForm(forms.Form):
    first_name = forms.CharField(label=_("First Name"), max_length=150, widget=forms.TextInput(attrs={"placeholder": _("First Name")}))
    last_name = forms.CharField(label=_("Last Name"), max_length=150, required=False, widget=forms.TextInput(attrs={"placeholder": _("Last Name")}))
    email = forms.EmailField(label=_("Email Address"), widget=forms.EmailInput(attrs={"placeholder": "name@example.com"}))
    phone = forms.CharField(label=_("Phone Number"), max_length=32, widget=forms.TextInput(attrs={"placeholder": "05xxxxxxxx"}))
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput(attrs={"placeholder": _("Strong Password")}), min_length=10)
    confirm_password = forms.CharField(label=_("Confirm Password"), widget=forms.PasswordInput(attrs={"placeholder": _("Confirm Password")}))

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("This email address is already registered."))
        return email

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        if phone and User.objects.filter(phone=phone).exists():
            raise forms.ValidationError(_("This phone number is already registered."))
        return phone

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", _("Passwords do not match."))
        
        # Basic strength check if not already handled by min_length
        if password:
            if not any(char.isdigit() for char in password):
                self.add_error("password", _("Password must contain at least one digit."))
            if not any(char.isupper() for char in password):
                self.add_error("password", _("Password must contain at least one uppercase letter."))
        
        return cleaned_data


class TicketForm(forms.Form):
    subject = forms.CharField(label=_("Subject"), max_length=180, widget=forms.TextInput(attrs={"placeholder": _("Ticket Subject")}))
    priority = forms.ChoiceField(
        label=_("Priority"),
        choices=[("low", _("Low")), ("normal", _("Normal")), ("high", _("High"))],
    )
    initial_message = forms.CharField(
        label=_("Message"),
        widget=forms.Textarea(attrs={"rows": 5, "placeholder": _("Write problem details or request")}),
    )


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
    class Meta:
        model = PaymentMethod
        fields = [
            "name", "method_type", "logo", "description",
            "display_order", "is_active", "is_maintenance_mode",
            "can_deposit", "can_withdraw", "supported_currencies",
            "deposit_min_amount", "deposit_max_amount", "deposit_instructions", "deposit_qr_image",
            "withdrawal_min_amount", "withdrawal_max_amount", "withdrawal_instructions",
            "deposit_info_schema", "withdrawal_info_schema",
            "deposit_form_schema", "withdrawal_form_schema",
            "deposit_fee_settings", "withdrawal_fee_settings"
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "builder-input"}),
            "method_type": forms.TextInput(attrs={"class": "builder-input"}),
            "display_order": forms.NumberInput(attrs={"class": "builder-input"}),
            "deposit_min_amount": forms.NumberInput(attrs={"class": "builder-input"}),
            "deposit_max_amount": forms.NumberInput(attrs={"class": "builder-input"}),
            "withdrawal_min_amount": forms.NumberInput(attrs={"class": "builder-input"}),
            "withdrawal_max_amount": forms.NumberInput(attrs={"class": "builder-input"}),
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
                raise forms.ValidationError(_("This phone number is already registered to another user."))
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
        label=_("Restricted Countries"),
        choices=COUNTRIES,
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "builder-input select2", "style": "height: 200px;"}),
        help_text=_("Choose one or more countries to block verification from.")
    )

    class Meta:
        model = KYCSettings
        fields = [
            "unverified_daily_deposit_limit", "unverified_daily_withdrawal_limit",
            "verified_daily_deposit_limit", "verified_daily_withdrawal_limit",
            "block_by_nationality", "block_by_issuing_country"
        ]
        widgets = {
            "unverified_daily_deposit_limit": forms.NumberInput(attrs={"class": "builder-input"}),
            "unverified_daily_withdrawal_limit": forms.NumberInput(attrs={"class": "builder-input"}),
            "verified_daily_deposit_limit": forms.NumberInput(attrs={"class": "builder-input"}),
            "verified_daily_withdrawal_limit": forms.NumberInput(attrs={"class": "builder-input"}),
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
            "mother_name": forms.TextInput(attrs={"class": "builder-input", "placeholder": _("Mother's full name")}),
            "place_of_birth": forms.TextInput(attrs={"class": "builder-input"}),
            "document_type": forms.Select(attrs={"class": "builder-input"}),
            "gender": forms.Select(attrs={"class": "builder-input"}),
        }

    def clean_id_number(self):
        id_number = self.cleaned_data.get("id_number")
        if id_number:
            qs = KYCRequest.objects.filter(id_number=id_number)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(_("An account is already verified with this identity data. Only one verified account is allowed per identity document."))
        return id_number

    def __init__(self, *args, **kwargs):
        is_admin = kwargs.pop('is_admin', False)
        super().__init__(*args, **kwargs)
        # Ensure all fields are required for users, but allow optional images for admin updates
        for field_name, field in self.fields.items():
            if is_admin and field_name in ["identity_front", "identity_back", "selfie_verification"]:
                field.required = False
            else:
                field.required = True


from apps.catalog.models import Category, Product, ProductVariant

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "parent", "is_active", "sort_order"]


class ProductForm(forms.ModelForm):
    sort_order = forms.IntegerField(required=False, initial=0, label=_("Display Order"), widget=forms.NumberInput(attrs={"class": "builder-input"}))
    
    class Meta:
        model = Product
        fields = [
            "name", "category", "image", "cover_image", "thumbnail",
            "description", "instructions", "is_active", "is_featured", "sort_order", "form_schema"
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "builder-input"}),
            "category": forms.Select(attrs={"class": "builder-input"}),
            "description": forms.Textarea(attrs={"rows": 4, "class": "builder-input"}),
            "instructions": forms.Textarea(attrs={"rows": 4, "class": "builder-input"}),
            "form_schema": forms.Textarea(attrs={"rows": 5, "placeholder": '{"version": 1, "fields": []}', "class": "builder-input font-mono text-xs"}),
            "image": forms.FileInput(attrs={"class": "builder-input"}),
            "cover_image": forms.FileInput(attrs={"class": "builder-input"}),
            "thumbnail": forms.FileInput(attrs={"class": "builder-input"}),
        }


class VariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["name", "sku", "price", "cost", "discount_percent", "estimated_delivery_minutes", "is_active", "sort_order"]
