import os
import subprocess
import sys

# Ensure UTF-8 output encoding on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def main():
    print("=" * 60)
    print("Exporting database data for Hetzner migration...")
    print("=" * 60)

    # 1. Export Django Fixtures
    output_fixture = "backup_data.json"
    print(f"1. Exporting Django data to {output_fixture}...")
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        cmd = [sys.executable, "manage.py", "dumpdata", "--natural-foreign", "--natural-primary", "-e", "contenttypes", "-e", "auth.Permission", "--indent", "2", "-o", output_fixture]
        res = subprocess.run(cmd, capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
        if res.returncode == 0:
            print(f"SUCCESS: Exported data to file: {output_fixture}")
        else:
            print(f"WARNING: Direct export failed with error:\n{res.stderr}")
    except Exception as e:
        print(f"ERROR: Exception occurred during export: {e}")



    print("\nTo restore this data on your Hetzner server inside Docker container:")
    print("docker compose -f docker-compose.prod.yml exec web python manage.py loaddata backup_data.json")
    print("=" * 60)

if __name__ == "__main__":
    main()

