#!/usr/bin/env bash
# Show collection progress. Live view: watch -n 10 scripts/progress.sh
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

echo "== Group 16 OpenAlex collection  ($(date '+%H:%M:%S'))"
PYTHONPATH="$REPO/src" "$REPO/.venv/bin/python" -m dpcn_mapping.collect_openalex status
echo
if ! flock -n logs/pipeline.lock true 2> /dev/null; then
    current="$(grep -oE "^(works|full-authors|indian_refs|indian_citers|authors):" logs/pipeline.log | tail -n 1 | tr -d :)"
    echo "Pipeline: RUNNING  (current step: ${current:-starting})"
else
    echo "Pipeline: not running"
fi
echo
echo "-- last log lines (logs/pipeline.log) --"
tail -n 5 logs/pipeline.log 2> /dev/null || echo "(no log yet)"
