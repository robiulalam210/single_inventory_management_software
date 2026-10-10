from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from accounts.models import Account
from django.conf import settings
from purchases.models import Purchase
from supplier_payment.model import SupplierPayment


from django.db.models import Q  
from django.db.models import F
import random
import string
import logging

logger = logging.getLogger(__name__)

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('debit', 'Debit'),
        ('credit', 'Credit'),
    ]
    
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('mobile', 'Mobile Banking'),
        ('card', 'Card'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    # Basic Info
    transaction_no = models.CharField(max_length=50, unique=True, blank=True)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    is_opening_balance = models.BooleanField(default=False)
    balance_already_updated = models.BooleanField(default=False)

    # Account
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')

    # Payment
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    cheque_no = models.CharField(max_length=100, blank=True, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)

    # Dates
    transaction_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    date_updated = models.DateTimeField(auto_now=True)

    # Flags
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')

    # Links to other models
    money_receipt = models.ForeignKey(
        'money_receipts.MoneyReceipt', 
        on_delete=models.SET_NULL,
        null=True, blank=True, 
        related_name='transactions'
    )
    sale = models.ForeignKey(
        'sales.Sale', 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name='transactions'
    )
    income = models.ForeignKey('income.Income', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    expense = models.ForeignKey(
        'expenses.Expense', 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name='transactions'
    )
    purchase = models.ForeignKey(
        'purchases.Purchase', 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name='transactions'
    )
    
    supplier_payment = models.ForeignKey(
    SupplierPayment,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='transactions'
)

  
    # Extra
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-transaction_date', '-id']
        indexes = [
            models.Index(fields=['transaction_date']),
            models.Index(fields=['account', 'transaction_date']),
            models.Index(fields=['transaction_no']),
            models.Index(fields=['supplier_payment']),
        ]

    def __str__(self):
        return f"{self.transaction_no} - {self.transaction_type} - {self.amount}"

    def save(self, *args, **kwargs):
        # Skip balance update if already done (for transfer transactions)
        if self.balance_already_updated:
            # Just save the transaction without updating balance
            is_new = self.pk is None
            if is_new and not self.transaction_no:
                self.transaction_no = self._generate_transaction_no()
            
            self.clean()
            super().save(*args, **kwargs)
            return
        
        # Original logic for non-transfer transactions
        is_new = self.pk is None

        # Generate transaction number if new
        if is_new and not self.transaction_no:
            self.transaction_no = self._generate_transaction_no()

        # Validate before saving
        self.clean()

        # Save the transaction first
        super().save(*args, **kwargs)

        # DEBUG LOGGING
        logger.info(f"TRANSACTION SAVE:")
        logger.info(f"  - ID: {self.id}")
        logger.info(f"  - No: {self.transaction_no}")
        logger.info(f"  - Account: {self.account.name if self.account else 'None'}")
        logger.info(f"  - Amount: {self.amount}")
        logger.info(f"  - Type: {self.transaction_type}")
        logger.info(f"  - Is New: {is_new}")

        # Update account balance for completed non-opening transactions
        if is_new and self.status == 'completed' and not self.is_opening_balance:
            logger.info(f"Updating account balance")
            self._update_account_balance()
        else:
            logger.info(f" Skipping balance update")

    def _generate_transaction_no(self):
        """Sequential transaction number: TXN-100001"""
        try:
            last = Transaction.objects.filter(
                transaction_no__regex=r'^TXN-\d+$'
            ).order_by('-id').first()
            new_number = 100001
            if last:
                try:
                    new_number = int(last.transaction_no.split('-')[1]) + 1
                except (ValueError, IndexError):
                    new_number = 100001 + Transaction.objects.count()
            transaction_no = f"TXN-{new_number:06d}"
            while Transaction.objects.filter(transaction_no=transaction_no).exists():
                new_number += 1
                transaction_no = f"TXN-{new_number:06d}"
            return transaction_no
        except Exception as e:
            logger.error(f"ERROR: Error generating transaction number: {str(e)}", exc_info=True)
            return f"TXN-{int(timezone.now().timestamp())}"

    def _update_account_balance(self):
        """Update account balance based on transaction"""
        try:
            # Refresh account to get latest balance
            account = Account.objects.get(id=self.account.id)
            old_balance = account.balance
            
            logger.info(f"BALANCE UPDATE DEBUG - Before:")
            logger.info(f"  - Account: {account.name}")
            logger.info(f"  - Old Balance: {old_balance}")
            logger.info(f"  - Transaction Type: {self.transaction_type}")
            logger.info(f"  - Amount: {self.amount}")
            
            if self.transaction_type == 'credit':
                # CREDIT increases balance
                new_balance = old_balance + self.amount
                account.balance = new_balance
                logger.info(f" CREDIT: Account {account.name} balance updated from {old_balance} to {new_balance} (+{self.amount})")
                
            elif self.transaction_type == 'debit':
                # DEBIT decreases balance with proper validation
                if old_balance < self.amount:
                    # Check if this is an opening balance transaction or special case
                    if self.is_opening_balance:
                        # Allow negative for opening balance setup
                        new_balance = old_balance - self.amount
                        account.balance = new_balance
                        logger.warning(f" DEBIT (Opening): Account {account.name} balance updated from {old_balance} to {new_balance} (-{self.amount}) - Negative balance allowed for opening")
                    else:
                        # Regular debit transaction - insufficient funds
                        error_msg = f"Insufficient balance in account {account.name}. Available: {old_balance}, Required: {self.amount}"
                        logger.error(f"ERROR:{error_msg}")
                        # Mark transaction as failed
                        self.status = 'failed'
                        super().save(update_fields=['status'])
                        raise ValidationError(error_msg)
                else:
                    # Sufficient funds
                    new_balance = old_balance - self.amount
                    account.balance = new_balance
                    logger.info(f"DEBIT: Account {account.name} balance updated from {old_balance} to {new_balance} (-{self.amount})")
            
            # Save the updated account balance
            account.save(update_fields=['balance', 'updated_at'])
            logger.info(f" Account balance saved successfully")
            
            # Update transaction status if it was successful
            if self.status != 'failed':
                self.status = 'completed'
                super().save(update_fields=['status'])
            
        except Exception as e:
            logger.error(f"Error updating account balance: {e}")
            # Mark transaction as failed
            if self.pk:
                self.status = 'failed'
                super().save(update_fields=['status'])
            raise

    def clean(self):
        """Validate the transaction"""
        if self.amount <= 0:
            raise ValidationError("Transaction amount must be greater than 0")
        
        # Improved debit transaction validation
        if (self.transaction_type == 'debit' and 
            self.status == 'completed' and 
            self.account and 
            not self.is_opening_balance):
            
            # Refresh account to get current balance
            current_account = Account.objects.get(id=self.account.id)
            if self.amount > current_account.balance:
                raise ValidationError(
                    f"Insufficient balance in account {current_account.name}. "
                    f"Available: {current_account.balance}, Required: {self.amount}"
                )

    def reverse(self):
        """Reverse this transaction"""
        if self.status != 'completed':
            raise ValidationError("Only completed transactions can be reversed")
        
        with transaction.atomic():
            # Create reversal transaction with proper amount handling
            reversal_type = 'credit' if self.transaction_type == 'debit' else 'debit'
            
            reversal = Transaction.objects.create(
                transaction_type=reversal_type,
                amount=self.amount,
                account=self.account,
                payment_method=self.payment_method,
                description=f"Reversal of {self.transaction_no} - {self.description}",
                created_by=self.created_by,
                status='completed',
                is_opening_balance=False
            )
            
            # Mark original as cancelled
            self.status = 'cancelled'
            self.save(update_fields=['status'])
            
            logger.info(f"Transaction {self.transaction_no} reversed by {reversal.transaction_no}")
            return reversal

    @property
    def is_debit(self):
        return self.transaction_type == 'debit'

    @property
    def is_credit(self):
        return self.transaction_type == 'credit'

    @staticmethod
    def normalize_payment_method(value):
        """App থেকে 'Cash' / 'Mobile Banking' / 'Bank' আসে; এখানে choices হলো cash/mobile/bank।"""
        v = (value or '').strip().lower()
        if 'mobile' in v or 'bkash' in v or 'nagad' in v or 'rocket' in v:
            return 'mobile'
        if 'bank' in v or 'cheque' in v:
            return 'bank'
        if 'card' in v:
            return 'card'
        if 'cash' in v or not v:
            return 'cash'
        return 'other'

    @classmethod
    def create_for_money_receipt(cls, money_receipt):
        """Create transaction for a money receipt"""
        try:
            if not money_receipt.account:
                logger.error(f"No account set for money receipt {money_receipt.mr_no}")
                return None
            
            # Use atomic transaction for consistency
            with transaction.atomic():
                transaction_obj = cls.objects.create(
                    transaction_type='credit',  # Money receipt is always credit
                    amount=money_receipt.amount,
                    account=money_receipt.account,
                    payment_method=cls.normalize_payment_method(money_receipt.payment_method),
                    sale=money_receipt.sale,
                    reference_no=money_receipt.mr_no,
                    description=f"Money Receipt {money_receipt.mr_no} - {money_receipt.get_customer_display()}",
                    money_receipt=money_receipt,
                    created_by=money_receipt.created_by,
                    status='completed',
                    transaction_date=money_receipt.payment_date,
                    is_opening_balance=False
                )
                
                logger.info(f"SUCCESS: Transaction created for money receipt: {transaction_obj.transaction_no}")
                return transaction_obj
            
        except Exception as e:
            logger.error(f"ERROR:Error creating transaction for money receipt {money_receipt.mr_no}: {e}")
            return None

    @classmethod
    def create_for_purchase_payment(cls, purchase, amount, payment_method, account, created_by):
        """Create transaction for purchase payment - SIMPLIFIED VERSION"""
        try:
            transaction_obj = cls(
                transaction_type='debit',
                amount=amount,
                account=account,
                payment_method=payment_method,
                description=f"Purchase Payment - {purchase.invoice_no} - {purchase.supplier.name}",
                purchase=purchase,
                created_by=created_by,
                status='completed',
                transaction_date=timezone.now(),
                is_opening_balance=False
            )
            
            # Generate transaction number before saving
            transaction_obj.transaction_no = transaction_obj._generate_transaction_no()
            transaction_obj.save()
            
            logger.info(f" Debit transaction created: {transaction_obj.transaction_no}")
            return transaction_obj
            
        except Exception as e:
            logger.error(f" Error creating transaction for purchase payment: {e}")
            return None

    @classmethod
    def create_for_expense(cls, expense):
        """Create transaction for expense"""
        try:
            if not expense.account:
                logger.error(f"No account set for expense {expense.invoice_number}")
                return None
            
            # Expenses are DEBIT transactions (money going out)
            with transaction.atomic():
                transaction_obj = cls.objects.create(
                    transaction_type='debit',  # Expense decreases balance
                    amount=expense.amount,
                    account=expense.account,
                    payment_method=expense.payment_method or 'cash',
                    description=f"Expense - {expense.invoice_number} - {expense.category.name if expense.category else 'No Category'}",
                    expense=expense,
                    created_by=expense.created_by,
                    status='completed',
                    transaction_date=expense.expense_date,
                    is_opening_balance=False
                )
                
                logger.info(f"Debit transaction created for expense: {transaction_obj.transaction_no}")
                return transaction_obj
            
        except Exception as e:
            logger.error(f" Error creating transaction for expense: {e}")
            return None

    @classmethod
    def create_for_supplier_payment(cls, supplier_payment, cash_amount):
        """Create transaction for supplier payment - ENHANCED VERSION"""
        try:
            logger.info(f"Attempting to create transaction for supplier payment: {supplier_payment.sp_no}")
            logger.info(f"  - Cash Amount: {cash_amount}")
            logger.info(f"  - Account: {supplier_payment.account}")
            logger.info(f"  - Payment Method: {supplier_payment.payment_method}")
            
            if not supplier_payment.account:
                logger.error(f" No account set for supplier payment {supplier_payment.sp_no}")
                return None
            
            if cash_amount <= 0:
                logger.info(f"No cash portion for supplier payment {supplier_payment.sp_no}, skipping transaction")
                return None
            
            # Supplier payments are DEBIT transactions (money going out)
            with transaction.atomic():
                transaction_obj = cls.objects.create(
                    transaction_type='debit',  # Supplier payment decreases balance
                    amount=cash_amount,
                    account=supplier_payment.account,
                    payment_method=supplier_payment.payment_method,
                    reference_no=supplier_payment.reference_no,
                    description=cls._generate_supplier_payment_description(supplier_payment),
                    supplier_payment=supplier_payment,  # LINK TO SUPPLIER PAYMENT
                    created_by=supplier_payment.created_by,
                    status='completed',
                    transaction_date=timezone.now(),
                    is_opening_balance=False
                )
                
                logger.info(f" Debit transaction created for supplier payment: {transaction_obj.transaction_no}")
                logger.info(f" Transaction {transaction_obj.transaction_no} linked to supplier payment {supplier_payment.sp_no}")
                return transaction_obj
            
        except Exception as e:
            logger.error(f" Error creating transaction for supplier payment {supplier_payment.sp_no}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    @classmethod
    def _generate_supplier_payment_description(cls, supplier_payment):
        """Generate description for supplier payment transaction"""
        base_desc = f"Supplier Payment - {supplier_payment.supplier.name}"
        
        if supplier_payment.payment_type == 'specific' and supplier_payment.purchase:
            return f"{base_desc} - Invoice: {supplier_payment.purchase.invoice_no}"
        elif supplier_payment.payment_type == 'advance':
            return f"{base_desc} - Advance Payment"
        else:
            return f"{base_desc} - Overall Payment"

    @classmethod
    def get_account_balance(cls, account):
        """Calculate account balance from transactions (for verification)"""
        try:
            credits = cls.objects.filter(
                account=account, 
                status='completed',
                transaction_type='credit',
                is_opening_balance=False
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            
            debits = cls.objects.filter(
                account=account, 
                status='completed',
                transaction_type='debit', 
                is_opening_balance=False
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            
            # Opening balance transactions (both debit and credit affect balance)
            opening_credits = cls.objects.filter(
                account=account,
                status='completed', 
                transaction_type='credit',
                is_opening_balance=True
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            
            opening_debits = cls.objects.filter(
                account=account,
                status='completed',
                transaction_type='debit',
                is_opening_balance=True
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            
            total_balance = (credits + opening_credits) - (debits + opening_debits)
            
            logger.info(f" Account Balance Calculation for {account.name}:")
            logger.info(f"  - Regular Credits: {credits}")
            logger.info(f"  - Regular Debits: {debits}")
            logger.info(f"  - Opening Credits: {opening_credits}")
            logger.info(f"  - Opening Debits: {opening_debits}")
            logger.info(f"  - Calculated Balance: {total_balance}")
            logger.info(f"  - Stored Balance: {account.balance}")
            
            return total_balance
            
        except Exception as e:
            logger.error(f" Error calculating account balance: {e}")
            return Decimal('0.00')

    def get_transaction_details(self):
        """Get detailed transaction information"""
        return {
            'id': self.id,
            'transaction_no': self.transaction_no,
            'type': self.transaction_type,
            'amount': float(self.amount),
            'account': self.account.name,
            'payment_method': self.payment_method,
            'status': self.status,
            'date': self.transaction_date.isoformat(),
            'description': self.description,
            'is_opening_balance': self.is_opening_balance,
            'linked_to': self._get_linked_object_type()
        }

    def _get_linked_object_type(self):
        """Get the type of object this transaction is linked to"""
        if self.money_receipt:
            return f"Money Receipt: {self.money_receipt.mr_no}"
        elif self.sale:
            return f"Sale: {self.sale.invoice_no}"
        elif self.expense:
            return f"Expense: {self.expense.invoice_number}"
        elif self.purchase:
            return f"Purchase: {self.purchase.invoice_no}"
        elif self.supplier_payment:
            return f"Supplier Payment: {self.supplier_payment.sp_no}"
        else:
            return "Manual Transaction"