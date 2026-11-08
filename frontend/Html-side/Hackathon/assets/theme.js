(() => {
  const root = document.documentElement;
  const fileTheme = window.location.protocol === "file:"
    ? new URLSearchParams(window.location.search).get("omni-theme")
    : null;
  const savedTheme = fileTheme === "dark" || fileTheme === "light"
    ? fileTheme
    : localStorage.getItem("omni-theme");
  const unreadStorageKey = "omni-unread-notifications";
  const readItemsStorageKey = "omni-read-items";

  function getReadItems() {
    try {
      const parsed = JSON.parse(localStorage.getItem(readItemsStorageKey) || "{}");
      return {
        tickets: new Set(parsed.tickets || []),
        alerts: new Set(parsed.alerts || []),
        tasks: new Set(parsed.tasks || []),
        devices: new Set(parsed.devices || []),
      };
    } catch {
      return { tickets: new Set(), alerts: new Set(), tasks: new Set(), devices: new Set() };
    }
  }

  function saveReadItems(readItems) {
    localStorage.setItem(readItemsStorageKey, JSON.stringify({
      tickets: [...readItems.tickets],
      alerts: [...readItems.alerts],
      tasks: [...readItems.tasks],
      devices: [...readItems.devices],
    }));
  }

  window.omniMarkItemRead = (section, id) => {
    const readItems = getReadItems();
    readItems[section]?.add(id);
    saveReadItems(readItems);
    window.dispatchEvent(new CustomEvent("omni-read-items-updated"));
  };

  window.omniMarkNotificationRead = () => {
    const currentCount = Number.parseInt(localStorage.getItem(unreadStorageKey) || "3", 10);
    const nextCount = Math.max(0, Number.isFinite(currentCount) ? currentCount - 1 : 0);
    localStorage.setItem(unreadStorageKey, String(nextCount));
    window.dispatchEvent(new CustomEvent("omni-unread-updated"));
  };

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
      toggle.setAttribute("aria-label", `Switch to ${nextTheme} theme`);
      toggle.title = `Current theme: ${currentTheme}`;
      toggle.setAttribute("aria-pressed", String(isDark));

      for (const icon of menu.querySelectorAll("[data-theme-icon]")) {
        icon.removeAttribute("hidden");
        icon.style.setProperty("display", "block", "important");
        icon.dataset.active = String(icon.dataset.themeIcon === currentTheme);
      }
    }

    for (const logo of document.querySelectorAll(".partner-brand[data-dark-src]")) {
      logo.src = isDark ? logo.dataset.darkSrc : logo.dataset.lightSrc;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const menus = document.querySelectorAll(".theme-menu");
    let unreadCount = 0;
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

    const readItems = getReadItems();
    const pageRows = [
      ["tickets", document.querySelector("#ticket-rows"), row => row.dataset.status === "New", row => row.querySelector(".ticket-id")?.textContent.trim()],
      ["alerts", document.querySelector("#alert-rows"), row => row.querySelector(".alert-state")?.textContent.trim() !== "Cleared", row => row.dataset.id],
      ["tasks", document.querySelector("#task-rows"), () => true, row => row.dataset.taskId || row.querySelector(".task-id")?.textContent.trim()],
    ];

    function decorateUnreadRows() {
      for (const [section, container, isUnreadCandidate, getId] of pageRows) {
        if (!container) continue;
        for (const row of container.querySelectorAll("tr[data-status], tr[data-severity]")) {
          const id = getId(row);
          if (!id) continue;
          const unread = isUnreadCandidate(row) && !readItems[section].has(id);
          const firstCell = row.firstElementChild;
          let dot = firstCell?.querySelector(".unread-dot");
          if (unread && firstCell && !dot) {
            dot = document.createElement("span");
            dot.className = "unread-dot";
            dot.title = "Unread";
            dot.setAttribute("aria-label", "Unread");
            firstCell.prepend(dot);
          } else if (!unread) {
            dot?.remove();
          }
          if (unread && !row.dataset.unreadHandler) {
            row.dataset.unreadHandler = "true";
            row.addEventListener("click", () => {
              window.omniMarkItemRead(section, id);
              readItems[section].add(id);
              decorateUnreadRows();
            });
          }
          if (section === "tasks" && !row.dataset.detailHandler) {
            row.dataset.detailHandler = "true";
            row.tabIndex = 0;
            row.classList.add("clickable-row");
            const openTask = event => {
              if (event.target.closest("a")) return;
              window.location.href = `task_detail.html?id=${encodeURIComponent(id)}`;
            };
            row.addEventListener("click", openTask);
            row.addEventListener("keydown", event => {
              if (event.key !== "Enter" && event.key !== " ") return;
              event.preventDefault();
              openTask(event);
            });
          }
        }
      }
    }

    decorateUnreadRows();
    for (const [, container] of pageRows) {
      container && new MutationObserver(decorateUnreadRows).observe(container, { childList: true, subtree: true });
    }

    for (const notification of document.querySelectorAll(".notification-link")) {
      const popup = document.createElement("div");
      popup.className = "notification-popup";
      popup.hidden = true;
      popup.setAttribute("role", "menu");
      notification.append(popup);
      notification.setAttribute("aria-expanded", "false");

      const count = notification.querySelector(".notification-count");
      const alertNotifications = [
        ["DEMO-A203", "HQ-FILE-01 is not responding", "alert_detail.html"],
        ["DEMO-A202", "BACKUP-02 backup failed", "alert_detail.html"],
        ["DEMO-A201", "DESIGN-WS-14 is running out of disk space", "alert_detail.html"],
        ["DEMO-A200", "CEDAR-LT-08 needs endpoint protection attention", "alert_detail.html"],
        ["DEMO-A199", "HARBOR-WS-03 has pending updates", "alert_detail.html"],
        ["DEMO-A198", "WILLOW-SQL-01 maintenance completed", "alert_detail.html"],
      ];
      const offlineNotifications = [
        ["WILLOW-WS-07", "Willow Accounting"],
        ["CEDAR-LT-08", "Cedar Works"],
      ];
      const getClearedAlertIds = () => new Set(JSON.parse(localStorage.getItem("omni-cleared-alerts") || "[]"));
      const getNotificationItems = () => {
        const clearedIds = getClearedAlertIds();
        const currentReadItems = getReadItems();
        return [
          ...[
            ["DEMO-1048", "New starter can't access email", "ticket_detail.html"],
          ]
            .filter(([id]) => !currentReadItems.tickets.has(id))
            .map(([id, title, href]) => ({ section: "tickets", id, title, href: `${href}?id=${id}` })),
          ...[
            ["DEMO-T312", "Review failed nightly backup", "task_detail.html"],
            ["DEMO-T311", "Replace finance workstation", "task_detail.html"],
            ["DEMO-T310", "Restore shared folder permissions", "task_detail.html"],
            ["DEMO-T309", "Prepare new employee laptop", "task_detail.html"],
            ["DEMO-T308", "Schedule network maintenance", "task_detail.html"],
            ["DEMO-T307", "Configure secure remote access", "task_detail.html"],
            ["DEMO-T306", "Apply workstation security updates", "task_detail.html"],
          ]
            .filter(([id]) => !currentReadItems.tasks.has(id))
            .map(([id, title, href]) => ({ section: "tasks", id, title, href: `${href}?id=${id}` })),
          ...alertNotifications
            .filter(([id]) => !clearedIds.has(id) && !currentReadItems.alerts.has(id))
            .map(([id, title, href]) => ({ section: "alerts", id, title, href: `${href}?id=${id}` })),
          ...offlineNotifications
            .filter(([id]) => !currentReadItems.devices.has(id))
            .map(([id]) => ({
            section: "devices",
            id,
            title: `${id} is down`,
            href: `device_detail.html?id=${id}&from=devices`,
          })),
        ];
      };
      function updateUnreadCount() {
        unreadCount = getNotificationItems().length;
        localStorage.setItem(unreadStorageKey, String(unreadCount));
        if (count) {
          count.textContent = unreadCount;
          count.hidden = unreadCount === 0;
        }
        notification.setAttribute("aria-label", `Notifications, ${unreadCount} unread`);
      }

      function renderNotifications() {
        if (unreadCount === 0) {
          popup.classList.add("is-empty");
          popup.innerHTML = "<strong>No new notifications</strong>";
          return;
        }
        popup.classList.remove("is-empty");
        const items = getNotificationItems();
        const visibleItems = items.slice(0, 3);
        const links = visibleItems.map(item =>
          `<li><a href="${item.href}" role="menuitem"><span class="notification-title">${item.title}</span></a></li>`);
        const footer = items.length > 3
          ? '<a class="notification-all" href="notifications.html" role="menuitem">Show more</a>'
          : "";
        popup.innerHTML = items.length
          ? `<strong>Notifications</strong><ul>${links.join("")}</ul>${footer}`
          : "<strong>No notifications</strong>";
        popup.querySelectorAll("a").forEach(link => {
          link.addEventListener("click", event => {
            if (link.classList.contains("notification-all")) return;
            const item = getNotificationItems().find(candidate => link.href.includes(candidate.href));
            if (!item) return;
            const destination = link.href;
            event.preventDefault();
            window.omniMarkItemRead(item.section, item.id);
            updateUnreadCount();
            window.location.href = destination;
          });
        });
      }

      notification.__omniRefreshNotifications = () => {
        updateUnreadCount();
        renderNotifications();
      };

      function positionPopup() {
        const bounds = notification.getBoundingClientRect();
        popup.style.top = `${bounds.bottom + 8}px`;
        popup.style.left = `${Math.max(8, bounds.right - popup.offsetWidth)}px`;
      }

      window.addEventListener("omni-unread-updated", () => {
        for (const notification of document.querySelectorAll(".notification-link")) {
          notification.__omniRefreshNotifications?.();
        }
      });

      notification.addEventListener("click", event => {
        if (event.target.closest(".notification-popup")) return;
        event.preventDefault();
        const isOpen = !popup.hidden;
        popup.hidden = isOpen;
        if (!isOpen) positionPopup();
        notification.setAttribute("aria-expanded", String(!isOpen));
      });

      updateUnreadCount();
      renderNotifications();

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
          popup.style.left = `${Math.max(8, bounds.right - popup.offsetWidth)}px`;
        }
      }
    });

    for (const menu of menus) {
      const toggle = menu.querySelector(".theme-toggle");
      toggle.removeAttribute("aria-haspopup");
      toggle.removeAttribute("aria-expanded");
      toggle.addEventListener("click", () => {
        applyTheme(root.dataset.theme === "dark" ? "light" : "dark");
      });
    }

    applyTheme(root.dataset.theme === "dark" ? "dark" : "light");
  });

  window.addEventListener("storage", event => {
    if (event.key === "omni-theme") {
      applyTheme(event.newValue === "dark" ? "dark" : "light", false);
    }
    if (event.key === "omni-unread-notifications" || event.key === "omni-cleared-alerts" || event.key === "omni-read-items") {
      for (const notification of document.querySelectorAll(".notification-link")) {
        notification.__omniRefreshNotifications?.();
      }
    }
  });
  window.addEventListener("omni-read-items-updated", () => {
    for (const notification of document.querySelectorAll(".notification-link")) {
      notification.__omniRefreshNotifications?.();
    }
  });
})();
