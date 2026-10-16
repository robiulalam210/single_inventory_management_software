from rest_framework import serializers
from django.db.models import Sum, F
from decimal import Decimal
from .models import Customer
from sales.models import Sale

class CustomerSerializer(serializers.ModelSerializer):
    total_due = serializers.SerializerMethodField()
    total_paid = serializers.SerializerMethodField()
    amount_type = serializers.SerializerMethodField()
    client_no = serializers.SerializerMethodField()
    total_sales = serializers.SerializerMethodField()
    advance_balance = serializers.SerializerMethodField()
    payment_breakdown = serializers.SerializerMethodField()
    customer_type = serializers.SerializerMethodField()
    total_bought = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'phone', 'email', 'address', 'is_active',
            'client_no', 'total_due', 'total_paid', 'amount_type',
            'total_sales', 'date_created', 'created_by',
            'advance_balance', 'payment_breakdown', 'special_customer',
            'customer_type', 'total_bought'
        ]
        read_only_fields = ['date_created', 'created_by', 'customer_type']

    def get_client_no(self, obj):
        """Get client number - use existing or generate if missing"""
        if obj.client_no:
            return obj.client_no
        
        # Generate client number if missing
        try:
            last_customer = Customer.objects.order_by("-id").first()
            new_id = (last_customer.id + 1) if last_customer else 1
            return f"CU-{1000 + new_id}"
        except:
            return f"CU-{1000 + obj.id}" if obj.id else "CU-1000"

    def get_total_bought(self, obj):
        """এই customer এর কাছে মোট কত টাকার বিক্রি (সব invoice এর grand total)"""
        return self.get_total_grand_total(obj)

    def get_customer_type(self, obj):
        """Get customer type display"""
        return "Special" if obj.special_customer else "Regular"

    def get_total_sales(self, obj):
        if hasattr(obj, 'sales_count'):
            return obj.sales_count
        return obj.sale_set.count()

    def get_total_grand_total(self, obj):
        """Get total grand total from sales"""
        try:
            if hasattr(obj, 'total_grand_total') and obj.total_grand_total is not None:
                return float(obj.total_grand_total)
            
            sales_total = Sale.objects.filter(
                customer=obj
            ).aggregate(total=Sum('grand_total'))
            
            return float(sales_total['total'] or 0)
        except:
            return 0.00

    def get_total_paid(self, obj):
        """Get total paid from sales"""
        try:
            if hasattr(obj, 'total_paid_amount') and obj.total_paid_amount is not None:
                return float(obj.total_paid_amount)
            
            sales_total = Sale.objects.filter(
                customer=obj
            ).aggregate(total=Sum('paid_amount'))
            
            return float(sales_total['total'] or 0)
        except:
            return 0.00

    def get_advance_balance(self, obj):
        """Return CORRECT advance balance calculation"""
        try:
            # Sync advance balance to ensure accuracy
            sync_result = obj.sync_advance_balance()
            
            if sync_result['synced']:
                # Return the newly synced value
                return sync_result['new_value']
            else:
                # Return the correct value
                return sync_result['current_value']
                
        except Exception as e:
            # Fallback to stored value
            try:
                return float(obj.advance_balance) if obj.advance_balance else 0.0
            except:
                return 0.0

    def get_total_due(self, obj):
        """Calculate total due properly considering advance"""
        try:
            grand_total = self.get_total_grand_total(obj)
            total_paid = self.get_total_paid(obj)
            
            # Basic due calculation
            basic_due = grand_total - total_paid
            
            # If there's advance balance, it reduces the due
            advance = self.get_advance_balance(obj)
            adjusted_due = max(0.0, basic_due - advance)
            
            return adjusted_due
        except:
            return 0.00

    def get_amount_type(self, obj):
        """Determine amount type considering advance"""
        try:
            advance = self.get_advance_balance(obj)
            grand_total = self.get_total_grand_total(obj)
            total_paid = self.get_total_paid(obj)
            total_due = self.get_total_due(obj)
            
            if advance > 0 and advance > (grand_total - total_paid):
                return "Advance"
            elif total_due > 0:
                return "Due"
            else:
                return "Paid"
        except:
            return "Paid"

    def get_payment_breakdown(self, obj):
        """Get detailed payment breakdown"""
        try:
            return obj.get_detailed_payment_breakdown()
        except Exception as e:
            return {
                'error': str(e),
                'customer_id': obj.id,
                'customer_name': obj.name,
                'summary': {
                    'advance': {'total': 0, 'count': 0},
                    'due': {'total': 0, 'count': 0},
                    'paid': {'total': 0, 'count': 0}
                },
                'details': {
                    'advance_receipts': [],
                    'due_sales': [],
                    'paid_sales': []
                }
            }