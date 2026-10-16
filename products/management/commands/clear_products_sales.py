"""পুরনো পণ্য + বিক্রি (সাথে ক্রয় ও রিটার্ন) মুছে ফেলে, যাতে seed_dry_fruits ফাঁকা থেকে চালানো যায়।

চালান:
    python manage.py clear_products_sales            # নিশ্চিত করতে জিজ্ঞেস করবে
    python manage.py clear_products_sales --yes      # জিজ্ঞেস না করে
    python manage.py clear_products_sales --yes --seed   # মুছে সাথে সাথে seed_dry_fruits চালায়

যা মোছে : Sale(+items, batch), Purchase(+items, batch), SalesReturn, PurchaseReturn, Product(+sale modes)
যা থাকে : ক্যাটাগরি, ইউনিট, সেল মোড, কাস্টমার, সাপ্লায়ার, অ্যাকাউন্ট, ইউজার, মানি রিসিপ্ট, ট্রানজেকশন
সতর্কতা: অ্যাকাউন্ট ব্যালেন্স/কাস্টমার বকেয়া/সাপ্লায়ার হিসাব নিজে থেকে ঠিক হয় না।
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'পুরনো পণ্য ও বিক্রি (সাথে ক্রয়/রিটার্ন) মুছে ফেলে।'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='নিশ্চিতকরণ ছাড়াই মুছুন')
        parser.add_argument('--seed', action='store_true', help='মোছার পর seed_dry_fruits চালান')

    def handle(self, *args, **opts):
        from products.models import Product
        from sales.models import Sale, SaleItem
        from purchases.models import Purchase, PurchaseItem
        from returns.models import SalesReturn, PurchaseReturn

        counts = {
            'পণ্য': Product.objects.count(),
            'বিক্রি (Sale)': Sale.objects.count(),
            'বিক্রির আইটেম': SaleItem.objects.count(),
            'ক্রয় (Purchase)': Purchase.objects.count(),
            'ক্রয়ের আইটেম': PurchaseItem.objects.count(),
            'সেলস রিটার্ন': SalesReturn.objects.count(),
            'পারচেজ রিটার্ন': PurchaseReturn.objects.count(),
        }
        self.stdout.write('মুছে যাবে:')
        for k, v in counts.items():
            self.stdout.write(f'  {k}: {v}')

        if not opts['yes']:
            ans = input('\nসত্যিই মুছবেন? ব্যাকআপ নিয়েছেন তো? (yes লিখুন): ').strip().lower()
            if ans != 'yes':
                self.stdout.write(self.style.WARNING('বাতিল করা হল, কিছু মোছা হয়নি।'))
                return

        with transaction.atomic():
            # queryset.delete() ব্যবহার — মডেলের কাস্টম delete() (স্টক ফেরত ইত্যাদি) চলে না, কারণ পণ্যই মুছে যাচ্ছে
            SalesReturn.objects.all().delete()
            PurchaseReturn.objects.all().delete()
            Sale.objects.all().delete()
            Purchase.objects.all().delete()
            Product.objects.all().delete()

        self.stdout.write(self.style.SUCCESS('পুরনো পণ্য ও বিক্রি মোছা হয়েছে।'))

        if opts['seed']:
            call_command('seed_dry_fruits')