from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import models, transaction
from django.utils import timezone

from .models import ProfitRecord, UserInvestment
from .verification import send_simple_email


def credit_due_profits(user=None, notify=False, dry_run=False):
    """Credit every full day of profit owed (including back-pay).

    Safe to run any number of times. With dry_run=True nothing is written.
    Returns {"days": int, "amount": Decimal, "completed": int}.
    """
    now = timezone.now()
    queryset = UserInvestment.objects.filter(status="active")
    if user is not None:
        queryset = queryset.filter(user=user)

    result = {"days": 0, "amount": Decimal("0"), "completed": 0}

    for pk in list(queryset.values_list("pk", flat=True)):
        new_days = []

        with transaction.atomic():
            investment = (
                UserInvestment.objects.select_for_update(of=("self",))
                .select_related("plan", "user")
                .get(pk=pk)
            )
            if investment.status != "active":
                continue

            plan = investment.plan
            total_days = plan.duration_days
            end = investment.expires_at or (
                investment.date_created + timedelta(days=total_days)
            )

            days_due = (min(now, end) - investment.date_created).days
            days_due = max(0, min(days_due, total_days))

            daily_profit = (
                investment.amount * plan.daily_roi / Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            paid_days = set(
                ProfitRecord.objects.filter(
                    investment=investment, profit_day__isnull=False
                ).values_list("profit_day", flat=True)
            )

            # Profit an admin already gave by hand counts as days already paid.
            manual_total = ProfitRecord.objects.filter(
                investment=investment, profit_day__isnull=True
            ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
            covered_days = (
                int(manual_total // daily_profit) if daily_profit > 0 else 0
            )

            if daily_profit > 0:
                for day in range(1, days_due + 1):
                    if day in paid_days or day <= covered_days:
                        continue
                    if not dry_run:
                        ProfitRecord.objects.create(
                            user=investment.user,
                            investment=investment,
                            profit_day=day,
                            amount=daily_profit,
                            narration=f"Daily ROI - {plan.name} (day {day})",
                        )
                    new_days.append(day)

            if now >= end:
                result["completed"] += 1
                if not dry_run:
                    investment.status = "completed"
                    investment.save(update_fields=["status"])

        result["days"] += len(new_days)
        result["amount"] += daily_profit * len(new_days)

        if notify and new_days and not dry_run:
            profile = getattr(investment.user, "creataura_profile", None)
            if (
                profile
                and profile.email_profit_notification
                and investment.user.email
            ):
                send_simple_email(
                    investment.user.email,
                    "You received investment profit",
                    f"${daily_profit * len(new_days):,.2f} profit from your "
                    f"{plan.name} was added to your account.",
                )

    return result