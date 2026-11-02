from django.db import migrations, models


def remove_duplicate_signup_bonuses(apps, schema_editor):
    Bonus = apps.get_model("creataura", "Bonus")
    seen = set()
    duplicate_ids = []

    for bonus in Bonus.objects.filter(
        amount="5.00",
        plan_narration="SignUp Bonus",
    ).order_by("date_created", "id"):
        key = (bonus.user_id, "5.00")
        if key in seen:
            duplicate_ids.append(bonus.id)
        else:
            seen.add(key)

    if duplicate_ids:
        Bonus.objects.filter(id__in=duplicate_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("creataura", "0023_notification"),
    ]

    operations = [
        migrations.RunPython(
            remove_duplicate_signup_bonuses,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="bonus",
            constraint=models.UniqueConstraint(
                condition=models.Q(("plan_narration", "SignUp Bonus")),
                fields=("user", "amount", "plan_narration"),
                name="unique_signup_bonus_per_user",
            ),
        ),
    ]
