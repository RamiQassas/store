import os
import sys
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.core.management import call_command
try:
    print("Running makemigrations accounts...")
    call_command('makemigrations', 'accounts')
    print("Running migrate accounts...")
    call_command('migrate', 'accounts')
    print("Done!")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
