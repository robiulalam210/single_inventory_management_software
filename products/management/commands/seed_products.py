from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from products.models import Brand, Category, Product, Unit

# (নাম, ক্যাটাগরি, ব্র্যান্ড, ইউনিট, ক্রয়মূল্য, বিক্রয়মূল্য, স্টক, ছাড়% বা None)
ITEMS = [
    ('Miniket Rice 5kg', 'Grocery', 'Pran', 'Pack', 330, 400, 40, None),
    ('Soybean Oil 1L', 'Grocery', 'Teer', 'Bottle', 150, 175, 60, 10),
    ('Masoor Dal 1kg', 'Grocery', 'Radhuni', 'Pack', 110, 135, 50, None),
    ('Sugar 1kg', 'Grocery', 'Fresh', 'Pack', 115, 130, 80, None),
    ('Atta 2kg', 'Grocery', 'Aci', 'Pack', 95, 115, 45, 5),
    ('Salt 1kg', 'Grocery', 'Aci', 'Pack', 30, 40, 100, None),
    ('Mango Juice 250ml', 'Beverages', 'Pran', 'Bottle', 18, 25, 120, None),
    ('Cola 1.5L', 'Beverages', 'Pran', 'Bottle', 70, 85, 70, 10),
    ('Mineral Water 1L', 'Beverages', 'Fresh', 'Bottle', 14, 20, 200, None),
    ('Tea 400g', 'Beverages', 'Ispahani', 'Pack', 210, 250, 35, None),
    ('Potato Chips 50g', 'Snacks', 'Pran', 'Pack', 22, 30, 150, None),
    ('Biscuit 200g', 'Snacks', 'Olympic', 'Pack', 38, 50, 90, 15),
    ('Instant Noodles 4pk', 'Snacks', 'Maggi', 'Pack', 70, 90, 60, None),
    ('Bath Soap 100g', 'Personal care', 'Lux', 'Piece', 38, 50, 100, None),
    ('Shampoo 180ml', 'Personal care', 'Clear', 'Bottle', 190, 240, 30, 10),
    ('Toothpaste 100g', 'Personal care', 'Pepsodent', 'Piece', 75, 95, 55, None),
    ('Dish Wash Liquid 500ml', 'Household', 'Vim', 'Bottle', 95, 120, 40, None),
    ('Detergent Powder 1kg', 'Household', 'Wheel', 'Pack', 120, 150, 50, 10),
    ('Tissue Box', 'Household', 'Fresh', 'Piece', 45, 60, 70, None),
    ('Phone Charger 20W', 'Electronics', 'Generic', 'Piece', 350, 500, 15, 20),
]


class Command(BaseCommand):
    help = 'ডেমো ক্যাটাগরি, ব্র্যান্ড ও পণ্য যোগ করে (বারবার চালালেও ডুপ্লিকেট হয় না)।'

    @transaction.atomic
    def handle(self, *args, **opts):
        made = 0
        for name, cat, brand, unit, cost, price, stock, off in ITEMS:
            c, _ = Category.objects.get_or_create(name=cat)
            b, _ = Brand.objects.get_or_create(name=brand)
            u, _ = Unit.objects.get_or_create(name=unit)
            kw = dict(category=c, brand=b, unit=u, purchase_price=Decimal(cost), selling_price=Decimal(price),
                      opening_stock=stock, stock_qty=stock, alert_quantity=5, is_active=True)
            if off:
                kw.update(discount_type='percentage', discount_value=Decimal(off), discount_applied_on=True)
            _, created = Product.objects.get_or_create(name=name, defaults=kw)
            made += int(created)
        self.stdout.write(self.style.SUCCESS(f'{made} টা নতুন পণ্য যোগ হয়েছে ({len(ITEMS) - made} টা আগে থেকেই ছিল)।'))
