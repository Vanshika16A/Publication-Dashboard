import { hoverFromList, ICONS, markItem, NetworkView, stageMarkup } from "../graph.js";
import { chart, chips, debounce, doiLink, esc, fmt, INST, INST_KEYS, load, maskColor, maskInsts, mount, fieldColor, rgba, SHARED, T, yearColor } from "../lib.js";

const MODES = [
  { id: "pagerank", title: "Most influential", text: "Top papers by PageRank inside the dataset", list: "Top papers by PageRank" },
  { id: "indeg", title: "Most cited here", text: "Top papers by citations from other papers in the dataset", list: "Most cited by papers here" },
  { id: "cross", title: "Across institutions", text: "Only citations between different assigned institutions", list: "Papers citing across institutions" },
  { id: "ego", title: "Neighbourhood", text: "One paper, what it cites and what cites it", list: "Paper neighbourhood" },
];
const LIST_MAX = 300;  // longer lists stay in the graph only
const DEFAULTS = { size: 1200, field: -1, from: 2016, to: 2026, hideIsolated: true, colorBy: "inst", sizeBy: "pagerank" };

export default async function citation(el) {
  el.innerHTML = `<div class="loading"><div class="spinner"></div>Loading the citation network (36k papers)…</div>`;
  const data = await load("citation");
  const N = data.nodes;
  const n = N.id.length;
  const flat = data.edges;
  // adjacency (outgoing = cites, incoming = cited by)
  const outs = Array.from({ length: n }, () => []);
  const ins = Array.from({ length: n }, () => []);
  for (let i = 0; i < flat.length; i += 2) { outs[flat[i]].push(flat[i + 1]); ins[flat[i + 1]].push(flat[i]); }

  const state = { mode: "indeg", ...DEFAULTS, insts: new Set(INST_KEYS), ego: null, depth: 1 };
  const years = [...new Set(N.year)].sort();
  const s = data.summary;

  mount(el, `
    <div class="net">
      <div class="card net-bar">
        <div class="net-bar-top">
          <div class="seg modes" id="modes" role="group" aria-label="View">${MODES.map((m) => `<button type="button" data-mode="${m.id}" title="${m.text}">${m.title}</button>`).join("")}</div>
          <div class="suggest net-search"><input class="input search" id="search" placeholder="Find a paper by title…" aria-label="Find a paper by title" autocomplete="off" /><div class="suggest-box" id="suggest" hidden></div></div>
        </div>
        <div class="filter-row" role="group" aria-label="Filters and style">
          <div class="fgroup" id="depth-group" hidden><span class="flabel">Depth</span>
            <div class="seg" id="depth" role="group" aria-label="Depth"><button type="button" data-d="1" class="active">1 step</button><button type="button" data-d="2">2 steps</button></div></div>
          <div class="fgroup"><span class="flabel">Institutions</span>
            <div class="checks" id="insts">${INST_KEYS.map((k) => `<label class="check"><input type="checkbox" value="${k}" checked><i style="background:${INST[k].color}"></i>${k}</label>`).join("")}</div></div>
          <div class="fgroup"><label class="flabel" for="field">Field</label>
            <select class="select" id="field"><option value="-1">All fields</option>${data.fields.map((f, i) => `<option value="${i}">${esc(f)}</option>`).join("")}</select></div>
          <div class="fgroup"><label class="flabel" for="from">Years</label>
            <div class="years"><select class="select" id="from">${years.map((y) => `<option>${y}</option>`).join("")}</select>–<select class="select" id="to" aria-label="Last year">${years.map((y) => `<option>${y}</option>`).join("")}</select></div></div>
          <div class="fgroup"><label class="flabel" for="size">Papers shown <output id="size-v"></output></label><input type="range" id="size" min="100" max="3000" step="100" /></div>
          <div class="fgroup"><span class="flabel">Unlinked</span><label class="check"><input type="checkbox" id="iso"><i style="background:var(--accent)"></i>Hide papers with no link</label></div>
          <div class="fgroup"><span class="flabel">Colour by</span>
            <div class="seg" id="color" role="group" aria-label="Colour by"><button type="button" data-v="inst">Institution</button><button type="button" data-v="year">Year</button><button type="button" data-v="field">Field</button></div></div>
          <div class="fgroup"><span class="flabel">Size by</span>
            <div class="seg" id="sizeby" role="group" aria-label="Size by"><button type="button" data-v="pagerank">PageRank</button><button type="button" data-v="indeg">Cited here</button><button type="button" data-v="citations">All citations</button></div></div>
          <div class="fgroup end"><button class="btn" id="reset" type="button" hidden>Reset filters</button></div>
        </div>
      </div>
      <div class="card" style="padding: 14px 18px;">
        <h4 style="margin: 0 0 10px; font-size: 13.5px; font-weight: 600; color: var(--text);">About this network</h4>
        <div class="summary-figs" style="grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-bottom: 0;">
          <div class="d-stat"><b>${fmt(s.nodes)}</b><span>papers</span></div>
          <div class="d-stat"><b>${fmt(s.edges)}</b><span>citations between them</span></div>
          <div class="d-stat"><b>${fmt(s.papers_with_links)}</b><span>papers with at least one link</span></div>
          <div class="d-stat"><b>${fmt(s.cross_institute_edges)}</b><span>citations across institutions</span></div>
        </div>
      </div>
      <div class="net-body">
        <aside class="card net-list" aria-label="Papers in the graph">
          <div class="net-list-head"><h4 id="list-title" style="margin: 0;"></h4></div>
          <ul class="plist" id="list"></ul>
        </aside>
        <div class="card net-stage">${stageMarkup()}</div>
        <aside class="card net-detail" aria-label="Selected paper">
          <div id="summary">
            <h4 style="margin-top: 0;">In-degree distribution</h4>
            <div class="chart" id="indeg" style="height:220px"></div>
            <div class="note">Papers by how often other papers here cite them (log scale).</div>
          </div>
          <div id="detail" hidden></div>
        </aside>
      </div>
    </div>`);
  const q = (sel) => el.querySelector(sel);
  const list = q("#list");

  const view = new NetworkView(q("#sigma"), {
    directed: true,
    onSelect: (key) => showDetail(key === null ? null : Number(key)),
    onHover: (key) => markItem(list, key, "hover"),
    onStatus: (running) => { q("#status").innerHTML = running ? `<div class="spinner"></div>Arranging…` : ""; },
  });

  // ---------------------------------------------------------------- choosing the subgraph
  const bits = () => [...state.insts].reduce((m, k) => m | INST[k].bit, 0);
  const passes = (i) => (N.mask[i] & bits()) && (state.field < 0 || N.field[i] === state.field) && N.year[i] >= state.from && N.year[i] <= state.to;
  const metric = { pagerank: N.pagerank, indeg: N.indeg, citations: N.citations };

  function chooseNodes() {
    if (state.mode === "ego" && state.ego !== null) {
      const chosen = new Set([state.ego]);
      let frontier = [state.ego];
      for (let d = 0; d < state.depth; d++) {
        const next = [];
        for (const v of frontier) for (const u of [...outs[v], ...ins[v]]) if (!chosen.has(u)) { chosen.add(u); next.push(u); }
        frontier = next;
      }
      let list = [...chosen];
      if (list.length > state.size) list = [state.ego, ...list.filter((i) => i !== state.ego).sort((a, b) => N.pagerank[b] - N.pagerank[a]).slice(0, state.size - 1)];
      return list;
    }
    const pool = [];
    for (let i = 0; i < n; i++) if (passes(i)) pool.push(i);
    if (state.mode === "cross") {
      const touch = new Set();
      for (const s of pool) for (const t of outs[s]) if (passes(t) && (N.mask[s] & N.mask[t]) === 0) { touch.add(s); touch.add(t); }
      return [...touch].sort((a, b) => N.pagerank[b] - N.pagerank[a]).slice(0, state.size);
    }
    const m = state.mode === "indeg" ? N.indeg : N.pagerank;
    return pool.sort((a, b) => m[b] - m[a]).slice(0, state.size);
  }

  function colorOf(i) {
    if (state.colorBy === "field") return fieldColor(data.fields[N.field[i]]);
    if (state.colorBy === "year") return yearColor(N.year[i]);
    return maskColor(N.mask[i]);
  }

  function draw() {
    let list = chooseNodes();
    const inView = new Set(list);
    const edges = [];
    for (const s of list) for (const t of outs[s]) {
      if (!inView.has(t)) continue;
      if (state.mode === "cross" && (N.mask[s] & N.mask[t]) !== 0) continue;
      edges.push([s, t]);
    }
    if (state.hideIsolated && state.mode !== "ego") {
      const linked = new Set(edges.flat());
      list = list.filter((i) => linked.has(i));
    }
    const m = metric[state.sizeBy];
    const max = Math.max(1, ...list.map((i) => m[i]));
    const nodes = list.map((i) => ({
      key: String(i), label: N.title[i].length > 60 ? `${N.title[i].slice(0, 58)}…` : N.title[i], hoverLabel: N.title[i],
      color: colorOf(i), size: 2.2 + 13 * Math.sqrt(m[i] / max) + (i === state.ego ? 4 : 0),
    }));
    const seed = (node) => {
      const i = Number(node.key);
      const insts = maskInsts(N.mask[i]);
      const angle = { DU: 0, JNU: 2.1, UoH: 4.2 }[insts[0]] + (insts.length > 1 ? 1.05 : 0);
      return { x: Math.cos(angle) * 60, y: Math.sin(angle) * 60 };
    };
    view.setGraph(nodes, edges.map(([s, t]) => ({ source: String(s), target: String(t), size: 0.7, color: T.edge })), { seed });
    q("#badges").innerHTML = `<span class="pill">${fmt(nodes.length)} papers</span><span class="pill">${fmt(edges.length)} citations</span>`;
    drawLegend();
    drawList(list);
    showDetail(null);
    if (state.mode === "ego" && state.ego !== null) setTimeout(() => { view.select(String(state.ego)); }, 50);
  }

  function drawLegend() {
    const el = q("#legend");
    if (state.colorBy === "field") {
      el.hidden = true;
      el.innerHTML = "";
      return;
    }
    el.hidden = false;
    let items;
    if (state.colorBy === "inst") items = [...INST_KEYS.map((k) => [k, INST[k].color]), ["Shared", SHARED]].map(([l, c]) => `<span><i style="background:${c}"></i>${l}</span>`).join("");
    else if (state.colorBy === "year") items = `<span>2016 <b class="ramp"></b> 2026</span>`;
    el.innerHTML = items;
  }

  // the left pane lists what is drawn, ranked by the measure the view is built on
  function drawList(drawn) {
    const mode = MODES.find((x) => x.id === state.mode);
    const m = state.mode === "indeg" ? N.indeg : N.pagerank;
    const ranked = [...drawn].sort((a, b) => (b === state.ego) - (a === state.ego) || m[b] - m[a]);
    q("#list-title").textContent = mode.list;
    list.innerHTML = ranked.slice(0, LIST_MAX).map((i) => `
      <li data-i="${i}" tabindex="0"><div class="t">${esc(N.title[i])}</div>
        <div class="m">${chips(maskInsts(N.mask[i]))}<span class="j">${esc(data.journals[N.journal[i]] || "–")}</span><span class="y">${N.year[i]}</span></div></li>`).join("")
      || `<li class="more">No papers match these filters.</li>`;
    list.scrollTop = 0;
  }

  const paperItem = (i) => `<li data-i="${i}" tabindex="0"><span class="lbl" title="${esc(N.title[i])}">${esc(N.title[i])}</span><span class="val">${N.year[i]}</span></li>`;

  function showDetail(i) {
    markItem(list, i, "active", true);
    q("#summary").hidden = i !== null;
    q("#detail").hidden = i === null;
    if (i === null) { indegChart.resize(); return; }
    const citedBy = [...ins[i]].sort((a, b) => N.pagerank[b] - N.pagerank[a]);
    const cites = [...outs[i]].sort((a, b) => N.pagerank[b] - N.pagerank[a]);
    q("#detail").innerHTML = `
      <button class="d-back" id="back" type="button">${ICONS.back}All papers in view</button>
      <h3 class="d-title">${esc(N.title[i])}</h3>
      <div class="d-meta">${chips(maskInsts(N.mask[i]))}<span class="note">${esc(data.fields[N.field[i]])}</span></div>
      <div class="d-sub">${N.year[i]} · ${esc(data.journals[N.journal[i]] || "–")}</div>
      <div class="d-stats">
        <div class="d-stat"><b>${fmt(N.citations[i])}</b><span>citations (all OpenAlex)</span></div>
        <div class="d-stat"><b>${fmt(N.indeg[i])}</b><span>cited by papers here</span></div>
        <div class="d-stat"><b>${N.pagerank[i].toFixed(1)}×</b><span>PageRank vs average</span></div>
      </div>
      <div class="open-in">Open in ${N.doi[i] ? doiLink(N.doi[i]) : ""}<a href="https://openalex.org/${N.id[i]}" target="_blank" rel="noopener">OpenAlex ↗</a></div>
      ${state.mode === "ego" && state.ego === i ? "" : `<div class="d-actions"><button class="btn" id="go-ego" type="button">Show its neighbourhood</button></div>`}
      ${citedBy.length ? `<h4 class="mt">Cited by (${citedBy.length})</h4><ul class="list">${citedBy.slice(0, 6).map(paperItem).join("")}</ul>` : ""}
      ${cites.length ? `<h4 class="mt">Cites (${cites.length})</h4><ul class="list">${cites.slice(0, 6).map(paperItem).join("")}</ul>` : ""}`;
    q("#detail").parentElement.scrollTop = 0;
    q("#back").addEventListener("click", () => view.select(null));
    q("#go-ego")?.addEventListener("click", () => openEgo(i));
  }

  function openEgo(i) {
    state.mode = "ego";
    state.ego = i;
    q("#search").value = N.title[i];
    syncControls();
    draw();
  }

  // ---------------------------------------------------------------- controls
  // the controls always mirror state, so a reset or a jump to a neighbourhood shows up in them too
  function syncControls() {
    q("#modes").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.mode === state.mode));
    q("#depth-group").hidden = state.mode !== "ego";
    q("#insts").querySelectorAll("input").forEach((x) => { x.checked = state.insts.has(x.value); });
    q("#field").value = String(state.field);
    q("#from").value = String(state.from);
    q("#to").value = String(state.to);
    q("#size").value = state.size;
    q("#size-v").textContent = state.mode === "ego" ? `up to ${fmt(state.size)}` : fmt(state.size);
    q("#iso").checked = state.hideIsolated;
    q("#color").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.v === state.colorBy));
    q("#sizeby").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.v === state.sizeBy));
    q("#reset").hidden = state.insts.size === INST_KEYS.length && Object.entries(DEFAULTS).every(([k, v]) => state[k] === v);
  }
  syncControls();
  q("#modes").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-mode]");
    if (!b) return;
    state.mode = b.dataset.mode;
    if (state.mode === "ego" && state.ego === null) state.ego = (() => { let best = 0; for (let i = 1; i < n; i++) if (N.pagerank[i] > N.pagerank[best]) best = i; return best; })();
    syncControls();
    draw();
  });
  const redraw = () => { syncControls(); draw(); };
  q("#size").addEventListener("input", () => { state.size = Number(q("#size").value); syncControls(); });
  q("#size").addEventListener("change", redraw);
  q("#insts").addEventListener("change", () => { state.insts = new Set([...q("#insts").querySelectorAll("input:checked")].map((x) => x.value)); redraw(); });
  q("#field").addEventListener("change", () => { state.field = Number(q("#field").value); redraw(); });
  q("#from").addEventListener("change", () => { state.from = Number(q("#from").value); redraw(); });
  q("#to").addEventListener("change", () => { state.to = Number(q("#to").value); redraw(); });
  q("#iso").addEventListener("change", () => { state.hideIsolated = q("#iso").checked; redraw(); });
  const seg = (id, key) => q(id).addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    state[key] = b.dataset.v;
    redraw();
  });
  seg("#color", "colorBy");
  seg("#sizeby", "sizeBy");
  q("#depth").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    q("#depth").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    state.depth = Number(b.dataset.d);
    draw();
  });
  q("#reset").addEventListener("click", () => { Object.assign(state, DEFAULTS, { insts: new Set(INST_KEYS) }); redraw(); });
  q("#relayout").addEventListener("click", () => view.runLayout(4000));
  q("#fit").addEventListener("click", () => view.fit());

  // any listed paper (left pane or detail lists): point to light it up, click or Enter to select it
  const root = el.firstElementChild;  // this view's own root, not the shared container
  hoverFromList(root, view);
  const pick = (li) => {
    const i = Number(li.dataset.i);
    if (view.graph.hasNode(String(i))) { view.select(String(i)); view.focus(String(i)); } else openEgo(i);
  };
  root.addEventListener("click", (e) => { const li = e.target.closest("li[data-i]"); if (li) pick(li); });
  root.addEventListener("keydown", (e) => { const li = e.target.closest("li[data-i]"); if (li && e.key === "Enter") pick(li); });

  // search (titles)
  const lower = N.title.map((t) => t.toLowerCase());
  const box = q("#suggest");
  q("#search").addEventListener("input", debounce(() => {
    const term = q("#search").value.trim().toLowerCase();
    if (term.length < 3) { box.hidden = true; return; }
    const hits = [];
    for (let i = 0; i < n && hits.length < 40; i++) if (lower[i].includes(term)) hits.push(i);
    hits.sort((a, b) => N.pagerank[b] - N.pagerank[a]);
    box.innerHTML = hits.slice(0, 10).map((i) => `<div data-i="${i}">${esc(N.title[i])}<small>${N.year[i]} · ${maskInsts(N.mask[i]).join(", ")} · cited ${fmt(N.citations[i])}×</small></div>`).join("")
      || `<div class="note" style="cursor:default">No matching title</div>`;
    box.hidden = false;
  }, 150));
  box.addEventListener("click", (e) => {
    const d = e.target.closest("div[data-i]");
    if (!d) return;
    box.hidden = true;
    openEgo(Number(d.dataset.i));
  });

  // in-degree distribution (log–log)
  const indegChart = chart(q("#indeg"), {
    grid: { left: 6, right: 20, top: 10, bottom: 6, containLabel: true },
    tooltip: { trigger: "item", formatter: (p) => `${fmt(p.data[1])} papers cited ${p.data[0]}× here` },
    xAxis: { type: "log", min: 1, axisLabel: { fontSize: 10 } },
    yAxis: { type: "log", min: 1, axisLabel: { fontSize: 10 } },
    series: [{ type: "scatter", symbolSize: 6, itemStyle: { color: rgba(T.accent, 0.8) }, data: s.indeg_hist.filter(([k]) => k > 0) }],
  });

  draw();
  return { destroy: () => view.kill() };
}
