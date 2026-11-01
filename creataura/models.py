from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="creataura_profile",
    )
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=40)
    bitcoin_address = models.CharField(max_length=150)
    country = models.CharField(max_length=100)
    referral_id = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.full_name
