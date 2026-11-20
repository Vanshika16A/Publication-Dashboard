// Shared helpers: data loading, colours, number formatting, DOM, charts, tables.
import * as echarts from "echarts";

// ---------------------------------------------------------------- data

const cache = new Map();
/** Load dashboard/public/data/<name>.json once and keep it. */
export function load(name) {
  // with a team-size filter on, every page except Insights reads its copy from data/team/<id>/
  const path = TEAM !== "all" && !TEAM_EXEMPT.has(name) ? `team/${TEAM}/${name}` : name;
  if (!cache.has(path)) {
    cache.set(path, fetch(`./data/${path}.json`).then((r) => {
      if (!r.ok) throw new Error(`could not load ${path}.json (${r.status})`);
      return r.json();
    }));
  }
  return cache.get(path);
}

// ---------------------------------------------------------------- team-size filter (set on the Overview page)

// papers by number of authors; the data files for each group are written by `python -m collector dashboard-data`
export const TEAMS = {
  all: { label: "All papers", short: "All papers" },
  le10: { label: "≤ 10 authors", short: "papers with 10 or fewer authors" },
  gt10: { label: "> 10 authors", short: "papers with more than 10 authors" },
};
const TEAM_EXEMPT = new Set(["insights", "team/index"]);  // Insights always uses every paper
export let TEAM = "all";
try { if (TEAMS[localStorage.getItem("dpcn-team")]) TEAM = localStorage.getItem("dpcn-team"); } catch { /* storage unavailable */ }

// which groups have data files (team/index.json); empty when the dashboard data predates the filter
export function teamIndex() {
  if (!cache.has("team/index")) {
    cache.set("team/index", fetch("./data/team/index.json").then((r) => (r.ok ? r.json() : { groups: [] })).catch(() => ({ groups: [] })));
  }
  return cache.get("team/index");
}

export function setTeam(id) {
  if (!TEAMS[id] || id === TEAM) return;
  TEAM = id;
  try { localStorage.setItem("dpcn-team", id); } catch { /* storage unavailable */ }
  window.dispatchEvent(new CustomEvent("teamchange", { detail: id }));
}

// ---------------------------------------------------------------- colours

// Colours live in two places: CSS custom properties (style.css, one block per theme) for the page,
// and T below for canvas drawing (charts, graphs), read from those same properties by applyTheme().
// The objects and arrays exported here are filled in place, so imports stay valid across a theme switch.
// Research areas: Flexoki accents and tints other than the three institution colours, fixed per field name, so a field
// (and a co-authorship community, coloured by its main field) has the same colour on every page and in both themes.
const FIELD_COLORS = {
  "Engineering": "#bc5215",
  "Materials Science": "#5abdac",
  "Physics and Astronomy": "#92bfdb",
  "Computer Science": "#66800b",
  "Biochemistry, Genetics and Molecular Biology": "#a02f6f",
  "Agricultural and Biological Sciences": "#bec97e",
  "Environmental Science": "#1c6c66",
  "Chemistry": "#eccb60",
  "Mathematics": "#6f6e69",
  "Earth and Planetary Sciences": "#71320d",
  "Energy": "#f9ae77",
  "Immunology and Microbiology": "#f89a8a",
  "Neuroscience": "#f4a4c2",
  "Chemical Engineering": "#205ea6",
};
const THEMES = ["light", "dark"];
/** Current canvas colours (see applyTheme). */
export const T = {};
export const PALETTE = Object.values(FIELD_COLORS);
/** Colour of an OpenAlex field; anything unknown is drawn as "other". */
export const fieldColor = (name) => FIELD_COLORS[name] ?? T.stone;

// One small line icon per OpenAlex field (24 × 24 stroke paths in the style of the sidebar icons).
const FIELD_ICONS = {
  "Engineering": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  "Materials Science": '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
  "Physics and Astronomy": '<circle cx="12" cy="12" r="1"/><path d="M20.2 20.2c2.04-2.03.02-7.36-4.5-11.9-4.54-4.52-9.87-6.54-11.9-4.5-2.04 2.03-.02 7.36 4.5 11.9 4.54 4.52 9.87 6.54 11.9 4.5Z"/><path d="M15.7 15.7c4.52-4.54 6.54-9.87 4.5-11.9-2.03-2.04-7.36-.02-11.9 4.5-4.52 4.54-6.54 9.87-4.5 11.9 2.03 2.04 7.36.02 11.9-4.5Z"/>',
  "Computer Science": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
  "Biochemistry, Genetics and Molecular Biology": '<path d="M2 15c6.67-6 13.33 0 20-6"/><path d="M9 22c1.8-2 2.52-4 2.81-6"/><path d="M15 2c-1.8 2-2.52 4-2.81 6"/><path d="m17 6-2.5-2.5M14 8l-1-1M7 18l2.5 2.5M3.5 14.5l.5.5M20 9l.5.5M6.5 12.5l1 1M16.5 10.5l1 1M10 16l1.5 1.5"/>',
  "Agricultural and Biological Sciences": '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>',
  "Environmental Science": '<path d="m17 14 3 3.3a1 1 0 0 1-.7 1.7H4.7a1 1 0 0 1-.7-1.7L7 14h-.3a1 1 0 0 1-.7-1.7L9 9h-.2A1 1 0 0 1 8 7.3L12 3l4 4.3a1 1 0 0 1-.8 1.7H15l3 3.3a1 1 0 0 1-.7 1.7H17Z"/><path d="M12 22v-3"/>',
  "Chemistry": '<path d="M10 2v7.53a2 2 0 0 1-.21.9L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.07-10.13A2 2 0 0 1 14 9.53V2"/><path d="M8.5 2h7M7 16h10"/>',
  "Mathematics": '<path d="M18 7V5a1 1 0 0 0-1-1H6.5a.5.5 0 0 0-.4.8l4.5 6a2 2 0 0 1 0 2.4l-4.5 6a.5.5 0 0 0 .4.8H17a1 1 0 0 0 1-1v-2"/>',
  "Earth and Planetary Sciences": '<path d="m8 3 4 8 5-5 5 15H2L8 3z"/>',
  "Energy": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
  "Immunology and Microbiology": '<path d="M6 18h8M3 22h18M9 14h2"/><path d="M14 22a7 7 0 1 0 0-14h-1"/><path d="M9 12a2 2 0 0 1-2-2V6h6v4a2 2 0 0 1-2 2Z"/><path d="M12 6V3a1 1 0 0 0-1-1H9a1 1 0 0 0-1 1v3"/>',
  "Neuroscience": '<path d="M12 5a3 3 0 1 0-6 .13 4 4 0 0 0-2.52 5.77 4 4 0 0 0 .55 6.59A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 6 .13 4 4 0 0 1 2.52 5.77 4 4 0 0 1-.55 6.59A4 4 0 1 1 12 18Z"/><path d="M12 5v13"/>',
  "Chemical Engineering": '<path d="M2 20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8l-7 5V8l-7 5V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/><path d="M17 18h1M12 18h1M7 18h1"/>',
};
const iconSvg = (name, color) => FIELD_ICONS[name]
  && `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${FIELD_ICONS[name]}</svg>`;
/** Inline SVG icon of a field for HTML (inherits the text colour), or "" for an unknown field. */
export const fieldIcon = (name, size = 14) => (FIELD_ICONS[name]
  ? iconSvg(name, "currentColor").replace("<svg ", `<svg class="field-icon" width="${size}" height="${size}" aria-hidden="true" `) : "");
/** Data URL of a field icon drawn in `color`, for canvas labels (ECharts rich text), or null for an unknown field. */
export const fieldIconUrl = (name, color) => (FIELD_ICONS[name] ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(iconSvg(name, color))}` : null);
export const QUARTILE_COLORS = {};
export const RANK_COLORS = {};
export let SHARED = "";
export let ALL_COLOR = "";
export let THEME = "light";

export const INST = {
  DU: { name: "University of Delhi", bit: 1, get color() { return T.du; } },
  JNU: { name: "Jawaharlal Nehru University", bit: 2, get color() { return T.jnu; } },
  UoH: { name: "University of Hyderabad", bit: 4, get color() { return T.uoh; } },
};
export const INST_KEYS = ["DU", "JNU", "UoH"];

/** Switch the page to "light" or "dark" and refresh every colour used for drawing. Views must be redrawn after. */
export function applyTheme(name) {
  THEME = THEMES.includes(name) ? name : "light";
  document.documentElement.dataset.theme = THEME;
  const css = getComputedStyle(document.documentElement);
  const v = (key) => css.getPropertyValue(`--${key}`).trim();
  Object.assign(T, {
    stage: v("stage"), text: v("text"), text2: v("text-2"), muted: v("muted"), accent: v("accent"), ring: v("ring"), bad: v("bad"),
    du: v("du"), jnu: v("jnu"), uoh: v("uoh"), shared: v("shared"), all: v("all"),
    edge: v("edge"), edgeFocus: v("edge-focus"), axis: v("chart-axis"), split: v("chart-split"), hover: v("chart-hover"),
    tipBg: v("tip-bg"), tipBorder: v("tip-border"), tipText: v("tip-text"), tipShadow: v("tip-shadow"),
    brand: v("brand"), stone: v("stone"), unranked: v("unranked"), onDark: v("on-dark"), onLight: v("on-light"),
    ifBands: [v("if-hi"), v("if-mid"), v("if-lo")],
    seq: [0, 1, 2, 3, 4].map((i) => v(`seq-${i}`)),
  });
  SHARED = T.shared;
  ALL_COLOR = T.all;
  // ordered categories take the brand ramp, best first
  Object.assign(QUARTILE_COLORS, { Q1: T.seq[4], Q2: T.seq[3], Q3: T.seq[2], Q4: T.seq[1], "Not ranked": T.unranked });
  Object.assign(RANK_COLORS, { "A*": T.seq[4], A: T.seq[3], B: T.seq[2], C: T.seq[1], "SCImago series": T.stone, "Not ranked": T.unranked });
  registerChartTheme();
}

export function scopeColor(scope) {
  return scope === "All" ? ALL_COLOR : INST[scope].color;
}
/** Colour for a paper / author by institution bit mask (several institutions -> shared). */
export function maskColor(mask) {
  if (mask === 1) return INST.DU.color;
  if (mask === 2) return INST.JNU.color;
  if (mask === 4) return INST.UoH.color;
  return SHARED;
}
export function maskInsts(mask) {
  return INST_KEYS.filter((k) => mask & INST[k].bit);
}
const rgb = (hex) => { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
/** Mix two hex colours: t = 0 gives a, t = 1 gives b. */
export function mix(a, b, t) {
  const x = rgb(a), y = rgb(b);
  return `#${x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, "0")).join("")}`;
}
/** Blend a hex colour towards the graph background (for faded items). */
export function fade(hex, amount = 0.82) {
  return mix(hex, T.stage, amount);
}
/** A see-through looking version of a colour for graph edges, pre-blended with the graph background (see --edge in style.css). */
export const tint = (hex, alpha) => mix(hex, T.stage, 1 - alpha);
/** Point t (0 = least, 1 = most) on the ordered ramp (--seq-0 … --seq-4), through every stop. */
export function rampColor(t) {
  const x = Math.max(0, Math.min(1, t)) * (T.seq.length - 1);
  const i = Math.min(Math.floor(x), T.seq.length - 2);
  return mix(T.seq[i], T.seq[i + 1], x - i);
}
/** Text colour that reads on a filled shape of colour hex. */
export function onColor(hex) {
  const [r, g, b] = rgb(hex).map((v) => { const c = v / 255; return c <= 0.04 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.3 ? T.onLight : T.onDark;
}
/** Colour for a year on the old-to-new ramp. */
export const yearColor = (year, from = 2016, to = 2026) => rampColor((year - from) / (to - from));
export function rgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

// ---------------------------------------------------------------- formatting

export const fmt = (n) => (n === null || n === undefined ? "–" : Number(n).toLocaleString("en-IN"));
export const fmtCompact = (n) => Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
export const pct = (n, d = 1) => (n === null || n === undefined ? "–" : `${Number(n).toFixed(d)}%`);
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
export const chips = (insts) => insts.map((i) => `<span class="chip ${i}">${i}</span>`).join("");
export const qBadge = (q) => (q ? `<span class="q ${q.replace("*", "s")}">${esc(q)}</span>` : `<span class="note">–</span>`);
export const doiLink = (doi) => (doi ? `<a href="https://doi.org/${esc(doi.replace("https://doi.org/", ""))}" target="_blank" rel="noopener">DOI ↗</a>` : "");

// ---------------------------------------------------------------- DOM

export function html(strings, ...values) {
  return strings.reduce((out, s, i) => out + s + (i < values.length ? values[i] : ""), "");
}
export function mount(container, markup) {
  container.innerHTML = markup;
  return (sel) => container.querySelector(sel);
}
export function debounce(fn, ms = 200) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
export const loadingMarkup = (what = "Loading") => `<div class="loading"><div class="spinner"></div>${esc(what)}…</div>`;

// ---------------------------------------------------------------- charts

function registerChartTheme() {
  const axis = { axisLine: { lineStyle: { color: T.axis } }, axisTick: { show: false },
    axisLabel: { color: T.muted, margin: 10 }, splitLine: { lineStyle: { color: T.split } },
    nameTextStyle: { color: T.muted } };
  echarts.registerTheme("dash", {
    color: [...PALETTE],
    backgroundColor: "transparent",
    textStyle: { fontFamily: "Atkinson Hyperlegible Next, system-ui, sans-serif", color: T.text2 },
    legend: { textStyle: { color: T.text2, fontSize: 12 }, icon: "circle", itemWidth: 8, itemHeight: 8, itemGap: 18 },
    tooltip: { backgroundColor: T.tipBg, borderColor: T.tipBorder, borderWidth: 1, padding: [9, 12],
      textStyle: { color: T.tipText, fontSize: 12.5 }, extraCssText: `border-radius:6px;box-shadow:${T.tipShadow};max-width:340px;white-space:normal;overflow-wrap:anywhere;line-height:1.5;` },
    categoryAxis: axis, valueAxis: axis, logAxis: axis,
    grid: { left: 4, right: 16, top: 40, bottom: 4, containLabel: true },
  });
}
/** Faint column highlight for axis tooltips. */
export const shadowPointer = () => ({ type: "shadow", shadowStyle: { color: T.hover } });

/**
 * Tooltip position that keeps the box inside the window. The tooltip lives on <body> (so small
 * cards and panels cannot clip it); the returned point is still relative to the chart.
 */
function onScreen(el) {
  return (point, _params, _dom, _rect, size) => {
    const box = el.getBoundingClientRect();
    const [w, h] = size.contentSize;
    const gap = 14, pad = 8;
    let x = point[0] + gap, y = point[1] + gap;
    if (box.left + x + w > window.innerWidth - pad) x = point[0] - w - gap;
    if (box.top + y + h > window.innerHeight - pad) y = point[1] - h - gap;
    x = Math.max(x, pad - box.left);
    y = Math.max(y, pad - box.top);
    return [x, y];
  };
}

const charts = new Set();
/** Create an ECharts instance in `el` with the dashboard theme; resized with the window. */
export function chart(el, option) {
  const c = echarts.init(el, "dash", { renderer: "canvas" });
  const tooltip = option.tooltip && { appendTo: "body", position: onScreen(el), ...option.tooltip };
  c.setOption({ animationDuration: 700, animationEasing: "cubicOut", ...(location.search.includes("static") && { animation: false }), ...option, ...(tooltip && { tooltip }) });
  charts.add(c);
  return c;
}
export function disposeCharts() {
  charts.forEach((c) => c.dispose());
  charts.clear();
}
window.addEventListener("resize", debounce(() => charts.forEach((c) => c.resize()), 120));
export { echarts };

export const gradient = (hex, top = 0.28, bottom = 0.0) => new echarts.graphic.LinearGradient(0, 0, 0, 1, [
  { offset: 0, color: rgba(hex, top) }, { offset: 1, color: rgba(hex, bottom) }]);

// ---------------------------------------------------------------- tables

/**
 * Sortable, searchable, paged table.
 * columns: [{key, label, num?, render?(row), sortValue?(row), width?}]
 */
export function dataTable(container, { columns, rows, pageSize = 25, sortKey, sortDir = -1, search = null, empty = "No rows" }) {
  let state = { sortKey, sortDir, page: 0, query: "", rows };
  const filtered = () => {
    let out = state.rows;
    if (state.query && search) {
      const q = state.query.toLowerCase();
      out = out.filter((r) => search(r).toLowerCase().includes(q));
    }
    if (state.sortKey) {
      const col = columns.find((c) => c.key === state.sortKey);
      const val = col.sortValue || ((r) => r[col.key]);
      out = [...out].sort((a, b) => {
        const x = val(a), y = val(b);
        if (x === y) return 0;
        if (x === null || x === undefined) return 1;
        if (y === null || y === undefined) return -1;
        return (x > y ? 1 : -1) * state.sortDir;
      });
    }
    return out;
  };
  function draw() {
    const list = filtered();
    const pages = Math.max(1, Math.ceil(list.length / pageSize));
    state.page = Math.min(state.page, pages - 1);
    const slice = list.slice(state.page * pageSize, (state.page + 1) * pageSize);
    container.innerHTML = `
      <div class="table-wrap"><table>
        <thead><tr>${columns.map((c) => `<th data-key="${c.key}" class="${c.num ? "num " : ""}${c.sortable === false ? "" : "sortable"} ${state.sortKey === c.key ? `sorted ${state.sortDir > 0 ? "asc" : ""}` : ""}" ${c.width ? `style="width:${c.width}"` : ""}>${c.label}</th>`).join("")}</tr></thead>
        <tbody>${slice.length ? slice.map((r, i) => `<tr>${columns.map((c) => `<td class="${c.num ? "num" : ""} ${c.cls || ""}">${c.render ? c.render(r, state.page * pageSize + i) : esc(r[c.key])}</td>`).join("")}</tr>`).join("")
          : `<tr><td colspan="${columns.length}" class="note">${empty}</td></tr>`}</tbody>
      </table></div>
      <div class="pager"><span>${fmt(list.length)} rows</span>
        <span><button class="btn" data-p="-1" ${state.page === 0 ? "disabled" : ""}>‹ Prev</button>
        &nbsp;Page ${state.page + 1} of ${pages}&nbsp;
        <button class="btn" data-p="1" ${state.page >= pages - 1 ? "disabled" : ""}>Next ›</button></span></div>`;
    container.querySelectorAll("th.sortable").forEach((th) => th.addEventListener("click", () => {
      const key = th.dataset.key;
      state.sortDir = state.sortKey === key ? -state.sortDir : -1;
      state.sortKey = key;
      draw();
    }));
    container.querySelectorAll("[data-p]").forEach((b) => b.addEventListener("click", () => { state.page += Number(b.dataset.p); draw(); }));
  }
  draw();
  return {
    setQuery(q) { state.query = q; state.page = 0; draw(); },
    setRows(r) { state.rows = r; state.page = 0; draw(); },
  };
}
