"""
Migration 0041: Automatically trigger Alkasr VIP catalog sync after the wipe in 0040.

This runs immediately after migration 0040 deletes all old data, so products
are re-imported with correct prices on the first deploy.
"""
from django.db import migrations
import logging

logger = logging.getLogger(__name__)


def run_sync(apps, schema_editor):
    """Trigger sync for all active provider profiles."""
    try:
        from apps.providers.models import ProviderProfile
        from services.provider.manager import ProviderManager

        profiles = ProviderProfile.all_objects.filter(is_active=True, store__isnull=True)
        if not profiles.exists():
            print("[0041] No active provider profiles found, skipping sync.")
            return

        for profile in profiles:
            print(f"[0041] Syncing: {profile} ...")
            try:
                stats = ProviderManager.sync_catalog(profile)
                print(f"[0041] Done: created={stats.get('created',0)}, updated={stats.get('updated',0)}")
            except Exception as e:
                print(f"[0041] Sync failed for {profile}: {e}")
                logger.warning(f"Auto-sync in migration 0041 failed: {e}")
    except Exception as e:
        print(f"[0041] Could not run auto-sync: {e}")
        logger.warning(f"Migration 0041 auto-sync error: {e}")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0040_wipe_provider_catalog_for_reimport"),
    ]

    operations = [
        migrations.RunPython(run_sync, noop_reverse),
    ]
