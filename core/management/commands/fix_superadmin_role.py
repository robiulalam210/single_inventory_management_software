from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "যাদের role ভুলে STAFF দেখাচ্ছে সেই সুপার অ্যাডমিনকে SUPER_ADMIN করে: manage.py fix_superadmin_role <username>"

    def add_arguments(self, parser):
        parser.add_argument('username')

    def handle(self, *args, **opts):
        User = get_user_model()
        u = User.objects.get(username=opts['username'])
        u.role = User.Role.SUPER_ADMIN
        u.save()
        self.stdout.write(self.style.SUCCESS(f'{u.username} এখন Super Admin'))
