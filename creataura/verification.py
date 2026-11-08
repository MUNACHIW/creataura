import logging
from functools import wraps

import resend
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import (
    PasswordResetTokenGenerator,
    default_token_generator,
)
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import UserProfile

logger = logging.getLogger(__name__)


def is_email_verified(user):
    profile = UserProfile.objects.filter(user=user).first()
    return bool(profile and profile.email_verified)


# URL names an unverified user may still visit
UNVERIFIED_ALLOWED = {
    # public pages
    "home",
    "loans",
    "contact",
    "careers",
    "faq",
    "about",
    # auth
    "login",
    "logout",
    "register",
    "register_referral",
    # verification and password reset
    "verify_email",
    "resend_verification",
    "verify_email_confirm",
    "forgot_password",
    "reset_password",
}


class EmailVerificationMiddleware:
    """Sends logged-in but unverified users to the verification page
    for any URL that isn't in UNVERIFIED_ALLOWED."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        if not user.is_authenticated or user.is_staff:
            return None  # staff/superusers have no profile, so skip them

        match = request.resolver_match
        if match and match.url_name in UNVERIFIED_ALLOWED:
            return None

        if is_email_verified(user):
            return None

        return redirect("verify_email")


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Doesn't depend on last_login, so logging in won't kill the link.
    Includes the verified flag, so the link is single-use."""

    key_salt = "creataura.verification.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{is_email_verified(user)}{timestamp}"


email_verification_token = EmailVerificationTokenGenerator()


def _build_url(request, url_name, user, generator):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = generator.make_token(user)
    return request.build_absolute_uri(
        reverse(url_name, kwargs={"uidb64": uid, "token": token})
    )


def _send(to_email, subject, context):
    html = render_to_string("creataura/emails/action_email.html", context)
    text = render_to_string("creataura/emails/action_email.txt", context)

    if not settings.RESEND_API_KEY:
        # Dev fallback: print the link instead of sending
        logger.warning("RESEND_API_KEY not set. Email to %s:\n%s", to_email, text)
        return settings.DEBUG

    resend.api_key = settings.RESEND_API_KEY
    try:
        resend.Emails.send(
            {
                "from": settings.DEFAULT_FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "html": html,
                "text": text,
            }
        )
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False


def send_verification_email(request, user):
    url = _build_url(request, "verify_email_confirm", user, email_verification_token)
    return _send(
        user.email,
        "Verify your Capiatalnext email",
        {
            "heading": f"Welcome, {user.first_name or user.username}!",
            "intro": "Please confirm your email address to verify your account.",
            "button_text": "Verify Email",
            "url": url,
            "outro": "If you didn't create this account, you can ignore this email.",
        },
    )


def send_password_reset_email(request, user):
    url = _build_url(request, "reset_password", user, default_token_generator)
    return _send(
        user.email,
        "Reset your Capiatalnext password",
        {
            "heading": "Reset your password",
            "intro": "We received a request to reset your password. "
            "Click the button below to choose a new one.",
            "button_text": "Reset Password",
            "url": url,
            "outro": "If you didn't request this, you can safely ignore this email. "
            "Your password won't change.",
        },
    )


def verified_required(view_func):
    """Use on sensitive views (withdrawals, address changes, etc.)."""

    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_email_verified(request.user):
            messages.warning(request, "Please verify your email to use this feature.")
            return redirect("verify_email")
        return view_func(request, *args, **kwargs)

    return _wrapped


def verification_status(request):
    """Context processor: exposes `email_unverified` to every template."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return {"email_unverified": not is_email_verified(user)}
    return {}
