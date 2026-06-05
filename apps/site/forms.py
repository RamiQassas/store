from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


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
        fields = ["name", "code", "symbol", "exchange_rate", "decimal_places", "display_order", "is_active", "is_default"]


class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = [
            "name", "method_type", "provider_name", "logo", "description",
            "display_order", "is_active", "is_maintenance_mode",
            "can_deposit", "can_withdraw", "supported_currencies",
            "account_number", "account_name", "iban", "wallet_address", "qr_image",
            "instructions", "custom_notes", "min_amount", "max_amount",
            "fixed_fee", "percentage_fee", "form_schema", "withdrawal_form_schema"
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "instructions": forms.Textarea(attrs={"rows": 3}),
            "custom_notes": forms.Textarea(attrs={"rows": 3}),
            "supported_currencies": forms.CheckboxSelectMultiple(),
            "form_schema": forms.Textarea(attrs={"rows": 6, "class": "font-mono text-xs"}),
            "withdrawal_form_schema": forms.Textarea(attrs={"rows": 6, "class": "font-mono text-xs"}),
        }


class ModerateUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "status", "tier", "restriction_withdrawals", "restriction_deposits", "restriction_purchases",
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
