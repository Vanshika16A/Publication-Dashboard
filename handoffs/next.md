# Handoff: state and next steps

Last updated 2026-10-13. Commands: `docs/reproducing.md`. Data choices: `docs/decisions.md` (D-xxx).
Columns: `docs/codebook.md`.

| File | Contents |
|---|---|
| [todo.md](todo.md) | Open questions awaiting a decision |
| [reviews.md](reviews.md) | Manual review checklist |
| [gaps.md](gaps.md) | Remaining gaps and duplicates, with counts |
| [risks.md](risks.md) | Risks and definitions to state in the report |
| [done.md](done.md) | Completed work |

## Current state

- **Snapshot** `data/raw/openalex/2026-10-08/`: sealed, read-only, about 10 GB, only on this laptop.
- **Deliverable** `data/processed/group16_data.csv`: 162,361 rows, 67,529 papers (build 20261012T134558Z, named in
  `data/builds/LATEST`), 2016–2026. Validation and 21 tests pass.
- **Rebuild** (no API calls, about 2.5 min): `PYTHONPATH=src .venv/bin/python -m dpcn_mapping.build_dataset`.
- **Inspect** with DuckDB: `scripts/duckdb_ui.sh`, checks in `scripts/quality_checks.sql`.
  After a build, stop the UI and run `python -m dpcn_mapping.duckdb_setup`.

## Decisions still open

- [ ] **D-004 DU medical colleges** in or out (32,577 DU rows depend on it). To exclude, add
  I39190216, I172982924, I114546181 to `scope.exclude_institution_ids` and rebuild.
- [ ] **D-013 borderline types**: group vote (index-source articles, no-source articles, "other",
  preprints in journals).
- [ ] **SCImago gaps**: 1,456 papers are in SCImago only in other years. Recommendation: keep blank.

## Next work

1. [ ] **Open questions** in [todo.md](todo.md) and remaining reviews in [reviews.md](reviews.md); then rebuild.
2. [ ] **Faculty rosters and departments** (IRINS in a browser, or department pages); until then
   authors are "affiliated authors" (D-007).
3. [ ] **CORE matching**: 144 of 9,933 conference rows have a rank; acronym matching with review.
4. [ ] **Spot-check** about 50 random rows against `raw_affiliation`.
5. [ ] **Housekeeping**: `git init` inside A2; back up the snapshot and `data/external/ror/`
   (184 MB) outside the laptop; commit `group16_data.csv` only at milestones.
