# transactions/services.py
from django.db import transaction as db_transaction
from .models import Transaction
import logging

logger = logging.getLogger(__name__)

class TransactionService:
    
    @staticmethod
    @db_transaction.atomic
    def create_sale_transaction(sale, account, payment_method, amount, created_by):
        """
        Create transaction for sale payment with proper validation
        """
        try:
            # Validate inputs
            if amount <= 0:
                raise ValueError("Transaction amount must be greater than 0")
            
            if not account:
                raise ValueError("Account is required for transaction")
            
            # Create the transaction
            transaction = Transaction.objects.create(
                transaction_type='credit',  # Sale increases account balance
                amount=amount,
                account=account,
                payment_method=payment_method,
                description=f"Sale payment - {sale.invoice_no} - {sale.get_customer_display()}",
                created_by=created_by,
                sale=sale,
                status='completed'
            )
            
            logger.info(f"Sale transaction created: {transaction.transaction_no}")
            return transaction
            
        except Exception as e:
            logger.error(f"Error creating sale transaction: {str(e)}")
            raise

    @staticmethod
    @db_transaction.atomic
    def create_expense_transaction(expense, created_by):
        """
        Create transaction for expense payment
        """
        try:
            transaction = Transaction.objects.create(
                transaction_type='debit',  # Expense decreases account balance
                amount=expense.amount,
                account=expense.account,
                payment_method=expense.payment_method,
                description=f"Expense: {expense.category} - {expense.description}",
                created_by=created_by,
                expense=expense,
                status='completed'
            )
            
            logger.info(f"Expense transaction created: {transaction.transaction_no}")
            return transaction
            
        except Exception as e:
            logger.error(f"Error creating expense transaction: {str(e)}")
            raise

    @staticmethod
    @db_transaction.atomic
    def create_money_receipt_transaction(money_receipt, created_by):
        """
        Create transaction for money receipt
        """
        try:
            transaction = Transaction.objects.create(
                transaction_type='credit',  # Money receipt increases account balance
                amount=money_receipt.amount,
                account=money_receipt.account,
                payment_method=money_receipt.payment_method,
                description=f"Money Receipt {money_receipt.mr_no} - {money_receipt.get_customer_display()}",
                created_by=created_by,
                money_receipt=money_receipt,
                status='completed'
            )
            
            logger.info(f"Money receipt transaction created: {transaction.transaction_no}")
            return transaction
            
        except Exception as e:
            logger.error(f"Error creating money receipt transaction: {str(e)}")
            raise

    @staticmethod
    def get_account_balance(account, as_of_date=None):
        """
        Get account balance as of specific date
        """
        try:
            from django.db.models import Sum, Q
            
            transactions = Transaction.objects.filter(
                account=account,
                status='completed'
            )
            
            if as_of_date:
                transactions = transactions.filter(transaction_date__lte=as_of_date)
            
            credit_total = transactions.filter(transaction_type='credit').aggregate(
                total=Sum('amount')
            )['total'] or 0
            
            debit_total = transactions.filter(transaction_type='debit').aggregate(
                total=Sum('amount')
            )['total'] or 0
            
            return credit_total - debit_total
            
        except Exception as e:
            logger.error(f"Error getting account balance: {str(e)}")
            return 0