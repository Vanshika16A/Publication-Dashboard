"""Command line: python -m collector <command>

    run        collect (resumable), build, then clean
    collect    only download from OpenAlex / CORE (resumable)
    build      turn the download into a first dataset in output/build/ (no internet needed)
    clean      clean output/build/ into the final dataset in output/ (no internet needed)
    networks   network files from the cleaned dataset, into output/networks/
    dashboard-data   JSON files for the dashboard (dashboard/public/data/), from output/ and output/networks/
    du-insights      add the DU citation network findings to insights.json, from citation.json only (no raw data needed)
    status     show what is downloaded

Options: --years 2016-2026   --cache-dir PATH   --out-dir PATH   --no-scimago
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .collect import STEPS, Run, collect, load_state, read_jsonl
from .config import END_YEAR, GROUP, OUTPUT_DIR, START_YEAR


def status(run: Run) -> None:
    print(f"cache: {run.raw_dir}")
    for step in ("works", "full-authors", "linked-refs", "linked-citers", "authors", "sources"):
        state = load_state(run, step)
        if not state:
            print(f"  {step:14s} not started")
        elif state.get("done"):
            print(f"  {step:14s} done")
        else:
            print(f"  {step:14s} in progress {state.get('records', state.get('next_batch', ''))}"
                  f"{'/' + str(state['expected']) if state.get('expected') else ''}")
    n = sum(1 for _ in read_jsonl(run.path("works.jsonl")))
    print(f"  works cached: {n}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m collector", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["run", "collect", "build", "clean", "networks", "dashboard-data", "du-insights", "status"])
    parser.add_argument("--years", default=f"{START_YEAR}-{END_YEAR}", help="e.g. 2016-2026 (use a short range to test)")
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None, help="final output folder (default collector/data/output)")
    parser.add_argument("--no-scimago", action="store_true", help="build even without SCImago files (quartiles blank)")
    args = parser.parse_args(argv)
    start, _, end = args.years.partition("-")
    run = Run(int(start), int(end or start), args.cache_dir)
    out_dir = args.out_dir or (OUTPUT_DIR if args.years == f"{START_YEAR}-{END_YEAR}" else OUTPUT_DIR / args.years)
    build_dir = out_dir / "build"

    if args.command == "status":
        status(run)
        return 0
    if args.command in {"run", "collect"}:
        code = collect(run, STEPS)
        if code:
            return code
    if args.command in {"run", "build"}:
        from .build import build  # pandas is only needed from here on
        build(run, build_dir, require_scimago=not args.no_scimago)
    if args.command in {"run", "clean"}:
        from .clean import clean
        clean(build_dir, out_dir, run)
        print(f"Cleaned dataset: {out_dir / f'group{GROUP}_data.csv'}")
    if args.command == "networks":
        import pandas as pd
        from .build import load_cache
        from .networks import write_networks
        source = out_dir / f"group{GROUP}_data_extended.csv"
        if not source.exists():
            raise SystemExit(f"{source} not found: run `python -m collector clean` first")
        frame = pd.read_csv(source, dtype=str, keep_default_na=False)
        for column in ("year", "citations", "n_authors"):
            frame[column] = frame[column].astype(int)
        networks_dir = out_dir / "networks"
        networks_dir.mkdir(parents=True, exist_ok=True)
        counts = write_networks(frame, load_cache(run), networks_dir)
        print(f"networks: {counts}\nFiles are in {networks_dir}")
    if args.command == "dashboard-data":
        from .dashboard_data import build_dashboard_data
        build_dashboard_data(run, out_dir)
    if args.command == "du-insights":
        from .dashboard_data import DASHBOARD_DATA
        from .du_citation import add_to_insights
        add_to_insights(DASHBOARD_DATA)
    return 0


if __name__ == "__main__":
    sys.exit(main())
