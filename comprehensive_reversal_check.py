import os
import sys

# Add current directory to sys.path
sys.path.append(os.getcwd())

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.urls import reverse
from apps.site import views
from apps.site.urls import urlpatterns

print("--- TESTING ALL URL NAMES REVERSAL ---")
all_passed = True
for url in urlpatterns:
    if hasattr(url, 'name') and url.name:
        try:
            # Skip URLs that require arguments for this simple test
            if '<uuid:' in url.pattern._route or '<str:' in url.pattern._route or '<int:' in url.pattern._route:
                print(f"SKIPPED (requires args): {url.name}")
                continue
            
            path = reverse(url.name)
            print(f"PASS: {url.name} -> {path}")
        except Exception as e:
            print(f"FAIL: {url.name} - {str(e)}")
            all_passed = False

if not all_passed:
    print("\nERROR: Some URL names could not be reversed!")
    sys.exit(1)

print("\n--- RUNNING DJANGO SYSTEM CHECK ---")
from django.core.management import call_command
try:
    call_command('check')
    print("Django system check passed.")
except Exception as e:
    print(f"Django system check failed: {e}")
    sys.exit(1)

print("\nSUCCESS: All critical routing and views verified.")
