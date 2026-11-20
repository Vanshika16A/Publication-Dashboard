import { chart, esc, fmt, fmtCompact, INST, INST_KEYS, fieldColor, fieldIcon, fieldIconUrl, load, mount, onColor, pct, setTeam, shadowPointer, T, TEAM, teamIndex, TEAMS } from "../lib.js";
import duArt from "../assets/du.svg?raw";
import jnuArt from "../assets/jnu.svg?raw";
import uohArt from "../assets/uoh.svg?raw";

const ART = { DU: duArt, JNU: jnuArt, UoH: uohArt };
const FORMAT = { int: fmt, compact: fmtCompact, pct: (v) => pct(v) };
// rows of the institution comparison: label, value, how to print it
const COMPARE = [
  ["Papers", (i) => i.papers, fmt],
  ["Faculty", (i) => i.faculty, fmt],
  ["Citations", (i) => i.citations, fmtCompact],
  ["Citations per paper", (i) => i.citations / i.papers, (v) => v.toFixed(1)],
  ["Papers in Q1 journals", (i) => i.q1_share, (v) => pct(v)],
  ["Median author h-index", (i) => i.median_h, (v) => String(v)],
  ["Indian partner institutions", (i) => i.partners, fmt],
];
const num = (value, kind = "int") => (value === null || value === undefined ? "–" : FORMAT[kind](value));

// treemap labels: OpenAlex field names short enough for a medium tile
const FIELD_SHORT = {
  "Engineering": "Engineering", "Materials Science": "Materials", "Physics and Astronomy": "Physics",
  "Computer Science": "Computer Sci.", "Biochemistry, Genetics and Molecular Biology": "Biochem. & Genetics",
  "Agricultural and Biological Sciences": "Agri. & Bio.", "Environmental Science": "Environment", "Chemistry": "Chemistry",
  "Mathematics": "Maths", "Earth and Planetary Sciences": "Earth Sciences", "Energy": "Energy",
  "Immunology and Microbiology": "Immunology", "Neuroscience": "Neuroscience", "Chemical Engineering": "Chemical Eng.",
};
const LABEL_FONT = "Atkinson Hyperlegible Next, system-ui, sans-serif";
const PAD_X = 10, PAD_Y = 8, MIN_FONT = 12;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const measureCtx = document.createElement("canvas").getContext("2d");
const textWidth = (text, size, weight) => {
  measureCtx.font = `${weight} ${size}px ${LABEL_FONT}`;
  return measureCtx.measureText(text).width;
};
// cut text to maxW with an ellipsis; null when fewer than `keep` characters would survive
function truncate(text, size, weight, maxW, keep = 1) {
  if (textWidth(text, size, weight) <= maxW) return text;
  for (let n = text.length - 1; n >= keep; n--) {
    const cut = `${text.slice(0, n).trimEnd()}…`;
    if (textWidth(cut, size, weight) <= maxW) return cut;
  }
  return null;
}
// greedy word wrap to at most maxLines; the last line is truncated if words remain
function wrap(text, size, weight, maxW, maxLines) {
  const lines = [];
  let rest = text.split(" ");
  while (rest.length && lines.length < maxLines) {
    let n = rest.length;
    while (n > 1 && textWidth(rest.slice(0, n).join(" "), size, weight) > maxW) n--;
    lines.push(rest.slice(0, n).join(" "));
    rest = rest.slice(n);
  }
  if (rest.length) lines[lines.length - 1] = `${lines[lines.length - 1]} ${rest.join(" ")}`;
  const last = truncate(lines[lines.length - 1], size, weight, maxW, 3);
  if (!last || lines.some((l, i) => i < lines.length - 1 && textWidth(l, size, weight) > maxW)) return null;
  lines[lines.length - 1] = last;
  return lines;
}
/**
 * Label for one treemap tile of drawn size w × h, or null when nothing fits (the tooltip still has it all).
 *   large   field icon + full name (wrapped, up to 3 lines, never clipped), count, share
 *   medium  field icon + short name (whole), count
 *   small   field icon + count, else count
 * The icon sits before the first text line; its width counts when fitting that line.
 * Font sizes grow with the tile; every line is measured, so text never runs past the tile.
 */
function fitTileLabel(tile, w, h, share, icon) {
  const innerW = w - 2 * PAD_X, innerH = h - 2 * PAD_Y;
  const count = fmt(tile.value);
  const ICON_GAP = 5;
  const build = (lines) => {
    const rich = {};
    lines.forEach(([style, , size, weight, lineHeight, opacity]) => {
      rich[style] = { fontSize: size, fontWeight: weight, lineHeight, align: "center", ...(opacity && { opacity }) };
    });
    const [, , iconSize] = lines[0];
    if (icon) Object.assign(rich, { ic: { width: iconSize, height: iconSize, backgroundColor: { image: icon } }, gap: { width: ICON_GAP } });
    const extra = (i, size) => (icon && i === 0 ? size + ICON_GAP : 0);
    const height = lines.reduce((sum, l) => sum + l[4], 0);
    const fits = height <= innerH && lines.every(([, text, size, weight], i) => textWidth(text, size, weight) + extra(i, size) <= innerW);
    const line = ([style, text], i) => `${icon && i === 0 ? "{ic|}{gap|}" : ""}{${style}|${text}}`;
    return fits && { text: lines.map(line).join("\n"), rich, padTop: Math.max(0, Math.round((h - height) / 2)) };
  };

  const v = Math.round(clamp(Math.min(w / 5.5, h / 3.8), 18, 30));
  const n = Math.round(clamp(v * 0.55, 13, 16));
  const name = wrap(tile.name, n, 600, innerW, 3);
  if (name?.join(" ") === tile.name) {  // the full name or nothing: a clipped name reads worse than a short one
    const large = build([...name.map((l) => ["n", l, n, 600, n + 5]), ["v", count, v, 700, v + 10], ["p", share, 13, 400, 18, 0.85]]);
    if (large) return large;
  }
  const mv = Math.round(clamp(Math.min(w / 5, h / 3), 14, 20));
  const short = FIELD_SHORT[tile.name] ?? tile.name;
  {
    const medium = build([["n", short, 12.5, 600, 17], ["v", count, mv, 700, mv + 6]]);
    if (medium) return medium;
  }
  const sv = Math.round(clamp(Math.min(w / 4.2, h / 1.8), MIN_FONT, 15));
  const small = build([["v", count, sv, 700, sv + 4]]);
  if (small || !icon) return small || null;
  icon = null;  // too narrow for the icon: count alone
  return build([["v", count, sv, 700, sv + 4]]) || null;
}

export default async function overview(el) {
  const [o, s, conn, au] = await Promise.all([load("overview"), load("stats"), load("connections"), load("authors")]);
  const t = o.totals;
  // faculty = authors with 5+ papers, same rule as the Authors page; one person counted once across institutions
  const col = Object.fromEntries(au.columns.map((c, i) => [c, i]));
  const faculty = {};
  const facultyAll = new Set();
  for (const r of au.rows) {
    if (r[col.papers] < 5) continue;
    const key = r[col.id] || r[col.name];
    (faculty[r[col.inst]] ||= new Set()).add(key);
    facultyAll.add(key);
  }
  for (const k of INST_KEYS) i_faculty(k);
  function i_faculty(k) { o.institutions[k].faculty = (faculty[k] || new Set()).size; }
  const kpis = [
    ["Papers", num(t.papers), `${fmt(t.journal)} journal · ${fmt(t.conference)} conference`],
    ["Faculty", num(facultyAll.size), "authors with 5+ papers"],
    ["Citations", num(t.citations, "compact"), "received by these papers"],
    ["Papers in Q1 journals", num(t.q1_share, "pct"), `of the ${pct(t.quartile_coverage, 0)} with a quartile`],
  ];
  // team-size filter: switches every page except Insights to papers with up to 10 / more than 10 authors
  const teams = await teamIndex();
  const teamPapers = Object.fromEntries(teams.groups.map((g) => [g.id, g.papers]));
  const teamFilter = teams.groups.length ? `
    <div class="team-filter">
      <span class="team-label">Papers by number of authors</span>
      <div class="seg" id="team">${Object.entries(TEAMS).map(([id, d]) => `<button data-team="${id}" class="${id === TEAM ? "active" : ""}"
        title="${id === "all" ? "Every paper" : `${fmt(teamPapers[id] ?? 0)} papers`}">${esc(d.label)}</button>`).join("")}</div>
      <span class="note">Applies to every page except Insights.${TEAM === "all" ? "" : ` Showing ${fmt(t.papers)} ${esc(TEAMS[TEAM].short)}.`}</span>
    </div>` : "";
  const $ = mount(el, `${teamFilter}
    <section class="hero">
      <h2>Comparing JNU, University of Hyderabad and University of Delhi</h2>
      <p>We collected ${fmt(t.papers)} journal and conference papers from ${o.years[0]} to ${o.years[1]}from OpenAlex.<br>
        Journal quartiles are from SCImago and conference ranks are from CORE.<br>
    </section>

    <div class="card stat-strip reveal">${kpis.map(([l, v, n]) => `
      <div class="stat"><div class="stat-label">${l}</div><div class="stat-value">${v}</div><div class="stat-note">${n}</div></div>`).join("")}
    </div>

    <div class="card mt"><h3>The three institutions side by side</h3>
      <p class="card-sub">Largest value in each row is shown in bold.</p>
      <div class="table-wrap" style="border:0"><table class="compare">
        <thead><tr><th class="metric"></th>${INST_KEYS.map((k) => `
          <th style="--c:${INST[k].color}"><div class="col-head"><div class="inst-art">${ART[k]}</div>
            <div class="name">${esc(o.institutions[k].name)}<small>${k}</small></div></div></th>`).join("")}</tr></thead>
        <tbody>${COMPARE.map(([label, get, show]) => {
          const vals = INST_KEYS.map((k) => get(o.institutions[k]));
          const max = Math.max(...vals.filter((v) => v !== null && v !== undefined));
          return `<tr><th class="metric">${label}</th>${INST_KEYS.map((k, c) => {
            const v = vals[c];
            return `<td class="${v === max ? "best" : ""}" style="--c:${INST[k].color}"><div class="num">${v === null || v === undefined ? "–" : show(v)}</div>
              <div class="bar"><i style="width:${v ? (v / max) * 100 : 0}%"></i></div></td>`;
          }).join("")}</tr>`;
        }).join("")}
          <tr><th class="metric">Largest field</th>${INST_KEYS.map((k) => `<td class="text">
            <span class="field-ic" style="color:${fieldColor(o.institutions[k].top_field)}">${fieldIcon(o.institutions[k].top_field, 16)}</span>${esc(o.institutions[k].top_field)}</td>`).join("")}</tr>
        </tbody>
      </table></div>
    </div>

    <div class="grid g-3 mt">
      <div class="card span-2"><h3>Papers per year</h3>
        <p class="card-sub">A paper shared by two institutions counts in both their bar heights, but the label above each bar counts it once.<br>Note that 2026 is a partial year.</p>
        <div class="chart" id="trend"></div></div>
      <div class="card"><h3>Papers written together</h3>
        <p class="card-sub">Papers with authors from both institutions.</p>
        <div class="pairs" id="shared"></div></div>
    </div>

    <div class="card mt"><h3>Research areas</h3><p class="card-sub">Papers are grouped by OpenAlex primary field. Tile area indicates the number of papers. Hover or tap a tile for more details.</p>
      <div class="chart" id="fields" style="height:460px"></div></div>`);

  $("#team")?.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-team]");
    if (b) setTeam(b.dataset.team);  // main.js redraws the page
  });

  // The stack height counts a shared paper once per institution, but the label gives the year's unique papers (s.trend.All)
  const unique = s.trend.All;
  const partial = s.years.length - 1;
  chart($("#trend"), {
    tooltip: { trigger: "axis", axisPointer: shadowPointer() },
    legend: { top: 0, right: 0 },
    grid: { left: 4, right: 16, top: 52, bottom: 4, containLabel: true },
    xAxis: { type: "category", data: s.years },
    yAxis: { type: "value" },
    series: INST_KEYS.map((k, i) => ({
      name: k, type: "bar", stack: "p", barWidth: "52%",
      data: s.trend[k].map((v, y) => (y === partial ? { value: v, itemStyle: { opacity: 0.4 } } : v)),
      itemStyle: { color: INST[k].color, borderRadius: i === 2 ? [4, 4, 0, 0] : 0 },
      emphasis: { focus: "series" },
      ...(i === 2 && {
        label: { show: true, position: "top", distance: 6, formatter: (p) => fmt(unique[p.dataIndex]), color: T.text2, fontSize: 11.5, fontWeight: 600 },
      }),
    })),
  });

  const m = conn.between_assigned;
  const pairs = [[0, 1], [0, 2], [1, 2]].map(([a, b]) => ({ a: INST_KEYS[a], b: INST_KEYS[b], n: m[a][b] })).sort((x, y) => y.n - x.n);
  const most = Math.max(...pairs.map((p) => p.n));
  const share = (k, n) => pct((n / o.institutions[k].papers) * 100, 1);
  $("#shared").innerHTML = pairs.map((p) => `
    <div class="pair">
      <div class="pair-head">
        <span class="pair-name"><i style="background:${INST[p.a].color}"></i>${p.a}<span class="pair-x">and</span><i style="background:${INST[p.b].color}"></i>${p.b}</span>
        <span class="pair-n">${fmt(p.n)}</span>
      </div>
      <div class="pair-track"><div class="pair-bar" style="width:${(p.n / most) * 100}%;background:linear-gradient(90deg, ${INST[p.a].color}, ${INST[p.b].color})"></div></div>
      <div class="pair-note">${share(p.a, p.n)} of ${p.a}'s papers · ${share(p.b, p.n)} of ${p.b}'s</div>
    </div>`).join("");

  // part of a whole with 14 parts: a treemap shows each field's share at a glance; each field has one fixed colour
  // across the dashboard (lib.js fieldColor). Labels follow the tile's drawn size (tiers below); every tile gives
  // its full details in the tooltip, on hover or tap.
  const ofAll = (v) => pct((v / t.papers) * 100);
  const tiles = Object.entries(s.fields.All).sort((a, b) => b[1] - a[1]).map(([name, value]) => ({ name, value, color: fieldColor(name) }));
  const tileData = (labels = {}) => tiles.map(({ name, value, color }) => {
    const l = labels[name];
    return { name, value, itemStyle: { color }, label: l ? { show: true, color: onColor(color), padding: [l.padTop, 0, 0, 0], formatter: l.text, rich: l.rich }
      : { show: false } };
  });
  const treemap = chart($("#fields"), {
    animation: false,
    tooltip: { triggerOn: "mousemove|click", formatter: (p) => `<span style="display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:7px;background:${p.color}"></span>${fieldIcon(p.name, 13)} <b>${esc(p.name)}</b><br/>${fmt(p.value)} papers · ${ofAll(p.value)} of all` },
    series: [{
      type: "treemap", left: 0, right: 0, top: 0, bottom: 0, roam: false, nodeClick: false, breadcrumb: { show: false },
      itemStyle: { borderColor: T.stage, borderWidth: 2, gapWidth: 2, borderRadius: 3 },
      label: { show: true, position: "insideTop", align: "center" },
      upperLabel: { show: false },
      emphasis: { itemStyle: { borderColor: T.text } },
      data: tileData(),
    }],
  });
  // ECharts stretches a treemap label box over the whole tile and draws from its top, so each label is placed by
  // measuring its lines and padding the box by half the free height; this reruns after every layout (resize) and
  // once the web font has loaded, since the measurements depend on it
  let lastKey = "";
  const relabel = () => {
    if (treemap.isDisposed()) return;
    const nodes = treemap.getModel().getSeriesByIndex(0).getData().tree.root.children;
    const labels = Object.fromEntries(nodes.map((n) => {
      const { width, height } = n.getLayout() ?? {};
      const tile = tiles.find((d) => d.name === n.name);
      return [n.name, width ? fitTileLabel(tile, width - 4, height - 4, ofAll(tile.value), fieldIconUrl(tile.name, onColor(tile.color))) : null];
    }));
    const key = JSON.stringify(labels);
    if (key === lastKey) return;
    lastKey = key;
    treemap.setOption({ series: [{ data: tileData(labels) }] });
  };
  treemap.on("finished", relabel);
  document.fonts?.ready.then(() => { lastKey = ""; relabel(); });
}
