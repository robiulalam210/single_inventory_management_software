from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal

class Customer(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, unique=True, blank=True, null=True)
    address = models.TextField(blank=True, null=True, default="")
    
    # Advance payment tracking
    advance_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    special_customer = models.BooleanField(default=False)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    date_created = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    client_no = models.CharField(max_length=20, blank=True, null=True)

    def save(self, *args, **kwargs):
        """Custom save method to handle client number generation"""
        is_new = self.pk is None
        
        # Generate client number for new customers if not provided
        if is_new and not self.client_no:
            existing_count = Customer.objects.filter(
                client_no__isnull=False
            ).count()
            new_number = 1001 + existing_count
            self.client_no = f"CU-{new_number}"
        
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def status(self):
        return "Active" if self.is_active else "Inactive"
    
    @property
    def customer_type(self):
        """Return customer type based on special flag"""
        return "Special" if self.special_customer else "Regular"
    

    def add_advance_direct(self, amount, created_by=None):
        """Add advance payment directly to customer balance AND create money receipt"""
        if amount <= 0:
            raise ValidationError("Advance amount must be greater than 0")
        
        # Directly update advance balance
        self.advance_balance += Decimal(str(amount))
        self.save(update_fields=['advance_balance'])
        
        # Try to create a money receipt for this advance
        try:
            from money_receipts.models import MoneyReceipt
            
            # Generate receipt number
            last_receipt = MoneyReceipt.objects.filter(
            ).order_by('-id').first()
            
            receipt_no = f"ADV-{1000 + (last_receipt.id + 1 if last_receipt else 1)}"
            
            # Create the money receipt
            MoneyReceipt.objects.create(
                customer=self,
                receipt_no=receipt_no,
                amount=amount,
                payment_date=timezone.now(),
                payment_method='cash',
                payment_status='completed',
                is_advance_payment=True,
                created_by=created_by,
                notes=f"Advance payment of {amount}"
            )
        except Exception as e:
            # If money receipt creation fails, just log it
            print(f"Note: Could not create money receipt for advance: {e}")
            # The advance is still added to customer balance
        
        return self.advance_balance

    def use_advance_payment(self, amount, sale=None):
        """Use advance balance for a payment"""
        if amount > self.advance_balance:
            raise ValidationError(f"Insufficient advance balance. Available: {self.advance_balance}")
        
        self.advance_balance -= Decimal(str(amount))
        self.save(update_fields=['advance_balance'])
        
        return self.advance_balance

    def is_advance_receipt(self, receipt):
        """Determine if a money receipt should be treated as advance"""
        # Rule 1: Explicitly marked as advance
        if hasattr(receipt, 'is_advance_payment') and receipt.is_advance_payment:
            return True, 'explicit_advance'
        
        # Rule 2: Has advance_amount field
        if hasattr(receipt, 'advance_amount') and receipt.advance_amount:
            return True, 'advance_amount_field'
        
        # Rule 3: Payment type is 'advance'
        if hasattr(receipt, 'payment_type') and receipt.payment_type == 'advance':
            return True, 'payment_type_advance'
        
        # Rule 4: Overall payment (not linked to specific invoice)
        if (hasattr(receipt, 'payment_type') and 
            receipt.payment_type == 'overall' and
            (not hasattr(receipt, 'sale') or receipt.sale is None)):
            return True, 'overall_payment'
        
        # Rule 5: Any payment not linked to a specific sale
        if not hasattr(receipt, 'sale') or receipt.sale is None:
            return True, 'no_sale_linked'
        
        return False, 'not_advance'

    def expected_advance_from_receipts(self):
        """
        রসিদের রেকর্ড থেকে এই customer এর advance কত হওয়ার কথা।
          • নতুন রসিদ: save এর সময় লেখা allocation["advance"] — ঠিক যতটুকু advance এ গেছে
          • পুরনো রসিদ (allocation নেই): শুধু স্পষ্ট advance রসিদ পুরোটা; overall/specific এর ভাগ জানা নেই
        ফেরত: (মোট, তালিকা, সব_রসিদের_হিসাব_জানা_কিনা)
        """
        from money_receipts.models import MoneyReceipt
        total = Decimal('0.00')
        rows = []
        complete = True
        for r in MoneyReceipt.objects.filter(customer=self).order_by('payment_date', 'id'):
            alloc = r.allocation or {}
            if alloc:
                adv = Decimal(str(alloc.get('advance') or '0'))
                kind = 'recorded'
            elif r.is_advance_payment or r.payment_type == 'advance':
                adv = r.amount or Decimal('0.00')
                kind = 'explicit_advance'
            else:
                adv = Decimal('0.00')
                kind = 'legacy_unknown'
                complete = False
            if adv > 0:
                rows.append({
                    'id': r.id,
                    'receipt_no': r.mr_no,
                    'amount': float(adv),
                    'date': r.payment_date,
                    'type': kind,
                    'payment_type': r.payment_type,
                    'is_advance_payment': r.is_advance_payment,
                    'sale_linked': r.sale_id is not None,
                    'sale_invoice_no': r.sale_invoice_no,
                })
            total += adv
        return total, rows, complete

    def sync_advance_balance(self):
        """
        FIX (গুরুতর): আগে এই method প্রতিটা "overall" রসিদের পুরো টাকাকে advance ধরে
        customer.advance_balance এ লিখে দিত — আর customer list/detail দেখলেই এটা চলত।
        ফলে ৳1,000 দিয়ে পুরনো due শোধ করলে customer list খোলামাত্র সে ৳1,000 advance ও পেয়ে যেত
        (একই টাকা দুইবার)। সাথে একটা debug কোড ব্যর্থ হলে ৳2,000 বসিয়ে দিত।

        এখন: stored advance_balance ই আসল হিসাব — MoneyReceipt একই transaction এ যোগ/বাতিল করে।
        এই method আর কিছু লেখে না; শুধু রসিদের রেকর্ডের সাথে মিলিয়ে breakdown দেয়
        (পুরনো serializer গুলো যে আকারে data চায় সেই আকারেই)।
        """
        from sales.models import Sale
        from django.db.models import Sum

        sales_total = Sale.objects.filter(customer=self).aggregate(
            total_grand=Sum('grand_total'), total_paid=Sum('paid_amount'))
        total_grand = float(sales_total['total_grand'] or 0)
        total_paid = float(sales_total['total_paid'] or 0)
        sales_overpayment = max(0.0, total_paid - total_grand)

        try:
            expected, rows, complete = self.expected_advance_from_receipts()
        except Exception:
            expected, rows, complete = Decimal('0.00'), [], False

        current = float(self.advance_balance or 0)
        return {
            'synced': False,
            'current_value': current,
            'is_correct': (not complete) or abs(current - float(expected)) <= 0.01,
            'breakdown': {
                'sales_overpayment': sales_overpayment,
                'advance_from_receipts': float(expected),
                'total_advance': current,
                'advance_receipts': rows,
                'records_complete': complete,
            }
        }

    def get_payment_summary(self):
        """Get comprehensive payment summary including advance"""
        from sales.models import Sale
        from django.db.models import Sum
        
        # Get all sales for this customer
        sales = Sale.objects.filter(customer=self)
        
        # Calculate totals
        total_sales = sales.count()
        total_grand_total = sales.aggregate(total=Sum('grand_total'))['total'] or 0
        total_paid = sales.aggregate(total=Sum('paid_amount'))['total'] or 0
        
        # Sync advance balance first
        sync_result = self.sync_advance_balance()
        stored_advance = float(self.advance_balance) if self.advance_balance else 0
        
        # Calculate overpayment from sales (when paid > grand_total)
        sales_overpayment = max(0, total_paid - total_grand_total)
        
        # Total advance = stored advance (already includes receipts + overpayment)
        total_advance = stored_advance
        
        # Calculate basic due (should be 0 if overpaid)
        basic_due = max(0, total_grand_total - total_paid)
        
        # Calculate net due after applying ALL advance
        net_due = max(0, basic_due - total_advance)
        
        # Calculate remaining advance after applying to due
        remaining_advance = max(0, total_advance - basic_due)
        
        # Determine amount type
        if remaining_advance > 0:
            amount_type = "Advance"
        elif net_due > 0:
            amount_type = "Due"
        else:
            amount_type = "Paid"
        
        return {
            'customer': self.name,
            'total_sales': total_sales,
            'total_grand_total': float(total_grand_total),
            'total_paid': float(total_paid),
            'sales_overpayment': float(sales_overpayment),
            'stored_advance_balance': float(stored_advance),
            'total_advance': float(total_advance),
            'basic_due': float(basic_due),
            'net_due': float(net_due),
            'remaining_advance': float(remaining_advance),
            'amount_type': amount_type,
            'sync_result': sync_result
        }

    def get_detailed_payment_breakdown(self):
        """Get detailed payment breakdown including advance, due, and paid with IDs"""
        from sales.models import Sale
        from django.db.models import Sum
        from decimal import Decimal
        
        # Sync advance balance first to ensure accuracy
        sync_result = self.sync_advance_balance()
        
        # Get all sales for this customer
        sales = Sale.objects.filter(customer=self)
        
        # Calculate sales totals - convert to float for consistency
        sales_total = sales.aggregate(
            total_grand=Sum('grand_total'),
            total_paid=Sum('paid_amount')
        )
        
        total_grand = float(sales_total['total_grand'] or 0)
        total_paid = float(sales_total['total_paid'] or 0)
        
        # Calculate overpayment from sales
        sales_overpayment = max(0.0, total_paid - total_grand)
        
        # Get stored advance balance - convert to float
        stored_advance = float(self.advance_balance) if self.advance_balance else 0.0
        
        # Get advance receipts from sync result
        advance_receipts = sync_result.get('breakdown', {}).get('advance_receipts', [])
        total_advance_from_receipts = float(sync_result.get('breakdown', {}).get('advance_from_receipts', 0))
        
        # Total advance should equal stored_advance (after sync)
        total_advance_available = stored_advance
        
        # Calculate basic due (before applying advance)
        basic_due = max(0.0, total_grand - total_paid)
        
        # Calculate net due after applying advance
        net_due = max(0.0, basic_due - total_advance_available)
        
        # Calculate remaining advance after applying to due
        remaining_advance = max(0.0, total_advance_available - basic_due)
        
        # Get individual sales with due amounts
        due_sales = []
        for sale in sales.filter(due_amount__gt=0):
            due_sales.append({
                'id': sale.id,
                'invoice_no': sale.invoice_no,
                'due_amount': float(sale.due_amount),
                'date': sale.sale_date
            })
        
        # Get individual sales with paid amounts
        paid_sales = []
        for sale in sales.filter(paid_amount__gt=0):
            paid_sales.append({
                'id': sale.id,
                'invoice_no': sale.invoice_no,
                'grand_total': float(sale.grand_total),
                'paid_amount': float(sale.paid_amount),
                'overpayment': float(max(Decimal('0'), sale.paid_amount - sale.grand_total)),
                'date': sale.sale_date
            })
        
        return {
            'customer_id': self.id,
            'customer_name': self.name,
            'summary': {
                'advance': {
                    'total': float(remaining_advance),
                    'breakdown': {
                        'from_sales_overpayment': float(sales_overpayment),
                        'from_advance_receipts': float(total_advance_from_receipts),
                        'stored_in_db': float(stored_advance),
                        'total_calculated': float(total_advance_available)
                    },
                    'count': len(advance_receipts)
                },
                'due': {
                    'total': float(net_due),
                    'count': len(due_sales)
                },
                'paid': {
                    'total': float(total_paid),
                    'count': len(paid_sales)
                }
            },
            'details': {
                'advance_receipts': advance_receipts,
                'due_sales': due_sales,
                'paid_sales': paid_sales
            },
            'calculation': {
                'sale_analysis': {
                    'total_sale_amount': float(total_grand),
                    'total_paid_to_sales': float(total_paid),
                    'sales_overpayment': float(sales_overpayment),
                    'sales_underpayment': float(max(0.0, total_grand - total_paid))
                },
                'advance_analysis': {
                    'advance_from_receipts': float(total_advance_from_receipts),
                    'advance_from_sales_overpayment': float(sales_overpayment),
                    'total_advance_available': float(total_advance_available),
                    'stored_advance_in_db': float(stored_advance)
                },
                'due_analysis': {
                    'basic_due_before_advance': float(basic_due),
                    'net_due_after_advance': float(net_due),
                    'remaining_advance_balance': float(remaining_advance)
                }
            },
            'sync_info': {
                'was_synced': sync_result.get('synced', False),
                'previous_value': float(sync_result.get('old_value', stored_advance))
            }
        }
    
    def get_advance_summary(self):
        """Get advance payment summary"""
        try:
            from money_receipts.models import MoneyReceipt
            from django.db.models import Sum
            
            advance_receipts = MoneyReceipt.objects.filter(
                customer=self,
                is_advance_payment=True,
                payment_status='completed'
            )
            
            total_advance = advance_receipts.aggregate(total=Sum('amount'))['total'] or 0
            
            return {
                'customer': self.name,
                'current_balance': float(self.advance_balance),
                'total_advance_received': float(total_advance),
                'advance_receipts_count': advance_receipts.count()
            }
        except:
            return {
                'customer': self.name,
                'current_balance': float(self.advance_balance),
                'total_advance_received': 0,
                'advance_receipts_count': 0
            }