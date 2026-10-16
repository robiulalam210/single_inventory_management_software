"""বাদাম / বীজ / শুকনো ফল / মধুর ডেমো পণ্য + কেজি-গ্রাম-প্যাক সেল মোড।

চালান:   python manage.py seed_dry_fruits
বারবার চালালেও ডুপ্লিকেট হয় না (নাম/কোড ধরে update করে)।

নকশা (এই সফটওয়্যারে স্টক পূর্ণসংখ্যা, তাই বেস ইউনিট = গ্রাম):
  স্টক সবসময় গ্রামে (১৯ কেজি = 19000)। সব সেল মোড ওই গ্রাম থেকেই কমায়:
    KG    factor 1000  flat   → ১ কেজির দাম (flat_price)
    GRAM  factor 1     unit   → যত গ্রাম লিখবেন × প্রতি গ্রামের দাম
    P500  factor 500   flat   → ৫০০ গ্রাম প্যাকের দাম
    P250  factor 250   flat   → ২৫০ গ্রাম প্যাকের দাম
    P100  factor 100   flat   → ১০০ গ্রাম প্যাকের দাম
  ফলে ওয়েব POS, মোবাইল অ্যাপ ও অনলাইন শপ একই ProductSaleMode টেবিল থেকে দাম নেবে।
"""
import os
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from products.models import Category, Product, ProductSaleMode, SaleMode, Unit

D = Decimal

# (code, নাম, factor, price_type)
MODES = [
    ('kg',   'কেজি',        1000, 'flat'),
    ('g',    'গ্রাম',        1,    'unit'),
    ('p500', '৫০০ গ্রাম প্যাক', 500,  'flat'),
    ('p250', '২৫০ গ্রাম প্যাক', 250,  'flat'),
    ('p100', '১০০ গ্রাম প্যাক', 100,  'flat'),
]

# (পণ্য, ক্যাটাগরি, ক্রয় টাকা/কেজি, বিক্রয় টাকা/কেজি, স্টক কেজি, ছাড়% (১ কেজিতে) বা None)
# দাম ১০ এর গুণিতক রাখুন — কারণ প্রতি গ্রামের দাম ২ দশমিক পর্যন্ত রাখা যায়।
ITEMS = [
    ('কাঠবাদাম',       'বাদাম',      1500, 1700, 25, None),
    ('কাজুবাদাম',      'বাদাম',      1600, 1850, 20, 5),
    ('আখরোট',          'বাদাম',      1400, 1650, 15, None),
    ('চিনাবাদাম',      'বাদাম',       220,  280, 60, None),
    ('চিয়া সিড',       'বীজ',         600,  750, 18, None),
    ('ফ্ল্যাক্স সিড',    'বীজ',         250,  330, 22, None),
    ('কুমড়ার বীজ',     'বীজ',        1100, 1300, 12, 10),
    ('সূর্যমুখীর বীজ',   'বীজ',         600,  750, 14, None),
    ('সুক্কারি খেজুর',   'শুকনো ফল',    650,  800, 40, None),
    ('কিশমিশ',         'শুকনো ফল',    700,  850, 16, None),
    ('কালোজিরা',       'মসলা',        550,  700, 20, None),
    ('লিচু ফুলের মধু',   'মধু',         800, 1000, 30, None),
    ('সরিষা ফুলের মধু',  'মধু',         600,  800, 30, None),
    ('সুন্দরবনের মধু',   'মধু',        1000, 1300, 25, 5),
]


# পণ্যের ছবির পাথ (MEDIA_ROOT/inventory-products/ এর ভেতরের ফাইলের নাম)।
# নতুন ছবি দিতে: ফাইলটা media/inventory-products/ এ রাখুন, এখানে নাম বদলান,
# তারপর:  python manage.py seed_dry_fruits --update-images
IMAGE_DIR = 'inventory-products'
IMAGES = {
    'কাঠবাদাম':        'Natural_Almonds_Halal_Nutrition_Poster.png',
    'কাজুবাদাম':       'Premium_Halal_Cashew_Nuts_Poster.png',
    'আখরোট':           'Natural_Walnut_Wellness_Ad.png',
    'চিনাবাদাম':       'Halal_Business_Peanut_Harvest_Poster.png',
    'চিয়া সিড':        'Natural_Chia_Seeds_Wellness_Advertisement.png',
    'ফ্ল্যাক্স সিড':     'Natural_Flax_Seeds_Wellness_Poster.png',
    'কুমড়ার বীজ':      'Natural_Pumpkin_Seeds_Wellness_Ad.png',
    'সূর্যমুখীর বীজ':    'Halal_Business_Sunflower_Seeds_Poster.png',
    'সুক্কারি খেজুর':    'Premium_Sukkari_Dates_Advertisement.png',
    'কিশমিশ':          'Natural_Raisins_Product_Advertisement.png',
    'কালোজিরা':        'Premium_Kalojira_Herbal_Product_Poster.png',
    'লিচু ফুলের মধু':    'Lychee_Blossom_Honey_Advertisement.png',
    'সরিষা ফুলের মধু':   'Mustard_Blossom_Honey_Delight_g5asMMY.png',
    'সুন্দরবনের মধু':    'Sundarbans_Honey__Natures_Golden_Promise.png',
}


def _apply_image(product, update, force_path, missing):
    """ছবির পাথ বসায়। ফাইল media তে না থাকলে (force_path ছাড়া) বসায় না, তালিকায় রাখে।
    আগে থেকে ছবি থাকলে --update-images ছাড়া ছোঁয় না।"""
    fname = IMAGES.get(product.name)
    if not fname:
        return False
    rel = f'{IMAGE_DIR}/{fname}'
    exists = os.path.exists(os.path.join(str(settings.MEDIA_ROOT), rel))
    if not exists and not force_path:
        missing.append(rel)
        return False
    if product.image and not update:
        return False
    if product.image and product.image.name == rel:
        return False
    product.image = rel
    product.save(update_fields=['image'])
    return True


def _pack_price(per_kg, grams):
    """প্যাকের দাম: আনুপাতিক + ৩% প্যাকিং খরচ, ৫ টাকায় রাউন্ড।"""
    raw = D(per_kg) * D(grams) / D(1000) * D('1.03')
    return (raw / 5).quantize(D('1'), rounding=ROUND_HALF_UP) * 5


class Command(BaseCommand):
    help = 'বাদাম/বীজ/খেজুর/মধুর ডেমো পণ্য ও কেজি-গ্রাম-প্যাক সেল মোড যোগ করে।'

    def add_arguments(self, parser):
        parser.add_argument('--update-images', action='store_true',
                            help='আগে থেকে ছবি থাকলেও IMAGES তালিকার ছবি দিয়ে বদলাবে')
        parser.add_argument('--force-image-paths', action='store_true',
                            help='ফাইল media তে না থাকলেও পাথ বসাবে (পরে ফাইল রাখবেন)')

    @transaction.atomic
    def handle(self, *args, **opts):
        gram, _ = Unit.objects.get_or_create(name='gram')

        modes = {}
        for code, name, factor, ptype in MODES:
            m, _ = SaleMode.objects.update_or_create(
                code=code,
                defaults=dict(name=name, base_unit=gram, conversion_factor=D(factor),
                              price_type=ptype, is_active=True))
            modes[code] = m

        made = 0
        img_set, img_missing = 0, []
        for name, cat, cost_kg, sell_kg, stock_kg, off in ITEMS:
            c, _ = Category.objects.get_or_create(name=cat)
            per_g_cost = (D(cost_kg) / 1000).quantize(D('0.01'))
            per_g_sell = (D(sell_kg) / 1000).quantize(D('0.01'))
            stock_g = int(stock_kg) * 1000
            p, created = Product.objects.get_or_create(
                name=name,
                defaults=dict(category=c, unit=gram, purchase_price=per_g_cost, selling_price=per_g_sell,
                              opening_stock=stock_g, stock_qty=stock_g, alert_quantity=2000, is_active=True))
            made += int(created)
            img_set += int(_apply_image(p, opts['update_images'], opts['force_image_paths'], img_missing))

            disc = dict(discount_type='percentage', discount_value=D(off)) if off else \
                dict(discount_type=None, discount_value=None)
            prices = {
                'kg':   dict(flat_price=D(sell_kg), unit_price=None, **disc),
                'g':    dict(unit_price=per_g_sell, flat_price=None, **disc),
                'p500': dict(flat_price=_pack_price(sell_kg, 500), unit_price=None),
                'p250': dict(flat_price=_pack_price(sell_kg, 250), unit_price=None),
                'p100': dict(flat_price=_pack_price(sell_kg, 100), unit_price=None),
            }
            for code, kw in prices.items():
                kw.setdefault('discount_type', None)
                kw.setdefault('discount_value', None)
                ProductSaleMode.objects.update_or_create(
                    product=p, sale_mode=modes[code], defaults=dict(is_active=True, **kw))

        if img_missing:
            self.stdout.write(self.style.WARNING('এই ছবির ফাইল media তে নেই (রাখলে আবার চালান):\n  ' + '\n  '.join(img_missing)))
        self.stdout.write(f'ছবির পাথ বসেছে: {img_set} টা')
        call_command('seed_halal_business')   # হালাল বিজনেসের নাম/ফোন/ঠিকানা ডিফল্ট (শুধু ফাঁকা ঘর)
        self.stdout.write(self.style.SUCCESS(
            f'{made} টা নতুন পণ্য ({len(ITEMS) - made} টা আগে থেকেই ছিল), '
            f'{len(MODES)} টা সেল মোড প্রতি পণ্যে সেট হয়েছে।'))
