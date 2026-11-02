from datetime import timedelta
import secrets

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.contrib.sessions.models import Session
from decimal import Decimal, InvalidOperation
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import SupportMessageForm

from .models import (
    BankAccount,
    Bonus,
    CryptoExchange,
    Deposit,
    DepositWallet,
    InvestmentPlan,
    KYCVerification,
    ProfitRecord,
    ReferralBonus,
    SupportMessage,
    UserProfile,
    UserInvestment,
    WithdrawalBTC,
    WithdrawalMethod,
    WithdrawalXRP,
)


def get_available_balance(user):
    approved_deposits = Deposit.objects.filter(
        user=user, status="approved"
    ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
    bonuses = Bonus.objects.filter(user=user).aggregate(
        total=models.Sum("amount")
    )["total"] or Decimal("0")
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

    completed_exchanges = CryptoExchange.objects.filter(
        user=user, status="completed",
    )
    usd_spent = sum(
        (
            record.from_amount
            for record in completed_exchanges
            if record.from_asset == "usd"
        ),
        Decimal("0"),
    )
    usd_received = sum(
        (
            record.to_amount
            for record in completed_exchanges
            if record.to_asset == "usd"
        ),
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


def home(request):
    return render(request, "creataura/index.html")


@login_required(login_url="login")
def dashboard(request):
    profile = getattr(request.user, "creataura_profile", None)
    full_name = (
        profile.full_name.strip()
        if profile and profile.full_name.strip()
        else request.user.get_full_name().strip()
        or request.user.username
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
        user=request.user,
        status="approved",
    )
    approved_xrp_withdrawals = WithdrawalXRP.objects.filter(
        user=request.user,
        status="approved",
    )
    approved_withdrawal_total = sum(
        (record.amount + record.charges for record in list(approved_btc_withdrawals) + list(approved_xrp_withdrawals)),
        Decimal("0"),
    )
    referral_total = ReferralBonus.objects.filter(
        referrer=request.user,
        status="paid",
    ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
    total_balance = get_available_balance(request.user)
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
        },
    )


@login_required(login_url="login")
def crypto_exchange(request):
    assets = (
        "usd", "btc", "eth", "ltc", "link",
        "bnb", "ada", "aave", "usdt", "bch", "xlm",
    )
    rates = {
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
    labels = {
        "usd": "USD",
        "btc": "BTC",
        "eth": "ETH",
        "ltc": "LTC",
        "link": "LINK",
        "bnb": "BNB",
        "ada": "ADA",
        "aave": "AAVE",
        "usdt": "USDT",
        "bch": "BCH",
        "xlm": "XLM",
    }

    completed = CryptoExchange.objects.filter(
        user=request.user,
        status="completed",
    )
    usd_spent = sum(
        (record.from_amount for record in completed if record.from_asset == "usd"),
        Decimal("0"),
    )
    usd_received = sum(
        (record.to_amount for record in completed if record.to_asset == "usd"),
        Decimal("0"),
    )
    account_balance = get_available_balance(request.user)

    asset_balances = {}
    for asset in assets:
        received = sum(
            (record.to_amount for record in completed if record.to_asset == asset),
            Decimal("0"),
        )
        sent = sum(
            (record.from_amount for record in completed if record.from_asset == asset),
            Decimal("0"),
        )
        asset_balances[asset] = received - sent

    if request.method == "POST":
        from_asset = request.POST.get("from_asset", "").lower()
        to_asset = request.POST.get("to_asset", "").lower()
        try:
            from_amount = Decimal(request.POST.get("from_amount", "").strip())
        except (InvalidOperation, AttributeError):
            from_amount = Decimal("0")

        if from_asset not in assets or to_asset not in assets or from_asset == to_asset:
            messages.error(request, "Choose two different assets.")
        elif from_amount <= 0 or not from_amount.is_finite():
            messages.error(request, "Enter a valid amount.")
        elif from_asset == "usd" and from_amount > account_balance:
            messages.error(request, "Insufficient account balance.")
        elif from_asset != "usd" and from_amount > asset_balances.get(from_asset, Decimal("0")):
            messages.error(request, f"Insufficient {labels[from_asset]} balance.")
        else:
            exchange_rate = rates[to_asset] / rates[from_asset]
            gross_value = from_amount * rates[from_asset]
            commission = gross_value * Decimal("0.02")
            to_amount = (gross_value - commission) / rates[to_asset]
            CryptoExchange.objects.create(
                user=request.user,
                from_asset=from_asset,
                to_asset=to_asset,
                from_amount=from_amount.quantize(Decimal("0.00000001")),
                to_amount=to_amount.quantize(Decimal("0.00000001")),
                exchange_rate=exchange_rate.quantize(Decimal("0.00000001")),
                commission=commission.quantize(Decimal("0.00000001")),
                status="completed",
            )
            messages.success(
                request,
                f"Exchange completed: {from_amount} {labels[from_asset]} to "
                f"{to_amount.quantize(Decimal('0.00000001'))} {labels[to_asset]}.",
            )
        return redirect("crypto_exchange")

    return render(
        request,
        "creataura/crypto_exchange.html",
        {
            "account_balance": account_balance,
            "asset_balances": asset_balances,
            "asset_labels": labels,
            "assets": assets,
            "exchange_records": completed[:10],
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
    return render(
        request,
        "creataura/kyc.html",
        {"kyc_verification": verification},
    )


@login_required(login_url="login")
def roi_history(request):
    records = ProfitRecord.objects.filter(user=request.user)
    total_profit = records.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
    return render(
        request,
        "creataura/roi_history.html",
        {"roi_records": records, "total_profit": total_profit},
    )


@login_required(login_url="login")
def withdraw_roi(request):
    total_profit = ProfitRecord.objects.filter(user=request.user).aggregate(
        total=models.Sum("amount")
    )["total"] or Decimal("0")

    btc_roi_withdrawals = WithdrawalBTC.objects.filter(
        user=request.user,
        source="roi",
    ).exclude(status="rejected")
    xrp_roi_withdrawals = WithdrawalXRP.objects.filter(
        user=request.user,
        source="roi",
    ).exclude(status="rejected")
    reserved_roi = sum(
        (
            record.amount
            for record in list(btc_roi_withdrawals) + list(xrp_roi_withdrawals)
        ),
        Decimal("0"),
    )
    available_roi = max(total_profit - reserved_roi, Decimal("0"))
    profile = getattr(request.user, "creataura_profile", None)
    bitcoin_address = profile.bitcoin_address if profile else ""

    if request.method == "POST":
        if available_roi <= 0:
            messages.error(request, "Nothing to withdraw at the moment!")
            return redirect("withdraw_roi")

        payment_mode = request.POST.get("payment_mode", "").strip().lower()
        try:
            amount = Decimal(request.POST.get("amount", "").strip())
        except (InvalidOperation, AttributeError):
            amount = Decimal("0")

        if payment_mode == "bitcoin":
            address = bitcoin_address.strip()
            if not address:
                messages.error(request, "Add your Bitcoin address in Settings first.")
            elif amount <= 0 or not amount.is_finite():
                messages.error(request, "Enter a valid withdrawal amount.")
            elif amount > available_roi:
                messages.error(request, "Amount exceeds your available ROI balance.")
            else:
                WithdrawalBTC.objects.create(
                    user=request.user,
                    cryptocoin="Bitcoin",
                    amount=amount,
                    status="pending",
                    source="roi",
                )
                messages.success(request, "ROI withdrawal submitted for approval.")
                return redirect("withdraw_roi")
        elif payment_mode == "xrp":
            address = request.POST.get("xrp_address", "").strip()
            if not address:
                messages.error(request, "Enter your XRP wallet address.")
            elif amount <= 0 or not amount.is_finite():
                messages.error(request, "Enter a valid withdrawal amount.")
            elif amount > available_roi:
                messages.error(request, "Amount exceeds your available ROI balance.")
            else:
                WithdrawalXRP.objects.create(
                    user=request.user,
                    cryptocoin="XRP",
                    amount=amount,
                    xrp_address=address,
                    status="pending",
                    source="roi",
                )
                messages.success(request, "ROI withdrawal submitted for approval.")
                return redirect("withdraw_roi")
        else:
            messages.error(request, "Select a valid payment method.")

    roi_withdrawals = []
    for withdrawal in list(btc_roi_withdrawals) + list(xrp_roi_withdrawals):
        roi_withdrawals.append(withdrawal)
    roi_withdrawals.sort(key=lambda record: record.date_created, reverse=True)
    if request.method == "GET" and available_roi <= 0:
        messages.error(request, "Nothing to withdraw at the moment!")

    return render(
        request,
        "creataura/withdraw_roi.html",
        {
            "total_profit": total_profit,
            "available_roi": available_roi,
            "bitcoin_address": bitcoin_address,
            "roi_withdrawals": roi_withdrawals,
        },
    )


@login_required(login_url="login")
def withdrawal(request):
    def balance():
        return get_available_balance(request.user)

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
            values = method_defaults[display_name]
            methods.append(
                {
                    "method_type": display_name,
                    **values,
                }
            )

    if request.method == "POST":
        method_type = request.POST.get("method_type", "").strip().lower()
        if method_type not in ("bitcoin", "xrp"):
            messages.error(request, "Select a valid withdrawal method.")
            return redirect("withdrawal")

        display_name = "Bitcoin" if method_type == "bitcoin" else "XRP"
        method = next(
            (
                item
                for item in methods
                if str(
                    item["method_type"] if isinstance(item, dict) else item.method_type
                ).lower() == method_type
            ),
            None,
        )
        try:
            amount = Decimal(request.POST.get("amount", "").strip())
        except (InvalidOperation, AttributeError):
            amount = Decimal("0")

        minimum = method["minimum_amount"] if isinstance(method, dict) else method.minimum_amount
        maximum = method["maximum_amount"] if isinstance(method, dict) else method.maximum_amount
        charge_type = method["charge_type"] if isinstance(method, dict) else method.charge_type
        charge_amount = method["charge_amount"] if isinstance(method, dict) else method.charge_amount
        charges = (
            amount * charge_amount / Decimal("100")
            if "percentage" in charge_type.lower()
            else charge_amount
        )

        if amount <= 0 or not amount.is_finite():
            messages.error(request, "Enter a valid withdrawal amount.")
        elif amount < minimum or amount > maximum:
            messages.error(
                request,
                f"Amount must be between ${minimum} and ${maximum}.",
            )
        elif amount + charges > balance():
            messages.error(request, "Insufficient account balance.")
        else:
            otpcode = request.POST.get("otpcode", "").strip()
            if method_type == "bitcoin":
                profile = getattr(request.user, "creataura_profile", None)
                if not profile or not profile.bitcoin_address.strip():
                    messages.error(request, "Add your Bitcoin address in withdrawal settings.")
                    return redirect("settings")
                WithdrawalBTC.objects.create(
                    user=request.user,
                    cryptocoin="Bitcoin",
                    amount=amount,
                    otpcode=otpcode,
                    charges=charges,
                    status="pending",
                )
            else:
                xrp_address = request.POST.get("xrp_address", "").strip()
                if not xrp_address:
                    messages.error(request, "Enter your XRP address.")
                    return redirect("withdrawal")
                WithdrawalXRP.objects.create(
                    user=request.user,
                    cryptocoin="XRP",
                    amount=amount,
                    otpcode=otpcode,
                    xrp_address=xrp_address,
                    charges=charges,
                    status="pending",
                )
            messages.success(request, f"{display_name} withdrawal request submitted.")
        return redirect("withdrawal")

    profile = getattr(request.user, "creataura_profile", None)
    return render(
        request,
        "creataura/withdrawal.html",
        {
            "withdrawal_methods": methods,
            "available_balance": balance(),
            "bitcoin_address": profile.bitcoin_address if profile else "",
        },
    )


@login_required(login_url="login")
def withdrawal_btc(request):
    profile = getattr(request.user, "creataura_profile", None)
    method = WithdrawalMethod.objects.filter(
        method_type__iexact="Bitcoin",
        is_active=True,
    ).first()
    minimum = method.minimum_amount if method else Decimal("10")
    maximum = method.maximum_amount if method else Decimal("50000000")
    charge_type = method.charge_type if method else "Percentage"
    charge_amount = method.charge_amount if method else Decimal("0")

    available_balance = get_available_balance(request.user)

    if request.method == "POST":
        if request.POST.get("action") == "request_otp":
            otp = secrets.token_hex(3).upper()
            request.session["btc_withdrawal_otp"] = otp
            if profile and profile.email_withdrawal_otp and request.user.email:
                send_mail(
                    "Createaura Bitcoin Withdrawal OTP",
                    f"Your Bitcoin withdrawal OTP is {otp}.",
                    None,
                    [request.user.email],
                    fail_silently=True,
                )
            messages.success(request, "Withdrawal OTP sent to your email.")
            return redirect("withdrawal_btc")

        try:
            amount = Decimal(request.POST.get("amount", "").strip())
        except (InvalidOperation, AttributeError):
            amount = Decimal("0")
        otp_code = request.POST.get("otpcode", "").strip().upper()
        expected_otp = request.session.get("btc_withdrawal_otp", "")

        charges = (
            amount * charge_amount / Decimal("100")
            if "percentage" in charge_type.lower()
            else charge_amount
        )
        if amount <= 0 or not amount.is_finite():
            messages.error(request, "Enter a valid withdrawal amount.")
        elif amount < minimum or amount > maximum:
            messages.error(
                request,
                f"Amount must be between ${minimum} and ${maximum}.",
            )
        elif amount + charges > available_balance:
            messages.error(request, "Insufficient account balance.")
        elif not expected_otp:
            messages.error(request, "Request an OTP before completing withdrawal.")
        elif otp_code != expected_otp:
            messages.error(request, "The withdrawal OTP is incorrect.")
        else:
            if not profile or not profile.bitcoin_address.strip():
                messages.error(request, "Add your Bitcoin address in withdrawal settings.")
                return redirect("settings")
            WithdrawalBTC.objects.create(
                user=request.user,
                cryptocoin="Bitcoin",
                amount=amount,
                otpcode=otp_code,
                charges=charges,
                status="pending",
            )
            request.session.pop("btc_withdrawal_otp", None)
            messages.success(request, "Bitcoin withdrawal request submitted.")
        return redirect("withdrawal_btc")

    return render(
        request,
        "creataura/withdrawal_btc.html",
        {
            "bitcoin_address": profile.bitcoin_address if profile else "",
            "minimum_amount": minimum,
            "maximum_amount": maximum,
            "available_balance": available_balance,
        },
    )


@login_required(login_url="login")
def withdrawal_xrp(request):
    profile = getattr(request.user, "creataura_profile", None)
    method = WithdrawalMethod.objects.filter(
        method_type__iexact="XRP",
        is_active=True,
    ).first()
    minimum = method.minimum_amount if method else Decimal("10")
    maximum = method.maximum_amount if method else Decimal("1000000")
    charge_type = method.charge_type if method else "Percentage"
    charge_amount = method.charge_amount if method else Decimal("0")

    available_balance = get_available_balance(request.user)

    if request.method == "POST":
        if request.POST.get("action") == "request_otp":
            otp = secrets.token_hex(3).upper()
            request.session["xrp_withdrawal_otp"] = otp
            if (
                profile
                and profile.email_withdrawal_otp
                and request.user.email
            ):
                send_mail(
                    "Createaura XRP Withdrawal OTP",
                    f"Your XRP withdrawal OTP is {otp}.",
                    None,
                    [request.user.email],
                    fail_silently=True,
                )
            messages.success(request, "Withdrawal OTP sent to your email.")
            return redirect("withdrawal_xrp")

        try:
            amount = Decimal(request.POST.get("amount", "").strip())
        except (InvalidOperation, AttributeError):
            amount = Decimal("0")
        otp_code = request.POST.get("otpcode", "").strip().upper()
        xrp_address = request.POST.get("xrp_address", "").strip()
        expected_otp = request.session.get("xrp_withdrawal_otp", "")
        charges = (
            amount * charge_amount / Decimal("100")
            if "percentage" in charge_type.lower()
            else charge_amount
        )

        if amount <= 0 or not amount.is_finite():
            messages.error(request, "Enter a valid withdrawal amount.")
        elif amount < minimum or amount > maximum:
            messages.error(
                request,
                f"Amount must be between ${minimum} and ${maximum}.",
            )
        elif amount + charges > available_balance:
            messages.error(request, "Insufficient account balance.")
        elif not xrp_address:
            messages.error(request, "Enter your XRP wallet address.")
        elif not expected_otp:
            messages.error(request, "Request an OTP before completing withdrawal.")
        elif otp_code != expected_otp:
            messages.error(request, "The withdrawal OTP is incorrect.")
        else:
            WithdrawalXRP.objects.create(
                user=request.user,
                cryptocoin="XRP",
                amount=amount,
                otpcode=otp_code,
                xrp_address=xrp_address,
                charges=charges,
                status="pending",
            )
            request.session.pop("xrp_withdrawal_otp", None)
            messages.success(request, "XRP withdrawal request submitted.")
        return redirect("withdrawal_xrp")

    return render(
        request,
        "creataura/withdrawal_xrp.html",
        {
            "minimum_amount": minimum,
            "maximum_amount": maximum,
            "available_balance": available_balance,
        },
    )


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
        elif amount <= 0 or not amount.is_finite():
            messages.error(request, "Enter a valid deposit amount.")
        else:
            request.session["deposit_amount"] = str(amount)
            request.session["deposit_mode"] = payment_mode
            return redirect("deposit_payment", payment_mode=payment_mode)

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

    defaults = {
        "bitcoin": (
            "bclqe0eqqpc6k4f9xkwzggp2mmpn8sh9nv32yuvv7m",
            "BTC",
        ),
        "ethereum": (
            "0x0000000000000000000000000000000000000000",
            "ETH",
        ),
        "xrp": (
            "r000000000000000000000000000000000000000",
            "XRP",
        ),
    }
    wallet = DepositWallet.objects.filter(
        crypto=payment_mode,
        is_active=True,
    ).first()
    wallet_address, network_type = defaults[payment_mode]
    if wallet:
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
    bitcoin_withdrawals = WithdrawalBTC.objects.filter(user=request.user)
    xrp_withdrawals = WithdrawalXRP.objects.filter(user=request.user)
    withdrawals = []
    for withdrawal in list(bitcoin_withdrawals) + list(xrp_withdrawals):
        withdrawals.append(
            {
                "amount": withdrawal.amount,
                "amount_with_charges": withdrawal.amount + withdrawal.charges,
                "receiving_mode": withdrawal.cryptocoin,
                "status": withdrawal.status,
                "date_created": withdrawal.date_created,
            }
        )
    withdrawals.sort(key=lambda record: record["date_created"], reverse=True)
    other_transactions = []
    signup_bonus = Bonus.objects.filter(
        user=request.user,
        plan_narration="SignUp Bonus",
    ).first()
    if signup_bonus:
        other_transactions.append(
            {
                "amount": signup_bonus.amount,
                "type": "Bonus",
                "plan_narration": "SignUp Bonus",
                "date_created": signup_bonus.date_created,
            }
        )
    for investment in UserInvestment.objects.filter(user=request.user):
        other_transactions.append(
            {
                "amount": investment.amount,
                "type": "Investment",
                "plan_narration": investment.plan.name,
                "status": investment.status,
                "date_created": investment.date_created,
            }
        )
    other_transactions.sort(
        key=lambda record: record["date_created"],
        reverse=True,
    )
    return render(
        request,
        "creataura/transactions.html",
        {
            "deposits": Deposit.objects.filter(user=request.user),
            "bitcoin_withdrawals": bitcoin_withdrawals,
            "xrp_withdrawals": xrp_withdrawals,
            "withdrawals": withdrawals,
            "other_transactions": other_transactions,
        },
    )


@login_required(login_url="login")
def investments(request):
    plans = InvestmentPlan.objects.filter(is_active=True)
    user_investments = UserInvestment.objects.filter(user=request.user)
    if not plans.exists():
        plans = [
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
    return render(
        request,
        "creataura/investments.html",
        {
            "plans": plans,
            "user_investments": user_investments,
            "available_balance": get_available_balance(request.user),
        },
    )


@login_required(login_url="login")
@require_POST
def join_investment(request, plan_id):
    plan = InvestmentPlan.objects.filter(id=plan_id, is_active=True).first()
    if not plan:
        messages.error(request, "That investment plan is no longer available.")
        return redirect("invest")
    raw_amount = request.POST.get("amount", "").strip()
    try:
        amount = Decimal(raw_amount)
    except (InvalidOperation, ValueError):
        messages.error(request, "Enter a valid investment amount.")
        return redirect("invest")
    if not amount.is_finite():
        messages.error(request, "Enter a valid investment amount.")
        return redirect("invest")
    if amount < plan.minimum_deposit:
        messages.error(request, f"The minimum investment amount is ${plan.minimum_deposit}.")
        return redirect("invest")
    if amount > plan.maximum_deposit:
        messages.error(request, f"The maximum investment amount is ${plan.maximum_deposit}.")
        return redirect("invest")
    with transaction.atomic():
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

    referred_profiles = UserProfile.objects.select_related("user").filter(
        referral_id__iexact=referral_id
    ).order_by("-user__date_joined")

    referred_users = [
        {
            "user": referred_profile.user,
            "profile": referred_profile,
            "parent": profile,
        }
        for referred_profile in referred_profiles
    ]

    referrer = None
    if profile and profile.referral_id:
        referrer_profile = UserProfile.objects.select_related("user").filter(
            user__username__iexact=profile.referral_id
        ).first()
        if referrer_profile:
            referrer = referrer_profile.user

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
    return render(
        request,
        "creataura/support.html",
        {"support_form": SupportMessageForm()},
    )


@login_required(login_url="login")
def settings(request):
    profile = getattr(request.user, "creataura_profile", None)
    if request.method == "POST":
        if request.POST.get("settings_action") == "withdrawals":
            withdrawal_account, _ = BankAccount.objects.get_or_create(user=request.user)
            withdrawal_account.bank_name = request.POST.get("bank_name", "").strip()
            withdrawal_account.account_name = request.POST.get("account_name", "").strip()
            withdrawal_account.account_number = request.POST.get("account_number", "").strip()
            withdrawal_account.swift_code = request.POST.get("swift_code", "").strip()
            withdrawal_account.ethereum_address = request.POST.get("ethereum_address", "").strip()
            withdrawal_account.litecoin_address = request.POST.get("litecoin_address", "").strip()
            withdrawal_account.save()
            messages.success(request, "Withdrawal settings saved successfully.")
        elif request.POST.get("settings_action") == "password":
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
                    login(request, request.user)
                    messages.success(request, "Password updated successfully.")
        elif request.POST.get("settings_action") == "other":
            if profile is None:
                profile = UserProfile.objects.create(
                    user=request.user,
                    full_name=request.user.get_full_name() or request.user.username,
                    phone_number="",
                    bitcoin_address="",
                    country="",
                )
            profile.email_withdrawal_otp = request.POST.get("email_withdrawal_otp") == "yes"
            profile.email_profit_notification = request.POST.get("email_profit_notification") == "yes"
            profile.email_plan_expiry_notification = request.POST.get("email_plan_expiry_notification") == "yes"
            profile.save(
                update_fields=[
                    "email_withdrawal_otp",
                    "email_profit_notification",
                    "email_plan_expiry_notification",
                ]
            )
            messages.success(request, "Other settings saved successfully.")
        else:
            full_name = request.POST.get("full_name", "").strip()
            email = request.POST.get("email", "").strip().lower()
            phone_number = request.POST.get("phone_number", "").strip()
            full_address = request.POST.get("full_address", "").strip()

            if not all([full_name, email, phone_number, full_address]):
                messages.error(request, "Please complete all required fields.")
            elif User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
                messages.error(request, "That email is already registered.")
            else:
                request.user.email = email
                request.user.first_name = full_name
                request.user.save(update_fields=["email", "first_name"])
                profile.full_name = full_name
                profile.phone_number = phone_number
                profile.country = full_address
                profile.save(update_fields=["full_name", "phone_number", "country"])
                messages.success(request, "Profile updated successfully.")
        return redirect("settings")

    withdrawal_account = getattr(request.user, "withdrawal_account", None)

    return render(
        request,
        "creataura/settings.html",
        {
            "profile": profile or request.user,
            "withdrawal_account": withdrawal_account,
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
        action = request.POST.get("security_action", "")
        password = request.POST.get("password", "")

        if action == "two_factor":
            if not password:
                messages.error(request, "Confirm your password to continue.")
            elif not request.user.check_password(password):
                messages.error(request, "Your password is incorrect.")
            else:
                profile.two_factor_enabled = not profile.two_factor_enabled
                profile.save(update_fields=["two_factor_enabled"])
                if profile.two_factor_enabled:
                    messages.success(request, "Two factor authentication has been enabled.")
                else:
                    messages.success(request, "Two factor authentication has been disabled.")
            return redirect("advanced_account_settings")

        if action == "logout_other_sessions":
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

        if action == "delete_account":
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
    for session in Session.objects.filter(expire_date__gte=timezone.now()).order_by("-expire_date"):
        data = session.get_decoded()
        if str(data.get("_auth_user_id")) != str(request.user.pk):
            continue
        browser_sessions.append(
            {
                "is_current": session.session_key == current_key,
                "expire_date": session.expire_date,
                "ip_address": request.META.get("REMOTE_ADDR", "") if session.session_key == current_key else "",
            }
        )

    return render(
        request,
        "creataura/advanced_account_settings.html",
        {
            "profile": profile,
            "browser_sessions": browser_sessions,
        },
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

    return render(
        request,
        "creataura/support.html",
        {"support_form": form},
        status=400,
    )


COUNTRIES = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola",
    "Antigua and Barbuda", "Argentina", "Armenia", "Australia", "Austria",
    "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados",
    "Belarus", "Belgium", "Belize", "Benin", "Bhutan",
    "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei",
    "Bulgaria", "Burkina Faso", "Burundi", "Cabo Verde", "Cambodia",
    "Cameroon", "Canada", "Central African Republic", "Chad", "Chile",
    "China", "Colombia", "Comoros", "Congo (Democratic Republic)",
    "Congo (Republic)", "Costa Rica", "Cote d'Ivoire", "Croatia", "Cuba",
    "Cyprus", "Czechia", "Denmark", "Djibouti", "Dominica",
    "Dominican Republic", "Ecuador", "Egypt", "El Salvador",
    "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia",
    "Fiji", "Finland", "France", "Gabon", "Gambia", "Georgia",
    "Germany", "Ghana", "Greece", "Grenada", "Guatemala", "Guinea",
    "Guinea-Bissau", "Guyana", "Haiti", "Honduras", "Hungary",
    "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland",
    "Israel", "Italy", "Jamaica", "Japan", "Jordan", "Kazakhstan",
    "Kenya", "Kiribati", "Kuwait", "Kyrgyzstan", "Laos", "Latvia",
    "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein",
    "Lithuania", "Luxembourg", "Madagascar", "Malawi", "Malaysia",
    "Maldives", "Mali", "Malta", "Marshall Islands", "Mauritania",
    "Mauritius", "Mexico", "Micronesia", "Moldova", "Monaco", "Mongolia",
    "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia",
    "Nauru", "Nepal", "Netherlands", "New Zealand", "Nicaragua",
    "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway",
    "Oman", "Pakistan", "Palau", "Palestine", "Panama",
    "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland",
    "Portugal", "Qatar", "Romania", "Russia", "Rwanda",
    "Saint Kitts and Nevis", "Saint Lucia",
    "Saint Vincent and the Grenadines", "Samoa", "San Marino",
    "Sao Tome and Principe", "Saudi Arabia", "Senegal", "Serbia",
    "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Slovenia",
    "Solomon Islands", "Somalia", "South Africa", "South Korea",
    "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden",
    "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania",
    "Thailand", "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago",
    "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine",
    "United Arab Emirates", "United Kingdom", "United States",
    "Uruguay", "Uzbekistan", "Vanuatu", "Vatican City", "Venezuela",
    "Vietnam", "Yemen", "Zambia", "Zimbabwe",
]


def register(request, referral_id=None):
    if request.user.is_authenticated:
        return redirect("dashboard")

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

        if not all([username, email, full_name, phone_number, bitcoin_address, country, password, password_again]):
            messages.error(request, "Please complete all required fields.")
        elif password != password_again:
            messages.error(request, "Passwords do not match.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "That username is already in use.")
        elif User.objects.filter(email=email).exists():
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
                    Bonus.objects.get_or_create(
                        user=user,
                        amount=Decimal("5.00"),
                        plan_narration="SignUp Bonus",
                    )
                messages.success(request, "Account created successfully. Please log in.")
                return redirect("login")

    return render(
        request,
        "creataura/register.html",
        {"countries": COUNTRIES, "initial_referral_id": referral_id or ""},
    )


def user_login(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        user = User.objects.filter(email=email).first()
        authenticated_user = authenticate(
            request,
            username=user.username if user else email,
            password=password,
        )
        if authenticated_user is not None:
            login(request, authenticated_user)
            if request.POST.get("remember"):
                request.session.set_expiry(14 * 24 * 60 * 60)
            else:
                request.session.set_expiry(12 * 60 * 60)
            return redirect(request.GET.get("next") or "dashboard")
        messages.error(request, "Invalid email or password.")

    return render(request, "creataura/login.html")


def user_logout(request):
    logout(request)
    return redirect("login")
