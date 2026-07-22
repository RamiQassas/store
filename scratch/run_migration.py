import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

log_file = open("scratch/migration_log.txt", "w", encoding="utf-8")

class Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
            s.flush()
    def flush(self):
        for s in self.streams:
            s.flush()

sys.stdout = Tee(sys.__stdout__, log_file)
sys.stderr = Tee(sys.__stderr__, log_file)

try:
    import django
    django.setup()
    print("Django setup OK")
    
    from django.core.management import call_command
    call_command("migrate", "common", verbosity=2)
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    log_file.close()
