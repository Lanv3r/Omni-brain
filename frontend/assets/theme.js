(() => {
  const root = document.documentElement;
  const fileTheme = window.location.protocol === "file:"
    ? new URLSearchParams(window.location.search).get("omni-theme")
    : null;
  let storedTheme;
  try { storedTheme = localStorage.getItem("omni-theme"); } catch { /* Storage may be unavailable for local files. */ }
  const savedTheme = fileTheme === "dark" || fileTheme === "light" ? fileTheme : storedTheme;

  if (savedTheme === "dark" || savedTheme === "light") {
    root.dataset.theme = savedTheme;
  }

  function syncFileNavigationLinks(theme) {
    if (window.location.protocol !== "file:") return;

    const currentDirectory = window.location.pathname.slice(0, window.location.pathname.lastIndexOf("/") + 1);
    for (const link of document.querySelectorAll("a[href]")) {
      const target = new URL(link.href);
      if (target.protocol !== "file:" || !target.pathname.startsWith(currentDirectory)) continue;
      target.searchParams.set("omni-theme", theme);
      link.href = target.href;
    }
  }

  function applyTheme(theme, persist = true) {
    const isDark = theme === "dark";
    const currentTheme = isDark ? "dark" : "light";
    const nextTheme = isDark ? "light" : "dark";
    root.dataset.theme = currentTheme;
    if (persist) {
      try { localStorage.setItem("omni-theme", currentTheme); } catch { /* Keep the theme for this page. */ }
    }
    syncFileNavigationLinks(currentTheme);

    for (const menu of document.querySelectorAll(".theme-menu")) {
      const toggle = menu.querySelector(".theme-toggle");
      const option = menu.querySelector(".theme-option");
      toggle.setAttribute("aria-label", `Choose color theme. Current theme: ${currentTheme}`);
      toggle.title = `Current theme: ${currentTheme}`;
      toggle.querySelector(".theme-current").textContent = `${isDark ? "Dark" : "Light"} mode`;
      option.dataset.themeOption = nextTheme;
      option.querySelector(".theme-option-label").textContent = `${nextTheme === "dark" ? "Dark" : "Light"} mode`;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const bar = document.querySelector("header .bar");
    if (bar) {
      const sunIcon = '<svg class="theme-icon theme-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"></path></svg>';
      const moonIcon = '<svg class="theme-icon theme-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13Z"></path></svg>';
      const menu = document.createElement("div");
      menu.className = "theme-menu";
      menu.innerHTML = `
        <button class="theme-toggle" type="button" aria-haspopup="true" aria-expanded="false">
          <span class="theme-icon-wrap">${sunIcon}${moonIcon}</span>
          <span class="theme-current">Light mode</span>
          <svg class="theme-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"></path></svg>
        </button>
        <div class="theme-options" hidden>
          <button class="theme-option" type="button">
            <span class="theme-option-icon">${sunIcon}${moonIcon}</span>
            <span class="theme-option-label">Dark mode</span>
          </button>
        </div>`;
      bar.insertBefore(menu, bar.querySelector(".partner-brand"));
    }
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

  window.addEventListener("storage", event => {
    if (event.key === "omni-theme") {
      applyTheme(event.newValue === "dark" ? "dark" : "light", false);
    }
  });
})();
