import sys
try:
    import django
    print(f"Django version: {django.get_version()}")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
