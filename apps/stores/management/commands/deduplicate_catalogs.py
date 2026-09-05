from django.core.management.base import BaseCommand
from apps.stores.services import deduplicate_all_stores

class Command(BaseCommand):
    help = "Deduplicates categories, products, and variants across all tenant stores and global catalog."

    def handle(self, *args, **options):
        self.stdout.write("Starting catalog deduplication across all stores...")
        res = deduplicate_all_stores()
        self.stdout.write(self.style.SUCCESS(f"Deduplication completed: {res}"))
