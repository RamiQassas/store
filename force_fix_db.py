import os
import django
from django.db import connection, transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

def run_fix():
    with connection.cursor() as cursor:
        # 1. Check existing columns
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='accounts_user';")
        columns = [row[0] for row in cursor.fetchall()]
        print(f"Current columns in accounts_user: {len(columns)}")

        fixes = [
            {
                "column": "custom_payment_limits",
                "sql": "ALTER TABLE accounts_user ADD COLUMN custom_payment_limits jsonb DEFAULT '{}'::jsonb NOT NULL;"
            },
            {
                "column": "preferred_language",
                "sql": "ALTER TABLE accounts_user ADD COLUMN preferred_language varchar(10) DEFAULT 'ar' NOT NULL;"
            },
            {
                "column": "last_session_key",
                "sql": "ALTER TABLE accounts_user ADD COLUMN last_session_key varchar(40) NULL;"
            }
        ]

        for fix in fixes:
            col = fix["column"]
            if col not in columns:
                print(f"Missing column: {col}. Attempting to add...")
                try:
                    with transaction.atomic():
                        cursor.execute(fix["sql"])
                    print(f"SUCCESS: Added {col}")
                except Exception as e:
                    print(f"ERROR adding {col}: {e}")
            else:
                print(f"Column {col} already exists.")

        # 2. Check if SupportSettings table exists
        cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='support_supportsettings';")
        exists = cursor.fetchone()[0] > 0
        if not exists:
            print("Table support_supportsettings is MISSING. Running migrations...")
            from django.core.management import execute_from_command_line
            try:
                execute_from_command_line(['manage.py', 'migrate', 'support', '--noinput'])
                print("SUCCESS: Migrated support app.")
            except Exception as e:
                print(f"ERROR migrating support: {e}")
        else:
            print("Table support_supportsettings exists.")

        # 3. Final migration check for all apps
        print("Running final migration for all apps...")
        from django.core.management import execute_from_command_line
        try:
            execute_from_command_line(['manage.py', 'migrate', '--noinput'])
            print("SUCCESS: All migrations synced.")
        except Exception as e:
            print(f"Migration error (might be expected if we manually added columns): {e}")

if __name__ == "__main__":
    run_fix()
