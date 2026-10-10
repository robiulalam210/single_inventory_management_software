"""
Account এর balance আর তার transaction গুলোর যোগফল মিলছে কিনা দেখে।

আগের কিছু bug এ balance ভুল হয়ে আছে:
  • প্রতিটা Income দ্বিগুণ যোগ হতো (Transaction + হাতে balance বাড়ানো)
  • Expense মুছলে টাকা দ্বিগুণ ফেরত আসত
  • Supplier payment এ account দুইবার কাটত (আগেই ঠিক করা)

ব্যবহার:
  python manage.py audit_account_balances                  # শুধু রিপোর্ট, কিছু বদলায় না
  python manage.py audit_account_balances --account 12 --fix   # balance = transaction এর যোগফল

সতর্কতা: কেউ যদি ইচ্ছা করে transaction ছাড়া balance বসিয়ে থাকে (যেমন পুরনো system থেকে আনা টাকা,
opening transaction ছাড়া), --fix সেটা মুছে দেবে। আগে রিপোর্ট দেখে আসল cash/bank এর সাথে মিলিয়ে নিন।
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction


class Command(BaseCommand):
    help = "Compare each account's balance with the sum of its transactions (and optionally fix it)."

    def add_arguments(self, parser):
        parser.add_argument('--account', type=int, help='Only this account id')
        parser.add_argument('--fix', action='store_true', help='Set balance = sum of transactions for the listed accounts')

    def handle(self, *args, **opts):
        from accounts.models import Account
        from transactions.models import Transaction
        from income.models import Income

        qs = Account.objects.all().order_by('id')
        if opts.get('account'):
            qs = qs.filter(id=opts['account'])
        if opts['fix'] and not opts.get('account'):
            self.stderr.write(self.style.ERROR('--fix needs --account, so nothing is changed by accident.'))
            return

        bad = 0
        for acc in qs:
            total = Decimal('0.00')
            for t in Transaction.objects.filter(account=acc).exclude(status__in=['pending', 'failed']).only('amount', 'transaction_type'):
                total += t.amount if t.transaction_type == 'credit' else -t.amount
            diff = (acc.balance or Decimal('0')) - total
            if abs(diff) < Decimal('0.01'):
                continue
            bad += 1
            incomes = Income.objects.filter(account=acc, transactions__transaction_type='credit').distinct()
            inc_sum = sum((i.amount for i in incomes), Decimal('0'))
            hint = ''
            if inc_sum and abs(diff - inc_sum) < Decimal('0.01'):
                hint = '  ← exactly the income total: income was added twice (old bug)'
            elif inc_sum and diff > 0:
                hint = f'  (income recorded on this account: {inc_sum}; part of the gap is likely the old double-income bug)'
            self.stdout.write(f'#{acc.id} {acc.name}: balance {acc.balance} | transactions add up to {total} | gap {diff:+}{hint}')
            if opts['fix']:
                with db_transaction.atomic():
                    Account.objects.filter(pk=acc.pk).update(balance=total)
                self.stdout.write(self.style.SUCCESS(f'    fixed → balance is now {total}'))

        if not bad:
            self.stdout.write(self.style.SUCCESS('All account balances match their transactions.'))
        elif not opts['fix']:
            self.stdout.write(self.style.WARNING(f'{bad} account(s) do not match. Check against the real cash/bank, then re-run with --account <id> --fix.'))
