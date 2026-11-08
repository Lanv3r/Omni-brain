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
      option.dataset.themeOption = nextTheme;
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

  window.addEventListener("storage", event => {
    if (event.key === "omni-theme") {
      applyTheme(event.newValue === "dark" ? "dark" : "light", false);
    }
  });
})();
