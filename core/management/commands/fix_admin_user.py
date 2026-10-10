# core/management/commands/fix_admin.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Company, StaffRole, Staff

User = get_user_model()

class Command(BaseCommand):
    help = 'Fix admin user role and company'

    def handle(self, *args, **options):
        self.stdout.write('Fixing admin user...')
        
        try:
            # Get or create company
            company, created = Company.objects.get_or_create(
                name="Super Admin Company",
                defaults={
                    'company_code': 'SUPER001',
                    'is_active': True,
                    'plan_type': Company.PlanType.PREMIUM,
                }
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created company: {company.name}'))
            else:
                self.stdout.write(self.style.WARNING(f'Company exists: {company.name}'))

            # Get or create System Administrator role
            admin_role, created = StaffRole.objects.get_or_create(
                name='System Administrator',
                defaults={
                    'role_type': 'management',
                    'default_permissions': {
                        'products': True, 'sales': True, 'purchases': True,
                        'customers': True, 'suppliers': True, 'reports': True, 'users': True,
                    }
                }
            )

            # Get the admin user
            try:
                user = User.objects.get(username='admin')
                self.stdout.write(self.style.WARNING('Found existing admin user, updating...'))
                
                # Update user
                user.role = User.Role.SUPER_ADMIN
                user.company = company
                user.is_staff = True
                user.is_superuser = True
                user.email = 'admin@erp.com'
                user.set_password('12345678')  # Reset password to ensure it's known
                user.save()
                
                self.stdout.write(self.style.SUCCESS('Updated admin user'))
                
            except User.DoesNotExist:
                # Create new admin user
                user = User.objects.create_superuser(
                    username='admin',
                    email='admin@erp.com',
                    password='12345678',
                    company=company,
                    role=User.Role.SUPER_ADMIN
                )
                self.stdout.write(self.style.SUCCESS('Created new admin user'))

            # Create staff profile if it doesn't exist
            if not hasattr(user, 'staff_profile'):
                Staff.objects.create(
                    user=user,
                    company=company,
                    role=admin_role,
                    designation='System Administrator',
                    is_main_user=True,
                    employment_type=Staff.EmploymentType.FULL_TIME
                )
                self.stdout.write(self.style.SUCCESS('Created staff profile'))
            else:
                self.stdout.write(self.style.WARNING('Staff profile already exists'))

            # Verify the fix
            self.stdout.write("\n" + "="*50)
            self.stdout.write("VERIFICATION:")
            self.stdout.write(f"Username: {user.username}")
            self.stdout.write(f"Role: {user.role}")
            self.stdout.write(f"Company: {user.company.name if user.company else 'None'}")
            self.stdout.write(f"Is Superuser: {user.is_superuser}")
            self.stdout.write(f"Is Staff: {user.is_staff}")
            self.stdout.write("="*50)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))