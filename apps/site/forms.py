from django import forms
from django.contrib.auth import get_user_model

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
    phone = forms.CharField(label="الهاتف", max_length=32, required=False, widget=forms.TextInput(attrs={"placeholder": "05xxxxxxxx"}))
    password = forms.CharField(label="كلمة المرور", widget=forms.PasswordInput(attrs={"placeholder": "كلمة مرور قوية"}), min_length=10)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email


class TicketForm(forms.Form):
    subject = forms.CharField(label="العنوان", max_length=180, widget=forms.TextInput(attrs={"placeholder": "عنوان التذكرة"}))
    priority = forms.ChoiceField(
        label="الأولوية",
        choices=[("low", "منخفض"), ("normal", "عادي"), ("high", "عالي")],
    )
    initial_message = forms.CharField(
        label="الرسالة",
        widget=forms.Textarea(attrs={"rows": 5, "placeholder": "اكتب تفاصيل المشكلة أو الطلب"}),
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
            "role", "status", "tier", "phone", "restriction_withdrawals", "restriction_deposits", "restriction_purchases",
            "suspension_reason", "admin_notes", "suspension_expires_at", "is_permanently_suspended"
        ]
        widgets = {
            "suspension_expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "suspension_reason": forms.Textarea(attrs={"rows": 3}),
            "admin_notes": forms.Textarea(attrs={"rows": 3}),
        }


from apps.catalog.models import Category, Product, ProductVariant

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "parent", "is_active", "sort_order"]


class ProductForm(forms.ModelForm):
    sort_order = forms.IntegerField(required=False, initial=0, label="ترتيب العرض")
    
    class Meta:
        model = Product
        fields = [
            "name", "category", "image", "cover_image", "thumbnail",
            "description", "instructions", "is_active", "is_featured", "sort_order", "form_schema"
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "instructions": forms.Textarea(attrs={"rows": 4}),
            "form_schema": forms.Textarea(attrs={"rows": 5, "placeholder": '{"version": 1, "fields": []}'}),
        }


class VariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["name", "sku", "price", "cost", "discount_percent", "estimated_delivery_minutes", "is_active", "sort_order"]
