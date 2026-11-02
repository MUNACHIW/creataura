from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from decimal import Decimal


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
    email_withdrawal_otp = models.BooleanField(default=True)
    email_profit_notification = models.BooleanField(default=True)
    email_plan_expiry_notification = models.BooleanField(default=True)
    two_factor_enabled = models.BooleanField(default=False)

    def __str__(self):
        return self.full_name


class InvestmentPlan(models.Model):
    name = models.CharField(max_length=100, default="Beginner plan")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Amount users can invest in this plan.",
    )
    minimum_deposit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    maximum_deposit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    daily_roi = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Daily ROI percentage.",
    )
    weekly_roi = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Weekly ROI percentage.",
    )
    gift_bonus = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Gift bonus percentage.",
    )
    duration_days = models.PositiveIntegerField(
        help_text="Investment duration in days.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["minimum_deposit", "name"]
        verbose_name = "Investment plan"
        verbose_name_plural = "Investment plans"

    def clean(self):
        super().clean()
        if self.maximum_deposit < self.minimum_deposit:
            raise ValidationError(
                {
                    "maximum_deposit": "Maximum deposit cannot be less than minimum deposit."
                }
            )

    def __str__(self):
        return self.name


class UserInvestment(models.Model):
    STATUS_CHOICES = (
        ("active", "Active"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="investments",
    )
    plan = models.ForeignKey(
        InvestmentPlan,
        on_delete=models.PROTECT,
        related_name="user_investments",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )
    date_created = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-date_created"]
        verbose_name = "User investment"
        verbose_name_plural = "User investments"

    def __str__(self):
        return f"{self.user.username} - {self.plan.name}"


class KYCVerification(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("verified", "Verified"),
        ("rejected", "Rejected"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kyc_verification",
    )
    passport_photo = models.ImageField(upload_to="kyc/passports/")
    identity_photo = models.ImageField(upload_to="kyc/identity/")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    date_created = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date_created"]
        verbose_name = "KYC verification"
        verbose_name_plural = "KYC verifications"

    def __str__(self):
        return f"{self.user.username} - {self.status.title()}"


class ProfitRecord(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profit_records",
    )
    investment = models.ForeignKey(
        UserInvestment,
        on_delete=models.SET_NULL,
        related_name="profit_records",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    narration = models.CharField(max_length=255, default="ROI Profit")
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_created"]
        verbose_name = "Profit record"
        verbose_name_plural = "Profit records"

    def __str__(self):
        return f"{self.user.username} - ${self.amount}"


class CryptoExchange(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("rejected", "Rejected"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="crypto_exchanges",
    )
    from_asset = models.CharField(max_length=20)
    to_asset = models.CharField(max_length=20)
    from_amount = models.DecimalField(max_digits=12, decimal_places=8)
    to_amount = models.DecimalField(max_digits=12, decimal_places=8)
    exchange_rate = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        default=Decimal("0"),
    )
    commission = models.DecimalField(
        max_digits=12,
        decimal_places=8,
        default=Decimal("0"),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="completed",
    )
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_created"]
        verbose_name = "Crypto exchange"
        verbose_name_plural = "Crypto exchanges"

    def __str__(self):
        return (
            f"{self.user.username} - {self.from_amount} "
            f"{self.from_asset.upper()} to {self.to_asset.upper()}"
        )


class Deposit(models.Model):
    PAYMENT_MODES = (
        ("bitcoin", "Bitcoin"),
        ("usdt_tron20", "USDT (TRON20)"),
        ("ethereum", "Ethereum"),
        ("xrp", "XRP"),
    )
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="deposits",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    payment_mode = models.CharField(
        max_length=20,
        choices=PAYMENT_MODES,
        default="bitcoin",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    network_type = models.CharField(max_length=50, blank=True)
    wallet_address = models.CharField(max_length=255, blank=True)
    proof_of_payment = models.FileField(
        upload_to="payment_proofs/",
        blank=True,
        null=True,
    )
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_created"]
        verbose_name = "Deposit"
        verbose_name_plural = "Deposits"

    def __str__(self):
        return f"{self.user.username} - {self.amount}"


class DepositWallet(models.Model):
    CRYPTO_CHOICES = (
        ("bitcoin", "Bitcoin"),
        ("ethereum", "Ethereum"),
        ("xrp", "XRP"),
    )
    crypto = models.CharField(max_length=20, choices=CRYPTO_CHOICES, unique=True)
    wallet_address = models.CharField(max_length=255)
    network_type = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["crypto"]
        verbose_name = "Deposit wallet"
        verbose_name_plural = "Deposit wallets"

    def __str__(self):
        return f"{self.get_crypto_display()} - {self.wallet_address}"


class Payment(models.Model):
    CRYPTO_CHOICES = (
        ("bitcoin", "Bitcoin"),
        ("usdt_tron20", "USDT (TRON20)"),
        ("ethereum", "Ethereum"),
        ("xrp", "XRP"),
    )
    NETWORK_CHOICES = (
        ("bitcoin", "Bitcoin Network"),
        ("tron20", "TRON20"),
        ("ethereum", "Ethereum Network"),
        ("xrp_ledger", "XRP Ledger"),
        ("other", "Other"),
    )

    crypto = models.CharField(
        max_length=20,
        choices=CRYPTO_CHOICES,
    )
    crypto_address = models.CharField(max_length=255)
    network_type = models.CharField(
        max_length=20,
        choices=NETWORK_CHOICES,
    )
    proof_of_payment = models.FileField(upload_to="payment_proofs/")
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_created"]
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

    def __str__(self):
        return f"{self.get_crypto_display()} - {self.crypto_address}"


class WithdrawalMethod(models.Model):
    method_type = models.CharField(max_length=100)
    minimum_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    maximum_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    charge_type = models.CharField(
        max_length=100,
        help_text="Charge type entered by the admin, such as Percentage.",
    )
    charge_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Charge amount. Enter the percentage value when charge type is percentage.",
    )
    duration = models.CharField(
        max_length=150,
        help_text="Processing duration entered by the admin.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["method_type"]
        verbose_name = "Withdrawal method"
        verbose_name_plural = "Withdrawal methods"

    def clean(self):
        super().clean()
        if self.maximum_amount < self.minimum_amount:
            raise ValidationError(
                {"maximum_amount": "Maximum amount cannot be less than minimum amount."}
            )

    def __str__(self):
        return self.method_type


class WithdrawalBTC(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bitcoin_withdrawals",
    )
    cryptocoin = models.CharField(max_length=100, default="Bitcoin")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    otpcode = models.CharField(max_length=10, blank=True)
    charges = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    source = models.CharField(
        max_length=20,
        choices=(("balance", "Balance"), ("roi", "ROI")),
        default="balance",
    )
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_created"]
        verbose_name = "Bitcoin withdrawal"
        verbose_name_plural = "Bitcoin withdrawals"

    def __str__(self):
        return f"{self.user.username} - {self.amount} {self.cryptocoin}"


class WithdrawalXRP(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="xrp_withdrawals",
    )
    cryptocoin = models.CharField(max_length=100, default="XRP")
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    otpcode = models.CharField(max_length=10, blank=True)
    xrp_address = models.CharField(max_length=255)
    charges = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    source = models.CharField(
        max_length=20,
        choices=(("balance", "Balance"), ("roi", "ROI")),
        default="balance",
    )
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_created"]
        verbose_name = "XRP withdrawal"
        verbose_name_plural = "XRP withdrawals"

    def __str__(self):
        return f"{self.user.username} - {self.amount} {self.cryptocoin}"


class Bonus(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bonuses",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    plan_narration = models.CharField(max_length=255)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_created"]
        verbose_name = "Bonus"
        verbose_name_plural = "Bonuses"

    def __str__(self):
        return f"{self.user.username} - {self.amount}"


class BankAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="withdrawal_account",
        null=True,
        blank=True,
    )
    bank_name = models.CharField(max_length=150, blank=True)
    account_name = models.CharField(max_length=150, blank=True)
    account_number = models.CharField(max_length=100, blank=True)
    swift_code = models.CharField(max_length=50, blank=True)
    bitcoin_address = models.CharField(max_length=255, blank=True)
    ethereum_address = models.CharField(max_length=255, blank=True)
    litecoin_address = models.CharField(max_length=255, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["bank_name", "account_name"]
        verbose_name = "Bank account"
        verbose_name_plural = "Bank accounts"

    def __str__(self):
        if self.account_name:
            return self.account_name
        if self.bank_name:
            return self.bank_name
        return "Payment account details"


class ReferralBonus(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
    )

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_bonuses_received",
    )
    referred_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_bonuses",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_created"]
        verbose_name = "Referral bonus"
        verbose_name_plural = "Referral bonuses"

    def __str__(self):
        return f"{self.referrer.username} - {self.referred_user.username} - {self.amount}"


class SupportMessage(models.Model):
    STATUS_CHOICES = (
        ("new", "New"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_messages",
    )
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="new",
    )
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_created"]
        verbose_name = "Support message"
        verbose_name_plural = "Support messages"

    def __str__(self):
        return f"{self.user.username} - {self.subject}"
