import { esc, fmt, load, mount } from "../lib.js";

const GLOSSARY = [
  ["Citation network", "Each dot is a paper. An arrow from A to B means paper A cites paper B. Only papers in our dataset are included."],
  ["PageRank", "How central a paper is in the citation network: being cited by papers that are themselves well cited counts more. Shown as a multiple of the average paper."],
  ["Cited here", "How many papers in our dataset cite this paper (its in-degree)."],
  ["Co-authorship network", "Each dot is an author. A line means two authors wrote at least one paper together; thicker lines mean more papers."],
  ["Co-authors", "How many different people an author has written papers with (their degree)."],
  ["Bridge score", "How often an author sits on the shortest path between two other authors. High scores mark people who connect separate groups."],
  ["Community", "A group of authors who mostly write with each other, found automatically (Louvain method)."],
  ["Impact factor", "The OpenAlex 2-year mean citedness of a paper's journal: citations in the last full year to the journal's items from the two years before, divided by the number of those items. One current value per journal."],
  ["Impact ratio", "Citations an institution receives from other Indian institutions, divided by the citations it gives them. Above 1 means it is cited more than it cites."],
];

export default async function about(el) {
  const o = await load("overview");
  const f = o.funnel;
  const t = o.totals;
  const steps = [
    ["1", "Download", fmt(f[0].papers), "papers",
      `Every article and conference paper from ${o.years[0]}–${o.years[1]} with an author at JNU, UoH or DU, in ${o.fields_included.length} science and engineering fields.`],
    ["2", "Check", fmt(f[1].papers), "papers",
      "Kept only real journals and conferences, removed duplicates, and kept an author only if they wrote the institution in their affiliation."],
    ["3", "Clean", fmt(f[2].papers), "papers",
      "Removed papers in medical or non-science journals, retracted papers, errata and abstract-only venues. Tidied author names."],
    ["4", "Enrich", fmt(t.citation_edges), "citation links",
      "Added journal quartiles and conference ranks, and built the citation and co-authorship networks from the papers."],
  ];

  mount(el, `
    <div class="card"><h3>How the data was made</h3><p class="card-sub">Four steps, from the raw download to what this dashboard shows.</p>
      <div class="steps">${steps.map(([n, title, value, unit, text], i) => `${i ? `
        <div class="step-arrow" aria-hidden="true">${i < f.length ? `<span>−${fmt(f[i - 1].papers - f[i].papers)}</span>` : ""}</div>` : ""}
        <div class="step">
          <div class="step-top"><span class="step-n">${n}</span><span class="step-title">${title}</span></div>
          <div class="step-value">${value} <span>${unit}</span></div>
          <p>${esc(text)}</p>
        </div>`).join("")}</div>
    </div>

    <div class="card mt"><h3>What the network terms mean</h3><p class="card-sub">Used on the network and author pages.</p>
      <dl class="glossary">${GLOSSARY.map(([term, text]) => `<dt>${esc(term)}</dt><dd>${esc(text)}</dd>`).join("")}</dl></div>

    <p class="note mt">Sources: OpenAlex (papers, citations, journal impact factor), SCImago Journal Rank 2016-2025, CORE conference ranking 2026.</p>`);
}
