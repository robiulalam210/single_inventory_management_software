# core/management/commands/check_user.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Check user details'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default='admin', help='Username to check')

    def handle(self, *args, **options):
        username = options['username']
        
        try:
            user = User.objects.get(username=username)
            self.stdout.write(f"User: {user.username}")
            self.stdout.write(f"Role: {user.role}")
            self.stdout.write(f"Is Superuser: {user.is_superuser}")
            self.stdout.write(f"Is Staff: {user.is_staff}")
            self.stdout.write(f"Email: {user.email}")
            
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User '{username}' not found"))