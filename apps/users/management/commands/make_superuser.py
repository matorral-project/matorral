from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Make an existing user a staff member and superuser by email"

    def add_arguments(self, parser):
        parser.add_argument("email", type=str, help="Email address of the user to promote")

    def handle(self, *args, **options):
        User = get_user_model()
        email = options["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f'No user found with email "{email}"') from None

        user.is_staff = True
        user.is_superuser = True
        user.save(update_fields=["is_staff", "is_superuser"])

        self.stdout.write(self.style.SUCCESS(f'User "{email}" is now a staff member and superuser.'))
