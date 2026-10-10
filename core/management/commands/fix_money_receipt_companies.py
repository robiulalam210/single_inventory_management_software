# Run in Django shell
from money_receipts.models import MoneyReceipt
from django.contrib.auth import get_user_model

User = get_user_model()

def fix_money_receipt_companies():
    """Fix money receipts with company mismatches"""
    
    receipts = MoneyReceipt.objects.all()
    fixed_count = 0
    
    for receipt in receipts:
        try:
            # Determine correct company
            correct_company = None
            
            if receipt.customer:
                correct_company = receipt.customer.company
            elif receipt.sale:
                correct_company = receipt.sale.company
            elif receipt.created_by and hasattr(receipt.created_by, 'company'):
                correct_company = receipt.created_by.company
            
            # Fix if company is wrong
            if correct_company and receipt.company != correct_company:
                print(f"Fixing {receipt.mr_no}: {receipt.company} → {correct_company}")
                receipt.company = correct_company
                receipt.save(update_fields=['company'])
                fixed_count += 1
                
        except Exception as e:
            print(f"Error fixing {receipt.mr_no}: {e}")
    
    print(f"SUCCESS: Fixed {fixed_count} money receipts")

fix_money_receipt_companies()