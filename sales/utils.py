from decimal import Decimal
from django.db import transaction
from .models import Sale, SaleItem, Customer
from products.models import Product

def create_sale_with_items(customer, sale_items_data, sale_type='retail', sale_by=''):
    """
    sale_items_data = [
        {"product": product_obj, "quantity": 2, "unit_price": 500, "discount": 50, "discount_type": "fixed"},
        {"product": product_obj2, "quantity": 1, "unit_price": 300, "discount": 10, "discount_type": "%"},
        ...
    ]
    """

    with transaction.atomic():
        # Sale প্রথমে create করুন, totals 0 দিয়ে
        sale = Sale.objects.create(
            customer=customer,
            sale_type=sale_type,
            sale_by=sale_by,
            gross_total=0,
            net_total=0,
            payable_amount=0
        )

        gross_total = Decimal('0')
        net_total = Decimal('0')

        # SaleItem create করুন
        for item_data in sale_items_data:
            product = item_data["product"]
            quantity = Decimal(item_data["quantity"])
            unit_price = Decimal(item_data["unit_price"])
            discount = Decimal(item_data.get("discount", 0))
            discount_type = item_data.get("discount_type", "fixed")

            # SaleItem create
            sale_item = SaleItem.objects.create(
                sale=sale,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                discount=discount,
                discount_type=discount_type
            )

            # subtotal হিসাব করুন
            if discount_type == "%":
                subtotal = (quantity * unit_price) - ((quantity * unit_price) * discount / 100)
            else:
                subtotal = (quantity * unit_price) - discount

            gross_total += quantity * unit_price
            net_total += subtotal

            # Product stock update
            product.stock_qty -= quantity
            product.save()

        # Sale এর totals update
        sale.gross_total = gross_total
        sale.net_total = net_total
        sale.payable_amount = net_total  # চাইলে এখানে delivery_charge, vat, etc যোগ করতে পারেন
        sale.save()

        return sale
