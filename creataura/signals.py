from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Deposit
from .referrals import sync_referral_bonus


@receiver(post_save, sender=Deposit)
def referral_bonus_on_deposit(sender, instance, **kwargs):
    sync_referral_bonus(instance)