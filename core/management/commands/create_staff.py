# core/management/commands/create_staff.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import StaffRole, User, Staff

User = get_user_model()

class Command(BaseCommand):
    help = 'Create staff users with specific roles'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, required=True, help='Username')
        parser.add_argument('--email', type=str, required=True, help='Email')
        parser.add_argument('--password', type=str, required=True, help='Password')
        parser.add_argument('--role', type=str, required=True, help='Staff role name')
        parser.add_argument('--first-name', type=str, default='', help='First name')
        parser.add_argument('--last-name', type=str, default='', help='Last name')

    def handle(self, *args, **options):
        try:
            # Get role
            role = StaffRole.objects.get(name=options['role'])
            
            # Create user
            if User.objects.filter(username=options['username']).exists():
                self.stdout.write(
                    self.style.WARNING(f'User already exists: {options["username"]}')
                )
                return

            # Determine user role based on staff role
            user_role = self._get_user_role_from_staff_role(role)
            
            user = User.objects.create_user(
                username=options['username'],
                email=options['email'],
                password=options['password'],
                role=user_role,
                first_name=options['first_name'],
                last_name=options['last_name'],
                is_staff=True
            )

            # Create staff profile
            staff = Staff.objects.create(
                user=user,
                role=role,
                designation=role.name,
                employment_type=Staff.EmploymentType.FULL_TIME
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created staff user: {user.username} '
                    f'with role: {role.name}'
                )
            )

        except StaffRole.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Role not found: {options["role"]}')
            )

    def _get_user_role_from_staff_role(self, staff_role):
        """Map StaffRole to User.Role"""
        role_mapping = {
            'System Administrator': User.Role.SUPER_ADMIN,
            'Sales Manager': User.Role.MANAGER,
            'Warehouse Manager': User.Role.MANAGER,
            'Accountant': User.Role.MANAGER,
            'Support Staff': User.Role.STAFF,
        }
        return role_mapping.get(staff_role.name, User.Role.STAFF)