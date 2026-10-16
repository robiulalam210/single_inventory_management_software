"""
ব্যবসার মানুষ (Staff / Users) — তৈরি, বদল, বন্ধ করার নিয়ম। UserViewSet এগুলো ব্যবহার করে।

আগের সমস্যা (ঠিক করা হয়েছে):
  • role, is_superuser সবই লেখা যেত — users.edit থাকা যেকোনো staff নিজেকে SUPER_ADMIN
    বানাতে পারত।
  • password না দিলে 'password123' বসে যেত।
  • role বদলালে permission পুরনোই থেকে যেত (STAFF → ADMIN করেও কিছু করতে পারত না, উল্টোটাও)।
  • user মুছে ফেললে তার করা বিক্রি/রসিদে "কে করেছে" হারিয়ে যেত — এখন মোছার বদলে বন্ধ হয়।

নিয়ম:
  • কেউ নিজের চেয়ে উঁচু বা সমান পদের কাউকে বানাতে/বদলাতে পারে না — শুধু Admin আরেকজন Admin কে পারে।
  • SUPER_ADMIN এখান থেকে কখনো তৈরি হয় না (সেটা `createsuperuser` / setup_business কমান্ডের কাজ)।
  • নিজের role বদলানো বা নিজেকে বন্ধ করা যায় না; শেষ চালু Admin কে বন্ধ/নামানো যায় না।
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email

User = get_user_model()

RANK = {'VIEWER': 0, 'STAFF': 1, 'MANAGER': 2, 'ADMIN': 3, 'SUPER_ADMIN': 4}
ASSIGNABLE = ('ADMIN', 'MANAGER', 'STAFF', 'VIEWER')


def is_admin(u):
    return getattr(u, 'role', '') in ('ADMIN', 'SUPER_ADMIN') or getattr(u, 'is_superuser', False)


def can_touch(actor, target):
    """actor কি target কে বদলাতে পারে?"""
    if actor.role == 'SUPER_ADMIN' or actor.is_superuser:
        return True
    if target.role == 'SUPER_ADMIN':
        return False
    if actor.pk == target.pk:
        return True
    if actor.role == 'ADMIN':
        return True
    return RANK.get(target.role, 0) < RANK.get(actor.role, 0)


def can_assign(actor, role):
    if role not in ASSIGNABLE:
        return False
    if is_admin(actor):
        return True
    return RANK[role] < RANK.get(actor.role, 0)


def _clean(v):
    return v.strip() if isinstance(v, str) else (v or '')


def active_admins(exclude=None):
    qs = User.objects.filter(role='ADMIN', is_active=True)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.count()


def validate_person(data, actor, instance=None):
    """(cleaned, errors) — instance থাকলে শুধু পাঠানো ঘরগুলো দেখে"""
    out, err = {}, {}
    new = instance is None

    def has(k):
        return new or k in data

    if has('first_name'):
        v = _clean(data.get('first_name'))[:150]
        if not v:
            err['first_name'] = 'Enter their name.'
        out['first_name'] = v
    if has('last_name'):
        out['last_name'] = _clean(data.get('last_name'))[:150]
    if has('phone'):
        out['phone'] = _clean(data.get('phone'))[:20] or None
    if has('username'):
        v = _clean(data.get('username'))
        if not v:
            err['username'] = 'Choose a username to sign in with.'
        elif len(v) < 3 or len(v) > 150 or not all(ch.isalnum() or ch in '._-' for ch in v):
            err['username'] = 'Use 3+ letters, numbers, dot, dash or underscore — no spaces.'
        elif User.objects.filter(username__iexact=v).exclude(pk=getattr(instance, 'pk', None)).exists():
            err['username'] = 'This username is taken.'
        else:
            out['username'] = v
    if has('email'):
        v = _clean(data.get('email'))
        if v:
            try:
                validate_email(v)
                # email দিয়েও login হয় — একই email দুজনের হলে login ভেঙে যায়
                if User.objects.filter(email__iexact=v).exclude(pk=getattr(instance, 'pk', None)).exists():
                    err['email'] = 'Another user already has this email.'
                else:
                    out['email'] = v
            except DjangoValidationError:
                err['email'] = 'Enter a valid email address.'
        else:
            out['email'] = ''
    if has('role'):
        role = data.get('role') or ('STAFF' if new else None)
        if role not in ASSIGNABLE:
            err['role'] = 'Pick a role.'
        elif not can_assign(actor, role) and not (instance is not None and instance.role == role):
            err['role'] = "You can't give someone this role."
        else:
            out['role'] = role
    if new or data.get('password'):
        pw = data.get('password') or ''
        if not pw:
            err['password'] = 'Set a password.'
        else:
            try:
                validate_password(pw, user=User(username=out.get('username') or getattr(instance, 'username', ''),
                                                email=out.get('email') or ''))
                out['password'] = pw
            except DjangoValidationError as e:
                err['password'] = ' '.join(e.messages)
    if 'is_active' in data and not new:
        out['is_active'] = bool(data.get('is_active'))
    return out, err


def check_change(actor, instance, out):
    """role/চালু-বন্ধ বদলের ব্যবসায়িক নিয়ম; সমস্যা থাকলে বার্তা ফেরত দেয়"""
    if actor.pk == instance.pk:
        if 'role' in out and out['role'] != instance.role:
            return "You can't change your own role."
        if out.get('is_active') is False:
            return "You can't turn off your own account."
    demoting = instance.role == 'ADMIN' and 'role' in out and out['role'] != 'ADMIN'
    disabling = instance.role == 'ADMIN' and out.get('is_active') is False and instance.is_active
    if (demoting or disabling) and active_admins(exclude=instance) == 0:
        return f'{instance.username} is the only active admin. Make someone else admin first.'
    return None


def person_row(u, actor=None):
    perms = u.get_permissions()
    perms.pop('permission_source', None)
    return {
        'id': u.id, 'username': u.username, 'email': u.email or '', 'phone': u.phone or '',
        'first_name': u.first_name, 'last_name': u.last_name,
        'name': (u.get_full_name() or '').strip() or u.username,
        'role': u.role, 'is_active': u.is_active, 'permission_source': u.permission_source,
        'last_login': u.last_login.isoformat() if u.last_login else None,
        'date_joined': u.date_joined.isoformat() if u.date_joined else None,
        'permissions': perms,
        'is_me': bool(actor and actor.pk == u.pk),
        'can_edit': bool(actor and can_touch(actor, u)),
        # update serializer এর নিয়ম: Admin অন্য Admin এর permission বদলাতে পারে না; Admin এর সব থাকে
        'can_edit_permissions': bool(actor and is_admin(actor) and u.role not in ('ADMIN', 'SUPER_ADMIN')),
    }
