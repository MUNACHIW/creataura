from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from decimal import Decimal

from .models import (
    BankAccount,
    Bonus,
    CryptoExchange,
    Deposit,
    InvestmentPlan,
    KYCVerification,
    ProfitRecord,
    ReferralBonus,
    SupportMessage,
    UserInvestment,
    WithdrawalBTC,
    WithdrawalXRP,
)
from .models import UserProfile


class SupportMessageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="support-user",
            email="support@example.com",
            password="test-password",
        )
        self.client.login(username="support-user", password="test-password")

    def test_support_page_is_rendered_for_authenticated_user(self):
        response = self.client.get(reverse("support"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/support.html")
        self.assertContains(response, 'action="/support/submit/"')

    def test_support_message_is_submitted(self):
        response = self.client.post(
            reverse("support_submit"),
            {"subject": "Deposit issue", "message": "My deposit has not appeared."},
        )

        self.assertRedirects(response, reverse("support"))
        support_message = SupportMessage.objects.get()
        self.assertEqual(support_message.user, self.user)
        self.assertEqual(support_message.subject, "Deposit issue")
        self.assertEqual(support_message.status, "new")

    def test_empty_support_message_is_rejected(self):
        response = self.client.post(
            reverse("support_submit"),
            {"subject": "", "message": ""},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(SupportMessage.objects.count(), 0)


class SettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="settings-user",
            email="settings@example.com",
            password="test-password",
            first_name="Settings User",
        )
        UserProfile.objects.create(
            user=self.user,
            full_name="Settings User",
            phone_number="+123456789",
            bitcoin_address="test-address",
            country="United States",
        )
        self.user.set_password("settings-password")
        self.user.save(update_fields=["password"])
        self.client.login(username="settings-user", password="settings-password")
        self.client.login(username="settings-user", password="test-password")

    def test_settings_page_uses_profile_template(self):
        response = self.client.get(reverse("settings"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/settings.html")
        self.assertContains(response, "Dark Mode")
        self.assertContains(response, "Update Profile")
        self.assertContains(response, "Bitcoin")
        self.assertContains(response, "test-address")

    def test_settings_profile_can_be_updated(self):
        response = self.client.post(
            reverse("settings"),
            {
                "full_name": "Updated User",
                "email": "updated@example.com",
                "phone_number": "+987654321",
                "full_address": "Canada",
            },
        )

        self.assertRedirects(response, reverse("settings"))
        self.user.refresh_from_db()
        profile = self.user.creataura_profile
        self.assertEqual(self.user.email, "updated@example.com")
        self.assertEqual(profile.full_name, "Updated User")
        self.assertEqual(profile.phone_number, "+987654321")
        self.assertEqual(profile.country, "Canada")

    def test_withdrawal_settings_can_be_updated(self):
        response = self.client.post(
            reverse("settings"),
            {
                "settings_action": "withdrawals",
                "bank_name": "Test Bank",
                "account_name": "Settings User",
                "account_number": "123456789",
                "swift_code": "TESTCODE",
                "ethereum_address": "0x123",
                "litecoin_address": "ltc123",
            },
        )

        self.assertRedirects(response, reverse("settings"))
        account = BankAccount.objects.get(user=self.user)
        self.assertEqual(account.bank_name, "Test Bank")
        self.assertEqual(account.account_name, "Settings User")
        self.assertEqual(account.account_number, "123456789")
        self.assertEqual(account.swift_code, "TESTCODE")
        self.assertEqual(account.ethereum_address, "0x123")
        self.assertEqual(account.litecoin_address, "ltc123")
        self.user.creataura_profile.refresh_from_db()
        self.assertEqual(self.user.creataura_profile.bitcoin_address, "test-address")

    def test_password_settings_reject_incorrect_old_password(self):
        response = self.client.post(
            reverse("settings"),
            {
                "settings_action": "password",
                "old_password": "incorrect-password",
                "new_password": "NewPassword123!",
                "confirm_password": "NewPassword123!",
            },
        )

        self.assertRedirects(response, reverse("settings"))

    def test_password_settings_reject_mismatched_passwords(self):
        response = self.client.post(
            reverse("settings"),
            {
                "settings_action": "password",
                "old_password": "incorrect-password",
                "new_password": "NewPassword123!",
                "confirm_password": "DifferentPassword123!",
            },
        )

        self.assertRedirects(response, reverse("settings"))

    def test_other_settings_can_be_updated(self):
        response = self.client.post(
            reverse("settings"),
            {
                "settings_action": "other",
                "email_withdrawal_otp": "no",
                "email_profit_notification": "yes",
                "email_plan_expiry_notification": "no",
            },
        )

        self.assertRedirects(response, reverse("settings"))
        profile = self.user.creataura_profile
        profile.refresh_from_db()
        self.assertFalse(profile.email_withdrawal_otp)
        self.assertTrue(profile.email_profit_notification)
        self.assertFalse(profile.email_plan_expiry_notification)

    def test_password_can_be_updated(self):
        self.user.set_password("CurrentPassword123!")
        self.user.save(update_fields=["password"])
        self.client.login(username="settings-user", password="CurrentPassword123!")

        response = self.client.post(
            reverse("settings"),
            {
                "settings_action": "password",
                "old_password": "CurrentPassword123!",
                "new_password": "UpdatedPassword123!",
                "confirm_password": "UpdatedPassword123!",
            },
        )

        self.assertRedirects(response, reverse("settings"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("UpdatedPassword123!"))

    def test_advanced_account_security_page_is_rendered(self):
        response = self.client.get(reverse("advanced_account_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/advanced_account_settings.html")
        self.assertContains(response, "Two Factor Authentication")
        self.assertContains(response, "Browser Sessions")
        self.assertContains(response, "Delete Account")

    def test_two_factor_can_be_enabled_with_password(self):
        response = self.client.post(
            reverse("advanced_account_settings"),
            {
                "security_action": "two_factor",
                "password": "settings-password",
            },
        )

        self.assertRedirects(response, reverse("advanced_account_settings"))
        self.user.creataura_profile.refresh_from_db()
        self.assertTrue(self.user.creataura_profile.two_factor_enabled)

    def test_account_deletion_requires_correct_password(self):
        response = self.client.post(
            reverse("advanced_account_settings"),
            {
                "security_action": "delete_account",
                "password": "incorrect-password",
            },
        )

        self.assertRedirects(response, reverse("advanced_account_settings"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())


class ReferralTests(TestCase):
    def setUp(self):
        self.referrer = User.objects.create_user(
            username="referrer-user",
            email="referrer@example.com",
            password="ReferralPassword123!",
        )
        UserProfile.objects.create(
            user=self.referrer,
            full_name="Referrer User",
            phone_number="+111111111",
            bitcoin_address="referrer-bitcoin",
            country="United States",
            referral_id="",
        )
        self.referred = User.objects.create_user(
            username="referred-user",
            email="referred@example.com",
            password="ReferralPassword123!",
        )
        UserProfile.objects.create(
            user=self.referred,
            full_name="Referred User",
            phone_number="+222222222",
            bitcoin_address="referred-bitcoin",
            country="Canada",
            referral_id="referrer-user",
        )

    def test_referrals_page_shows_referral_link_and_referred_user(self):
        self.client.login(username="referrer-user", password="ReferralPassword123!")

        response = self.client.get(reverse("referrals"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/referrals.html")
        self.assertContains(response, "/ref/referrer-user/")
        self.assertContains(response, "referred-user")

    def test_referral_signup_prefills_referral_id(self):
        response = self.client.get(
            reverse("referral_signup", kwargs={"referral_id": "referrer-user"})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'name="referral_id" value="referrer-user"',
        )


class DashboardStatisticsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dashboard-user",
            email="dashboard@example.com",
            password="dashboard-password",
        )
        UserProfile.objects.create(
            user=self.user,
            full_name="Dashboard User",
            phone_number="+123456789",
            bitcoin_address="dashboard-address",
            country="United States",
        )
        self.client.force_login(self.user)

    def test_dashboard_totals_only_use_approved_and_paid_records(self):
        Deposit.objects.create(user=self.user, amount="1000", status="approved")
        Deposit.objects.create(user=self.user, amount="500", status="pending")
        Bonus.objects.create(
            user=self.user,
            amount="75",
            plan_narration="Gift Bonus",
        )
        ProfitRecord.objects.create(
            user=self.user,
            amount="50",
            narration="Daily ROI",
        )
        ReferralBonus.objects.create(
            referrer=self.user,
            referred_user=self.user,
            amount="25",
            status="paid",
        )
        ReferralBonus.objects.create(
            referrer=self.user,
            referred_user=self.user,
            amount="15",
            status="pending",
        )
        WithdrawalBTC.objects.create(
            user=self.user,
            amount="200",
            charges="5",
            status="approved",
        )
        WithdrawalBTC.objects.create(
            user=self.user,
            amount="100",
            charges="2",
            status="pending",
        )
        WithdrawalXRP.objects.create(
            user=self.user,
            amount="50",
            charges="1",
            xrp_address="test-xrp-address",
            status="approved",
        )
        WithdrawalXRP.objects.create(
            user=self.user,
            amount="40",
            charges="1",
            xrp_address="test-xrp-address",
            status="rejected",
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.context["total_deposit"], Decimal("1000"))
        self.assertEqual(response.context["total_bonus"], Decimal("75"))
        self.assertEqual(response.context["total_profit"], Decimal("50"))
        self.assertEqual(response.context["total_referral_bonus"], Decimal("25"))
        self.assertEqual(response.context["total_withdrawals"], Decimal("256"))


class InvestmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="investment-user",
            email="investment@example.com",
            password="InvestmentPassword123!",
        )
        UserProfile.objects.create(
            user=self.user,
            full_name="Investment User",
            phone_number="+123456789",
            bitcoin_address="investment-bitcoin",
            country="United States",
        )
        self.plan = InvestmentPlan.objects.create(
            name="Beginner Plan",
            amount="500",
            minimum_deposit="500",
            maximum_deposit="25000",
            daily_roi="1.5",
            weekly_roi="10.5",
            gift_bonus="1",
            duration_days=60,
        )
        Deposit.objects.create(
            user=self.user,
            amount="1000",
            status="approved",
        )

    def test_investments_page_is_rendered(self):
        self.client.login(username="investment-user", password="InvestmentPassword123!")
        response = self.client.get(reverse("invest"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/investments.html")
        self.assertContains(response, "Beginner Plan")
        self.assertContains(response, "Join plan")

    def test_plan_can_be_joined(self):
        self.client.login(username="investment-user", password="InvestmentPassword123!")
        response = self.client.post(
            reverse("join_investment", kwargs={"plan_id": self.plan.id}),
            {"amount": "750"},
        )

        self.assertRedirects(response, reverse("invest"))
        investment = UserInvestment.objects.get(user=self.user, plan=self.plan)
        self.assertEqual(str(investment.amount), "750.00")
        self.assertEqual(investment.status, "active")

        page = self.client.get(reverse("invest"))
        self.assertContains(page, "$750.00")
        self.assertContains(page, "Active")

    def test_plan_rejects_amount_below_minimum(self):
        self.client.login(username="investment-user", password="InvestmentPassword123!")
        response = self.client.post(
            reverse("join_investment", kwargs={"plan_id": self.plan.id}),
            {"amount": "499"},
        )

        self.assertRedirects(response, reverse("invest"))
        self.assertFalse(UserInvestment.objects.filter(user=self.user, plan=self.plan).exists())

    def test_plan_rejects_amount_above_available_balance(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("join_investment", kwargs={"plan_id": self.plan.id}),
            {"amount": "1001"},
        )

        self.assertRedirects(response, reverse("invest"))
        self.assertFalse(UserInvestment.objects.filter(user=self.user, plan=self.plan).exists())


class KYCTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="kyc-user",
            email="kyc@example.com",
            password="kyc-pass-123",
        )
        self.client.login(username="kyc-user", password="kyc-pass-123")

    def test_kyc_page_is_rendered(self):
        response = self.client.get(reverse("kyc"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/kyc.html")
        self.assertContains(response, "Verify Your Account")
        self.assertContains(response, "Submit documents")

    def test_kyc_requires_both_documents(self):
        response = self.client.post(reverse("kyc"), {})

        self.assertContains(response, "Please upload both required documents.")
        self.assertFalse(KYCVerification.objects.filter(user=self.user).exists())


class ROIHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="roi-user",
            email="roi@example.com",
            password="roi-pass-123",
        )
        self.client.login(username="roi-user", password="roi-pass-123")

    def test_empty_roi_history_is_rendered(self):
        response = self.client.get(reverse("profit_record"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/roi_history.html")
        self.assertContains(response, "Your ROI history")
        self.assertContains(response, "No transaction found")
        self.assertContains(response, "Total earned")
        self.assertContains(response, "$0.00")

    def test_roi_history_only_shows_user_records_and_total(self):
        other_user = User.objects.create_user(
            username="other-roi-user",
            email="other-roi@example.com",
            password="roi-pass-123",
        )
        ProfitRecord.objects.create(
            user=self.user,
            amount="12.50",
            narration="Daily ROI",
        )
        ProfitRecord.objects.create(
            user=other_user,
            amount="75.00",
            narration="Daily ROI",
        )

        response = self.client.get(reverse("profit_record"))

        self.assertContains(response, "$12.50")
        self.assertContains(response, "Daily ROI")
        self.assertNotContains(response, "$75.00")


class ROIWithdrawalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="roi-withdrawal-user",
            email="roi-withdrawal@example.com",
            password="roi-password",
        )
        UserProfile.objects.create(
            user=self.user,
            full_name="ROI User",
            phone_number="+123456789",
            bitcoin_address="roi-bitcoin-address",
            country="United States",
        )
        self.client.login(username="roi-withdrawal-user", password="roi-password")

    def test_dashboard_links_to_roi_withdrawal_page(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("withdraw_roi"))

    def test_empty_roi_shows_nothing_to_withdraw(self):
        response = self.client.get(reverse("withdraw_roi"))

        self.assertContains(response, "Nothing to withdraw at the moment!")

    def test_bitcoin_roi_withdrawal_reserves_available_profit(self):
        ProfitRecord.objects.create(
            user=self.user,
            amount="50.00",
            narration="Daily ROI",
        )

        first_response = self.client.post(
            reverse("withdraw_roi"),
            {"payment_mode": "bitcoin", "amount": "20.00"},
        )
        self.assertRedirects(first_response, reverse("withdraw_roi"))

        withdrawal = WithdrawalBTC.objects.get(user=self.user)
        self.assertEqual(withdrawal.amount, 20)
        self.assertEqual(withdrawal.source, "roi")
        self.assertEqual(withdrawal.status, "pending")

        page = self.client.get(reverse("withdraw_roi"))
        self.assertContains(page, "$30.00")

    def test_xrp_roi_withdrawal_is_created(self):
        ProfitRecord.objects.create(
            user=self.user,
            amount="40.00",
            narration="Weekly ROI",
        )

        response = self.client.post(
            reverse("withdraw_roi"),
            {"payment_mode": "xrp", "amount": "15.00", "xrp_address": "rROIAddress"},
        )

        self.assertRedirects(response, reverse("withdraw_roi"))
        withdrawal = WithdrawalXRP.objects.get(user=self.user)
        self.assertEqual(withdrawal.amount, 15)
        self.assertEqual(withdrawal.xrp_address, "rROIAddress")
        self.assertEqual(withdrawal.source, "roi")


class CryptoExchangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="exchange-user",
            email="exchange@example.com",
            password="TestPassword123!",
        )
        UserProfile.objects.create(
            user=self.user,
            full_name="Exchange User",
            phone_number="+123456789",
            bitcoin_address="exchange-bitcoin",
            country="United States",
        )
        Bonus.objects.create(
            user=self.user,
            amount="20.00",
            plan_narration="SignUp Bonus",
        )
        self.client.login(username="exchange-user", password="TestPassword123!")

    def test_exchange_page_uses_user_balance(self):
        response = self.client.get(reverse("crypto_exchange"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/crypto_exchange.html")
        self.assertContains(response, "$20.00")

    def test_usd_exchange_creates_persistent_record(self):
        response = self.client.post(
            reverse("crypto_exchange"),
            {
                "from_asset": "usd",
                "to_asset": "bnb",
                "from_amount": "10.00",
            },
        )

        self.assertRedirects(response, reverse("crypto_exchange"))
        exchange = CryptoExchange.objects.get(user=self.user)
        self.assertEqual(exchange.from_asset, "usd")
        self.assertEqual(exchange.to_asset, "bnb")
        self.assertEqual(exchange.status, "completed")
        self.assertGreater(exchange.to_amount, 0)

    def test_exchange_rejects_insufficient_balance(self):
        response = self.client.post(
            reverse("crypto_exchange"),
            {
                "from_asset": "bnb",
                "to_asset": "usd",
                "from_amount": "1",
            },
        )

        self.assertRedirects(response, reverse("crypto_exchange"))
        self.assertEqual(CryptoExchange.objects.count(), 0)


class WithdrawalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="withdrawal-user",
            email="withdrawal@example.com",
            password="TestPassword123!",
        )
        UserProfile.objects.create(
            user=self.user,
            full_name="Withdrawal User",
            phone_number="+123456789",
            bitcoin_address="withdrawal-bitcoin-address",
            country="United States",
        )
        Deposit.objects.create(
            user=self.user,
            amount="100.00",
            payment_mode="bitcoin",
            status="approved",
        )
        self.client.login(username="withdrawal-user", password="TestPassword123!")

    def test_withdrawal_page_renders_both_methods(self):
        response = self.client.get(reverse("withdrawal"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/withdrawal.html")
        self.assertContains(response, "Bitcoin")
        self.assertContains(response, "XRP")
        self.assertContains(response, "withdrawal-bitcoin-address")

    def test_bitcoin_withdrawal_is_created(self):
        response = self.client.post(
            reverse("withdrawal"),
            {
                "method_type": "bitcoin",
                "amount": "25.00",
                "otpcode": "123456",
            },
        )

        self.assertRedirects(response, reverse("withdrawal"))
        withdrawal = WithdrawalBTC.objects.get(user=self.user)
        self.assertEqual(withdrawal.amount, 25)
        self.assertEqual(withdrawal.status, "pending")

    def test_xrp_withdrawal_requires_address_and_is_created(self):
        response = self.client.post(
            reverse("withdrawal"),
            {
                "method_type": "xrp",
                "amount": "30.00",
                "xrp_address": "rXrpTestAddress",
            },
        )

        self.assertRedirects(response, reverse("withdrawal"))
        withdrawal = WithdrawalXRP.objects.get(user=self.user)
        self.assertEqual(withdrawal.xrp_address, "rXrpTestAddress")

    def test_withdrawal_rejects_insufficient_balance(self):
        response = self.client.post(
            reverse("withdrawal"),
            {
                "method_type": "bitcoin",
                "amount": "101.00",
            },
        )

        self.assertRedirects(response, reverse("withdrawal"))
        self.assertEqual(WithdrawalBTC.objects.count(), 0)

    def test_btc_withdrawal_second_page_is_rendered(self):
        response = self.client.get(reverse("withdrawal_btc"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/withdrawal_btc.html")
        self.assertContains(response, "Your Payment Method is Bitcoin")
        self.assertContains(response, "Complete Request")

    def test_btc_otp_can_be_requested_and_used_for_pending_record(self):
        otp_response = self.client.post(
            reverse("withdrawal_btc"),
            {"action": "request_otp"},
        )
        self.assertRedirects(otp_response, reverse("withdrawal_btc"))

        otp = self.client.session["btc_withdrawal_otp"]
        response = self.client.post(
            reverse("withdrawal_btc"),
            {
                "amount": "25.00",
                "otpcode": otp,
            },
        )

        self.assertRedirects(response, reverse("withdrawal_btc"))
        withdrawal = WithdrawalBTC.objects.get(user=self.user)
        self.assertEqual(withdrawal.amount, 25)
        self.assertEqual(withdrawal.status, "pending")

    def test_xrp_withdrawal_second_page_is_rendered(self):
        response = self.client.get(reverse("withdrawal_xrp"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/withdrawal_xrp.html")
        self.assertContains(response, "Your Payment Method is XRP")
        self.assertContains(response, "Enter XRP Address")

    def test_xrp_otp_can_be_requested_and_used_for_pending_record(self):
        otp_response = self.client.post(
            reverse("withdrawal_xrp"),
            {"action": "request_otp"},
        )
        self.assertRedirects(otp_response, reverse("withdrawal_xrp"))

        otp = self.client.session["xrp_withdrawal_otp"]
        response = self.client.post(
            reverse("withdrawal_xrp"),
            {
                "amount": "30.00",
                "otpcode": otp,
                "xrp_address": "rXrpWalletAddress123",
            },
        )

        self.assertRedirects(response, reverse("withdrawal_xrp"))
        withdrawal = WithdrawalXRP.objects.get(user=self.user)
        self.assertEqual(withdrawal.amount, 30)
        self.assertEqual(withdrawal.xrp_address, "rXrpWalletAddress123")
        self.assertEqual(withdrawal.status, "pending")


class DepositFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="deposit-user",
            email="deposit@example.com",
            password="deposit-password",
        )
        self.client.login(username="deposit-user", password="deposit-password")

    def test_deposit_selection_page_lists_supported_modes(self):
        response = self.client.get(reverse("deposit"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/deposit.html")
        self.assertContains(response, "Bitcoin")
        self.assertContains(response, "Ethereum")
        self.assertContains(response, "XRP")

    def test_deposit_mode_and_amount_redirect_to_payment(self):
        response = self.client.post(
            reverse("deposit"),
            {"payment_mode": "ethereum", "amount": "125.50"},
        )

        self.assertRedirects(
            response,
            reverse("deposit_payment", kwargs={"payment_mode": "ethereum"}),
        )

        payment_response = self.client.get(
            reverse("deposit_payment", kwargs={"payment_mode": "ethereum"})
        )
        self.assertEqual(payment_response.status_code, 200)
        self.assertContains(payment_response, "$125.50")
        self.assertContains(payment_response, "Ethereum")

    def test_invalid_deposit_mode_is_rejected(self):
        response = self.client.post(
            reverse("deposit"),
            {"payment_mode": "bank", "amount": "100.00"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid payment method.")
        self.assertNotIn("deposit_amount", self.client.session)

    def test_proof_submission_creates_pending_user_deposit(self):
        self.client.post(
            reverse("deposit"),
            {"payment_mode": "bitcoin", "amount": "75.25"},
        )
        proof = SimpleUploadedFile(
            "proof.png",
            b"payment-proof-content",
            content_type="image/png",
        )

        response = self.client.post(
            reverse("deposit_payment", kwargs={"payment_mode": "bitcoin"}),
            {"proof_of_payment": proof},
        )

        self.assertRedirects(response, reverse("transaction_history"))
        deposit = Deposit.objects.get(user=self.user)
        self.assertEqual(deposit.amount, 75.25)
        self.assertEqual(deposit.payment_mode, "bitcoin")
        self.assertEqual(deposit.status, "pending")
        self.assertTrue(deposit.wallet_address)
        self.assertTrue(deposit.proof_of_payment.name.startswith("payment_proofs/"))

    def test_payment_route_requires_selected_mode_and_amount(self):
        response = self.client.get(
            reverse("deposit_payment", kwargs={"payment_mode": "xrp"})
        )

        self.assertRedirects(response, reverse("deposit"))


class TransactionHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="history-user",
            email="history@example.com",
            password="history-pass-123",
        )
        self.client.login(username="history-user", password="history-pass-123")

    def test_transaction_history_page_is_rendered(self):
        response = self.client.get(reverse("transaction_history"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "creataura/transactions.html")
        self.assertContains(response, "Transactions on your account")
        self.assertContains(response, "Deposit Table")

    def test_only_authenticated_users_deposits_are_shown(self):
        other_user = User.objects.create_user(
            username="other-history-user",
            email="other-history@example.com",
            password="history-pass-123",
        )
        Deposit.objects.create(
            user=self.user,
            amount="125.50",
            payment_mode="bitcoin",
            status="approved",
        )
        Deposit.objects.create(
            user=other_user,
            amount="999.00",
            payment_mode="ethereum",
            status="pending",
        )

        response = self.client.get(reverse("transaction_history"))

        self.assertContains(response, "$125.50")
        self.assertNotContains(response, "$999.00")

    def test_withdrawal_columns_use_requested_and_total_amounts(self):
        WithdrawalBTC.objects.create(
            user=self.user,
            cryptocoin="Bitcoin",
            amount="300.00",
            charges="15.00",
            status="approved",
        )

        response = self.client.get(
            reverse("transaction_history") + "?tab=withdrawals"
        )

        self.assertContains(response, "Amount requested")
        self.assertContains(response, "Amount + charges")
        self.assertContains(response, "Receiving mode")
        self.assertContains(response, "$300.00")
        self.assertContains(response, "$315.00")

    def test_signup_bonus_is_shown_in_others(self):
        bonus = Bonus.objects.create(
            user=self.user,
            amount="5.00",
            plan_narration="SignUp Bonus",
        )

        response = self.client.get(
            reverse("transaction_history") + "?tab=others"
        )

        self.assertContains(response, "$5")
        self.assertContains(response, "Bonus")
        self.assertContains(response, "SignUp Bonus")


class SignupBonusTests(TestCase):
    def test_login_does_not_create_signup_bonus(self):
        user = User.objects.create_user(
            username="signup-bonus-user",
            email="signup-bonus@example.com",
            password="testpass123",
        )

        for _ in range(2):
            self.client.logout()
            response = self.client.post(
                reverse("login"),
                {"email": user.email, "password": "testpass123"},
            )
            self.assertEqual(response.status_code, 302)

        self.assertFalse(
            Bonus.objects.filter(
                user=user,
                plan_narration="SignUp Bonus",
            ).exists()
        )

    def test_registration_awards_signup_bonus_and_login_does_not_duplicate_it(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "new-signup-user",
                "email": "new-signup@example.com",
                "full_name": "New Signup User",
                "phone_number": "+123456789",
                "bitcoin_address": "new-signup-wallet",
                "country": "United States",
                "password": "testpass123",
                "password_again": "testpass123",
            },
        )
        self.assertRedirects(response, reverse("login"))

        user = User.objects.get(username="new-signup-user")
        login_response = self.client.post(
            reverse("login"),
            {"email": user.email, "password": "testpass123"},
        )
        self.assertEqual(login_response.status_code, 302)

        self.assertEqual(
            Bonus.objects.filter(
                user=user,
                amount="5.00",
                plan_narration="SignUp Bonus",
            ).count(),
            1,
        )

        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, "$5.00")
