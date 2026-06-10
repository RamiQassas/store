from django.db import migrations
from collections import Counter

def fix_empty_usernames(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for user in User.objects.filter(username=''):
        user.username = f"user_{user.id}"
        user.save(update_fields=['username'])

def fix_duplicate_usernames(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    usernames = list(
        User.objects.exclude(username='')
        .values_list('username', flat=True)
    )
    duplicates = [
        k for k, v in Counter(usernames).items()
        if v > 1
    ]
    for username in duplicates:
        users = User.objects.filter(
            username=username
        ).order_by('id')[1:]
        for user in users:
            user.username = f"{username}_{user.id}"
            user.save(update_fields=['username'])

class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0023_temporarykycimage_alter_user_options_and_more'),
    ]
    operations = [
        migrations.RunPython(fix_empty_usernames, reverse_code=migrations.RunPython.noop),
        migrations.RunPython(fix_duplicate_usernames, reverse_code=migrations.RunPython.noop),
    ]
