(function () {
    const savedTheme = localStorage.getItem("creataura-theme") || "light";
    document.documentElement.dataset.theme = savedTheme;

    document.addEventListener("DOMContentLoaded", function () {
        const controls = document.querySelectorAll(".theme-toggle, #darkModeToggle, [data-theme-toggle]");

        controls.forEach(function (control) {
            control.checked = savedTheme === "dark";
            control.addEventListener("change", function () {
                const theme = control.checked ? "dark" : "light";
                document.documentElement.dataset.theme = theme;
                localStorage.setItem("creataura-theme", theme);
                controls.forEach(function (item) { item.checked = control.checked; });
            });
        });
    });
})();
