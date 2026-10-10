"""
python manage.py recalc_supplier_totals

প্রতিটা supplier এর মোট কেনা / পরিশোধ / বাকি নতুন করে হিসাব করে।
কেন: আগে বাতিল (cancelled) purchase ও supplier এর মোটে ধরা হত। কোড ঠিক করা হয়েছে, কিন্তু পুরনো সংখ্যা
শুধু ওই supplier এর পরের purchase save হলে ঠিক হয় — এই command একবারে সবার ঠিক করে দেয়।
নিরাপদ: শুধু হিসাবের field (total_purchases, total_paid, total_due, purchase_count) বদলায়।
"""
from django.core.management.base import BaseCommand

from suppliers.models import Supplier


class Command(BaseCommand):
    help = "Recalculate every supplier's purchase totals (excluding cancelled purchases)."

    def handle(self, *args, **opts):
        changed = 0
        for s in Supplier.objects.all().iterator():
            before = (s.total_purchases, s.total_paid, s.total_due, s.purchase_count)
            s.update_purchase_totals()
            s.refresh_from_db()
            after = (s.total_purchases, s.total_paid, s.total_due, s.purchase_count)
            if before != after:
                changed += 1
                self.stdout.write(f"#{s.id} {s.name}: due {before[2]} → {after[2]}, bought {before[0]} → {after[0]}")
        self.stdout.write(self.style.SUCCESS(f"Done. {changed} supplier(s) corrected."))
