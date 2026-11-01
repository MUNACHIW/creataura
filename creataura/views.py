from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render

from .models import SupportMessage, UserProfile


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
    return render(
        request,
        "creataura/dashboard.html",
        {"dashboard_full_name": full_name},
    )


@login_required(login_url="login")
def crypto_exchange(request):
    return render(request, "creataura/crypto_exchange.html")


@login_required(login_url="login")
def support(request):
    if request.method == "POST":
        subject = request.POST.get("subject", "").strip()
        message = request.POST.get("message", "").strip()

        if not subject or not message:
            messages.error(request, "Please enter both a subject and message.")
        else:
            SupportMessage.objects.create(
                user=request.user,
                subject=subject,
                message=message,
            )
            messages.success(request, "Your support message has been sent.")
            return redirect("support")

    return render(request, "creataura/support.html")


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
