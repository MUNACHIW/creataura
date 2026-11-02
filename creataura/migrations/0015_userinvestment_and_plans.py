from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


def seed_investment_plans(apps, schema_editor):
    InvestmentPlan = apps.get_model("creataura", "InvestmentPlan")
    plans = [
        ("Beginner Plan", "500", "500", "25000", "1.5", "10.5", "1", 60),
        ("Standard Plan", "25000", "25000", "100000", "2.5", "17.5", "10", 60),
        ("Business Pro Plan", "101000", "101000", "1000000", "3.1", "21.7", "15", 60),
    ]
    for name, amount, minimum, maximum, daily, weekly, gift, duration in plans:
        InvestmentPlan.objects.update_or_create(
            name=name,
            defaults={
                "amount": Decimal(amount),
                "minimum_deposit": Decimal(minimum),
                "maximum_deposit": Decimal(maximum),
                "daily_roi": Decimal(daily),
                "weekly_roi": Decimal(weekly),
                "gift_bonus": Decimal(gift),
                "duration_days": duration,
                "is_active": True,
            },
        )


def remove_seeded_plans(apps, schema_editor):
    InvestmentPlan = apps.get_model("creataura", "InvestmentPlan")
    InvestmentPlan.objects.filter(
        name__in=["Beginner Plan", "Standard Plan", "Business Pro Plan"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("creataura", "0014_userprofile_notifications"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserInvestment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, validators=[MinValueValidator(Decimal("0.01"))])),
                ("status", models.CharField(choices=[("active", "Active"), ("completed", "Completed"), ("cancelled", "Cancelled")], default="active", max_length=20)),
                ("date_created", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="user_investments", to="creataura.investmentplan")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="investments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "User investment",
                "verbose_name_plural": "User investments",
                "ordering": ["-date_created"],
            },
        ),
        migrations.RunPython(seed_investment_plans, remove_seeded_plans),
    ]
