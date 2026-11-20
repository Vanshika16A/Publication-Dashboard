import "./style.css";
import { applyTheme, disposeCharts, esc, INST, INST_KEYS, load, loadingMarkup, setTeam, TEAM, teamIndex, TEAMS, THEME } from "./lib.js";
import overview from "./views/overview.js";
import publications from "./views/publications.js";
import journals from "./views/journals.js";
import cited from "./views/cited.js";
import authors from "./views/authors.js";
import citation from "./views/citation.js";
import coauthor from "./views/coauthor.js";
import connections from "./views/connections.js";
import insights from "./views/insights.js";
import about from "./views/about.js";

const icon = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const VIEWS = [
  { group: "Statistics" },
  { id: "overview", label: "Overview", view: overview, scoped: false, icon: icon('<rect x="3" y="3" width="7" height="9" rx="2"/><rect x="14" y="3" width="7" height="5" rx="2"/><rect x="14" y="12" width="7" height="9" rx="2"/><rect x="3" y="16" width="7" height="5" rx="2"/>'),
    sub: "Broad trends and statistics across science and engineering publications of the three institutions." },
  { id: "publications", label: "Publications", view: publications, scoped: true, icon: icon('<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/>'),
    sub: "Publication trend, journal quartiles, conference ranks and research areas." },
  { id: "journals", label: "Top journals", view: journals, scoped: true, icon: icon('<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M8 7h8M8 11h6"/>'),
    sub: "Journals with the most papers from each institution." },
  { id: "cited", label: "Most cited", view: cited, scoped: true, icon: icon('<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>'),
    sub: "The most-cited papers as per OpenAlex citation counts at the time of data collection." },
  { id: "authors", label: "Authors", view: authors, scoped: true, icon: icon('<circle cx="9" cy="8" r="4"/><path d="M2 21a7 7 0 0 1 14 0"/><circle cx="18" cy="9" r="3"/><path d="M17 15a5 5 0 0 1 5 5"/>'),
    sub: "Information about affiliated authors across all time from OpenAlex." },
  { group: "Networks" },
  { id: "citation", label: "Citation network", view: citation, scoped: false, icon: icon('<circle cx="5" cy="6" r="2.5"/><circle cx="19" cy="5" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M7.4 6.7 16.5 5.4M6.5 8.2l4.3 7.6M17.7 7.3l-4.5 8.6"/>'),
    sub: "Papers (nodes) citing other papers in the dataset (arrows)." },
  { id: "coauthor", label: "Co-authorship", view: coauthor, scoped: false, icon: icon('<circle cx="6" cy="7" r="3"/><circle cx="18" cy="7" r="3"/><circle cx="12" cy="17" r="3"/><path d="M9 7h6M7.5 9.6l3 4.8M16.5 9.6l-3 4.8"/>'),
    sub: "Authors (nodes) linked when they wrote a paper together. Colours show institutions or Louvain communities." },
  { id: "connections", label: "Indian connections", view: connections, scoped: false, icon: icon('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'),
    sub: "Partner institutions in India: shared papers and citations flowing in and out." },
  { group: "Findings" },
  { id: "insights", label: "Insights", view: insights, scoped: false, icon: icon('<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1.1 2.2h5c.1-1 .5-1.7 1.1-2.2A6 6 0 0 0 12 3z"/>'),
    sub: "Written findings from the papers, authors and networks behind the other pages." },
  { group: "Project" },
  { id: "about", label: "Glossary", view: about, scoped: false, icon: icon('<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.01"/>'),
    sub: "How the data was made and what the network terms mean." },
];

const state = { view: null, scope: "All", current: null };
const $ = (s) => document.querySelector(s);

function renderNav() {
  $("#nav").innerHTML = VIEWS.map((v) => (v.group ? `<div class="nav-group">${v.group}</div>`
    : `<button data-view="${v.id}">${v.id === "insights" ? `<div class="nav-hop">${v.icon}<span>${v.label}</span></div>` : `${v.icon}<span>${v.label}</span>`}</button>`)).join("");
  $("#nav").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-view]");
    if (b) location.hash = b.dataset.view;
  });
  const scopes = ["All", ...INST_KEYS];
  $("#scope").innerHTML = scopes.map((s) => `<button data-scope="${s}" title="${s === "All" ? "All three institutions" : esc(INST[s].name)}">
      ${s === "All" ? "" : `<span class="dot" style="background:${INST[s].color}"></span>`}${s}</button>`).join("");
  $("#scope").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-scope]");
    if (!b || b.dataset.scope === state.scope) return;
    state.scope = b.dataset.scope;
    show(state.view, true);
  });
}

async function show(id, keepScroll = false) {
  const def = VIEWS.find((v) => v.id === id) || VIEWS[1];
  state.view = def.id;
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === def.id));
  document.querySelectorAll("#scope button").forEach((b) => b.classList.toggle("active", b.dataset.scope === state.scope));
  $("#scope").hidden = !def.scoped;
  $("#page-title").textContent = def.label;
  $("#page-sub").textContent = def.sub;
  if (state.current?.destroy) state.current.destroy();
  disposeCharts();
  // team-size filter (chosen on Overview): a reminder on every other page it applies to (not Insights or Glossary)
  const banner = $("#team-banner");
  banner.hidden = TEAM === "all" || ["overview", "insights", "about"].includes(def.id);
  if (!banner.hidden) {
    banner.innerHTML = `<span>Showing only <b>${esc(TEAMS[TEAM].short)}</b>. The filter is set on the Overview page.</span>
      <button class="btn" type="button" data-team-reset>Show all papers</button>`;
  }
  const el = $("#view");
  el.innerHTML = loadingMarkup();
  if (!keepScroll) window.scrollTo({ top: 0 });
  try {
    state.current = (await def.view(el, { scope: state.scope })) || null;
  } catch (err) {
    console.error(err);
    el.innerHTML = `<div class="card"><h3>Could not load this view</h3><p class="note">${esc(err.message)}</p></div>`;
  }
}

function setCollapsed(collapsed) {
  $(".app").classList.toggle("sidebar-collapsed", collapsed);
  const btn = $("#collapse");
  const what = collapsed ? "Expand sidebar" : "Collapse sidebar";
  btn.setAttribute("aria-expanded", String(!collapsed));
  btn.setAttribute("aria-label", what);
  btn.title = `${what} ( [ )`;
  // labels are hidden in the icon rail, so show them on hover instead
  document.querySelectorAll("#nav button").forEach((b) => { b.title = collapsed ? b.textContent.trim() : ""; });
  try { localStorage.setItem("dpcn-sidebar", collapsed ? "collapsed" : "open"); } catch { /* storage unavailable */ }
}

function initSidebar() {
  let collapsed = false;
  try { collapsed = localStorage.getItem("dpcn-sidebar") === "collapsed"; } catch { /* storage unavailable */ }
  setCollapsed(collapsed);
  const toggle = () => setCollapsed(!$(".app").classList.contains("sidebar-collapsed"));
  $("#collapse").addEventListener("click", toggle);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "[" || e.ctrlKey || e.metaKey || e.altKey || e.target.closest("input, select, textarea, [contenteditable]")) return;
    toggle();
  });
  // sigma and ECharts only re-measure on window resize, so fire one when the column width settles
  $(".app").addEventListener("transitionend", (e) => {
    if (e.target === $(".app") && e.propertyName === "grid-template-columns") window.dispatchEvent(new Event("resize"));
  });
}

const SUN = icon('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>');
const MOON = icon('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>');

function setTheme(name) {
  applyTheme(name);
  const next = THEME === "dark" ? "light" : "dark";
  const btn = $("#theme");
  btn.innerHTML = `${THEME === "dark" ? SUN : MOON}<span>${next === "dark" ? "Dark" : "Light"} theme</span>`;
  btn.setAttribute("aria-label", `Switch to ${next} theme`);
  btn.title = `Switch to ${next} theme`;
  try { localStorage.setItem("dpcn-theme", THEME); } catch { /* storage unavailable */ }
}

function initTheme() {
  setTheme(document.documentElement.dataset.theme);  // set from storage by the inline script in index.html
  // charts and graphs draw on canvas with colours fixed at creation, so redraw the current view
  $("#theme").addEventListener("click", () => { setTheme(THEME === "dark" ? "light" : "dark"); show(state.view, true); });
}

async function init() {
  initTheme();
  renderNav();
  initSidebar();
  // a saved team filter whose data files are not published falls back to all papers
  const teams = await teamIndex();
  if (TEAM !== "all" && !teams.groups.some((g) => g.id === TEAM)) setTeam("all");
  window.addEventListener("teamchange", () => show(state.view, true));
  $("#team-banner").addEventListener("click", (e) => { if (e.target.closest("[data-team-reset]")) setTeam("all"); });
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  show(location.hash.slice(1) || "overview");
}
init();
