# core/management/commands/fix_serial_numbers.py

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from sales.models import Sale
from purchases.models import Purchase
from money_receipts.models import MoneyReceipt
from expenses.models import Expense
from core.models import Company
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Reset all serial numbers to start from 1001 for each company'
    
    def handle(self, *args, **options):
        self.stdout.write("🔄 Resetting all serial numbers...")
        
        try:
            with transaction.atomic():
                # Use direct SQL to avoid model save methods and constraints
                self.fix_with_sql()
                
            self.stdout.write(self.style.SUCCESS("SUCCESS: All serial numbers reset successfully!"))
            
            # Verify the results
            self.verify_serial_numbers()
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"ERROR:Error: {str(e)}"))
            logger.error(f"Error resetting serial numbers: {str(e)}")
    
    def fix_with_sql(self):
        """Use raw SQL to reset serial numbers and avoid constraints"""
        self.stdout.write("🔄 Using SQL approach to avoid constraints...")
        
        # Get database vendor
        vendor = connection.vendor
        
        if vendor == 'sqlite':
            self.fix_sqlite()
        elif vendor == 'postgresql':
            self.fix_postgresql()
        else:
            self.fix_generic()
    
    def fix_sqlite(self):
        """Fix for SQLite database"""
        with connection.cursor() as cursor:
            # Disable foreign keys temporarily
            cursor.execute("PRAGMA foreign_keys=OFF")
            
            # Reset Money Receipts
            self.stdout.write("🔄 Fixing Money Receipts...")
            cursor.execute("""
                UPDATE money_receipts_moneyreceipt 
                SET mr_no = 'MR-' || (
                    1000 + (
                        SELECT COUNT(*) 
                        FROM money_receipts_moneyreceipt m2 
                        WHERE m2.company_id = money_receipts_moneyreceipt.company_id 
                        AND m2.id <= money_receipts_moneyreceipt.id
                    )
                )
            """)
            
            # Reset Sales
            self.stdout.write("🔄 Fixing Sales...")
            cursor.execute("""
                UPDATE sales_sale 
                SET invoice_no = 'SL-' || (
                    1000 + (
                        SELECT COUNT(*) 
                        FROM sales_sale s2 
                        WHERE s2.company_id = sales_sale.company_id 
                        AND s2.id <= sales_sale.id
                    )
                )
            """)
            
            # Reset Purchases
            self.stdout.write("🔄 Fixing Purchases...")
            cursor.execute("""
                UPDATE purchases_purchase 
                SET invoice_no = 'PO-' || (
                    1000 + (
                        SELECT COUNT(*) 
                        FROM purchases_purchase p2 
                        WHERE p2.company_id = purchases_purchase.company_id 
                        AND p2.id <= purchases_purchase.id
                    )
                )
            """)
            
            # Reset Expenses
            self.stdout.write("🔄 Fixing Expenses...")
            cursor.execute("""
                UPDATE expenses_expense 
                SET invoice_number = 'EXP-' || (
                    1000 + (
                        SELECT COUNT(*) 
                        FROM expenses_expense e2 
                        WHERE e2.company_id = expenses_expense.company_id 
                        AND e2.id <= expenses_expense.id
                    )
                )
            """)
            
            # Re-enable foreign keys
            cursor.execute("PRAGMA foreign_keys=ON")
    
    def fix_postgresql(self):
        """Fix for PostgreSQL database"""
        with connection.cursor() as cursor:
            # Reset Money Receipts
            self.stdout.write("🔄 Fixing Money Receipts...")
            cursor.execute("""
                UPDATE money_receipts_moneyreceipt 
                SET mr_no = 'MR-' || (1000 + row_number)
                FROM (
                    SELECT id, ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY id) as row_number
                    FROM money_receipts_moneyreceipt
                ) AS numbered
                WHERE money_receipts_moneyreceipt.id = numbered.id
            """)
            
            # Reset Sales
            self.stdout.write("🔄 Fixing Sales...")
            cursor.execute("""
                UPDATE sales_sale 
                SET invoice_no = 'SL-' || (1000 + row_number)
                FROM (
                    SELECT id, ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY id) as row_number
                    FROM sales_sale
                ) AS numbered
                WHERE sales_sale.id = numbered.id
            """)
            
            # Reset Purchases
            self.stdout.write("🔄 Fixing Purchases...")
            cursor.execute("""
                UPDATE purchases_purchase 
                SET invoice_no = 'PO-' || (1000 + row_number)
                FROM (
                    SELECT id, ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY id) as row_number
                    FROM purchases_purchase
                ) AS numbered
                WHERE purchases_purchase.id = numbered.id
            """)
            
            # Reset Expenses
            self.stdout.write("🔄 Fixing Expenses...")
            cursor.execute("""
                UPDATE expenses_expense 
                SET invoice_number = 'EXP-' || (1000 + row_number)
                FROM (
                    SELECT id, ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY id) as row_number
                    FROM expenses_expense
                ) AS numbered
                WHERE expenses_expense.id = numbered.id
            """)
    
    def fix_generic(self):
        """Generic fix for other databases"""
        companies = Company.objects.all()
        
        for company in companies:
            self.stdout.write(f"🔄 Processing {company.name}...")
            
            # Fix Money Receipts
            receipts = MoneyReceipt.objects.filter(company=company).order_by('id')
            counter = 1001
            for receipt in receipts:
                MoneyReceipt.objects.filter(pk=receipt.pk).update(mr_no=f"MR-{counter}")
                counter += 1
            
            # Fix Sales
            sales = Sale.objects.filter(company=company).order_by('id')
            counter = 1001
            for sale in sales:
                Sale.objects.filter(pk=sale.pk).update(invoice_no=f"SL-{counter}")
                counter += 1
            
            # Fix Purchases
            purchases = Purchase.objects.filter(company=company).order_by('id')
            counter = 1001
            for purchase in purchases:
                Purchase.objects.filter(pk=purchase.pk).update(invoice_no=f"PO-{counter}")
                counter += 1
            
            # Fix Expenses
            expenses = Expense.objects.filter(company=company).order_by('id')
            counter = 1001
            for expense in expenses:
                Expense.objects.filter(pk=expense.pk).update(invoice_number=f"EXP-{counter}")
                counter += 1
    
    def verify_serial_numbers(self):
        """Verify that serial numbers were reset correctly"""
        self.stdout.write("\n🔍 Verifying serial numbers...")
        
        companies = Company.objects.all()
        
        for company in companies:
            self.stdout.write(f"\n=== {company.name} ===")
            
            # Check counts and ranges
            sales = Sale.objects.filter(company=company)
            purchases = Purchase.objects.filter(company=company)
            receipts = MoneyReceipt.objects.filter(company=company)
            expenses = Expense.objects.filter(company=company)
            
            self.stdout.write(f"Sales: {sales.count()} records")
            if sales.exists():
                first_sale = sales.order_by('invoice_no').first()
                last_sale = sales.order_by('invoice_no').last()
                self.stdout.write(f"  Range: {first_sale.invoice_no} to {last_sale.invoice_no}")
            
            self.stdout.write(f"Purchases: {purchases.count()} records")
            if purchases.exists():
                first_purchase = purchases.order_by('invoice_no').first()
                last_purchase = purchases.order_by('invoice_no').last()
                self.stdout.write(f"  Range: {first_purchase.invoice_no} to {last_purchase.invoice_no}")
            
            self.stdout.write(f"Money Receipts: {receipts.count()} records")
            if receipts.exists():
                first_receipt = receipts.order_by('mr_no').first()
                last_receipt = receipts.order_by('mr_no').last()
                self.stdout.write(f"  Range: {first_receipt.mr_no} to {last_receipt.mr_no}")
            
            self.stdout.write(f"Expenses: {expenses.count()} records")
            if expenses.exists():
                first_expense = expenses.order_by('invoice_number').first()
                last_expense = expenses.order_by('invoice_number').last()
                self.stdout.write(f"  Range: {first_expense.invoice_number} to {last_expense.invoice_number}")
            
            # Check for duplicates
            self.check_duplicates(company)
    
    def check_duplicates(self, company):
        """Check for duplicate serial numbers"""
        # Check Money Receipt duplicates
        receipt_duplicates = MoneyReceipt.objects.filter(
            company=company
        ).values('mr_no').annotate(
            count=models.Count('id')
        ).filter(count__gt=1)
        
        if receipt_duplicates.exists():
            self.stdout.write(self.style.WARNING(f"  ⚠️  Money Receipt duplicates: {list(receipt_duplicates)}"))
        
        # Check Sales duplicates
        sale_duplicates = Sale.objects.filter(
            company=company
        ).values('invoice_no').annotate(
            count=models.Count('id')
        ).filter(count__gt=1)
        
        if sale_duplicates.exists():
            self.stdout.write(self.style.WARNING(f"  ⚠️  Sales duplicates: {list(sale_duplicates)}"))