from dpcn_mapping.ror_review import is_candidate


def org(display, *aliases):
    names = [{"value": display, "types": ["ror_display", "label"]}]
    names += [{"value": alias, "types": ["alias"]} for alias in aliases]
    return {"names": names}


def test_exact_part_is_a_candidate():
    assert is_candidate("Bharati College, University of Delhi, India", org("University of Delhi"))
    assert is_candidate("Dept. of CSE; Shiv Nadar Institution of Eminence, Noida",
                        org("Shiv Nadar University", "Shiv Nadar Institution of Eminence"))


def test_generic_name_inside_a_longer_one_is_not():
    assert not is_candidate("Kalinga Institute of Medical Sciences, Bhubaneswar",
                            org("Institute of Medical Sciences"))


def test_department_names_are_not():
    assert not is_candidate("Department of Biotechnology, Jamia Hamdard", org("Department of Biotechnology"))
