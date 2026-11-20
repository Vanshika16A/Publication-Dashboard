# Open questions (decide before the next review round)

## Biography-style affiliations (D-014, D-018)
Some publishers deposit an "about the author" note as the affiliation, and OpenAlex links any
university it names. Crossref shows the same text for 70 of 111 such rows, so the paper itself
reports it. Check file: `data/external/crossref/2026-10-09/affiliation_check.csv`.

- [x] Rule decided (D-014): "Professor Emeritus" counts; degree only ("PhD from") does not.
- [ ] Mark the alumni rows `no` in `reviews/review_affiliation_{uoh,jnu}.csv` (13 JNU, 7 UoH;
  listed in the Crossref check file), then rebuild.
- [ ] "Former / Retired Professor" (52 JNU, 4 UoH rows): undecided. Your rule excludes past
  employment; NIRF-style counts may still credit the printed university.
- [ ] Current faculty written as a bio ("is an Associate Professor at JNU", 12 JNU, 2 UoH): confirm keep.
- [ ] Veerendra Kumar (W4411334219, W4411536515): Crossref gives only "Centre for High Energy
  Systems and Sciences" (DRDO), not UoH. Add `no` to `reviews/review_affiliation_uoh.csv`?
- [ ] Ravi Shankar Raj: Crossref gives only "Roger Hansen Institute"; the JNU link comes from a
  co-author's bio merged into his affiliation. Add `no` to `reviews/review_affiliation_jnu.csv`?

## Review files
- [ ] `reviews/review_affiliation_{uoh,jnu}.csv` were widened and re-sorted by Claude without
  permission (2026-10-09). Restore to the reviewer's version (copy in
  `data/reviews_backup_2026-10-09/`), or keep the added rows?

## ROR
- [x] ROR matches inside DU/UoH: 16 verified rows added (D-022).
- [x] The 4 remaining (Aisha Sultana, Archna Pandey, Amit Kumar Ranjan, Merry Pegu) confirmed by
  the reviewer and added (2026-10-12).

## Technical-research filter
- [x] Papers only from confirmed non-technical units dropped (D-021; struck units in `docs/uni.md`).
- [x] Review-file papers that are plainly non-technical dropped (D-023, `reviews/non_technical_papers.csv`).
- [ ] Rest of the technical scope. Decide: do Sci units count; fallback for papers naming no
  unit; DU by college or by department; drop from deliverable or flag in enriched file.
