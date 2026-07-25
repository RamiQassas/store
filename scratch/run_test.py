import os
import sys
import django

sys.path.insert(0, r"C:\Users\a0947\Documents\store")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
django.setup()

from django.core.management import call_command

try:
    print("Starting unit & integration tests...")
    call_command("test", "apps.providers.tests.test_provider_overhaul", verbosity=2)
    print("All tests passed successfully!")
except Exception as e:
    import traceback
    traceback.print_exc()
