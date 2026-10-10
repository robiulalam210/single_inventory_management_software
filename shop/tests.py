import json
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import User
from products.models import Category, Product

from .models import ShopOrder, ShopSettings


def make_product(name, price, stock, **kw):
    return Product.objects.create(name=name, selling_price=Decimal(price), stock_qty=stock, **kw)


@override_settings(ALLOWED_HOSTS=['*'])
class ShopFlowTests(TestCase):
    def setUp(self):
        cache.clear()   # অর্ডার rate-limit টেস্টের মধ্যে জমে না যেন
        self.cat = Category.objects.create(name='Grocery')
        self.rice = make_product('Rice 5kg', '650.00', 10, category=self.cat)
        self.oil = make_product('Oil 1L', '200.00', 3,
                                discount_type='percentage', discount_value=Decimal('10'), discount_applied_on=True)
        self.hidden = make_product('Out of stock item', '10.00', 0)

    def order(self, items, **extra):
        body = {'name': 'Rahim', 'phone': '01712345678', 'address': 'Mirpur, Dhaka', 'items': items}
        body.update(extra)
        url = reverse('shop:place_order')
        return self.client.post(url, json.dumps(body), content_type='application/json')

    # ── public page ──
    def test_home_shows_products_and_login(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('Rice 5kg', html)
        self.assertIn('Login', html)
        self.assertNotIn('Out of stock item', html)

    def test_discount_price_used(self):
        r = self.order([{'id': self.oil.pk, 'qty': 1}])
        self.assertEqual(r.status_code, 200, r.content)
        item = ShopOrder.objects.get().items.get()
        self.assertEqual(item.unit_price, self.oil.final_price)
        self.assertLess(item.unit_price, Decimal('200.00'))

    # ── ordering & stock ──
    def test_order_reserves_stock_and_adds_delivery(self):
        ss = ShopSettings.load()
        ss.delivery_charge = Decimal('60'); ss.free_delivery_min = Decimal('1500'); ss.save()
        r = self.order([{'id': self.rice.pk, 'qty': 2}])
        self.assertEqual(r.status_code, 200, r.content)
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.stock_qty, 8)
        o = ShopOrder.objects.get()
        self.assertEqual(o.delivery_charge, Decimal('60.00'))
        self.assertEqual(o.total, Decimal('1360.00'))
        self.assertTrue(o.stock_deducted)
        self.assertTrue(o.order_no.startswith('WEB-'))

    def test_free_delivery_over_threshold(self):
        ss = ShopSettings.load()
        ss.delivery_charge = Decimal('60'); ss.free_delivery_min = Decimal('1000'); ss.save()
        self.order([{'id': self.rice.pk, 'qty': 2}])
        self.assertEqual(ShopOrder.objects.get().delivery_charge, Decimal('0.00'))

    def test_cannot_order_more_than_stock(self):
        r = self.order([{'id': self.oil.pk, 'qty': 4}])
        self.assertEqual(r.status_code, 409)
        self.oil.refresh_from_db()
        self.assertEqual(self.oil.stock_qty, 3)
        self.assertEqual(ShopOrder.objects.count(), 0)

    def test_client_cannot_set_price(self):
        r = self.order([{'id': self.rice.pk, 'qty': 1, 'price': 1}])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ShopOrder.objects.get().total, Decimal('650.00'))

    def test_bad_phone_and_empty_cart_rejected(self):
        self.assertEqual(self.order([{'id': self.rice.pk, 'qty': 1}], phone='123').status_code, 400)
        self.assertEqual(self.order([]).status_code, 400)

    def test_cancel_restores_stock_and_confirm_does_not_double_deduct(self):
        self.order([{'id': self.rice.pk, 'qty': 3}])
        o = ShopOrder.objects.get()
        o.change_status('confirmed')
        self.rice.refresh_from_db(); self.assertEqual(self.rice.stock_qty, 7)   # still 7, not 4
        o.refresh_from_db(); o.change_status('cancelled')
        self.rice.refresh_from_db(); self.assertEqual(self.rice.stock_qty, 10)
        self.assertIsNone(ShopOrder.objects.get().sale)

    def test_closed_shop_rejects_orders(self):
        ss = ShopSettings.load(); ss.is_open = False; ss.save()
        self.assertEqual(self.order([{'id': self.rice.pk, 'qty': 1}]).status_code, 403)

    # ── delivery → Sale / accounts ──
    def _delivered_order(self, cash):
        from accounts.models import Account
        ss = ShopSettings.load(); ss.delivery_charge = Decimal('60'); ss.save()
        acct = Account.objects.create(name='Cash in hand', ac_type='Cash')
        self.order([{'id': self.rice.pk, 'qty': 2}])
        u = User.objects.create_user(username='seller', password='x', role='ADMIN')
        o = ShopOrder.objects.get()
        o.change_status('confirmed', user=u)
        o = ShopOrder.objects.get(pk=o.pk)
        o.change_status('delivered', user=u, cash_received=cash)
        return ShopOrder.objects.get(pk=o.pk), acct

    def test_delivery_creates_sale_once_and_stock_not_double_deducted(self):
        o, acct = self._delivered_order(cash=False)
        self.assertEqual(o.status, 'delivered')
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.stock_qty, 8)           # 10 − 2, দুইবার নয়
        sale = o.sale
        self.assertEqual(sale.grand_total, Decimal('1360.00'))
        self.assertEqual(sale.due_amount, Decimal('1360.00'))
        self.assertEqual(sale.customer.phone, '01712345678')
        self.assertEqual(sale.items.count(), 1)

    def test_cash_received_records_receipt_and_account_balance(self):
        from money_receipts.models import MoneyReceipt
        o, acct = self._delivered_order(cash=True)
        sale = o.sale
        self.assertEqual(sale.paid_amount, Decimal('1360.00'))
        self.assertEqual(sale.payment_status, 'paid')
        self.assertEqual(MoneyReceipt.objects.filter(sale=sale).count(), 1)
        acct.refresh_from_db()
        self.assertEqual(acct.balance, Decimal('1360.00'))   # একবারই জমা
        self.rice.refresh_from_db(); self.assertEqual(self.rice.stock_qty, 8)

    def test_delivery_without_account_rolls_back(self):
        from django.core.exceptions import ValidationError
        self.order([{'id': self.rice.pk, 'qty': 2}])
        u = User.objects.create_user(username='seller', password='x', role='ADMIN')
        o = ShopOrder.objects.get(); o.change_status('confirmed', user=u)
        o = ShopOrder.objects.get(pk=o.pk)
        with self.assertRaises(ValidationError):
            o.change_status('delivered', user=u, cash_received=True)
        o = ShopOrder.objects.get(pk=o.pk)
        self.assertEqual(o.status, 'confirmed'); self.assertIsNone(o.sale)
        self.rice.refresh_from_db(); self.assertEqual(self.rice.stock_qty, 8)   # reserve আগের মতোই
        from sales.models import Sale
        self.assertEqual(Sale.objects.count(), 0)

    def test_returning_customer_reused(self):
        from customers.models import Customer
        self.order([{'id': self.rice.pk, 'qty': 1}])
        self.order([{'id': self.rice.pk, 'qty': 1}])
        u = User.objects.create_user(username='seller', password='x', role='ADMIN')
        for o in ShopOrder.objects.all():
            o.change_status('confirmed', user=u); ShopOrder.objects.get(pk=o.pk).change_status('delivered', user=u)
        self.assertEqual(Customer.objects.filter(phone='01712345678').count(), 1)

    def test_staff_deliver_via_page(self):
        from accounts.models import Account
        Account.objects.create(name='Cash in hand', ac_type='Cash')
        self.order([{'id': self.rice.pk, 'qty': 1}])
        self.staff(sales_view=True, sales_edit=True)
        o = ShopOrder.objects.get()
        self.client.post(reverse('web:shop_orders'), {'order_id': o.pk, 'action': 'confirm'})
        r = self.client.post(reverse('web:shop_orders'), {'order_id': o.pk, 'action': 'deliver', 'cash_received': 'on'})
        self.assertEqual(r.status_code, 302)
        o.refresh_from_db(); self.assertEqual(o.status, 'delivered'); self.assertIsNotNone(o.sale)
        page = self.client.get(reverse('web:shop_orders') + '?status=delivered').content.decode()
        self.assertIn(o.sale.invoice_no, page)

    # ── staff side ──
    def staff(self, role='ADMIN', **perms):
        u = User.objects.create_user(username='boss', password='pw12345!', role=role, **perms)
        self.client.force_login(u)
        return u

    def test_staff_orders_confirm_flow(self):
        self.order([{'id': self.rice.pk, 'qty': 1}])
        self.staff(sales_view=True, sales_edit=True, can_access_dashboard=True)
        r = self.client.get(reverse('web:shop_orders'))
        self.assertEqual(r.status_code, 200, r.content[:500])
        self.assertIn('WEB-', r.content.decode())
        o = ShopOrder.objects.get()
        r = self.client.post(reverse('web:shop_orders'), {'order_id': o.pk, 'action': 'confirm'})
        self.assertEqual(r.status_code, 302)
        o.refresh_from_db(); self.assertEqual(o.status, 'confirmed')

    def test_permissions_are_enforced(self):
        self.order([{'id': self.rice.pk, 'qty': 1}])
        u = self.staff(role='STAFF')
        # view আছে, edit নেই → দেখতে পারে, confirm/settings পারে না
        User.objects.filter(pk=u.pk).update(sales_view=True, sales_edit=False)
        self.client.force_login(User.objects.get(pk=u.pk))
        self.assertEqual(self.client.get(reverse('web:shop_orders')).status_code, 200)
        o = ShopOrder.objects.get()
        r = self.client.post(reverse('web:shop_orders'), {'order_id': o.pk, 'action': 'confirm'})
        self.assertEqual(r.status_code, 403)
        o.refresh_from_db(); self.assertEqual(o.status, 'pending')
        self.assertEqual(self.client.get(reverse('web:shop_settings')).status_code, 403)
        # view ও নেই → কিছুই না
        User.objects.filter(pk=u.pk).update(sales_view=False)
        self.client.force_login(User.objects.get(pk=u.pk))
        self.assertEqual(self.client.get(reverse('web:shop_orders')).status_code, 403)

    def test_settings_page_saves(self):
        self.staff(sales_view=True, sales_edit=True)
        self.assertEqual(self.client.get(reverse('web:shop_settings')).status_code, 200)
        r = self.client.post(reverse('web:shop_settings'), {
            'is_open': 'on', 'shop_name': 'Alpha Shop', 'brand_color': '#aa3300',
            'default_theme': 'dark', 'hero_button_text': 'Buy now', 'delivery_charge': '50', 'free_delivery_min': '0',
            'whatsapp': '+880 1712-345678',
        })
        self.assertEqual(r.status_code, 302, r.content.decode()[:800])
        ss = ShopSettings.load()
        self.assertEqual(ss.brand_color, '#aa3300')
        self.assertEqual(ss.whatsapp, '8801712345678')
        html = self.client.get('/').content.decode()
        self.assertIn('Alpha Shop', html); self.assertIn('--brand:#aa3300', html)

    def test_dashboard_still_renders(self):
        self.staff(sales_view=True, sales_edit=True, can_access_dashboard=True)
        self.assertIn(self.client.get(reverse('web:home')).status_code, (200, 302))
