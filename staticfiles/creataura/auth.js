const toggle = document.querySelector(".theme-toggle");
const savedTheme = localStorage.getItem("creataura-theme");

if (savedTheme === "dark") {
    document.body.classList.add("auth-dark");
    if (toggle) toggle.checked = true;
}

if (toggle) {
    toggle.addEventListener("change", () => {
        document.body.classList.toggle("auth-dark", toggle.checked);
        localStorage.setItem("creataura-theme", toggle.checked ? "dark" : "light");
    });
}
