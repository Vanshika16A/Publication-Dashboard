"""Precompute everything the dashboard shows: `python -m collector dashboard-data`.

Reads the cleaned dataset (output/) and the network files (output/networks/) and writes small
JSON files into dashboard/public/data/. All heavy work (PageRank, betweenness, Louvain
communities, statistics) happens here, so the browser only draws.

Files written:
    overview.json      totals, per-institution summary, pipeline funnel, progress checklist
    stats.json         trends, quartiles, CORE ranks, fields, top journals, most-cited papers
    authors.json       one row per (institution, author): papers, citations, h-index, network metrics
    citation.json      citation graph: every paper (node) and every citation inside the dataset (edge)
    coauthor.json      co-authorship graph: authors (nodes), co-author pairs (edges), communities
    connections.json   Indian partner institutions, citation flow in / out per year
    impact.json        journal impact factor (OpenAlex 2-year mean citedness): Q1 papers above IF 5 / 10, top 10 papers per faculty
    stats_by_authors.json  stats.json again for papers with 1-5, 6-20, 21-99 and 100+ authors, keyed by group (Publications filter)
    insights.json      chart data for the Insights page (written by insights_data.py, after all of the above)
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd

from .build import name_key
from .collect import Run, read_jsonl
from .config import CONFIG, END_YEAR, GROUP, INSTITUTIONS, OUTPUT_DIR, ROOT, START_YEAR

DASHBOARD_DATA = ROOT / "dashboard" / "public" / "data"
SHORT = {"University of Delhi": "DU", "Jawaharlal Nehru University": "JNU", "University of Hyderabad": "UoH"}
ORDER = ["University of Delhi", "Jawaharlal Nehru University", "University of Hyderabad"]
BIT = {name: 1 << i for i, name in enumerate(ORDER)}  # institution bit mask: DU 1, JNU 2, UoH 4
YEARS = list(range(START_YEAR, END_YEAR + 1))


def write(name: str, data: Any, dest: Path | None = None) -> None:
    path = (dest or DASHBOARD_DATA) / name
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  {name:18s} {path.stat().st_size / 1e6:6.2f} MB")


def r(value: float, digits: int = 4) -> float:
    return round(float(value), digits) if value == value else 0.0  # NaN -> 0


# ---------------------------------------------------------------- loading

def load(out_dir: Path) -> dict[str, Any]:
    ext = pd.read_csv(out_dir / f"group{GROUP}_data_extended.csv", dtype=str, keep_default_na=False)
    for column in ("year", "citations", "n_authors"):
        ext[column] = ext[column].astype(int)
    ext["author_key"] = [a if a else name_key(n) for a, n in zip(ext["openalex_author_id"], ext["author"])]
    net = out_dir / "networks"
    if not (net / "citation_network.csv").exists():
        raise SystemExit("network files not found: run `python -m collector networks` first")
    return {
        "ext": ext,
        "authors": pd.read_csv(out_dir / "authors.csv", dtype=str, keep_default_na=False),
        "cit": pd.read_csv(net / "citation_network.csv", dtype=str, keep_default_na=False),
        "coa": pd.read_csv(net / "authorship_network.csv", dtype=str, keep_default_na=False),
        "conn": pd.read_csv(net / "indian_connections.csv", dtype=str, keep_default_na=False),
        "flow": pd.read_csv(net / "citation_flow.csv", dtype=str, keep_default_na=False),
        # per-paper citation flow (written by `networks` since the team-size filter); needed only for that filter
        "flow_by_paper": pd.read_csv(net / "citation_flow_by_paper.csv", dtype=str, keep_default_na=False)
        if (net / "citation_flow_by_paper.csv").exists() else None,
    }


def paper_table(ext: pd.DataFrame) -> pd.DataFrame:
    """One row per paper, with the set of assigned institutions it belongs to."""
    insts = ext.groupby("openalex_work_id")["institution"].agg(lambda s: sorted(set(s), key=ORDER.index))
    papers = ext.drop_duplicates("openalex_work_id").set_index("openalex_work_id")
    papers["insts"] = insts
    papers["mask"] = papers["insts"].map(lambda names: sum(BIT[n] for n in names))
    return papers


# ---------------------------------------------------------------- stats

def per_inst_papers(ext: pd.DataFrame) -> pd.DataFrame:
    return ext.drop_duplicates(["institution", "openalex_work_id"])


def stats(ext: pd.DataFrame, papers: pd.DataFrame) -> dict[str, Any]:
    pi = per_inst_papers(ext)
    scopes = {SHORT[name]: pi[pi["institution"] == name] for name in ORDER}
    scopes["All"] = papers.reset_index()  # every paper once (shared papers not double counted)
    out: dict[str, Any] = {"years": YEARS, "scopes": list(scopes)}

    out["trend"] = {k: [int((v["year"] == y).sum()) for y in YEARS] for k, v in scopes.items()}
    out["citations_by_year"] = {k: [int(v.loc[v["year"] == y, "citations"].sum()) for y in YEARS]
                                for k, v in scopes.items()}

    quartiles = ["Q1", "Q2", "Q3", "Q4"]
    out["quartiles"] = {}
    out["q1_share_by_year"] = {}
    for k, v in scopes.items():
        journal = v[v["type"] == "journal"]
        counts = {q: int((journal["quartile"] == q).sum()) for q in quartiles}
        counts["Not ranked"] = int((journal["quartile"] == "").sum())
        out["quartiles"][k] = counts
        shares = []
        for y in YEARS:
            ranked = journal[(journal["year"] == y) & (journal["quartile"] != "")]
            shares.append(r((ranked["quartile"] == "Q1").mean() * 100, 1) if len(ranked) else None)
        out["q1_share_by_year"][k] = shares

    ranks = ["A*", "A", "B", "C"]
    out["conference"] = {}
    for k, v in scopes.items():
        conf = v[v["type"] == "conference"]
        counts = {rank: int((conf["quartile"] == rank).sum()) for rank in ranks}
        counts["SCImago series"] = int(conf["quartile"].isin(quartiles).sum())
        counts["Not ranked"] = int((conf["quartile"] == "").sum())
        out["conference"][k] = counts

    out["fields"] = {k: v["primary_field"].value_counts().to_dict() for k, v in scopes.items()}
    out["subfields"] = {k: v["primary_subfield"].value_counts().head(15).to_dict() for k, v in scopes.items()}

    out["top_journals"] = {}
    for k, v in scopes.items():
        journal = v[(v["type"] == "journal") & (v["journal_name"] != "")]
        rows = []
        for name, group in journal.groupby("journal_name"):
            q = group["quartile"].replace("", pd.NA).dropna()
            sjr = pd.to_numeric(group["sjr"], errors="coerce").dropna()
            rows.append({"name": name, "papers": len(group), "citations": int(group["citations"].sum()),
                         "quartile": q.mode().iloc[0] if len(q) else "", "sjr": r(sjr.median(), 2) if len(sjr) else None})
        out["top_journals"][k] = sorted(rows, key=lambda x: (-x["papers"], x["name"]))[:10]

    def paper(p: Any) -> dict[str, Any]:
        return {"title": p.title, "journal": p.journal_name, "year": int(p.year), "citations": int(p.citations),
                "doi": p.doi, "insts": [SHORT[n] for n in p.insts], "field": p.primary_field, "type": p.type,
                "n_authors": int(p.n_authors)}

    ranked = papers.sort_values("citations", ascending=False)
    out["most_cited"] = {"All": [paper(p) for p in ranked.head(25).itertuples()]}
    for name in ORDER:
        mine = ranked[ranked["insts"].map(lambda names: name in names)]
        out["most_cited"][SHORT[name]] = [paper(p) for p in mine.head(25).itertuples()]
    return out


# ---------------------------------------------------------------- citation network

def citation_graph(data: dict[str, Any], papers: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    edges = data["cit"].drop_duplicates(["source_openalex_id", "target_openalex_id"])
    ids = list(papers.index)
    index = {work_id: i for i, work_id in enumerate(ids)}
    graph = nx.DiGraph()
    graph.add_nodes_from(range(len(ids)))
    pairs = [(index[s], index[t]) for s, t in zip(edges["source_openalex_id"], edges["target_openalex_id"])
             if s in index and t in index and s != t]
    graph.add_edges_from(pairs)
    print(f"  citation graph: {graph.number_of_nodes()} papers, {graph.number_of_edges()} citations")
    pagerank = nx.pagerank(graph, alpha=0.85)
    indeg = dict(graph.in_degree())
    outdeg = dict(graph.out_degree())

    fields = sorted(papers["primary_field"].unique())
    journals = sorted(papers["journal_name"].unique())
    field_index = {f: i for i, f in enumerate(fields)}
    journal_index = {j: i for i, j in enumerate(journals)}
    nodes = {
        "id": ids,
        "title": [t[:160] for t in papers["title"]],
        "year": papers["year"].astype(int).tolist(),
        "mask": papers["mask"].astype(int).tolist(),
        "field": [field_index[f] for f in papers["primary_field"]],
        "journal": [journal_index[j] for j in papers["journal_name"]],
        "citations": papers["citations"].astype(int).tolist(),
        "doi": [d.replace("https://doi.org/", "") for d in papers["doi"]],
        "indeg": [indeg[i] for i in range(len(ids))],
        "outdeg": [outdeg[i] for i in range(len(ids))],
        "pagerank": [r(pagerank[i] * len(ids), 3) for i in range(len(ids))],  # 1.0 = average paper
    }
    flat = [v for pair in pairs for v in pair]
    indeg_hist = Counter(indeg.values())
    summary = {
        "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(),
        "papers_with_links": sum(1 for i in range(len(ids)) if indeg[i] or outdeg[i]),
        "indeg_hist": sorted(([k, v] for k, v in indeg_hist.items()), key=lambda kv: kv[0]),
        "cross_institute_edges": int((data["cit"]["cross_institute"] == "True").sum()),
    }
    return {"fields": fields, "journals": journals, "nodes": nodes, "edges": flat, "summary": summary}, \
        {"pagerank": pagerank, "ids": ids}


# ---------------------------------------------------------------- co-authorship network

def coauthor_graph(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    coa = data["coa"].copy()
    coa["weight"] = coa["weight"].astype(float)
    per_pair = coa.drop_duplicates(["author_a_id", "author_b_id", "openalex_work_id"])
    grouped = per_pair.groupby(["author_a_id", "author_b_id"]).agg(
        papers=("openalex_work_id", "nunique"), weight=("weight", "sum")).reset_index()

    # node attributes: display name and main institution (most rows)
    name: dict[str, Counter] = defaultdict(Counter)
    inst: dict[str, Counter] = defaultdict(Counter)
    for side in ("a", "b"):
        for key, author, institution in zip(coa[f"author_{side}_id"], coa[f"author_{side}"], coa[f"inst_{side}"]):
            name[key][author] += 1
            inst[key][institution] += 1
    keys = sorted(name)
    index = {k: i for i, k in enumerate(keys)}
    graph = nx.Graph()
    graph.add_nodes_from(range(len(keys)))
    for a, b, papers, weight in zip(grouped["author_a_id"], grouped["author_b_id"], grouped["papers"], grouped["weight"]):
        graph.add_edge(index[a], index[b], weight=float(weight), papers=int(papers))
    print(f"  co-authorship graph: {graph.number_of_nodes()} authors, {graph.number_of_edges()} pairs")

    degree = dict(graph.degree())
    strength = dict(graph.degree(weight="weight"))
    k = min(800, len(keys))
    print(f"  betweenness (sampled, k={k}) ...")
    betweenness = nx.betweenness_centrality(graph, k=k, seed=16, normalized=True)
    print("  louvain communities ...")
    communities = nx.community.louvain_communities(graph, weight="weight", seed=16, resolution=1.0)
    communities = sorted(communities, key=len, reverse=True)
    community_of = {}
    for c, members in enumerate(communities):
        for node in members:
            community_of[node] = c
    components = sorted((len(c) for c in nx.connected_components(graph)), reverse=True)

    def main_inst(key: str) -> str:
        return inst[key].most_common(1)[0][0]

    nodes = {
        "id": keys,
        "name": [name[k].most_common(1)[0][0] for k in keys],
        "mask": [sum(BIT[i] for i in inst[k]) for k in keys],
        "inst": [ORDER.index(main_inst(k)) for k in keys],
        "degree": [degree[i] for i in range(len(keys))],
        "strength": [r(strength[i], 3) for i in range(len(keys))],
        "betweenness": [r(betweenness[i] * 1000, 4) for i in range(len(keys))],  # per mille
        "community": [community_of[i] for i in range(len(keys))],
    }
    edges = []
    for u, v, attrs in graph.edges(data=True):
        edges += [u, v, attrs["papers"]]
    # community summary: size, main institution mix, main field (from the dataset rows)
    ext = data["ext"]
    field_of = ext.groupby("author_key")["primary_field"].agg(lambda s: s.value_counts().index[0])
    community_summary = []
    for c, members in enumerate(communities[:60]):
        member_keys = [keys[m] for m in members]
        inst_mix = Counter(main_inst(m) for m in member_keys)
        fields = Counter(field_of.get(m, "") for m in member_keys)
        top_members = sorted(members, key=lambda m: -degree[m])[:5]
        community_summary.append({
            "id": c, "size": len(members),
            "insts": {SHORT[i]: n for i, n in inst_mix.most_common()},
            "field": fields.most_common(1)[0][0],
            "top": [nodes["name"][m] for m in top_members],
        })
    summary = {
        "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(),
        "communities": len(communities), "largest_component": components[0] if components else 0,
        "components": len(components),
        "cross_institution_pairs": int(sum(1 for u, v in graph.edges() if nodes["inst"][u] != nodes["inst"][v])),
        "papers_left_out_hyperauthor": int(data["ext"].loc[data["ext"]["n_authors"] >= CONFIG["hyperauthor"]["threshold"],
                                                           "openalex_work_id"].nunique()),
        "degree_hist": sorted(([d, n] for d, n in Counter(degree.values()).items()), key=lambda kv: kv[0]),
    }
    metrics = {keys[i]: {"degree": degree[i], "betweenness": nodes["betweenness"][i], "community": community_of[i]}
               for i in range(len(keys))}
    return {"nodes": nodes, "edges": edges, "communities": community_summary, "summary": summary}, metrics


# ---------------------------------------------------------------- authors table

def author_journals(ext: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    """Per (institution, author key): papers in each journal, and the journal with the highest impact factor.

    Impact factor is the same value as on the Top 10 table: OpenAlex 2-year mean citedness of the
    journal (oa_2yr_mean_citedness). Journals without a value are never picked as the best journal.
    Ties on impact factor go to the journal with more of the author's papers, then by name.
    """
    journal = ext[(ext["type"] == "journal") & (ext["journal_name"] != "")]
    journal = journal.drop_duplicates(["institution", "author_key", "openalex_work_id"])
    journal = journal.assign(impact=pd.to_numeric(journal["oa_2yr_mean_citedness"], errors="coerce"))
    out = {}
    for (institution, key), g in journal.groupby(["institution", "author_key"], sort=False):
        counts = g["journal_name"].value_counts()
        ifs = g.dropna(subset=["impact"]).groupby("journal_name")["impact"].max()
        best = min(ifs.index, key=lambda j: (-ifs[j], -counts[j], j)) if len(ifs) else ""
        out[(institution, key)] = {"counts": counts, "best": best, "best_if": r(ifs[best], 2) if best else None}
    return out


def authors_table(data: dict[str, Any], metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    a = data["authors"].copy()
    a["key"] = [i if i else name_key(n) for i, n in zip(a["openalex_author_id"], a["author"])]
    num = lambda s: pd.to_numeric(s, errors="coerce")
    journals = author_journals(data["ext"])
    # top_journal (from authors.csv) is the journal with the most of the author's papers; top_journal_papers
    # is how many. best_journal is the journal with the highest impact factor; best_journal_if is that factor.
    columns = ["name", "inst", "papers", "citations", "h", "i10", "works", "top_journal", "field", "degree",
               "betweenness", "community", "orcid", "id", "top_journal_papers", "best_journal", "best_journal_if"]
    rows = []
    for row, h, i10, works in zip(a.itertuples(), num(a["h_index_all_time"]), num(a["i10_index_all_time"]),
                                  num(a["works_count_all_time"])):
        m = metrics.get(row.key, {})
        j = journals.get((row.institution, row.key), {})
        counts = j.get("counts")
        rows.append([row.author, SHORT[row.institution], int(row.papers_in_dataset), int(row.citations_in_dataset),
                     None if h != h else int(h), None if i10 != i10 else int(i10), None if works != works else int(works),
                     row.top_journal, row.main_field, m.get("degree", 0), m.get("betweenness", 0),
                     m.get("community", -1), row.orcid, row.openalex_author_id,
                     int(counts.get(row.top_journal, 0)) if counts is not None and row.top_journal else None,
                     j.get("best", ""), j.get("best_if")])
    rows.sort(key=lambda x: (-x[2], -x[3]))
    return {"columns": columns, "rows": rows}


# ---------------------------------------------------------------- connections

def connections(data: dict[str, Any]) -> dict[str, Any]:
    conn = data["conn"].copy()
    for column in ("shared_papers", "total_citations", "citations_given_to_partner", "citations_received_from_partner"):
        conn[column] = conn[column].astype(int)
    flow = data["flow"].copy()
    flow["year"] = flow["year"].astype(int)
    flow["citations"] = flow["citations"].astype(int)
    flow = flow[flow["year"].between(START_YEAR, END_YEAR)]
    out: dict[str, Any] = {"years": YEARS, "institutions": {}}
    for name in ORDER:
        mine = conn[conn["your_inst"] == name]
        external = mine[~mine["partner_inst"].isin(ORDER)]
        given, received = int(mine["citations_given_to_partner"].sum()), int(mine["citations_received_from_partner"].sum())
        f = flow[flow["your_inst"] == name]
        out["institutions"][SHORT[name]] = {
            "partners": int((mine["shared_papers"] > 0).sum()),
            "citations_in": received, "citations_out": given,
            "impact_ratio": r(received / given, 3) if given else None,
            "top_partners": [{"name": p.partner_inst, "shared": int(p.shared_papers), "citations": int(p.total_citations),
                              "given": int(p.citations_given_to_partner), "received": int(p.citations_received_from_partner),
                              "assigned": p.partner_inst in ORDER}
                             for p in mine.sort_values("shared_papers", ascending=False).head(25).itertuples()],
            "top_citing": [{"name": p.partner_inst, "received": int(p.citations_received_from_partner)}
                           for p in external.sort_values("citations_received_from_partner", ascending=False).head(10).itertuples()],
            "flow_in": [int(f[(f["direction"] == "in") & (f["year"] == y)]["citations"].sum()) for y in YEARS],
            "flow_out": [int(f[(f["direction"] == "out") & (f["year"] == y)]["citations"].sum()) for y in YEARS],
        }
    # links between the three assigned institutions (chord-like matrix of shared papers)
    out["between_assigned"] = [[int(conn[(conn["your_inst"] == a) & (conn["partner_inst"] == b)]["shared_papers"].sum())
                                if a != b else 0 for b in ORDER] for a in ORDER]
    return out


# ---------------------------------------------------------------- impact factor

IF_THRESHOLDS = (5, 10)        # Q1 papers in journals with impact factor above each value
AUTHOR_SPLIT = 10              # papers with fewer authors vs. this many or more
FACULTY_MIN_JOURNAL_PAPERS = 10  # a top 10 is shown for authors with more journal papers than this


def impact(data: dict[str, Any], papers: pd.DataFrame, q1_only: bool = False) -> dict[str, Any]:
    """Journal impact factor, shown on the Publications and Authors pages.

    The impact factor is OpenAlex `summary_stats.2yr_mean_citedness` of the paper's journal
    (column oa_2yr_mean_citedness): the mean citations in the latest full year to the journal's
    works from the two years before, which OpenAlex describes as the impact factor. It is one
    current value per journal (at collection time), not a value for the paper's year.
    Quartiles are the dataset's SCImago quartiles.
    """
    def with_impact(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.assign(impact=pd.to_numeric(frame["oa_2yr_mean_citedness"], errors="coerce"))
        return frame[(frame["type"] == "journal") & frame["impact"].notna()]

    journal_rows = with_impact(data["ext"])
    pi = journal_rows.drop_duplicates(["institution", "openalex_work_id"])
    scopes = {SHORT[name]: pi[pi["institution"] == name] for name in ORDER}
    scopes["All"] = with_impact(papers.reset_index())  # every paper once

    # Q1 papers in journals with impact factor > 5 and > 10, split by number of authors
    out: dict[str, Any] = {"thresholds": list(IF_THRESHOLDS), "author_split": AUTHOR_SPLIT, "q1": {}}
    for k, v in scopes.items():
        q1 = v[v["quartile"] == "Q1"]
        few = q1["n_authors"].astype(int) < AUTHOR_SPLIT
        out["q1"][k] = {"total": len(q1), "rows": [
            {"above": t, "few_authors": int(((q1["impact"] > t) & few).sum()),
             "many_authors": int(((q1["impact"] > t) & ~few).sum())} for t in IF_THRESHOLDS]}

    if q1_only:
        return out

    # faculty with more than FACULTY_MIN_JOURNAL_PAPERS journal papers: their 10 papers in the journals
    # with the highest impact factor (ties: more citations first, then newer)
    mine = journal_rows.drop_duplicates(["institution", "author_key", "openalex_work_id"])
    paper_index: dict[str, int] = {}
    paper_rows: list[list[Any]] = []
    # authors.json identifies an author by OpenAlex id, or by name when there is no id
    a = data["authors"]
    label = {(inst, i if i else name_key(n)): i or n for inst, i, n in zip(a["institution"], a["openalex_author_id"], a["author"])}
    faculty: dict[str, list[int]] = {}
    for (institution, key), g in mine.groupby(["institution", "author_key"]):
        if len(g) <= FACULTY_MIN_JOURNAL_PAPERS:
            continue
        g = g.assign(c=g["citations"].astype(int)).sort_values(["impact", "c", "year"], ascending=False)
        top = []
        for p in g.head(10).itertuples():
            if p.openalex_work_id not in paper_index:
                paper_index[p.openalex_work_id] = len(paper_rows)
                paper_rows.append([p.title[:200], p.journal_name, int(p.year), p.quartile, r(p.impact, 2),
                                   int(p.citations), int(p.n_authors), p.doi.replace("https://doi.org/", "")])
            top.append(paper_index[p.openalex_work_id])
        faculty[f"{SHORT[institution]}|{label.get((institution, key), key)}"] = top
    out["faculty_min_journal_papers"] = FACULTY_MIN_JOURNAL_PAPERS
    out["faculty"] = faculty
    out["papers"] = {"columns": ["title", "journal", "year", "quartile", "if", "citations", "n_authors", "doi"],
                     "rows": paper_rows}
    return out


# ---------------------------------------------------------------- overview

def funnel(run: Run, out_dir: Path) -> list[dict[str, Any]]:
    """Paper counts at each stage, from the reports (letters/reviews are never part of the dataset)."""
    types = set(CONFIG["collection"]["work_types"])
    downloaded = sum(1 for w in read_jsonl(run.path("works.jsonl")) if w["type"] in types)
    build = json.loads((out_dir / "build" / "build_report.json").read_text())
    clean = json.loads((out_dir / "cleaning_report.json").read_text())
    return [
        {"stage": "Downloaded", "papers": downloaded, "note": "science & engineering, 2016–2026, article / conference paper"},
        {"stage": "Built", "papers": build["unique_papers"], "note": "real journal / conference venues, duplicates and wrong affiliations removed"},
        {"stage": "Cleaned", "papers": clean["output_papers"], "note": "medical & non-science journals, retractions, notices removed"},
    ]


def overview(data: dict[str, Any], papers: pd.DataFrame, run: Run, out_dir: Path, cit: dict, coa: dict,
             conn: dict) -> dict[str, Any]:
    ext = data["ext"]
    pi = per_inst_papers(ext)
    info_path = run.path("collection_info.json")
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    journal = papers[papers["type"] == "journal"]
    ranked = journal[journal["quartile"] != ""]
    institutions = {}
    for name in ORDER:
        mine = pi[pi["institution"] == name]
        mj = mine[mine["type"] == "journal"]
        mr = mj[mj["quartile"] != ""]
        authors = data["authors"][data["authors"]["institution"] == name]
        h = pd.to_numeric(authors["h_index_all_time"], errors="coerce").dropna()
        institutions[SHORT[name]] = {
            "name": name, "ror": INSTITUTIONS[name]["ror"], "papers": len(mine), "rows": int((ext["institution"] == name).sum()),
            "authors": int(authors.shape[0]), "citations": int(mine["citations"].sum()),
            "q1_share": r((mr["quartile"] == "Q1").mean() * 100, 1) if len(mr) else None,
            "conference": int((mine["type"] == "conference").sum()),
            "median_h": float(h.median()) if len(h) else None,
            "top_field": mine["primary_field"].value_counts().index[0],
            "shared_with_other_assigned": int(mine["openalex_work_id"].isin(papers[papers["mask"].map(lambda m: bin(m).count("1") > 1)].index).sum()),
            "partners": conn["institutions"][SHORT[name]]["partners"],
        }
    return {
        "group": GROUP,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "collected_at": info.get("collected_at_utc", ""),
        "years": [START_YEAR, END_YEAR],
        "totals": {
            "papers": len(papers), "rows": len(ext), "authors": int(ext["author_key"].nunique()),
            "citations": int(papers["citations"].sum()), "journal": int(len(journal)),
            "conference": int((papers["type"] == "conference").sum()),
            "q1_share": r((ranked["quartile"] == "Q1").mean() * 100, 1),
            "quartile_coverage": r(len(ranked) / len(journal) * 100, 1),
            "partner_institutions": int(data["conn"].loc[data["conn"]["shared_papers"].astype(int) > 0, "partner_inst"].nunique()),
            "citation_edges": cit["summary"]["edges"], "coauthor_edges": coa["summary"]["edges"],
            "communities": coa["summary"]["communities"],
        },
        "institutions": institutions,
        "funnel": funnel(run, out_dir),
        "fields_included": CONFIG["scope"]["include_fields"],
    }


# Publications page filter: papers grouped by number of authors. group id -> (smallest, largest) author count
AUTHOR_GROUPS = {"1-5": (1, 5), "6-20": (6, 20), "21-99": (21, 99), "100+": (100, 10**9)}


def author_group_data(data: dict[str, Any], papers: pd.DataFrame) -> dict[str, Any]:
    """stats.json once per author-count group (plus the Q1 impact-factor counts), keyed by group id."""
    out = {}
    for group, (lo, hi) in AUTHOR_GROUPS.items():
        ext = data["ext"][data["ext"]["n_authors"].between(lo, hi)]
        subset = papers[papers["n_authors"].between(lo, hi)]
        out[group] = stats(ext, subset)
        out[group]["impact_q1"] = impact({**data, "ext": ext}, subset, q1_only=True)
    return out


def build_dashboard_data(run: Run, out_dir: Path = OUTPUT_DIR) -> None:
    DASHBOARD_DATA.mkdir(parents=True, exist_ok=True)
    data = load(out_dir)
    papers = paper_table(data["ext"])
    print("computing ...")
    cit, _ = citation_graph(data, papers)
    coa, metrics = coauthor_graph(data)
    conn = connections(data)
    print("writing", DASHBOARD_DATA)
    write("overview.json", overview(data, papers, run, out_dir, cit, coa, conn))
    write("stats.json", stats(data["ext"], papers))
    write("authors.json", authors_table(data, metrics))
    write("citation.json", cit)
    write("coauthor.json", coa)
    write("connections.json", conn)
    write("impact.json", impact(data, papers))
    write("stats_by_authors.json", author_group_data(data, papers))
    from .insights_data import build_insights  # reads the files written above
    build_insights(out_dir)
    build_team_data(data, run, out_dir)


# ---------------------------------------------------------------- team-size filter (Overview buttons)

# Every page except Insights can be switched to papers with at most 10 authors or more than 10 authors.
# For each group the files above are written again from that group's papers only, into data/team/<id>/,
# with data/team/index.json listing the groups. All-time author profiles (h-index, i10, works) are not split.
TEAM_GROUPS = {"le10": ("Papers with 10 or fewer authors", 1, 10), "gt10": ("Papers with more than 10 authors", 11, 10**9)}


def subset_authors(authors: pd.DataFrame, ext: pd.DataFrame) -> pd.DataFrame:
    """authors.csv recomputed from a subset of papers (same columns, same rules as clean.write_authors)."""
    a = authors.assign(_key=[i if i else name_key(n) for i, n in zip(authors["openalex_author_id"], authors["author"])])
    profile = {(row["institution"], row["_key"]): row for row in a.drop_duplicates(["institution", "_key"]).to_dict("records")}
    records = []
    for (institution, key), group in ext.groupby(["institution", "author_key"], sort=True):
        papers = group.drop_duplicates("openalex_work_id")
        journals = papers[papers["type"] == "journal"]["journal_name"].replace("", pd.NA).dropna()
        p = profile.get((institution, key), {})
        records.append({
            "institution": institution, "author": p.get("author") or group["author"].iloc[0],
            "openalex_author_id": group["openalex_author_id"].iloc[0], "orcid": p.get("orcid", ""),
            "papers_in_dataset": len(papers), "citations_in_dataset": int(papers["citations"].sum()),
            "top_journal": journals.value_counts().index[0] if len(journals) else "",
            "main_field": papers["primary_field"].value_counts().index[0],
            "h_index_all_time": p.get("h_index_all_time", ""), "i10_index_all_time": p.get("i10_index_all_time", ""),
            "works_count_all_time": p.get("works_count_all_time", "")})
    return pd.DataFrame(records, columns=list(authors.columns))


def subset_connections(ext: pd.DataFrame, flow_by_paper: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """indian_connections.csv and citation_flow.csv recomputed from a subset of papers (same rules as networks.py)."""
    first = ext.drop_duplicates(["institution", "openalex_work_id"])
    shared: dict[tuple[str, str], set[str]] = defaultdict(set)
    cites = dict(zip(first["openalex_work_id"], first["citations"].astype(int)))
    for own, work_id, names in zip(first["institution"], first["openalex_work_id"], first["coauthor_institutes"]):
        for partner in (names.split("; ") if names else []):
            shared[(own, partner)].add(work_id)
    f = flow_by_paper[flow_by_paper["openalex_work_id"].isin(set(first["openalex_work_id"]))]
    f = f.assign(citations=f["citations"].astype(int))
    totals = f.groupby(["your_inst", "partner_inst", "direction"])["citations"].sum().to_dict()

    def get(own: str, partner: str, direction: str) -> int:
        return int(totals.get((own, partner, direction), 0))

    rows = [{"your_inst": own, "partner_inst": partner, "shared_papers": len(ids), "total_citations": int(sum(cites[w] for w in ids)),
             "citations_given_to_partner": get(own, partner, "out"), "citations_received_from_partner": get(own, partner, "in")}
            for (own, partner), ids in sorted(shared.items())]
    for own, partner in sorted(set(zip(f["your_inst"], f["partner_inst"])) - set(shared)):
        rows.append({"your_inst": own, "partner_inst": partner, "shared_papers": 0, "total_citations": 0,
                     "citations_given_to_partner": get(own, partner, "out"), "citations_received_from_partner": get(own, partner, "in")})
    conn = pd.DataFrame(rows, columns=["your_inst", "partner_inst", "shared_papers", "total_citations",
                                       "citations_given_to_partner", "citations_received_from_partner"])
    flow = f[f["year"] != ""].groupby(["your_inst", "partner_inst", "direction", "year"])["citations"].sum().reset_index()
    flow = flow.reindex(columns=["your_inst", "partner_inst", "direction", "year", "citations"])
    return conn.astype(str), flow.astype(str)


def build_team_data(data: dict[str, Any], run: Run, out_dir: Path) -> None:
    if data.get("flow_by_paper") is None:
        print("team-size filter skipped: run `python -m collector networks` again to write citation_flow_by_paper.csv")
        return
    index = []
    for gid, (label, lo, hi) in TEAM_GROUPS.items():
        ext = data["ext"][data["ext"]["n_authors"].between(lo, hi)].reset_index(drop=True)
        ids = set(ext["openalex_work_id"])
        conn, flow = subset_connections(ext, data["flow_by_paper"])
        sub = {**data, "ext": ext, "authors": subset_authors(data["authors"], ext),
               "cit": data["cit"][data["cit"]["source_openalex_id"].isin(ids) & data["cit"]["target_openalex_id"].isin(ids)],
               "coa": data["coa"][data["coa"]["openalex_work_id"].isin(ids)], "conn": conn, "flow": flow}
        papers = paper_table(ext)
        dest = DASHBOARD_DATA / "team" / gid
        dest.mkdir(parents=True, exist_ok=True)
        print(f"team-size group {gid}: {label.lower()} ({len(papers)} papers) -> {dest}")
        cit, _ = citation_graph(sub, papers)
        coa, metrics = coauthor_graph(sub)
        con = connections(sub)
        ov = overview(sub, papers, run, out_dir, cit, coa, con)
        ov["funnel"].append({"stage": label, "papers": len(papers), "note": "team-size filter chosen on the Overview page"})
        ov["team"] = {"id": gid, "label": label, "min_authors": lo, "max_authors": hi if hi < 10**9 else None}
        write("overview.json", ov, dest)
        write("stats.json", stats(ext, papers), dest)
        write("authors.json", authors_table(sub, metrics), dest)
        write("citation.json", cit, dest)
        write("coauthor.json", coa, dest)
        write("connections.json", con, dest)
        write("impact.json", impact(sub, papers), dest)
        write("stats_by_authors.json", author_group_data(sub, papers), dest)
        index.append({"id": gid, "label": label, "papers": len(papers), "min_authors": lo,
                      "max_authors": hi if hi < 10**9 else None})
    write("index.json", {"groups": index}, DASHBOARD_DATA / "team")
