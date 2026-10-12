# dayclose/tests.py — দিন বন্ধের সারাংশ, বন্ধ করা, অনুমতি
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Account
from expenses.models import Expense
from sales.models import Sale
from transactions.models import Transaction

User = get_user_model()


class DayCloseTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_user('boss', password='x', role='SUPER_ADMIN')
        self.api = APIClient()
        self.api.force_authenticate(self.boss)
        self.today = timezone.localdate()
        self.cash = Account.objects.create(name='Drawer', ac_type='Cash', created_by=self.boss)
        Transaction.objects.create(account=self.cash, transaction_type='credit', amount=Decimal('1000'),
                                   payment_method='cash', status='completed', created_by=self.boss)
        self.cash.refresh_from_db()
        sale = Sale.objects.create(created_by=self.boss)
        Sale.objects.filter(pk=sale.pk).update(grand_total=Decimal('1500'), paid_amount=Decimal('1000'),
                                               due_amount=Decimal('500'))
        Expense.objects.create(amount=Decimal('200'), account=self.cash, created_by=self.boss)

    def summary(self):
        r = self.api.get('/api/day-close/summary/', {'date': self.today.isoformat()})
        self.assertEqual(r.status_code, 200, r.content)
        return r.data['data']

    def test_summary_numbers(self):
        d = self.summary()['summary']
        self.assertEqual(d['sales']['count'], 1)
        self.assertEqual(d['sales']['total'], 1500.0)
        self.assertEqual(d['sales']['due'], 500.0)
        self.assertEqual(d['expenses']['total'], 200.0)
        acc = [a for a in d['accounts'] if a['account_id'] == self.cash.id][0]
        self.assertEqual(acc['money_in'] - acc['money_out'], 800.0)
        self.assertEqual(acc['expected'], 800.0)

    def test_close_records_difference(self):
        r = self.api.post('/api/day-close/', {'date': self.today.isoformat(),
                                              'counts': {str(self.cash.id): 790}, 'note': 'short 10'}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data['data']['difference'], -10.0)
        self.assertEqual(self.summary()['closed']['total_counted'], 790.0)

    def test_cannot_close_twice_or_future(self):
        body = {'date': self.today.isoformat(), 'counts': {str(self.cash.id): 800}}
        self.assertEqual(self.api.post('/api/day-close/', body, format='json').status_code, 201)
        self.assertEqual(self.api.post('/api/day-close/', body, format='json').status_code, 400)
        future = (self.today + timezone.timedelta(days=2)).isoformat()
        self.assertEqual(self.api.post('/api/day-close/', {'date': future}, format='json').status_code, 400)

    def test_bad_amount_rejected(self):
        r = self.api.post('/api/day-close/', {'date': self.today.isoformat(),
                                              'counts': {str(self.cash.id): 'abc'}}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_reopen_and_permission(self):
        r = self.api.post('/api/day-close/', {'date': self.today.isoformat(), 'counts': {}}, format='json')
        pk = r.data['data']['id']
        nobody = User.objects.create_user('nobody', password='x', role='VIEWER')
        c = APIClient(); c.force_authenticate(nobody)
        body = {'date': (self.today - timezone.timedelta(days=1)).isoformat(), 'counts': {}}
        self.assertEqual(c.post('/api/day-close/', body, format='json').status_code, 403)
        self.assertEqual(c.delete(f'/api/day-close/{pk}/').status_code, 403)
        self.assertEqual(self.api.delete(f'/api/day-close/{pk}/').status_code, 200)
        self.assertIsNone(self.summary()['closed'])


class DayClosePageTests(TestCase):
    def test_page_renders_and_is_in_menu(self):
        from django.test import Client
        boss = User.objects.create_user('boss2', password='x', role='SUPER_ADMIN')
        c = Client(); c.force_login(boss)
        r = c.get('/app/reports/day-close/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'dayClose()')
        self.assertContains(r, 'Day Close')
