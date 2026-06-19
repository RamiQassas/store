import os
import django
import sys
from django.core.management import call_command

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

def run():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "makemigrations"
    args = sys.argv[2:]
    
    print(f"Running django command: {cmd} with args: {args}")
    try:
        call_command(cmd, *args)
        print("Command completed successfully.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run()
