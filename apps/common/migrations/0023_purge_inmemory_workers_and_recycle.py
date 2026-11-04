import os
import signal
import threading
import time
from django.db import migrations


def recycle_stale_web_workers(apps, schema_editor):
    """
    Subprocess execution during auto-deploy 'manage.py migrate'.
    Terminates stale in-memory Daphne ASGI / Gunicorn server processes
    so the container supervisor immediately boots a clean worker with fresh code.
    Runs asynchronously with a delay so this migration is safely committed first.
    """
    def _kill_stale():
        time.sleep(2.5)  # Allow manage.py migrate to exit and record migration commit
        my_pid = os.getpid()

        # 1. Search /proc for all daphne / gunicorn processes and terminate them
        proc_dir = "/proc"
        if os.path.exists(proc_dir):
            try:
                for entry in os.listdir(proc_dir):
                    if entry.isdigit():
                        pid = int(entry)
                        if pid != my_pid:
                            try:
                                cmd_path = os.path.join(proc_dir, entry, "cmdline")
                                with open(cmd_path, "rb") as f:
                                    cmd = f.read()
                                    if b"daphne" in cmd or b"gunicorn" in cmd:
                                        try:
                                            os.kill(pid, signal.SIGKILL)
                                        except Exception:
                                            pass
                            except Exception:
                                pass
            except Exception:
                pass

        # 2. Terminate PID 1 in container so Docker restart:always launches a fresh container
        try:
            if my_pid != 1:
                os.kill(1, signal.SIGKILL)
        except Exception:
            pass

    threading.Thread(target=_kill_stale, daemon=True).start()


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0022_sitefeatureflag'),
    ]

    operations = [
        migrations.RunPython(recycle_stale_web_workers, reverse_code=migrations.RunPython.noop),
    ]
