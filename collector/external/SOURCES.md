# External reference files

Third-party lookup tables used by the build. They are not produced by our pipeline, so
their origin is recorded here. Every build also records each file's sha256 in
`data/builds/<build_id>/build_manifest.json`, so a changed file is detected.

OpenAlex data is not listed here: it is collected by code into
`data/raw/openalex/<snapshot_id>/`, and each snapshot's manifest is committed in
`data/metadata/snapshots/<snapshot_id>.json`.

## CORE conference rankings

- **File:** `core/CORE_ICORE2026.csv` (987 rows, no header; columns: id, title, acronym,
  source, rank, primary flag, field-of-research codes)
- **Source:** CORE portal export, edition ICORE2026
  `https://portal.core.edu.au/conf-ranks/?search=&by=all&source=ICORE2026&sort=arank&page=1&do=Export`
- **Method:** downloaded by code: `python -m dpcn_mapping.collect_openalex core`
- **Date:** 2026-10-08 (IST)
- **Record:** `core/CORE_ICORE2026.source.json` (URL, time, rows, sha256)
- **sha256:** `8da30ebe4e6a40dc00c8c1aff926373a43f2cdcb90a6709fddd2e6b2e7126569`

## SCImago Journal Rank

- **Files:** `scimago/scimagojr_2016.csv` … `scimagojr_2025.csv` (one per year;
  `;`-separated; columns used: `Issn`, `SJR Best Quartile`)
- **Source:** https://www.scimagojr.com/journalrank.php, year selected, "Download data"
- **Method:** downloaded by hand in a browser (the site blocks scripted downloads with
  HTTP 403), then saved under these names
- **Date:** 2026-10-08 (file times 13:48 IST)

| File | sha256 |
|---|---|
| scimagojr_2016.csv | `d22aa565091728fcdc952dc171d60113bf25df4fb1ab08248c0a2bc4379713eb` |
| scimagojr_2017.csv | `fd66a8f4d2f14d65b353907d326555380ff817fae04d382b51c34f63607d510d` |
| scimagojr_2018.csv | `88ffd101a7e823cc794a7cff802b0c906d2dc05c046066e5ab7fa99ee2a293c3` |
| scimagojr_2019.csv | `afec64c67c49a880d1383532156499e2cb622538ce3b7665e158d07558f46fd8` |
| scimagojr_2020.csv | `61182b37489df532352ce6b26123432a440120ce8d290218003534110d0e5f80` |
| scimagojr_2021.csv | `98286447a8fc346f4ad5baf5b3ff747a607fcbc3714a4d91a6b43ea5771985e1` |
| scimagojr_2022.csv | `a9226c14939f145510fda78f806c968f8b962a3bb11cbf98d0d64865be2f7eb7` |
| scimagojr_2023.csv | `5d0cd25797e6f7eb9e6fddf8cad809fabbaff1b46961145bca17dea363149524` |
| scimagojr_2024.csv | `5054289ee269d611a63322bcc71226e8430b43e8535a1fd4577b630af5a5bd18` |
| scimagojr_2025.csv | `6f20399957173a13e3c1729a5fb3b5821844ba75e8d640c8b3040ab19a6f7180` |

When a file here is replaced or added, update this page and add an entry to
`docs/decisions.md`.
