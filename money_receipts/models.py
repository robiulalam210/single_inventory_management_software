from django.db import models, transaction as db_transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from customers.models import Customer
from accounts.models import Account
from django.contrib.auth import get_user_model
import logging
import random
import string
# models.py - Add this at the top
from decimal import Decimal  # Make sure this is imported
logger = logging.getLogger(__name__)
User = get_user_model()

class MoneyReceipt(models.Model):
    PAYMENT_TYPE_CHOICES = [
        ('overall', 'Overall Payment'),
        ('specific', 'Specific Invoice Payment'),
        ('advance', 'Advance Payment'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    mr_no = models.CharField(max_length=20, blank=True, unique=True)  # Added unique constraint
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True)
    sale = models.ForeignKey('sales.Sale', on_delete=models.SET_NULL, null=True, blank=True)
    sale_invoice_no = models.CharField(max_length=50, blank=True, null=True)  # ADDED THIS FIELD

    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, default='overall')
    specific_invoice = models.BooleanField(default=False)
    is_advance_payment = models.BooleanField(default=False)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='completed')

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=100, default='cash')
    payment_date = models.DateTimeField(default=timezone.now)
    remark = models.TextField(null=True, blank=True)
    seller = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='money_receipts_sold')
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    cheque_status = models.CharField(max_length=20, null=True, blank=True)
    cheque_id = models.CharField(max_length=64, null=True, blank=True)

    transaction = models.OneToOneField(
        'transactions.Transaction', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='linked_money_receipt'
    )

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='money_receipts_created')
    # টাকাটা কোথায় বসেছে: {"sales": {"<sale_id>": "amount"}, "advance": "amount"}
    # Receipt বাতিল করলে ঠিক এই হিসাব উল্টে দেওয়া হয় — তাই কোনো গরমিল থাকে না।
    allocation = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment_date']),
            models.Index(fields=['customer', 'payment_date']),
            models.Index(fields=['mr_no']),
            models.Index(fields=['is_advance_payment']),
        ]

    def __str__(self):
        customer_name = self.customer.name if self.customer else 'N/A'
        return f"{self.mr_no} - {customer_name} - {self.amount}"

    def clean(self):
        """Model validation"""
        if self.amount <= 0:
            raise ValidationError("Amount must be greater than 0")
        
        if self.is_advance_payment and not self.customer:
            raise ValidationError("Customer is required for advance payments")
        
        if self.payment_type == 'specific' and not self.sale:
            raise ValidationError("Specific invoice payment must have a sale reference")
        
        if self.payment_type == 'overall' and not self.customer:
            raise ValidationError("Overall payment must have a customer reference")


    def save(self, *args, **kwargs):
        """Safe save method"""
        # Check if we're already saving to prevent recursion
        if hasattr(self, '_currently_saving') and self._currently_saving:
            return super().save(*args, **kwargs)
        
        self._currently_saving = True
        
        try:
            is_new = self.pk is None

            # Generate MR number if new
            if is_new and not self.mr_no:
                self.mr_no = self._generate_mr_no()

            # Set payment type based on conditions
            if self.is_advance_payment:
                self.payment_type = 'advance'
                self.specific_invoice = False
            elif self.sale:
                self.payment_type = 'specific'
                self.specific_invoice = True
                # Set sale_invoice_no from sale
                if self.sale and not self.sale_invoice_no:
                    self.sale_invoice_no = self.sale.invoice_no
                # Ensure customer is set from sale
                if not self.customer and self.sale.customer:
                    self.customer = self.sale.customer
            else:
                self.payment_type = 'overall'
                self.specific_invoice = False

            # Validate before saving
            self.clean()

            # FIX: আগে প্রতিটা save এ (edit করলেও) payment আবার process হত, আর কোনো ধাপ
            # ব্যর্থ হলে error চাপা পড়ে receipt থেকে যেত কিন্তু sale/account আপডেট হত না।
            # এখন: শুধু নতুন receipt এ, সব ধাপ একসাথে (atomic) — হয় সব হবে, নয়তো কিছুই না।
            with db_transaction.atomic():
                super().save(*args, **kwargs)
                if is_new and self.payment_status == 'completed':
                    self.process_payment()
                    self.create_transaction()

        finally:
            # Clean up the flag
            if hasattr(self, '_currently_saving'):
                delattr(self, '_currently_saving')
            if hasattr(self, '_payment_already_processed'):
                delattr(self, '_payment_already_processed')

    def _generate_mr_no(self):
        """Sequential MR number: MR-000001"""
        try:
            last_receipt = MoneyReceipt.objects.filter(
                mr_no__regex=r'^MR-\d+$'
            ).order_by('-id').first()
            new_number = 1
            if last_receipt:
                try:
                    new_number = int(last_receipt.mr_no.split('-')[1]) + 1
                except (ValueError, IndexError):
                    new_number = MoneyReceipt.objects.count() + 1
            mr_no = f"MR-{new_number:06d}"
            while MoneyReceipt.objects.filter(mr_no=mr_no).exists():
                new_number += 1
                mr_no = f"MR-{new_number:06d}"
            return mr_no
        except Exception as e:
            logger.error(f"Error generating mr_no: {e}")
            timestamp = int(timezone.now().timestamp())
            random_suffix = ''.join(random.choices(string.digits, k=4))
            return f"MR-{timestamp}-{random_suffix}"

    def process_payment(self):
        """Payment type অনুযায়ী টাকা বসানো। কোনো সমস্যা হলে exception → পুরো receipt rollback।"""
        logger.info(f"Processing payment for {self.mr_no} - Type: {self.payment_type}, Amount: {self.amount}")
        if self.is_advance_payment:
            allocation = self._process_advance_payment()
        elif self.payment_type == 'specific' and self.sale_id:
            allocation = self._process_specific_invoice_payment()
        else:
            allocation = self._process_overall_payment()
        self.allocation = allocation
        super().save(update_fields=['allocation'])
        return True

    def _add_advance(self, customer, amount):
        if amount <= 0:
            return
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        customer.advance_balance = (customer.advance_balance or Decimal('0.00')) + amount
        customer.save(update_fields=['advance_balance'])

    def _apply_to_sale(self, sale, amount):
        """Sale এর paid বাড়ানো; due/status Sale.calculate_totals() নিজেই ঠিক করে।"""
        sale.paid_amount = (sale.paid_amount or Decimal('0.00')) + amount
        sale.save(update_fields=['paid_amount', 'updated_at'])

    def _process_advance_payment(self):
        if not self.customer_id:
            raise ValidationError("Customer is required for advance payments")
        self._add_advance(self.customer, self.amount)
        return {"sales": {}, "advance": str(self.amount)}

    def _process_specific_invoice_payment(self):
        from sales.models import Sale
        sale = Sale.objects.select_for_update().get(pk=self.sale_id)
        sale.calculate_totals()
        applied = min(self.amount, max(sale.due_amount, Decimal('0.00')))
        advance = self.amount - applied
        customer = sale.customer or self.customer
        if advance > 0 and not customer:
            raise ValidationError(
                f"Amount {self.amount} is more than invoice due {sale.due_amount}. "
                f"Walk-in sale এ অতিরিক্ত টাকা নেওয়া যায় না।")
        if applied > 0:
            self._apply_to_sale(sale, applied)
        if advance > 0:
            self._add_advance(customer, advance)
            logger.info(f"Excess {advance} kept as advance for {customer.name}")
        return {"sales": {str(sale.pk): str(applied)} if applied > 0 else {}, "advance": str(advance)}

    def _process_overall_payment(self):
        """পুরনো due invoice থেকে শুরু করে পরিশোধ, বাকি থাকলে advance।"""
        from sales.models import Sale
        if not self.customer_id:
            raise ValidationError("Customer is required for overall payments")
        remaining = self.amount
        sales_alloc = {}
        due_sales = (Sale.objects.select_for_update()
                     .filter(customer_id=self.customer_id, due_amount__gt=0)
                     .order_by('sale_date', 'id'))
        for sale in due_sales:
            if remaining <= 0:
                break
            applied = min(remaining, sale.due_amount)
            self._apply_to_sale(sale, applied)
            sales_alloc[str(sale.pk)] = str(applied)
            remaining -= applied
        if remaining > 0:
            self._add_advance(self.customer, remaining)
        return {"sales": sales_alloc, "advance": str(remaining)}

    def create_transaction(self):
        """এই receipt এর টাকা account এ জমা (credit) — একবারই।"""
        if self.transaction_id:
            return self.transaction
        if not self.account_id:
            raise ValidationError("Account is required to receive payment")
        from transactions.models import Transaction
        txn = Transaction.create_for_money_receipt(self)
        if txn is None:
            raise ValidationError(f"Could not create account transaction for {self.mr_no}")
        self.transaction = txn
        super().save(update_fields=['transaction'])
        logger.info(f"Transaction created for money receipt {self.mr_no}: {txn.transaction_no}")
        return txn

    # ------------------------------------------------------------------
    # বাতিল (delete) — যা যা বদলেছিল সব উল্টে দেওয়া
    # ------------------------------------------------------------------
    def _legacy_allocation(self):
        if self.allocation:
            return self.allocation
        if self.is_advance_payment or self.payment_type == 'advance':
            return {"sales": {}, "advance": str(self.amount)}
        if self.payment_type == 'specific' and self.sale_id:
            return {"sales": {str(self.sale_id): str(self.amount)}, "advance": "0"}
        raise ValidationError(
            "এই পুরনো overall receipt কোন invoice এ কত বসেছিল তার রেকর্ড নেই, তাই নিরাপদে বাতিল করা যাচ্ছে না।")

    def reverse_and_delete(self):
        from sales.models import Sale
        with db_transaction.atomic():
            alloc = self._legacy_allocation()
            for sale_id, amt in (alloc.get("sales") or {}).items():
                sale = Sale.objects.select_for_update().filter(pk=int(sale_id)).first()
                if sale:
                    sale.paid_amount = max(Decimal('0.00'), (sale.paid_amount or Decimal('0.00')) - Decimal(amt))
                    sale.save(update_fields=['paid_amount', 'updated_at'])
            advance = Decimal(str(alloc.get("advance") or "0"))
            if advance > 0:
                customer = self.customer or (self.sale.customer if self.sale_id else None)
                if customer:
                    customer = Customer.objects.select_for_update().get(pk=customer.pk)
                    if customer.advance_balance < advance:
                        raise ValidationError(
                            f"Customer এর advance ({customer.advance_balance}) ইতিমধ্যে ব্যবহার হয়েছে — "
                            f"এই receipt ({advance} advance) বাতিল করা যাচ্ছে না।")
                    customer.advance_balance -= advance
                    customer.save(update_fields=['advance_balance'])
            if self.transaction_id and self.transaction.status == 'completed':
                self.transaction.reverse()
            super().delete()

    def delete(self, *args, **kwargs):
        return self.reverse_and_delete()

    def get_payment_summary(self):
        """Get payment summary"""
        summary = {
            'mr_no': self.mr_no,
            'payment_type': self.payment_type,
            'amount': float(self.amount),
            'payment_method': self.payment_method,
            'payment_date': self.payment_date.isoformat(),
            'status': self.payment_status,
            'is_advance_payment': self.is_advance_payment,
        }

        if self.is_advance_payment:
            summary.update({
                'customer': self.customer.name if self.customer else 'Unknown',
                'type': 'advance_payment',
                'new_balance': float(self.customer.advance_balance) if self.customer else 0
            })
        elif self.payment_type == 'specific' and self.sale:
            try:
                # Get fresh sale data
                from sales.models import Sale
                sale = Sale.objects.get(id=self.sale.id)
                
                # Calculate before payment values
                previous_paid = float(sale.paid_amount - self.amount)
                previous_due = float(sale.due_amount + self.amount)

                summary.update({
                    'invoice_no': sale.invoice_no,
                    'before_payment': {
                        'invoice_total': float(sale.grand_total),
                        'previous_paid': previous_paid,
                        'previous_due': previous_due,
                    },
                    'after_payment': {
                        'current_paid': float(sale.paid_amount),
                        'current_due': float(sale.due_amount),
                        'payment_applied': float(self.amount),
                    },
                    'invoice_status': 'paid' if sale.due_amount == 0 else 'partial'
                })
            except Exception as e:
                logger.error(f"Error getting payment summary for sale: {e}")
        
        return summary

    def get_customer_display(self):
        """Get customer display name"""
        if self.customer:
            return self.customer.name
        elif self.sale and self.sale.customer:
            return self.sale.customer.name
        elif self.sale:
            # walk-in বিক্রি — "Unknown Customer" এর বদলে বোধগম্য নাম
            return self.sale.customer_name or "Walk-in customer"
        return "Walk-in customer"

    @property
    def is_specific_payment(self):
        return self.payment_type == 'specific'

    @property
    def is_overall_payment(self):
        return self.payment_type == 'overall'

    @classmethod
    def create_auto_receipt(cls, sale, created_by=None):
        """Create money receipt automatically for sale - FIXED VERSION"""
        if sale.paid_amount <= 0:
            return None
        
        # Check if auto receipt already exists for this sale
        existing = cls.objects.filter(sale=sale, payment_type='specific').first()
        if existing:
            logger.info(f"Auto receipt already exists for sale {sale.invoice_no}: {existing.mr_no}")
            return existing

        try:
            receipt = cls(
                customer=sale.customer,
                sale=sale,
                sale_invoice_no=sale.invoice_no,
                payment_type='specific',
                specific_invoice=True,
                amount=sale.paid_amount,
                payment_method=sale.payment_method or 'Cash',
                payment_date=timezone.now(),
                remark=f"Auto receipt for {sale.invoice_no}",
                seller=sale.sale_by,
                account=sale.account,
                created_by=created_by or sale.created_by,
                payment_status='completed'
            )

            # Mark as auto-created to prevent recursion
            receipt._skip_payment_processing = True
            receipt.save()
            return receipt
            
        except Exception as e:
            logger.error(f"Error creating auto receipt for sale {sale.invoice_no}: {e}")
            return None

    @classmethod
    def create_advance_receipt(cls, customer, amount, payment_method, account, created_by=None, seller=None):
        """Create advance payment receipt"""
        try:
            receipt = cls(
                customer=customer,
                sale=None,
                sale_invoice_no=None,
                payment_type='advance',
                specific_invoice=False,
                is_advance_payment=True,
                amount=amount,
                payment_method=payment_method,
                payment_date=timezone.now(),
                remark="Advance payment received",
                seller=seller,
                account=account,
                created_by=created_by,
                payment_status='completed'
            )

            receipt.save()
            return receipt
            
        except Exception as e:
            logger.error(f"Error creating advance receipt: {e}")
            return None