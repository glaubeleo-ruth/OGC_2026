#!/usr/bin/env bash
# make_submission.sh -- build + verify the submission zip (FINALE_PLAN Phase 2).
#
# Layout rules: myalgorithm.py at zip root, both pipelines included, no
# tests/results/tester/caches, <= 15 MB, relative paths only.  The zip is
# then unzipped into a clean temp dir and smoke-run on prob_1 from there --
# the dry run exercises exactly what the server will import, not the repo.
#
# Usage: ./make_submission.sh [timelimit_for_dry_run]   (default 30)
set -euo pipefail
cd "$(dirname "$0")"

TL="${1:-30}"
STAMP="$(date +%Y%m%d-%H%M)"
REV="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
OUT="submission_${STAMP}_${REV}.zip"

rm -f "$OUT"
zip -q -r "$OUT" \
    myalgorithm.py legacy_entry.py baseline_greedy.py utils.py \
    alns solver \
    -x "*/__pycache__/*" -x "*.pyc" -x "*_smoke_test*" \
    -x "*_parity_test*" -x "*/.DS_Store" -x "*/results/*"

SZ=$(stat -f%z "$OUT" 2>/dev/null || stat -c%s "$OUT")
echo "built $OUT ($((SZ / 1024)) KB)"
if [ "$SZ" -gt $((15 * 1024 * 1024)) ]; then
    echo "FAIL: zip exceeds 15 MB"; exit 1
fi

PROB="$(cd ../../../train && pwd)/prob_1.json"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
unzip -q "$OUT" -d "$TMP"
echo "dry run from clean unzip ($TMP), timelimit=${TL}s ..."
( cd "$TMP" && OGC_PROB="$PROB" OGC_TL="$TL" conda run -n ogc2026 python - <<'PYEOF'
import json, os, time
from myalgorithm import algorithm
import utils

prob = json.load(open(os.environ["OGC_PROB"]))
tl = float(os.environ["OGC_TL"])
t0 = time.monotonic()
sol = algorithm(prob, tl)
wall = time.monotonic() - t0
res = utils.check_feasibility(prob, sol)
ok = bool(res["feasible"]) and wall <= tl
print(f"feasible={res['feasible']} obj={res['objective']} "
      f"(z1={res['obj1']} z2={res['obj2']} z3={res['obj3']}) "
      f"wall={wall:.1f}s/{tl:.0f}s")
raise SystemExit(0 if ok else 1)
PYEOF
)
echo "DRY RUN PASS -- $OUT is submit-ready (tag sub-YYYYMMDD-N before Leo emails it)"
