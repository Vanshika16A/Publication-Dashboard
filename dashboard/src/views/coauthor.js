import { hoverFromList, ICONS, markItem, NetworkView, stageMarkup } from "../graph.js";
import { chart, chips, debounce, esc, fieldColor, fmt, INST, INST_KEYS, load, mount, T, tint } from "../lib.js";

const MODES = [
  { id: "degree", title: "Most connected", text: "Authors with the most co-authors", list: "Authors with the most co-authors" },
  { id: "betweenness", title: "Bridges", text: "Authors who connect otherwise separate groups (betweenness)", list: "Top bridges (betweenness)" },
  { id: "community", title: "Community", text: "One Louvain collaboration cluster", list: "Community members" },
  { id: "cross", title: "Across institutions", text: "Only collaborations between different assigned institutions", list: "Authors with cross-institution links" },
  { id: "ego", title: "Neighbourhood", text: "One author and their co-authors", list: "Author neighbourhood" },
];
const LIST_MAX = 300;  // longer lists stay in the graph only
const DEFAULTS = { size: 800, colorBy: "inst", sizeBy: "degree" };

export default async function coauthor(el) {
  el.innerHTML = `<div class="loading"><div class="spinner"></div>Loading the co-authorship network…</div>`;
  const data = await load("coauthor");
  const N = data.nodes;
  const n = N.id.length;
  const adj = Array.from({ length: n }, () => []);
  const flat = data.edges;
  for (let i = 0; i < flat.length; i += 3) { adj[flat[i]].push([flat[i + 1], flat[i + 2]]); adj[flat[i + 1]].push([flat[i], flat[i + 2]]); }
  const instKey = (i) => INST_KEYS[N.inst[i]];
  const communities = data.communities;
  const other = T.stone;
  // a community takes the colour of its main research area, the same colour that field has on every other page
  const commField = new Map(communities.map((c) => [c.id, c.field]));
  const commColor = (c) => (commField.has(c) ? fieldColor(commField.get(c)) : other);
  const s = data.summary;

  const state = { mode: "degree", ...DEFAULTS, insts: new Set(INST_KEYS), community: 0, ego: null, depth: 1 };

  mount(el, `
    <div class="net">
      <div class="card net-bar">
        <div class="net-bar-top">
          <div class="seg modes" id="modes" role="group" aria-label="View">${MODES.map((m) => `<button type="button" data-mode="${m.id}" title="${m.text}">${m.title}</button>`).join("")}</div>
          <div class="suggest net-search"><input class="input search" id="search" placeholder="Find an author…" aria-label="Find an author" autocomplete="off" /><div class="suggest-box" id="suggest" hidden></div></div>
        </div>
        <div class="filter-row" role="group" aria-label="Filters and style">
          <div class="fgroup" id="comm-group" hidden><label class="flabel" for="comm">Community</label>
            <select class="select" id="comm">${communities.map((c) => `<option value="${c.id}">#${c.id + 1} · ${fmt(c.size)} authors · ${esc(c.field)}</option>`).join("")}</select></div>
          <div class="fgroup" id="depth-group" hidden><span class="flabel">Depth</span>
            <div class="seg" id="depth" role="group" aria-label="Depth"><button type="button" data-d="1" class="active">Co-authors</button><button type="button" data-d="2">+ their co-authors</button></div></div>
          <div class="fgroup"><span class="flabel">Main institution</span>
            <div class="checks" id="insts">${INST_KEYS.map((k) => `<label class="check"><input type="checkbox" value="${k}" checked><i style="background:${INST[k].color}"></i>${k}</label>`).join("")}</div></div>
          <div class="fgroup"><label class="flabel" for="size">Authors shown <output id="size-v"></output></label><input type="range" id="size" min="100" max="3000" step="100" /></div>
          <div class="fgroup"><span class="flabel">Colour by</span>
            <div class="seg" id="color" role="group" aria-label="Colour by"><button type="button" data-v="inst">Institution</button><button type="button" data-v="community">Community</button></div></div>
          <div class="fgroup"><span class="flabel">Size by</span>
            <div class="seg" id="sizeby" role="group" aria-label="Size by"><button type="button" data-v="degree">Co-authors</button><button type="button" data-v="betweenness">Bridge score</button><button type="button" data-v="strength">Strength</button></div></div>
          <div class="fgroup end"><button class="btn" id="reset" type="button" hidden>Reset filters</button></div>
        </div>
      </div>
      <div class="card" style="padding: 14px 18px;">
        <h4 style="margin: 0 0 10px; font-size: 13.5px; font-weight: 600; color: var(--text);">About this network</h4>
        <div class="summary-figs" style="grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-bottom: 10px;">
          <div class="d-stat"><b>${fmt(n)}</b><span>authors</span></div>
          <div class="d-stat"><b>${fmt(s.edges)}</b><span>co-author pairs</span></div>
          <div class="d-stat"><b>${fmt(s.cross_institution_pairs)}</b><span>pairs across institutions</span></div>
          <div class="d-stat"><b>${fmt(s.largest_component)}</b><span>authors in the largest connected group</span></div>
        </div>
        <p class="note" style="margin: 0; line-height: 1.5;">Papers with 100+ authors are left out. Edge thickness corresponds to papers written together. Pick an author in the list or the graph to see their co-authors and network position.</p>
      </div>
      <div class="net-body">
        <aside class="card net-list" aria-label="Authors in the graph">
          <div class="net-list-head"><h4 id="list-title" style="margin: 0;"></h4></div>
          <ul class="plist" id="list"></ul>
        </aside>
        <div class="card net-stage">${stageMarkup()}</div>
        <aside class="card net-detail" aria-label="Selected author">
          <div id="summary">
            <h4 style="margin-top: 0;">Largest communities</h4>
            <div class="chart" id="comms" style="height:220px"></div>
            <div class="note">${fmt(s.communities)} communities.<br>Click a bar to show that community.</div>
          </div>
          <div id="detail" hidden></div>
        </aside>
      </div>
    </div>`);
  const q = (sel) => el.querySelector(sel);
  const list = q("#list");
  const view = new NetworkView(q("#sigma"), {
    onSelect: (key) => showDetail(key === null ? null : Number(key)),
    onHover: (key) => markItem(list, key, "hover"),
    onStatus: (running) => { q("#status").innerHTML = running ? `<div class="spinner"></div>Arranging…` : ""; },
  });

  const allowed = (i) => state.insts.has(instKey(i));
  const metric = { degree: N.degree, betweenness: N.betweenness, strength: N.strength };

  function chooseNodes() {
    if (state.mode === "ego" && state.ego !== null) {
      const chosen = new Set([state.ego]);
      let frontier = [state.ego];
      for (let d = 0; d < state.depth; d++) {
        const next = [];
        for (const v of frontier) for (const [u] of adj[v]) if (!chosen.has(u)) { chosen.add(u); next.push(u); }
        frontier = next;
      }
      let list = [...chosen];
      if (list.length > state.size) list = [state.ego, ...list.filter((i) => i !== state.ego).sort((a, b) => N.degree[b] - N.degree[a]).slice(0, state.size - 1)];
      return list;
    }
    const pool = [];
    for (let i = 0; i < n; i++) {
      if (!allowed(i)) continue;
      if (state.mode === "community" && N.community[i] !== state.community) continue;
      if (state.mode === "cross" && !adj[i].some(([u]) => N.inst[u] !== N.inst[i])) continue;
      pool.push(i);
    }
    const m = state.mode === "betweenness" ? N.betweenness : N.degree;
    return pool.sort((a, b) => m[b] - m[a]).slice(0, state.size);
  }

  function colorOf(i) { return state.colorBy === "community" ? commColor(N.community[i]) : INST[instKey(i)].color; }

  function draw() {
    let list = chooseNodes();
    const inView = new Set(list);
    const edges = [];
    for (const s of list) for (const [t, papers] of adj[s]) {
      if (t <= s || !inView.has(t)) continue;
      if (state.mode === "cross" && N.inst[s] === N.inst[t]) continue;
      edges.push([s, t, papers]);
    }
    if (state.mode !== "ego") { const linked = new Set(edges.flatMap(([a, b]) => [a, b])); list = list.filter((i) => linked.has(i)); }
    const m = metric[state.sizeBy];
    const max = Math.max(1e-9, ...list.map((i) => m[i]));
    const nodes = list.map((i) => ({ key: String(i), label: N.name[i], color: colorOf(i),
      size: 2.5 + 13 * Math.sqrt(m[i] / max) + (i === state.ego ? 4 : 0) }));
    const seed = (node) => {
      const i = Number(node.key);
      const angle = state.colorBy === "community" ? (N.community[i] % 12) * 0.52 : N.inst[i] * 2.1;
      return { x: Math.cos(angle) * 60, y: Math.sin(angle) * 60 };
    };
    const cross = tint(T.shared, 0.45);
    view.setGraph(nodes, edges.map(([s, t, papers]) => ({ source: String(s), target: String(t), weight: papers,
      size: Math.min(4, 0.5 + Math.log2(papers) * 0.7), color: N.inst[s] !== N.inst[t] ? cross : T.edge })), { seed });
    q("#badges").innerHTML = `<span class="pill">${fmt(nodes.length)} authors</span><span class="pill">${fmt(edges.length)} co-author links</span>`;
    drawLegend();
    drawList(list);
    showDetail(null);
    if (state.mode === "ego" && state.ego !== null) setTimeout(() => view.select(String(state.ego)), 50);
  }

  function drawLegend() {
    const items = state.colorBy === "inst" ? INST_KEYS.map((k) => [k, INST[k].color])
      : [...[...new Set(communities.map((c) => c.field))].map((f) => [f, fieldColor(f)]), [`Communities below ${fmt(communities.at(-1).size)} authors`, other]];
    q("#legend").innerHTML = items.map(([l, c]) => `<span><i style="background:${c}"></i>${esc(l)}</span>`).join("")
      + (state.colorBy === "inst" ? `<span><i style="background:${T.shared};border-radius:2px;height:3px"></i>cross-institution link</span>` : "");
  }

  // the left pane lists what is drawn, ranked by the measure the view is built on
  function drawList(drawn) {
    const mode = MODES.find((x) => x.id === state.mode);
    const key = state.mode === "betweenness" ? "betweenness" : "degree";
    const ranked = [...drawn].sort((a, b) => (b === state.ego) - (a === state.ego) || N[key][b] - N[key][a]);
    q("#list-title").textContent = state.mode === "community" ? `Community #${state.community + 1}` : mode.list;
    list.innerHTML = ranked.slice(0, LIST_MAX).map((i) => `
      <li data-i="${i}" tabindex="0"><div class="t">${esc(N.name[i])}</div>
        <div class="m">${chips([instKey(i)])}<span class="j">${fmt(N.degree[i])} co-authors · community #${N.community[i] + 1}</span>
        ${key === "betweenness" ? `<span class="y">${N.betweenness[i].toFixed(2)}</span>` : ""}</div></li>`).join("")
      || `<li class="more">No authors match these filters.</li>`;
    list.scrollTop = 0;
  }

  let authorInfo = null;
  load("authors").then((a) => {
    const c = Object.fromEntries(a.columns.map((name, i) => [name, i]));
    authorInfo = new Map();
    for (const r of a.rows) {
      const key = r[c.id];
      if (!key) continue;
      const prev = authorInfo.get(key);
      if (!prev || r[c.papers] > prev.papers) authorInfo.set(key, { papers: r[c.papers], citations: r[c.citations], h: r[c.h], journal: r[c.top_journal], field: r[c.field] });
    }
  }).catch(() => {});

  function showDetail(i) {
    markItem(list, i, "active", true);
    q("#summary").hidden = i !== null;
    q("#detail").hidden = i === null;
    if (i === null) { comms.resize(); return; }
    const info = authorInfo?.get(N.id[i]);
    const comm = communities.find((c) => c.id === N.community[i]);
    const co = [...adj[i]].sort((a, b) => b[1] - a[1]);
    q("#detail").innerHTML = `
      <button class="d-back" id="back" type="button">${ICONS.back}All authors in view</button>
      <h3 class="d-title">${esc(N.name[i])}</h3>
      <div class="d-meta">${chips(INST_KEYS.filter((k) => N.mask[i] & INST[k].bit))}${info ? `<span class="note">${esc(info.field)}</span>` : ""}</div>
      <div class="d-stats">
        <div class="d-stat"><b>${fmt(N.degree[i])}</b><span>co-authors</span></div>
        <div class="d-stat"><b>${info ? fmt(info.papers) : "–"}</b><span>papers in dataset</span></div>
        <div class="d-stat"><b>${info?.h ?? "–"}</b><span>h-index (all-time)</span></div>
      </div>
      <dl class="kv">
        <dt>Bridge score (betweenness ×1000)</dt><dd>${N.betweenness[i].toFixed(2)}</dd>
        <dt>Strength (weighted)</dt><dd>${N.strength[i].toFixed(1)}</dd>
        <dt>Community</dt><dd>#${N.community[i] + 1}${comm ? ` · ${fmt(comm.size)} authors` : ""}</dd>
        ${info ? `<dt>Citations</dt><dd>${fmt(info.citations)}</dd>` : ""}
      </dl>
      ${N.id[i].startsWith("A") ? `<div class="open-in">Open in <a href="https://openalex.org/${N.id[i]}" target="_blank" rel="noopener">OpenAlex ↗</a></div>` : ""}
      <div class="d-actions">
        ${state.mode === "ego" && state.ego === i ? "" : `<button class="btn" id="go-ego" type="button">Show their network</button>`}
        ${comm && !(state.mode === "community" && state.community === comm.id) ? `<button class="btn" id="go-comm" type="button">Show community #${comm.id + 1}</button>` : ""}</div>
      <h4 class="mt">Most frequent co-authors</h4>
      <ul class="list">${co.slice(0, 8).map(([u, p]) => `<li data-i="${u}" tabindex="0"><span class="lbl">${esc(N.name[u])} ${chips([instKey(u)])}</span><span class="val">${p} paper${p > 1 ? "s" : ""}</span></li>`).join("")}</ul>`;
    q("#detail").parentElement.scrollTop = 0;
    q("#back").addEventListener("click", () => view.select(null));
    q("#go-ego")?.addEventListener("click", () => openEgo(i));
    q("#go-comm")?.addEventListener("click", () => openCommunity(N.community[i]));
  }

  function openEgo(i) { state.mode = "ego"; state.ego = i; q("#search").value = N.name[i]; syncControls(); draw(); }
  function openCommunity(c) { state.mode = "community"; state.community = c; q("#comm").value = String(c); syncControls(); draw(); }

  // the controls always mirror state, so a reset or a jump to a community shows up in them too
  function syncControls() {
    q("#modes").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.mode === state.mode));
    q("#depth-group").hidden = state.mode !== "ego";
    q("#comm-group").hidden = state.mode !== "community";
    q("#comm").value = String(state.community);
    q("#insts").querySelectorAll("input").forEach((x) => { x.checked = state.insts.has(x.value); });
    q("#size").value = state.size;
    q("#size-v").textContent = state.mode === "ego" || state.mode === "community" ? `up to ${fmt(state.size)}` : fmt(state.size);
    q("#color").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.v === state.colorBy));
    q("#sizeby").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.v === state.sizeBy));
    q("#reset").hidden = state.insts.size === INST_KEYS.length && Object.entries(DEFAULTS).every(([k, v]) => state[k] === v);
  }
  syncControls();
  q("#modes").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-mode]");
    if (!b) return;
    state.mode = b.dataset.mode;
    if (state.mode === "ego" && state.ego === null) state.ego = N.degree.indexOf(Math.max(...N.degree));
    syncControls();
    draw();
  });
  q("#comm").addEventListener("change", () => { state.community = Number(q("#comm").value); draw(); });
  q("#size").addEventListener("input", () => { state.size = Number(q("#size").value); syncControls(); });
  q("#size").addEventListener("change", () => { syncControls(); draw(); });
  q("#insts").addEventListener("change", () => { state.insts = new Set([...q("#insts").querySelectorAll("input:checked")].map((x) => x.value)); syncControls(); draw(); });
  const seg = (id, key) => q(id).addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    state[key] = b.dataset.v;
    syncControls();
    draw();
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
  q("#reset").addEventListener("click", () => { Object.assign(state, DEFAULTS, { insts: new Set(INST_KEYS) }); syncControls(); draw(); });
  q("#relayout").addEventListener("click", () => view.runLayout(4000));
  q("#fit").addEventListener("click", () => view.fit());

  // any listed author (left pane or co-author list): point to light it up, click or Enter to select it
  const root = el.firstElementChild;  // this view's own root, not the shared container
  hoverFromList(root, view);
  const pick = (li) => {
    const i = Number(li.dataset.i);
    if (view.graph.hasNode(String(i))) { view.select(String(i)); view.focus(String(i)); } else openEgo(i);
  };
  root.addEventListener("click", (e) => { const li = e.target.closest("li[data-i]"); if (li) pick(li); });
  root.addEventListener("keydown", (e) => { const li = e.target.closest("li[data-i]"); if (li && e.key === "Enter") pick(li); });

  const lower = N.name.map((t) => t.toLowerCase());
  const box = q("#suggest");
  q("#search").addEventListener("input", debounce(() => {
    const term = q("#search").value.trim().toLowerCase();
    if (term.length < 2) { box.hidden = true; return; }
    const hits = [];
    for (let i = 0; i < n && hits.length < 60; i++) if (lower[i].includes(term)) hits.push(i);
    hits.sort((a, b) => N.degree[b] - N.degree[a]);
    box.innerHTML = hits.slice(0, 10).map((i) => `<div data-i="${i}">${esc(N.name[i])}<small>${instKey(i)} · ${fmt(N.degree[i])} co-authors · community #${N.community[i] + 1}</small></div>`).join("")
      || `<div class="note" style="cursor:default">No matching author</div>`;
    box.hidden = false;
  }, 150));
  box.addEventListener("click", (e) => {
    const d = e.target.closest("div[data-i]");
    if (!d) return;
    box.hidden = true;
    openEgo(Number(d.dataset.i));
  });

  const top = communities.slice(0, 10).reverse();
  const comms = chart(q("#comms"), {
    grid: { left: 6, right: 34, top: 4, bottom: 4, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: T.hover } }, formatter: (p) => {
      const c = top[p[0].dataIndex];
      return `<b>Community #${c.id + 1}</b> · ${fmt(c.size)} authors<br/>${esc(c.field)}<br/>${Object.entries(c.insts).map(([k, v]) => `${k} ${fmt(v)}`).join(" · ")}<br/><span style="color:${T.muted}">${esc(c.top.slice(0, 3).join(", "))}</span>`;
    } },
    xAxis: { type: "value", show: false },
    yAxis: { type: "category", data: top.map((c) => `#${c.id + 1} ${c.field.split(" and ")[0].split(",")[0]}`), axisLabel: { fontSize: 11, color: T.text2, width: 130, overflow: "truncate" } },
    series: [{ type: "bar", barWidth: "62%", data: top.map((c) => ({ value: c.size, itemStyle: { color: commColor(c.id), borderRadius: [0, 2, 2, 0] } })),
      label: { show: true, position: "right", color: T.muted, fontSize: 10.5 } }],
  });
  comms.on("click", (p) => openCommunity(top[p.dataIndex].id));

  draw();
  return { destroy: () => view.kill() };
}
