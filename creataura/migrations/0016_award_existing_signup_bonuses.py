from django.db import migrations
from decimal import Decimal


def award_signup_bonuses(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Bonus = apps.get_model("creataura", "Bonus")

    for user in User.objects.all():
        bonus, created = Bonus.objects.get_or_create(
            user_id=user.id,
            amount=Decimal("5.00"),
            plan_narration="SignUp Bonus",
        )
        if created:
            Bonus.objects.filter(pk=bonus.pk).update(date_created=user.date_joined)


def remove_signup_bonuses(apps, schema_editor):
    Bonus = apps.get_model("creataura", "Bonus")
    Bonus.objects.filter(plan_narration="SignUp Bonus").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("creataura", "0015_userinvestment_and_plans"),
    ]

    operations = [
        migrations.RunPython(award_signup_bonuses, remove_signup_bonuses),
    ]
