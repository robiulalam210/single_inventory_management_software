from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from core.models import BusinessProfile, StaffRole

User = get_user_model()

ROLES = [
    ('System Administrator', 'management', {'products': True, 'sales': True, 'purchases': True, 'customers': True,
                                            'suppliers': True, 'reports': True, 'users': True}),
    ('Sales Manager', 'sales', {'products': True, 'sales': True, 'customers': True, 'reports': True}),
    ('Warehouse Manager', 'warehouse', {'products': True, 'purchases': True, 'suppliers': True}),
    ('Accountant', 'accounts', {'reports': True, 'sales': True, 'purchases': True}),
    ('Support Staff', 'support', {'customers': True, 'sales': True}),
]


class Command(BaseCommand):
    help = 'Setup initial data: business profile, default staff roles, optional superuser'

    def add_arguments(self, parser):
        parser.add_argument('--create-superuser', action='store_true', help='Create a superuser account')
        parser.add_argument('--username', type=str, default='admin')
        parser.add_argument('--email', type=str, default='admin@example.com')
        parser.add_argument('--password', type=str, default='12345678')

    def handle(self, *args, **options):
        BusinessProfile.get()
        self.stdout.write(self.style.SUCCESS('Business profile ready.'))
        for name, role_type, perms in ROLES:
            _, created = StaffRole.objects.get_or_create(
                name=name, defaults={'role_type': role_type, 'default_permissions': perms})
            self.stdout.write(f"{'Created' if created else 'Exists'}: {name}")
        if options['create_superuser']:
            user, created = User.objects.get_or_create(
                username=options['username'],
                defaults={'email': options['email'], 'role': User.Role.SUPER_ADMIN,
                          'is_staff': True, 'is_superuser': True})
            user.role = User.Role.SUPER_ADMIN
            user.is_staff = user.is_superuser = True
            if created:
                user.set_password(options['password'])
            user.save()
            self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} superuser: {user.username}"))
        self.stdout.write(self.style.SUCCESS('Setup complete.'))
