# Manual review checklist

Build review lists in `data/builds/latest/` are rewritten by every build. Record decisions in a
copy under `reviews/` (committed) with `decision` (yes/no) and `note` columns. The build reads
`reviews/ror_matches.csv`, `reviews/ror_assigned_rows.csv`, the two affiliation files, title
duplicates, split authors, `reviews/non_technical_papers.csv` and `reviews/review_doi_matches.csv`.

- [x] **`reviews/ror_assigned_rows.csv`**: 20 verified and applied (D-022).
- [x] **`reviews/ror_matches.csv`**: 204 decided (123 yes); applied.
- [ ] **`reviews/review_affiliation_uoh.csv`** (145; 144 decided, 1 open) and
  **`reviews/review_affiliation_jnu.csv`** (92; 79 decided, 13 open): is the author really at
  UoH/JNU on that paper? New rows: text not naming the institution (CHESS, Osmania, GITAM, EFL…)
  and biographies (alumni, former/retired/emeritus). `no` removes only that author's link (D-018).
  Rerun `python -m dpcn_mapping.affiliation_review` after rebuilds; decisions are kept.
- [x] **`reviews/review_title_duplicates.csv`**: 405 groups same paper, 15 different; applied (D-019).
- [x] **`reviews/review_split_authors.csv`**: 1,364 same person, 116 different; applied as `person_id` (D-020).
- [x] **`reviews/non_technical_papers.csv`**: 460 papers listed and dropped (D-023, D-024).
- [ ] **`reviews/review_doi_matches.csv`**: 8 `copy` applied (D-024); 11 weak candidates blank
  (optional: mark `yes` only if title, year, venue and author all agree).
- [ ] **`identical_rows_audit.csv`** (628, optional): dropped copies that might be two namesakes (D-005).
- [ ] **`excluded_works_summary.csv`**: group vote on D-013 borderline types.
