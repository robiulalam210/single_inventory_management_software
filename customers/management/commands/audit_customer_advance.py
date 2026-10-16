"""
python manage.py audit_customer_advance          → শুধু রিপোর্ট (কিছু বদলায় না)
python manage.py audit_customer_advance --fix    → যাদের সব রসিদের হিসাব জানা, তাদের advance ঠিক করে

কেন: পুরনো sync_advance_balance() প্রতিটা "overall" রসিদের পুরো টাকাকে advance ধরে customer এ লিখে দিত,
তাই অনেক customer এর advance বেশি দেখাতে পারে। নতুন রসিদে (allocation রেকর্ড আছে) ঠিক কত advance গেছে
জানা আছে — সেটা দিয়ে মেলানো হয়। যে customer এর পুরনো overall রসিদ আছে (রেকর্ড নেই), তাকে শুধু
"নিজে দেখে নিন" হিসেবে দেখায়, নিজে থেকে বদলায় না।
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from customers.models import Customer


class Command(BaseCommand):
    help = "Compare each customer's stored advance with what their money receipts recorded (optionally fix)."

    def add_arguments(self, parser):
        parser.add_argument('--fix', action='store_true', help='Correct customers whose receipts are fully recorded.')

    def handle(self, *args, **opts):
        qs = Customer.objects.all().order_by('id')
        fixed = manual = ok = 0
        for c in qs.iterator():
            expected, _rows, complete = c.expected_advance_from_receipts()
            stored = c.advance_balance or Decimal('0.00')
            if abs(stored - expected) <= Decimal('0.01'):
                ok += 1
                continue
            line = f"#{c.id} {c.name}: stored {stored} vs receipts {expected}"
            if not complete:
                manual += 1
                self.stdout.write(self.style.WARNING(line + "  → has old receipts without records, check by hand"))
                continue
            if opts['fix']:
                with transaction.atomic():
                    locked = Customer.objects.select_for_update().get(pk=c.pk)
                    locked.advance_balance = expected
                    locked.save(update_fields=['advance_balance'])
                fixed += 1
                self.stdout.write(self.style.SUCCESS(line + "  → fixed"))
            else:
                fixed += 1
                self.stdout.write(line + "  → would fix (run with --fix)")
        verb = 'fixed' if opts['fix'] else 'to fix'
        self.stdout.write(f"\nOK: {ok}   {verb}: {fixed}   check by hand: {manual}")
