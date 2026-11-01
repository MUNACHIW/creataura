from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render

from .models import UserProfile


def home(request):
    return render(request, "creataura/index.html")


@login_required(login_url="login")
def dashboard(request):
    return render(request, "creataura/dashboard.html")


@login_required(login_url="login")
def crypto_exchange(request):
    return render(request, "creataura/crypto_exchange.html")


@login_required(login_url="login")
def support(request):
    return render(request, "creataura/support.html")


COUNTRIES = [
    "Nigeria", "United States", "United Kingdom", "Canada", "Australia",
    "Ghana", "South Africa", "Kenya", "Germany", "France", "India",
    "United Arab Emirates", "China", "Japan", "Singapore",
]


def register(request):
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
        referral_id = request.POST.get("referral_id", "").strip()

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
                messages.success(request, "Account created successfully. Please log in.")
                return redirect("login")

    return render(request, "creataura/register.html", {"countries": COUNTRIES})


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
