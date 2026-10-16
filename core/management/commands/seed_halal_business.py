"""হালাল বিজনেস (চাঁদপুর) এর তথ্য BusinessProfile ও ShopSettings এ ডিফল্ট হিসেবে বসায়।

চালান:        python manage.py seed_halal_business
জোর করে বদলাতে: python manage.py seed_halal_business --force   (আগের লেখা মুছে নতুন তথ্য বসবে)
শুধু ফাঁকা ঘর (বা "My Business") পূরণ হয়; আপনার নিজের লেখা তথ্য --force ছাড়া বদলায় না।
"""
from django.core.management.base import BaseCommand

from core.models import BusinessProfile
from shop.models import ShopSettings

NAME = 'হালাল বিজনেস'
PHONE = '01834-419706'
WHATSAPP_PLAIN = '8801757770163'
EMAIL = 'kazisorrowar71@gmail.com'
ADDRESS = 'মজুমদার মার্কেট, ফকির বাজার, ফরিদগঞ্জ, চাঁদপুর'
TAGLINE = 'খাঁটি স্বাদের বিশ্বস্ত ঠিকানা'

BUSINESS = dict(name=NAME, tagline=TAGLINE, phone=PHONE, whatsapp='+880 1757-770163',
                email=EMAIL, address=ADDRESS)

SHOP = dict(
    shop_name=NAME,
    tagline=TAGLINE,
    announcement='সারাদেশে কুরিয়ারের মাধ্যমে পণ্য পাঠানো হয়',
    hero_title='সুন্দরবনের ১০০% খাঁটি মধু, বাদাম ও সুক্কারি খেজুর',
    hero_subtitle='রাজশাহীর খাঁটি খেজুরের গুড়, চিয়া সিড, কালোজিরা — সরাসরি আমাদের কাছ থেকে',
    hero_button_text='এখনই কিনুন',
    about_title='আমাদের সম্পর্কে',
    about_text=('হালাল বিজনেস — সুন্দরবনের ১০০% খাঁটি মধু, হানিনাট, খেজুর, খেজুরের গুড়, বাদাম, মসলা, '
                'চিয়া সিড, কালোজিরা ও খাঁটি সরিষার তেল পাওয়া যায়। প্রোঃ সারোয়ার কাজী।'),
    phone=PHONE,
    whatsapp=WHATSAPP_PLAIN,
    email=EMAIL,
    address=ADDRESS,
    opening_hours='সবসময় খোলা',
    delivery_note='সারাদেশে কুরিয়ারের মাধ্যমে ডেলিভারি',
    payment_note='ক্যাশ অন ডেলিভারি',
)


def _fill(obj, values, force):
    changed = []
    for field, value in values.items():
        cur = getattr(obj, field, '')
        if force or not cur or cur == 'My Business':
            setattr(obj, field, value)
            changed.append(field)
    if changed:
        obj.save()
    return changed


class Command(BaseCommand):
    help = 'হালাল বিজনেসের নাম, ফোন, ঠিকানা ইত্যাদি ডিফল্ট হিসেবে বসায়।'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='আগের তথ্য বদলে ফেলবে')

    def handle(self, *args, **opts):
        force = opts['force']
        b = _fill(BusinessProfile.get(), BUSINESS, force)
        s = _fill(ShopSettings.load(), SHOP, force)
        self.stdout.write(self.style.SUCCESS(f'BusinessProfile: {len(b)} ঘর, ShopSettings: {len(s)} ঘর আপডেট হয়েছে।'))
