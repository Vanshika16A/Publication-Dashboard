# Reproducing the Group 16 dataset

Everything in `data/processed/` and `data/builds/` is produced by code from three inputs:
a sealed OpenAlex snapshot, the reference files in `data/external/`, and
`config/build.toml`. Same inputs, same code and same package versions give the same output.

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.lock   # exact versions used (requirements.txt has ranges)
```

Run every command with `.venv/bin/python`. Each build records the Python and pandas
versions in its `build_manifest.json`. A free OpenAlex API key in `.env` (gitignored) as
`OPENALEX_API_KEY=...` is needed only to collect a new snapshot.

## Commands

```bash
scripts/run_pipeline.sh                                    # collect (resumable), seal the snapshot, build
scripts/progress.sh                                        # collection progress
PYTHONPATH=src .venv/bin/python -m dpcn_mapping.build_dataset   # rebuild from the sealed snapshot (no API calls), then audit
PYTHONPATH=src .venv/bin/python -m dpcn_mapping.audit           # re-run the audit of the latest build
PYTHONPATH=src .venv/bin/python -m pytest                       # schema and validation tests
PYTHONPATH=src .venv/bin/python -m dpcn_mapping.duckdb_setup    # refresh the DuckDB views (stop the UI first)
```

External lookups (network; each writes raw responses and a manifest under `data/external/`,
resumes where it stopped, and changes the dataset only through a review file in `reviews/`):

```bash
PYTHONPATH=src .venv/bin/python -m dpcn_mapping.collect_ror         # ROR affiliation matches (D-015)
PYTHONPATH=src .venv/bin/python -m dpcn_mapping.ror_review          # write/refresh reviews/ror_matches.csv
PYTHONPATH=src .venv/bin/python -m dpcn_mapping.affiliation_review  # refresh the UoH/JNU affiliation review files (D-018)
PYTHONPATH=src .venv/bin/python -m dpcn_mapping.collect_crossref    # Crossref affiliation check (D-014)
PYTHONPATH=src .venv/bin/python -m dpcn_mapping.verify_ror_rows     # Crossref check of ROR rows (D-022)
PYTHONPATH=src .venv/bin/python -m dpcn_mapping.collect_doi         # Crossref DOI search (D-024); --check = no network
```

## Rules

1. **Raw snapshots never change.** A snapshot is complete when `MANIFEST.json` exists; its
   files are then read-only. To re-collect, set a new `collection.snapshot_id` (a date) in
   `config/build.toml` and run the pipeline.
2. **Derived files are rebuilt, never edited.** A build regenerates `data/processed/*`.
3. **Every choice is in the config and the decision log.** Change `config/build.toml`, add
   or supersede an entry in `docs/decisions.md`, then rebuild. Audit heuristics (regular
   expressions, ID lists) are in the `[audit]` section.
4. **Every build is validated, recorded and audited.** If validation fails, the deliverable
   is not overwritten. Each build writes `data/builds/<build_id>/`: build manifest (snapshot,
   config, code, input and list-file hashes, environment), coverage report, diff against the
   previous deliverable and audit (`audit.md`, `audit.json`). List files (review lists, drop and
   repair logs) go to `data/builds/latest/`, overwritten by every build. `data/builds/LATEST` names
   the newest build. A rerun whose outputs are byte-identical to the latest build makes no
   new folder; it is appended to that build's `reproduced.log`, which doubles as proof the
   build reproduces. Column definitions are in `docs/codebook.md`.
5. **Rebuild or re-collect?** Rebuild (about 2 minutes) after any config, code, SCImago or
   CORE change. Re-collect into a new snapshot only for a new data date or a new query scope.
6. **Git:** commit code, config, docs, `requirements.lock`, `data/builds/`,
   `data/metadata/snapshots/` (a copy of each snapshot's `MANIFEST.json`, written when the
   snapshot is sealed) and `data/external/` with its `SOURCES.md`. Raw snapshots,
   the enriched file and logs are gitignored. Commit `group16_data.csv` only at milestones.

## What code cannot reproduce

- **SCImago files** were downloaded by hand (scimagojr.com blocks scripts). Origin, date and
  sha256 are in `data/external/SOURCES.md`, and every build manifest records the hashes, so a
  different download would be detected.
- **OpenAlex changes over time.** A new collection gives different citation counts and
  author IDs. Exact reproduction needs the sealed snapshot itself, which is about 10 GB and
  currently stored only on one laptop; back it up.
- **Institution IDs** were checked once by hand against ROR (D-001); they are fixed in
  `collect_openalex.py` and recorded in the snapshot manifest.
