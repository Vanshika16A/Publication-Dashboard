import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dpcn_mapping.build_dataset import coauthor_status, compact_authorships, indian_institutions

UOH, JNU = "I36893310", "I152429107"


def inst(inst_id, country="IN", parent=None):
    lineage = [f"https://openalex.org/{inst_id}"] + ([f"https://openalex.org/{parent}"] if parent else [])
    return {"id": f"https://openalex.org/{inst_id}", "display_name": inst_id, "country_code": country,
            "lineage": lineage}


def author(position, *institutions, raw=()):
    return {"author": {"id": f"https://openalex.org/A{position}", "display_name": f"Author {position}"},
            "institutions": list(institutions), "raw_affiliation_strings": list(raw)}


def status(authorships, target=UOH, ror=None):
    compact = compact_authorships(authorships, ror)
    partners = indian_institutions(compact["indian"], target)
    return coauthor_status(partners, compact["n_authorships"], compact["n_unlinked"], compact["has_foreign"])


def test_status_rules_in_order():
    uoh_school = inst("I999", parent=UOH)  # a UoH child institution
    assert status([author(1, inst(UOH)), author(2, inst("I1"))]) == "listed"
    assert status([author(1, inst(UOH))]) == "single_author"
    # An unlinked co-author makes the empty value uncertain, even next to a foreign co-author.
    assert status([author(1, inst(UOH)), author(2, inst("I2", "US")), author(3, raw=["Somewhere"])]) == \
        "unknown_affiliation"
    assert status([author(1, inst(UOH)), author(2, inst("I2", "US"))]) == "foreign_only"
    assert status([author(1, inst(UOH)), author(2, uoh_school)]) == "same_institution_only"
    # Another assigned institution is a partner (D-008).
    assert status([author(1, inst(UOH)), author(2, inst(JNU))]) == "listed"


def test_ror_match_fills_unlinked_coauthor_but_adds_no_row():
    raw = "School of Physics, University of Hyderabad"
    authorships = [author(1, inst(JNU)), author(2, raw=[raw])]
    ror = {raw: {"id": UOH, "display_name": "University of Hyderabad", "country_code": "IN", "lineage": [UOH]}}
    assert status(authorships, target=JNU) == "unknown_affiliation"
    assert status(authorships, target=JNU, ror=ror) == "listed"
    compact = compact_authorships(authorships, ror)
    assert [a["id"] for a in compact["affiliated"]] == ["A1"]  # no UoH row from the ROR match
    assert compact["ror_resolved"] == 1
    assert compact["ror_assigned"] == [(raw, UOH)]
    # OpenAlex links take precedence: a linked authorship is never looked up.
    linked = compact_authorships([author(1, inst(JNU), raw=[raw])], ror)
    assert linked["ror_resolved"] == 0 and len(linked["indian"]) == 1
