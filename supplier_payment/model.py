# supplier_payment/models.py
from django.db import models, transaction
from django.core.exceptions import ValidationError
from suppliers.models import Supplier
from purchases.models import Purchase
from accounts.models import Account
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class SupplierPayment(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Cash'
        BANK = 'bank', 'Bank Transfer'
        CHEQUE = 'cheque', 'Cheque'
        MOBILE = 'mobile', 'Mobile Banking'
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
    
    class PaymentType(models.TextChoices):
        SPECIFIC = 'specific', 'Specific Bill Payment'
        OVERALL = 'overall', 'Overall Payment'
        ADVANCE = 'advance', 'Advance Payment'

    # Basic information
    supplier = models.ForeignKey('suppliers.Supplier', on_delete=models.CASCADE)
    
    # Payment identification
    sp_no = models.CharField(max_length=20, unique=True, blank=True, null=True)
    
    # Payment type and details
    payment_type = models.CharField(
        max_length=20, 
        choices=PaymentType.choices, 
        default=PaymentType.OVERALL
    )
    purchase = models.ForeignKey(
        'purchases.Purchase', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='supplier_payments'
    )
    
    # Payment details
    payment_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    payment_method = models.CharField(
        max_length=20, 
        choices=PaymentMethod.choices, 
        default=PaymentMethod.CASH
    )
    
    # Account information
    account = models.ForeignKey(
        'accounts.Account',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_payments'
    )
    
    # Advance payment handling
    use_advance = models.BooleanField(default=False)
    advance_amount_used = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    
    # Reference and description
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    # টাকাটা কোথায় বসেছে — বাতিল করলে ঠিক এটাই উল্টে দেওয়া হয়
    # {"purchases": {"<purchase_id>": "amount"}, "advance_used": "x", "advance_added": "y"}
    allocation = models.JSONField(default=dict, blank=True)
    
    # Status - CHANGE DEFAULT TO COMPLETED FOR TESTING
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.COMPLETED  # CHANGED from 'pending' to 'completed'
    )
    
    # Metadata
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='supplier_payments_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Supplier Payment'
        verbose_name_plural = 'Supplier Payments'
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['payment_date']),
            models.Index(fields=['supplier', 'payment_date']),
            models.Index(fields=['sp_no']),
        ]

    def __str__(self):
        return f"{self.sp_no} - {self.supplier.name} - ৳{self.amount}"

    def clean(self):
        """Validate payment data"""
        errors = {}
        
        # Validate payment type consistency
        if self.payment_type == 'specific' and not self.purchase:
            errors['purchase'] = 'Purchase must be selected for specific bill payments'
        
        if self.payment_type == 'advance' and self.purchase:
            errors['purchase'] = 'Purchase should not be selected for advance payments'
        
        # Validate amount
        if self.amount <= 0:
            errors['amount'] = 'Payment amount must be greater than 0'
        
        # Validate advance usage
        if self.use_advance:
            if self.advance_amount_used <= 0:
                errors['advance_amount_used'] = 'Advance amount used must be greater than 0'
            
            if self.advance_amount_used > self.supplier.advance_balance:
                errors['advance_amount_used'] = f'Advance amount used ({self.advance_amount_used}) exceeds available advance balance ({self.supplier.advance_balance})'
            
            if self.advance_amount_used > self.amount:
                errors['advance_amount_used'] = 'Advance amount used cannot be greater than total payment amount'
        
        # Validate account for cash payments
        cash_amount = self.amount
        if self.use_advance:
            cash_amount = self.amount - self.advance_amount_used
        
        if cash_amount > 0 and not self.account:
            errors['account'] = 'Account is required for cash payments'
        
        # Validate account balance for cash portion
        if cash_amount > 0 and self.account:
            # Refresh account to get current balance
            current_account = Account.objects.get(id=self.account.id)
            if cash_amount > current_account.balance:
                errors['amount'] = f'Insufficient balance in account {current_account.name}. Available: {current_account.balance}, Required: {cash_amount}'
        
        if errors:
            raise ValidationError(errors)

    def generate_sp_no(self):
        """Generate unique supplier payment number"""
        try:
            last_payment = SupplierPayment.objects.order_by('-id').first()
            
            if last_payment and last_payment.sp_no:
                try:
                    # Extract number from "SP-1001" format
                    last_number = int(last_payment.sp_no.split('-')[1])
                    new_number = last_number + 1
                except (ValueError, IndexError):
                    # If parsing fails, count existing payments
                    existing_count = SupplierPayment.objects.count()
                    new_number = 1001 + existing_count
            else:
                # First payment
                existing_count = SupplierPayment.objects.count()
                new_number = 1001 + existing_count
                
            sp_no = f"SP-{new_number}"
            
            # Ensure uniqueness
            counter = 1
            while SupplierPayment.objects.filter(sp_no=sp_no).exists():
                sp_no = f"SP-{new_number + counter}"
                counter += 1
                if counter > 100:
                    # Fallback with timestamp
                    timestamp = int(timezone.now().timestamp())
                    sp_no = f"SP-{timestamp}"
                    break
                    
            return sp_no
            
        except Exception as e:
            logger.error(f"Error generating SP number: {e}")
            timestamp = int(timezone.now().timestamp())
            return f"SP-{timestamp}"

    def save(self, *args, **kwargs):
        """
        নতুন payment save — সব ধাপ একসাথে (atomic): হয় সব হবে, নয়তো কিছুই না।

        FIX (গুরুতর): আগে _process_* method গুলো হাতে হাতে account.balance কমাত, তারপর আবার একটা
        debit Transaction তৈরি হত — Transaction নিজেও balance কমায়। ফলে supplier কে ৳1,000 দিলে
        account থেকে ৳2,000 কাটত। এখন account শুধু Transaction দিয়েই বদলায় (একবার)।
        আর Transaction ব্যর্থ হলে (যেমন যথেষ্ট টাকা নেই) পুরো payment বাতিল হয়, চুপচাপ থেকে যায় না।
        """
        is_new = self.pk is None

        if is_new and not self.sp_no:
            self.sp_no = self.generate_sp_no()

        # Auto-set payment type based on purchase
        if self.purchase:
            self.payment_type = 'specific'
        elif self.payment_type != 'advance':
            self.payment_type = 'overall'

        self.clean()

        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new and self.status == 'completed':
                self._process_payment()
                self._create_transaction()
                super().save(update_fields=['allocation', 'updated_at'])

    def _process_payment(self):
        """Payment type অনুযায়ী টাকা বসানো (account ছাড়া — সেটা Transaction করে)। সমস্যা হলে exception → rollback।"""
        logger.info(f"Processing supplier payment: {self.sp_no}, Type: {self.payment_type}, Amount: {self.amount}")
        if self.payment_type == 'advance':
            self.allocation = self._process_advance_payment()
        elif self.payment_type == 'specific':
            self.allocation = self._process_specific_payment()
        else:
            self.allocation = self._process_overall_payment()

    def _cash_portion(self):
        return self.amount - (self.advance_amount_used if self.use_advance else Decimal('0.00'))

    def _create_transaction(self):
        """নগদ অংশের জন্য একটা debit Transaction — এটাই account থেকে টাকা কাটে। ব্যর্থ হলে exception।"""
        from transactions.models import Transaction
        cash_amount = self._cash_portion()
        if cash_amount <= 0:
            return None
        if not self.account:
            raise ValidationError({"account": "Account is required for cash payments"})
        existing = self.transactions.filter(status='completed').first()
        if existing:
            return existing
        # create_for_supplier_payment error চাপা দেয়; তাই সরাসরি তৈরি করি যাতে কারণ উপরে যায়
        txn = Transaction.objects.create(
            transaction_type='debit',
            amount=cash_amount,
            account=self.account,
            payment_method=Transaction.normalize_payment_method(self.payment_method),
            reference_no=self.reference_no or self.sp_no,
            description=Transaction._generate_supplier_payment_description(self),
            supplier_payment=self,
            created_by=self.created_by,
            status='completed',
            transaction_date=timezone.now(),
            is_opening_balance=False,
        )
        logger.info(f"Debit transaction {txn.transaction_no} created for supplier payment {self.sp_no}")
        return txn

    def _locked_supplier(self):
        return Supplier.objects.select_for_update().get(pk=self.supplier_id)

    def _apply_to_purchase(self, purchase, amount, with_cash):
        purchase.paid_amount += amount
        purchase.due_amount = max(Decimal('0.00'), purchase.grand_total - purchase.paid_amount)
        purchase._update_payment_status()
        fields = ['paid_amount', 'due_amount', 'payment_status', 'change_amount', 'date_updated']
        if with_cash:
            purchase.payment_method = self.payment_method
            purchase.account = self.account
            fields += ['payment_method', 'account']
        purchase.save(update_fields=fields)

    def _process_advance_payment(self):
        """Supplier কে অগ্রিম — শুধু supplier এর advance বাড়ে"""
        supplier = self._locked_supplier()
        supplier.advance_balance += self.amount
        supplier.save(update_fields=['advance_balance', 'updated_at'])
        return {"purchases": {}, "advance_used": "0", "advance_added": str(self.amount)}

    def _process_specific_payment(self):
        """একটা নির্দিষ্ট purchase এর বাকি শোধ (advance + নগদ)"""
        if not self.purchase_id:
            raise ValidationError({"purchase": "Purchase is required for specific payments"})
        purchase = Purchase.objects.select_for_update().get(pk=self.purchase_id)
        if purchase.payment_status == 'cancelled':
            raise ValidationError({"purchase": f"{purchase.invoice_no} is cancelled."})
        advance_used = self.advance_amount_used if self.use_advance else Decimal('0.00')
        cash_amount = self.amount - advance_used
        if self.amount > purchase.due_amount:
            raise ValidationError({
                "amount": f"Payment amount ({self.amount}) exceeds purchase due amount ({purchase.due_amount})"})
        if advance_used > 0:
            supplier = self._locked_supplier()
            if advance_used > supplier.advance_balance:
                raise ValidationError({"advance_amount_used": f"Advance balance insufficient: {supplier.advance_balance}"})
            supplier.advance_balance -= advance_used
            supplier.save(update_fields=['advance_balance', 'updated_at'])
        self._apply_to_purchase(purchase, self.amount, with_cash=cash_amount > 0)
        return {"purchases": {str(purchase.pk): str(self.amount)}, "advance_used": str(advance_used), "advance_added": "0"}

    def _process_overall_payment(self):
        """পুরনো বাকি invoice থেকে শুরু করে শোধ; যা বাকি থাকে তা supplier এর advance"""
        advance_used = self.advance_amount_used if self.use_advance else Decimal('0.00')
        if advance_used > 0:
            supplier = self._locked_supplier()
            if advance_used > supplier.advance_balance:
                raise ValidationError({"advance_amount_used": f"Advance balance insufficient: {supplier.advance_balance}"})
        cash_amount = self.amount - advance_used
        remaining_adv, remaining_cash = advance_used, cash_amount
        applied = {}
        due_purchases = (Purchase.objects.select_for_update()
                         .filter(supplier_id=self.supplier_id, due_amount__gt=0)
                         .exclude(payment_status='cancelled').order_by('purchase_date', 'id'))
        adv_spent = Decimal('0.00')
        for purchase in due_purchases:
            if remaining_adv + remaining_cash <= 0:
                break
            due = purchase.due_amount
            from_adv = min(remaining_adv, due)
            from_cash = min(remaining_cash, due - from_adv)
            take = from_adv + from_cash
            if take <= 0:
                continue
            self._apply_to_purchase(purchase, take, with_cash=from_cash > 0)
            applied[str(purchase.pk)] = str(take)
            remaining_adv -= from_adv
            remaining_cash -= from_cash
            adv_spent += from_adv
        # যা বেঁচে গেল: ব্যবহার না হওয়া advance supplier এর কাছেই থাকে; বাড়তি নগদ নতুন advance
        advance_added = remaining_cash
        supplier = self._locked_supplier()
        supplier.advance_balance = supplier.advance_balance - adv_spent + advance_added
        supplier.save(update_fields=['advance_balance', 'updated_at'])
        if adv_spent != advance_used:
            # বাকির চেয়ে বেশি advance ধরা হলে, না-লাগা অংশ supplier এর advance এই থেকে যায় —
            # তাই সেটুকু এই payment এর অংশ নয়: amount থেকে বাদ, যাতে account থেকে ঠিক নগদ অংশই কাটে
            unused = advance_used - adv_spent
            self.amount -= unused
            if self.amount <= 0:
                raise ValidationError({"amount": "Nothing is due to this supplier, so the advance was not used."})
            self.advance_amount_used = adv_spent
            self.use_advance = adv_spent > 0
            super().save(update_fields=['amount', 'advance_amount_used', 'use_advance', 'updated_at'])
        return {"purchases": applied, "advance_used": str(adv_spent), "advance_added": str(advance_added)}

    def get_payment_summary(self):
        """Get comprehensive payment summary"""
        # Get the first transaction linked to this payment
        transaction = self.transactions.first() if hasattr(self, 'transactions') and self.transactions.exists() else None
        
        summary = {
            'payment_id': self.id,
            'sp_no': self.sp_no,
            'supplier': self.supplier.name,
            'payment_type': self.payment_type,
            'total_amount': float(self.amount),
            'advance_used': float(self.advance_amount_used),
            'cash_amount': float(self.amount - self.advance_amount_used),
            'payment_method': self.payment_method,
            'payment_date': self.payment_date.isoformat(),
            'status': self.status,
            'account': self.account.name if self.account else None,
            'transaction_no': transaction.transaction_no if transaction else None,
        }
        
        if self.payment_type == 'specific' and self.purchase:
            summary.update({
                'invoice_no': self.purchase.invoice_no,
                'invoice_total': float(self.purchase.grand_total),
            })
        
        return summary

    # ... rest of your methods ...

    def _recorded_allocation(self):
        if self.allocation:
            return self.allocation
        # পুরনো payment (রেকর্ড নেই) — যেটুকু নিশ্চিত জানা যায়
        used = self.advance_amount_used if self.use_advance else Decimal('0.00')
        if self.payment_type == 'specific' and self.purchase_id:
            return {"purchases": {str(self.purchase_id): str(self.amount)}, "advance_used": str(used), "advance_added": "0"}
        if self.payment_type == 'advance':
            return {"purchases": {}, "advance_used": "0", "advance_added": str(self.amount)}
        raise ValidationError(
            "This older payment has no record of which invoices it paid, so it cannot be reversed safely.")

    def cancel_payment(self, reason=None):
        """
        Payment বাতিল — যা যা বদলেছিল সব উল্টে দেয়: invoice এর পরিশোধ, supplier এর advance,
        আর account এর টাকা (উল্টো Transaction দিয়ে)। Record মুছে যায় না, "cancelled" হয়ে থাকে।
        FIX: আগের version এ _reverse_specific/_reverse_overall method ই ছিল না, আর self.transaction
        নামে কোনো field নেই — বাতিল করতে গেলেই error হত।
        """
        if self.status != 'completed':
            raise ValidationError("Only completed payments can be cancelled")
        alloc = self._recorded_allocation()
        with transaction.atomic():
            for pid, amt in (alloc.get('purchases') or {}).items():
                purchase = Purchase.objects.select_for_update().filter(pk=int(pid)).first()
                if not purchase:
                    continue
                if purchase.payment_status == 'cancelled':
                    raise ValidationError(
                        f"{purchase.invoice_no} was cancelled and its payments were already returned to the account.")
                purchase.paid_amount = max(Decimal('0.00'), purchase.paid_amount - Decimal(str(amt)))
                purchase.due_amount = max(Decimal('0.00'), purchase.grand_total - purchase.paid_amount)
                purchase._update_payment_status()
                purchase.save(update_fields=['paid_amount', 'due_amount', 'payment_status', 'change_amount', 'date_updated'])

            added = Decimal(str(alloc.get('advance_added') or '0'))
            used = Decimal(str(alloc.get('advance_used') or '0'))
            if added or used:
                supplier = self._locked_supplier()
                if supplier.advance_balance < added:
                    raise ValidationError(
                        f"The supplier's advance ({supplier.advance_balance}) has already been used, "
                        f"so this payment ({added} advance) cannot be cancelled.")
                supplier.advance_balance = supplier.advance_balance - added + used
                supplier.save(update_fields=['advance_balance', 'updated_at'])

            for txn in self.transactions.filter(status='completed', transaction_type='debit'):
                txn.reverse()

            self.status = 'cancelled'
            if reason:
                self.description = f"{(self.description or '').strip()}\nCancelled: {reason}".strip()
            super().save(update_fields=['status', 'description', 'updated_at'])
            # supplier এর মোট হিসাব আবার মেলাই
            self.supplier.update_purchase_totals()
        logger.info(f"Payment {self.sp_no} cancelled successfully")
        return True

    @classmethod
    def get_supplier_payment_summary(cls, supplier):
        """Get payment summary for a supplier"""
        payments = cls.objects.filter(supplier=supplier, status='completed')
        
        total_payments = payments.aggregate(
            total_amount=models.Sum('amount'),
            total_advance_used=models.Sum('advance_amount_used')
        )
        
        return {
            'total_payments': float(total_payments['total_amount'] or 0),
            'total_advance_used': float(total_payments['total_advance_used'] or 0),
            'total_cash_payments': float((total_payments['total_amount'] or 0) - (total_payments['total_advance_used'] or 0)),
            'payment_count': payments.count(),
            'current_advance_balance': float(supplier.advance_balance)
        }