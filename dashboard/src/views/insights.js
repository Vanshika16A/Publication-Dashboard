import "./insights.css";
import { ALL_COLOR, chart, esc, gradient, INST, load, mix, mount, SHARED, T } from "../lib.js";

// Written findings, worked out from the paper-level data (collector/data/output) rather than read off the other pages.
// Unless a finding says otherwise, papers with 100+ authors are left out, so large physics collaborations do not swamp
// the comparison. "Cited relative to field and year" means a paper's citations divided by the average for papers in
// the same OpenAlex field and year in this dataset, counting papers up to 2023 so every paper has had time to be cited.
const INSIGHTS = [
  {
    key: "expansion",
    title: "DU's expansion came from environmental, agricultural, engineering and materials research, not from its physics base",
    body: "Most of the papers DU added between 2016–18 and 2023–25 are in environmental science, agriculture, engineering, materials science and computer science, while physics grew far less and fell from about 12% to about 9% of DU's papers. At UoH the added papers are mostly in computer science and engineering, and chemistry shrank. JNU's growth was modest, and its molecular biology output has stayed flat.",
    see: ["publications", "Publications"],
  },
  {
    key: "topics",
    title: "Research topics have moved towards applied and environmental problems",
    body: "The fastest-growing topics at all three universities are pollutant removal, photocatalysis, nanoparticles, battery and solar cell materials, microplastics and computer-based drug discovery. In computing, work has moved from studying networks themselves to applied areas such as blockchain, IoT, intrusion detection and AI for agriculture and medicine. Particle physics and mid-2010s wireless networking topics have shrunk.",
    see: ["publications", "Publications"],
  },
  {
    key: "conference",
    title: "Conference output now goes mostly into publisher book series",
    body: "Springer series such as Lecture Notes in Networks and Systems and Springer Proceedings in Physics were absent in 2016–2018 but are now among the most-used venues, and SCImago grades almost all of them Q4. This is why so few conference papers carry a CORE rank: the work goes into proceedings series, not the computer science conferences CORE ranks.",
    see: ["publications", "Publications"],
  },
  {
    key: "regrade",
    title: "Much of the fall in Q1 share comes from journals being re-graded, not from researchers choosing weaker journals",
    body: "Several journals these universities used throughout the decade, such as The Journal of Organic Chemistry, Dalton Transactions and the Journal of High Energy Physics, were moved from Q1 to Q2 by SCImago. If recent papers kept their journal's 2016–2018 grade, UoH's Q1 share would have risen rather than fallen. At DU re-grading explains part of the decline, and the rest is a real shift towards lower-ranked journals.",
    see: ["publications", "Publications"],
  },
  {
    key: "chemistry",
    title: "Chemistry was affected most, at all three universities",
    body: "The share of chemistry papers in Q1 journals fell sharply at DU, JNU and UoH at the same time, matching the main chemistry journals losing their Q1 grade between 2021 and 2023. It should not be read as a problem in any one department. Environmental science went the other way, partly because its journals were graded higher in later years.",
    see: ["journals", "Top journals"],
  },
  {
    key: "chemistry_if",
    title: "Measured by impact factor instead, chemistry held steady",
    body: "This is the chemistry finding above redone with journal impact factor (IF, OpenAlex 2-year mean citedness, one value per journal) in place of the SCImago quartile, with the same papers. The share of chemistry papers in journals with IF above 5 shows no fall like the Q1 share: comparing 2016–18 with 2023–25 it rose a little at DU and UoH and dipped a little at JNU. Roughly three in four chemistry papers at each university are in journals with IF of 5 or below, most of the rest have IF between 5 and 10, and only a few percent have IF of 10 or more.",
    see: ["journals", "Top journals"],
  },
  {
    key: "chemistry_compare",
    title: "Q1 and impact factor disagree on chemistry, so the fall in Q1 share is re-grading rather than weaker journals",
    body: "Between 2016–18 and 2023–25 the Q1 share of chemistry papers fell by between about 17 and 30 percentage points at all three universities. Over the same years the share in journals with IF above 5 rose by about 7 points at DU and 6 at UoH and fell by about 4 at JNU, and the share with IF 10 or more barely moved at DU and UoH (JNU, with few chemistry papers, fell 4 points). Each journal has one fixed IF here, so the IF shares change only when chemists publish in different journals, whereas the quartile also changes when SCImago re-grades a journal. Read together, chemists kept publishing in journals of similar impact, and the drop in Q1 share comes from the main chemistry journals being moved out of Q1 (see the re-grading finding). Q1 is also not the same as high impact: in 2016–18 about half or more of chemistry papers were in Q1 journals, but only a sixth to a third were in journals with IF above 5, and 62% of chemistry papers in Q1 journals are in journals with IF of 5 or below.",
    see: ["journals", "Top journals"],
  },
  {
    key: "q1vscite",
    title: "A high Q1 share and a high citation rate do not go together here",
    body: "UoH publishes the largest share of its papers in Q1 journals, but they are cited at about the average rate for their field and year (the average of all three universities' papers in the same OpenAlex field and year, papers up to 2023). JNU's papers are cited above that average in most fields. The two measures put the universities in a different order, so neither should be used on its own to compare them.",
    see: ["overview", "Overview"],
  },
  {
    key: "ifactor",
    title: "A high Q1 share therefore does not mean many papers in top-impact journals",
    body: "Impact factor here is OpenAlex's 2-year mean citedness of the journal, measured once at data collection. Averages are taken over the three universities' journal papers, 2016–2026, each paper counted once: 3.8 overall, and 3.6 for DU, 4.0 for JNU and 4.2 for UoH on their own. Fewer than half of each university's papers are in journals above either average. Among papers by fewer than 100 authors, those in journals scoring 10 or more average about 67 citations, against about 4 for journals scoring under 1.",
    see: ["publications", "Publications"],
  },
  {
    key: "teamsize",
    title: "Papers now credit about one more author than they did in 2016, at all three universities",
    body: "Average team size per paper, leaving out papers with 100 or more authors, rose at DU, JNU and UoH, mostly between 2018 and 2023, and has stayed near five since. Growth in paper counts is therefore partly growth in authors per paper, and counts of papers or author-paper links should not be read as a like-for-like rise in separate projects.",
    see: ["publications", "Publications"],
  },
  {
    key: "hyper",
    title: "Hyperauthor behaviour differs: DU's papers with 100+ authors have not grown with its output, while UoH's have",
    body: "DU had 105 papers with 100 or more authors in 2016 and 81 in 2025, while its other output roughly doubled, so such papers matter less to DU than they once did. UoH had 2 in 2016 and 57 in 2025, so large consortia are now a visible part of its recent output. JNU has had almost none. Counts that include these papers, such as authors, partners and citations, should be read with this in mind.",
    see: ["connections", "Indian connections"],
  },
  {
    key: "roles",
    title: "Papers these universities join are cited more than papers they lead",
    body: "Papers where the university had the first, last or corresponding author are cited at about the average for their field and year, while papers where it only contributed middle authors are cited more and appear in Q1 journals more often. The gap is largest at JNU, where most of the above-average citation rate comes from projects led elsewhere.",
    see: ["cited", "Most cited"],
  },
  {
    key: "led",
    title: "The universities are leading a smaller share of their own papers",
    body: "The share of papers with a first, last or corresponding author from the university has gone down at all three, most steadily at DU, while teams have grown slightly. This means growth in paper counts overstates growth in research led from these universities.",
    see: ["publications", "Publications"],
  },
  {
    key: "partners",
    title: "Papers with Indian partners are cited more, and DU has moved furthest in that direction",
    body: "Papers that include another Indian institution are cited more than papers written by one university alone. DU's share of such papers rose from under half to about three in five, JNU has had the highest share throughout, and UoH still writes about half of its papers without any other Indian institution.",
    see: ["connections", "Indian connections"],
  },
  {
    key: "dupartners",
    title: "DU's list of partners is shaped by particle physics collaborations",
    body: "DU's apparent top partners, such as Panjab University, TIFR, Saha Institute and BARC, come almost entirely from large international physics experiments that list every member institution on every paper. With those set aside, DU's main partners are Delhi institutions: JNU, NSUT, Amity, DTU, Jamia Millia Islamia and IIT Delhi.",
    see: ["connections", "Indian connections"],
  },
  {
    key: "local",
    title: "Collaboration is mostly local",
    body: "JNU works mainly with DU, IIT Delhi, Jamia and its neighbours ICGEB and NIPGR. UoH's partners are almost all in Hyderabad or elsewhere in Telangana, including IIT Hyderabad, GITAM, IDRBT, IICT and Osmania University. Being in the same city seems to matter more than working in the same subjects.",
    see: ["connections", "Indian connections"],
  },
  {
    key: "pairs",
    title: "DU and JNU are the only pair with a real working relationship",
    body: "None of the papers DU and JNU share come from the large physics collaborations, while most of what UoH shares with DU, and about half of what it shares with JNU, does. JNU and UoH publish about the same amount and overlap in several subjects but hardly work together, most likely because of distance.",
    see: ["coauthor", "Co-authorship"],
  },
  {
    key: "communities",
    title: "The DU–JNU link is spread across many researchers",
    body: "Most co-authorship communities belong almost entirely to one university, and the few mixed ones are nearly all DU–JNU groups in environmental science, agriculture, materials science and engineering. No small group of researchers accounts for most of these cross-university links, so the relationship does not depend on a few individuals.",
    see: ["coauthor", "Co-authorship"],
  },
  {
    key: "citers",
    title: "The institutions that cite these universities most are often not their collaborators",
    body: "Saveetha, Lovely Professional University, Chandigarh University, VIT and SRM are among the heaviest citers but rarely appear as co-authors. They are large private universities that publish a great deal, so their citation counts reflect volume as much as close interest in the work.",
    see: ["connections", "Indian connections"],
  },
  {
    key: "impact",
    title: "The overall impact ratio understates where the universities stand now",
    body: "In the early years the universities' papers had little time to be cited, while the papers they cited spanned many earlier years, so the full-period ratio starts low for all three. In the most recent full years JNU and UoH are cited by other Indian institutions more than they cite them, and DU is close to even.",
    see: ["connections", "Indian connections"],
  },
  {
    key: "mostcited",
    title: "The most-cited papers are mostly reviews or parts of large consortia",
    body: "Among small-team papers, most of the highly cited ones are reviews in environmental science, agriculture and microbiology, and reviews have become about twice as common since 2020. The rest of the top places go mainly to large international projects such as the wheat genome study, so the Most cited page reflects influential reviews and collaborations more than each university's own discoveries.",
    see: ["cited", "Most cited"],
  },
];

// DU citation network: findings from citation network analysis of the University of Delhi's papers (collector/du_citation.py).
// The DU network is every paper with a DU author and every citation between two such papers (citation.json).
const DU_SECTION = {
  title: "University of Delhi: what its citation network shows",
  intro: "These findings come from the citation network of DU's papers alone: every paper with a DU author (2016–2026) and every citation from one such paper to another. They use the methods of citation network analysis as described by McLaren & Bruner (2022): network structure and connected components, prominence by citations received inside the network (in-degree), main path analysis and community detection. The field-integration reading follows Healy, Hammer & McIlveen (2022), who used direct citation networks to show whether research fields with shared goals actually build on each other.",
  refs: [
    ["McLaren & Bruner (2022), Citation network analysis, International Review of Sport and Exercise Psychology", "https://doi.org/10.1080/1750984X.2021.1989705"],
    ["Healy, Hammer & McIlveen (2022), Mapping graduate employability and career development in higher education research: a citation network analysis, Studies in Higher Education", "https://doi.org/10.1080/03075079.2020.1804851"],
  ],
};
const DU_INSIGHTS = [
  {
    key: "du_structure",
    title: "DU's citation network is sparse and split into many separate groups",
    body: "Of 21,856 DU papers, 35,219 citations link one DU paper to another, about 1.6 per paper. 37% of DU papers neither cite nor are cited by another DU paper, and the largest connected group holds only a third of DU's papers; the rest fall into more than a thousand small groups. Citations between DU papers are recent, with a median gap of two years. DU's output is therefore many separate lines of work rather than one connected body of research.",
    see: ["citation", "Citation network"],
  },
  {
    key: "du_selfcite",
    title: "DU builds on its own papers, and hardly on JNU's or UoH's",
    body: "94% of DU's citations to papers in this dataset go to other DU papers, although DU wrote 61% of the dataset's papers. DU cites JNU and UoH papers 2,205 times and is cited by them 1,524 times. JNU and UoH are even more inward-looking for their size: about 90% of their citations go to their own papers, though each wrote about a fifth of the dataset. The three universities draw little on each other's published work, as they also rarely write together outside the DU–JNU pair.",
    see: ["citation", "Citation network"],
  },
  {
    key: "du_concentration",
    title: "A small set of DU papers receives most of the citations DU gives itself",
    body: "The top 10% of DU papers receive 63% of all DU-to-DU citations and the top 1% receive 21%, while 58% of DU papers are never cited by another DU paper (Gini coefficient 0.80). Papers that DU colleagues cite often are usually cited often overall too (rank correlation 0.60), but 13 of DU's 100 most-cited papers have never been cited by another DU paper. These are mostly reviews and large international collaborations, whose influence lies outside DU.",
    see: ["cited", "Most cited"],
  },
  {
    key: "du_fields",
    title: "DU's fields mostly cite themselves, physics and mathematics most of all",
    body: "80% of citations between DU papers stay inside one OpenAlex field. Physics and astronomy (98%) and mathematics (93%) are almost closed: physics alone gives 31% of all DU-to-DU citations from 15% of DU's papers, and about two-thirds of those are inside the CMS particle-physics collaboration. Energy (53%), and chemical engineering, neuroscience, biochemistry and environmental science (about 62%), draw most on other fields. Healy et al. (2022) found two fields with shared goals that rarely cite each other. In the same way, DU's departments share applied themes such as sensors, energy and pollution, but each mostly builds on its own field's papers.",
    see: ["citation", "Citation network"],
  },
  {
    key: "du_mainpath",
    title: "DU's main citation path is one mathematical-physics line; outside physics it runs from materials to medical sensors",
    body: "Main path analysis follows the chain of citations that the most citation paths pass through (search path count). For the whole DU network that chain is 26 papers from 2018 to 2026 on Lie symmetry and soliton solutions of nonlinear wave equations. Each paper builds on the last, so it is one steadily growing line of work, not the large physics collaborations. Leaving physics out, the main path starts with polyaniline and other conducting nanocomposites (2016–2021), moves to MXene-based gas sensors (2021–2022) and ends with breath-analysis biosensors for detecting disease (2023–2026). DU's longest continuous knowledge flow outside physics has therefore moved from making materials to medical applications, matching the shift to applied topics above.",
    see: ["citation", "Citation network"],
  },
  {
    key: "du_communities",
    title: "DU's citation communities are research groups and topics, not departments",
    body: "Louvain community detection splits the 13,699 DU papers with at least one DU citation link into 1,148 communities, with modularity 0.94. That is very high, meaning citations seldom cross from one community to another. The largest community is the CMS particle-physics collaboration (886 papers, nearly all physics). Many of the next largest mix fields: the second largest is computational drug-design work (DFT and molecular docking studies), and only 28% of its papers are chemistry, the rest being biochemistry, materials science, computer science and chemical engineering. DU's citation structure follows research groups and topics that cut across fields.",
    see: ["coauthor", "Co-authorship"],
  },
];

// ICONS used in Overview and Insights pages
const ICONS = {
  chemistry_if: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3"/><path d="M8 15h3M13 13l3 4"/>',
  chemistry_compare: '<path d="M4 20V8M10 20V4M16 20v-9M22 20H2"/><path d="M3 6l6-3 6 5 6-4"/>',
  du_structure: '<circle cx="5" cy="6" r="2"/><circle cx="11" cy="9" r="2"/><circle cx="6" cy="14" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="17" cy="17" r="2"/><path d="M6.700 7l2.600 1.300M7.400 12.700l2.400-2.200"/>',
  du_selfcite: '<path d="M20 12a8 8 0 1 1-3-6.200"/><path d="M20 4v4h-4"/>',
  du_concentration: '<path d="M3 20h18"/><path d="M5 20V4M9 20v-6M13 20v-3M17 20v-2"/>',
  du_fields: '<rect x="3" y="3" width="8" height="8" rx="1.500"/><rect x="13" y="13" width="8" height="8" rx="1.500"/><path d="M7 11v2a4 4 0 0 0 4 4h2"/>',
  du_mainpath: '<circle cx="5" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="19" r="2"/><path d="M6.500 6.500l4 4M13.500 13.500l4 4"/>',
  du_communities: '<circle cx="7" cy="8" r="4"/><circle cx="17" cy="8" r="3"/><circle cx="12" cy="17" r="3.500"/>',
  ifactor: '<path d="M3 20h18"/><path d="M6 20v-5M11 20V9M16 20v-8"/><path d="M4 8l5-4 4 3 7-4"/>',
  teamsize: '<circle cx="8" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M2.5 20c.5-3.500 2.700-5.500 5.500-5.500s5 2 5.500 5.500M14.500 14.800c.8-.3 1.600-.4 2.500-.4 2.400 0 4.200 1.700 4.600 4.600"/>',
  hyper: '<circle cx="12" cy="12" r="2"/><circle cx="5" cy="6" r="1.600"/><circle cx="19" cy="6" r="1.600"/><circle cx="5" cy="18" r="1.600"/><circle cx="19" cy="18" r="1.600"/><path d="M6.300 7.200l4 3.600M17.700 7.200l-4 3.600M6.300 16.800l4-3.600M17.700 16.800l-4-3.600"/>',
  expansion: '<path d="M3 21h18"/><path d="M5 21V10l7-6 7 6v11"/><path d="M9 21v-6h6v6"/>',
  topics: '<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
  conference: '<path d="M4 4h12a4 4 0 0 1 4 4v12H8a4 4 0 0 1-4-4z"/><path d="M8 8h8M8 12h8"/>',
  regrade: '<path d="M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.5 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z"/>',
  chemistry: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3"/><path d="M7.5 15h9"/>',
  q1vscite: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  roles: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><path d="M17 11l2 2 3-4"/>',
  led: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  partners: '<circle cx="6" cy="12" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M8.7 10.6l6.6-3.2M8.7 13.4l6.6 3.2"/>',
  dupartners: '<circle cx="12" cy="12" r="2.5"/><circle cx="12" cy="12" r="8"/><path d="M12 4v-2M12 22v-2M4 12H2M22 12h-2"/>',
  local: '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.800 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
  pairs: '<circle cx="9" cy="12" r="6"/><circle cx="15" cy="12" r="6"/>',
  communities: '<circle cx="12" cy="6" r="2.5"/><circle cx="5" cy="17" r="2.5"/><circle cx="19" cy="17" r="2.5"/><path d="M10.800 8.200L6.200 14.800M13.200 8.200l4.600 6.600M7.500 17h9"/>',
  citers: '<path d="M7 7h4v4c0 3-1.500 5-4 6M15 7h4v4c0 3-1.500 5-4 6"/>',
  impact: '<path d="M4 8h13l-3-3M20 16H7l3 3"/>',
  mostcited: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM7 6H4v1a3 3 0 0 0 3 3M17 6h3v1a3 3 0 0 1-3 3"/>',
};
const icon = (k) => `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[k]}</svg>`;
const colorOf = (key) => (INST[key] ? INST[key].color : key === "Shared" ? SHARED : ALL_COLOR);
const short = (s, n) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

const txt = () => ({ color: T.muted, fontSize: 11 });
const light = (hex, t) => mix(hex, T.stage, t);

// DOM-drawn forms: waffle (100 squares per group) and pictogram (one dot per item)
function drawCells(el, spec) {
  el.classList.add("ins-dom");
  if (spec.type === "waffle") {
    el.innerHTML = `<div class="ins-waffles">${spec.groups.map((g) => {
      const c = colorOf(g.color), n = Math.round(g.pct);
      return `<figure><div class="ins-waffle">${Array.from({ length: 100 }, (_, i) => `<i style="background:${i < n ? c : light(c, 0.82)}"></i>`).join("")}</div>
        <figcaption><b style="color:${c}">${g.pct}%</b> ${esc(g.label)}</figcaption></figure>`;
    }).join("")}</div>`;
  } else {
    el.innerHTML = `<div class="ins-dots">${spec.cells.map((k) => `<i style="background:${colorOf(k)}"></i>`).join("")}</div>
      <div class="ins-legend">${spec.legend.map(([l, k]) => `<span><i style="background:${colorOf(k)}"></i>${esc(l)} <b>${spec.cells.filter((c) => c === k).length}</b></span>`).join("")}</div>`;
  }
}

// Different charts 
function option(spec) {
  const tip = (extra = {}) => ({ appendTo: "body", ...extra });
  const type = spec.type;
  const hbarGrid = { left: 8, right: 30, top: 20, bottom: 8, containLabel: true };
  if (type === "bar") { // horizontal bars; grouped by university when there are several series, one colour per bar when the spec gives them
    const multi = spec.series.length > 1, s0 = spec.series[0], base = colorOf(s0.color);
    const label = { show: true, position: "right", color: T.muted, fontSize: 11, formatter: (p) => p.value.toLocaleString("en-IN") };
    return { tooltip: { trigger: "axis", axisPointer: { type: "shadow" } }, legend: multi ? { top: 0, right: 0 } : undefined, grid: { left: 8, right: 44, top: multi ? 30 : 8, bottom: 22, containLabel: true },
      xAxis: { type: "value", name: spec.unit, nameLocation: "middle", nameGap: 26, nameTextStyle: txt(), splitNumber: 4, axisLabel: { formatter: (v) => (v >= 1000 ? `${v / 1000}k` : v) } },
      yAxis: { type: "category", data: spec.categories, inverse: true, axisLabel: { width: 250, overflow: "truncate", fontSize: 11 } },
      series: multi ? spec.series.map((x, i) => ({ name: x.name, type: "bar", barMaxWidth: spec.stack ? 26 : 16, data: x.data, ...(spec.stack && { stack: "s" }),
        label: spec.stack ? { ...label, position: "inside", color: "#fff", formatter: (p) => (p.value >= 15 ? p.value : "") } : label,
        itemStyle: { color: x.tint ? light(colorOf(x.color), x.tint) : colorOf(x.color), borderRadius: spec.stack ? (i ? [0, 4, 4, 0] : [4, 0, 0, 4]) : [0, 4, 4, 0] } }))
        : [{ type: "bar", barMaxWidth: 22, data: s0.data.map((v, i) => ({ value: v, itemStyle: { color: spec.colors ? colorOf(spec.colors[i]) : light(base, 0), borderRadius: [0, 4, 4, 0] } })), label }] };
  }
  if (type === "line") {
    return { tooltip: { trigger: "axis" }, legend: { top: 0, right: 0 }, grid: { left: 8, right: 20, top: 34, bottom: 8, containLabel: true },
      xAxis: { type: "category", data: spec.x, boundaryGap: false }, yAxis: { type: "value", name: spec.unit, nameTextStyle: { ...txt(), align: "left" }, ...(spec.ymin ? { min: spec.ymin } : {}) },
      series: spec.series.map((s, i) => { const c = colorOf(s.color); return { name: s.name, type: "line", smooth: 0.3, symbol: "circle", symbolSize: 6, data: s.data, lineStyle: { width: 3, color: c }, itemStyle: { color: c },
        ...(i === 0 && spec.refline ? { markLine: { silent: true, symbol: "none", lineStyle: { color: T.muted, type: "dashed" }, label: { formatter: "even", position: "insideEndTop" }, data: [{ yAxis: spec.refline }] } } : {}) }; }) };
  }
  if (type === "dot") { // dot plot: one row per field, one dot per university
    return { tooltip: { trigger: "item" }, legend: { top: 0, right: 0 }, grid: { ...hbarGrid, bottom: 30 },
      xAxis: { type: "value", name: spec.unit, nameTextStyle: txt(), nameLocation: "middle", nameGap: 24 },
      yAxis: { type: "category", data: spec.categories, inverse: true, axisLabel: { width: 170, overflow: "truncate", fontSize: 11 }, splitLine: { show: true } },
      series: spec.series.map((s) => ({ name: s.name, type: "scatter", symbolSize: 14, itemStyle: { color: colorOf(s.color) }, data: s.data.map((v, i) => [v, i]) })) };
  }
  if (type === "rose") { // nightingale rose
    const d = spec.categories.map((c, i) => ({ name: c, value: spec.series[0].data[i] }));
    const base = colorOf("All");
    return { tooltip: { trigger: "item" }, series: [{ type: "pie", roseType: "area", radius: ["12%", "72%"], center: ["50%", "52%"],
      itemStyle: { borderColor: T.stage, borderWidth: 2, borderRadius: 4 }, label: { color: T.muted, fontSize: 11, width: 120, overflow: "break", formatter: "{b}\n+{c}" }, labelLine: { length: 8, length2: 6 },
      data: d.map((x, i) => ({ ...x, itemStyle: { color: light(base, 0.05 + i * 0.07) } })) }] };
  }
  if (type === "donuts") { // small multiple donuts
    const n = spec.donuts.length;
    return { tooltip: { trigger: "item" }, legend: { bottom: 0 }, series: spec.donuts.map((d, i) => ({
      type: "pie", radius: ["42%", "62%"], center: [`${(100 / n) * (i + 0.5)}%`, "46%"], name: d.name, avoidLabelOverlap: true,
      itemStyle: { borderColor: T.stage, borderWidth: 2 }, label: { show: false },
      data: d.data.map(([name, value], k) => ({ name, value, itemStyle: { color: k === 0 ? colorOf("All") : light(colorOf("All"), 0.8) } })) })),
      graphic: spec.donuts.map((d, i) => ({ type: "text", left: `${(100 / spec.donuts.length) * (i + 0.5) - 6}%`, top: "42%", style: { text: `${d.name}\n${Math.round((d.data[0][1] / (d.data[0][1] + d.data[1][1])) * 100)}%`, fill: T.text, font: "600 14px sans-serif", textAlign: "center" } })) };
  }
  if (type === "slope") {
    return { tooltip: { trigger: "item" }, legend: { top: 0, right: 0 }, grid: { left: 40, right: 50, top: 40, bottom: 12, containLabel: true },
      xAxis: { type: "category", data: spec.categories, boundaryGap: true, axisLabel: { fontSize: 11 } },
      yAxis: { type: "value", name: spec.unit, nameTextStyle: txt(), min: (v) => Math.floor(v.min - 5) },
      series: spec.series.map((s) => { const c = colorOf(s.color); return { name: s.name, type: "line", symbolSize: 10, itemStyle: { color: c }, lineStyle: { width: 3, color: c },
        data: s.data.map((v, i) => ({ value: v, label: { position: s.color === "DU" ? "bottom" : s.color === "JNU" && i === 1 ? "bottom" : "top" }, ...(i === 2 ? { itemStyle: { color: T.stage, borderColor: c, borderWidth: 2 } } : {}) })),
        label: { show: true, color: T.muted, fontSize: 11 } }; }) };
  }
  if (type === "heatmap") { // one hue per university, intensity = value
    const data = []; spec.series.forEach((s, r) => s.data.forEach((v, i) => { if (v !== null) data.push({ value: [i, r, v], itemStyle: { color: mix(light(colorOf(s.color), 0.9), colorOf(s.color), Math.min(1, v / 80)) } }); }));
    return { tooltip: { formatter: (p) => `${spec.series[p.value[1]].name}, ${spec.x[p.value[0]]}: ${p.value[2]}%` }, grid: { left: 8, right: 10, top: 10, bottom: 8, containLabel: true },
      xAxis: { type: "category", data: spec.x, axisLabel: { fontSize: 11 } }, yAxis: { type: "category", data: spec.series.map((s) => s.name), inverse: true },
      series: [{ type: "custom", data,
        renderItem: (params, api) => {
          const c = api.coord([api.value(0), api.value(1)]), [sw, sh] = api.size([1, 1]);
          const w = sw - 4, h = sh - 4;
          return { type: "group", children: [
            { type: "rect", shape: { x: c[0] - w / 2, y: c[1] - h / 2, width: w, height: h, r: 4 }, style: api.style() },
            { type: "text", style: { text: String(Math.round(api.value(2))), x: c[0], y: c[1], textAlign: "center", textVerticalAlign: "middle", fill: "#1c1b1a", font: "11px sans-serif" } }] };
        } }] };
  }
  if (type === "bump") { // rank chart: lines cross when the two measures disagree
    return { tooltip: { trigger: "item", formatter: (p) => `${esc(p.seriesName)}: rank ${p.value}<br>${esc(p.data.text)}` }, legend: { top: 0, right: 0 },
      grid: { left: 30, right: 30, top: 70, bottom: 12, containLabel: true },
      xAxis: { type: "category", data: spec.categories, boundaryGap: true, axisLabel: { interval: 0, fontSize: 11, width: 170, overflow: "break", lineHeight: 14 }, position: "top" },
      yAxis: { type: "value", min: 0.5, max: 3.5, inverse: true, interval: 1, axisLabel: { formatter: (v) => (v % 1 === 0 ? `#${v}` : ""), fontSize: 12 }, splitLine: { show: false } },
      series: spec.series.map((x) => { const c = colorOf(x.color); return { name: x.name, type: "line", symbolSize: 22, lineStyle: { width: 5, color: c }, itemStyle: { color: c },
        data: x.data.map((v, i) => ({ value: v, text: x.labels[i], label: { position: i ? "right" : "left" } })),
        label: { show: true, color: T.text, fontSize: 12, fontWeight: 600, formatter: (p) => `${x.name} ${p.data.text}`, distance: 12 } }; }) };
  }
  if (type === "bubble" || type === "scatter") {
    const maxS = Math.max(...spec.points.map((p) => p.size));
    const sz = type === "bubble" ? (v) => 18 + (v / maxS) * 50 : (v) => 10 + Math.sqrt(v / maxS) * 36;
    return { tooltip: { formatter: (p) => `${esc(p.data.name)}<br>${esc(spec.xname)}: ${p.data.value[0]}<br>${esc(spec.yname)}: ${p.data.value[1]}` },
      grid: { left: 8, right: 30, top: 34, bottom: 34, containLabel: true },
      xAxis: { type: "value", name: spec.xname, nameLocation: "middle", nameGap: 26, nameTextStyle: txt(), min: 30, max: 65 },
      yAxis: { type: "value", name: spec.yname, nameTextStyle: { ...txt(), align: "left" }, min: 85, max: 125 },
      series: [{ type: "scatter", data: spec.points.map((p) => ({ name: p.name, value: [p.x, p.y], symbolSize: sz(p.size), itemStyle: { color: colorOf(p.color), opacity: 0.85, borderColor: T.stage, borderWidth: 1.5 },
        label: type === "bubble" ? { show: true, formatter: p.name, position: "inside", color: "#fff", fontWeight: 600 } : { show: false } })) }] };
  }
  if (type === "arrow") { // dumbbell: papers the university led (filled) vs middle-author-only papers (hollow)
    const rows = spec.series.map((x) => x.name);
    return { tooltip: { trigger: "item", formatter: (p) => `${esc(p.seriesName)}<br>${esc(p.data.label)}: ${p.data.value[0]}` }, grid: { left: 8, right: 30, top: 52, bottom: 34, containLabel: true },
      xAxis: { type: "value", min: 0.5, max: 2.0, interval: 0.5, name: spec.unit, nameLocation: "middle", nameGap: 26, nameTextStyle: txt() }, yAxis: { type: "category", data: rows, inverse: true },
      graphic: [{ type: "text", left: 8, top: 0, style: { text: "Left dot = papers the university led (first, last or corresponding author)\nRight dot = papers where it was only a middle author", fill: T.muted, font: "12px sans-serif" } }],
      series: [
        { type: "line", silent: true, data: [], markLine: { silent: true, symbol: "none", lineStyle: { color: T.muted, type: "dashed" }, label: { formatter: "field-year avg", position: "end", fontSize: 10 }, data: [{ xAxis: 1 }] } },
        ...spec.series.map((x) => { const c = colorOf(x.color); return { name: x.name, type: "line", data: x.data.map((v, i) => ({ value: [v, x.name], label: i ? "Middle author only" : "Led" })), symbol: "circle", symbolSize: 16, lineStyle: { width: 5, color: c, opacity: 0.55 },
          itemStyle: { color: c }, label: { show: true, position: "top", color: T.text, fontSize: 12, fontWeight: 600, formatter: (p) => `${p.data.label === "Led" ? "led" : "middle only"}  ${p.value[0].toFixed(2)}×` } }; })] };
  }
  if (type === "small-area") { // small multiples
    const n = spec.series.length;
    return { tooltip: { trigger: "axis" },
      grid: spec.series.map((_, i) => ({ left: 8, right: 14, top: `${(100 / n) * i + 7}%`, height: `${100 / n - 14}%`, containLabel: true })),
      xAxis: spec.series.map((_, i) => ({ type: "category", gridIndex: i, data: spec.x, boundaryGap: false, axisLabel: { show: i === n - 1, fontSize: 11 }, axisTick: { show: false } })),
      yAxis: spec.series.map((_, i) => ({ type: "value", gridIndex: i, min: 60, max: 100, splitNumber: 2, axisLabel: { formatter: "{value}%", fontSize: 10 } })),
      graphic: spec.series.map((s, i) => ({ type: "text", right: 16, top: `${(100 / n) * i + 8}%`, style: { text: s.name, fill: colorOf(s.color), font: "700 14px sans-serif" } })),
      series: spec.series.map((s, i) => { const c = colorOf(s.color); return { name: s.name, type: "line", xAxisIndex: i, yAxisIndex: i, smooth: 0.3, symbol: "none", data: s.data, lineStyle: { width: 3, color: c }, itemStyle: { color: c }, areaStyle: { color: gradient(c, 0.35) } }; }) };
  }
  if (type === "donut") {
    const base = colorOf(spec.series[0].color);
    return { tooltip: { trigger: "item" }, series: [{ type: "pie", radius: ["38%", "70%"], center: ["50%", "52%"], itemStyle: { borderColor: T.stage, borderWidth: 2, borderRadius: 4 },
      label: { color: T.muted, fontSize: 11, width: 130, overflow: "break" }, labelLine: { length: 8, length2: 6 },
      data: spec.categories.map((c, i) => ({ name: c, value: spec.series[0].data[i], itemStyle: { color: light(base, i * 0.09) } })) }] };
  }
  if (type === "sankey") {
    return { tooltip: { trigger: "item" }, series: [{ type: "sankey", left: 8, right: 250, top: 8, bottom: 8, nodeGap: 10, nodeWidth: 14, draggable: false,
      emphasis: { focus: "adjacency" }, lineStyle: { curveness: 0.5, opacity: 0.4 }, label: { color: T.text, fontSize: 11, width: 240, overflow: "truncate" },
      data: spec.nodes.map((n) => ({ name: n.name, itemStyle: { color: colorOf(n.color) } })),
      links: spec.links.map((l) => ({ source: l.source, target: l.target, value: l.value, lineStyle: { color: colorOf(l.color) } })) }] };
  }
  if (type === "network") {
    const maxS = Math.max(...spec.nodes.map((n) => n.size)), maxV = Math.max(...spec.links.map((l) => l.value));
    const w = spec.w || 540, h = 300;
    const pos = { DU: [0.5, 0.2], JNU: [0.14, 0.62], UoH: [0.86, 0.62] };
    return { tooltip: { trigger: "item" }, series: [{ type: "graph", layout: "none", roam: false, left: 0, top: 0, right: 0, bottom: 0,
      edgeLabel: { show: true, formatter: (p) => `${p.data.value} shared`, color: T.text, fontSize: 12 },
      data: spec.nodes.map((n) => ({ name: n.name, x: pos[n.name][0] * w, y: pos[n.name][1] * h, symbolSize: 34 + (n.size / maxS) * 46, itemStyle: { color: colorOf(n.color) },
        label: { show: true, position: "bottom", distance: 6, formatter: `${n.name}\n${n.size.toLocaleString("en-IN")} papers`, color: T.text, fontWeight: 600, fontSize: 12, lineHeight: 16 } })),
      links: spec.links.map((l) => ({ ...l, lineStyle: { width: 2 + (l.value / maxV) * 16, color: colorOf("Shared"), opacity: 0.55 } })) }] };
  }
  if (type === "treemap") {
    return { tooltip: { formatter: (p) => `${esc(p.name)}: ${p.value ? p.value.toLocaleString("en-IN") : ""}` }, series: [{ type: "treemap", roam: false, nodeClick: false, breadcrumb: { show: false }, left: 0, right: 0, top: 0, bottom: 0,
      label: { fontSize: 11, color: "#fff", overflow: "truncate" }, upperLabel: { show: true, height: 22, color: "#fff", fontWeight: 700 }, itemStyle: { borderColor: T.stage, borderWidth: 2, gapWidth: 2 },
      data: spec.tree.map((t) => ({ name: t.name, itemStyle: { color: colorOf(t.color) }, children: t.children.map((c, i) => ({ ...c, itemStyle: { color: light(colorOf(t.color), i * 0.07) } })) })) }] };
  }
  if (type === "path") { // connected scatter: each year is a point, arrows show direction
    const all = spec.paths.flatMap((p) => p.points); const hi = Math.max(...all.flatMap((p) => [p[0], p[1]])) * 1.05;
    return { tooltip: { formatter: (p) => `${esc(p.seriesName)} ${p.data[2]}<br>given ${p.data[0].toLocaleString("en-IN")}<br>received ${p.data[1].toLocaleString("en-IN")}` }, legend: { top: 0, right: 0 },
      grid: { left: 8, right: 20, top: 30, bottom: 34, containLabel: true },
      xAxis: { type: "value", name: spec.xname, nameLocation: "middle", nameGap: 26, nameTextStyle: txt(), max: hi, axisLabel: { formatter: (v) => `${v / 1000}k` } },
      yAxis: { type: "value", name: spec.yname, nameTextStyle: { ...txt(), align: "left" }, max: hi, axisLabel: { formatter: (v) => `${v / 1000}k` } },
      series: [{ type: "line", name: "even", data: [[0, 0], [hi, hi]], symbol: "none", lineStyle: { color: T.muted, type: "dashed", width: 1 }, tooltip: { show: false }, silent: true },
        ...spec.paths.map((p) => { const c = colorOf(p.color); return { name: p.name, type: "line", data: p.points, symbolSize: 7, itemStyle: { color: c }, lineStyle: { width: 2.5, color: c },
          endLabel: { show: true, formatter: p.name, color: c, fontWeight: 700 }, label: { show: false } }; })] };
  }
  return {};
}

// Draw a network diagram using DOM elements (SVG) instead of ECharts
function drawNetwork(el, spec) {
  el.classList.add("ins-dom");
  const W = 540, H = 300, pos = { DU: [270, 62], JNU: [95, 190], UoH: [445, 190] };
  const maxS = Math.max(...spec.nodes.map((n) => n.size)), maxV = Math.max(...spec.links.map((l) => l.value));
  const r = (n) => 22 + (n.size / maxS) * 26;
  const lines = spec.links.map((l) => {
    const [x1, y1] = pos[l.source], [x2, y2] = pos[l.target], mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
    return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${colorOf("Shared")}" stroke-opacity=".55" stroke-width="${2 + (l.value / maxV) * 16}" stroke-linecap="round"/>
      <text x="${mx}" y="${my - 12 + (l.target === "UoH" && l.source === "JNU" ? 26 : 0)}" text-anchor="middle" class="ins-svgt" font-size="13" font-weight="600">${l.value.toLocaleString("en-IN")} shared</text>`;
  }).join("");
  const nodes = spec.nodes.map((n) => { const [x, y] = pos[n.name];
    return `<circle cx="${x}" cy="${y}" r="${r(n)}" fill="${colorOf(n.color)}"/>
      <text x="${x}" y="${y + r(n) + 18}" text-anchor="middle" class="ins-svgt" font-size="13" font-weight="700">${n.name}</text>
      <text x="${x}" y="${y + r(n) + 34}" text-anchor="middle" class="ins-svgt" font-size="11.5" opacity=".7">${n.size.toLocaleString("en-IN")} papers</text>`; }).join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Papers shared between universities">${lines}${nodes}</svg>`;
}

// Main path analysis: each path as a timeline, oldest paper first (each paper cites the one before it)
function drawMainPath(el, spec) {
  el.classList.add("ins-dom");
  const c = colorOf("DU");
  el.innerHTML = `<div class="ins-paths">${spec.paths.map((p) => `
    <div class="ins-path"><div class="ins-path-head" style="color:${c}">${esc(p.name)} <span>${p.items.length} papers</span></div>
      <ol>${p.items.map((it) => `<li style="--c:${c}"><span class="y">${it.year}</span>
        <span class="t">${it.doi ? `<a href="https://doi.org/${esc(it.doi)}" target="_blank" rel="noopener">${esc(it.title)}</a>` : esc(it.title)}
          <small>${esc(it.field)} · ${it.citations.toLocaleString("en-IN")} citations · cited by ${it.du_citations} DU papers</small></span></li>`).join("")}</ol></div>`).join("")}</div>`;
}

function drawChart(el, spec) {
  if (spec.type === "mainpath") { drawMainPath(el, spec); return null; }
  if (spec.type === "network") { drawNetwork(el, spec); return null; }
  if (spec.type === "waffle" || spec.type === "pictogram") { drawCells(el, spec); return null; }
  spec.w = el.clientWidth;
  const o = option(spec);
  if (location.search.includes("static")) o.animation = false;
  return chart(el, o);
}

function tileBody(it, data) {
  const spec = data[it.key];
  const col = colorOf(spec.stat.color);
  return `
    <div class="ins-top">
      <span class="ins-ico" style="color:${col};background:${col}1f">${icon(it.key)}</span>
      <div class="ins-stat"><b style="color:${col}">${esc(spec.stat.value)}</b><span>${esc(spec.stat.label)}</span></div>
    </div>
    <p class="ins-cap">${esc(spec.caption)}${spec.unit ? ` · ${esc(spec.unit)}` : ""}</p>
    <div class="ins-chart" data-key="${it.key}"></div>`;
}

export default async function insights(el) {
  const data = await load("insights");
  let mode = "tiles";
  try { mode = localStorage.getItem("ins-mode") || "tiles"; } catch { /* storage may be blocked */ }
  const $ = mount(el, `
    <div class="ins-bar"><div class="seg" id="ins-mode">
      <button data-m="tiles" title="Tiles" aria-label="Tiles view"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="3" y="3" width="7.500" height="7.500" rx="1.500"/><rect x="13.500" y="3" width="7.500" height="7.500" rx="1.500"/><rect x="3" y="13.500" width="7.500" height="7.500" rx="1.500"/><rect x="13.500" y="13.500" width="7.500" height="7.500" rx="1.500"/></svg></button><button data-m="list" title="List" aria-label="List view"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.500" cy="6" r=".8"/><circle cx="3.500" cy="12" r=".8"/><circle cx="3.500" cy="18" r=".8"/></svg></button></div></div>
    <div id="ins-root"></div>`);
  const root = $("#ins-root");
  const drawn = new Set();
  const plot = (host, key) => { const c = host.querySelector(".ins-chart"); if (c && !drawn.has(c)) { drawn.add(c); drawChart(c, data[key]); } };

  // findings whose chart data is missing from insights.json (older data files) are left out
  const main = INSIGHTS.filter((it) => data[it.key]);
  const du = DU_INSIGHTS.filter((it) => data[it.key]);
  const duHead = du.length ? `<section class="ins-section"><h2>${esc(DU_SECTION.title)}</h2><p>${esc(DU_SECTION.intro)}</p>
    <p class="ins-refs">${DU_SECTION.refs.map(([t, u]) => `<a href="${u}" target="_blank" rel="noopener">${esc(t)}</a>`).join("<br>")}</p></section>` : "";
  const tiles = (list) => `<div class="ins-tiles">${list.map((it) => `
        <article class="ins-tile${it.key === "du_mainpath" ? " ins-wide" : ""}" data-key="${it.key}">
          <h3>${esc(it.title)}</h3>
          ${tileBody(it, data)}
          <p class="ins-body">${esc(it.body)}</p>
          <a class="ins-see" href="#${it.see[0]}">Related page: ${esc(it.see[1])} →</a>
        </article>`).join("")}</div>`;
  const items = (list) => `<div class="ins-list">${list.map((it) => `
        <article class="ins-item" data-key="${it.key}">
          <h3 tabindex="0" role="button" aria-expanded="false">${esc(it.title)}</h3>
          <p>${esc(it.body)}</p>
          <a class="ins-see" href="#${it.see[0]}">Related page: ${esc(it.see[1])} →</a>
          <div class="ins-expand" hidden><div class="ins-tile">${tileBody(it, data)}</div></div>
        </article>`).join("")}</div>`;

  const render = () => {
    $("#ins-mode").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.m === mode));
    drawn.clear();
    if (mode === "tiles") {
      root.innerHTML = tiles(main) + (du.length ? duHead + tiles(du) : "");
      root.querySelectorAll(".ins-tile").forEach((t) => plot(t, t.dataset.key));
    } else {
      root.innerHTML = items(main) + (du.length ? duHead + items(du) : "");
    }
  };
  const toggle = (item) => {
    const box = item.querySelector(".ins-expand");
    const open = box.hidden;
    box.hidden = !open;
    item.classList.toggle("open", open);
    item.querySelector("h3").setAttribute("aria-expanded", String(open));
    if (open) plot(item, item.dataset.key);
  };
  root.addEventListener("click", (e) => { const h = e.target.closest(".ins-item h3"); if (h) toggle(h.parentElement); });
  root.addEventListener("keydown", (e) => { if ((e.key === "Enter" || e.key === " ") && e.target.matches(".ins-item h3")) { e.preventDefault(); toggle(e.target.parentElement); } });
  $("#ins-mode").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b || b.dataset.m === mode) return;
    mode = b.dataset.m;
    try { localStorage.setItem("ins-mode", mode); } catch { /* ignore */ }
    render();
  });
  render();
}
