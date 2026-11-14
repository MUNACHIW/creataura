from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import secrets

from actstream import action
from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import models, transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import url_has_allowed_host_and_scheme, urlsafe_base64_decode
from django.views.decorators.http import require_POST

from .countries import COUNTRIES
from .forms import SupportMessageForm
from .models import (
    BankAccount,
    Bonus,
    CryptoExchange,
    Deposit,
    DepositWallet,
    InvestmentPlan,
    KYCVerification,
    Notification,
    ProfitRecord, 
    ReferralBonus,
    SupportMessage,
    UserInvestment,
    UserProfile,
    WithdrawalBTC,
    WithdrawalMethod,
    WithdrawalXRP,
)
from .verification import (
    email_verification_token,
    is_email_verified,
    send_password_reset_email,
    send_verification_email,
     send_simple_email,
)

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
ROI_OTP_MINUTES = 10
OTP_MINUTES = 10
OTP_MAX_TRIES = 5


# =========================================================
# Helpers
# =========================================================
def _checked(value):
    return "checked" if value else ""

def _status_label(value):
    return str(value or "").replace("_", " ").title()


def _money(value):
    return f"${value:,.2f}"


def _when(value):
    return timezone.localtime(value).strftime("%b %d, %Y, %I:%M %p")


def _plain(value, places=0):
    return f"{float(value):.{places}f}"

def _issue_otp(request, session_key, label):
    """Create an OTP, store it in the session and email it."""
    if not request.user.email:
        messages.error(request, "Add an email address to your account first.")
        return
    otp = secrets.token_hex(3).upper()
    request.session[session_key] = {
        "code": otp,
        "at": timezone.now().timestamp(),
        "tries": 0,
    }
    sent = send_simple_email(
        request.user.email,
        f"Capitalnext {label} Withdrawal OTP",
        f"Your {label} withdrawal OTP is {otp}. It expires in {OTP_MINUTES} minutes.",
    )
    if sent:
        messages.success(request, "Withdrawal OTP sent to your email.")
    else:
        messages.error(request, "We couldn't send the OTP. Please try again shortly.")


def _otp_error(request, session_key, code):
    """Return an error message if the OTP is not valid, otherwise None."""
    stored = request.session.get(session_key) or {}
    expected = stored.get("code", "")
    if not expected:
        return "Request an OTP before completing withdrawal."

    age = timezone.now().timestamp() - stored.get("at", 0)
    if age > OTP_MINUTES * 60:
        request.session.pop(session_key, None)
        return "Your OTP has expired. Request a new one."

    if secrets.compare_digest(code.encode(), expected.encode()):
        return None

    stored["tries"] = stored.get("tries", 0) + 1
    if stored["tries"] >= OTP_MAX_TRIES:
        request.session.pop(session_key, None)
        return "Too many wrong attempts. Request a new OTP."
    request.session[session_key] = stored
    return "The withdrawal OTP is incorrect."


def _lock_user(user):
    """Lock the user's row so concurrent requests can't spend the same money."""
    User.objects.select_for_update().get(pk=user.pk)


def _roi_figures(user):
    """Return (total_profit, withdrawable_roi).

    withdrawable_roi can never exceed the real account balance, so ROI
    cannot be withdrawn on top of money that was already paid out.
    """
    total_profit = ProfitRecord.objects.filter(user=user).aggregate(
        total=models.Sum("amount")
    )["total"] or Decimal("0")

    reserved = Decimal("0")
    for model in (WithdrawalBTC, WithdrawalXRP):
        reserved += model.objects.filter(user=user, source="roi").exclude(
            status="rejected"
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    available_roi = max(total_profit - reserved, Decimal("0"))
    balance = get_available_balance(user)
    return total_profit, min(available_roi, balance)


def _get_profile(user):
    profile = getattr(user, "creataura_profile", None)
    if profile is None:
        profile = UserProfile.objects.create(
            user=user,
            full_name=user.get_full_name() or user.username,
            phone_number="",
            bitcoin_address="",
            country="",
        )
    return profile


def _country_options(selected):
    return [
        {"name": name, "selected": "selected" if name == selected else ""}
        for name in COUNTRIES
    ]


def _client_ip(request):
    # Behind a proxy (Render, Cloudflare), make sure REMOTE_ADDR is correct there.
    return request.META.get("REMOTE_ADDR", "unknown")


def _safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return "dashboard"


def _get_user_from_uid(uidb64):
    try:
        return User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


def award_signup_bonus(user):
    return Bonus.objects.get_or_create(
        user=user,
        amount=Decimal("5.00"),
        plan_narration="SignUp Bonus",
    )


def get_available_balance(user):
    approved_deposits = Deposit.objects.filter(user=user, status="approved").aggregate(
        total=models.Sum("amount")
    )["total"] or Decimal("0")
    bonuses = Bonus.objects.filter(user=user).aggregate(total=models.Sum("amount"))[
        "total"
    ] or Decimal("0")
    profits = ProfitRecord.objects.filter(user=user).aggregate(
        total=models.Sum("amount")
    )["total"] or Decimal("0")
    referral_bonuses = ReferralBonus.objects.filter(
        referrer=user, status="paid"
    ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    btc_withdrawals = WithdrawalBTC.objects.filter(user=user).exclude(status="rejected")
    xrp_withdrawals = WithdrawalXRP.objects.filter(user=user).exclude(status="rejected")
    reserved_withdrawals = sum(
        (record.amount + record.charges for record in btc_withdrawals),
        Decimal("0"),
    ) + sum(
        (record.amount + record.charges for record in xrp_withdrawals),
        Decimal("0"),
    )

    active_investments = UserInvestment.objects.filter(
        user=user, status="active"
    ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    completed_exchanges = CryptoExchange.objects.filter(user=user, status="completed")
    usd_spent = sum(
        (r.from_amount for r in completed_exchanges if r.from_asset == "usd"),
        Decimal("0"),
    )
    usd_received = sum(
        (r.to_amount for r in completed_exchanges if r.to_asset == "usd"),
        Decimal("0"),
    )

    balance = (
        approved_deposits
        + bonuses
        + profits
        + referral_bonuses
        - reserved_withdrawals
        - active_investments
        - usd_spent
        + usd_received
    )
    return max(balance, Decimal("0"))


# =========================================================
# Public pages
# =========================================================
def home(request):
    return render(request, "creataura/index.html")


def loans(request):
    return render(request, "creataura/loans.html")


def contact(request):
    return render(request, "creataura/contact.html")


def careers(request):
    return render(request, "creataura/careers.html")


def faq(request):
    return render(request, "creataura/faq.html")


def about(request):
    return render(request, "creataura/about.html")


def cryptocurrency(request):
    return render(request, "creataura/cryptocurrency.html")


def renewable_energy(request):
    return render(request, "creataura/renewableenergy.html")


def stocks_etfs(request):
    return render(request, "creataura/stocksetfs.html")


def real_estate(request):
    return render(request, "creataura/realestate.html")


def oil_gas(request):
    return render(request, "creataura/oilandgas.html")


def foreign_investor_protection(request):
    return render(request, "creataura/foreigninvestorprotection.html")


def page_not_found(request, exception=None):
    return render(request, "creataura/404.html", status=404)


# =========================================================
# Dashboard
# =========================================================
@login_required(login_url="login")
def notifications(request):
    notification_list = Notification.objects.filter(
        models.Q(send_to_all=True) | models.Q(recipients=request.user)
    ).distinct()
    unread_notifications = notification_list.exclude(read_by=request.user)

    if request.method == "POST":
        for notification in unread_notifications:
            notification.read_by.add(request.user)
        return redirect("notifications")

    action.send(request.user, verb="viewed Notifications  ")

    return render(
        request,
        "creataura/notifications.html",
        {
            "notifications": notification_list,
            "unread_notification_count": unread_notifications.count(),
        },
    )


@login_required(login_url="login")
def dashboard(request):
    profile = getattr(request.user, "creataura_profile", None)
    full_name = (
        profile.full_name.strip()
        if profile and profile.full_name.strip()
        else request.user.get_full_name().strip() or request.user.username
    )
    investments = UserInvestment.objects.filter(user=request.user)
    total_bonus = sum(
        (bonus.amount for bonus in Bonus.objects.filter(user=request.user)),
        Decimal("0"),
    )
    total_profit = ProfitRecord.objects.filter(user=request.user).aggregate(
        total=models.Sum("amount")
    )["total"] or Decimal("0")
    approved_deposits = Deposit.objects.filter(
        user=request.user,
        status="approved",
    ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
    approved_btc_withdrawals = WithdrawalBTC.objects.filter(
        user=request.user, status="approved"
    )
    approved_xrp_withdrawals = WithdrawalXRP.objects.filter(
        user=request.user, status="approved"
    )
    approved_withdrawal_total = sum(
        (
            record.amount + record.charges
            for record in list(approved_btc_withdrawals)
            + list(approved_xrp_withdrawals)
        ),
        Decimal("0"),
    )
    referral_total = ReferralBonus.objects.filter(
        referrer=request.user,
        status="paid",
    ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
    total_balance = get_available_balance(request.user)
    notification_list = Notification.objects.filter(
        models.Q(send_to_all=True) | models.Q(recipients=request.user)
    ).distinct()
    unread_notifications = notification_list.exclude(read_by=request.user)
    latest_deposits = Deposit.objects.filter(
    user=request.user
      ).order_by("-date_created")[:1]  # latest 5 deposits
      # latest 5 withdrawals
    action.send(request.user, verb="viewed dashboard")
    return render(
        request,
        "creataura/dashboard.html",
        {
            "dashboard_full_name": full_name,
            "total_investment_plans": investments.count(),
            "active_investment_plans": investments.filter(status="active").count(),
            "total_bonus": total_bonus,
            "total_profit": total_profit,
            "total_balance": total_balance,
            "total_deposit": approved_deposits,
            "total_referral_bonus": referral_total,
            "total_withdrawals": approved_withdrawal_total,
            "notifications": unread_notifications[:10],
            "latest_deposits": latest_deposits,
            "unread_notification_count": unread_notifications.count(),
        },
    )

EXCHANGE_ASSETS = (
    "usd", "btc", "eth", "ltc", "link", "bnb",
    "ada", "aave", "usdt", "bch", "xlm",
)
EXCHANGE_RATES = {
    "usd": Decimal("1"),
    "btc": Decimal("97000"),
    "eth": Decimal("3500"),
    "ltc": Decimal("100"),
    "link": Decimal("25"),
    "bnb": Decimal("710.58"),
    "ada": Decimal("0.50"),
    "aave": Decimal("300"),
    "usdt": Decimal("1"),
    "bch": Decimal("500"),
    "xlm": Decimal("0.10"),
}
def _coin(value):
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    return text or "0"


def _exchange_balances(user):
    """Coin holdings (everything except USD) built from completed exchanges."""
    balances = {asset: Decimal("0") for asset in EXCHANGE_ASSETS if asset != "usd"}
    for record in CryptoExchange.objects.filter(user=user, status="completed"):
        if record.to_asset in balances:
            balances[record.to_asset] += record.to_amount
        if record.from_asset in balances:
            balances[record.from_asset] -= record.from_amount
    return balances
@login_required(login_url="login")
def crypto_exchange(request):
    if request.method == "POST":
        from_asset = request.POST.get("from_asset", "").lower()
        to_asset = request.POST.get("to_asset", "").lower()
        try:
            from_amount = Decimal(request.POST.get("from_amount", "").strip())
            if from_amount.is_finite():
                from_amount = from_amount.quantize(Decimal("0.00000001"))
        except (InvalidOperation, AttributeError):
            from_amount = Decimal("0")

        if (
            from_asset not in EXCHANGE_ASSETS
            or to_asset not in EXCHANGE_ASSETS
            or from_asset == to_asset
        ):
            messages.error(request, "Choose two different assets.")
        elif not from_amount.is_finite() or from_amount <= 0:
            messages.error(request, "Enter a valid amount.")
        else:
            with transaction.atomic():
                # Lock so two simultaneous exchanges can't spend the same funds
                _lock_user(request.user)
                usd_balance = get_available_balance(request.user)
                coin_balances = _exchange_balances(request.user)

                if from_asset == "usd" and from_amount > usd_balance:
                    messages.error(request, "Insufficient account balance.")
                elif from_asset != "usd" and from_amount > coin_balances[from_asset]:
                    messages.error(
                        request, f"Insufficient {from_asset.upper()} balance."
                    )
                else:
                    rate_from = EXCHANGE_RATES[from_asset]
                    rate_to = EXCHANGE_RATES[to_asset]
                    gross_value = from_amount * rate_from
                    commission = gross_value * Decimal("0.02")
                    to_amount = (gross_value - commission) / rate_to
                    CryptoExchange.objects.create(
                        user=request.user,
                        from_asset=from_asset,
                        to_asset=to_asset,
                        from_amount=from_amount,
                        to_amount=to_amount.quantize(Decimal("0.00000001")),
                        exchange_rate=(rate_to / rate_from).quantize(
                            Decimal("0.00000001")
                        ),
                        commission=commission.quantize(Decimal("0.00000001")),
                        status="completed",
                    )
                    messages.success(
                        request,
                        f"Exchange completed: {_coin(from_amount)} {from_asset.upper()} "
                        f"to {_coin(to_amount)} {to_asset.upper()}.",
                    )
        return redirect("crypto_exchange")

    usd_balance = get_available_balance(request.user)
    coin_balances = _exchange_balances(request.user)

    balances = {"usd": _money(usd_balance)}
    for asset, value in coin_balances.items():
        balances[asset] = f"{_coin(value)} {asset.upper()}"

    exchange_data = {
        "rates": {asset: float(rate) for asset, rate in EXCHANGE_RATES.items()},
        "balances": {
            "usd": float(usd_balance),
            **{asset: float(value) for asset, value in coin_balances.items()},
        },
    }

    exchange_rows = [
        {
            "pair": f"{record.from_asset.upper()} to {record.to_asset.upper()}",
            "sent": f"{_coin(record.from_amount)} {record.from_asset.upper()}",
            "received": f"{_coin(record.to_amount)} {record.to_asset.upper()}",
            "status": record.status,
            "status_label": _status_label(record.status),
            "date": _when(record.date_created),
        }
        for record in CryptoExchange.objects.filter(user=request.user)[:10]
    ]

    action.send(request.user, verb="viewed cryptoexchange")
    return render(
        request,
        "creataura/crypto_exchange.html",
        {
            "balances": balances,
            "exchange_data": exchange_data,
            "exchange_rows": exchange_rows,
        },
    )


@login_required(login_url="login")
def kyc(request):
    verification = KYCVerification.objects.filter(user=request.user).first()
    if request.method == "POST":
        passport_photo = request.FILES.get("passport_photo")
        identity_photo = request.FILES.get("identity_photo")
        if not passport_photo or not identity_photo:
            messages.error(request, "Please upload both required documents.")
        else:
            if verification:
                verification.passport_photo = passport_photo
                verification.identity_photo = identity_photo
                verification.status = "pending"
                verification.save()
            else:
                verification = KYCVerification.objects.create(
                    user=request.user,
                    passport_photo=passport_photo,
                    identity_photo=identity_photo,
                )
            messages.success(request, "Your documents were submitted successfully.")
        action.send(request.user, verb="viewed kyc")
    return render(
        request,
        "creataura/kyc.html",
        {"kyc_verification": verification},
    )


@login_required(login_url="login")
def roi_history(request):
    records = ProfitRecord.objects.filter(user=request.user).select_related(
        "investment__plan"
    )
    total_profit = records.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    roi_rows = [
        {
            "narration": record.narration,
            "plan_name": (
                record.investment.plan.name if record.investment else "Manual credit"
            ),
            "amount": _money(record.amount),
            "date": _when(record.date_created),
        }
        for record in records
    ]

    action.send(request.user, verb="viewed ROI")
    return render(
        request,
        "creataura/roi_history.html",
        {
            "roi_rows": roi_rows,
            "total_profit": _money(total_profit),
        },
    )


@login_required(login_url="login")
def withdraw_roi(request):
    profile = getattr(request.user, "creataura_profile", None)
    bitcoin_address = profile.bitcoin_address if profile else ""
    session_key = "roi_withdrawal_otp"

    if request.method == "POST":
        total_profit, withdrawable = _roi_figures(request.user)
        if withdrawable <= 0:
            messages.error(request, "Nothing to withdraw at the moment!")
            return redirect("withdraw_roi")

        if request.POST.get("action") == "request_otp":
            _issue_otp(request, session_key, "ROI")
            return redirect("withdraw_roi")

        payment_mode = request.POST.get("payment_mode", "").strip().lower()
        otp_code = request.POST.get("otpcode", "").strip().upper()
        xrp_address = request.POST.get("xrp_address", "").strip()
        try:
            amount = Decimal(request.POST.get("amount", "").strip())
        except (InvalidOperation, AttributeError):
            amount = Decimal("0")

        if payment_mode not in ("bitcoin", "xrp"):
            messages.error(request, "Select a valid payment method.")
        elif not amount.is_finite() or amount <= 0:
            messages.error(request, "Enter a valid withdrawal amount.")
        elif payment_mode == "bitcoin" and not bitcoin_address.strip():
            messages.error(request, "Add your Bitcoin address in Settings first.")
        elif payment_mode == "xrp" and not xrp_address:
            messages.error(request, "Enter your XRP wallet address.")
        else:
            error = _otp_error(request, session_key, otp_code)
            if error:
                messages.error(request, error)
            else:
                with transaction.atomic():
                    _lock_user(request.user)
                    # Re-check inside the lock with fresh numbers
                    _, withdrawable = _roi_figures(request.user)
                    if amount > withdrawable:
                        messages.error(
                            request, "Amount exceeds your available ROI balance."
                        )
                        return redirect("withdraw_roi")

                    if payment_mode == "bitcoin":
                        WithdrawalBTC.objects.create(
                            user=request.user,
                            cryptocoin="Bitcoin",
                            amount=amount,
                            otpcode=otp_code,
                            status="pending",
                            source="roi",
                        )
                    else:
                        WithdrawalXRP.objects.create(
                            user=request.user,
                            cryptocoin="XRP",
                            amount=amount,
                            otpcode=otp_code,
                            xrp_address=xrp_address,
                            status="pending",
                            source="roi",
                        )
                request.session.pop(session_key, None)
                messages.success(request, "ROI withdrawal submitted for approval.")
                return redirect("withdraw_roi")

    total_profit, withdrawable = _roi_figures(request.user)

    withdrawal_rows = list(
        WithdrawalBTC.objects.filter(user=request.user, source="roi")
    ) + list(WithdrawalXRP.objects.filter(user=request.user, source="roi"))
    withdrawal_rows.sort(key=lambda record: record.date_created, reverse=True)
    roi_withdrawals = [
        {
            "cryptocoin": item.cryptocoin,
            "amount": _money(item.amount),
            "status": item.status,
            "status_label": _status_label(item.status),
            "date": _when(item.date_created),
        }
        for item in withdrawal_rows
    ]

    if request.method == "GET" and withdrawable <= 0:
        messages.error(request, "Nothing to withdraw at the moment!")

    action.send(request.user, verb="viewed withdraw roi")
    return render(
        request,
        "creataura/withdraw_roi.html",
        {
            "has_roi": withdrawable > 0,
            "available_roi": _money(withdrawable),
            "available_roi_max": f"{withdrawable:.2f}",
            "total_profit": _money(total_profit),
            "bitcoin_address": bitcoin_address,
            "roi_withdrawals": roi_withdrawals,
        },
    )
# =========================================================
# Withdrawals
# =========================================================
@login_required(login_url="login")
def withdrawal(request):
    method_defaults = {
        "Bitcoin": {
            "minimum_amount": Decimal("10"),
            "maximum_amount": Decimal("50000000"),
            "charge_type": "Percentage",
            "charge_amount": Decimal("0"),
            "duration": "Instant",
        },
        "XRP": {
            "minimum_amount": Decimal("10"),
            "maximum_amount": Decimal("1000000"),
            "charge_type": "Percentage",
            "charge_amount": Decimal("0"),
            "duration": "Instant",
        },
    }
    methods = []
    for display_name in ("Bitcoin", "XRP"):
        method = WithdrawalMethod.objects.filter(
            method_type__iexact=display_name,
            is_active=True,
        ).first()
        if method:
            methods.append(method)
        else:
            methods.append(
                {"method_type": display_name, **method_defaults[display_name]}
            )

    # Withdrawals must go through the OTP-protected pages, never straight from here.
    if request.method == "POST":
        method_type = request.POST.get("method_type", "").strip().lower()
        if method_type == "bitcoin":
            return redirect("withdrawal_btc")
        if method_type == "xrp":
            return redirect("withdrawal_xrp")
        messages.error(request, "Select a valid withdrawal method.")
        return redirect("withdrawal")

    profile = getattr(request.user, "creataura_profile", None)
    action.send(request.user, verb="viewed withdrawal")
    return render(
        request,
        "creataura/withdrawal.html",
        {
            "withdrawal_methods": methods,
            "available_balance": get_available_balance(request.user),
            "bitcoin_address": profile.bitcoin_address if profile else "",
        },
    )


@login_required(login_url="login")
def withdrawal_btc(request):
    profile = getattr(request.user, "creataura_profile", None)
    method = WithdrawalMethod.objects.filter(
        method_type__iexact="Bitcoin", is_active=True
    ).first()
    minimum = method.minimum_amount if method else Decimal("10")
    maximum = method.maximum_amount if method else Decimal("50000000")
    charge_type = method.charge_type if method else "Percentage"
    charge_amount = method.charge_amount if method else Decimal("0")
    session_key = "btc_withdrawal_otp"

    if request.method == "POST":
        if request.POST.get("action") == "request_otp":
            _issue_otp(request, session_key, "Bitcoin")
            return redirect("withdrawal_btc")

        try:
            amount = Decimal(request.POST.get("amount", "").strip())
        except (InvalidOperation, AttributeError):
            amount = Decimal("0")
        otp_code = request.POST.get("otpcode", "").strip().upper()
        charges = (
            amount * charge_amount / Decimal("100")
            if "percentage" in charge_type.lower()
            else charge_amount
        )

        if not amount.is_finite() or amount <= 0:
            messages.error(request, "Enter a valid withdrawal amount.")
        elif amount < minimum or amount > maximum:
            messages.error(
                request, f"Amount must be between ${minimum} and ${maximum}."
            )
        elif not profile or not profile.bitcoin_address.strip():
            messages.error(request, "Add your Bitcoin address in withdrawal settings.")
            return redirect("settings")
        else:
            error = _otp_error(request, session_key, otp_code)
            if error:
                messages.error(request, error)
            else:
                with transaction.atomic():
                    _lock_user(request.user)
                    if amount + charges > get_available_balance(request.user):
                        messages.error(request, "Insufficient account balance.")
                        return redirect("withdrawal_btc")
                    WithdrawalBTC.objects.create(
                        user=request.user,
                        cryptocoin="Bitcoin",
                        amount=amount,
                        otpcode=otp_code,
                        charges=charges,
                        status="pending",
                    )
                request.session.pop(session_key, None)
                messages.success(request, "Bitcoin withdrawal request submitted.")
        return redirect("withdrawal_btc")

    return render(
        request,
        "creataura/withdrawal_btc.html",
        {
            "bitcoin_address": profile.bitcoin_address if profile else "",
            "minimum_amount": minimum,
            "maximum_amount": maximum,
            "available_balance": get_available_balance(request.user),
        },
    )

@login_required(login_url="login")
def withdrawal_xrp(request):
    method = WithdrawalMethod.objects.filter(
        method_type__iexact="XRP", is_active=True
    ).first()
    minimum = method.minimum_amount if method else Decimal("10")
    maximum = method.maximum_amount if method else Decimal("1000000")
    charge_type = method.charge_type if method else "Percentage"
    charge_amount = method.charge_amount if method else Decimal("0")
    session_key = "xrp_withdrawal_otp"

    if request.method == "POST":
        if request.POST.get("action") == "request_otp":
            _issue_otp(request, session_key, "XRP")
            return redirect("withdrawal_xrp")

        try:
            amount = Decimal(request.POST.get("amount", "").strip())
        except (InvalidOperation, AttributeError):
            amount = Decimal("0")
        otp_code = request.POST.get("otpcode", "").strip().upper()
        xrp_address = request.POST.get("xrp_address", "").strip()
        charges = (
            amount * charge_amount / Decimal("100")
            if "percentage" in charge_type.lower()
            else charge_amount
        )

        if not amount.is_finite() or amount <= 0:
            messages.error(request, "Enter a valid withdrawal amount.")
        elif amount < minimum or amount > maximum:
            messages.error(
                request, f"Amount must be between ${minimum} and ${maximum}."
            )
        elif not xrp_address:
            messages.error(request, "Enter your XRP wallet address.")
        else:
            error = _otp_error(request, session_key, otp_code)
            if error:
                messages.error(request, error)
            else:
                with transaction.atomic():
                    _lock_user(request.user)
                    if amount + charges > get_available_balance(request.user):
                        messages.error(request, "Insufficient account balance.")
                        return redirect("withdrawal_xrp")
                    WithdrawalXRP.objects.create(
                        user=request.user,
                        cryptocoin="XRP",
                        amount=amount,
                        otpcode=otp_code,
                        xrp_address=xrp_address,
                        charges=charges,
                        status="pending",
                    )
                request.session.pop(session_key, None)
                messages.success(request, "XRP withdrawal request submitted.")
        return redirect("withdrawal_xrp")

    return render(
        request,
        "creataura/withdrawal_xrp.html",
        {
            "minimum_amount": minimum,
            "maximum_amount": maximum,
            "available_balance": get_available_balance(request.user),
        },
    )

# =========================================================
# Deposits
# =========================================================
@login_required(login_url="login")
def deposit(request):
    if request.method == "POST":
        payment_mode = request.POST.get("payment_mode", "").strip().lower()
        try:
            amount = Decimal(request.POST.get("amount", "").strip())
        except (InvalidOperation, AttributeError):
            amount = Decimal("0")
        if payment_mode not in ("bitcoin", "ethereum", "xrp"):
            messages.error(request, "Select a valid payment method.")
        elif not amount.is_finite() or amount <= 0:
            messages.error(request, "Enter a valid deposit amount.")
        else:
            request.session["deposit_amount"] = str(amount)
            request.session["deposit_mode"] = payment_mode
            return redirect("deposit_payment", payment_mode=payment_mode)
    action.send(request.user, verb="viewed deposit")

    return render(
        request,
        "creataura/deposit.html",
        {"available_balance": get_available_balance(request.user)},
    )


@login_required(login_url="login")
def deposit_payment(request, payment_mode):
    payment_mode = payment_mode.lower()
    if payment_mode not in ("bitcoin", "ethereum", "xrp"):
        return redirect("deposit")

    amount_value = request.session.get("deposit_amount")
    selected_mode = request.session.get("deposit_mode")
    if selected_mode != payment_mode or not amount_value:
        return redirect("deposit")
    try:
        amount = Decimal(amount_value)
    except InvalidOperation:
        return redirect("deposit")

    # No placeholder addresses: customers must never be shown a dead wallet.
    wallet = DepositWallet.objects.filter(crypto=payment_mode, is_active=True).first()
    if not wallet:
        messages.error(request, "This payment method is temporarily unavailable.")
        return redirect("deposit")
    wallet_address = wallet.wallet_address
    network_type = wallet.network_type

    if request.method == "POST":
        proof = request.FILES.get("proof_of_payment")
        if not proof:
            messages.error(request, "Upload the proof of payment.")
        else:
            Deposit.objects.create(
                user=request.user,
                amount=amount,
                payment_mode=payment_mode,
                network_type=network_type,
                wallet_address=wallet_address,
                proof_of_payment=proof,
                status="pending",
            )
            request.session.pop("deposit_amount", None)
            request.session.pop("deposit_mode", None)
            messages.success(request, "Deposit proof submitted for approval.")
            return redirect("transaction_history")

    return render(
        request,
        "creataura/deposit_payment.html",
        {
            "payment_mode": payment_mode,
            "payment_label": payment_mode.title(),
            "network_type": network_type,
            "wallet_address": wallet_address,
            "deposit_amount": amount,
        },
    )


@login_required(login_url="login")
def transaction_history(request):
    deposits = [
        {
            "amount": _money(item.amount),
            "payment_mode": item.get_payment_mode_display(),
            "status": item.status,
            "status_label": _status_label(item.status),
            "date": _when(item.date_created),
        }
        for item in Deposit.objects.filter(user=request.user)
    ]

    withdrawal_rows = []
    for item in WithdrawalBTC.objects.filter(user=request.user):
        withdrawal_rows.append(item)
    for item in WithdrawalXRP.objects.filter(user=request.user):
        withdrawal_rows.append(item)
    withdrawal_rows.sort(key=lambda record: record.date_created, reverse=True)

    withdrawals = [
        {
            "amount": _money(item.amount),
            "amount_with_charges": _money(item.amount + item.charges),
            "receiving_mode": item.cryptocoin,
            "status": item.status,
            "status_label": _status_label(item.status),
            "date": _when(item.date_created),
        }
        for item in withdrawal_rows
    ]

    other_rows = []
    signup_bonus = Bonus.objects.filter(
        user=request.user, plan_narration="SignUp Bonus"
    ).first()
    if signup_bonus:
        other_rows.append(
            {
                "amount": signup_bonus.amount,
                "type": "Bonus",
                "plan_narration": "SignUp Bonus",
                "status": "completed",
                "date_created": signup_bonus.date_created,
            }
        )
    for investment in UserInvestment.objects.filter(
        user=request.user
    ).select_related("plan"):
        other_rows.append(
            {
                "amount": investment.amount,
                "type": "Investment",
                "plan_narration": investment.plan.name,
                "status": investment.status,
                "date_created": investment.date_created,
            }
        )
    other_rows.sort(key=lambda record: record["date_created"], reverse=True)

    other_transactions = [
        {
            "amount": _money(row["amount"]),
            "type": row["type"],
            "plan_narration": row["plan_narration"],
            "status": row["status"],
            "status_label": _status_label(row["status"]),
            "date": _when(row["date_created"]),
        }
        for row in other_rows
    ]

    action.send(request.user, verb="viewed transaction history")
    return render(
        request,
        "creataura/transactions.html",
        {
            "deposits": deposits,
            "withdrawals": withdrawals,
            "other_transactions": other_transactions,
        },
    )

# =========================================================
# Investments
# =========================================================
@login_required(login_url="login")
def investments(request):
    plan_rows = list(InvestmentPlan.objects.filter(is_active=True))
    if not plan_rows:
        plan_rows = [
            {
                "id": 0,
                "name": "Beginner Plan",
                "amount": 500,
                "minimum_deposit": 500,
                "maximum_deposit": 25000,
                "daily_roi": 1.5,
                "weekly_roi": 10.5,
                "gift_bonus": 1,
                "duration_days": 60,
            },
            {
                "id": 0,
                "name": "Standard Plan",
                "amount": 25000,
                "minimum_deposit": 25000,
                "maximum_deposit": 100000,
                "daily_roi": 2.5,
                "weekly_roi": 17.5,
                "gift_bonus": 10,
                "duration_days": 60,
            },
            {
                "id": 0,
                "name": "Business Pro Plan",
                "amount": 101000,
                "minimum_deposit": 101000,
                "maximum_deposit": 1000000,
                "daily_roi": 3.1,
                "weekly_roi": 21.7,
                "gift_bonus": 15,
                "duration_days": 60,
            },
        ]

    def field(plan, name):
        return plan[name] if isinstance(plan, dict) else getattr(plan, name)

    plans = [
        {
            "id": field(plan, "id"),
            "name": field(plan, "name"),
            "price": _plain(field(plan, "amount")),
            "minimum": _plain(field(plan, "minimum_deposit")),
            "maximum": _plain(field(plan, "maximum_deposit")),
            "daily_roi": _plain(field(plan, "daily_roi"), 1),
            "weekly_roi": _plain(field(plan, "weekly_roi"), 1),
            "gift_bonus": _plain(field(plan, "gift_bonus")),
            "duration": field(plan, "duration_days"),
            "input_default": str(field(plan, "amount")),
            "input_min": str(field(plan, "minimum_deposit")),
            "input_max": str(field(plan, "maximum_deposit")),
        }
        for plan in plan_rows
    ]

    user_investments = [
        {
            "plan_name": item.plan.name,
            "started": timezone.localtime(item.date_created).strftime("%b %d, %Y"),
            "amount": _money(item.amount),
            "status": item.status,
            "status_label": _status_label(item.status),
        }
        for item in UserInvestment.objects.filter(user=request.user).select_related(
            "plan"
        )
    ]

    action.send(request.user, verb="viewed investment plans ")
    return render(
        request,
        "creataura/investments.html",
        {
            "plans": plans,
            "user_investments": user_investments,
            "available_balance": _money(get_available_balance(request.user)),
        },
    )


@login_required(login_url="login")
@require_POST
def join_investment(request, plan_id):
    plan = InvestmentPlan.objects.filter(id=plan_id, is_active=True).first()
    if not plan:
        messages.error(request, "That investment plan is no longer available.")
        return redirect("invest")
    try:
        amount = Decimal(request.POST.get("amount", "").strip())
    except (InvalidOperation, ValueError):
        messages.error(request, "Enter a valid investment amount.")
        return redirect("invest")
    if not amount.is_finite():
        messages.error(request, "Enter a valid investment amount.")
        return redirect("invest")
    if amount < plan.minimum_deposit:
        messages.error(
            request, f"The minimum investment amount is ${plan.minimum_deposit}."
        )
        return redirect("invest")
    if amount > plan.maximum_deposit:
        messages.error(
            request, f"The maximum investment amount is ${plan.maximum_deposit}."
        )
        return redirect("invest")
    with transaction.atomic():
        # Lock the user row so two simultaneous requests can't spend the same balance.
        User.objects.select_for_update().get(pk=request.user.pk)
        available_balance = get_available_balance(request.user)
        if amount > available_balance:
            messages.error(request, "Insufficient account balance.")
            return redirect("invest")
        UserInvestment.objects.create(
            user=request.user,
            plan=plan,
            amount=amount,
            expires_at=timezone.now() + timedelta(days=plan.duration_days),
        )
    messages.success(request, f"You joined the {plan.name} successfully.")
    return redirect("invest")


@login_required(login_url="login")
def referrals(request):
    profile = getattr(request.user, "creataura_profile", None)
    referral_id = request.user.username
    referral_link = request.build_absolute_uri(f"/ref/{referral_id}/")

    referred_profiles = (
        UserProfile.objects.select_related("user")
        .filter(referral_id__iexact=referral_id)
        .order_by("-user__date_joined")
    )
    referred_users = [
        {"user": p.user, "profile": p, "parent": profile} for p in referred_profiles
    ]

    referrer = None
    if profile and profile.referral_id:
        referrer_profile = (
            UserProfile.objects.select_related("user")
            .filter(user__username__iexact=profile.referral_id)
            .first()
        )
        if referrer_profile:
            referrer = referrer_profile.user
    action.send(request.user, verb="viewed referal page")
    return render(
        request,
        "creataura/referrals.html",
        {
            "profile": profile,
            "referral_id": referral_id,
            "referral_link": referral_link,
            "referrer": referrer,
            "referred_users": referred_users,
        },
    )


@login_required(login_url="login")
def support(request):
    action.send(request.user, verb="viewed support")
    return render(
        request,
        "creataura/support.html",
        {"support_form": SupportMessageForm()},
    )


@login_required(login_url="login")
@require_POST
def support_submit(request):
    form = SupportMessageForm(request.POST)
    if form.is_valid():
        support_message = form.save(commit=False)
        support_message.user = request.user
        support_message.save()
        messages.success(request, "Your support message has been sent.")
        return redirect("support")
    action.send(request.user, verb="viewed support")
    return render(
        request,
        "creataura/support.html",
        {"support_form": form},
        status=400,
    )


# =========================================================
# Settings
# =========================================================
@login_required(login_url="login")
def settings(request):
    profile = _get_profile(request.user)
    action_name = request.POST.get("settings_action", "")

    if request.method == "POST":
        if action_name == "withdrawals":
            bitcoin_address = request.POST.get("bitcoin_address", "").strip()

            if not bitcoin_address:
                messages.error(request, "Bitcoin address cannot be empty.")
            else:
                profile.bitcoin_address = bitcoin_address
                profile.save(update_fields=["bitcoin_address"])

                account, _ = BankAccount.objects.get_or_create(user=request.user)
                account.bank_name = request.POST.get("bank_name", "").strip()
                account.account_name = request.POST.get("account_name", "").strip()
                account.account_number = request.POST.get("account_number", "").strip()
                account.swift_code = request.POST.get("swift_code", "").strip()
                account.ethereum_address = request.POST.get(
                    "ethereum_address", ""
                ).strip()
                account.litecoin_address = request.POST.get(
                    "litecoin_address", ""
                ).strip()
                account.save()
                messages.success(request, "Withdrawal settings saved successfully.")

        elif action_name == "password":
            old_password = request.POST.get("old_password", "")
            new_password = request.POST.get("new_password", "")
            confirm_password = request.POST.get("confirm_password", "")

            if not all([old_password, new_password, confirm_password]):
                messages.error(request, "Please complete all password fields.")
            elif not request.user.check_password(old_password):
                messages.error(request, "Your old password is incorrect.")
            elif new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
            else:
                try:
                    validate_password(new_password, request.user)
                except ValidationError as error:
                    messages.error(request, " ".join(error.messages))
                else:
                    request.user.set_password(new_password)
                    request.user.save(update_fields=["password"])
                    update_session_auth_hash(request, request.user)
                    messages.success(request, "Password updated successfully.")

        elif action_name == "other":
            profile.email_profit_notification = (
                request.POST.get("email_profit_notification") == "yes"
            )
            profile.save(update_fields=["email_profit_notification"])
            messages.success(request, "Other settings saved successfully.")

        else:
            full_name = request.POST.get("full_name", "").strip()
            email = request.POST.get("email", "").strip().lower()
            phone_number = request.POST.get("phone_number", "").strip()
            full_address = request.POST.get("full_address", "").strip()
            nationality = request.POST.get("nationality", "").strip()
            dob_raw = request.POST.get("date_of_birth", "").strip()

            date_of_birth = None
            dob_error = False
            if dob_raw:
                try:
                    date_of_birth = date.fromisoformat(dob_raw)
                    if date_of_birth > date.today():
                        dob_error = True
                except ValueError:
                    dob_error = True

            if not all([full_name, email, phone_number]):
                messages.error(request, "Please complete all required fields.")
            elif dob_error:
                messages.error(request, "Please enter a valid date of birth.")
            elif (
                User.objects.filter(email__iexact=email)
                .exclude(pk=request.user.pk)
                .exists()
            ):
                messages.error(request, "That email is already registered.")
            else:
                email_changed = email != request.user.email.lower()

                request.user.email = email
                request.user.first_name = full_name
                request.user.save(update_fields=["email", "first_name"])

                profile.full_name = full_name
                profile.phone_number = phone_number
                profile.full_address = full_address
                profile.nationality = nationality
                profile.date_of_birth = date_of_birth

                if email_changed:
                    profile.email_verified = False
                    profile.email_verified_at = None

                profile.save()

                if email_changed:
                    send_verification_email(request, request.user)
                    messages.success(
                        request,
                        "Profile updated. We've sent a verification link to your new email.",
                    )
                    return redirect("verify_email")

                messages.success(request, "Profile updated successfully.")

        return redirect("settings")

    withdrawal_account = getattr(request.user, "withdrawal_account", None)
    action.send(request.user, verb="viewed settings")
    return render(
        request,
        "creataura/settings.html",
        {
            "profile": profile,
            "withdrawal_account": withdrawal_account,
            "nationality_options": _country_options(profile.nationality),
            "dob_value": (
                profile.date_of_birth.isoformat() if profile.date_of_birth else ""
            ),
            "profit_yes": _checked(profile.email_profit_notification),
            "profit_no": _checked(not profile.email_profit_notification),
        },
    )


@login_required(login_url="login")
def advanced_account_settings(request):
    profile, _ = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={
            "full_name": request.user.get_full_name() or request.user.username,
            "phone_number": "",
            "bitcoin_address": "",
            "country": "",
        },
    )

    if request.method == "POST":
        security_action = request.POST.get("security_action", "")
        password = request.POST.get("password", "")

        if security_action == "two_factor":
            if not password:
                messages.error(request, "Confirm your password to continue.")
            elif not request.user.check_password(password):
                messages.error(request, "Your password is incorrect.")
            else:
                profile.two_factor_enabled = not profile.two_factor_enabled
                profile.save(update_fields=["two_factor_enabled"])
                if profile.two_factor_enabled:
                    messages.success(
                        request, "Two factor authentication has been enabled."
                    )
                else:
                    messages.success(
                        request, "Two factor authentication has been disabled."
                    )
            return redirect("advanced_account_settings")

        if security_action == "logout_other_sessions":
            current_key = request.session.session_key
            removed = 0
            for session in Session.objects.filter(expire_date__gte=timezone.now()):
                if session.session_key == current_key:
                    continue
                data = session.get_decoded()
                if str(data.get("_auth_user_id")) == str(request.user.pk):
                    session.delete()
                    removed += 1
            messages.success(
                request,
                f"{removed} other browser session{'s' if removed != 1 else ''} logged out.",
            )
            return redirect("advanced_account_settings")

        if security_action == "delete_account":
            if not password:
                messages.error(request, "Enter your password to delete your account.")
            elif not request.user.check_password(password):
                messages.error(request, "Your password is incorrect.")
            else:
                request.session.flush()
                request.user.delete()
                messages.success(request, "Your account has been deleted permanently.")
                return redirect("login")
            return redirect("advanced_account_settings")

    current_key = request.session.session_key
    browser_sessions = []
    for session in Session.objects.filter(expire_date__gte=timezone.now()).order_by(
        "-expire_date"
    ):
        data = session.get_decoded()
        if str(data.get("_auth_user_id")) != str(request.user.pk):
            continue
        browser_sessions.append(
            {
                "is_current": session.session_key == current_key,
                "expire_date": session.expire_date,
                "ip_address": (
                    request.META.get("REMOTE_ADDR", "")
                    if session.session_key == current_key
                    else ""
                ),
            }
        )

    return render(
        request,
        "creataura/advanced_account_settings.html",
        {"profile": profile, "browser_sessions": browser_sessions},
    )


# =========================================================
# Auth
# =========================================================
def register(request, referral_id=None):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form_data = {}

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip().lower()
        full_name = request.POST.get("full_name", "").strip()
        phone_number = request.POST.get("phone_number", "").strip()
        bitcoin_address = request.POST.get("bitcoin_address", "").strip()
        country = request.POST.get("country", "").strip()
        password = request.POST.get("password", "")
        password_again = request.POST.get("password_again", "")
        referral_id = request.POST.get("referral_id", "").strip() or referral_id
        referral_id = referral_id or ""

        # Passwords are never sent back to the browser.
        form_data = {
            "username": username,
            "email": email,
            "full_name": full_name,
            "phone_number": phone_number,
            "bitcoin_address": bitcoin_address,
            "country": country,
        }

        if not all(
            [
                username,
                email,
                full_name,
                phone_number,
                bitcoin_address,
                country,
                password,
                password_again,
            ]
        ):
            messages.error(request, "Please complete all required fields.")
        elif password != password_again:
            messages.error(request, "Passwords do not match.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "That username is already in use.")
        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request, "That email is already registered.")
        else:
            user = User(username=username, email=email, first_name=full_name)
            try:
                validate_password(password, user)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                with transaction.atomic():
                    user.set_password(password)
                    user.save()
                    UserProfile.objects.create(
                        user=user,
                        full_name=full_name,
                        phone_number=phone_number,
                        bitcoin_address=bitcoin_address,
                        country=country,
                        referral_id=referral_id,
                    )
                    award_signup_bonus(user)

                login(
                    request, user, backend="django.contrib.auth.backends.ModelBackend"
                )
                request.session.set_expiry(12 * 60 * 60)
                send_verification_email(request, user)
                messages.success(
                    request,
                    "Account created! We've sent a verification link to your email.",
                )
                return redirect("verify_email")

    return render(
        request,
        "creataura/register.html",
        {
            "countries": _country_options(form_data.get("country", "")),
            "initial_referral_id": referral_id or "",
            "form_data": form_data,
        },
    )


def user_login(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")

        throttle_key = f"login-fail:{_client_ip(request)}:{email}"
        attempts = cache.get(throttle_key, 0)

        if attempts >= MAX_LOGIN_ATTEMPTS:
            messages.error(
                request,
                "Too many failed attempts. Please try again in 15 minutes "
                "or reset your password.",
            )
            return render(request, "creataura/login.html")

        if not email or not password:
            messages.error(request, "Please enter your email and password.")
            return render(request, "creataura/login.html")

        user = User.objects.filter(email__iexact=email).first()
        authenticated_user = authenticate(
            request,
            username=user.username if user else email,
            password=password,
        )

        if authenticated_user is not None:
            cache.delete(throttle_key)
            login(request, authenticated_user)

            if request.POST.get("remember"):
                request.session.set_expiry(14 * 24 * 60 * 60)
            else:
                request.session.set_expiry(12 * 60 * 60)

            if not is_email_verified(authenticated_user):
                messages.warning(
                    request, "Please verify your email to access your account."
                )
                return redirect("verify_email")

            return redirect(_safe_next_url(request))

        cache.add(throttle_key, 0, timeout=LOCKOUT_SECONDS)
        try:
            cache.incr(throttle_key)
        except ValueError:
            cache.set(throttle_key, 1, timeout=LOCKOUT_SECONDS)

        messages.error(request, "Invalid email or password.")

    return render(request, "creataura/login.html")


def user_logout(request):
    logout(request)
    return redirect("login")


# ---------- Email verification ----------
@login_required
def verify_email(request):
    if is_email_verified(request.user):
        messages.info(request, "Your email is already verified.")
        return redirect("dashboard")
    return render(request, "creataura/verify_email.html", {"email": request.user.email})


@login_required
@require_POST
def resend_verification(request):
    if is_email_verified(request.user):
        return redirect("dashboard")

    if not cache.add(f"verify-resend:{request.user.pk}", 1, timeout=60):
        messages.error(request, "Please wait a minute before requesting another email.")
        return redirect("verify_email")

    if send_verification_email(request, request.user):
        messages.success(request, "Verification email sent. Check your inbox.")
    else:
        messages.error(request, "We couldn't send the email. Please try again shortly.")
    return redirect("verify_email")


def verify_email_confirm(request, uidb64, token):
    user = _get_user_from_uid(uidb64)

    if user is not None and is_email_verified(user):
        messages.info(request, "Your email is already verified.")
    elif user is not None and email_verification_token.check_token(user, token):
        UserProfile.objects.filter(user=user).update(
            email_verified=True, email_verified_at=timezone.now()
        )
        messages.success(request, "Email verified successfully.")
    else:
        messages.error(request, "This verification link is invalid or has expired.")
        return redirect("verify_email" if request.user.is_authenticated else "login")

    return redirect("dashboard" if request.user.is_authenticated else "login")


# ---------- Forgot / reset password ----------
def forgot_password(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user and user.has_usable_password():
            if cache.add(f"pwreset:{user.pk}", 1, timeout=60):
                send_password_reset_email(request, user)

        messages.success(
            request,
            "If an account exists for that email, we've sent a reset link.",
        )
        return redirect("forgot_password")

    return render(request, "creataura/forgot_password.html")


def reset_password(request, uidb64, token):
    user = _get_user_from_uid(uidb64)
    if user is None or not default_token_generator.check_token(user, token):
        return render(request, "creataura/reset_password.html", {"valid": False})

    if request.method == "POST":
        password = request.POST.get("password", "")
        password_again = request.POST.get("password_again", "")

        if not password or password != password_again:
            messages.error(request, "Passwords do not match.")
        else:
            try:
                validate_password(password, user)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
            else:
                user.set_password(password)
                user.save()
                UserProfile.objects.filter(user=user, email_verified=False).update(
                    email_verified=True, email_verified_at=timezone.now()
                )
                messages.success(request, "Password updated. Please log in.")
                return redirect("login")

    return render(request, "creataura/reset_password.html", {"valid": True})


def user_logout(request):
    logout(request)
    return redirect("login")
