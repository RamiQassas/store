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
    class Meta:
        model = Store
        fields = ["name", "subdomain", "description", "logo", "subscription_plan"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

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
            "is_out_of_stock", "is_sale", "sort_order", "delivery_time_display", "form_schema"
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
