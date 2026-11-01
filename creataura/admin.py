from django.contrib import admin

from .models import (
    BankAccount,
    Bonus,
    Deposit,
    InvestmentPlan,
    Payment,
    ReferralBonus,
    UserProfile,
    WithdrawalMethod,
    WithdrawalBTC,
    WithdrawalXRP,
)


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
        "date_created",
    )
    list_filter = ("status", "cryptocoin", "date_created")
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
        "date_created",
    )
    list_filter = ("status", "cryptocoin", "date_created")
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
