from django.core.management.base import BaseCommand
from sales.models import Sale
from money_receipts.models import MoneyReceipt
from transactions.models import Transaction
from accounts.models import Account
from decimal import Decimal, InvalidOperation
from django.db import connection
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'URGENT: Fix all decimal corruption in the entire database'

    def handle(self, *args, **options):
        self.stdout.write('🚨 URGENT: Fixing decimal corruption in database...')
        
        # FIX 1: Fix Sales data
        self.stdout.write('🔧 Fixing Sales data...')
        sales_fixed = self._fix_sales_data()
        
        # FIX 2: Fix Money Receipts data
        self.stdout.write('🔧 Fixing Money Receipts data...')
        receipts_fixed = self._fix_money_receipts_data()
        
        # FIX 3: Fix Transactions data
        self.stdout.write('🔧 Fixing Transactions data...')
        transactions_fixed = self._fix_transactions_data()
        
        # FIX 4: Fix Accounts data
        self.stdout.write('🔧 Fixing Accounts data...')
        accounts_fixed = self._fix_accounts_data()
        
        # FIX 5: Direct SQL fix for any remaining corrupted data
        self.stdout.write('🔧 Running direct SQL fixes...')
        sql_fixed = self._run_sql_fixes()
        
        self.stdout.write(self.style.SUCCESS(f'''
🎉 DECIMAL CORRUPTION FIXED!
• Sales fixed: {sales_fixed}
• Money Receipts fixed: {receipts_fixed}
• Transactions fixed: {transactions_fixed}
• Accounts fixed: {accounts_fixed}
• SQL fixes applied: {sql_fixed}
        '''))

    def _fix_sales_data(self):
        fixed_count = 0
        sales = Sale.objects.all()
        
        for sale in sales:
            try:
                # Test if this sale has corrupted decimal data
                needs_fix = False
                
                # List of decimal fields to check
                decimal_fields = [
                    'gross_total', 'net_total', 'grand_total', 'payable_amount',
                    'paid_amount', 'due_amount', 'change_amount', 'overall_discount',
                    'overall_delivery_charge', 'overall_service_charge', 'overall_vat_amount'
                ]
                
                # Check each field
                for field in decimal_fields:
                    value = getattr(sale, field)
                    try:
                        # Try to convert to Decimal to test if it's valid
                        Decimal(str(value))
                    except (InvalidOperation, TypeError):
                        # Field is corrupted, reset it
                        setattr(sale, field, Decimal('0.00'))
                        needs_fix = True
                        self.stdout.write(f'   Fixed {sale.invoice_no}.{field}: {value} → 0.00')
                
                # Also check if amounts are unreasonably large
                if sale.paid_amount > Decimal('1000000000'):  # Over 1 billion
                    sale.paid_amount = Decimal('0.00')
                    sale.due_amount = sale.payable_amount
                    needs_fix = True
                    self.stdout.write(f'   Fixed {sale.invoice_no} paid_amount: Too large')
                
                if sale.payable_amount > Decimal('1000000000'):
                    sale.payable_amount = Decimal('1000.00')
                    sale.due_amount = sale.payable_amount - sale.paid_amount
                    needs_fix = True
                    self.stdout.write(f'   Fixed {sale.invoice_no} payable_amount: Too large')
                
                if needs_fix:
                    # Update payment status
                    if sale.paid_amount >= sale.payable_amount:
                        sale.payment_status = 'paid'
                        sale.due_amount = Decimal('0.00')
                    elif sale.paid_amount > Decimal('0.00'):
                        sale.payment_status = 'partial'
                    else:
                        sale.payment_status = 'pending'
                    
                    sale.save()
                    fixed_count += 1
                    
            except Exception as e:
                self.stdout.write(f'   ERROR:Error fixing sale {sale.invoice_no}: {e}')
                # If we can't fix it, delete it (last resort)
                try:
                    sale.delete()
                    self.stdout.write(f'   🗑️  Deleted corrupted sale: {sale.invoice_no}')
                except:
                    pass
        
        return fixed_count

    def _fix_money_receipts_data(self):
        fixed_count = 0
        receipts = MoneyReceipt.objects.all()
        
        for receipt in receipts:
            try:
                needs_fix = False
                
                # Check amount field
                try:
                    Decimal(str(receipt.amount))
                except (InvalidOperation, TypeError):
                    receipt.amount = Decimal('0.00')
                    needs_fix = True
                    self.stdout.write(f'   Fixed {receipt.mr_no}.amount: {receipt.amount} → 0.00')
                
                # Check for unreasonable amounts
                if receipt.amount > Decimal('1000000000'):
                    receipt.amount = Decimal('0.00')
                    receipt.payment_status = 'failed'
                    needs_fix = True
                    self.stdout.write(f'   Fixed {receipt.mr_no} amount: Too large')
                
                if needs_fix:
                    receipt.save()
                    fixed_count += 1
                    
            except Exception as e:
                self.stdout.write(f'   ERROR:Error fixing receipt {receipt.mr_no}: {e}')
        
        return fixed_count

    def _fix_transactions_data(self):
        fixed_count = 0
        try:
            transactions = Transaction.objects.all()
            
            for transaction in transactions:
                try:
                    needs_fix = False
                    
                    # Check amount field
                    try:
                        Decimal(str(transaction.amount))
                    except (InvalidOperation, TypeError):
                        transaction.amount = Decimal('0.00')
                        needs_fix = True
                        self.stdout.write(f'   Fixed {transaction.transaction_no}.amount')
                    
                    if transaction.amount > Decimal('1000000000'):
                        transaction.amount = Decimal('0.00')
                        transaction.status = 'failed'
                        needs_fix = True
                        self.stdout.write(f'   Fixed {transaction.transaction_no} amount: Too large')
                    
                    if needs_fix:
                        transaction.save()
                        fixed_count += 1
                        
                except Exception as e:
                    self.stdout.write(f'   ERROR:Error fixing transaction {transaction.transaction_no}: {e}')
        
        except Exception as e:
            self.stdout.write(f'   ⚠️ Could not access transactions: {e}')
        
        return fixed_count

    def _fix_accounts_data(self):
        fixed_count = 0
        accounts = Account.objects.all()
        
        for account in accounts:
            try:
                needs_fix = False
                
                # Check balance field
                try:
                    Decimal(str(account.balance))
                except (InvalidOperation, TypeError):
                    account.balance = Decimal('0.00')
                    needs_fix = True
                    self.stdout.write(f'   Fixed {account.name}.balance')
                
                # Reset unreasonable balances
                if account.balance > Decimal('1000000000'):
                    account.balance = Decimal('10000.00')
                    needs_fix = True
                    self.stdout.write(f'   Fixed {account.name} balance: Too large')
                
                if account.balance < Decimal('-1000000000'):
                    account.balance = Decimal('0.00')
                    needs_fix = True
                    self.stdout.write(f'   Fixed {account.name} balance: Too negative')
                
                if needs_fix:
                    account.save()
                    fixed_count += 1
                    
            except Exception as e:
                self.stdout.write(f'   ERROR:Error fixing account {account.name}: {e}')
        
        return fixed_count

    def _run_sql_fixes(self):
        """Direct SQL fixes for stubborn corruption"""
        try:
            with connection.cursor() as cursor:
                # Fix sales decimal fields
                tables_fields = [
                    ('sales_sale', 'gross_total'), ('sales_sale', 'net_total'),
                    ('sales_sale', 'grand_total'), ('sales_sale', 'payable_amount'),
                    ('sales_sale', 'paid_amount'), ('sales_sale', 'due_amount'),
                    ('sales_sale', 'change_amount'), ('sales_sale', 'overall_discount'),
                    ('sales_sale', 'overall_delivery_charge'), ('sales_sale', 'overall_service_charge'),
                    ('sales_sale', 'overall_vat_amount'),
                    ('money_receipts_moneyreceipt', 'amount'),
                    ('transactions_transaction', 'amount'),
                    ('accounts_account', 'balance')
                ]
                
                fixed_count = 0
                for table, field in tables_fields:
                    try:
                        # Set any invalid values to 0
                        cursor.execute(f"UPDATE {table} SET {field} = 0 WHERE {field} IS NULL OR {field} = '' OR CAST({field} AS TEXT) = 'NaN'")
                        fixed_count += cursor.rowcount
                    except Exception as e:
                        self.stdout.write(f'   SQL fix failed for {table}.{field}: {e}')
                
                return fixed_count
                
        except Exception as e:
            self.stdout.write(f'   ERROR:SQL fixes failed: {e}')
            return 0