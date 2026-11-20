import { chart, esc, fmt, gradient, INST, INST_KEYS, load, mount, onColor, pct, rampColor, T } from "../lib.js";

export default async function connections(el) {
  const [c, o] = await Promise.all([load("connections"), load("overview")]);
  let inst = "DU";
  const $ = mount(el, `
    <div class="grid g-3">${INST_KEYS.map((k) => {
      const v = c.institutions[k];
      return `<div class="card inst-card" style="--c:${INST[k].color}">
        <div class="inst-name"><span class="inst-dot"></span>${esc(INST[k].name)} <span class="inst-short">${k}</span></div>
        <div class="inst-stats">
          <div><div class="v">${fmt(v.partners)}</div><div class="l">partner institutions</div></div>
          <div><div class="v">${v.impact_ratio ?? "–"}</div><div class="l">impact ratio (in ÷ out)</div></div>
          <div><div class="v">${fmt(v.citations_in)}</div><div class="l">citations received</div></div>
          <div><div class="v">${fmt(v.citations_out)}</div><div class="l">citations given</div></div>
        </div>
        <div class="note">${v.impact_ratio >= 1 ? "Cited by other Indian institutions more than it cites them." : "Cites other Indian institutions more than it is cited by them."}</div>
      </div>`;
    }).join("")}</div>
    <div class="picker">
      <div><div class="picker-label">Show partners of</div><div class="picker-note">Sets the two charts below and the citation flow by year.</div></div>
      <div class="inst-pick" id="pick" role="group" aria-label="Institution">${INST_KEYS.map((k) => `<button data-k="${k}" class="${k === inst ? "active" : ""}"
        style="--c:${INST[k].color};--on:${onColor(INST[k].color)}" aria-pressed="${k === inst}"><span class="dot"></span>${esc(INST[k].name)} <small>${k}</small></button>`).join("")}</div>
    </div>
    <div class="grid g-2">
      <div class="card"><h3 id="p-title"></h3><p class="card-sub">Indian institutions with the most shared papers (other assigned institutions included).</p>
        <div class="chart tall" id="partners"></div></div>
      <div class="card"><h3 id="c-title"></h3><p class="card-sub">Indian institutions (outside the assigned three) whose papers cite this institution most.</p>
        <div class="chart tall" id="citing"></div></div>
    </div>
    <div class="card mt"><div class="card-head"><div><h3>Who collaborates with whom</h3>
      <p class="card-sub">Rows correspond to the top 8 Indian partners from each university combined. Numbers and shading show co-authored papers as a share of that university's output. Blank cells mean the partner is outside that university's top 25.</p></div></div>
      <div class="chart" id="matrix"></div></div>
    <div class="card mt"><h3 id="f-title"></h3><p class="card-sub">Citations received from (in) and given to (out) other Indian institutions, by year of the citing paper.</p>
      <div class="chart" id="flow"></div></div>`);

  // matrix: partner rows × institution columns; the shade is normalised by each institution's size so DU does not dominate
  const top = INST_KEYS.map((k) => c.institutions[k].top_partners.filter((p) => !p.assigned));
  const names = [...new Set(top.flatMap((list) => list.slice(0, 8).map((p) => p.name)))];
  const shared = (i, name) => top[i].find((p) => p.name === name)?.shared;
  const total = (name) => INST_KEYS.reduce((sum, _, i) => sum + (shared(i, name) ?? 0), 0);
  names.sort((a, b) => total(a) - total(b));  // largest partner at the top of the y-axis
  const share = (i, n) => n / o.institutions[INST_KEYS[i]].papers;
  const cells = names.flatMap((name, y) => INST_KEYS.map((k, x) => [x, y, shared(x, name)]).filter((d) => d[2] !== undefined));
  const maxShare = Math.max(...cells.map(([x, , n]) => share(x, n)));
  const matrix = $("#matrix");
  matrix.style.height = `${names.length * 30 + 50}px`;
  chart(matrix, {
    tooltip: { formatter: (p) => `<b>${esc(names[p.data.value[1]])}</b> × ${INST_KEYS[p.data.value[0]]}<br/>${fmt(p.data.value[2])} shared papers
      (${pct(share(p.data.value[0], p.data.value[2]) * 100, 1)} of ${INST_KEYS[p.data.value[0]]}'s papers)` },
    grid: { left: 8, right: 8, top: 30, bottom: 4, containLabel: true },
    xAxis: { type: "category", position: "top", data: INST_KEYS, axisTick: { show: false }, axisLine: { show: false }, splitArea: { show: false },
      axisLabel: { fontWeight: 700, fontSize: 12.5, color: (k) => INST[k].color } },
    yAxis: { type: "category", data: names, axisTick: { show: false }, axisLine: { show: false }, splitArea: { show: false },
      axisLabel: { color: T.text2, width: 300, overflow: "truncate" } },
    // heatmap needs a visualMap (dev builds throw without one); it is hidden, the cell text carries the numbers
    visualMap: { show: false, dimension: 3, min: 0, max: 1, inRange: { color: [...T.seq] } },
    series: [{ type: "heatmap", itemStyle: { borderColor: T.stage, borderWidth: 3, borderRadius: 3 },
      emphasis: { itemStyle: { borderColor: T.text, borderWidth: 2 } },
      data: cells.map(([x, y, n]) => {
        const t = share(x, n) / maxShare;
        return { value: [x, y, n, t], label: { show: true, color: onColor(rampColor(t)), fontWeight: 600, formatter: () => fmt(n) } };
      }) }],
  });

  const partners = chart($("#partners"), {});
  const citing = chart($("#citing"), {});
  const flow = chart($("#flow"), {});
  function draw() {
    const v = c.institutions[inst];
    const color = INST[inst].color;
    $("#p-title").textContent = `Top partners · ${inst}`;
    $("#c-title").textContent = `Top 10 institutes citing ${inst}`;
    $("#f-title").textContent = `Citation flow by year · ${inst}`;
    const top = v.top_partners.slice(0, 12).reverse();
    partners.setOption({
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (p) => {
        const x = top[p[0].dataIndex];
        return `<b>${esc(x.name)}</b><br/>${fmt(x.shared)} shared papers · ${fmt(x.citations)} citations<br/>cites ${inst}: ${fmt(x.received)} · cited by ${inst}: ${fmt(x.given)}`;
      } },
      grid: { left: 8, right: 44, top: 6, bottom: 4, containLabel: true },
      xAxis: { type: "value", show: false },
      yAxis: { type: "category", data: top.map((x) => x.name), axisLabel: { color: T.text2, width: 250, overflow: "truncate" } },
      series: [{ type: "bar", barWidth: "62%", data: top.map((x) => ({ value: x.shared,
        itemStyle: { color: x.assigned ? INST[INST_KEYS.find((k) => INST[k].name === x.name)].color : color, opacity: x.assigned ? 1 : 0.8, borderRadius: [0, 2, 2, 0] } })),
        label: { show: true, position: "right", color: T.muted } }],
    }, true);
    const ct = v.top_citing.slice().reverse();
    citing.setOption({
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 8, right: 54, top: 6, bottom: 4, containLabel: true },
      xAxis: { type: "value", show: false },
      yAxis: { type: "category", data: ct.map((x) => x.name), axisLabel: { color: T.text2, width: 250, overflow: "truncate" } },
      series: [{ type: "bar", barWidth: "62%", data: ct.map((x) => x.received), itemStyle: { color, opacity: 0.75, borderRadius: [0, 2, 2, 0] },
        label: { show: true, position: "right", color: T.muted, formatter: (p) => fmt(p.value) } }],
    }, true);
    flow.setOption({
      tooltip: { trigger: "axis" }, legend: { top: 0, right: 0 },
      xAxis: { type: "category", data: c.years, boundaryGap: false },
      yAxis: { type: "value" },
      series: [
        { name: "Citations in", type: "line", smooth: 0.35, symbol: "none", data: v.flow_in, lineStyle: { width: 3, color }, itemStyle: { color }, areaStyle: { color: gradient(color, 0.35) } },
        { name: "Citations out", type: "line", smooth: 0.35, symbol: "none", data: v.flow_out, lineStyle: { width: 2.5, color: T.all, type: "dashed" }, itemStyle: { color: T.all } },
      ],
    }, true);
  }
  draw();
  $("#pick").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    inst = b.dataset.k;
    $("#pick").querySelectorAll("button").forEach((x) => { x.classList.toggle("active", x === b); x.setAttribute("aria-pressed", x === b); });
    draw();
  });
}
