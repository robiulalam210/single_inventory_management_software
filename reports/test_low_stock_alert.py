# reports/test_low_stock_alert.py — Low stock সতর্কতা API এর পরীক্ষা
# Django লাগে:  python manage.py test reports.test_low_stock_alert
# (reports/tests.py র মতো Django-ছাড়া পরীক্ষা থেকে আলাদা রাখা হয়েছে, যাতে ওটা আগের মতোই চলে)
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from products.models import Brand, Category, Product, Unit

URL = '/api/reports/low-stock-alert/'


class LowStockAlertTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_user('boss', password='pass-12345', role='ADMIN')
        cls.nobody = User.objects.create_user('nobody', password='pass-12345')
        for flag in ('can_access_dashboard', 'products_view', 'purchases_view', 'reports_view'):
            setattr(cls.nobody, flag, False)
        cls.nobody.save()
        cls.cat = Category.objects.create(name='Grocery')
        cls.brand = Brand.objects.create(name='Pran')
        cls.unit = Unit.objects.create(name='Pack')

    def make(self, name, stock, alert=5, active=True):
        return Product.objects.create(
            name=name, category=self.cat, brand=self.brand, unit=self.unit,
            purchase_price=Decimal('10'), selling_price=Decimal('15'),
            opening_stock=stock, stock_qty=stock, alert_quantity=alert, is_active=active)

    def get(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client.get(URL)

    def test_uses_each_products_own_alert_level_and_skips_inactive(self):
        self.make('Rice', 2)               # কম
        self.make('Oil', 0)                # শেষ
        self.make('Salt', 5)               # ঠিক alert এর সমান — ধরা পড়বে
        self.make('Sugar', 6)              # যথেষ্ট আছে
        self.make('Tea', 12, alert=20)     # global 10 এর বেশি, কিন্তু নিজের alert এর নিচে
        self.make('Old stock', 0, active=False)   # বন্ধ product — ধরা হবে না

        res = self.get(self.admin)
        self.assertEqual(res.status_code, 200)
        data = res.data['data']
        self.assertEqual([r['product_name'] for r in data['report']], ['Oil', 'Rice', 'Salt', 'Tea'])  # কম stock আগে
        self.assertEqual(data['summary'], {'total_low_stock_items': 4, 'critical_items': 1, 'running_low': 3})
        first = data['report'][0]
        self.assertEqual((first['total_stock_quantity'], first['alert_quantity']), (0, 5))

    def test_nothing_to_report_when_everything_is_stocked(self):
        self.make('Rice', 50)
        data = self.get(self.admin).data['data']
        self.assertEqual(data['report'], [])
        self.assertEqual(data['summary']['total_low_stock_items'], 0)

    def test_user_without_stock_related_permissions_is_refused(self):
        self.make('Rice', 1)
        self.assertEqual(self.get(self.nobody).status_code, 403)

    def test_anonymous_is_refused(self):
        self.assertIn(APIClient().get(URL).status_code, (401, 403))
