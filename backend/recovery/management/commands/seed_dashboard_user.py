from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Create or update the single seeded operator account (DASHBOARD_USERNAME / "
        "DASHBOARD_PASSWORD) used to log into the Recovery Room dashboard. This is a "
        "single-tenant app — there is no registration flow, just this one account."
    )

    def handle(self, *args, **opts):
        username = settings.DASHBOARD_USERNAME
        password = settings.DASHBOARD_PASSWORD

        if not password:
            raise CommandError(
                "DASHBOARD_PASSWORD is not set. Add it to backend/.env (see .env.example) before running this command."
            )

        User = get_user_model()
        user, created = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.is_staff = True  # convenient for /admin/ during local dev; not otherwise required by the API
        user.save()

        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} dashboard operator account '{username}'."))
