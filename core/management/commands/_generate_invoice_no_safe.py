# core/management/commands/fix_serial_numbers.py - FIXED VERSION

from django.core.management.base import BaseCommand
from django.db import transaction
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
        
        with transaction.atomic():
            # Temporarily remove unique constraint by setting mr_no to NULL first
            self.temporarily_remove_unique_constraints()
            
            # Reset serial numbers
            self.fix_sales_serial_numbers()
            self.fix_purchases_serial_numbers()  
            self.fix_money_receipts_serial_numbers()
            self.fix_expenses_serial_numbers()
            
        self.stdout.write(self.style.SUCCESS("SUCCESS: All serial numbers reset successfully!"))
    
    def temporarily_remove_unique_constraints(self):
        """Temporarily set unique fields to NULL to avoid constraint violations"""
        self.stdout.write("🔄 Temporarily removing unique constraints...")
        
        # Set money receipt numbers to temporary values
        MoneyReceipt.objects.all().update(mr_no=None)
        
        self.stdout.write("SUCCESS: Unique constraints temporarily removed")
    
    def fix_sales_serial_numbers(self):
        """Reset sales invoice numbers to SL-1001, SL-1002... per company"""
        companies = Company.objects.all()
        
        for company in companies:
            sales = Sale.objects.filter(company=company).order_by('id')
            counter = 1001
            
            for sale in sales:
                new_invoice_no = f"SL-{counter}"
                
                # Update without triggering signals
                Sale.objects.filter(pk=sale.pk).update(invoice_no=new_invoice_no)
                
                counter += 1
                
            self.stdout.write(f"SUCCESS: Company {company.name}: Fixed {sales.count()} sales")
    
    def fix_purchases_serial_numbers(self):
        """Reset purchase invoice numbers to PO-1001, PO-1002... per company"""
        companies = Company.objects.all()
        
        for company in companies:
            purchases = Purchase.objects.filter(company=company).order_by('id')
            counter = 1001
            
            for purchase in purchases:
                new_invoice_no = f"PO-{counter}"
                
                # Update without triggering signals
                Purchase.objects.filter(pk=purchase.pk).update(invoice_no=new_invoice_no)
                
                counter += 1
                
            self.stdout.write(f"SUCCESS: Company {company.name}: Fixed {purchases.count()} purchases")
    
    def fix_money_receipts_serial_numbers(self):
        """Reset money receipt numbers to MR-1001, MR-1002... per company"""
        companies = Company.objects.all()
        
        for company in companies:
            receipts = MoneyReceipt.objects.filter(company=company).order_by('id')
            counter = 1001
            
            for receipt in receipts:
                new_mr_no = f"MR-{counter}"
                
                # Update without triggering the save method
                MoneyReceipt.objects.filter(pk=receipt.pk).update(mr_no=new_mr_no)
                
                counter += 1
                
            self.stdout.write(f"SUCCESS: Company {company.name}: Fixed {receipts.count()} money receipts")
    
    def fix_expenses_serial_numbers(self):
        """Reset expense invoice numbers to EXP-1001, EXP-1002... per company"""
        companies = Company.objects.all()
        
        for company in companies:
            expenses = Expense.objects.filter(company=company).order_by('id')
            counter = 1001
            
            for expense in expenses:
                new_invoice_no = f"EXP-{counter}"
                
                # Update without triggering signals
                Expense.objects.filter(pk=expense.pk).update(invoice_number=new_invoice_no)
                
                counter += 1
                
            self.stdout.write(f"SUCCESS: Company {company.name}: Fixed {expenses.count()} expenses")