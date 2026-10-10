# reports/reminder_utils.py
"""রিমাইন্ডারের ছোট, Django-মুক্ত সহায়ক — ফোন নম্বর ঠিক করা, টাকার লেখা, বার্তার ছাঁচ বসানো।"""
import re
from decimal import Decimal

DEFAULT_TEMPLATE = (
    'আসসালামু আলাইকুম {name}, {shop} থেকে জানাচ্ছি — আপনার কাছে মোট ৳{amount} বাকি আছে। '
    'সুবিধামতো সময়ে পরিশোধ করার অনুরোধ রইল। ধন্যবাদ। {phone}'
).strip()

MAX_INVOICES_IN_MESSAGE = 5
MAX_ROWS = 1000


def normalize_phone(raw):
    """
    বাংলাদেশের নম্বর → আন্তর্জাতিক রূপ (শুধু অঙ্ক, '+' ছাড়া), যেমন 8801712345678।
    চেনা না গেলে None — তখন লিংক বানানো হয় না।
    """
    digits = re.sub(r'\D', '', str(raw or ''))
    if not digits:
        return None
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('8801') and len(digits) == 13:
        return digits
    if digits.startswith('01') and len(digits) == 11:
        return '88' + digits
    if digits.startswith('1') and len(digits) == 10:
        return '880' + digits
    # অন্য দেশের নম্বর হতে পারে (দেশকোড সহ) — যুক্তিসঙ্গত দৈর্ঘ্য হলে রাখি
    if 10 <= len(digits) <= 15 and not digits.startswith('0'):
        return digits
    return None


def money(v):
    """১২৫০ → '1,250'; ১২৫০.৫ → '1,250.50'"""
    d = Decimal(str(v or 0))
    return f'{d:,.0f}' if d == d.to_integral_value() else f'{d:,.2f}'


def render_message(template, *, name, amount, shop, phone, invoices, days):
    values = {'name': name, 'amount': money(amount), 'shop': shop, 'phone': phone, 'invoices': invoices, 'days': str(days)}
    out = template
    for k, v in values.items():
        out = out.replace('{' + k + '}', v or '')
    return re.sub(r'[ \t]{2,}', ' ', out).strip()
