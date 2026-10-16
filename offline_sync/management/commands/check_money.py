"""
পুরনো bug এর কারণে production data তে যে গরমিল হয়েছে তা খুঁজে বের করে।

    python manage.py check_money                 # শুধু রিপোর্ট (কিছু বদলায় না)
    python manage.py check_money
    python manage.py check_money --fix-accounts  # account balance = ledger অনুযায়ী ঠিক করা

Account balance এর "সঠিক" মান = opening balance + সব completed credit − সব completed debit
(transactions table থেকে)। আগে sale save হলেই balance এ একই টাকা বারবার যোগ হত, কিন্তু
transaction তৈরি হত না — তাই balance ledger এর চেয়ে বেশি দেখাবে।
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q, Sum


class Command(BaseCommand):
    help = "Account balance / sale due / money receipt এর গরমিল রিপোর্ট (এবং ঐচ্ছিকভাবে account ঠিক করা)"

    def add_arguments(self, parser):
        parser.add_argument("--fix-accounts", action="store_true")

    def handle(self, *args, **opts):
        from accounts.models import Account
        from money_receipts.models import MoneyReceipt
        from sales.models import Sale
        from transactions.models import Transaction

        problems = 0

        self.stdout.write(self.style.MIGRATE_HEADING("\n== Account balance vs ledger =="))
        for acc in Account.objects.order_by("id"):
            base = Transaction.objects.filter(account=acc, status="completed", is_opening_balance=False)
            credit = base.filter(transaction_type="credit").aggregate(s=Sum("amount"))["s"] or Decimal("0")
            debit = base.filter(transaction_type="debit").aggregate(s=Sum("amount"))["s"] or Decimal("0")
            expected = (acc.opening_balance or Decimal("0")) + credit - debit
            if expected != acc.balance:
                problems += 1
                self.stdout.write(
                    f"  {acc.name} (#{acc.id}): stored {acc.balance}  ledger {expected}  "
                    f"difference {acc.balance - expected}")
                if opts["fix_accounts"]:
                    with transaction.atomic():
                        Account.objects.filter(pk=acc.pk).update(balance=expected)
                    self.stdout.write(self.style.SUCCESS("      → fixed"))

        self.stdout.write(self.style.MIGRATE_HEADING("\n== Sale totals (due = total − paid) =="))
        for s in Sale.objects.only("id", "invoice_no", "grand_total", "paid_amount", "due_amount"):
            exp_due = max(Decimal("0"), s.grand_total - s.paid_amount)
            if s.due_amount != exp_due or s.paid_amount > s.grand_total:
                problems += 1
                self.stdout.write(f"  {s.invoice_no} (#{s.id}): total {s.grand_total} paid {s.paid_amount} due {s.due_amount}")

        self.stdout.write(self.style.MIGRATE_HEADING("\n== Sale paid vs receipts =="))
        for s in Sale.objects.filter(paid_amount__gt=0).only("id", "invoice_no", "paid_amount"):
            received = MoneyReceipt.objects.filter(sale=s, payment_status="completed").aggregate(x=Sum("amount"))["x"] or Decimal("0")
            if received < s.paid_amount:
                problems += 1
                self.stdout.write(
                    f"  {s.invoice_no} (#{s.id}): paid {s.paid_amount} কিন্তু এই invoice এর receipt মোট {received} "
                    f"(overall receipt থেকে এসে থাকলে ঠিক আছে)")

        self.stdout.write(self.style.MIGRATE_HEADING("\n== Receipts without account transaction =="))
        for r in MoneyReceipt.objects.filter(payment_status="completed", transaction__isnull=True):
            problems += 1
            self.stdout.write(f"  {r.mr_no} (#{r.id}) amount {r.amount} — account এ জমা হয়নি")

        self.stdout.write(self.style.SUCCESS(f"\nমোট সম্ভাব্য সমস্যা: {problems}") if problems == 0
                          else self.style.WARNING(f"\nমোট সম্ভাব্য সমস্যা: {problems}"))
