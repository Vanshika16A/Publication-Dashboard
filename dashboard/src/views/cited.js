import { chart, chips, doiLink, esc, fmt, INST, load, mount, scopeColor, T } from "../lib.js";

export default async function cited(el, { scope }) {
  const s = await load("stats");
  const all = s.most_cited[scope];
  let shown = 10;
  const $ = mount(el, `
    <div class="card"><h3>Citations of the top 10</h3><p class="card-sub">Hover a dot to see the paper. Numbers match the table below.</p>
      <div class="chart short" id="bars"></div></div>
    <div class="card mt"><div class="card-head"><div><h3>Most-cited papers · ${scope === "All" ? "all institutions" : esc(INST[scope].name)}</h3>
      <p class="card-sub">Citation counts from OpenAlex on the collection date. Very large collaborations (100+ authors) are marked.</p></div>
      <div class="seg" id="count"><button data-n="10" class="active">Top 10</button><button data-n="25">Top 25</button></div></div>
      <div id="table"></div></div>`);

  const draw = () => {
    $("#table").innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Paper</th><th>Year</th><th class="num">Citations</th><th></th></tr></thead>
      <tbody>${all.slice(0, shown).map((p, i) => `<tr>
        <td class="rank">${i + 1}</td>
        <td class="title-cell"><div class="t">${esc(p.title)}</div>
          <div class="s">${chips(p.insts)} ${esc(p.journal || "–")} · ${esc(p.field)}${p.n_authors >= 100 ? ` · <span style="color:var(--shared)">${fmt(p.n_authors)} authors</span>` : ""}</div></td>
        <td>${p.year}</td><td class="num"><b>${fmt(p.citations)}</b></td><td>${doiLink(p.doi)}</td></tr>`).join("")}</tbody></table></div>`;
  };
  draw();
  $("#count").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    shown = Number(b.dataset.n);
    $("#count").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    draw();
  });

  const top = all.slice(0, 10);
  chart($("#bars"), {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: T.hover } }, formatter: (p) => {
      const x = top[p[0].dataIndex];
      return `<div style="max-width:340px;white-space:normal"><b>${esc(x.title)}</b><br/>${esc(x.journal)} · ${x.year}<br/>${fmt(x.citations)} citations</div>`;
    } },
    grid: { left: 4, right: 8, top: 24, bottom: 4, containLabel: true },
    xAxis: { type: "category", data: top.map((_, i) => `#${i + 1}`) },
    yAxis: { type: "value", splitNumber: 3 },
    // lollipops: a thin stem and a dot carry the same value as a bar with far less ink
    series: [
      { type: "bar", barWidth: 3, data: top.map((x) => x.citations), itemStyle: { color: scopeColor(scope), opacity: 0.45, borderRadius: 2 }, tooltip: { show: false } },
      { type: "scatter", symbolSize: 16, data: top.map((x) => x.citations), itemStyle: { color: scopeColor(scope), borderColor: T.stage, borderWidth: 3 },
        label: { show: true, position: "top", distance: 8, color: T.text2, fontWeight: 700, formatter: (p) => fmt(p.value) } },
    ],
  });
}
