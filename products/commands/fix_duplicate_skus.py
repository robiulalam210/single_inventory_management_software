# management/commands/complete_sku_reset.py
from django.core.management.base import BaseCommand
from django.db import transaction
from products.models import ProductSequence, Product


class Command(BaseCommand):
    help = 'SKU সিকোয়েন্স রিসেট করে (১০০০০ থেকে আবার শুরু)'

    def handle(self, *args, **options):
        with transaction.atomic():
            ProductSequence.objects.all().delete()
            ProductSequence.objects.create(pk=1, last_number=10000)  # প্রথম পণ্য পাবে 10001
            print("✓ SKU sequence reset")

            choice = input("Delete all existing product SKUs? (y/n): ")
            if choice.lower() == 'y':
                Product.objects.all().update(sku=None)
                print("✓ Cleared all existing SKUs")

            print("🎉 DONE")
