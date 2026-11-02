"""
URL configuration for investmentsite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from creataura.views import (
    home, register, user_login, user_logout, dashboard, crypto_exchange,
    support, support_submit,
    settings, referrals,
    investments, join_investment,
    transaction_history, roi_history, kyc, withdrawal, withdrawal_btc, withdrawal_xrp,
    deposit, deposit_payment, withdraw_roi, advanced_account_settings,
)

urlpatterns = [
    path("", home, name="home"),
    path("register/", register, name="register"),
    path("login/", user_login, name="login"),
    path("logout/", user_logout, name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
    path("crypto-exchange/", crypto_exchange, name="crypto_exchange"),
    path("support/", support, name="support"),
    path("support/submit/", support_submit, name="support_submit"),
    path("settings/", settings, name="settings"),
    path("settings/security/", advanced_account_settings, name="advanced_account_settings"),
    path("withdraw/", withdrawal, name="withdrawal"),
    path("withdraw/btc/", withdrawal_btc, name="withdrawal_btc"),
    path("withdraw/xrp/", withdrawal_xrp, name="withdrawal_xrp"),
    path("withdraw/roi/", withdraw_roi, name="withdraw_roi"),
    path("deposit/", deposit, name="deposit"),
    path("deposit/<str:payment_mode>/", deposit_payment, name="deposit_payment"),
    path("referrals/", referrals, name="referrals"),
    path("transactions/", transaction_history, name="transaction_history"),
    path("profit-record/", roi_history, name="profit_record"),
    path("kyc/", kyc, name="kyc"),
    path("invest/", investments, name="invest"),
    path("investments/", RedirectView.as_view(pattern_name="invest", permanent=False)),
    path("invest/<int:plan_id>/join/", join_investment, name="join_investment"),
    path("investments/<int:plan_id>/join/", join_investment),
    path("ref/<str:referral_id>/", register, name="referral_signup"),
    path("admin/", admin.site.urls),
]
