(() => {
  const root = document.documentElement;
  const savedTheme = localStorage.getItem("omni-theme");

  if (savedTheme === "dark") {
    root.dataset.theme = "dark";
  }

  function applyTheme(theme) {
    const isDark = theme === "dark";
    const currentTheme = isDark ? "dark" : "light";
    const nextTheme = isDark ? "light" : "dark";
    root.dataset.theme = currentTheme;
    localStorage.setItem("omni-theme", currentTheme);

    for (const menu of document.querySelectorAll(".theme-menu")) {
      const toggle = menu.querySelector(".theme-toggle");
      const option = menu.querySelector(".theme-option");
      toggle.setAttribute("aria-label", `Choose color theme. Current theme: ${currentTheme}`);
      toggle.title = `Current theme: ${currentTheme}`;
      option.dataset.themeOption = nextTheme;
      option.querySelector("span").textContent = `${nextTheme === "dark" ? "Dark" : "Light"} mode`;

      for (const icon of menu.querySelectorAll("[data-theme-icon]")) {
        const visibleTheme = icon.closest(".theme-option") ? nextTheme : currentTheme;
        const isVisible = icon.dataset.themeIcon === visibleTheme;
        icon.removeAttribute("hidden");
        icon.style.setProperty("display", isVisible ? "block" : "none", "important");
      }
    }

    for (const logo of document.querySelectorAll(".partner-brand[data-dark-src]")) {
      logo.src = isDark ? logo.dataset.darkSrc : logo.dataset.lightSrc;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const menus = document.querySelectorAll(".theme-menu");

    function closeMenu(menu, returnFocus = false) {
      const toggle = menu.querySelector(".theme-toggle");
      menu.querySelector(".theme-options").hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      if (returnFocus) toggle.focus();
    }

    function openMenu(menu) {
      const toggle = menu.querySelector(".theme-toggle");
      menu.querySelector(".theme-options").hidden = false;
      toggle.setAttribute("aria-expanded", "true");
    }

    for (const menu of menus) {
      const toggle = menu.querySelector(".theme-toggle");
      const options = menu.querySelector(".theme-options");
      const option = menu.querySelector(".theme-option");

      toggle.addEventListener("click", () => {
        if (options.hidden) openMenu(menu);
        else closeMenu(menu);
      });

      toggle.addEventListener("keydown", event => {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          openMenu(menu);
          option.focus();
        }
      });

      option.addEventListener("click", () => {
        applyTheme(option.dataset.themeOption);
        closeMenu(menu, true);
      });
    }

    document.addEventListener("pointerdown", event => {
      for (const menu of menus) {
        if (!menu.contains(event.target)) closeMenu(menu);
      }
    });

    document.addEventListener("keydown", event => {
      if (event.key !== "Escape") return;
      for (const menu of menus) {
        if (!menu.querySelector(".theme-options").hidden) {
          event.preventDefault();
          closeMenu(menu, true);
        }
      }
    });

    applyTheme(root.dataset.theme === "dark" ? "dark" : "light");
  });
})();
