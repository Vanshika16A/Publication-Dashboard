"""The network files from the instruction note, built from the finished dataset.

    citation_network.csv     source_doi, target_doi, source_inst, target_inst, year
    authorship_network.csv   author_a, author_b, paper_doi, inst_a, inst_b, year
    indian_connections.csv   your_inst, partner_inst, shared_papers, total_citations
    citation_flow.csv        extra: citations received / given per partner institution and year (section 7a)
    citation_flow_by_paper.csv  extra: the same per paper, so the dashboard can split it by team size

Extra columns come after the required ones. A paper without a DOI is identified by its OpenAlex
URL so that no edge is lost.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from .build import Cache, mapped_partner, name_key
from .config import CONFIG, TARGET_IDS, TARGET_NAMES

NAME_TO_TARGET = {name: target for target, name in TARGET_NAMES.items()}


def paper_ref(doi: str, work_id: str) -> str:
    return doi or f"https://openalex.org/{work_id}"


def write_networks(frame: pd.DataFrame, cache: Cache, out_dir: Path) -> dict[str, int]:
    """`frame`: the cleaned extended dataset; `cache`: the collected OpenAlex data (references, citers)."""
    works = cache.works
    threshold = CONFIG["hyperauthor"]["threshold"]
    counts: dict[str, int] = {}
    hidden = pd.DataFrame({
        "_partners": [[(None, name) for name in names.split("; ")] if names else [] for names in frame["coauthor_institutes"]],
        "_author_key": [a if a else name_key(n) for a, n in zip(frame["openalex_author_id"], frame["author"])],
    }, index=frame.index)

    # one record per (institution, paper)
    first = ~frame.duplicated(["institution", "openalex_work_id"])
    paper_rows = frame[first].assign(partners=hidden.loc[first, "_partners"].values)
    insts_of: dict[str, set[str]] = defaultdict(set)
    meta: dict[str, dict[str, Any]] = {}
    for row in paper_rows.itertuples():
        insts_of[row.openalex_work_id].add(row.institution)
        meta[row.openalex_work_id] = {"doi": row.doi, "year": row.year, "citations": row.citations}

    # ---- citation network (papers of the dataset citing papers of the dataset)
    edges = []
    for source_id, source_insts in insts_of.items():
        for target_id in works[source_id]["refs"]:
            if target_id not in insts_of:
                continue
            for source_inst in sorted(source_insts):
                for target_inst in sorted(insts_of[target_id]):
                    edges.append({
                        "source_doi": paper_ref(meta[source_id]["doi"], source_id),
                        "target_doi": paper_ref(meta[target_id]["doi"], target_id),
                        "source_inst": source_inst, "target_inst": target_inst, "year": meta[source_id]["year"],
                        "cross_institute": source_inst != target_inst,
                        "source_openalex_id": source_id, "target_openalex_id": target_id})
    pd.DataFrame(edges, columns=["source_doi", "target_doi", "source_inst", "target_inst", "year", "cross_institute",
                                 "source_openalex_id", "target_openalex_id"]).to_csv(out_dir / "citation_network.csv", index=False)
    counts["citation_edges"] = len(edges)

    # ---- authorship network
    people = frame.assign(author_key=hidden["_author_key"].values)
    edge_rows: list[dict[str, Any]] = []
    skipped_hyper = 0
    for work_id, group in people.groupby("openalex_work_id", sort=True):
        n_authors = int(group["n_authors"].iloc[0])
        if n_authors >= threshold:
            skipped_hyper += 1
            continue
        members = sorted({(r.author_key, r.author, r.institution) for r in group.itertuples()})
        weight = round(1 / (n_authors - 1), 6) if n_authors > 1 else 1.0
        seen: set[tuple] = set()
        for (key_a, name_a, inst_a), (key_b, name_b, inst_b) in combinations(members, 2):
            if key_a == key_b:
                continue
            if key_a > key_b:
                key_a, name_a, inst_a, key_b, name_b, inst_b = key_b, name_b, inst_b, key_a, name_a, inst_a
            edge_key = (key_a, key_b, inst_a, inst_b)
            if edge_key in seen:
                continue
            seen.add(edge_key)
            edge_rows.append({
                "author_a": name_a, "author_b": name_b, "paper_doi": paper_ref(meta[work_id]["doi"], work_id),
                "inst_a": inst_a, "inst_b": inst_b, "year": meta[work_id]["year"],
                "author_a_id": key_a, "author_b_id": key_b, "weight": weight,
                "cross_institution": inst_a != inst_b, "openalex_work_id": work_id})
    pd.DataFrame(edge_rows, columns=["author_a", "author_b", "paper_doi", "inst_a", "inst_b", "year", "author_a_id",
                                     "author_b_id", "weight", "cross_institution", "openalex_work_id"]
                 ).to_csv(out_dir / "authorship_network.csv", index=False)
    counts["authorship_edges"] = len(edge_rows)
    counts["papers_left_out_of_authorship_network_as_hyperauthor"] = skipped_hyper

    # ---- indian connections and citation flow
    shared: dict[tuple[str, str], set[str]] = defaultdict(set)
    given: Counter = Counter()      # (own, partner) -> references from own papers to partner papers
    received: Counter = Counter()   # (own, partner) -> citations of own papers by partner papers
    flow: Counter = Counter()       # (own, partner, direction, year) -> count
    by_paper: Counter = Counter()   # (own, partner, paper, direction, year) -> count: lets the dashboard split flows by paper
    for row in paper_rows.itertuples():
        own, own_id, work_id = row.institution, NAME_TO_TARGET[row.institution], row.openalex_work_id
        for _, partner in row.partners:
            shared[(own, partner)].add(work_id)
        for ref_id in works[work_id]["refs"]:
            for inst in cache.ref_insts.get(ref_id, []):
                partner = mapped_partner(inst[0], inst[1], inst[2], own_id)
                if partner:
                    given[(own, partner[1])] += 1
                    flow[(own, partner[1], "out", row.year)] += 1
                    by_paper[(own, partner[1], work_id, "out", row.year)] += 1
        for citer_id in cache.citers_of.get(work_id, []):
            citer = cache.citers[citer_id]
            for partner_name in {p[1] for p in (mapped_partner(i[0], i[1], i[2], own_id) for i in citer["i"]) if p}:
                received[(own, partner_name)] += 1
                by_paper[(own, partner_name, work_id, "in", citer["year"] if citer["year"] is not None else "")] += 1
                if citer["year"] is not None:  # a few OpenAlex works have no publication year
                    flow[(own, partner_name, "in", citer["year"])] += 1
    connection_rows = []
    for (own, partner), work_ids in sorted(shared.items()):
        connection_rows.append({
            "your_inst": own, "partner_inst": partner, "shared_papers": len(work_ids),
            "total_citations": int(sum(meta[w]["citations"] for w in work_ids)),
            "citations_given_to_partner": given.get((own, partner), 0),
            "citations_received_from_partner": received.get((own, partner), 0)})
    for own, partner in sorted(set(given) | set(received)):  # partners we only cite / are cited by
        if (own, partner) not in shared:
            connection_rows.append({"your_inst": own, "partner_inst": partner, "shared_papers": 0, "total_citations": 0,
                                    "citations_given_to_partner": given.get((own, partner), 0),
                                    "citations_received_from_partner": received.get((own, partner), 0)})
    pd.DataFrame(connection_rows).sort_values(["your_inst", "shared_papers"], ascending=[True, False]).to_csv(
        out_dir / "indian_connections.csv", index=False)
    pd.DataFrame([{"your_inst": o, "partner_inst": p, "direction": d, "year": y, "citations": c}
                  for (o, p, d, y), c in sorted(flow.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][3], kv[0][1]))]
                 ).to_csv(out_dir / "citation_flow.csv", index=False)
    pd.DataFrame([{"your_inst": o, "partner_inst": p, "openalex_work_id": w, "direction": d, "year": y, "citations": c}
                  for (o, p, w, d, y), c in by_paper.items()],
                 columns=["your_inst", "partner_inst", "openalex_work_id", "direction", "year", "citations"]
                 ).to_csv(out_dir / "citation_flow_by_paper.csv", index=False)
    counts["partner_institutions"] = len({p for _, p in shared})
    return counts
