"""Offline tests for the parts of the collector that decide what ends up in the dataset."""

from __future__ import annotations

import pandas as pd

from collector import quartiles
from collector.build import AffiliationRules, classify, clean_doi, find_title_duplicates, merge_author_ids
from collector.collect import reduce_authorships

JNU, UOH, DU = "I152429107", "I36893310", "I110166357"


def inst(inst_id: str, name: str, lineage: list[str] | None = None, country: str = "IN") -> dict:
    return {"id": f"https://openalex.org/{inst_id}", "display_name": name, "country_code": country,
            "lineage": [f"https://openalex.org/{x}" for x in (lineage or [inst_id])]}


def authorship(institutions: list[dict], strings: list[str], affiliations: list[dict] | None = None) -> dict:
    return {"author": {"id": "https://openalex.org/A1", "display_name": "A B", "orcid": None},
            "author_position": "first", "institutions": institutions, "raw_affiliation_strings": strings,
            "affiliations": affiliations if affiliations is not None else [
                {"raw_affiliation_string": s, "institution_ids": [i["id"] for i in institutions]} for s in strings]}


# ---- unstated affiliation (OpenAlex assigns an institution but the author wrote nothing)

def test_affiliation_with_text_is_stated():
    authors, _ = reduce_authorships([authorship([inst(JNU, "JNU")], ["School of Physics, JNU, New Delhi"])])
    assert authors[0]["t"][JNU]["strings"] == ["School of Physics, JNU, New Delhi"]


def test_institution_without_text_is_unstated():
    authors, _ = reduce_authorships([authorship([inst(JNU, "JNU")], [], affiliations=[])])
    assert authors[0]["t"][JNU]["strings"] == []


def test_text_only_counts_for_the_institution_it_names():
    two = [inst(JNU, "JNU"), inst("I1", "IIT Delhi")]
    affs = [{"raw_affiliation_string": "IIT Delhi", "institution_ids": ["https://openalex.org/I1"]}]
    authors, _ = reduce_authorships([authorship(two, ["IIT Delhi"], affiliations=affs)])
    assert authors[0]["t"][JNU]["strings"] == []  # JNU was inferred; the text names IIT Delhi


def test_child_institution_counts_toward_parent():
    college = inst("I999", "Hansraj College", lineage=["I999", DU])
    authors, institutions = reduce_authorships([authorship([college], ["Hansraj College, Delhi"])])
    assert DU in authors[0]["t"] and "I999" in institutions


def test_rules_drop_unstated_and_lookalikes():
    rules = AffiliationRules()
    assert rules.judge(JNU, ["Jawaharlal Nehru University, Delhi"])[0]
    assert not rules.judge(JNU, [])[0]
    assert not rules.judge(JNU, ["Jawaharlal Nehru Technological University, Hyderabad"])[0]
    assert not rules.judge(JNU, ["Jawaharlal Nehru Centre for Advanced Scientific Research"])[0]
    assert rules.judge(JNU, ["JNCASR; Jawaharlal Nehru University"])[0]  # also names JNU
    assert not rules.judge(UOH, ["Osmania University, Hyderabad"])[0]
    assert rules.judge(UOH, ["School of Chemistry, University of Hyderabad"])[0]
    assert rules.judge(DU, ["Hansraj College"])[0]


# ---- classification, DOI

def test_classify():
    def work(kind, source):
        return {"type": kind, "source": {"type": source}}
    assert classify(work("article", "journal")) == "journal"
    assert classify(work("article", "conference")) == "conference"
    assert classify(work("conference-paper", "book series")) == "conference"
    assert classify(work("article", "repository")) == ""
    assert classify(work("article", "ebook platform")) == ""
    assert classify(work("letter", "journal")) == ""      # letters are excluded
    assert classify(work("review", "journal")) == ""      # reviews are excluded


def test_letters_and_reviews_are_never_downloaded():
    from collector.config import CONFIG
    assert not {"letter", "review"} & set(CONFIG["collection"]["work_types"])


def test_clean_doi():
    assert clean_doi("https://doi.org/10.1/abc?x=1") == "https://doi.org/10.1/abc"
    assert clean_doi("https://doi.org/10.1/abc.html") == "https://doi.org/10.1/abc"
    assert clean_doi("") == ""


# ---- duplicates

def make_work(work_id, title, author_ids, citations=0, year=2020):
    return {"title": title, "year": year, "cited_by_count": citations, "doi": "", "source": {"name": "", "type": "journal"},
            "authors": [{"id": a} for a in author_ids]}


def test_title_duplicates_need_a_shared_author():
    long_title = "Synthesis and characterisation of novel nanostructured materials"
    works = {"W1": make_work("W1", long_title, ["A1"], 5), "W2": make_work("W2", long_title, ["A1", "A2"], 9),
             "W3": make_work("W3", long_title, ["A9"], 1)}
    drop, review = find_title_duplicates(works, 21)
    assert drop == {"W1"}                      # W2 has more citations; W3 is a different author group
    assert {r["openalex_work_id"] for r in review} == {"W1", "W2", "W3"}


def test_authors_with_same_orcid_are_merged():
    works = {"W1": {"authors": [{"id": "A1", "name": "R. Kumar", "orcid": "https://orcid.org/0000-0001-2345-6789"}]},
             "W2": {"authors": [{"id": "A2", "name": "Rakesh Kumar", "orcid": "0000-0001-2345-6789"}]},
             "W3": {"authors": [{"id": "A3", "name": "R. Kumar", "orcid": ""}]}}
    profiles = {"A1": {"works_count": 3, "name": "R. Kumar"}, "A2": {"works_count": 40, "name": "Rakesh Kumar"}}
    canonical, display, review = merge_author_ids(works, profiles, True)
    assert canonical["A1"] == canonical["A2"] == "A2" and canonical["A3"] == "A3"
    assert display["A2"] == "Rakesh Kumar" and len(review) == 2


# ---- quartiles

def write_scimago(folder, year, rows):
    header = "Rank;Sourceid;Title;Type;Issn;SJR;SJR Best Quartile;Cites / Doc. (2years)\n"
    (folder / f"scimagojr_{year}.csv").write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def test_scimago_lookup(tmp_path):
    write_scimago(tmp_path, 2020, ["1;1;Nature Physics;journal;17452473, 17452481;12,5;Q1;15,2",
                                   "2;2;Odd Journal;journal;11112222;0,1;-;0,5"])
    write_scimago(tmp_path, 2022, ["1;1;Nature Physics;journal;17452473;13,0;Q1;16,0",
                                   "2;2;Odd Journal;journal;11112222;0,2;Q4;0,6"])
    tables = quartiles.load_scimago(tmp_path)
    hit = quartiles.scimago_lookup(tables, ["1745-2481"], "x", 2020)
    assert hit["quartile"] == "Q1" and hit["source"] == "SCImago 2020" and hit["sjr"] == 12.5
    newer = quartiles.scimago_lookup(tables, ["1745-2473"], "", 2026)
    assert newer["source"] == "SCImago 2022 (nearest year)"
    gap = quartiles.scimago_lookup(tables, ["1111-2222"], "", 2020)  # "-" in 2020, Q4 in 2022
    assert gap["quartile"] == "Q4" and gap["source"] == "SCImago 2022 (nearest year)"
    by_title = quartiles.scimago_lookup(tables, [], "The Nature Physics", 2022)
    assert by_title["quartile"] == "Q1" and "title match" in by_title["source"]
    assert quartiles.scimago_lookup(tables, ["9999-9999"], "Unknown", 2020)["quartile"] == ""


def test_core_lookup(tmp_path):
    path = tmp_path / "core.csv"
    path.write_text('1,International Conference on Machine Learning,ICML,ICORE2026,A*,Yes,4611\n'
                    '2,Some Workshop,SW,ICORE2026,Australasian B,Yes,4611\n', encoding="utf-8")
    table = quartiles.load_core(path)
    assert quartiles.core_lookup(table, "2021 International Conference on Machine Learning")[0] == "A*"
    assert quartiles.core_lookup(table, "Proceedings of Something Else (ICML)")[0] == "A*"
    assert quartiles.core_lookup(table, "ICML")[0] == "A*"
    assert quartiles.core_lookup(table, "Some Workshop")[0] == ""  # non-standard rank ignored
    assert quartiles.core_lookup(table, "Unrelated Conference")[0] == ""


def test_jcr_best_quartile(tmp_path):
    (tmp_path / "jcr.csv").write_text(
        'Journal Data Filtered By: Selected JCR Year: 2023\n'
        'Journal name,JCR Abbreviation,Publisher,ISSN,eISSN,Category,Total Citations,2023 JIF,JIF Quartile\n'
        'NATURE PHYSICS,NAT PHYS,X,1745-2473,1745-2481,"Physics, Multidisciplinary",1,19.6,Q1\n'
        'NATURE PHYSICS,NAT PHYS,X,1745-2473,1745-2481,"Physics, Applied",1,19.6,Q2\n', encoding="utf-8")
    table = quartiles.load_jcr(tmp_path)
    assert table["17452481"] == {"jif": 19.6, "jif_quartile": "Q1", "jif_year": 2023}
    assert pd.isna(quartiles.jcr_lookup(table, ["0000-0000"])["jif"])


# ---- cleaning step

def test_clean_author():
    from collector.clean import clean_author
    assert clean_author("VED PRAKASH GUPTA") == "Ved Prakash Gupta"
    assert clean_author("D. K.") == "D. K."                          # initials only: left alone
    assert clean_author("G. CHAUHAN") == "G. Chauhan"
    assert clean_author("Rakesh Kumar  Sonker1") == "Rakesh Kumar Sonker"
    assert clean_author("Shailesh ORCID 0000-0003-2781-5173") == "Shailesh"
    assert clean_author("Manish Kumar (50435)") == "Manish Kumar"
    assert clean_author("Muthappa Senthil‐Kumar") == "Muthappa Senthil-Kumar"
    assert clean_author("Jayanti Vaishnav⧧") == "Jayanti Vaishnav"
    assert clean_author("Dr. D. D. Aggarwal Dr. D. D. Aggarwal") == "D. D. Aggarwal"
    assert clean_author("Prof. Anil Kumar Chaudhary") == "Anil Kumar Chaudhary"
    assert clean_author("PARAGMONI DAS -") == "Paragmoni Das"
    assert clean_author("MS Bhatia") == "MS Bhatia"                  # initials, not "Ms"
    assert clean_author("Ms Garima") == "Garima"
    assert clean_author("Shri Ram Sharma") == "Shri Ram Sharma"
    assert clean_author("Juan José Gómez-Navarro") == "Juan José Gómez-Navarro"


def test_clean_title():
    from collector.clean import clean_title
    assert clean_title("Memory in the rat.") == "Memory in the rat"
    assert clean_title("A new species, Aus bus sp.") == "A new species, Aus bus sp."
    assert clean_title("Results from Smith et al.") == "Results from Smith et al."
    assert clean_title("Isolated from strain B.") == "Isolated from strain B."
    assert clean_title("Wait for it...") == "Wait for it..."


# ---- our own papers' filter

def test_scope_filter():
    from collector.collect import scope_filter
    scope = scope_filter(["31", "17"], 2016, 2026)
    assert scope == "publication_year:2016-2026,primary_topic.field.id:17|31,type:article|conference-paper"
