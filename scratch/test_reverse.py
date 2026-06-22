import os
import sys
import django

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.urls import reverse, set_urlconf

print("Trying to reverse 'google_login' with default URLConf...")
try:
    print("Default urlconf:", reverse('google_login'))
except Exception as e:
    print("Default failed:", e)

print("\nTrying to reverse 'google_login' with apps.stores.urls...")
try:
    set_urlconf('apps.stores.urls')
    print("Stores urlconf:", reverse('google_login'))
except Exception as e:
    print("Stores failed:", e)
