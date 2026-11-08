(() => {
  const key = "omni.currentEmployeeId";
  const staffCacheKey = "omni.staffCache";
  const select = document.getElementById("current-employee");
  if (!select) return;

  let staff = [];
  try {
    const cached = JSON.parse(sessionStorage.getItem(staffCacheKey) || "null");
    if (Array.isArray(cached)) staff = cached.filter(member => member && member.id != null && typeof member.name === "string");
  } catch { /* Load the staff list normally. */ }
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
  const showStaff = (verifyId = false) => {
    select.replaceChildren(
      new Option("Choose employee", ""),
      ...staff.map(member => new Option(member.name, String(member.id)))
    );
    const id = storedId();
    select.value = staff.some(member => String(member.id) === id) ? id : "";
    if (verifyId && id && !select.value) saveId("");
    select.disabled = false;
  };
  if (staff.length) showStaff();
  else select.disabled = true;
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
        const fetchedStaff = (await response.json()).staff;
        if (!Array.isArray(fetchedStaff) || !fetchedStaff.length) continue;
        staff = fetchedStaff;
        try { sessionStorage.setItem(staffCacheKey, JSON.stringify(staff)); } catch { /* Continue without a cache. */ }
        break;
      } catch { /* Try the other staff route. */ }
    }
    if (!staff.length) throw new Error("Could not load employees");
    return staff;
  })()
    .then(() => {
      showStaff(true);
      changed();
      return staff;
    })
    .catch(reason => {
      if (staff.length) {
        changed();
        return staff;
      }
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
