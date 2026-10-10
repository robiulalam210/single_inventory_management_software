"""
Web login এর নিয়ম — mobile / desktop app এর login এর হুবহু একই:
  • username অথবা email + password
  • ভুল হলে "Invalid credentials", বন্ধ account হলে "User account is disabled"
  (দুটোই core.serializers.UserLoginSerializer থেকে — app যেটা ব্যবহার করে)

Web এর জন্য বাড়তি সুরক্ষা:
  • একই IP + একই username এ ৫ বার ভুল হলে ১৫ মিনিট login বন্ধ (password আন্দাজ ঠেকাতে)
"""
from django.core.cache import cache

from core.serializers import UserLoginSerializer

MAX_ATTEMPTS = 5
LOCK_SECONDS = 15 * 60


def client_ip(request):
    fwd = request.META.get('HTTP_X_FORWARDED_FOR')
    return (fwd.split(',')[0].strip() if fwd else request.META.get('REMOTE_ADDR')) or 'unknown'


def _key(request, identifier):
    return f"web-login:{client_ip(request)}:{(identifier or '').strip().lower()}"


def locked_minutes(request, identifier):
    """আটকানো থাকলে কত মিনিট বাকি, না হলে 0"""
    data = cache.get(_key(request, identifier))
    if not data or data.get('count', 0) < MAX_ATTEMPTS:
        return 0
    import time
    left = int(data['until'] - time.time())
    return max(1, (left + 59) // 60) if left > 0 else 0


def register_failure(request, identifier):
    import time
    key = _key(request, identifier)
    data = cache.get(key) or {'count': 0}
    data['count'] = data.get('count', 0) + 1
    data['until'] = time.time() + LOCK_SECONDS
    cache.set(key, data, LOCK_SECONDS)
    return MAX_ATTEMPTS - data['count']


def clear_failures(request, identifier):
    cache.delete(_key(request, identifier))


def authenticate_identifier(identifier, password):
    """
    App এর মতোই: '@' থাকলে email, না হলে username।
    ফেরত দেয় (user, None) অথবা (None, error message)
    """
    identifier = (identifier or '').strip()
    payload = {'password': password or ''}
    if '@' in identifier:
        payload['email'] = identifier
    else:
        payload['username'] = identifier

    serializer = UserLoginSerializer(data=payload)
    if serializer.is_valid():
        return serializer.validated_data['user'], None

    errors = serializer.errors
    msgs = errors.get('non_field_errors') or []
    if msgs:
        return None, str(msgs[0])
    # email এর format ভুল ইত্যাদি
    for value in errors.values():
        if value:
            return None, 'Invalid credentials' if 'email' in errors else str(value[0])
    return None, 'Invalid credentials'
