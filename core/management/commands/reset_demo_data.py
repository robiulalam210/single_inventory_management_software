# core/management/commands/reset_demo_data.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Company, StaffRole, User, Staff
from datetime import date

User = get_user_model()

class Command(BaseCommand):
    help = 'Reset demo data for testing'

    def handle(self, *args, **options):
        self.stdout.write('Resetting demo data...')

        # Create demo companies
        demo_companies = [
            {
                'name': 'Tech Solutions Inc',
                'company_code': 'TECH001',
                'address': '123 Tech Park, Silicon Valley',
                'phone': '+1-555-0101',
                'email': 'info@techsolutions.com',
                'plan_type': Company.PlanType.PREMIUM,
                'max_users': 20,
                'max_products': 5000,
                'max_branches': 5
            },
            {
                'name': 'Global Trading Co',
                'company_code': 'GLOB001',
                'address': '456 Business District, New York',
                'phone': '+1-555-0102',
                'email': 'contact@globaltrading.com',
                'plan_type': Company.PlanType.STANDARD,
                'max_users': 10,
                'max_products': 2000,
                'max_branches': 3
            }
        ]

        for company_data in demo_companies:
            company, created = Company.objects.get_or_create(
                name=company_data['name'],
                defaults=company_data
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Created company: {company.name}')
                )

        # Create demo users for each company
        demo_users = [
            {
                'username': 'tech_admin',
                'email': 'admin@techsolutions.com',
                'password': 'tech123',
                'first_name': 'John',
                'last_name': 'Smith',
                'company': 'Tech Solutions Inc',
                'staff_role': 'System Administrator',
                'user_role': User.Role.SUPER_ADMIN
            },
            {
                'username': 'tech_sales',
                'email': 'sales@techsolutions.com',
                'password': 'sales123',
                'first_name': 'Sarah',
                'last_name': 'Johnson',
                'company': 'Tech Solutions Inc',
                'staff_role': 'Sales Manager',
                'user_role': User.Role.MANAGER
            },
            {
                'username': 'global_admin',
                'email': 'admin@globaltrading.com',
                'password': 'global123',
                'first_name': 'Michael',
                'last_name': 'Brown',
                'company': 'Global Trading Co',
                'staff_role': 'System Administrator',
                'user_role': User.Role.SUPER_ADMIN
            }
        ]

        for user_data in demo_users:
            try:
                company = Company.objects.get(name=user_data['company'])
                staff_role = StaffRole.objects.get(name=user_data['staff_role'])
                
                if not User.objects.filter(username=user_data['username']).exists():
                    # Create user
                    user = User.objects.create_user(
                        username=user_data['username'],
                        email=user_data['email'],
                        password=user_data['password'],
                        first_name=user_data['first_name'],
                        last_name=user_data['last_name'],
                        company=company,
                        role=user_data['user_role'],
                        is_staff=True
                    )
                    
                    # Create staff profile
                    Staff.objects.create(
                        user=user,
                        company=company,
                        role=staff_role,
                        designation=staff_role.name,
                        employment_type=Staff.EmploymentType.FULL_TIME,
                        is_main_user=(user_data['user_role'] == User.Role.SUPER_ADMIN)
                    )
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'Created user: {user_data["username"]}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'User already exists: {user_data["username"]}')
                    )
                    
            except (Company.DoesNotExist, StaffRole.DoesNotExist) as e:
                self.stdout.write(
                    self.style.ERROR(f'Error creating user {user_data["username"]}: {str(e)}')
                )

        self.stdout.write(
            self.style.SUCCESS('Demo data reset completed!')
        )