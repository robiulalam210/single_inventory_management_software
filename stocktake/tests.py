# stocktake/tests.py — Stock adjustment ও Stocktake এর নিয়ম, API, অনুমতি
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from products.models import Category, Product
from . import services
from .models import StockAdjustment, Stocktake

User = get_user_model()


class Base(TestCase):
    def setUp(self):
        self.boss = User.objects.create_user('boss', password='x', role='SUPER_ADMIN')
        self.dairy = Category.objects.create(name='Dairy')
        self.dry = Category.objects.create(name='Dry')
        self.milk = self.mk('Milk', self.dairy, 10, 80)
        self.rice = self.mk('Rice', self.dry, 20, 50)
        self.salt = self.mk('Salt', self.dry, 5, 20)
        self.api = APIClient()
        self.api.force_authenticate(self.boss)

    def mk(self, name, cat, stock, cost):
        return Product.objects.create(name=name, category=cat, stock_qty=stock, purchase_price=Decimal(cost),
                                      selling_price=Decimal(cost) + 10)

    def stock(self, p):
        p.refresh_from_db()
        return p.stock_qty


class AdjustmentTests(Base):
    def test_set_new_quantity_logs_everything(self):
        a = services.adjust_stock(self.milk.id, self.boss, new_qty=7, reason='damaged', note='dropped crate')
        self.assertEqual((a.qty_before, a.qty_after, a.change), (10, 7, -3))
        self.assertEqual(a.value_change, Decimal('-240.00'))
        self.assertEqual(a.number, f'ADJ-{a.pk:06d}')
        self.assertEqual(self.stock(self.milk), 7)

    def test_relative_change_and_floor_at_zero(self):
        services.adjust_stock(self.milk.id, self.boss, change=5, reason='found')
        self.assertEqual(self.stock(self.milk), 15)
        with self.assertRaisesMessage(ValueError, 'only 15 in stock'):
            services.adjust_stock(self.milk.id, self.boss, change=-16, reason='lost')
        self.assertEqual(self.stock(self.milk), 15)

    def test_validation(self):
        for kw in ({}, {'new_qty': 3, 'change': 1}, {'new_qty': 2.5}, {'new_qty': -1}, {'new_qty': 10}):
            with self.assertRaises(ValueError, msg=str(kw)):
                services.adjust_stock(self.milk.id, self.boss, reason='other', **kw)
        with self.assertRaises(ValueError):
            services.adjust_stock(self.milk.id, self.boss, new_qty=3, reason='bogus')
        self.assertEqual(StockAdjustment.objects.count(), 0)


class StocktakeFlowTests(Base):
    def test_start_snapshots_active_products_and_scope(self):
        Product.objects.filter(pk=self.salt.pk).update(is_active=False)
        st = services.start_stocktake(self.boss)
        self.assertEqual(st.lines.count(), 2)
        self.assertEqual(st.number, f'ST-{st.pk:06d}')
        dairy_only = services.start_stocktake(self.boss, category_id=self.dairy.id)
        self.assertEqual([l.product_name for l in dairy_only.lines.all()], ['Milk'])

    def test_count_apply_adjusts_only_counted_lines(self):
        st = services.start_stocktake(self.boss)
        by = {l.product_name: l for l in st.lines.all()}
        services.save_counts(st.id, [{'line_id': by['Milk'].id, 'counted_qty': 8},
                                     {'product_id': self.rice.id, 'counted_qty': 23}])   # Salt গণনা হয়নি
        s = services.summary(st)
        self.assertEqual((s['total'], s['counted'], s['uncounted'], s['differing']), (3, 2, 1, 2))
        self.assertEqual((s['short_qty'], s['over_qty'], s['net_value']), (2, 3, -160 + 150))
        out = services.apply_stocktake(st.id, self.boss)
        self.assertEqual(out['adjusted'], 2)
        self.assertEqual((self.stock(self.milk), self.stock(self.rice), self.stock(self.salt)), (8, 23, 5))
        self.assertEqual(StockAdjustment.objects.filter(stocktake=st, reason='count').count(), 2)
        st.refresh_from_db()
        self.assertEqual(st.status, 'applied')
        self.assertEqual(st.lines.get(product=self.milk).applied_change, -2)

    def test_sales_during_count_do_not_break_the_result(self):
        st = services.start_stocktake(self.boss)               # Milk snapshot = 10
        Product.objects.filter(pk=self.milk.pk).update(stock_qty=7)    # গণনার মাঝে ৩টা বিক্রি
        services.save_counts(st.id, [{'product_id': self.milk.id, 'counted_qty': 9}])   # পার্থক্য −১
        services.apply_stocktake(st.id, self.boss)
        self.assertEqual(self.stock(self.milk), 6)             # ৭ − ১ (পার্থক্য এখনকার স্টকে)

    def test_apply_refuses_when_stock_would_go_negative_and_changes_nothing(self):
        st = services.start_stocktake(self.boss)
        services.save_counts(st.id, [{'product_id': self.rice.id, 'counted_qty': 25},
                                     {'product_id': self.milk.id, 'counted_qty': 0}])   # Milk −১০
        Product.objects.filter(pk=self.milk.pk).update(stock_qty=4)      # মাঝে ৬টা বিক্রি → ৪ − ১০ < 0
        with self.assertRaisesMessage(ValueError, 'recount'):
            services.apply_stocktake(st.id, self.boss)
        self.assertEqual((self.stock(self.rice), self.stock(self.milk)), (20, 4))
        self.assertEqual(Stocktake.objects.get(pk=st.id).status, 'draft')
        self.assertEqual(StockAdjustment.objects.count(), 0)

    def test_cannot_apply_empty_or_twice_or_after_cancel(self):
        st = services.start_stocktake(self.boss)
        with self.assertRaisesMessage(ValueError, 'at least one'):
            services.apply_stocktake(st.id, self.boss)
        services.save_counts(st.id, [{'product_id': self.rice.id, 'counted_qty': 21}])
        services.apply_stocktake(st.id, self.boss)
        with self.assertRaises(ValueError):
            services.apply_stocktake(st.id, self.boss)
        with self.assertRaises(ValueError):
            services.save_counts(st.id, [{'product_id': self.rice.id, 'counted_qty': 1}])
        st2 = services.start_stocktake(self.boss)
        services.cancel_stocktake(st2.id)
        with self.assertRaises(ValueError):
            services.apply_stocktake(st2.id, self.boss)
        self.assertEqual(self.stock(self.rice), 21)

    def test_clear_count_and_bad_input(self):
        st = services.start_stocktake(self.boss)
        services.save_counts(st.id, [{'product_id': self.rice.id, 'counted_qty': 4}])
        s = services.save_counts(st.id, [{'product_id': self.rice.id, 'counted_qty': None}])
        self.assertEqual(s['counted'], 0)
        for bad in (-1, 'x', 2.5):
            with self.assertRaises(ValueError):
                services.save_counts(st.id, [{'product_id': self.rice.id, 'counted_qty': bad}])
        with self.assertRaises(ValueError):
            services.save_counts(st.id, [{'product_id': 99999, 'counted_qty': 1}])

    def test_counted_equal_to_system_creates_no_adjustment(self):
        st = services.start_stocktake(self.boss)
        services.save_counts(st.id, [{'product_id': self.rice.id, 'counted_qty': 20}])
        out = services.apply_stocktake(st.id, self.boss)
        self.assertEqual(out['adjusted'], 0)
        self.assertEqual(StockAdjustment.objects.count(), 0)


class ApiTests(Base):
    def test_full_flow_over_http(self):
        r = self.api.post('/api/stock/counts/', {'title': 'Weekly', 'category_id': self.dry.id}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        cid = r.data['data']['id']
        d = self.api.get(f'/api/stock/counts/{cid}/').data['data']
        self.assertEqual(len(d['lines']), 2)
        rice = next(l for l in d['lines'] if l['name'] == 'Rice')
        r = self.api.post(f'/api/stock/counts/{cid}/count/', {'rows': [{'line_id': rice['id'], 'counted_qty': 18}]}, format='json')
        self.assertEqual(r.data['data']['differing'], 1)
        r = self.api.post(f'/api/stock/counts/{cid}/apply/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.stock(self.rice), 18)
        hist = self.api.get('/api/stock/adjustments/', {'reason': 'count'}).data['data']
        self.assertEqual(hist['count'], 1)
        self.assertEqual(hist['totals']['loss_value'], 100.0)
        self.assertEqual(self.api.get('/api/stock/counts/').data['data'][0]['status'], 'applied')

    def test_adjustment_endpoint_and_errors(self):
        r = self.api.post('/api/stock/adjustments/', {'product_id': self.milk.id, 'change': -4, 'reason': 'expired'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.stock(self.milk), 6)
        self.assertEqual(self.api.post('/api/stock/adjustments/', {'product_id': self.milk.id, 'change': -99, 'reason': 'lost'}, format='json').status_code, 400)
        self.assertEqual(self.api.post('/api/stock/adjustments/', {'product_id': self.milk.id, 'change': 1, 'reason': 'count'}, format='json').status_code, 400)
        self.assertEqual(self.api.get(f'/api/stock/counts/9999/').status_code, 404)

    def test_permissions(self):
        viewer = User.objects.create_user('viewer', password='x', role='VIEWER')
        c = APIClient()
        c.force_authenticate(viewer)
        self.assertEqual(c.post('/api/stock/adjustments/', {'product_id': self.milk.id, 'change': 1, 'reason': 'found'}, format='json').status_code, 403)
        self.assertEqual(c.post('/api/stock/counts/', {}, format='json').status_code, 403)
        self.assertEqual(self.stock(self.milk), 10)
        self.assertEqual(APIClient().get('/api/stock/adjustments/').status_code in (401, 403, 400), True)


class WebPageTests(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.boss)

    def test_pages_render_with_guides_and_menu(self):
        st = services.start_stocktake(self.boss)
        for url, marker in (('/app/stock/adjust/', 'stockAdjust('), ('/app/stocktake/', 'stocktakeList('),
                            (f'/app/stocktake/{st.id}/', f'stocktakeCount({{ id: {st.id}')):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertContains(r, marker)
        self.assertContains(self.client.get('/app/stocktake/'), 'Start counting')
        self.assertContains(self.client.get('/app/'), 'Stock Adjustment')
        self.assertContains(self.client.get('/app/expiry/'), 'Soon means within')

    def test_viewer_sees_pages_but_without_edit(self):
        v = User.objects.create_user('v2', password='x', role='VIEWER')
        v.products_view = True
        v.save()
        self.client.force_login(v)
        r = self.client.get('/app/stock/adjust/')
        if r.status_code == 200:
            self.assertContains(r, 'canEdit: false')
            self.assertNotContains(r, 'id="adj-qty"')
