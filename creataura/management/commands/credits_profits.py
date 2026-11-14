from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from creataura.models import ProfitRecord, UserInvestment
from creataura.verification import send_simple_email


class Command(BaseCommand):
    help = "Credit daily ROI profit for every active investment."

    def handle(self, *args, **options):
        now = timezone.now()
        credited = 0
        completed = 0

        investment_ids = list(
            UserInvestment.objects.filter(status="active").values_list("pk", flat=True)
        )

        for pk in investment_ids:
            new_days = []
            daily_profit = Decimal("0")

            with transaction.atomic():
                investment = (
                    UserInvestment.objects.select_for_update(of=("self",))
                    .select_related("plan", "user")
                    .get(pk=pk)
                )
                if investment.status != "active":
                    continue

                plan = investment.plan
                end = investment.expires_at or (
                    investment.date_created + timedelta(days=plan.duration_days)
                )
                cutoff = min(now, end)

                days_due = (cutoff - investment.date_created).days
                days_total = (end - investment.date_created).days
                days_due = max(0, min(days_due, days_total))

                paid_days = set(
                    ProfitRecord.objects.filter(
                        investment=investment, profit_day__isnull=False
                    ).values_list("profit_day", flat=True)
                )

                daily_profit = (
                    investment.amount * plan.daily_roi / Decimal("100")
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                if daily_profit > 0:
                    for day in range(1, days_due + 1):
                        if day in paid_days:
                            continue
                        ProfitRecord.objects.create(
                            user=investment.user,
                            investment=investment,
                            profit_day=day,
                            amount=daily_profit,
                            narration=f"Daily ROI - {plan.name} (day {day})",
                        )
                        new_days.append(day)

                if now >= end:
                    investment.status = "completed"
                    investment.save(update_fields=["status"])
                    completed += 1

            if new_days:
                credited += len(new_days)
                self._notify(investment, len(new_days), daily_profit)

        self.stdout.write(
            self.style.SUCCESS(
                f"Credited {credited} profit record(s); completed {completed} investment(s)."
            )
        )

    def _notify(self, investment, days, daily_profit):
        profile = getattr(investment.user, "creataura_profile", None)
        if not (profile and profile.email_profit_notification and investment.user.email):
            return
        total = daily_profit * days
        send_simple_email(
            investment.user.email,
            "You received investment profit",
            f"${total:,.2f} profit from your {investment.plan.name} was added to your account.",
        )