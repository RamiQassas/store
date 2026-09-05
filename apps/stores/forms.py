from django.db import models
from django import forms
from apps.stores.models import Store, StorePage, StoreEmployee, SubscriptionPlan
from apps.catalog.models import Product, Category
from apps.orders.models import Coupon

class StoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = [
            "name", "subdomain", "description", "logo", "banner", 
            "primary_color", "secondary_color", "background_color", "text_color",
            "import_products_from_raqamiyat",
            "phone", "email", "address", 
            "social_facebook", "social_instagram", "social_twitter", "social_tiktok"
        ]
        widgets = {
            "primary_color": forms.TextInput(attrs={"type": "color"}),
            "secondary_color": forms.TextInput(attrs={"type": "color"}),
            "background_color": forms.TextInput(attrs={"type": "color"}),
            "text_color": forms.TextInput(attrs={"type": "color"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "address": forms.Textarea(attrs={"rows": 2}),
        }

class StoreCustomDomainForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = ["custom_domain"]

class StoreCreateForm(forms.ModelForm):
    subscription_plan = forms.ModelChoiceField(
        queryset=SubscriptionPlan.objects.filter(is_active=True),
        required=True,
        label="خطة الاشتراك"
    )
    import_products_from_raqamiyat = forms.BooleanField(
        required=False,
        initial=True,
        label="استيراد منتجات رقميات"
    )
    # Admin Credentials for Sub-store
    admin_email = forms.EmailField(
        required=True,
        label="البريد الإلكتروني لمدير المتجر الفرعي",
        help_text="البريد المخصص لتسجيل الدخول للوحة تحكم المتجر الفرعي بشكل مستقل"
    )
    admin_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}),
        required=True,
        min_length=6,
        label="كلمة مرور مدير المتجر الفرعي"
    )
    admin_password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}),
        required=True,
        min_length=6,
        label="تأكيد كلمة المرور"
    )

    # Initial Tier Profit Margins (%)
    margin_customer = forms.DecimalField(
        required=False,
        initial=15.0,
        min_value=0,
        max_value=500,
        label="نسبة ربح العميل العادي (%)",
        help_text="تضاف إلى تكلفة الجملة عند البيع للعملاء"
    )
    margin_dealer = forms.DecimalField(
        required=False,
        initial=10.0,
        min_value=0,
        max_value=500,
        label="نسبة ربح التاجر (%)",
        help_text="تضاف إلى تكلفة الجملة لفئة التاجر"
    )
    margin_vip = forms.DecimalField(
        required=False,
        initial=5.0,
        min_value=0,
        max_value=500,
        label="نسبة ربح VIP (%)",
        help_text="تضاف إلى تكلفة الجملة لفئة VIP"
    )

    accept_legal_terms = forms.BooleanField(
        required=True,
        label="الموافقة على الشروط القانونية"
    )
    class Meta:
        model = Store
        fields = ["name", "subdomain", "description", "logo", "subscription_plan", "billing_cycle", "import_products_from_raqamiyat"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_subdomain(self):
        subdomain = self.cleaned_data.get("subdomain")
        if subdomain:
            subdomain = subdomain.strip().lower()
            import re
            if not re.match(r"^[a-z0-9\-]+$", subdomain):
                raise forms.ValidationError("يجب أن يحتوي الرابط الفرعي على أحرف إنجليزية وأرقام وعلامة الشرطة (-) فقط.")
            
            reserved_words = ["www", "admin", "api", "control", "mail", "blog", "support", "shop", "store", "assets", "static", "media", "merchant", "site", "dashboard"]
            if subdomain in reserved_words:
                raise forms.ValidationError("هذا الرابط الفرعي محجوز، يرجى اختيار رابط آخر.")
                
            # Check uniqueness case-insensitively
            if Store.objects.filter(subdomain__iexact=subdomain).exists():
                raise forms.ValidationError("هذا الرابط الفرعي مستخدم بالفعل، يرجى اختيار رابط آخر.")
        return subdomain

    def clean(self):
        cleaned_data = super().clean()
        pwd = cleaned_data.get("admin_password")
        pwd_conf = cleaned_data.get("admin_password_confirm")
        if pwd and pwd_conf and pwd != pwd_conf:
            self.add_error("admin_password_confirm", "كلمتا المرور غير متطابقتين.")
        return cleaned_data

class StorePageForm(forms.ModelForm):
    class Meta:
        model = StorePage
        fields = ["title", "slug", "content", "is_active"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 10}),
        }

class StoreEmployeeForm(forms.Form):
    email = forms.EmailField(label="البريد الإلكتروني للموظف")
    role = forms.ChoiceField(choices=StoreEmployee.Role.choices, label="الدور/الوظيفة")
    permissions = forms.MultipleChoiceField(
        choices=[
            ("manage_products", "إدارة المنتجات"),
            ("manage_orders", "إدارة الطلبات"),
            ("manage_coupons", "إدارة الكوبونات"),
            ("manage_pages", "إدارة الصفحات"),
            ("manage_settings", "إدارة الإعدادات"),
            ("manage_employees", "إدارة الموظفين"),
            ("view_reports", "عرض التقارير المتقدمة"),
        ],
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="الصلاحيات المخصصة"
    )

class MerchantProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "category", "image", "cover_image", "thumbnail",
            "description", "instructions", "is_active", "is_featured", 
            "is_out_of_stock", "is_sale", "sort_order", "delivery_time_display", "form_schema",
            "track_inventory", "quantity", "low_stock_threshold"
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "instructions": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        store = kwargs.pop("store", None)
        super().__init__(*args, **kwargs)
        if store:
            # Only show categories belonging to this store
            self.fields["category"].queryset = Category.objects.filter(store=store)

class MerchantCategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "parent", "image", "is_active", "is_featured", "sort_order"]

    def __init__(self, *args, **kwargs):
        store = kwargs.pop("store", None)
        super().__init__(*args, **kwargs)
        if store:
            self.fields["parent"].queryset = Category.objects.filter(store=store)

class MerchantCouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            "code", "discount_type", "discount_percent", "discount_amount",
            "max_uses", "max_uses_per_user", "min_order_amount", "is_active",
            "is_verified_only", "expires_at"
        ]
