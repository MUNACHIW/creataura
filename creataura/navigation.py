from django.urls import reverse


def navigation(request):
    match = request.resolver_match
    current = match.url_name if match else ""

    def link(label, name):
        return {
            "label": label,
            "url": reverse(name),
            "on": " active" if current == name else "",
            "aria": "page" if current == name else "false",
        }

    def group(label, children, **extra):
        is_active = any(child["on"] for child in children)
        return {
            "label": label,
            "children": children,
            "on": " active" if is_active else "",
            **extra,
        }

    sustainability = group(
        "Sustainability",
        [
            link("Cryptocurrency", "cryptocurrency"),
            link("Renewable Energy", "renewable_energy"),
            link("Stocks & ETFs", "stocks_etfs"),
            link("Real Estate", "real_estate"),
            link("Oil and Gas", "oil_gas"),
        ],
        dom_id="sustainabilityLinks",
    )

    privacy = group(
        "Privacy and Policy",
        [link("Foreign Investor Protection", "foreign_investor_protection")],
        dom_id="privacyPolicyLinks",
        menu_end=" dropdown-menu-end",
    )

    careers = link("Careers", "careers")
    contact = link("Contact", "contact")
    contact["children"] = [careers]
    contact["split"] = True
    if careers["on"]:
        contact["on"] = " active"

    return {
        "nav_items": [
            link("Home", "home"),
            sustainability,
            link("About", "about"),
            link("Loans", "loans"),
            contact,
            link("FAQ", "faq"),
            privacy,
        ],
        "nav_dashboard": link("Dashboard", "dashboard"),
        "nav_register": link("Sign Up", "register"),
        "nav_login": link("Login", "login"),
    }