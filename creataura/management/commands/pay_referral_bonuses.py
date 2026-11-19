from django.core.management.base import BaseCommand

from creataura.models import Deposit
from creataura.referrals import sync_referral_bonus


class Command(BaseCommand):
    help = "Create referral bonuses for deposits that were approved before this feature."

    def handle(self, *args, **options):
        created = 0
        for deposit in Deposit.objects.filter(status="approved").order_by("date_created"):
            bonus = sync_referral_bonus(deposit)
            if bonus and bonus.deposit_id == deposit.pk:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Referral bonuses now linked: {created}"))