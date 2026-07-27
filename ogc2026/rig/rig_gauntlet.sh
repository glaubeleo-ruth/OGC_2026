#!/usr/bin/env bash
# OGC 2026 — server-parity gauntlet runner (Linux, 4 pinned cores).
# Builds the zip FRESH from the tree, byte-verifies contents (stale-zip guard),
# runs the full 40-instance panel @60s + long-timelimit spot checks under
# taskset + thread caps, and prints the eligibility checklist.
# Usage: bash ogc2026/rig/rig_gauntlet.sh          (from anywhere)
# Env overrides: CORES=0-3  T=60  SPOT_T=300  SPOTS="21 31 38 40"  PY=python3
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUB="$ROOT/ogc2026/baseline/sub"
TRAIN="$ROOT/train"
RIG="$ROOT/ogc2026/rig"
OUT="$ROOT/ogc2026/baseline/results"
CORES="${CORES:-0-3}"
T="${T:-60}"
SPOT_T="${SPOT_T:-300}"
SPOTS="${SPOTS:-21 31 38 40}"
PY="${PY:-$(command -v python3)}"

STAMP=$(date +%Y%m%d-%H%M)
HASH=$(git -C "$ROOT" rev-parse --short HEAD)
DIRTY=$(git -C "$ROOT" status --porcelain | grep -cv '^??' || true)

echo "== OGC 2026 rig gauntlet =="
echo "host: $(uname -srm)"
echo "cpus: $(nproc), pinned to: $CORES"
echo "mem:  $(free -h | awk '/Mem:/{print $2}')"
echo "HEAD: $HASH (dirty tracked files: $DIRTY)"
if [ "$DIRTY" -gt 0 ]; then
  echo "WARNING: tree has uncommitted tracked changes - results cannot certify a submission hash"
fi

command -v taskset >/dev/null || { echo "FATAL: taskset missing (install util-linux)"; exit 1; }
"$PY" -c "import numpy, shapely, ortools" 2>/dev/null \
  || { echo "FATAL: python env missing numpy/shapely/ortools (see RIG_SETUP.md)"; exit 1; }

# --- 1. fresh zip + sha256 manifest -----------------------------------------
STAGE=$(mktemp -d)
ZIP="$STAGE/submission_${STAMP}_${HASH}.zip"
( cd "$SUB" && zip -qr "$ZIP" myalgorithm.py utils.py baseline_greedy.py legacy_entry.py alns solver \
    -x "*__pycache__*" -x "*.pyc" -x "*.zip" -x "*.DS_Store" )
( cd "$SUB" && find myalgorithm.py utils.py baseline_greedy.py legacy_entry.py alns solver -type f \
    ! -name "*.pyc" ! -path "*__pycache__*" -exec sha256sum {} \; | sort -k2 ) > "$STAGE/manifest.sha256"
echo "zip built: $ZIP ($(du -h "$ZIP" | cut -f1))"

# --- 2. clean unzip + byte-verify (stale-zip guard) --------------------------
UNZ="$STAGE/unzipped"; mkdir "$UNZ"; unzip -qq "$ZIP" -d "$UNZ"
[ -f "$UNZ/myalgorithm.py" ] || { echo "FATAL: myalgorithm.py not at zip root"; exit 1; }
( cd "$UNZ" && sha256sum --quiet -c "$STAGE/manifest.sha256" ) \
  || { echo "FATAL: zip contents != tree manifest (stale-zip class)"; exit 1; }
echo "zip contents byte-verified against the tree"

CSV="$OUT/${STAMP}_rig_gauntlet_${HASH}.csv"
mkdir -p "$OUT"
echo "prob,timelimit,feasible,objective,obj1,obj2,obj3,wall,wall_ratio,peak_rss_mb,status" > "$CSV"

run_one () {
  local n=$1 t=$2
  local probfile="$TRAIN/prob_${n}.json"
  local hard=$(( t + 5 ))
  local line
  line=$(taskset -c "$CORES" env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
      timeout -k 5 "$hard" "$PY" "$RIG/run_one.py" "$UNZ" "$probfile" "$t" 2>/dev/null \
      | grep '^ROW:' | tail -1) || true
  if [ -z "$line" ]; then
    echo "prob_${n}.json,$t,False,,,,,,,,MINUS_ONE" >> "$CSV"
    echo "prob_${n} @${t}s: -1 (timeout/crash)"
  else
    "$PY" - "$line" >> "$CSV" <<'PYEOF'
import json, sys
r = json.loads(sys.argv[1][4:])
keys = ("prob","timelimit","feasible","objective","obj1","obj2","obj3","wall","wall_ratio","peak_rss_mb")
print(",".join(str(r.get(k, "")) for k in keys) + ",OK")
PYEOF
    echo "prob_${n} @${t}s: $line"
  fi
}

echo "== full panel @ ${T}s =="
for n in $(seq 1 40); do run_one "$n" "$T"; done
echo "== spot checks @ ${SPOT_T}s =="
for n in $SPOTS; do run_one "$n" "$SPOT_T"; done

# --- 3. summary + eligibility checklist --------------------------------------
"$PY" - "$CSV" <<'PYEOF'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1])))
bad = [r for r in rows if r["status"] != "OK" or r["feasible"] != "True"]
walls = [(r["prob"], float(r["timelimit"]), float(r["wall"])) for r in rows if r["status"] == "OK"]
rss = max((float(r["peak_rss_mb"]) for r in rows if r["status"] == "OK" and r["peak_rss_mb"]), default=0.0)
b090 = [(p, t, w) for p, t, w in walls if w > 0.90 * t]
b095 = [(p, t, w) for p, t, w in walls if w > 0.95 * t]
print(f"\n== SUMMARY ==\nrows: {len(rows)}  failures(-1/infeasible): {len(bad)}  peak RSS: {rss:.0f} MB")
for r in bad:
    print("  FAIL:", r["prob"], r["timelimit"], r["status"])
print(f"walls >0.90t: {len(b090)} ->", b090 or "none")
print(f"walls >0.95t: {len(b095)} ->", b095 or "none")
print("ELIGIBILITY CHECKLIST (eva stamps the verdict; this is raw input):")
print("  0 x -1        :", "PASS" if not bad else "FAIL")
print("  RSS < 12 GB   :", "PASS" if rss < 12288 else "FAIL")
print("  0.90t wall line:", "PASS" if not b090 else "BREACHED (design line 0.93t-1; ruling required at t>=300)")
print("  0.95t design line:", "PASS" if not b095 else "BREACHED")
PYEOF

echo ""
echo "CSV: $CSV"
echo "ZIP: $ZIP"
echo "If eligible: copy back BOTH files. The zip is the exact artifact to submit."
