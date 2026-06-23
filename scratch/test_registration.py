import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding='utf-8')

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from apps.site.views import v3_register_view
from apps.stores.models import Store
from apps.accounts.models import User
from django.contrib.auth.models import AnonymousUser
from apps.common.tenant_utils import set_current_store, reset_current_store

def run_test():
    stores = list(Store.objects.all())
    store1, store2 = stores[0], stores[1]
    email = "shared_email@example.com"
    
    # Let's clean up and register first on Store 1
    User.all_objects.filter(email=email).delete()
    User.all_objects.filter(phone__in=["+963955555555", "+963955555556"]).delete()
    
    factory = RequestFactory()
    
    # Store 1 registration
    data1 = {
        "first_name": "Shared",
        "last_name": "User",
        "email": email,
        "phone_input": "0555555555",
        "phone": "+963955555555",
        "password": "Password123!",
        "confirm_password": "Password123!"
    }
    req1 = factory.post("/auth/register/", data1)
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(req1)
    req1.session.save()
    req1.user = AnonymousUser()
    req1.store = store1
    
    token1 = set_current_store(store1)
    try:
        res1 = v3_register_view(req1)
        print(f"Store 1 registration status: {res1.status_code}")
    finally:
        reset_current_store(token1)
        
    # Store 2 registration
    data2 = {
        "first_name": "Shared",
        "last_name": "User",
        "email": email,
        "phone_input": "0555555555",
        "phone": "+963955555556", # unique phone
        "password": "Password123!",
        "confirm_password": "Password123!"
    }
    req2 = factory.post("/auth/register/", data2)
    middleware.process_request(req2)
    req2.session.save()
    req2.user = AnonymousUser()
    req2.store = store2
    
    token2 = set_current_store(store2)
    try:
        from apps.site.forms import RegisterForm
        # Run form validation manually in Store 2 context
        form = RegisterForm(data2)
        print(f"Is form valid: {form.is_valid()}")
        if not form.is_valid():
            print("Form errors:", form.errors)
        else:
            # Try to create user manually in Store 2 context to see exception
            print("Form is valid. Attempting to create user...")
            try:
                user = User.objects.create_user(
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password"],
                    phone=data2["phone"],
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    store=store2
                )
                print("User created successfully:", user)
            except Exception as e:
                import traceback
                print("Exception raised during User creation:")
                traceback.print_exc()
    finally:
        reset_current_store(token2)

if __name__ == "__main__":
    run_test()
