#!/usr/bin/env bash
# End-to-end, resumable data collection for Group 16.
#
# Runs every collection step in order for the snapshot named by collection.snapshot_id
# in config/build.toml, seals it (MANIFEST.json), then builds data/processed/group16_data.csv.
# Each step saves its progress, so this script can be killed (shutdown, sleep,
# exhausted OpenAlex budget) and simply started again. Optional cron: run it at boot
# and every hour; a lock makes sure only one copy runs at a time.
#
#   scripts/run_pipeline.sh            run (or resume) the pipeline
#   scripts/progress.sh                show progress
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$REPO/.venv/bin/python}"
LOG_DIR="$REPO/logs"
LOG="$LOG_DIR/pipeline.log"
LOCK="$LOG_DIR/pipeline.lock"

mkdir -p "$LOG_DIR"
cd "$REPO" || exit 1
export PYTHONPATH="$REPO/src"
SNAPSHOT_ID="$("$PYTHON" -c 'from dpcn_mapping.config import CONFIG; print(CONFIG["collection"]["snapshot_id"])')"
DONE_MARKER="$REPO/data/raw/openalex/$SNAPSHOT_ID/MANIFEST.json"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

exec 9> "$LOCK"
if ! flock -n 9; then
    exit 0  # another run holds the lock
fi
# A collector started by hand (outside this script) must not run twice.
if pgrep -f "dpcn_mapping.collect_openalex" > /dev/null; then
    log "collector already running outside the pipeline; skipping this run"
    exit 0
fi
if [[ -f "$DONE_MARKER" ]]; then
    exit 0  # snapshot already sealed
fi

log "pipeline run started (snapshot $SNAPSHOT_ID)"
for step in works full-authors indian-refs indian-citers authors; do
    "$PYTHON" -u -m dpcn_mapping.collect_openalex "$step" >> "$LOG" 2>&1
    status=$?
    if [[ $status -eq 2 ]]; then
        log "step '$step' paused: OpenAlex daily budget exhausted; next cron run resumes it"
        exit 0
    elif [[ $status -ne 0 ]]; then
        log "step '$step' FAILED with exit code $status; next cron run retries it"
        exit "$status"
    fi
    log "step '$step' complete"
done

if [[ ! -s "$REPO/data/external/core/CORE_ICORE2026.csv" ]]; then
    "$PYTHON" -u -m dpcn_mapping.collect_openalex core >> "$LOG" 2>&1 || log "CORE download FAILED"
fi

if ! "$PYTHON" -u -m dpcn_mapping.collect_openalex manifest >> "$LOG" 2>&1; then
    log "sealing snapshot FAILED; next run retries it"
    exit 1
fi
log "snapshot $SNAPSHOT_ID sealed"

log "building group16_data.csv (build.snapshot_id in config/build.toml)"
if "$PYTHON" -u -m dpcn_mapping.build_dataset >> "$LOG" 2>&1; then
    log "pipeline finished; see data/builds/$(cat data/builds/LATEST)/"
    command -v notify-send > /dev/null && \
        DISPLAY="${DISPLAY:-:0}" notify-send "DPCN Group 16" "OpenAlex collection finished" 2> /dev/null
else
    log "build_dataset FAILED; next cron run retries it"
    exit 1
fi
