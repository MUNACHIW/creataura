from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from creataura.profits import credit_due_profits
from creataura.verification import send_simple_email


class Command(BaseCommand):
    help = "Credit daily ROI profit (including back-pay) for active investments."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be credited without writing anything.",
        )
        parser.add_argument("--user", help="Only this username.")

    def handle(self, *args, **options):
        user = None
        if options["user"]:
            user = User.objects.get(username=options["user"])

        dry = options["dry_run"]
        result = credit_due_profits(user=user, notify=not dry, dry_run=dry)

        prefix = "[DRY RUN] Would credit" if dry else "Credited"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix} {result['days']} profit day(s) totalling "
                f"${result['amount']:,.2f}; "
                f"{result['completed']} investment(s) finished."
            )
        )

    def _notify_profit(self, investment, days, daily_profit):
        profile = getattr(investment.user, "creataura_profile", None)
        if not (
            profile and profile.email_profit_notification and investment.user.email
        ):
            return
        total = daily_profit * days
        send_simple_email(
            investment.user.email,
            "You received investment profit",
            f"${total:,.2f} profit from your {investment.plan.name} "
            "was added to your account.",
        )