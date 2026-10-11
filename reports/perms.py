# reports/perms.py
"""web এর `has_perm` এর একই নিয়ম (web/views.py) — API তেও permission মানার জন্য।"""


def user_has_perm(user, module, action='view'):
    if getattr(user, 'is_superuser', False):
        return True
    perms = user.get_permissions() if hasattr(user, 'get_permissions') else {}
    return bool((perms.get(module) or {}).get(action))
