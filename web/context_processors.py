"""
Web software এর প্রতিটা page এ লাগে: menu, user এর নাম/ছবি, company, মেয়াদের সতর্কতা।
শুধু /app/ এর page এ কাজ করে — Django admin বা API তে কিছু যোগ করে না।
"""
from .menu import build_menu


def _initials(name):
    parts = [p for p in (name or '').split() if p]
    if not parts:
        return '?'
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def web_shell(request):
    if not request.path.startswith('/app/'):
        return {}
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    from core.models import BusinessProfile
    company = BusinessProfile.get()
    display_name = (getattr(user, 'full_name', '') or '').strip() or user.username

    expiry = None

    picture = getattr(user, 'profile_picture', None)
    logo = getattr(company, 'logo', None)
    return {
        'web_menu': build_menu(user, request.path),
        'web_user': {
            'name': display_name,
            'initials': _initials(display_name),
            'role': user.get_role_display() if hasattr(user, 'get_role_display') else '',
            'email': user.email,
            'picture': picture.url if picture else None,
        },
        'web_company': {
            'name': company.name or 'My Business',
            'logo': logo.url if logo else None,
        },
        'web_expiry': expiry,
    }
