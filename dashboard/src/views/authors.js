import { chart, chips, dataTable, debounce, doiLink, esc, fmt, INST, INST_KEYS, load, mount, qBadge, rgba, scopeColor, T } from "../lib.js";

const BINS = [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4], [5, 5], [6, 7], [8, 9], [10, 14], [15, 19], [20, 29], [30, 39], [40, 59], [60, 1e9]];
const binLabel = ([a, b]) => (a === b ? `${a}` : b > 1e6 ? `${a}+` : `${a}–${b}`);

export default async function authors(el, { scope }) {
  const [data, im] = await Promise.all([load("authors"), load("impact")]);
  const col = Object.fromEntries(data.columns.map((c, i) => [c, i]));
  const rows = data.rows.map((r) => ({
    name: r[col.name], inst: r[col.inst], papers: r[col.papers], citations: r[col.citations], h: r[col.h], i10: r[col.i10],
    works: r[col.works], journal: r[col.top_journal], field: r[col.field], degree: r[col.degree], betweenness: r[col.betweenness],
    orcid: r[col.orcid], id: r[col.id],
    // older authors.json files do not have these columns: treat as missing
    journalPapers: col.top_journal_papers === undefined ? null : r[col.top_journal_papers],
    best: col.best_journal === undefined ? "" : r[col.best_journal],
    bestIf: col.best_journal_if === undefined ? null : r[col.best_journal_if],
  }));
  const journalCell = (name, sub) => name
    ? `<span class="note" style="margin:0">${esc(name)}</span>${sub ? `<div class="note" style="margin:0;font-size:11px;opacity:.75">${sub}</div>` : ""}`
    : `<span class="note" style="margin:0">–</span>`;
  // All = one row per person: an author at several institutions keeps the row with the most papers
  const best = new Map();
  for (const r of rows) {
    const k = r.id || r.name;
    if (!best.has(k) || r.papers > best.get(k).papers) best.set(k, r);
  }
  const inScope = scope === "All" ? rows.filter((r) => best.get(r.id || r.name) === r) : rows.filter((r) => r.inst === scope);
  const withH = inScope.filter((r) => r.h !== null);
  const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : null; };
  const active = inScope.filter((r) => r.papers >= 5);
  // faculty with more than im.faculty_min_journal_papers journal papers get a top 10 by journal impact factor
  const topKey = (r) => `${r.inst}|${r.id || r.name}`;
  const pcol = Object.fromEntries(im.papers.columns.map((c, i) => [c, i]));
  const paper = (i) => Object.fromEntries(im.papers.columns.map((c) => [c, im.papers.rows[i][pcol[c]]]));
  const eligible = inScope.filter((r) => im.faculty[topKey(r)]);
  let selected = eligible[0] || null;

  const $ = mount(el, `
    <div class="grid g-4">
      <div class="card kpi"><div class="kpi-label">Faculty</div><div class="kpi-value">${fmt(active.length)}</div><div class="kpi-note">authors with 5+ papers</div></div>
      <div class="card kpi"><div class="kpi-label">Median h-index</div><div class="kpi-value">${median(active.filter((r) => r.h !== null).map((r) => r.h)) ?? "–"}</div><div class="kpi-note">considering authors with 5+ papers</div></div>
      <div class="card kpi"><div class="kpi-label">Total affiliated authors</div><div class="kpi-value">${fmt(inScope.length)}</div><div class="kpi-note">at least one paper in the dataset</div></div>
      <div class="card kpi"><div class="kpi-label">Authors with an ORCID</div><div class="kpi-value">${Math.round((inScope.filter((r) => r.orcid).length / inScope.length) * 100)}%</div></div>
    </div>
    <div class="grid g-2 mt">
      <div class="card"><h3>h-index distribution</h3><p class="card-sub">All-time h-index of authors with 5+ papers in the dataset.</p>
        <div class="chart" id="hist"></div></div>
      <div class="card"><h3>Output vs. impact</h3><p class="card-sub">Papers in the dataset against all-time h-index for authors with 5+ papers.</p>
        <div class="chart" id="scatter"></div></div>
    </div>
    <div class="card mt"><div class="card-head"><div><h3>All authors</h3>
      <p class="card-sub">Presented as a sortable table. Note that bridge score (betweenness × 1000) is calculated from the co-authorship network.
        <b>Most published in</b> is the journal with the most of the author's papers in the dataset; <b>Best journal</b> is the journal
        with the highest impact factor (OpenAlex 2-year mean citedness) the author has published in.</p></div></div>
      <div class="toolbar">
        <input class="input search" id="q" placeholder="Search author, journal or field" />
        <span class="note" style="margin:0">Minimum papers</span>
        <div class="seg" id="min">${[1, 3, 5, 10].map((n) => `<button data-n="${n}" class="${n === 3 ? "active" : ""}">${n}+</button>`).join("")}</div>
      </div>
      <div id="table"></div></div>
    <div class="card mt" id="top-card"><div class="card-head"><div><h3>Top 10 publications by journal impact factor</h3>
      <p class="card-sub">For authors with more than ${im.faculty_min_journal_papers} journal papers (${fmt(eligible.length)} here). Search a name, or click <b>Top 10</b> in the table above.
        Impact factor is the OpenAlex 2-year mean citedness of the journal at data collection; ties are broken by citations.</p></div>
      <div class="top-search"><input class="input search" id="top-q" placeholder="Search faculty" autocomplete="off" />
        <ul class="list top-results" id="top-results" hidden></ul></div></div>
      <div id="top-who"></div><div id="top"></div></div>`);

  const histScopes = scope === "All" ? INST_KEYS : [scope];
  chart($("#hist"), {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { top: 0, right: 0 },
    xAxis: { type: "category", data: BINS.map(binLabel), name: "h-index", nameLocation: "middle", nameGap: 28, nameTextStyle: { color: T.muted } },
    yAxis: { type: "value", name: "authors", nameTextStyle: { color: T.muted } },
    grid: { left: 12, right: 18, top: 36, bottom: 30, containLabel: true },
    series: histScopes.map((k) => ({
      name: k, type: "bar", barGap: "8%",
      itemStyle: { color: INST[k].color, borderRadius: [2, 2, 0, 0] },
      data: BINS.map(([a, b]) => rows.filter((r) => r.inst === k && r.papers >= 5 && r.h !== null && r.h >= a && r.h <= b).length),
    })),
  });

  const sample = active.filter((r) => r.h !== null).slice(0, 4000);
  chart($("#scatter"), {
    tooltip: { formatter: (p) => `<b>${esc(p.data[2])}</b> (${p.data[3]})<br/>${p.data[0]} papers · h-index ${p.data[1]}` },
    legend: { top: 0, right: 0 },
    grid: { left: 12, right: 18, top: 36, bottom: 30, containLabel: true },
    xAxis: { type: "log", name: "papers in dataset", nameLocation: "middle", nameGap: 28, nameTextStyle: { color: T.muted }, min: 5 },
    yAxis: { type: "value", name: "h-index", nameTextStyle: { color: T.muted } },
    series: (scope === "All" ? INST_KEYS : [scope]).map((k) => ({
      name: k, type: "scatter", symbolSize: 6, large: true,
      itemStyle: { color: rgba(INST[k].color, 0.55), borderColor: INST[k].color, borderWidth: 0.6 },
      data: sample.filter((r) => r.inst === k).map((r) => [r.papers, r.h, r.name, r.inst]),
    })),
  });

  let minPapers = 3;
  const filtered = () => inScope.filter((r) => r.papers >= minPapers);
  const table = dataTable($("#table"), {
    rows: filtered(), pageSize: 20, sortKey: "papers",
    search: (r) => `${r.name} ${r.journal} ${r.best} ${r.field}`,
    columns: [
      { key: "rank", label: "#", sortable: false, render: (r, i) => `<span class="rank">${i + 1}</span>` },
      { key: "name", label: "Author", render: (r) => `<b>${esc(r.name)}</b>${r.orcid ? ` <a href="https://orcid.org/${esc(r.orcid)}" target="_blank" rel="noopener" title="ORCID" style="font-size:11px">iD</a>` : ""}${
        im.faculty[topKey(r)] ? `<button class="top-btn${r === selected ? " active" : ""}" data-top="${esc(topKey(r))}" title="Top 10 publications by journal impact factor">Top 10</button>` : ""}` },
      { key: "inst", label: "Inst.", render: (r) => chips([r.inst]) },
      { key: "papers", label: "Papers", num: true, render: (r) => fmt(r.papers) },
      { key: "citations", label: "Citations", num: true, render: (r) => fmt(r.citations) },
      { key: "h", label: "h-index", num: true, render: (r) => (r.h ?? "–") },
      { key: "i10", label: "i10", num: true, render: (r) => (r.i10 ?? "–") },
      { key: "degree", label: "Co-authors", num: true, render: (r) => fmt(r.degree) },
      { key: "betweenness", label: "Bridge score", num: true, render: (r) => (r.betweenness ? r.betweenness.toFixed(2) : "–") },
      { key: "journal", label: "Most published in", sortValue: (r) => r.journalPapers,
        render: (r) => journalCell(r.journal, r.journalPapers ? `${fmt(r.journalPapers)} paper${r.journalPapers === 1 ? "" : "s"}` : "") },
      { key: "best", label: "Best journal (highest IF)", sortValue: (r) => r.bestIf,
        render: (r) => journalCell(r.best, r.bestIf !== null ? `IF ${r.bestIf.toFixed(2)}` : "") },
      { key: "field", label: "Main field", render: (r) => `<span class="note" style="margin:0">${esc(r.field)}</span>` },
    ],
  });
  $("#q").addEventListener("input", debounce((e) => table.setQuery(e.target.value.trim()), 180));
  $("#min").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    minPapers = Number(b.dataset.n);
    $("#min").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    table.setRows(filtered());
  });

  const drawTop = () => {
    if (!selected) {
      $("#top-who").innerHTML = "";
      $("#top").innerHTML = `<p class="note">No author in this scope has more than ${im.faculty_min_journal_papers} journal papers.</p>`;
      return;
    }
    const top = im.faculty[topKey(selected)].map(paper);
    $("#top-who").innerHTML = `<div class="top-who" style="--c:${scopeColor(selected.inst)}">
      <div class="who-name">${esc(selected.name)}</div>
      <div class="fac-head">${chips([selected.inst])}<span>${esc(INST[selected.inst].name)}</span><span><b>${fmt(selected.papers)}</b> papers</span>
        <span><b>${fmt(selected.citations)}</b> citations</span><span>h-index <b>${selected.h ?? "–"}</b></span>
        ${selected.field ? `<span>${esc(selected.field)}</span>` : ""}</div></div>`;
    $("#top").innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Paper</th><th>Q</th><th class="num">Impact factor</th><th class="num">Authors</th><th class="num">Citations</th><th></th></tr></thead>
      <tbody>${top.map((p, i) => `<tr><td class="rank">${i + 1}</td>
        <td class="title-cell"><div class="t">${esc(p.title)}</div><div class="s">${esc(p.journal)} · ${p.year}</div></td>
        <td>${qBadge(p.quartile)}</td><td class="num if-val" style="color:${scopeColor(selected.inst)}">${p.if.toFixed(2)}</td>
        <td class="num">${fmt(p.n_authors)}</td><td class="num">${fmt(p.citations)}</td><td>${doiLink(p.doi)}</td></tr>`).join("")}</tbody></table></div>`;
  };
  drawTop();
  const choose = (key, scroll) => {
    selected = eligible.find((r) => topKey(r) === key) || selected;
    $("#table").querySelectorAll("button[data-top]").forEach((x) => x.classList.toggle("active", x.dataset.top === key));
    drawTop();
    if (scroll) $("#top-card").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  $("#table").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-top]");
    if (b) choose(b.dataset.top, true);
  });

  // search box for the top 10: matching faculty in a dropdown, Enter picks the first
  const results = $("#top-results");
  let hits = [];
  const showHits = () => {
    const q = $("#top-q").value.trim().toLowerCase();
    hits = q ? eligible.filter((r) => r.name.toLowerCase().includes(q)).slice(0, 8) : [];
    results.hidden = !q;
    results.innerHTML = hits.length ? hits.map((r) => `<li data-key="${esc(topKey(r))}"><span class="lbl">${esc(r.name)}</span>${chips([r.inst])}
        <span class="val">${fmt(r.papers)}</span></li>`).join("") : `<li class="note">No faculty match</li>`;
  };
  const pick = (key) => { $("#top-q").value = ""; results.hidden = true; choose(key, false); };
  $("#top-q").addEventListener("input", showHits);
  $("#top-q").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && hits[0]) pick(topKey(hits[0]));
    if (e.key === "Escape") { $("#top-q").value = ""; results.hidden = true; }
  });
  $("#top-q").addEventListener("blur", () => setTimeout(() => { results.hidden = true; }, 150));
  results.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li[data-key]");
    if (li) { e.preventDefault(); pick(li.dataset.key); }
  });
}
