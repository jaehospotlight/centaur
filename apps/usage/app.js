const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let DATA = { tools: [], users: [] };
let state = {
  view: "tools",
  sort: "threads",
  dir: "desc",
  search: "",
  minCalls: 0,
  minUsers: 0,
  userMinCalls: 0,
  userMinThreads: 0,
};

const TOOL_COLS = [
  { key: "rank",     label: "#",        num: true,  noSort: true, w: "3.5%",  cls: "" },
  { key: "tool",     label: "Tool",     num: false, w: "10%",     cls: "tool-name" },
  { key: "calls",    label: "Calls",    num: true,  w: "7%" },
  { key: "threads",  label: "Threads",  num: true,  w: "7%" },
  { key: "users",    label: "Users",    num: true,  w: "6%" },
  { key: "methods_count", label: "Methods", num: true, w: "6%", cls: "col-methods" },
  { key: "calls_per_thread", label: "C/T", num: true, w: "5%", cls: "col-cpt" },
  { key: "method1",  label: "#1 Method", num: false, w: "17%", noSort: true, cls: "method" },
  { key: "method2",  label: "#2 Method", num: false, w: "15%", noSort: true, cls: "method col-method2" },
  { key: "method3",  label: "#3 Method", num: false, w: "13%", noSort: true, cls: "method col-method3" },
  { key: "first_seen", label: "First",  num: false, w: "7%",  cls: "col-first" },
  { key: "last_seen",  label: "Last",   num: false, w: "7%",  cls: "col-last" },
];

const USER_COLS = [
  { key: "rank",     label: "#",       num: true,  noSort: true, w: "3.5%" },
  { key: "name",     label: "Name",    num: false, w: "14%",     cls: "user-name" },
  { key: "handle",   label: "Handle",  num: false, w: "9%" },
  { key: "calls",    label: "Calls",   num: true,  w: "7%" },
  { key: "threads",  label: "Threads", num: true,  w: "7%" },
  { key: "tools",    label: "Tools",   num: true,  w: "6%" },
  { key: "calls_per_thread", label: "C/T", num: true, w: "6%", cls: "col-cpt" },
  { key: "tool1",    label: "#1 Tool", num: false, w: "16%", noSort: true, cls: "method" },
  { key: "tool2",    label: "#2 Tool", num: false, w: "16%", noSort: true, cls: "method col-method2" },
  { key: "tool3",    label: "#3 Tool", num: false, w: "14%", noSort: true, cls: "method col-method3 col-tool3" },
];

function fmt(n) {
  if (n == null) return "\u2014";
  return Number(n).toLocaleString();
}

function getCols() {
  return state.view === "tools" ? TOOL_COLS : USER_COLS;
}

function getRows() {
  const src = state.view === "tools" ? DATA.tools : DATA.users;
  let rows = [...src];

  if (state.search) {
    const q = state.search.toLowerCase();
    rows = rows.filter((r) => {
      const fields = state.view === "tools"
        ? [r.tool, r.method1, r.method2, r.method3]
        : [r.name, r.handle, r.tool1, r.tool2, r.tool3];
      return fields.some((f) => f && f.toLowerCase().includes(q));
    });
  }

  if (state.view === "tools") {
    if (state.minCalls > 0) rows = rows.filter((r) => r.calls >= state.minCalls);
    if (state.minUsers > 0) rows = rows.filter((r) => r.users >= state.minUsers);
  } else {
    if (state.userMinCalls > 0) rows = rows.filter((r) => r.calls >= state.userMinCalls);
    if (state.userMinThreads > 0) rows = rows.filter((r) => r.threads >= state.userMinThreads);
  }

  const key = state.sort;
  const mult = state.dir === "desc" ? -1 : 1;
  rows.sort((a, b) => {
    let av = a[key], bv = b[key];
    if (typeof av === "string") return mult * av.localeCompare(bv);
    return mult * ((av ?? 0) - (bv ?? 0));
  });

  return rows;
}

function renderHead() {
  const cols = getCols();
  const ths = cols.map((c) => {
    const sorted = state.sort === c.key;
    const arrow = sorted ? (state.dir === "desc" ? "\u25BC" : "\u25B2") : "";
    const cls = [
      c.num ? "num" : "",
      c.noSort ? "no-sort" : "",
      sorted ? "sorted" : "",
      c.cls || "",
    ].filter(Boolean).join(" ");
    return `<th class="${cls}" data-col="${c.key}"${c.w ? ` style="width:${c.w}"` : ""}>
      ${c.label}${arrow ? `<span class="sort-arrow">${arrow}</span>` : ""}
    </th>`;
  }).join("");
  $("#thead").innerHTML = `<tr>${ths}</tr>`;
}

function renderBody() {
  const cols = getCols();
  const rows = getRows();
  $("#row-count").textContent = `${rows.length} ${state.view}`;

  const html = rows.map((r, i) => {
    const tds = cols.map((c) => {
      const cls = [c.num ? "num" : "", c.cls || ""].filter(Boolean).join(" ");
      let val;
      if (c.key === "rank") {
        val = i + 1;
      } else if (c.key === "handle" && state.view === "users") {
        val = r.handle === "\u2014" ? "\u2014" : `@${r.handle}`;
      } else if (c.num) {
        val = fmt(r[c.key]);
      } else {
        val = r[c.key] || "\u2014";
      }
      return `<td class="${cls}">${val}</td>`;
    }).join("");
    return `<tr>${tds}</tr>`;
  }).join("");

  $("#tbody").innerHTML = html;
}

function render() {
  renderHead();
  renderBody();
}

function syncPills(name, value) {
  $$(`input[name="${name}"]`).forEach((r) => {
    const checked = r.value === String(value);
    r.checked = checked;
    r.closest(".radio-pill").classList.toggle("active", checked);
  });
}

function init() {
  fetch("data.json")
    .then((r) => r.json())
    .then((d) => {
      DATA = d;
      render();
    });

  $$('input[name="view"]').forEach((r) => {
    r.addEventListener("change", () => {
      state.view = r.value;
      state.sort = r.value === "tools" ? "threads" : "calls";
      state.dir = "desc";
      state.search = "";
      $("#search").value = "";
      $("#tools-filters").hidden = state.view !== "tools";
      $("#users-filters").hidden = state.view !== "users";
      syncPills("view", state.view);
      render();
    });
  });

  $$('input[name="min-calls"]').forEach((r) => {
    r.addEventListener("change", () => {
      state.minCalls = Number(r.value);
      syncPills("min-calls", r.value);
      renderBody();
    });
  });

  $$('input[name="min-users"]').forEach((r) => {
    r.addEventListener("change", () => {
      state.minUsers = Number(r.value);
      syncPills("min-users", r.value);
      renderBody();
    });
  });

  $$('input[name="user-min-calls"]').forEach((r) => {
    r.addEventListener("change", () => {
      state.userMinCalls = Number(r.value);
      syncPills("user-min-calls", r.value);
      renderBody();
    });
  });

  $$('input[name="user-min-threads"]').forEach((r) => {
    r.addEventListener("change", () => {
      state.userMinThreads = Number(r.value);
      syncPills("user-min-threads", r.value);
      renderBody();
    });
  });

  $("#search").addEventListener("input", (e) => {
    state.search = e.target.value;
    renderBody();
  });

  document.addEventListener("click", (e) => {
    const th = e.target.closest("th[data-col]");
    if (!th || th.classList.contains("no-sort")) return;
    const col = th.dataset.col;
    if (state.sort === col) {
      state.dir = state.dir === "desc" ? "asc" : "desc";
    } else {
      state.sort = col;
      state.dir = "desc";
    }
    render();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== $("#search")) {
      e.preventDefault();
      $("#search").focus();
    }
  });
}

init();
