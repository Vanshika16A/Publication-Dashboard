import { chart, esc, fmt, INST, INST_KEYS, load, mount, onColor, qBadge, QUARTILE_COLORS, T } from "../lib.js";

export default async function journals(el, { scope }) {
  const [s, o] = await Promise.all([load("stats"), load("overview")]);
  const list = s.top_journals[scope];
  // each journal carries the same numbered, quartile-coloured marker in the chart and in the table
  const qOf = (j) => j.quartile || "Not ranked";
  const marker = (j, i) => `<span class="jmark" style="background:${QUARTILE_COLORS[qOf(j)]};color:${onColor(QUARTILE_COLORS[qOf(j)])}">${i + 1}</span>`;
  const $ = mount(el, `
    <div class="grid g-3">${INST_KEYS.map((k) => `
      <div class="card inst-card" style="--c:${INST[k].color}">
        <div class="inst-name"><span class="inst-dot"></span>${esc(INST[k].name)} <span class="inst-short">${k}</span></div>
        <ul class="list static" style="margin-top:14px">${s.top_journals[k].slice(0, 5).map((j, i) => `
          <li><span class="n">${i + 1}</span><span class="lbl" title="${esc(j.name)}">${esc(j.name)}</span>
            ${qBadge(j.quartile)}<span class="val">${fmt(j.papers)}</span></li>`).join("")}
        </ul></div>`).join("")}
    </div>
    <div class="grid g-2 mt">
      <div class="card"><h3>Top 10 journals across ${scope === "All" ? "all institutions" : esc(INST[scope].name)}</h3>
        <p class="card-sub">Papers against citations per paper. The dashed line represents the average number of citations per paper.</p>
        <div class="chart tall" id="bars"></div></div>
      <div class="card"><h3>Details</h3><p class="card-sub">Papers, citations and median SCImago Journal Rank (SJR) in the papers' years.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>#</th><th>Journal</th><th>Q</th><th class="num">Papers</th><th class="num">Citations</th><th class="num">SJR</th></tr></thead>
          <tbody id="rows">${list.map((j, i) => `<tr data-i="${i}"><td class="rank">${marker(j, i)}</td><td>${esc(j.name)}</td><td>${qBadge(j.quartile)}</td>
            <td class="num">${fmt(j.papers)}</td><td class="num">${fmt(j.citations)}</td><td class="num">${j.sjr ?? "–"}</td></tr>`).join("")}</tbody>
        </table></div></div>
    </div>`);

  // volume against impact: a bar chart of paper counts repeats the table, the scatter adds citations per paper
  const base = scope === "All" ? o.totals : o.institutions[scope];
  const avg = base.citations / base.papers;
  const mid = (Math.min(...list.map((j) => j.papers)) + Math.max(...list.map((j) => j.papers))) / 2;
  const short = (name) => (name.length > 28 ? `${name.slice(0, 26)}…` : name);
  const quartiles = ["Q1", "Q2", "Q3", "Q4", "Not ranked"].filter((q) => list.some((j) => qOf(j) === q));
  const where = list.map((j) => {  // series and data index of each journal, for linking table rows to dots
    const seriesIndex = quartiles.indexOf(qOf(j));
    return { seriesIndex, dataIndex: list.filter((x) => qOf(x) === qOf(j)).indexOf(j) };
  });
  const point = (j) => [j.papers, j.citations / j.papers];
  const bars = chart($("#bars"), {
    tooltip: { formatter: (p) => {
      const j = p.data.j;
      return `<b>${p.data.rank + 1}. ${esc(j.name)}</b><br/>${fmt(j.papers)} papers · ${fmt(j.citations)} citations<br/>${(j.citations / j.papers).toFixed(1)} citations per paper<br/>Quartile ${j.quartile || "–"} · SJR ${j.sjr ?? "–"}`;
    } },
    legend: { top: 0, right: 0, data: quartiles },
    grid: { left: 8, right: 24, top: 40, bottom: 28, containLabel: true },
    xAxis: { type: "value", name: "Papers", nameLocation: "middle", nameGap: 28, splitLine: { show: false },
      min: (r) => Math.floor((r.min * 0.85) / 50) * 50, max: (r) => Math.ceil((r.max * 1.05) / 50) * 50 },
    yAxis: { type: "value", name: "Citations per paper", nameLocation: "middle", nameGap: 36, min: 0 },
    series: [
      // numbered dots, one series per quartile so the legend reads as the colour key
      ...quartiles.map((q, k) => ({
        name: q, type: "scatter", symbolSize: 24, z: 3,
        itemStyle: { color: QUARTILE_COLORS[q], borderColor: T.stage, borderWidth: 1.5 },
        emphasis: { scale: 1.35, itemStyle: { borderColor: T.text, borderWidth: 2 } },
        label: { show: true, position: "inside", color: onColor(QUARTILE_COLORS[q]), fontWeight: 700, fontSize: 12,
          formatter: (p) => String(p.data.rank + 1) },
        data: list.filter((j) => qOf(j) === q).map((j) => ({ value: point(j), j, rank: list.indexOf(j) })),
        ...(k === 0 && { markLine: { silent: true, symbol: "none", lineStyle: { color: T.muted, type: "dashed" },
          label: { formatter: `average paper · ${avg.toFixed(1)}`, color: T.muted, position: "insideEndTop" }, data: [{ yAxis: avg }] } }),
      })),
      // journal names beside the dots, kept out of the legend and the tooltip
      { name: "names", type: "scatter", symbolSize: 1, silent: true, itemStyle: { color: "transparent" }, tooltip: { show: false },
        data: list.map((j) => ({ value: point(j), label: { position: j.papers > mid ? "left" : "right" } })),
        label: { show: true, distance: 16, color: T.text2, fontSize: 12, formatter: (p) => short(list[p.dataIndex].name) },
        labelLayout: { hideOverlap: true, moveOverlap: "shiftY" } },
    ],
  });

  // hovering a row lights up its dot, hovering a dot lights up its row
  const rows = [...$("#rows").children];
  const light = (i, on) => {
    rows.forEach((r, k) => r.classList.toggle("hot", on && k === i));
    bars.dispatchAction({ type: on ? "highlight" : "downplay", ...where[i] });
  };
  $("#rows").addEventListener("mouseover", (e) => { const r = e.target.closest("tr"); if (r) light(Number(r.dataset.i), true); });
  $("#rows").addEventListener("mouseout", (e) => { const r = e.target.closest("tr"); if (r) light(Number(r.dataset.i), false); });
  bars.on("mouseover", (p) => { if (p.data?.j) rows.forEach((r, k) => r.classList.toggle("hot", k === p.data.rank)); });
  bars.on("mouseout", () => rows.forEach((r) => r.classList.remove("hot")));
}
