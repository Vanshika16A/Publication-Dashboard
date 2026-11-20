"""Chart datasets for the Insights page: `python -m collector dashboard-data` writes dashboard/public/data/insights.json.

Runs last in `build_dashboard_data`, because it reads the cleaned paper-level CSV (output/) and four files
written just before it: stats.json, overview.json, connections.json and coauthor.json. Each insight in
dashboard/src/views/insights.js has an entry here (chart type, data, headline number) under the same key.
The written findings in insights.js are hand-written and are not regenerated.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .config import GROUP, OUTPUT_DIR

INST = {"University of Delhi": "DU", "Jawaharlal Nehru University": "JNU", "University of Hyderabad": "UoH"}
KEYS = ["DU", "JNU", "UoH"]


def build_insights(out_dir: Path = OUTPUT_DIR) -> None:
    from . import dashboard_data as dd  # imported here: dashboard_data imports this module at the end of its own run
    data_dir = dd.DASHBOARD_DATA

    def read(name: str) -> dict:
        return json.loads((data_dir / name).read_text(encoding="utf-8"))

    d = pd.read_csv(out_dir / f"group{GROUP}_data_extended.csv", low_memory=False,
                    usecols=["institution", "year", "journal_name", "citations", "quartile", "coauthor_institutes", "openalex_work_id",
                             "author_position", "is_corresponding", "primary_field", "primary_topic", "n_authors", "is_hyperauthor",
                             "source_id", "type", "oa_2yr_mean_citedness"])
    d["inst"] = d.institution.map(INST)
    d["led"] = d.author_position.isin(["first", "last"]) | (d.is_corresponding == True)
    d["has_partner"] = d.coauthor_institutes.notna()
    g = d.groupby(["inst", "openalex_work_id"]).agg(
        year=("year", "first"), field=("primary_field", "first"), topic=("primary_topic", "first"), cites=("citations", "first"),
        q=("quartile", "first"), src=("source_id", "first"), journal=("journal_name", "first"), n=("n_authors", "first"),
        ifv=("oa_2yr_mean_citedness", "first"), hyper=("is_hyperauthor", "max"), led=("led", "max"), partner=("has_partner", "max"), type=("type", "first")).reset_index()
    YEARS = list(range(2016, 2027))
    r1 = lambda v: round(float(v), 1)
    E = lambda df: df.year.between(2016, 2018); L = lambda df: df.year.between(2023, 2025)
    small = g[(g.n < 100) & ~g.hyper]
    out = {}

    def yearly(df, f):
        return {k: [r1(f(df[(df.inst == k) & (df.year == y)])) if len(df[(df.inst == k) & (df.year == y)]) else None for y in YEARS] for k in KEYS}

    # 1 field change DU, early vs late
    fc = {k: small[(small.inst == k) & L(small)].field.value_counts().sub(small[(small.inst == k) & E(small)].field.value_counts(), fill_value=0) for k in KEYS}
    cats = list(fc["DU"].sort_values(ascending=False).index[:8])
    out["expansion"] = {"type": "bar", "horizontal": True, "categories": cats, "unit": "papers added",
        "series": [{"name": k, "color": k, "data": [int(fc[k].get(c, 0)) for c in cats]} for k in KEYS],
        "caption": "Change in papers per field, 2016–18 to 2023–25 (teams under 100 authors)",
        "stat": {"value": f"+{int(fc['DU'].sum())}", "label": "more DU papers in 2023–25 than in 2016–18", "color": "DU"}}

    # 2 growing topics
    tc = small[L(small)].topic.value_counts().sub(small[E(small)].topic.value_counts(), fill_value=0).sort_values(ascending=False).head(8)
    out["topics"] = {"type": "bar", "horizontal": True, "categories": list(tc.index), "unit": "papers added",
        "series": [{"name": "All", "color": "All", "data": [int(v) for v in tc.values]}],
        "caption": "Fastest-growing research topics, all three universities (2016–18 to 2023–25)",
        "stat": {"value": f"+{int(tc.iloc[0])}", "label": f"papers in '{tc.index[0]}'", "color": "All"}}

    # 3 conference series
    conf = g[g.type == "conference"]
    lns = conf[conf.journal.fillna("").str.contains("Lecture Notes in Networks and Systems|Springer Proceedings in Physics", case=False, regex=True)]
    out["conference"] = {"type": "bar", "categories": ["2016–18", "2019–22", "2023–25"], "unit": "papers",
        "series": [{"name": "Springer-type series", "color": "All", "data": [int(len(lns[lns.year.between(a, b)])) for a, b in [(2016, 2018), (2019, 2022), (2023, 2025)]]}],
        "caption": "Conference papers in publisher book series (Lecture Notes / Proceedings in Physics)",
        "stat": {"value": f"{int(len(lns[lns.year.between(2023, 2025)]))}", "label": "series papers in 2023–25", "color": "All"}}

    # 4 regrading
    j = g[g.q.isin(["Q1", "Q2", "Q3", "Q4"]) & (g.type == "journal")]
    old = j[j.year.between(2016, 2018)].groupby("src").q.agg(lambda s: s.mode().iloc[0])
    rows = {}
    for k in KEYS:
        a = j[(j.inst == k) & j.year.between(2016, 2018)]; b = j[(j.inst == k) & j.year.between(2023, 2025)]
        fixed = b[b.src.isin(old.index)]
        rows[k] = [r1((a.q == "Q1").mean() * 100), r1((b.q == "Q1").mean() * 100), r1((fixed.src.map(old) == "Q1").mean() * 100)]
    out["regrade"] = {"type": "bar", "categories": ["2016–18 actual", "2023–25 actual", "2023–25 at 2016–18 grade"], "unit": "% in Q1",
        "series": [{"name": k, "color": k, "data": rows[k]} for k in KEYS],
        "caption": "Q1 share of journal papers: as graded, and if journals kept their 2016–18 grade",
        "stat": {"value": f"{rows['UoH'][0]}% → {rows['UoH'][2]}%", "label": "UoH Q1 share at fixed grades (rose, not fell)", "color": "UoH"}}

    # 5 chemistry Q1
    chem = j[j.field == "Chemistry"]
    out["chemistry"] = {"type": "line", "x": YEARS, "unit": "% of chemistry papers in Q1",
        "series": [{"name": k, "color": k, "data": yearly(chem, lambda x: (x.q == "Q1").mean() * 100)[k]} for k in KEYS],
        "caption": "Chemistry papers in Q1 journals, by year",
        "stat": {"value": f"{yearly(chem, lambda x: (x.q == 'Q1').mean() * 100)['UoH'][0]}% → {yearly(chem, lambda x: (x.q == 'Q1').mean() * 100)['UoH'][-3]}%", "label": "UoH chemistry Q1 share, 2016 → 2024; DU and JNU fell too", "color": "UoH"}}

    # relative citation
    ref = g[(g.year <= 2023) & (g.n < 100)].drop_duplicates("openalex_work_id")
    mean = ref.groupby(["field", "year"]).cites.mean().rename("fm")
    sm = g[(g.year <= 2023) & (g.n < 100)].merge(mean, left_on=["field", "year"], right_index=True)
    sm["rel"] = sm.cites / sm.fm
    rel = sm.groupby("inst").rel.mean()
    q1s = {k: (j[(j.inst == k) & (j.year <= 2023) & (j.n < 100)].q == "Q1").mean() * 100 for k in KEYS}
    out["q1vscite"] = {"type": "bar", "categories": ["Q1 share (%)", "Cited vs field-year average (×100)"], "unit": "",
        "series": [{"name": k, "color": k, "data": [r1(q1s[k]), r1(rel[k] * 100)]} for k in KEYS],
        "caption": "Q1 share and relative citation rate (100 = field and year average)",
        "stat": {"value": f"{r1(q1s['UoH'])}% / {int(rel['UoH']*100)}", "label": "UoH Q1 share / relative citations", "color": "UoH"}}

    # 7 role
    sm["role"] = sm.led.map({True: "Led (first/last/corresp.)", False: "Middle author only"})
    rr = sm.groupby(["inst", "role"]).rel.mean().unstack()
    out["roles"] = {"type": "bar", "categories": ["Led (first/last/corresp.)", "Middle author only"], "unit": "× average for same field and year (1.0 = average)",
        "series": [{"name": k, "color": k, "data": [round(float(rr.loc[k, c]), 2) for c in ["Led (first/last/corresp.)", "Middle author only"]]} for k in KEYS],
        "caption": "Citations relative to the average for the same field and year, by the university's role",
        "stat": {"value": f"{rr.loc['JNU','Middle author only']:.2f}×", "label": "JNU papers where it was only a middle author are cited at this multiple of the field average", "color": "JNU"}}

    # 8 led share
    out["led"] = {"type": "line", "x": YEARS, "unit": "% of papers led",
        "series": [{"name": k, "color": k, "data": yearly(g[g.n < 100], lambda x: x.led.mean() * 100)[k]} for k in KEYS],
        "caption": "Share of papers with a first, last or corresponding author from the university",
        "stat": {"value": f"{yearly(g[g.n<100], lambda x: x.led.mean()*100)['DU'][0]}% → {yearly(g[g.n<100], lambda x: x.led.mean()*100)['DU'][-2]}%", "label": "DU led share, 2016 → 2025", "color": "DU"}}

    # 9 partner share
    ps = yearly(g[g.n < 100], lambda x: x.partner.mean() * 100)
    out["partners"] = {"type": "line", "x": YEARS, "unit": "% with another Indian institution",
        "series": [{"name": k, "color": k, "data": ps[k]} for k in KEYS],
        "caption": "Papers with at least one other Indian institution, by year",
        "stat": {"value": f"{ps['DU'][0]}% → {ps['DU'][-2]}%", "label": "DU, 2016 → 2025", "color": "DU"}}

    con = read("connections.json")
    I = con["institutions"]
    # partner institutions per paper: one entry per (university, paper, partner), with the paper's author count
    own = {"DU": "University of Delhi", "JNU": "Jawaharlal Nehru University", "UoH": "University of Hyderabad"}
    pr = d[["inst", "openalex_work_id", "coauthor_institutes"]].dropna()
    pr = pr.assign(p=pr.coauthor_institutes.str.split(";")).explode("p")
    pr["p"] = pr.p.str.strip()
    pr = pr[pr.p != ""].drop_duplicates(["inst", "openalex_work_id", "p"]).merge(g[["inst", "openalex_work_id", "n"]], on=["inst", "openalex_work_id"])
    pr = pr[pr.p != pr.inst.map(own)]

    def partner_counts(k, small=False):
        x = pr[pr.inst == k]
        return (x[x.n < 100] if small else x).groupby("p").size().sort_values(ascending=False)

    # 10 DU's apparent top partners, with and without papers of 100+ authors
    du_all, du_small = partner_counts("DU"), partner_counts("DU", True)
    top8 = list(du_all.index[:8])
    out["dupartners"] = {"type": "bar", "horizontal": True, "categories": top8, "unit": "papers shared with DU",
        "series": [{"name": "All papers", "color": "DU", "data": [int(du_all[c]) for c in top8]},
                   {"name": "Without papers of 100+ authors", "color": "DU", "tint": 0.55, "data": [int(du_small.get(c, 0)) for c in top8]}],
        "caption": "DU's eight apparent top partners: papers shared, with and without papers of 100+ authors",
        "stat": {"value": f"{int(du_all[top8[0]])} → {int(du_small.get(top8[0], 0))}", "label": f"papers shared with {top8[0]}, all papers → without 100+ author papers", "color": "DU"}}
    # 11 local: each university's top 4 partners, leaving out papers of 100+ authors
    cats, vals, cols = [], [], []
    for k in KEYS:
        for name, v in partner_counts(k, True).head(4).items():
            cats.append(f"{name} ({k})"); vals.append(int(v)); cols.append(k)
    out["local"] = {"type": "sankey", "unit": "shared papers",
        "nodes": [{"name": k, "color": k} for k in KEYS] + [{"name": c, "color": cl} for c, cl in zip(cats, cols)],
        "links": [{"source": cl, "target": c, "value": v, "color": cl} for c, v, cl in zip(cats, vals, cols)],
        "caption": "Top 4 partners of each university by shared papers, leaving out papers of 100+ authors (flow colour = university)",
        "stat": {"value": "Same city", "label": "partners cluster in Delhi and Hyderabad", "color": "All"}}
    # 12 pairs: papers shared by two universities, split by whether the paper has 100+ authors
    w = g.groupby("openalex_work_id").agg(insts=("inst", frozenset), n=("n", "first"))
    pair_names = [("DU", "JNU"), ("DU", "UoH"), ("JNU", "UoH")]
    pair_n = [w[w.insts.map(lambda t: set(pair) <= t)].n for pair in pair_names]
    out["pairs"] = {"type": "bar", "horizontal": True, "stack": True, "categories": [f"{a}–{b}" for a, b in pair_names], "unit": "papers shared",
        "series": [{"name": "Papers of fewer than 100 authors", "color": "Shared", "data": [int((x < 100).sum()) for x in pair_n]},
                   {"name": "Papers of 100+ authors", "color": "Shared", "tint": 0.55, "data": [int((x >= 100).sum()) for x in pair_n]}],
        "caption": "Papers shared between each pair of universities, split by whether the paper has 100+ authors",
        "stat": {"value": str(len(pair_n[0])), "label": f"DU–JNU shared papers, only {int((pair_n[0] >= 100).sum())} with 100+ authors", "color": "Shared"}}
    # 13 communities
    co = read("coauthor.json")["communities"]
    cnt = {"DU only": 0, "JNU only": 0, "UoH only": 0, "Mixed": 0}
    for c in co:
        tot = sum(c["insts"].values()); big = max(c["insts"].items(), key=lambda kv: kv[1])
        if big[1] / tot >= 0.9: cnt[f"{big[0]} only"] += 1
        else: cnt["Mixed"] += 1
    out["communities"] = {"type": "bar", "categories": list(cnt), "unit": "communities (60 largest)", "colors": ["DU", "JNU", "UoH", "Shared"],
        "series": [{"name": "Communities", "color": "All", "data": list(cnt.values())}],
        "caption": "Largest co-authorship communities by university mix (≥90% one university = 'only')",
        "stat": {"value": str(cnt["Mixed"]), "label": "mixed communities among the 60 largest", "color": "Shared"}}
    # 14 citers: DU's heaviest citing institutions, citations received against papers written together
    du_cite = I["DU"]["top_citing"][:10]
    shared_all = partner_counts("DU")
    heavy = next((p for p in du_cite if p["name"] == "Saveetha University"), du_cite[0])
    out["citers"] = {"type": "bar", "horizontal": True, "categories": [p["name"] for p in du_cite], "unit": "citations to DU / papers written together",
        "series": [{"name": "Citations to DU from them", "color": "DU", "data": [p["received"] for p in du_cite]},
                   {"name": "Papers written together", "color": "DU", "tint": 0.55, "data": [int(shared_all.get(p["name"], 0)) for p in du_cite]}],
        "caption": "DU's ten heaviest citing institutions in India: citations received against papers written together",
        "stat": {"value": f"{heavy['received']:,} vs {int(shared_all.get(heavy['name'], 0))}", "label": f"citations to DU from {heavy['name']} vs papers written together", "color": "DU"}}
    # 15 impact ratio by year
    out["impact"] = {"type": "line", "x": con["years"], "unit": "cited by India ÷ cites India",
        "series": [{"name": k, "color": k, "data": [round(a / b, 2) if b else None for a, b in zip(I[k]["flow_in"], I[k]["flow_out"])] } for k in KEYS],
        "refline": 1, "caption": "Citations received from Indian institutions ÷ citations given to them, by year",
        "stat": {"value": f"{round(I['JNU']['flow_in'][-2]/I['JNU']['flow_out'][-2],2)}", "label": "JNU ratio in 2025 (full-period ratio 1.02)", "color": "JNU"}}
    # 16 most cited
    st = read("stats.json")["most_cited"]["All"][:8]
    def ck(p): return p["insts"][0] if len(p["insts"]) == 1 else "Shared"
    out["mostcited"] = {"type": "bar", "horizontal": True, "categories": [p["title"][:46] + "…" for p in st], "unit": "citations", "colors": [ck(p) for p in st],
        "series": [{"name": "Citations", "color": "All", "data": [p["citations"] for p in st]}],
        "caption": "Most-cited papers (bar colour = university)",
        "stat": {"value": f"{st[0]['citations']:,}", "label": "citations to the wheat genome paper", "color": "DU"}}

    # ---- chart types: pick the form that fits each finding
    out["expansion"]["type"] = "dot"
    out["topics"]["type"] = "rose"
    ce, cl = conf[conf.year.between(2016, 2018)], conf[conf.year.between(2023, 2025)]
    le, ll = lns[lns.year.between(2016, 2018)], lns[lns.year.between(2023, 2025)]
    out["conference"].update({"type": "donuts", "donuts": [
        {"name": "2016–18", "data": [["Lecture Notes in Networks and Systems + Springer Proceedings in Physics", int(len(le))], ["Other conference papers", int(len(ce) - len(le))]]},
        {"name": "2023–25", "data": [["Lecture Notes in Networks and Systems + Springer Proceedings in Physics", int(len(ll))], ["Other conference papers", int(len(cl) - len(ll))]]}],
        "stat": {"value": f"{round(len(le)/len(ce)*100)}% → {round(len(ll)/len(cl)*100)}%", "label": "of conference papers are in these two Springer series", "color": "All"},
        "caption": "Conference papers: share in Lecture Notes in Networks and Systems and Springer Proceedings in Physics, vs all other conference papers"})
    out["regrade"]["type"] = "slope"
    out["chemistry"]["type"] = "heatmap"
    n_q1 = {k: int(len(j[(j.inst == k) & (j.year <= 2023) & (j.n < 100)])) for k in KEYS}
    out["q1vscite"] = {"type": "bubble", "unit": "", "xname": "Papers in Q1 journals (%)", "yname": "Relative citations (100 = average for same field and year)",
        "points": [{"name": k, "color": k, "x": r1(q1s[k]), "y": r1(rel[k] * 100), "size": n_q1[k]} for k in KEYS],
        "caption": "Q1 share against relative citations. 100 = the average for papers in the same OpenAlex field and year across the three universities (papers up to 2023, teams under 100 authors). Bubble size = papers", "stat": out["q1vscite"]["stat"]}
    out["roles"]["type"] = "arrow"
    out["led"]["type"] = "small-area"
    out["partners"].update({"type": "waffle", "groups": [
        {"label": f"{k} {y}", "pct": ps[k][i], "color": k} for k in KEYS for y, i in [("2016", 0), ("2025", 9)]],
        "caption": "Papers with another Indian institution, per 100 papers (2016 vs 2025)"})
    cells = []
    for c in co:
        tot = sum(c["insts"].values()); big = max(c["insts"].items(), key=lambda kv: kv[1])
        cells.append(big[0] if big[1] / tot >= 0.9 else "Shared")
    out["communities"].update({"type": "pictogram", "cells": cells, "legend": [["DU only", "DU"], ["JNU only", "JNU"], ["UoH only", "UoH"], ["Mixed", "Shared"]]})
    out["impact"].update({"type": "path", "paths": [{"name": k, "color": k, "points": [[a, bb, y] for a, bb, y in zip(I[k]["flow_out"], I[k]["flow_in"], con["years"])]} for k in KEYS],
        "xname": "Citations given to Indian institutions", "yname": "Citations received from them"})
    mc = read("stats.json")["most_cited"]["All"][:10]
    out["mostcited"].update({"type": "scatter", "points": [{"name": q["title"][:60], "color": ck(q), "x": q["year"], "y": q["citations"], "size": q["n_authors"]} for q in mc],
        "xname": "Year", "yname": "Citations", "caption": "Ten most-cited papers (bubble size = number of authors)"})
    # ---- after review of the rendered page: use plain forms where the fancy ones hid or crowded information
    out["topics"]["type"] = "bar"
    out["mostcited"]["type"] = "bar"
    out["mostcited"]["caption"] = "Ten most-cited papers (bar colour = university)"
    out["mostcited"]["categories"] = [q["title"][:70] + ("…" if len(q["title"]) > 70 else "") for q in mc]
    out["mostcited"]["series"] = [{"name": "Citations", "color": "All", "data": [q["citations"] for q in mc]}]
    out["mostcited"]["colors"] = [ck(q) for q in mc]
    out["impact"]["type"] = "line"
    out["partners"]["unit"] = ""
    out["regrade"]["categories"] = ["2016–18 actual", "2023–25 actual", "2023–25 old grades"]
    # ---- simple forms for these six
    out["communities"]["type"] = "bar"
    out["partners"]["type"] = "line"
    out["partners"]["unit"] = "% of papers"
    out["chemistry"]["type"] = "line"
    out["expansion"]["type"] = "bar"
    out["expansion"]["series"] = [x for x in out["expansion"]["series"] if x["name"] == "DU"]
    out["expansion"]["caption"] = "DU: change in papers per field, 2016–18 to 2023–25 (teams under 100 authors)"
    # ---- impact factor (OpenAlex 2-year mean citedness of the journal, fixed at collection time)
    jf = g[(g.type == "journal") & g.ifv.notna()]
    uniq = jf.drop_duplicates("openalex_work_id")                    # each paper once, all three universities pooled
    pooled_avg = float(uniq.ifv.mean())                              # average IF over all unique journal papers 2016-2026
    field_avg = uniq.groupby("field").ifv.mean()                     # average IF of papers in the same OpenAlex field
    jf = jf.assign(fav=jf.field.map(field_avg))
    rows_ = [("Above the 3-university average IF (%.1f)" % pooled_avg, lambda x: x.ifv > pooled_avg),
             ("Above the average IF of their own field", lambda x: x.ifv > x.fav),
             ("IF of 5 or more", lambda x: x.ifv >= 5), ("IF of 10 or more", lambda x: x.ifv >= 10)]
    share = {k: [r1(f(jf[jf.inst == k]).mean() * 100) for _, f in rows_] for k in KEYS}
    avg_if = {k: r1(jf[jf.inst == k].ifv.mean()) for k in KEYS}
    sj = jf[jf.n < 100]
    band = lambda lo, hi: sj[(sj.ifv >= lo) & (sj.ifv < hi)].cites.mean()
    out["ifactor"] = {"type": "bar", "horizontal": True, "categories": [c for c, _ in rows_], "unit": "% of the university's journal papers",
        "series": [{"name": k, "color": k, "data": share[k]} for k in KEYS],
        "caption": "Share of journal papers in journals above each impact factor (IF) mark. IF = OpenAlex 2-year mean citedness at collection time; averages are over the three universities' journal papers, 2016–2026, each paper counted once",
        "stat": {"value": f"{share['UoH'][2]}% / {share['DU'][2]}%", "label": "of UoH / DU journal papers are in journals with IF 5 or more", "color": "All"},
        "facts": {"low": r1(band(0, 1)), "high": r1(band(10, 999)), "pooled_avg": r1(pooled_avg), "avg_if": avg_if}}
    # ---- rank chart: the two measures order the universities differently
    rk = lambda vals: {k: int(1 + sum(bool(vals[o] > vals[k]) for o in KEYS)) for k in KEYS}
    r_q, r_c = rk(q1s), rk({k: float(rel[k]) for k in KEYS})
    out["q1vscite"].update({"type": "bump", "categories": ["Share of papers in Q1 journals", "Relative citations (100 = average for the same field and year)"],
        "series": [{"name": k, "color": k, "data": [r_q[k], r_c[k]], "labels": [f"{r1(q1s[k])}%", f"{r1(rel[k]*100)}"]} for k in KEYS],
        "caption": "Rank of each university on the two measures (1 = highest). Papers up to 2023, teams under 100 authors"})
    # ---- team size, hyperauthorship, conference mix, author seniority (2026 is a partial year, so the year charts stop at 2025)
    Y = YEARS[:-1]
    def by_year(df, f):
        return {k: [r1(f(df[(df.inst == k) & (df.year == y)])) for y in Y] for k in KEYS}
    ts = by_year(g[g.n < 100], lambda x: x.n.mean())
    out["teamsize"] = {"type": "line", "x": Y, "unit": "average authors per paper", "ymin": 3.5,
        "series": [{"name": k, "color": k, "data": ts[k]} for k in KEYS],
        "caption": "Average authors per paper, leaving out papers with 100 or more authors. 2026 is a partial year and is left out",
        "stat": {"value": f"{ts['DU'][0]} → {ts['DU'][-1]}", "label": "DU average authors per paper, 2016 → 2025", "color": "DU"}}
    hy = by_year(g, lambda x: x.hyper.astype(float).mean() * 100)
    out["hyper"] = {"type": "line", "x": Y, "unit": "% of papers with 100+ authors",
        "series": [{"name": k, "color": k, "data": hy[k]} for k in KEYS],
        "caption": "Share of each university's papers with 100 or more authors, by year. 2026 is a partial year and is left out",
        "stat": {"value": f"{hy['UoH'][0]}% → {hy['UoH'][-1]}%", "label": "UoH share of papers with 100+ authors, 2016 → 2025", "color": "UoH"}}
    out.update(chemistry_impact(g, YEARS))
    # ---- DU citation network (citation network analysis; see du_citation.py)
    from .du_citation import du_citation_insights
    out.update(du_citation_insights(read("citation.json")))
    dd.write("insights.json", out)


IF_BANDS = [("IF 5 or below", 0, 5), ("IF above 5, below 10", 5, 10), ("IF 10 or more", 10, float("inf"))]


def if_band(v: float) -> str:
    return IF_BANDS[0][0] if v <= 5 else IF_BANDS[1][0] if v < 10 else IF_BANDS[2][0]


def chemistry_impact(g: pd.DataFrame, years: list[int]) -> dict:
    """The chemistry Q1 finding redone with journal impact factor, and the two compared.

    g: one row per (university, paper) with inst, year, field, type, q (SCImago quartile of the paper's year) and
    ifv (OpenAlex 2-year mean citedness of the journal, one value per journal measured at collection). Bands: IF 5 or
    below, above 5 and below 10, 10 or more. Because the IF is fixed per journal, a change in the IF shares over the years
    can only come from papers moving between journals, while a change in Q1 share also includes journals re-graded.
    """
    r1 = lambda v: round(float(v), 1) + 0.0  # + 0.0 turns -0.0 into 0.0
    chem = g[(g.type == "journal") & (g.field == "Chemistry")]
    cf = chem[pd.to_numeric(chem.ifv, errors="coerce").notna()].assign(ifv=lambda x: pd.to_numeric(x.ifv, errors="coerce"))
    cq = chem[chem.q.isin(["Q1", "Q2", "Q3", "Q4"])]

    def yearly(df, f):
        return {k: [r1(f(df[(df.inst == k) & (df.year == y)])) if len(df[(df.inst == k) & (df.year == y)]) else None for y in years] for k in KEYS}

    above5 = yearly(cf, lambda x: (x.ifv > 5).mean() * 100)
    period_share = lambda df, k, p: r1((df[(df.inst == k) & df.year.between(*p)].ifv > 5).mean() * 100)
    above10 = yearly(cf, lambda x: (x.ifv >= 10).mean() * 100)
    out = {"chemistry_if": {
        "type": "line", "x": years, "unit": "% of chemistry papers in journals with IF above 5",
        "series": [{"name": k, "color": k, "data": above5[k]} for k in KEYS],
        "caption": "Chemistry papers in journals with impact factor above 5, by year (same papers and layout as the Q1 chart; IF = OpenAlex 2-year mean citedness at collection)",
        "stat": {"value": f"{period_share(cf, 'UoH', (2016, 2018))}% → {period_share(cf, 'UoH', (2023, 2025))}%",
                 "label": "UoH chemistry papers in journals with IF above 5, 2016–18 → 2023–25 (its Q1 share fell)", "color": "UoH"},
        "facts": {"above10": above10, "bands": {k: {name: r1(cf[cf.inst == k].ifv.map(lambda v: if_band(v) == name).mean() * 100)
                                                         for name, _, _ in IF_BANDS} for k in KEYS}}}}
    # early vs late: percentage-point change in each measure
    early, late = (2016, 2018), (2023, 2025)
    def share(df, k, period, f):
        x = df[(df.inst == k) & df.year.between(*period)]
        return float(f(x).mean() * 100) if len(x) else float("nan")
    measures = [("Papers in Q1 journals", cq, lambda x: x.q == "Q1"),
                ("Papers in journals with IF above 5", cf, lambda x: x.ifv > 5),
                ("Papers in journals with IF 10 or more", cf, lambda x: x.ifv >= 10)]
    change = {k: [r1(share(df, k, late, f) - share(df, k, early, f)) for _, df, f in measures] for k in KEYS}
    levels = {k: [[r1(share(df, k, early, f)), r1(share(df, k, late, f))] for _, df, f in measures] for k in KEYS}
    both = chem[chem.q.isin(["Q1", "Q2", "Q3", "Q4"]) & pd.to_numeric(chem.ifv, errors="coerce").notna()].assign(ifv=lambda x: pd.to_numeric(x.ifv, errors="coerce"))
    q1 = both[both.q == "Q1"]
    out["chemistry_compare"] = {
        "type": "bar", "horizontal": True, "unit": "percentage-point change, 2016–18 to 2023–25",
        "categories": [m[0] for m in measures],
        "series": [{"name": k, "color": k, "data": change[k]} for k in KEYS],
        "caption": "Chemistry: change in the share of papers by each measure, 2016–18 to 2023–25 (Q1 = SCImago grade of the paper's year; IF fixed per journal)",
        "stat": {"value": f"{change['UoH'][0]:+} / {change['UoH'][1]:+} pts", "label": "UoH chemistry: Q1 share / IF > 5 share, change 2016–18 → 2023–25", "color": "UoH"},
        "facts": {"levels": levels, "q1_with_if_5_or_below": r1((q1.ifv <= 5).mean() * 100) if len(q1) else None,
                  "if_above5_in_q1": r1((both[both.ifv > 5].q == "Q1").mean() * 100) if len(both[both.ifv > 5]) else None},
    }
    return out
