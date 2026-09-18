from django.db import migrations

def restore_and_fix_site(apps, schema_editor):
    Site = apps.get_model('sites', 'Site')
    db_alias = schema_editor.connection.alias
    
    # 1. Check if Site with id=1 exists
    site_1 = Site.objects.using(db_alias).filter(id=1).first()
    if site_1:
        site_1.domain = "raqamiyatapp.com"
        site_1.name = "Raqamiyat"
        site_1.save(using=db_alias)
    else:
        # Check if there's any existing site (e.g. with id=2 or another domain)
        existing_site = Site.objects.using(db_alias).filter(domain="raqamiyatapp.com").first() or Site.objects.using(db_alias).first()
        if existing_site:
            # Update its id to 1 using raw SQL to safely adjust the primary key
            with schema_editor.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE django_site SET id = 1, domain = %s, name = %s WHERE id = %s",
                    ["raqamiyatapp.com", "Raqamiyat", existing_site.id]
                )
        else:
            with schema_editor.connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO django_site (id, domain, name) VALUES (1, %s, %s)",
                    ["raqamiyatapp.com", "Raqamiyat"]
                )

    # 2. Sync PostgreSQL sequence if applicable
    try:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SELECT setval(pg_get_serial_sequence('django_site', 'id'), COALESCE(MAX(id), 1)) FROM django_site;")
    except Exception:
        pass

    # 3. Ensure all SocialApp instances include Site 1
    try:
        SocialApp = apps.get_model('socialaccount', 'SocialApp')
        for app in SocialApp.objects.using(db_alias).all():
            app.sites.add(1)
    except Exception:
        pass

def reverse_noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('common', '0016_alter_sitemaintenancemode_id'),
        ('sites', '0002_alter_domain_unique'),
    ]

    operations = [
        migrations.RunPython(restore_and_fix_site, reverse_noop),
    ]
