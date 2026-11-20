"""Insights on the University of Delhi (DU) citation network, for the Insights page.

Reads dashboard/public/data/citation.json (written by `python -m collector dashboard-data`) and returns chart
entries for insights.json under keys starting with "du_". The written findings are in dashboard/src/views/insights.js.

Methods follow citation network analysis (CNA) as set out by McLaren & Bruner (2022, International Review of Sport
and Exercise Psychology, doi:10.1080/1750984X.2021.1989705) and the direct-citation mapping of research fields by
Healy, Hammer & McIlveen (2022, Studies in Higher Education, doi:10.1080/03075079.2020.1804851):

    structure        nodes, edges, density, connected components, isolated papers
    prominence       in-degree (citations from other DU papers) and how concentrated it is
    integration      share of citations that stay inside the citing paper's field (Healy et al.: are fields siloed?)
    main path        search path count (SPC) main path analysis (Hummon & Doreian 1989), the backbone of knowledge flow
    communities      Louvain modularity clusters of the citation graph and how well they match OpenAlex fields

The DU network is every paper with a DU author (shared papers included) and every citation between two such papers.
Can be run on its own, without the raw dataset: `python -m collector du-insights` adds these entries to insights.json.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd

DU_BIT, JNU_BIT, UOH_BIT = 1, 2, 4  # citation.json node mask: DU 1, JNU 2, UoH 4
PHYSICS = "Physics and Astronomy"


def clean_title(title: str) -> str:
    """OpenAlex titles sometimes carry inline LaTeX ($$...$$) next to its plain-text rendering: keep the plain text."""
    return re.sub(r"\s+", " ", re.sub(r"\$\$.*?\$\$", "", title)).replace("( ", "(").replace(" )", ")").strip()


def _main_path(dag: nx.DiGraph) -> list[int]:
    """Key-route main path: start at the edge with the highest search path count, extend both ways by the best edge."""
    if dag.number_of_edges() == 0:
        return []
    order = list(nx.topological_sort(dag))
    forward = {v: 1 if dag.in_degree(v) == 0 else 0 for v in dag}   # paths from any source to v
    for v in order:
        for w in dag.successors(v):
            forward[w] += forward[v]
    backward = {v: 1 if dag.out_degree(v) == 0 else 0 for v in dag}  # paths from v to any sink
    for v in reversed(order):
        for w in dag.successors(v):
            backward[v] += backward[w]
    spc = {(u, v): forward[u] * backward[v] for u, v in dag.edges()}
    u, v = max(spc, key=spc.get)
    path = [u, v]
    while dag.out_degree(path[-1]):
        path.append(max(dag.successors(path[-1]), key=lambda w: spc[(path[-1], w)]))
    while dag.in_degree(path[0]):
        path.insert(0, max(dag.predecessors(path[0]), key=lambda w: spc[(w, path[0])]))
    return path


def du_citation_insights(cit: dict[str, Any]) -> dict[str, Any]:
    n, fields = cit["nodes"], cit["fields"]
    mask, field, year = n["mask"], n["field"], n["year"]
    pairs = list(zip(cit["edges"][0::2], cit["edges"][1::2]))  # (citing, cited)
    N = len(mask)
    du = [i for i in range(N) if mask[i] & DU_BIT]
    is_du = lambda i: mask[i] & DU_BIT
    g = nx.DiGraph()
    g.add_nodes_from(du)
    g.add_edges_from((s, t) for s, t in pairs if is_du(s) and is_du(t))
    out: dict[str, Any] = {}
    r1 = lambda v: round(float(v), 1) + 0.0  # + 0.0 turns -0.0 into 0.0

    # ---- structure: how connected is DU's own literature
    comps = sorted((len(c) for c in nx.weakly_connected_components(g)), reverse=True)
    isolated = sum(1 for v in g if g.degree(v) == 0)
    linked_small = len(du) - isolated - comps[0] - (comps[1] if len(comps) > 1 else 0)
    lag = [year[s] - year[t] for s, t in g.edges()]
    out["du_structure"] = {
        "type": "bar", "horizontal": True, "unit": "DU papers",
        "categories": ["Largest connected group", "Second largest group", f"{len(comps) - 2 - isolated:,} smaller groups", "No citation link to another DU paper"],
        "series": [{"name": "DU papers", "color": "DU", "data": [comps[0], comps[1], linked_small, isolated]}],
        "caption": "DU papers by the connected group of the DU citation network they fall in (citations between DU papers, either direction)",
        "stat": {"value": f"{r1(isolated / len(du) * 100)}%", "label": "of DU papers neither cite nor are cited by another DU paper", "color": "DU"},
        "facts": {"papers": len(du), "citations": g.number_of_edges(), "density": float(f"{nx.density(g):.2e}"),
                  "components": len(comps), "largest_share": r1(comps[0] / len(du) * 100),
                  "median_lag_years": float(np.median(lag)) if lag else None,
                  "mean_refs_per_paper": round(g.number_of_edges() / len(du), 2)},
    }

    # ---- whose work DU builds on: own papers vs JNU / UoH papers, against each university's share of the dataset
    own_share, size_share = [], []
    for bit in (DU_BIT, JNU_BIT, UOH_BIT):
        refs = [t for s, t in pairs if mask[s] & bit]
        own_share.append(r1(sum(1 for t in refs if mask[t] & bit) / len(refs) * 100) if refs else 0)
        size_share.append(r1(sum(1 for i in range(N) if mask[i] & bit) / N * 100))
    out["du_selfcite"] = {
        "type": "bar", "horizontal": True, "unit": "%", "categories": ["DU", "JNU", "UoH"],
        "series": [{"name": "Share of the dataset's papers that are the university's own", "color": "All", "tint": 0.55, "data": size_share},
                   {"name": "Share of its citations (within the dataset) that go to its own papers", "color": "All", "data": own_share}],
        "caption": "Citations inside the dataset: how much each university cites its own papers, against how much of the dataset it is",
        "stat": {"value": f"{own_share[0]}%", "label": f"of DU's citations to papers in the dataset go to DU papers (DU is {size_share[0]}% of the papers)", "color": "DU"},
        "facts": {"du_to_others": sum(1 for s, t in pairs if is_du(s) and not is_du(t)),
                  "others_to_du": sum(1 for s, t in pairs if is_du(t) and not is_du(s))},
    }

    # ---- prominence: how concentrated citations from other DU papers are
    indeg = np.array([g.in_degree(v) for v in du])
    srt = np.sort(indeg)[::-1]
    total = srt.sum()
    cut = lambda q: int(round(len(srt) * q))
    shares = [srt[:cut(0.01)].sum(), srt[cut(0.01):cut(0.10)].sum(), srt[cut(0.10):cut(0.50)].sum(), srt[cut(0.50):].sum()]
    asc = np.sort(indeg)
    gini = float((2 * np.arange(1, len(asc) + 1) - len(asc) - 1).dot(asc) / (len(asc) * asc.sum())) if total else 0.0
    cites = np.array([n["citations"][v] for v in du])
    spearman = float(pd.Series(indeg).rank().corr(pd.Series(cites).rank()))  # Spearman: Pearson on tie-averaged ranks
    top100 = np.argsort(-cites)[:100]
    out["du_concentration"] = {
        "type": "bar", "horizontal": True, "unit": "% of citations from other DU papers",
        "categories": ["Top 1% of DU papers", "Next 9%", "Next 40%", "Bottom 50%"],
        "series": [{"name": "Share of citations received from DU papers", "color": "DU", "data": [r1(x / total * 100) for x in shares]}],
        "caption": "Share of all DU-to-DU citations received by DU papers, ranked by those citations",
        "stat": {"value": f"{r1((shares[0] + shares[1]) / total * 100)}%", "label": "of DU-to-DU citations go to the top 10% of DU papers", "color": "DU"},
        "facts": {"gini": round(gini, 2), "never_cited_by_du": r1((indeg == 0).mean() * 100), "spearman_vs_all_citations": round(spearman, 2),
                  "top100_never_cited_by_du": int((indeg[top100] == 0).sum())},
    }

    # ---- integration of fields (Healy et al.): share of each field's citations that stay inside the field
    pair_fields = Counter((field[s], field[t]) for s, t in g.edges())
    rows = []
    for f in range(len(fields)):
        given = sum(v for (a, _), v in pair_fields.items() if a == f)
        if given >= 100:  # fields with too few DU-to-DU citations are left out
            rows.append((fields[f], r1(pair_fields.get((f, f), 0) / given * 100), given))
    rows.sort(key=lambda x: -x[1])
    within = sum(v for (a, b), v in pair_fields.items() if a == b) / max(1, g.number_of_edges())
    phys = fields.index(PHYSICS) if PHYSICS in fields else -1
    phys_given = sum(v for (a, _), v in pair_fields.items() if a == phys)
    out["du_fields"] = {
        "type": "bar", "horizontal": True, "unit": "% of the field's citations to DU papers that stay in the same field",
        "categories": [r[0] for r in rows], "series": [{"name": "Citations within the field", "color": "DU", "data": [r[1] for r in rows]}],
        "caption": "Each field's citations to other DU papers: share going to DU papers of the same OpenAlex field (fields with 100+ such citations)",
        "stat": {"value": f"{r1(within * 100)}%", "label": "of DU-to-DU citations stay inside one field", "color": "DU"},
        "facts": {"physics_papers_share": r1(sum(1 for v in du if field[v] == phys) / len(du) * 100),
                  "physics_citations_share": r1(phys_given / max(1, g.number_of_edges()) * 100),
                  "rows": [{"field": f, "within": w, "citations": c} for f, w, c in rows]},
    }

    # ---- main path analysis: knowledge flows from the cited paper to the citing one
    dag = nx.DiGraph()
    dag.add_nodes_from(du)
    dag.add_edges_from((t, s) for s, t in g.edges())
    for comp in nx.strongly_connected_components(dag):  # mutual citations (same-year papers) would make a cycle
        if len(comp) > 1:
            dag.remove_edges_from([(u, v) for u in comp for v in list(dag.successors(u)) if v in comp])

    def item(i: int) -> dict[str, Any]:
        return {"year": year[i], "title": clean_title(n["title"][i]), "field": fields[field[i]], "citations": n["citations"][i],
                "doi": n["doi"][i], "du_citations": g.in_degree(i)}

    whole = _main_path(dag)
    rest = _main_path(dag.subgraph([v for v in dag if fields[field[v]] != PHYSICS]).copy())
    out["du_mainpath"] = {
        "type": "mainpath", "unit": "",
        "paths": [{"name": "Whole DU network", "items": [item(i) for i in whole]},
                  {"name": "Without physics and astronomy", "items": [item(i) for i in rest]}],
        "caption": "Main paths of the DU citation network (search path count, key-route). Oldest paper first; each paper cites the one above it",
        "stat": {"value": f"{len(whole)} papers, {year[whole[0]]}–{year[whole[-1]]}" if whole else "–",
                 "label": "on the main path of the whole DU network, all in one line of mathematical physics", "color": "DU"},
    }

    # ---- communities: Louvain on the undirected citation graph (papers with at least one link)
    und = g.to_undirected()
    und.remove_nodes_from([v for v in list(und) if und.degree(v) == 0])
    comms = sorted(nx.community.louvain_communities(und, seed=16), key=len, reverse=True)
    modularity = nx.community.modularity(und, comms)
    top = []
    for c in comms[:10]:
        f, k = Counter(fields[field[v]] for v in c).most_common(1)[0]
        hub = max(c, key=lambda v: g.in_degree(v))
        top.append({"size": len(c), "field": f, "purity": r1(k / len(c) * 100), "median_year": int(np.median([year[v] for v in c])),
                    "hub": n["title"][hub][:120]})
    purity = sum(Counter(field[v] for v in c).most_common(1)[0][1] for c in comms) / max(1, und.number_of_nodes())
    out["du_communities"] = {
        "type": "bar", "horizontal": True, "unit": "papers in the community",
        "categories": [f"{c['field']} ({c['purity'] if c['purity'] > 99 else round(c['purity'])}% of papers)" for c in top],
        "series": [{"name": "Papers", "color": "DU", "data": [c["size"] for c in top]}],
        "caption": "Ten largest Louvain communities of the DU citation network, named by their most common OpenAlex field (share of the community's papers in that field)",
        "stat": {"value": f"{len(comms):,}", "label": f"communities, modularity {modularity:.2f}: research groups cite mostly within themselves", "color": "DU"},
        "facts": {"communities": len(comms), "modularity": round(modularity, 3), "papers_linked": und.number_of_nodes(),
                  "field_purity": r1(purity * 100), "top": top},
    }
    return out


def add_to_insights(data_dir: Path) -> None:
    """Add the DU entries to an existing insights.json (for use without the raw dataset)."""
    cit = json.loads((data_dir / "citation.json").read_text(encoding="utf-8"))
    path = data_dir / "insights.json"
    ins = json.loads(path.read_text(encoding="utf-8"))
    ins.update(du_citation_insights(cit))
    path.write_text(json.dumps(ins, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  insights.json      {path.stat().st_size / 1e6:6.2f} MB (DU citation network entries added)")
