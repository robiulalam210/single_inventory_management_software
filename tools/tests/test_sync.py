import os, sys, uuid, json, django
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ['DJANGO_SETTINGS_MODULE']='inventory_api.settings'
django.setup()
import datetime
from rest_framework.test import APIClient
from core.models import User
from products.models import Product
from sales.models import Sale
from customers.models import Customer
from offline_sync import views as sv
from offline_sync.models import ChangeLog, SyncIssue, ProcessedOperation
sv.PULL_SAFETY_LAG = datetime.timedelta(seconds=0)

u = User.objects.get(id=3)
c = APIClient(SERVER_NAME='localhost'); c.force_authenticate(u)
dev = str(uuid.uuid4())
H = {'HTTP_X_DEVICE_ID': dev, 'HTTP_X_CLIENT_SOURCE': 'desktop'}

def j(r):
    return r.json() if hasattr(r,'json') else r.data

r = c.post('/api/sync/devices/register/', {'device_id': dev, 'name': 'Counter PC', 'platform': 'windows'}, format='json', **H)
print('register', r.status_code, j(r)['data']['device_code'])
code = j(r)['data']['device_code']

r = c.get('/api/sync/manifest/', **H); m = j(r)['data']
print('manifest', r.status_code, [(e['entity'], e['count']) for e in m['entities'] if e['count']][:8])
r = c.get('/api/sync/bootstrap/?entity=product', **H); b = j(r)['data']
print('bootstrap product', r.status_code, b['total'], 'keys', sorted(b['items'][0].keys())[:8])

p = Product.objects.get(id=1); stock0 = p.stock_qty
phone = '017' + str(uuid.uuid4().int)[:8]
op_c, op_s, op_m = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
inv = f'SL-{code}-00001'
ops = [
  {'op_id': op_c, 'method':'POST', 'path':'/api/customers/', 'local_id': -1, 'user_id': u.id,
   'client_created_at': '2026-10-01T15:25:00+06:00', 'payload': {'name':'Offline Karim','phone':phone,'address':'Dhaka'}},
  {'op_id': op_s, 'method':'POST', 'path':'/api/sales/', 'local_id': -2, 'user_id': u.id,
   'client_created_at': '2026-10-01T15:30:00+06:00',
   'payload': {'type':'normal_sale','sale_date':'2026-10-01','sale_by': str(u.id),'overall_vat_type':'fixed','vat':0,
     'overall_service_type':'fixed','service_charge':0,'overall_delivery_type':'fixed','delivery_charge':0,
     'overall_discount_type':'fixed','overall_discount':0,'remark':'offline',
     'items':[{'product_id':1,'quantity':2,'unit_price':12.0,'discount':0.0,'discount_type':'fixed'}],
     'customer_type':'saved_customer','with_money_receipt':'No','paid_amount':0.0,'due_amount':24.0,
     'customer_id':'-1','offline_invoice_no': inv}},
  {'op_id': op_m, 'method':'POST', 'path':'/api/money-receipts/', 'local_id': -3, 'user_id': u.id,
   'client_created_at': '2026-10-01T15:40:00+06:00',
   'payload': {'amount': 10.0,'customer_id':'-1','payment_date':'2026-10-01','payment_method':'Cash','seller_id':str(u.id),
     'account':'1','specific_invoice':True,'payment_type':'specific','sale':'-2'}},
]
r = c.post('/api/sync/push/', {'device_id': dev, 'ops': ops}, format='json', **H)
res = j(r)['data']['results']
for x in res: print(' push1', x['status'], x['server_id'], x['message'][:120])

r = c.post('/api/sync/push/', {'device_id': dev, 'ops': ops}, format='json', **H)
print('push2 (retry) statuses', [x['status'] for x in j(r)['data']['results']])

p.refresh_from_db()
sale = Sale.objects.get(id=res[1]['server_id'])
print('stock', stock0, '->', p.stock_qty, '| sale', sale.invoice_no, sale.sale_date, 'paid', sale.paid_amount, 'due', sale.due_amount, sale.payment_status)
print('customers with phone', Customer.objects.filter(phone=phone).count())

# stock conflict
big = dict(ops[1]); big = json.loads(json.dumps(big)); big['op_id']=str(uuid.uuid4()); big['local_id']=-9
big['payload']['items'][0]['quantity'] = p.stock_qty + 50; big['payload']['offline_invoice_no']=f'SL-{code}-00002'
r = c.post('/api/sync/push/', {'device_id': dev, 'ops': [big]}, format='json', **H)
x = j(r)['data']['results'][0]; print('conflict push', x['status'], x['message'][:140])
p.refresh_from_db(); print('stock after conflict', p.stock_qty, '| open issues', SyncIssue.objects.filter(is_resolved=False, op_id=big['op_id']).count(),
   '| sale created?', Sale.objects.filter(invoice_no=f'SL-{code}-00002').exists())

# blocked dependency
blk = {'op_id': str(uuid.uuid4()), 'method':'POST','path':'/api/money-receipts/','local_id':-11,'user_id':u.id,
       'payload': {'amount': 1,'customer_id':'-77','payment_date':'2026-10-01','payment_method':'Cash','account':'1','payment_type':'overall'}}
r = c.post('/api/sync/push/', {'device_id': dev, 'ops': [blk]}, format='json', **H)
print('blocked', j(r)['data']['results'][0]['status'])

# pull
cursor = 0; n=0; ents=set()
while True:
    r = c.get(f'/api/sync/pull/?cursor={cursor}&limit=200', **H); d = j(r)['data']
    n += len(d['changes']); ents |= {ch['entity'] for ch in d['changes']}; cursor = d['next_cursor']
    if not d['has_more']: break
print('pull changes', n, sorted(ents), 'cursor', cursor)

# audit
r = c.get('/api/sync/audit/?source=desktop_offline&page_size=50', **H); a = j(r)['data']
print('audit offline rows', a['count'])
for row in a['results'][:40]:
    if row['model'] in ('sales.Sale','customers.Customer','money_receipts.MoneyReceipt') and row['action']=='create':
        print('  ', row['action'], row['model'], row['object_repr'][:30], 'by', row['user'], 'device', row['device'], 'client_time', row['client_time'], 'fields', len(row['changes']))
r = c.get(f'/api/sync/audit/?model=product&object_id=1&page_size=3', **H)
for row in j(r)['data']['results']: print('  product audit', row['action'], [ (ch['field'],ch['old'],ch['new']) for ch in row['changes'] if ch['field']=='stock_qty'], row['source'])

# idempotency middleware (mobile double-tap)
key = str(uuid.uuid4()); ph2 = '018' + str(uuid.uuid4().int)[:8]
r1 = c.post('/api/customers/', {'name':'Double Tap','phone':ph2}, format='json', HTTP_X_IDEMPOTENCY_KEY=key, HTTP_X_CLIENT_SOURCE='mobile')
r2 = c.post('/api/customers/', {'name':'Double Tap','phone':ph2}, format='json', HTTP_X_IDEMPOTENCY_KEY=key, HTTP_X_CLIENT_SOURCE='mobile')
print('idempotency', r1.status_code, r2.status_code, r2.get('X-Idempotent-Replay'), 'count', Customer.objects.filter(phone=ph2).count())
r = c.get('/api/sync/issues/', **H); print('issues api', len(j(r)['data']))
