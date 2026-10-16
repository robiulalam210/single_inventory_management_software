"""
{% icon "name" %} — বাইরের কোনো icon library ছাড়া হালকা inline SVG।
সব icon 24×24, রেখা-ভিত্তিক (stroke), রং লেখার রং থেকে নেয় (currentColor)।
"""
from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

_P = {
    'dashboard': '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    'cart': '<circle cx="9" cy="20" r="1.4"/><circle cx="18" cy="20" r="1.4"/><path d="M2.5 3.5h2.6l2.4 11.2a1.5 1.5 0 0 0 1.5 1.2h8.4a1.5 1.5 0 0 0 1.5-1.1l1.6-6.3H6.1"/>',
    'receipt': '<path d="M5 2.8v18.4l2.3-1.4 2.3 1.4 2.4-1.4 2.3 1.4 2.4-1.4 2.3 1.4V2.8l-2.3 1.4-2.4-1.4-2.3 1.4-2.4-1.4-2.3 1.4z"/><path d="M8.5 9h7M8.5 13h7"/>',
    'truck': '<path d="M2.5 6.5h11v9h-11z"/><path d="M13.5 9.5h4l3 3.2v2.8h-7"/><circle cx="7" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/>',
    'box': '<path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5 12 12l8.5-4.5M12 12v9"/>',
    'wallet': '<path d="M3.5 7.5a2 2 0 0 1 2-2h12v3"/><rect x="3.5" y="7.5" width="17" height="12" rx="2"/><path d="M16 13.5h1.5"/>',
    'users': '<circle cx="9" cy="8" r="3.2"/><path d="M3 19.5c.6-3.2 3-5 6-5s5.4 1.8 6 5"/><path d="M16 4.9a3.2 3.2 0 0 1 0 6.2M18 14.8c1.6.6 2.7 2.2 3 4.7"/>',
    'store': '<path d="M4 9.5V20h16V9.5"/><path d="M2.8 9.5 4.6 4h14.8l1.8 5.5a2.6 2.6 0 0 1-4.6 1.6 2.7 2.7 0 0 1-4.6 0 2.7 2.7 0 0 1-4.6 0A2.6 2.6 0 0 1 2.8 9.5z"/><path d="M9.5 20v-5h5v5"/>',
    'expense': '<rect x="2.5" y="6" width="19" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 9.5v5M18 9.5v5"/>',
    'return': '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    'chart': '<path d="M3.5 20.5h17"/><rect x="5" y="11" width="3" height="7" rx="1"/><rect x="10.5" y="6" width="3" height="12" rx="1"/><rect x="16" y="13.5" width="3" height="4.5" rx="1"/>',
    'settings': '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    'income': '<path d="M3 17 9 11l4 4 8-8"/><path d="M15 7h6v6"/>',
    'transfer': '<path d="M4 8h14l-3.5-3.5M20 16H6l3.5 3.5"/>',
    'shield': '<path d="M12 2.8 4.5 5.6v5.6c0 4.6 3.2 8.6 7.5 10 4.3-1.4 7.5-5.4 7.5-10V5.6z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
    'logout': '<path d="M9 20.5H5.5a2 2 0 0 1-2-2v-13a2 2 0 0 1 2-2H9"/><path d="M16 16.5 20.5 12 16 7.5M20.5 12H9"/>',
    'user': '<circle cx="12" cy="8" r="4"/><path d="M4 20.5c.8-3.6 4-6 8-6s7.2 2.4 8 6"/>',
    'lock': '<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
    'mail': '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 6.5 8.5 6.5 8.5-6.5"/>',
    'eye': '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    'eye-off': '<path d="M10.6 5.6A9.9 9.9 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-2.7 3.5M6.6 6.6A16.6 16.6 0 0 0 2.5 12S6 18.5 12 18.5a9.6 9.6 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2M3 3l18 18"/>',
    'menu': '<path d="M3.5 6.5h17M3.5 12h17M3.5 17.5h17"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'chevron-right': '<path d="m9 6 6 6-6 6"/>',
    'x': '<path d="M6 6l12 12M18 6 6 18"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'trash': '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    'coins': '<circle cx="9" cy="9" r="6"/><path d="M15.1 9.6A6 6 0 1 1 9.6 15.1"/><path d="M9 6.5v5M7 8h3a1 1 0 0 1 0 2H8a1 1 0 0 0 0 2h3"/>',
    'alert': '<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.2v.3"/>',
    'check': '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    'check-circle': '<circle cx="12" cy="12" r="9"/><path d="m8 12.3 2.8 2.8L16.5 9.5"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.8v.3"/>',
    'building': '<rect x="4.5" y="3" width="15" height="18" rx="1.5"/><path d="M9 7.5h1.5M13.5 7.5H15M9 11.5h1.5M13.5 11.5H15M10.5 21v-4.5h3V21"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'key': '<circle cx="8" cy="15" r="4"/><path d="m10.8 12.2 8.7-8.7M16.5 6.5l2.5 2.5M14.5 8.5l2 2"/>',
    'sparkle': '<path d="M12 3.5 13.8 9 19.5 10.8 13.8 12.6 12 18.2 10.2 12.6 4.5 10.8 10.2 9z"/><path d="M19 3.5v3M17.5 5h3"/>',
    'rocket': '<path d="M12.5 15.5 8.5 11.5c1.5-4.5 5-7.5 11-8-.5 6-3.5 9.5-8 11z"/><path d="M8.5 11.5 5 11l2.5-3.5h4M12.5 15.5l.5 3.5 3.5-2.5v-4"/><path d="M6 15.5c-1.5.5-2.5 2.5-2.5 5 2.5 0 4.5-1 5-2.5"/>',
    'arrow-right': '<path d="M4.5 12h15M14 6.5l5.5 5.5-5.5 5.5"/>',
    'refresh': '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 3.5V8h4.5"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20.5V16h-4.5"/>',
    'search': '<circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4.5-4.5"/>',
    'calendar': '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    'printer': '<path d="M7 9V3.5h10V9"/><rect x="3.5" y="9" width="17" height="8" rx="2"/><path d="M7 14.5h10v6H7z"/>',
    'chevron-left': '<path d="m15 6-6 6 6 6"/>',
    'filter-x': '<path d="M3.5 4.5h17l-6.5 8v6l-4 2v-8z"/>',
    'phone': '<path d="M6.5 3.5h3l1.5 4-2 1.5a11 11 0 0 0 6 6l1.5-2 4 1.5v3a2 2 0 0 1-2 2A16.5 16.5 0 0 1 4.5 5.5a2 2 0 0 1 2-2z"/>',
    'globe': '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>',
    'pencil': '<path d="M14.5 5.5l4 4M4 20l1-4.5L15.5 5a2 2 0 0 1 2.8 0l.7.7a2 2 0 0 1 0 2.8L8.5 19z"/>',
    'ruler': '<rect x="2.5" y="8" width="19" height="8" rx="1.5"/><path d="M6.5 8v3M10 8v4M13.5 8v3M17 8v4"/>',
    'eye-dim': '<path d="M3 3l18 18M10.6 6.1A9.8 9.8 0 0 1 12 6c5 0 8.5 4.5 9.5 6a17 17 0 0 1-2.6 3.2M6.6 7.6A16.6 16.6 0 0 0 2.5 12c1 1.5 4.5 6 9.5 6a9 9 0 0 0 4.2-1"/>',
}


@register.simple_tag
def icon(name, size=20, cls=''):
    paths = _P.get(name, _P['info'])
    return format_html(
        '<svg class="ic {}" width="{}" height="{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>',
        cls, size, size, mark_safe(paths),
    )
