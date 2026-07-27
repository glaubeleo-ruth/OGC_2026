"""
_smoke_test.py -- headless smoke loop for the clean-slate pipeline.

Sanity gate per the working agreement (tom's contract), not the benchmark:
runs solver.algorithm on prob_1 and one large instance, asserts feasibility
via utils.check_feasibility and prints objective components, wall time, and
the per-pass info (including Z1-vs-LB gaps when bays ended tardy).

Run from baseline/sub/:  python -m solver._smoke_test [timelimit] [prob ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parents[1]
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))
import utils

from solver.api import solve


def run_one(prob_path: Path, timelimit: float) -> bool:
    prob = json.loads(prob_path.read_text())
    t0 = time.monotonic()
    sol, info = solve(prob, timelimit)
    wall = time.monotonic() - t0
    res = utils.check_feasibility(prob, sol)
    ok = bool(res["feasible"]) and wall <= timelimit
    print(f"{prob_path.name}: feasible={res['feasible']} "
          f"obj={res['objective']} (z1={res['obj1']} z2={res['obj2']} "
          f"z3={res['obj3']}) wall={wall:.1f}s/{timelimit:.0f}s")
    for p in info["passes"]:
        print(f"  pass={p.get('pass')} feasible={p.get('feasible')} "
              f"obj={p.get('objective')} z1={p.get('z1')} "
              f"delayed={ {k: len(v) for k, v in p.get('delayed', {}).items()} } "
              f"gaps={p.get('z1_gaps', {})} err={p.get('error')}")
    if not ok:
        print(f"  VIOLATIONS: {res['violations'][:5]}")
    return ok


if __name__ == "__main__":
    timelimit = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    root = Path(__file__).resolve().parents[3]
    probs = ([Path(p) for p in sys.argv[2:]] if len(sys.argv) > 2
             else [root / "train" / "prob_1.json", root / "train" / "prob_14.json"])
    ok = all(run_one(p, timelimit) for p in probs)
    print("SMOKE:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
