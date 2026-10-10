from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Create a superuser without requiring a company'

    def handle(self, *args, **options):
        username = input("Username: ")
        email = input("Email: ")
        password = input("Password: ")
        
        # Create superuser with SUPER_ADMIN role
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            role=User.Role.SUPER_ADMIN
        )
        
        self.stdout.write(self.style.SUCCESS(f'Superuser {username} created successfully!'))