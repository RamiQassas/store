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
