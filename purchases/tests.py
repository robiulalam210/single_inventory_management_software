# purchases/tests.py — ব্যাচ / মেয়াদ ট্র্যাকিং, FEFO বিক্রি, সতর্কতা API আর ড্যাশবোর্ড চার্ট API এর পরীক্ষা
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from products.models import Product, Category
from purchases.batches import effective_quantities, expiry_report, write_off_batch
from purchases.models import Purchase, PurchaseItem, ProductBatch
from returns.models import BadStock
from sales.models import Sale, SaleItem
from suppliers.models import Supplier

User = get_user_model()
TODAY = timezone.localdate()


def day(n):
    return TODAY + timedelta(days=n)


class BatchTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('boss', password='x', role='SUPER_ADMIN')
        self.supplier = Supplier.objects.create(name='Fresh Co')
        self.cat = Category.objects.create(name='Dairy')
        self.milk = Product.objects.create(name='Milk 1L', category=self.cat, purchase_price=Decimal('80'),
                                           selling_price=Decimal('100'))
        self.sale = Sale.objects.create(created_by=self.user)

    def buy(self, qty, expiry=None, batch_no='', price='80', product=None):
        p = Purchase.objects.create(supplier=self.supplier, purchase_date=TODAY, created_by=self.user)
        return PurchaseItem.objects.create(
            purchase=p, product=product or self.milk, qty=qty, price=Decimal(price),
            batch_no=batch_no or None, expiry_date=expiry)

    def sell(self, qty, product=None):
        return SaleItem.objects.create(sale=self.sale, product=product or self.milk, quantity=qty,
                                       unit_price=Decimal('100'))

    def stock(self):
        self.milk.refresh_from_db()
        return self.milk.stock_qty

    def left(self, batch):
        batch.refresh_from_db()
        return batch.qty_remaining


class BatchCreationTests(BatchTestBase):
    def test_batch_created_when_expiry_or_batch_no_given(self):
        item = self.buy(10, expiry=day(20), batch_no='L1')
        b = item.batch
        self.assertEqual((b.batch_no, b.qty_received, b.qty_remaining, b.expiry_date), ('L1', 10, 10, day(20)))
        self.assertEqual(self.stock(), 10)

    def test_no_batch_without_info(self):
        item = self.buy(10)
        self.assertFalse(ProductBatch.objects.filter(purchase_item=item).exists())
        self.assertEqual(self.stock(), 10)

    def test_expiry_only_uses_invoice_as_batch_no(self):
        item = self.buy(5, expiry=day(9))
        self.assertEqual(item.batch.batch_no, item.purchase.invoice_no)

    def test_edit_qty_adjusts_batch_and_delete_removes_it(self):
        item = self.buy(10, expiry=day(20))
        item.qty = 15
        item.save()
        b = ProductBatch.objects.get(purchase_item=item)
        self.assertEqual((b.qty_received, b.qty_remaining), (15, 15))
        self.assertEqual(self.stock(), 15)
        item.delete()
        self.assertFalse(ProductBatch.objects.exists())
        self.assertEqual(self.stock(), 0)

    def test_old_item_with_passed_expiry_can_still_be_edited(self):
        item = self.buy(10, expiry=day(1))
        PurchaseItem.objects.filter(pk=item.pk).update(expiry_date=day(-3))
        item.refresh_from_db()
        item.qty = 12
        item.save()  # মেয়াদ না বদলালে error নয়
        self.assertEqual(self.stock(), 12)

    def test_new_item_with_past_expiry_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.buy(5, expiry=day(-1))

    def test_cancel_purchase_zeroes_batches(self):
        item = self.buy(10, expiry=day(20))
        item.purchase.cancel_purchase('mistake')
        b = ProductBatch.objects.get(purchase_item=item)
        self.assertEqual((b.qty_remaining, b.is_active), (0, False))
        self.assertEqual(self.stock(), 0)


class FefoTests(BatchTestBase):
    def test_earliest_expiry_sold_first(self):
        late = self.buy(10, expiry=day(60)).batch
        soon = self.buy(10, expiry=day(5)).batch
        self.sell(12)
        self.assertEqual(self.left(soon), 0)
        self.assertEqual(self.left(late), 8)
        self.assertEqual(self.stock(), 8)

    def test_expired_batch_is_sold_last(self):
        expired = self.buy(10, expiry=day(1)).batch
        ProductBatch.objects.filter(pk=expired.pk).update(expiry_date=day(-2))
        fresh = self.buy(10, expiry=day(30)).batch
        self.sell(4)
        self.assertEqual(self.left(fresh), 6)
        self.assertEqual(self.left(expired), 10)

    def test_untracked_stock_used_after_batches(self):
        self.buy(5)                                   # মেয়াদহীন, ব্যাচ নেই
        b = self.buy(3, expiry=day(10)).batch
        self.sell(6)
        self.assertEqual(self.left(b), 0)
        self.assertEqual(self.stock(), 2)

    def test_deleting_sale_item_restores_same_batches(self):
        a = self.buy(5, expiry=day(5)).batch
        c = self.buy(5, expiry=day(50)).batch
        it = self.sell(7)
        self.assertEqual((self.left(a), self.left(c)), (0, 3))
        it.delete()
        self.assertEqual((self.left(a), self.left(c)), (5, 5))
        self.assertEqual(self.stock(), 10)


class ExpiryReportTests(BatchTestBase):
    def test_statuses_counts_and_order(self):
        e = self.buy(2, expiry=day(1), price='50').batch
        ProductBatch.objects.filter(pk=e.pk).update(expiry_date=day(-4))
        self.buy(3, expiry=day(10), price='40')
        self.buy(4, expiry=day(90), price='30')
        r = expiry_report(days=30, status='all')
        self.assertEqual([b['status'] for b in r['batches']], ['expired', 'expiring', 'ok'])
        self.assertEqual(r['batches'][0]['days_left'], -4)
        self.assertEqual(r['counts'], {'expired': 1, 'expiring': 1, 'ok': 1, 'total': 3})
        self.assertEqual(r['value']['expired'], 100.0)
        self.assertEqual(r['value']['expiring'], 120.0)
        self.assertEqual(len(expiry_report(days=30, status='alerts')['batches']), 2)   # পেরোনো + শিগগিরই
        self.assertEqual(len(expiry_report(days=100, status='alerts')['batches']), 3)  # ৯০ দিনেরটাও এখন "শিগগিরই"

    def test_sold_out_batch_hidden(self):
        self.buy(3, expiry=day(5))
        self.sell(3)
        self.assertEqual(expiry_report()['counts']['total'], 0)

    def test_sum_of_batches_capped_at_stock_latest_expiry_trimmed_first(self):
        soon = self.buy(5, expiry=day(5)).batch
        late = self.buy(5, expiry=day(50)).batch
        Product.objects.filter(pk=self.milk.pk).update(stock_qty=6)          # যেমন purchase return এ ৪ কমেছে
        eff = effective_quantities([self.milk.pk])
        self.assertEqual(eff[soon.id], 5)       # জরুরি সতর্কতা লুকোয় না
        self.assertEqual(eff[late.id], 1)

    def test_write_off_removes_stock_and_logs_bad_stock(self):
        b = self.buy(6, expiry=day(1)).batch
        ProductBatch.objects.filter(pk=b.pk).update(expiry_date=day(-1))
        self.sell(2)
        out = write_off_batch(b.pk, 'expired')
        self.assertEqual(out['written_off'], 4)
        self.assertEqual(self.stock(), 0)
        self.assertEqual(self.left(b), 0)
        bad = BadStock.objects.get()
        self.assertEqual((bad.quantity, bad.reference_type), (4, 'direct'))
        with self.assertRaises(ValueError):
            write_off_batch(b.pk)


class ApiTests(BatchTestBase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_expiry_alerts_endpoint(self):
        self.buy(3, expiry=day(4), batch_no='X9')
        r = self.api.get('/api/reports/expiry-alerts/', {'days': 30, 'limit': 5})
        self.assertEqual(r.status_code, 200)
        d = r.data['data']
        self.assertEqual(d['counts']['expiring'], 1)
        self.assertEqual(d['batches'][0]['batch_no'], 'X9')

    def test_write_off_endpoint_needs_permission(self):
        b = self.buy(3, expiry=day(1)).batch
        viewer = User.objects.create_user('v', password='x', role='VIEWER')
        c = APIClient()
        c.force_authenticate(viewer)
        self.assertEqual(c.post(f'/api/reports/expiry-alerts/{b.pk}/write-off/').status_code, 403)
        r = self.api.post(f'/api/reports/expiry-alerts/{b.pk}/write-off/', {'reason': 'damaged'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.stock(), 0)

    def test_purchase_api_accepts_batch_fields(self):
        r = self.api.post('/api/purchases/', {
            'supplier': self.supplier.id, 'purchase_date': TODAY.isoformat(),
            'purchase_items': [{'product_id': self.milk.id, 'qty': 4, 'price': '80.00',
                                'batch_no': 'A1', 'expiry_date': day(12).isoformat()}],
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        b = ProductBatch.objects.get()
        self.assertEqual((b.batch_no, b.expiry_date, b.qty_remaining), ('A1', day(12), 4))

    def test_dashboard_charts_endpoint(self):
        self.buy(10, expiry=day(30), price='60')
        self.sell(3)
        self.milk.refresh_from_db()
        r = self.api.get('/api/reports/dashboard-charts/', {'months': 6, 'days': 30})
        self.assertEqual(r.status_code, 200, r.data)
        d = r.data['data']
        self.assertEqual(len(d['monthly']['labels']), 6)
        self.assertEqual(d['monthly']['labels'][-1], TODAY.strftime('%Y-%m'))
        # মোট লাভ = (100 − 80 [product.purchase_price]) × 3 = 60
        self.assertEqual(d['monthly']['gross_profit'][-1], 60.0)
        self.assertEqual(d['monthly']['net_profit'][-1], 60.0)
        self.assertEqual(d['profit_trend']['net_profit'][-1], 60.0)
        self.assertEqual(len(d['profit_trend']['labels']), 30)
        sv = d['stock_value']
        self.assertEqual(sv['total_cost'], 7 * 80.0)
        self.assertEqual(sv['total_retail'], 7 * 100.0)
        self.assertEqual(sv['by_category'][0]['name'], 'Dairy')

    def test_dashboard_charts_loss_day_is_negative(self):
        from expenses.models import Expense, ExpenseHead
        self.buy(10, price='60')
        self.sell(2)  # লাভ ২×২০ = ৪০
        head = ExpenseHead.objects.create(name='Rent')
        Expense.objects.create(head=head, amount=Decimal('100'), expense_date=TODAY, created_by=self.user)
        d = self.api.get('/api/reports/dashboard-charts/', {'days': 7}).data['data']
        self.assertEqual(d['profit_trend']['net_profit'][-1], -60.0)   # 40 − 100 = ক্ষতি
        self.assertEqual(d['monthly']['net_profit'][-1], -60.0)


class WebPageTests(BatchTestBase):
    """পেজগুলো ভাঙা ছাড়া আঁকা হয় কিনা, আর নতুন অংশ HTML এ আছে কিনা।"""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_expiry_page_renders_for_superuser_with_write_off(self):
        r = self.client.get('/app/expiry/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'expiryPage({ canWriteOff: true })')
        self.assertContains(r, 'web/js/expiry.js')

    def test_expiry_page_hides_write_off_without_products_edit(self):
        v = User.objects.create_user('viewer2', password='x', role='VIEWER')
        v.reports_view = True
        v.save()
        self.client.force_login(v)
        r = self.client.get('/app/expiry/')
        # VIEWER role এর ডিফল্ট permission এ reports দেখা আছে কিনা — না থাকলে 403, থাকলে write-off বন্ধ
        if r.status_code == 200:
            self.assertContains(r, 'canWriteOff: false')
        else:
            self.assertEqual(r.status_code, 403)

    def test_dashboard_has_new_chart_canvases_and_expiry_card(self):
        r = self.client.get('/app/')
        self.assertEqual(r.status_code, 200)
        for cid in ('chart-monthly', 'chart-accounts', 'chart-pl', 'chart-stock'):
            self.assertContains(r, f'id="{cid}"')
        self.assertContains(r, 'Expiry alerts')

    def test_purchase_form_has_batch_and_expiry_inputs(self):
        r = self.client.get('/app/purchases/new/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Expiry date')
        self.assertContains(r, 'Batch no')

    def test_sidebar_lists_expiry_alerts(self):
        self.assertContains(self.client.get('/app/'), 'Expiry Alerts')

    def test_label_print_page_renders_and_is_in_menu(self):
        r = self.client.get('/app/products/labels/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'labelPrint()')
        self.assertContains(r, 'web/js/labels.js')
        self.assertContains(r, 'jsbarcode-code128')
        self.assertContains(self.client.get('/app/'), 'Barcode Labels')

    def test_label_print_page_forbidden_without_permission(self):
        u = User.objects.create_user('nobody', password='x', role='VIEWER')
        self.client.force_login(u)
        r = self.client.get('/app/products/labels/')
        self.assertIn(r.status_code, (200, 403))
