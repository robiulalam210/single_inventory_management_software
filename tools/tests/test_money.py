import os, sys, uuid, django, datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ['DJANGO_SETTINGS_MODULE']='inventory_api.settings'
django.setup()
import logging; logging.disable(logging.CRITICAL)
from decimal import Decimal as D
from rest_framework.test import APIClient
from core.models import User
from accounts.models import Account
from customers.models import Customer
from sales.models import Sale
from money_receipts.models import MoneyReceipt
from transactions.models import Transaction

u = User.objects.get(id=3)
c = APIClient(SERVER_NAME='localhost'); c.force_authenticate(u)
acc = Account.objects.get(id=1)
cust = Customer.objects.create(name='Test Cust', phone='019'+str(uuid.uuid4().int)[:8])

def snap():
    acc.refresh_from_db(); cust.refresh_from_db()
    return dict(bal=acc.balance, adv=cust.advance_balance, tx=Transaction.objects.filter(account=acc).count(), mr=MoneyReceipt.objects.all().count())

def diff(a,b): return {k: b[k]-a[k] for k in a}

def sale(paid, mr='Yes', customer=True, items=((1,2,12.0),(1,1,12.0))):
    body = {'type':'normal_sale','sale_date': datetime.date.today().isoformat(),'sale_by':str(u.id),
        'overall_vat_type':'fixed','vat':0,'overall_service_type':'fixed','service_charge':0,
        'overall_delivery_type':'fixed','delivery_charge':0,'overall_discount_type':'fixed','overall_discount':0,
        'remark':'t','items':[{'product_id':p,'quantity':q,'unit_price':pr,'discount':0,'discount_type':'fixed'} for p,q,pr in items],
        'customer_type':'saved_customer' if customer else 'walk_in','with_money_receipt':mr,'paid_amount':paid}
    if customer: body['customer_id']=str(cust.id)
    if paid: body['payment_method']='Cash'; body['account_id']=str(acc.id)
    r = c.post('/api/sales/', body, format='json')
    d = r.json()
    if r.status_code>=300: return r.status_code, d.get('message'), d.get('data')
    s = Sale.objects.get(id=d['data']['id'])
    return s

def check(name, before, s=None, exp_bal=None, exp_adv=D('0'), exp_tx=None, exp_paid=None, exp_due=None, exp_change=None):
    after = snap(); d = diff(before, after)
    extra = ''
    ok = True
    if s is not None and not isinstance(s, tuple):
        s.refresh_from_db()
        extra = f"| sale total={s.grand_total} paid={s.paid_amount} due={s.due_amount} change={s.change_amount} status={s.payment_status}"
        if exp_paid is not None and s.paid_amount != D(str(exp_paid)): ok=False
        if exp_due is not None and s.due_amount != D(str(exp_due)): ok=False
        if exp_change is not None and s.change_amount != D(str(exp_change)): ok=False
    elif isinstance(s, tuple):
        extra = f"| ERROR {s}"
    if exp_bal is not None and d['bal'] != D(str(exp_bal)): ok=False
    if d['adv'] != exp_adv: ok=False
    if exp_tx is not None and d['tx'] != exp_tx: ok=False
    print(('PASS ' if ok else 'FAIL ')+name, f"account +{d['bal']} (exp {exp_bal}) advance +{d['adv']} tx +{d['tx']} receipts +{d['mr']}", extra)
    return ok

res=[]
b=snap(); s=sale(36, 'Yes');                res.append(check('1. Full paid sale (receipt Yes)', b, s, exp_bal=36, exp_tx=1, exp_paid=36, exp_due=0))
b=snap(); s1=sale(10, 'No');                res.append(check('2. Partial paid sale (receipt No)', b, s1, exp_bal=10, exp_tx=1, exp_paid=10, exp_due=26))
b=snap(); s2=sale(50, 'Yes', customer=False); res.append(check('3. Walk-in pays 50 for 36 (change 14)', b, s2, exp_bal=36, exp_tx=1, exp_paid=36, exp_due=0, exp_change=14))
b=snap(); s3=sale(0, 'No');                 res.append(check('4. Full due sale', b, s3, exp_bal=0, exp_tx=0, exp_paid=0, exp_due=36))
# money receipt specific partial on s1 (due 26)
def mr(amount, ptype, sale_id=None):
    body={'amount':amount,'customer_id':str(cust.id),'payment_date':datetime.date.today().isoformat(),'payment_method':'Cash',
          'seller_id':str(u.id),'account':str(acc.id),'specific_invoice':ptype=='specific','payment_type':ptype}
    if sale_id: body['sale']=str(sale_id)
    r=c.post('/api/money-receipts/', body, format='json'); d=r.json()
    return (d['data']['id'] if r.status_code<300 else (r.status_code, d.get('message'), d.get('data')))
b=snap(); m=mr(6,'specific',s1.id);            res.append(check('5. Receipt 6 on invoice (due 26→20)', b, s1, exp_bal=6, exp_tx=1, exp_paid=16, exp_due=20))
b=snap(); m2=mr(30,'specific',s1.id);          res.append(check('6. Receipt 30 on invoice due 20 (10 → advance)', b, s1, exp_bal=30, exp_adv=D('10'), exp_tx=1, exp_paid=36, exp_due=0))
b=snap(); m3=mr(40,'overall');                 res.append(check('7. Overall 40 (s3 due 36 → paid, 4 advance)', b, s3, exp_bal=40, exp_adv=D('4'), exp_tx=1, exp_paid=36, exp_due=0))
# add_payment endpoint
s4=sale(0,'No')
b=snap(); r=c.post(f'/api/sales/{s4.id}/add_payment/', {'amount':16,'payment_method':'Cash','account_id':acc.id}, format='json')
res.append(check('8. add_payment 16 on due 36', b, s4, exp_bal=16, exp_tx=1, exp_paid=16, exp_due=20))
# delete receipt reverses
if isinstance(m, int):
    b=snap(); r=c.delete(f'/api/money-receipts/{m}/') 
    res.append(check(f'9. Delete receipt of 6 (status {r.status_code})', b, s1, exp_bal=-6, exp_tx=1, exp_paid=30, exp_due=6))
print(f"\n{sum(res)}/{len(res)} passed")
from products.models import Product
print('--- edge cases ---')
p=Product.objects.get(id=1); st=p.stock_qty
b=snap(); r=sale(20,'Yes',customer=False); print('PASS' if isinstance(r,tuple) and r[0]==400 else 'FAIL', '10. Walk-in partial payment rejected', r if isinstance(r,tuple) else r.id, diff(b,snap())['bal'])
p.refresh_from_db(); print('PASS' if p.stock_qty==st else 'FAIL', '11. Rejected sale did not reduce stock', st, p.stock_qty)
s5=sale(36,'Yes',customer=False)
b=snap(); body={'amount':5,'payment_date':datetime.date.today().isoformat(),'payment_method':'Cash','account':str(acc.id),'payment_type':'specific','sale':str(s5.id)}
r=c.post('/api/money-receipts/', body, format='json'); print('PASS' if r.status_code==400 else 'FAIL','12. Extra payment on fully-paid walk-in invoice rejected', r.status_code, r.json().get('data'))
mid=mr(5,'specific',s3.id) if False else mr(5,'advance') 
r=c.put(f'/api/money-receipts/{m2}/', {'amount':99}, format='json'); print('PASS' if r.status_code==400 else 'FAIL','13. Editing receipt amount blocked', r.status_code)
r=c.put(f'/api/money-receipts/{m2}/', {'remark':'fixed note'}, format='json'); print('PASS' if r.status_code==200 else 'FAIL','14. Editing remark allowed', r.status_code)
body={'type':'normal_sale','sale_date':datetime.date.today().isoformat(),'items':[{'product_id':1,'quantity':1,'unit_price':12,'discount':0,'discount_type':'fixed'}],
      'customer_type':'saved_customer','customer_id':str(cust.id),'paid_amount':5,'with_money_receipt':'No'}
r=c.post('/api/sales/', body, format='json'); print('PASS' if r.status_code==400 else 'FAIL','15. Paid without payment method rejected', r.status_code, r.json().get('message'))
p.refresh_from_db(); st=p.stock_qty; s6=sale(0,'No',items=((1,3,12.0),)); p.refresh_from_db(); print('PASS' if st-p.stock_qty==3 else 'FAIL','16. Stock reduced exactly once', st, p.stock_qty)
