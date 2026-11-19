from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction

from .models import ReferralBonus


def sync_referral_bonus(deposit):
    """Create, restore or cancel the referral bonus for one deposit.
    Safe to call repeatedly."""
    referred = deposit.user
    profile = getattr(referred, "creataura_profile", None)
    if not profile or not profile.referral_id:
        return None

    referrer = User.objects.filter(username__iexact=profile.referral_id).first()
    if not referrer or referrer.pk == referred.pk:
        return None

    with transaction.atomic():
        existing = ReferralBonus.objects.filter(deposit=deposit).first()

        if deposit.status == "approved":
            if existing:
                if existing.status == "cancelled":
                    existing.status = "paid"
                    existing.save(update_fields=["status"])
                return existing

            if getattr(settings, "REFERRAL_FIRST_DEPOSIT_ONLY", True):
                already_paid = ReferralBonus.objects.filter(
                    referred_user=referred
                ).exclude(status="cancelled").exists()
                if already_paid:
                    return None

            percent = Decimal(str(getattr(settings, "REFERRAL_PERCENT", 5)))
            amount = (deposit.amount * percent / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if amount <= 0:
                return None
            return ReferralBonus.objects.create(
                referrer=referrer,
                referred_user=referred,
                deposit=deposit,
                amount=amount,
                percentage=percent,
                status="paid",
            )

        # Deposit no longer approved (e.g. changed to rejected): take the bonus back
        if existing and existing.status == "paid":
            existing.status = "cancelled"
            existing.save(update_fields=["status"])
        return existing