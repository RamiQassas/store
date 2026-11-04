import os
import signal
from django.db import migrations


def force_kill_daphne_now(apps, schema_editor):
    """
    Runs inside Linux Docker container during auto-deploy 'manage.py migrate'.
    Explicitly commits the migration record, then sends SIGKILL to stale Daphne workers
    and container PID 1 so Docker immediately spawns a fresh container with updated code.
    """
    if os.name != 'posix':
        return  # Only run inside Linux production container

    try:
        schema_editor.connection.commit()
    except Exception:
        pass

    my_pid = os.getpid()

    # 1. Kill Daphne / Gunicorn / ASGI server processes in the container
    proc_dir = "/proc"
    if os.path.exists(proc_dir):
        for entry in os.listdir(proc_dir):
            if entry.isdigit():
                pid = int(entry)
                if pid != my_pid:
                    try:
                        with open(f"/proc/{pid}/cmdline", "rb") as f:
                            cmd = f.read()
                            if b"daphne" in cmd or b"gunicorn" in cmd or b"config.asgi" in cmd:
                                try:
                                    os.kill(pid, signal.SIGKILL)
                                except Exception:
                                    pass
                    except Exception:
                        pass

    # 2. Kill PID 1 (container main process) to force Docker 'restart: always' reload
    try:
        if my_pid != 1:
            os.kill(1, signal.SIGKILL)
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0023_purge_inmemory_workers_and_recycle'),
    ]

    operations = [
        migrations.RunPython(force_kill_daphne_now, reverse_code=migrations.RunPython.noop),
    ]
