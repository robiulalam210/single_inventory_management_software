from django.db import models, transaction as db_transaction
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from accounts.models import Account
import logging
import traceback

logger = logging.getLogger(__name__)

class ExpenseHead(models.Model):
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    date_created = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.name
    
    @property
    def status(self):
        return "Active" if self.is_active else "Inactive"

class ExpenseSubHead(models.Model):
    name = models.CharField(max_length=255)
    head = models.ForeignKey(ExpenseHead, related_name='subheads', on_delete=models.CASCADE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    date_created = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['head__name', 'name']
        indexes = [
            models.Index(fields=['head', 'is_active']),
        ]

    def __str__(self):
        return f"{self.head.name} - {self.name}" if self.head else self.name
    
    @property
    def status(self):
        return "Active" if self.is_active else "Inactive"

class Expense(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('mobile', 'Mobile Banking'),
        ('card', 'Card'),
        ('other', 'Other'),
    ]

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    date_created = models.DateTimeField(default=timezone.now)
    head = models.ForeignKey(ExpenseHead, on_delete=models.SET_NULL, null=True, blank=True)
    subhead = models.ForeignKey(ExpenseSubHead, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=100, choices=PAYMENT_METHOD_CHOICES, default='cash')
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, blank=True, null=True, related_name='expenses')
    expense_date = models.DateField(default=timezone.now)
    note = models.TextField(blank=True, null=True)
    invoice_number = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['-expense_date', '-date_created']
        indexes = [
            models.Index(fields=['expense_date']),
            models.Index(fields=['head', 'expense_date']),
            models.Index(fields=['invoice_number']),
            models.Index(fields=['account', 'expense_date']),
        ]

    def __str__(self):
        description = self.note[:50] + '...' if self.note and len(self.note) > 50 else (self.note or '')
        return f"{self.invoice_number} - {description} - {self.amount}"

    def clean(self):
        """Validate expense data"""
        if self.amount <= 0:
            raise ValidationError("Expense amount must be greater than 0")
        if self.account and self.amount is not None:
            available = self.account.balance
            # edit এর সময় একই account হলে আগের খরচের টাকা তো আগেই কাটা — সেটা ফেরত ধরে হিসাব করি।
            # (আগে শুধু note বদলাতে গেলেও "Insufficient balance" আসত)
            if self.pk:
                old = Expense.objects.filter(pk=self.pk).values('account_id', 'amount').first()
                if old and old['account_id'] == self.account_id and self.get_associated_transaction():
                    available += old['amount']
            if self.amount > available:
                raise ValidationError(f"Insufficient balance in {self.account.name}. Available: {available}")

    def save(self, *args, **kwargs):
        """Save expense with proper transaction handling for both creation and updates"""
        is_new = self.pk is None
        old_instance = None
        old_amount = None
        old_account = None

        if not is_new:
            try:
                old_instance = Expense.objects.get(pk=self.pk)
                old_amount = old_instance.amount
                old_account = old_instance.account
            except Expense.DoesNotExist:
                old_instance = None
        
        if is_new and not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        
        self.clean()
        super().save(*args, **kwargs)

        with db_transaction.atomic():
            if is_new:
                if self.account:
                    logger.info(f"Processing new expense {self.invoice_number}")
                    try:
                        transaction = self.create_expense_transaction()
                        if transaction:
                            logger.info(f"SUCCESS: Transaction created: {transaction.id}")
                            self.account.refresh_from_db()
                            logger.info(f" Account balance after transaction: {self.account.balance}")
                        else:
                            logger.error(f"ERROR: Transaction creation failed for expense {self.invoice_number}")
                    except Exception as e:
                        logger.error(f"ERROR: Error in transaction creation: {str(e)}")
                        logger.error(f"ERROR: Traceback: {traceback.format_exc()}")
                else:
                    logger.warning(f"No account specified for new expense {self.invoice_number}")
            else:
                logger.info(f" Processing expense update {self.invoice_number}")
                existing_transaction = self.get_associated_transaction()
                amount_changed = old_instance and self.amount != old_amount
                account_changed = old_instance and self.account != old_account
                if amount_changed or account_changed:
                    logger.info(f"  - Amount changed: {amount_changed} ({old_amount} → {self.amount})")
                    logger.info(f"  - Account changed: {account_changed} ({old_account} → {self.account})")
                    self._handle_expense_update(old_instance, existing_transaction)
                else:
                    logger.info(f" No significant changes to amount or account - transaction unchanged")

    def _handle_expense_update(self, old_instance, existing_transaction):
        """Handle updates to expense by modifying transactions"""
        try:
            from transactions.models import Transaction
            if old_instance and old_instance.account and existing_transaction:
                logger.info(f"Reversing old transaction {existing_transaction.transaction_no}")
                reversal = self._create_reversal_transaction(old_instance)
                if reversal:
                    logger.info(f"Reversal created: {reversal.transaction_no}")
                existing_transaction.status = 'cancelled'
                existing_transaction.save(update_fields=['status'])
                logger.info(f"Old transaction cancelled: {existing_transaction.transaction_no}")
            if self.account:
                logger.info(f"Creating new transaction for updated expense")
                new_transaction = self.create_expense_transaction()
                if new_transaction:
                    logger.info(f"New transaction created: {new_transaction.transaction_no}")
                    self.account.refresh_from_db()
                    logger.info(f"Updated account balance: {self.account.balance}")
                else:
                    logger.error(f"ERROR: Failed to create new transaction for updated expense")
            else:
                logger.info(f"No account specified - no new transaction created")
        except Exception as e:
            logger.error(f"ERROR: Error handling expense update: {str(e)}")
            logger.error(f"ERROR: Traceback: {traceback.format_exc()}")

    def _create_reversal_transaction(self, old_instance):
        """Create a reversal transaction for the old expense"""
        try:
            from transactions.models import Transaction
            reversal = Transaction.objects.create(
                transaction_type='credit',
                amount=old_instance.amount,
                account=old_instance.account,
                payment_method=old_instance.payment_method,
                description=f"Reversal - Previous expense: {old_instance.invoice_number}",
                created_by=old_instance.created_by,
                status='completed',
                transaction_date=timezone.now().date(),
                is_opening_balance=False
            )
            logger.info(f"Created reversal transaction: {reversal.transaction_no}")
            logger.info(f"Account {old_instance.account.name} balance increased by {old_instance.amount}")
            return reversal
        except Exception as e:
            logger.error(f"ERROR: Error creating reversal transaction: {e}")
            logger.error(f"ERROR: Traceback: {traceback.format_exc()}")
            return None

    def delete(self, *args, **kwargs):
        """
        খরচ মুছলে টাকা account এ ফেরত যায় — একবারই।
        আগে হাতে balance বাড়ানো + credit Transaction (যেটা নিজেও balance বাড়ায়) দুটোই হতো, তাই দ্বিগুণ ফেরত আসত।
        এখন: মূল debit transaction বাতিল + একটা reversal credit (statement এ দুটোই দেখা যায়)।
        """
        from transactions.models import Transaction
        with db_transaction.atomic():
            original = self.get_associated_transaction()
            if original:
                Transaction.objects.create(
                    transaction_type='credit',
                    amount=original.amount,
                    account=original.account,
                    payment_method=self.payment_method,
                    description=f"Reversal of deleted expense: {self.invoice_number}",
                    reference_no=self.invoice_number,
                    status='completed',
                    transaction_date=timezone.localdate(),
                    created_by=self.created_by,
                )
                original.status = 'cancelled'
                original.save(update_fields=['status'])
            super().delete(*args, **kwargs)

    def generate_invoice_number(self):
        """Generate unique invoice number"""
        try:
            from django.db.models import Max
            from django.db.models.functions import Cast, Substr
            max_expense = Expense.objects.filter(
                invoice_number__regex=r'^EXP-\d+$'
            ).aggregate(
                max_number=Max(
                    Cast(
                        Substr('invoice_number', 5),
                        output_field=models.IntegerField()
                    )
                )
            )
            next_number = (max_expense['max_number'] or 1000) + 1
            invoice_number = f"EXP-{next_number}"
            counter = 0
            while Expense.objects.filter(invoice_number=invoice_number).exists():
                counter += 1
                invoice_number = f"EXP-{next_number + counter}"
            return invoice_number
        except Exception as e:
            logger.error(f"Error generating invoice number: {str(e)}")
            return f"EXP-{int(timezone.now().timestamp() * 1000)}"

    def create_expense_transaction(self):
        """Create DEBIT transaction record for this expense"""
        if not self.account:
            logger.warning(f"No account specified for expense {self.invoice_number}")
            return None
        try:
            from transactions.models import Transaction
            description_parts = [f"Expense: {self.head.name if self.head else 'No Head'}"]
            if self.subhead:
                description_parts.append(f" - {self.subhead.name}")
            if self.note:
                description_parts.append(f" - {self.note}")
            description = ''.join(description_parts)
            logger.info(f"🔍 Creating transaction for expense {self.invoice_number}")
            logger.info(f"  - Amount: {self.amount}")
            logger.info(f"  - Account: {self.account} (ID: {self.account.id})")
            logger.info(f"  - Payment Method: {self.payment_method}")
            logger.info(f"  - Description: {description}")
            transaction = Transaction.objects.create(
                transaction_type='debit',
                amount=self.amount,
                account=self.account,
                payment_method=self.payment_method,
                description=description,
                reference_no=self.invoice_number,
                expense=self,
                status='completed',
                transaction_date=self.expense_date,
                created_by=self.created_by
            )
            logger.info(f"SUCCESS: TRANSACTION CREATED - {transaction.transaction_no}")
            return transaction
        except ImportError as e:
            logger.error(f"ERROR: Failed to import Transaction model: {e}")
            return None
        except Exception as e:
            logger.error(f"ERROR: Error creating transaction: {str(e)}")
            logger.error(f"ERROR: Traceback: {traceback.format_exc()}")
            return None

    def force_create_transaction(self):
        """Force create a transaction if one doesn't exist"""
        try:
            from transactions.models import Transaction
            existing_transaction = Transaction.objects.filter(expense=self).first()
            if existing_transaction:
                logger.info(f"Transaction already exists: {existing_transaction.id}")
                return existing_transaction
            return self.create_expense_transaction()
        except Exception as e:
            logger.error(f"ERROR: Error in force_create_transaction: {e}")
            return None

    @property
    def description(self):
        if self.note:
            return self.note
        base_desc = f"{self.head.name if self.head else ''}"
        if self.subhead:
            base_desc += f" - {self.subhead.name}"
        return base_desc

    @property
    def status(self):
        if self.expense_date < timezone.now().date():
            return "Completed"
        elif self.expense_date == timezone.now().date():
            return "Today"
        else:
            return "Upcoming"

    @property
    def is_debit(self):
        return True

    def get_expense_summary(self):
        summary = {
            'id': self.id,
            'invoice_number': self.invoice_number,
            'head': self.head.name if self.head else '',
            'subhead': self.subhead.name if self.subhead else '',
            'amount': float(self.amount),
            'payment_method': self.get_payment_method_display(),
            'account': self.account.name if self.account else '',
            'expense_date': self.expense_date.isoformat(),
            'note': self.note,
            'status': self.status,
            'created_by': self.created_by.get_full_name() if self.created_by else 'System',
            'is_debit': self.is_debit
        }
        transaction = self.get_associated_transaction()
        if transaction:
            summary['transaction_id'] = transaction.id
            if hasattr(transaction, 'transaction_no'):
                summary['transaction_no'] = transaction.transaction_no
            summary['transaction_status'] = transaction.status
        else:
            summary['transaction_id'] = None
            summary['transaction_no'] = None
            summary['transaction_status'] = 'Not Created'
        return summary

    def get_associated_transaction(self):
        try:
            from transactions.models import Transaction
            # শুধু চালু debit টা — edit এর পর পুরনোটা cancelled থাকে; সেটা ধরলে দ্বিতীয় edit এ
            # পুরনো টাকা আবার ফেরত চলে যেত
            transaction = Transaction.objects.filter(
                expense=self, transaction_type='debit', status='completed'
            ).order_by('-id').first()
            if transaction:
                logger.info(f"Found associated transaction: {transaction.id}")
            else:
                logger.info(f"No associated transaction found for expense {self.id}")
            return transaction
        except ImportError:
            logger.error("ERROR: Cannot import Transaction model")
            return None
        except Exception as e:
            logger.error(f"ERROR: Error getting associated transaction: {e}")
            return None

    def has_transaction(self):
        transaction = self.get_associated_transaction()
        return transaction is not None

# Management command is unchanged (good)