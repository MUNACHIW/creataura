from django.contrib import admin
from django.contrib.auth.models import User
from django.core.mail import send_mail

from .models import (
    BankAccount,
    Bonus,
    CryptoExchange,
    Deposit,
    DepositWallet,
    InvestmentPlan, UserInvestment,
    KYCVerification,
    Payment,
    ProfitRecord,
    ReferralBonus,
    UserProfile,
    WithdrawalMethod,
    WithdrawalBTC,
    WithdrawalXRP,
    SupportMessage,
    Notification,
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "send_to_all", "email_sent", "created_at")
    list_filter = ("send_to_all", "email_sent", "created_at")
    search_fields = ("title", "message")
    filter_horizontal = ("recipients",)
    readonly_fields = ("email_sent", "created_at")
    fields = (
        "title",
        "message",
        "send_to_all",
        "recipients",
        "email_sent",
        "created_at",
    )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        notification = form.instance
        if notification.send_to_all:
            notification.recipients.set(
                User.objects.filter(is_active=True)
            )

        if not notification.email_sent:
            recipient_users = notification.recipients.select_related()
            recipient_emails = [
                user.email for user in recipient_users
                if user.email and not user.is_staff
            ]
            if notification.send_to_all:
                recipient_emails = [
                    user.email for user in User.objects.filter(is_active=True)
                    if user.email and not user.is_staff
                ]
            if recipient_emails:
                send_mail(
                    notification.title,
                    notification.message,
                    None,
                    recipient_emails,
                    fail_silently=True,
                )
            notification.email_sent = True
            notification.save(update_fields=["email_sent"])


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "country", "phone_number")
    search_fields = ("full_name", "user__username", "user__email", "phone_number")


@admin.register(InvestmentPlan)
class InvestmentPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "amount",
        "minimum_deposit",
        "maximum_deposit",
        "daily_roi",
        "weekly_roi",
        "gift_bonus",
        "duration_days",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("name",)
    list_editable = (
        "amount",
        "minimum_deposit",
        "maximum_deposit",
        "daily_roi",
        "weekly_roi",
        "gift_bonus",
        "duration_days",
        "is_active",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserInvestment)
class UserInvestmentAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "amount", "status", "date_created", "expires_at")
    list_filter = ("status", "date_created", "plan")
    search_fields = ("user__username", "user__email", "plan__name")
    readonly_fields = ("date_created",)


@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "payment_mode", "status", "date_created")
    list_filter = ("status", "payment_mode", "date_created")
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    list_editable = ("status",)
    readonly_fields = ("date_created",)


@admin.register(DepositWallet)
class DepositWalletAdmin(admin.ModelAdmin):
    list_display = ("crypto", "wallet_address", "network_type", "is_active", "updated_at")
    list_filter = ("crypto", "is_active")
    search_fields = ("wallet_address",)
    list_editable = ("is_active",)
    readonly_fields = ("updated_at",)


@admin.register(CryptoExchange)
class CryptoExchangeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "from_asset",
        "from_amount",
        "to_asset",
        "to_amount",
        "status",
        "date_created",
    )
    list_filter = ("status", "from_asset", "to_asset", "date_created")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("date_created",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "crypto",
        "crypto_address",
        "network_type",
        "proof_of_payment",
        "date_created",
    )
    list_filter = ("crypto", "network_type", "date_created")
    search_fields = ("crypto_address",)
    readonly_fields = ("date_created",)


@admin.register(WithdrawalMethod)
class WithdrawalMethodAdmin(admin.ModelAdmin):
    list_display = (
        "method_type",
        "minimum_amount",
        "maximum_amount",
        "charge_type",
        "charge_amount",
        "duration",
        "is_active",
    )
    list_filter = ("is_active", "charge_type")
    search_fields = ("method_type", "charge_type", "duration")
    list_editable = (
        "minimum_amount",
        "maximum_amount",
        "charge_type",
        "charge_amount",
        "duration",
        "is_active",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(WithdrawalBTC)
class WithdrawalBTCAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "cryptocoin",
        "amount",
        "otpcode",
        "charges",
        "status",
        "source",
        "date_created",
    )
    list_filter = ("status", "source", "cryptocoin", "date_created")
    search_fields = ("user__username", "user__email", "cryptocoin", "otpcode")
    list_editable = ("status",)
    readonly_fields = ("date_created",)


@admin.register(WithdrawalXRP)
class WithdrawalXRPAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "cryptocoin",
        "amount",
        "otpcode",
        "xrp_address",
        "charges",
        "status",
        "source",
        "date_created",
    )
    list_filter = ("status", "source", "cryptocoin", "date_created")
    search_fields = (
        "user__username",
        "user__email",
        "cryptocoin",
        "otpcode",
        "xrp_address",
    )
    list_editable = ("status",)
    readonly_fields = ("date_created",)


@admin.register(Bonus)
class BonusAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "plan_narration", "date_created")
    list_filter = ("date_created",)
    search_fields = (
        "user__username",
        "user__email",
        "plan_narration",
    )
    readonly_fields = ("date_created",)


@admin.register(ProfitRecord)
class ProfitRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "narration", "investment", "date_created")
    list_filter = ("date_created",)
    search_fields = ("user__username", "user__email", "narration")
    readonly_fields = ("date_created",)


@admin.register(KYCVerification)
class KYCVerificationAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "passport_photo", "identity_photo", "date_created")
    list_filter = ("status", "date_created")
    search_fields = ("user__username", "user__email")
    list_editable = ("status",)
    readonly_fields = ("date_created", "updated_at")


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = (
        "bank_name",
        "account_name",
        "account_number",
        "swift_code",
        "bitcoin_address",
        "ethereum_address",
        "litecoin_address",
    )
    search_fields = (
        "bank_name",
        "account_name",
        "account_number",
        "swift_code",
        "bitcoin_address",
        "ethereum_address",
        "litecoin_address",
    )
    readonly_fields = ("date_created", "updated_at")


@admin.register(ReferralBonus)
class ReferralBonusAdmin(admin.ModelAdmin):
    list_display = (
        "referrer",
        "referred_user",
        "amount",
        "percentage",
        "status",
        "date_created",
    )
    list_filter = ("status", "date_created")
    search_fields = (
        "referrer__username",
        "referrer__email",
        "referred_user__username",
        "referred_user__email",
    )
    list_editable = ("status",)
    readonly_fields = ("date_created",)


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ("user", "subject", "status", "date_created")
    list_filter = ("status", "date_created")
    search_fields = (
        "user__username",
        "user__email",
        "subject",
        "message",
    )
    list_editable = ("status",)
    readonly_fields = ("user", "subject", "message", "date_created")
