(() => {
  const key = "omni.currentEmployeeId";
  const select = document.getElementById("current-employee");
  if (!select) return;

  const style = document.createElement("style");
  style.textContent = `
    .current-employee { display: grid; gap: 4px; margin-left: auto; min-width: 180px; }
    .current-employee label { color: #666; font: 600 12px/1.2 system-ui, sans-serif; }
    .current-employee select { width: 100%; min-height: 36px; padding: 6px 9px; border: 1px solid #dedede; border-radius: 8px; background: #fff; color: #333; font: 14px system-ui, sans-serif; }
  `;
  document.head.append(style);

  select.disabled = true;

  let staff = [];
  let error = null;
  const storedId = () => {
    try { return localStorage.getItem(key) || ""; } catch { return ""; }
  };
  const saveId = id => {
    try {
      if (id) localStorage.setItem(key, id);
      else localStorage.removeItem(key);
    } catch { /* The selector still works for this page. */ }
  };
  const changed = () => window.dispatchEvent(new CustomEvent("omni:employee-changed", {
    detail: { id: select.value || null, name: select.selectedOptions[0]?.textContent || null }
  }));

  select.addEventListener("change", () => { saveId(select.value); changed(); });
  window.addEventListener("storage", event => {
    if (event.key !== key || !staff.length) return;
    const id = event.newValue || "";
    select.value = staff.some(member => String(member.id) === id) ? id : "";
    changed();
  });

  const ready = (async () => {
    for (const path of ["/staff", "/process-plans/staff"]) {
      try {
        const response = await fetch("http://127.0.0.1:8000" + path);
        if (!response.ok) continue;
        staff = (await response.json()).staff;
        break;
      } catch { /* Try the other staff route. */ }
    }
    if (!staff.length) throw new Error("Could not load employees");
    return staff;
  })()
    .then(() => {
      select.replaceChildren(
        new Option("Choose employee", ""),
        ...staff.map(member => new Option(member.name, String(member.id)))
      );
      const id = storedId();
      select.value = staff.some(member => String(member.id) === id) ? id : "";
      if (id && !select.value) saveId("");
      select.disabled = false;
      changed();
      return staff;
    })
    .catch(reason => {
      error = reason.message;
      select.replaceChildren(new Option("Employees unavailable", ""));
      return [];
    });

  window.OmniEmployee = {
    ready,
    getId: () => select.value || null,
    getName: () => select.value ? select.selectedOptions[0]?.textContent || null : null,
    getStaff: () => staff,
    getError: () => error,
    createAssigneeFilter({ options, selection, requested = [], onChange }) {
      let chosen = new Set(requested.map(String));
      const values = () => [...options.querySelectorAll('input[type="checkbox"]:checked')].map(input => input.value);
      const updateLabel = () => {
        const selected = [...options.querySelectorAll('input[type="checkbox"]:checked')];
        selection.textContent = selected.length === 0 ? "All"
          : selected.length === 1 ? selected[0].parentElement.textContent.trim()
            : selected.length + " selected";
      };
      const render = () => {
        const currentId = select.value;
        const me = staff.find(member => String(member.id) === currentId);
        const members = me ? [me, ...staff.filter(member => String(member.id) !== currentId)] : staff;
        const choices = [
          ...(me ? [members[0]] : []),
          { id: "unassigned", name: "Unassigned" },
          ...members.slice(me ? 1 : 0)
        ];
        options.replaceChildren(...choices.map(member => {
          const label = document.createElement("label");
          label.className = "multi-option";
          const input = document.createElement("input");
          input.type = "checkbox";
          input.value = String(member.id);
          input.checked = chosen.has(input.value);
          input.addEventListener("change", () => { chosen = new Set(values()); updateLabel(); onChange(); });
          label.append(input, document.createTextNode(" " + member.name + (member === me ? " (you)" : "")));
          return label;
        }));
        updateLabel();
      };
      window.addEventListener("omni:employee-changed", () => { chosen = new Set(values()); render(); });
      render();
      return { values };
    }
  };
})();
