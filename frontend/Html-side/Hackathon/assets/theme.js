(() => {
  const root = document.documentElement;
  const fileTheme = window.location.protocol === "file:"
    ? new URLSearchParams(window.location.search).get("omni-theme")
    : null;
  const savedTheme = fileTheme === "dark" || fileTheme === "light"
    ? fileTheme
    : localStorage.getItem("omni-theme");

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
    if (persist) localStorage.setItem("omni-theme", currentTheme);
    syncFileNavigationLinks(currentTheme);

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
    const sortOrders = {
      severity: { critical: 0, warning: 1, info: 2 },
      priority: { urgent: 0, high: 1, medium: 2, low: 3 },
      status: { overdue: 0, urgent: 0, "in progress": 1, pending: 2, new: 2, open: 2, resolved: 3, offline: 0, online: 1 },
    };

    for (const table of document.querySelectorAll(".table-scroll table")) {
      const headers = [...table.querySelectorAll("thead th")];
      const body = table.querySelector("tbody");
      if (!body) continue;

      headers.forEach((header, columnIndex) => {
        const label = header.textContent.trim();
        const button = document.createElement("button");
        button.className = "sortable-header";
        button.type = "button";
        button.textContent = label;
        button.dataset.sortKey = label.toLocaleLowerCase();
        button.setAttribute("aria-label", `Sort by ${label}`);
        header.replaceChildren(button);

        button.addEventListener("click", () => {
          const currentDirection = button.getAttribute("aria-sort");
          const direction = currentDirection === "ascending" ? "descending" : "ascending";
          for (const otherButton of headers.map(item => item.firstElementChild)) {
            if (otherButton !== button) otherButton.removeAttribute("aria-sort");
          }
          button.setAttribute("aria-sort", direction);

          const rows = [...body.querySelectorAll("tr")].filter(row => row.id !== "empty-state");
          rows.sort((left, right) => {
            const leftValue = left.cells[columnIndex]?.textContent.trim().toLocaleLowerCase() || "";
            const rightValue = right.cells[columnIndex]?.textContent.trim().toLocaleLowerCase() || "";
            const sortOrder = sortOrders[button.dataset.sortKey];
            const comparison = sortOrder
              ? (sortOrder[leftValue] ?? Number.MAX_SAFE_INTEGER) - (sortOrder[rightValue] ?? Number.MAX_SAFE_INTEGER)
              : leftValue.localeCompare(rightValue, undefined, { numeric: true, sensitivity: "base" });
            return direction === "ascending" ? comparison : -comparison;
          });
          rows.forEach(row => body.append(row));
        });
      });
    }

    for (const notification of document.querySelectorAll(".notification-link")) {
      const popup = document.createElement("div");
      popup.className = "notification-popup";
      popup.hidden = true;
      popup.setAttribute("role", "dialog");
      popup.innerHTML = `
        <strong>Unread notifications</strong>
        <ul>
          <li><a href="alerts.html?severity=Critical">2 critical alerts need attention.</a></li>
          <li><a href="alerts.html?severity=Warning">1 device is offline.</a></li>
        </ul>
        <a href="alerts.html">View all alerts</a>
      `;
      notification.append(popup);
      notification.setAttribute("aria-expanded", "false");

      function positionPopup() {
        const bounds = notification.getBoundingClientRect();
        popup.style.top = `${bounds.bottom + 8}px`;
        popup.style.left = `${Math.max(8, bounds.right - 250)}px`;
      }

      notification.addEventListener("click", event => {
        if (event.target.closest(".notification-popup")) return;
        event.preventDefault();
        const isOpen = !popup.hidden;
        if (!isOpen) positionPopup();
        popup.hidden = isOpen;
        notification.setAttribute("aria-expanded", String(!isOpen));
      });

      notification.addEventListener("keydown", event => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        notification.click();
      });
    }

    document.addEventListener("pointerdown", event => {
      for (const notification of document.querySelectorAll(".notification-link")) {
        if (notification.contains(event.target)) continue;
        const popup = notification.querySelector(".notification-popup");
        if (!popup) continue;
        popup.hidden = true;
        notification.setAttribute("aria-expanded", "false");
      }
    });

    window.addEventListener("resize", () => {
      for (const notification of document.querySelectorAll(".notification-link")) {
        const popup = notification.querySelector(".notification-popup");
        if (popup && !popup.hidden) {
          const bounds = notification.getBoundingClientRect();
          popup.style.top = `${bounds.bottom + 8}px`;
          popup.style.left = `${Math.max(8, bounds.right - 250)}px`;
        }
      }
    });

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
