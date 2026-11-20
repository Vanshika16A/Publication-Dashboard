import { ALL_COLOR, chart, disposeCharts, esc, fieldColor, fmt, gradient, INST, INST_KEYS, load, mix, mount, onColor, pct, QUARTILE_COLORS, RANK_COLORS, scopeColor, T } from "../lib.js";

// papers grouped by number of authors; data for each group is in stats_by_authors.json, built by collector/dashboard_data.py
const AUTHOR_GROUPS = [
  { id: "all", label: "All papers", group: null },
  { id: "1-5", label: "1–5 authors", group: "1-5" },
  { id: "6-20", label: "6–20", group: "6-20" },
  { id: "21-99", label: "21–99", group: "21-99" },
  { id: "100+", label: "100+", group: "100+" },
];
const groupStats = async (g) => (g.group ? (await load("stats_by_authors"))[g.group] : load("stats"));
let authorGroup = new URLSearchParams(location.search).get("authors") || "all";

export default async function publications(el, { scope }) {
  if (!AUTHOR_GROUPS.some((g) => g.id === authorGroup)) authorGroup = "all";
  el.innerHTML = `<div class="authbar"><span class="authbar-label">Number of authors per paper</span>
      <div class="seg" id="author-group">${AUTHOR_GROUPS.map((g) => `<button data-g="${g.id}" class="${g.id === authorGroup ? "active" : ""}">${g.label}</button>`).join("")}</div>
      <span class="authbar-note" id="author-note"></span></div><div id="pub-body"></div>`;
  const body = el.querySelector("#pub-body");
  let drawId = 0;  // a click made while an earlier one is still loading wins; the older one stops
  const draw = async () => {
    const mine = ++drawId;
    disposeCharts();
    const group = AUTHOR_GROUPS.find((g) => g.id === authorGroup);
    const data = await groupStats(group);
    if (mine !== drawId) return;
    try {
      await render(body, scope, group);
    } catch (err) {
      body.innerHTML = `<div class="card"><h3>Could not draw this group</h3><p class="card-sub">${esc(err.message)}</p></div>`;
      return;
    }
    if (mine !== drawId) return;
    const n = data.trend[scope].reduce((a, v) => a + v, 0);
    const total = (await load("stats")).trend[scope].reduce((a, v) => a + v, 0);
    const who = scope === "All" ? "papers across all three institutions" : `${scope} papers`;
    el.querySelector("#author-note").textContent = `${fmt(n)} of ${fmt(total)} ${who}${n < 500 ? " · small group, so yearly figures are noisy" : ""}`;
  };
  el.querySelector("#author-group").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b || b.dataset.g === authorGroup) return;
    authorGroup = b.dataset.g;
    el.querySelectorAll("#author-group button").forEach((x) => x.classList.toggle("active", x === b));
    draw();
  });
  await draw();
}

async function render(el, scope, group) {
  const s = await groupStats(group);
  const im = group.group ? { thresholds: s.impact_q1.thresholds, q1: s.impact_q1.q1 } : await load("impact");
  const color = scopeColor(scope);
  const label = scope === "All" ? "all three institutions" : INST[scope].name;
  const $ = mount(el, `
    <div class="grid g-3">
      <div class="card span-2"><div class="card-head"><div><h3>Publication trend</h3>
        <p class="card-sub">Papers per year for ${esc(label)}${scope === "All" ? ", against each institution for comparison" : ""}. 2026 is a partial year.</p></div>
        <div class="seg" id="metric"><button data-m="papers" class="active">Papers</button><button data-m="citations">Citations</button></div></div>
        <div class="chart" id="trend"></div></div>
      <div class="card"><h3>Journal quartiles</h3><p class="card-sub">SCImago best quartile of the journal in the paper's year.</p>
        <div class="chart" id="donut"></div></div>
    </div>
    <div class="grid g-2 mt">
      <div class="card"><h3>Quartile mix by institution</h3><p class="card-sub">Share of journal papers in each quartile.</p>
        <div class="chart short" id="qmix"></div></div>
      <div class="card"><h3>Q1 share over time</h3><p class="card-sub">Q1 papers as a share of ranked journal papers, per year.</p>
        <div class="chart short" id="q1year"></div></div>
    </div>
    <div class="grid g-2 mt">
      <div class="card"><h3>Q1 papers in high-impact journals</h3>
        <p class="card-sub">${fmt(im.q1[scope].total)} Q1 journal papers of ${scope === "All" ? "the three institutions together" : esc(label)}, by the impact factor of their journal (OpenAlex 2-year mean citedness at data collection).</p>
        <div class="chart" id="q1if" style="height:340px"></div></div>
      <div class="card"><h3>Conference ranks</h3><p class="card-sub">We use CORE A* / A / B / C where available, falling back to SCImago quartile of the proceedings series. Most papers have neither, so the CORE ranked group is broken down below.</p>
        <div class="rank-chips" id="core-chips"></div>
        <div class="chart" id="core" style="height:64px;flex:0 0 auto"></div>
        <div id="core-detail"><h4 class="rank-detail-title" id="core-detail-title"></h4>
          <div class="chart" id="core-ranks" style="height:170px;flex:0 0 auto"></div></div></div>
    </div>
    <div class="grid g-2 mt">
      <div class="card"><h3>Research areas</h3><p class="card-sub">Papers by OpenAlex primary field, ${esc(label)}.</p>
        <div class="chart tall" id="fields"></div></div>
      <div class="card"><h3>Top sub-fields</h3><p class="card-sub">The ten largest OpenAlex sub-fields, ${esc(label)}.</p>
        <div class="chart tall" id="subfields"></div></div>
    </div>
`);

  const trend = chart($("#trend"), {});
  const drawTrend = (metric) => {
    const data = metric === "papers" ? s.trend : s.citations_by_year;
    const series = [{
      name: scope === "All" ? "All (unique papers)" : scope, type: "line", smooth: 0.35, symbol: "circle", symbolSize: 7, data: data[scope],
      lineStyle: { width: 3, color }, itemStyle: { color }, areaStyle: { color: gradient(color, 0.35) }, z: 3,
    }];
    if (scope === "All") {
      INST_KEYS.forEach((k) => series.push({ name: k, type: "line", smooth: 0.35, symbol: "none", data: data[k],
        lineStyle: { width: 2, color: INST[k].color, type: "dashed", opacity: 0.85 }, itemStyle: { color: INST[k].color } }));
    }
    trend.setOption({
      tooltip: { trigger: "axis" }, legend: { top: 0, right: 0 },
      xAxis: { type: "category", data: s.years, boundaryGap: false },
      yAxis: { type: "value", name: metric === "papers" ? "papers" : "citations", nameTextStyle: { color: T.muted } },
      series,
    }, true);
  };
  drawTrend("papers");
  $("#metric").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    $("#metric").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    drawTrend(b.dataset.m);
  });

  const q = s.quartiles[scope];
  const qTotal = Object.values(q).reduce((a, b) => a + b, 0);
  chart($("#donut"), {
    tooltip: { formatter: (p) => `${p.name}: <b>${fmt(p.value)}</b> (${pct(p.percent)})` },
    legend: { bottom: 0, left: "center" },
    title: { text: pct(((q.Q1) / (qTotal - q["Not ranked"])) * 100, 0), subtext: "in Q1", left: "center", top: "36%",
      textStyle: { color: T.text, fontFamily: "Atkinson Hyperlegible Next, system-ui, sans-serif", fontSize: 28, fontWeight: 600 }, subtextStyle: { color: T.muted } },
    series: [{ type: "pie", radius: ["52%", "74%"], center: ["50%", "45%"], padAngle: 1, itemStyle: { borderRadius: 2 },
      label: { show: false }, data: Object.entries(q).map(([name, value]) => ({ name, value, itemStyle: { color: QUARTILE_COLORS[name] } })) }],
  });

  const scopes = ["All", ...INST_KEYS];
  chart($("#qmix"), {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => pct(v) },
    legend: { top: 0, right: 0 },
    grid: { left: 8, right: 16, top: 34, bottom: 4, containLabel: true },
    xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
    yAxis: { type: "category", data: [...scopes].reverse(), axisLabel: { color: T.text, fontWeight: 600 } },
    series: ["Q1", "Q2", "Q3", "Q4"].map((name) => ({
      name, type: "bar", stack: "q", barWidth: 22, itemStyle: { color: QUARTILE_COLORS[name] },
      data: [...scopes].reverse().map((k) => {
        const v = s.quartiles[k];
        const ranked = v.Q1 + v.Q2 + v.Q3 + v.Q4;
        return +((v[name] / ranked) * 100).toFixed(1);
      }),
    })),
  });

  chart($("#q1year"), {
    tooltip: { trigger: "axis", valueFormatter: (v) => (v == null ? "–" : pct(v)) },
    legend: { top: 0, right: 0 },
    xAxis: { type: "category", data: s.years, boundaryGap: false },
    yAxis: { type: "value", axisLabel: { formatter: "{value}%" }, min: (v) => Math.max(0, Math.floor(v.min / 10) * 10 - 10) },
    series: scopes.map((k) => ({ name: k, type: "line", smooth: 0.3, symbol: "none", data: s.q1_share_by_year[k],
      lineStyle: { width: k === scope ? 3.5 : 2, color: k === "All" ? ALL_COLOR : INST[k].color, opacity: k === scope || scope === "All" ? 1 : 0.35 },
      itemStyle: { color: k === "All" ? ALL_COLOR : INST[k].color } })),
  });

  const fields = Object.entries(s.fields[scope]).sort((a, b) => a[1] - b[1]);
  const fieldTotal = fields.reduce((a, [, v]) => a + v, 0);
  chart($("#fields"), {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (p) => `${esc(p[0].name)}<br/><b>${fmt(p[0].value)}</b> papers (${pct((p[0].value / fieldTotal) * 100)})` },
    grid: { left: 8, right: 60, top: 6, bottom: 4, containLabel: true },
    xAxis: { type: "value", show: false },
    yAxis: { type: "category", data: fields.map(([n]) => n), axisLabel: { color: T.text2, width: 210, overflow: "truncate" } },
    series: [{ type: "bar", data: fields.map(([, v]) => v), barWidth: "62%",
      itemStyle: { borderRadius: [0, 2, 2, 0], color: (p) => fieldColor(fields[p.dataIndex][0]) },  // same colour per field as everywhere else
      label: { show: true, position: "right", color: T.muted, formatter: (p) => fmt(p.value) } }],
  });

  const c = s.conference[scope];
  // three groups: CORE ranked (A*, A, B, C together, few papers), SCImago series, not ranked; the CORE group is split below
  const coreRanks = ["A*", "A", "B", "C"];
  const coreTotal = coreRanks.reduce((sum, name) => sum + c[name], 0);
  // one institution: shades of its own colour (strongest = best rank); all three together: the shared rank colours
  const rankColor = scope === "All" ? RANK_COLORS : {
    "A*": color, A: mix(color, T.stage, 0.25), B: mix(color, T.stage, 0.5), C: mix(color, T.stage, 0.7),
    "SCImago series": mix(color, T.stage, 0.82), "Not ranked": mix(color, T.stage, 0.92) };
  const groups = [["CORE ranked", coreTotal, scope === "All" ? RANK_COLORS.A : color], ["SCImago series", c["SCImago series"], rankColor["SCImago series"]],
    ["Not ranked", c["Not ranked"], rankColor["Not ranked"]]];
  const confTotal = groups.reduce((sum, g) => sum + g[1], 0);
  $("#core-chips").innerHTML = confTotal ? groups.map(([name, , col]) => `<span class="rank-chip"><i style="background:${col}"></i>${name}</span>`).join("") : `<span class="note">No conference papers in this group.</span>`;
  chart($("#core"), {
    tooltip: { trigger: "item", formatter: (p) => `${p.seriesName}: <b>${fmt(p.value)}</b> (${confTotal ? pct((p.value / confTotal) * 100) : "–"})${p.seriesName === "CORE ranked" ? "<br/>Split by CORE rank below" : ""}` },
    grid: { left: 0, right: 0, top: 4, bottom: 4 },
    xAxis: { type: "value", show: false, max: confTotal },
    yAxis: { type: "category", data: ["Conference papers"], show: false },
    series: groups.map(([name, value, col], i) => ({ name, type: "bar", stack: "c", barWidth: 40, data: [value], 
      itemStyle: { color: col, borderColor: T.stage, borderWidth: 1 },
      label: { show: i > 0 && value / confTotal > 0.1, color: onColor(col), fontWeight: 700, formatter: () => fmt(value) } })),
  });
  $("#core-detail-title").textContent = `CORE ranked conferences · ${fmt(coreTotal)} papers`;
  chart($("#core-ranks"), {
    tooltip: { formatter: (p) => `CORE ${p.name}: <b>${fmt(p.value)}</b> papers (${coreTotal ? pct((p.value / coreTotal) * 100) : "–"} of CORE ranked)` },
    grid: { left: 8, right: 56, top: 4, bottom: 4, containLabel: true },
    xAxis: { type: "value", show: false },
    yAxis: { type: "category", data: coreRanks, inverse: true, axisLabel: { color: T.text, fontWeight: 700, fontSize: 13 } },
    series: [{ type: "bar", barWidth: "58%", data: coreRanks.map((name) => ({ value: c[name], itemStyle: { color: rankColor[name], borderRadius: [0, 3, 3, 0] } })),
      label: { show: true, position: "right", color: T.text2, fontWeight: 700, formatter: (p) => fmt(p.value) } }],
  });

  const subs = Object.entries(s.subfields[scope]).slice(0, 10).reverse();
  chart($("#subfields"), {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 8, right: 50, top: 4, bottom: 4, containLabel: true },
    xAxis: { type: "value", show: false },
    yAxis: { type: "category", data: subs.map(([n]) => n), axisLabel: { color: T.text2, width: 230, overflow: "truncate" } },
    series: [{ type: "bar", data: subs.map(([, v]) => v), barWidth: "58%", itemStyle: { color, borderRadius: [0, 2, 2, 0], opacity: 0.85 },
      label: { show: true, position: "right", color: T.muted } }],
  });

  // Q1 papers by journal impact factor band as one pie: above 10, 5 to 10, 5 or below. The labels sit in a large legend on top
  // (name and share); on "All" the pie uses the purple scale, for one institution three shades of that institution's colour.
  const [lo, hi] = im.thresholds;
  const above = (i) => im.q1[scope].rows[i].few_authors + im.q1[scope].rows[i].many_authors;
  const total = im.q1[scope].total;
  const names = [`IF > ${hi}`, `IF ${lo}–${hi}`, `IF ≤ ${lo}`];
  const counts = [above(1), above(0) - above(1), total - above(0)];
  const shades = scope === "All" ? T.ifBands : [color, mix(color, T.stage, 0.5), mix(color, T.stage, 0.82)];
  const share = (v) => (total ? pct((v / total) * 100) : "–");
  chart($("#q1if"), {
    tooltip: { formatter: (p) => `<b>${p.name}</b><br/>${fmt(p.value)} of ${fmt(total)} Q1 papers (${pct(p.percent)})` },
    legend: { top: 0, left: "center", itemGap: 28, itemWidth: 14, itemHeight: 14, selectedMode: false,
      textStyle: { fontSize: 15, fontWeight: 700, color: T.text },
      formatter: (name) => `${name}   ${share(counts[names.indexOf(name)])}` },
    series: [{ type: "pie", radius: "68%", center: ["50%", "56%"], startAngle: 90, label: { show: false }, labelLine: { show: false },
      itemStyle: { borderColor: T.stage, borderWidth: 2 }, emphasis: { scale: true, scaleSize: 5 },
      data: counts.map((value, b) => ({ name: names[b], value, itemStyle: { color: shades[b] } })) }],
  });
}

