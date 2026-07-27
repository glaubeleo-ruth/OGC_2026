"""Forced-kill wall measurement (finding 20260727c-6) — rig-portable version of
rex's rex06_forcedkill.py acceptance harness.

Real _run_legacy_hard_walled, real forked child, real SIGKILL drain, tl=60.
Line 1 (solver) forced dead; hedge forced to hang. Observe the return value of
algorithm() — in mode 'pure' no myalgorithm internals are patched.

The one number this exists to capture on the Linux rig: the kill path is
DESIGNED to run to ~0.985 x raw timelimit (hard wall at t-1.5, then drain +
rung + audit). On a slower 4-core box that tail can overrun the raw limit —
unobservable from any natural run. PASS = feasible dict, wall < t.

Run from ogc2026/baseline/sub/ (or with it on PYTHONPATH + as cwd):

  cd ogc2026/baseline/sub
  PYTHONPATH=$PWD taskset -c 0-3 env OMP_NUM_THREADS=1 \
    python ../../rig/forced_kill_test.py prob_38 pure raise

Usage: forced_kill_test.py <prob_id> <mode:pure|instr> <line1:raise|none|empty|infeas>
"""
import json
import os
import sys
import time

# locate train/ by walking up from cwd (rig-portable; no hardcoded paths)
_d = os.path.abspath(os.getcwd())
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "train")):
        break
    _d = os.path.dirname(_d)
TRAIN = os.path.join(_d, "train", "%s.json")

pid, mode, l1 = sys.argv[1], sys.argv[2], sys.argv[3]
prob = json.load(open(TRAIN % pid))

import utils
# Pre-import legacy_entry in the PARENT so the forked child inherits the
# patched module via sys.modules (fork copies memory; the child's
# `import legacy_entry` is then a sys.modules hit).
import legacy_entry


def _hang(pi, tl):
    while True:
        time.sleep(3600)


legacy_entry.algorithm = _hang

import solver.api


def _dead(pi, tl):
    if l1 == "raise":
        raise RuntimeError("forced line-1 death")
    if l1 == "none":
        return None, {}
    if l1 == "empty":
        return {"operations": {}}, {}
    if l1 == "infeas":
        # stage-1 infeasible: one ENTRY, no EXIT
        return {"operations": {"0": [{"type": "ENTRY", "block_id": 0,
                                      "bay_id": 0, "x": 0, "y": 0,
                                      "orient_idx": 0}]}}, {}
    raise AssertionError(l1)


solver.api.solve = _dead

import myalgorithm

trace = {}
if mode == "instr":
    _sc = myalgorithm._serial_construction
    _rl = myalgorithm._run_legacy_hard_walled

    def sc(pi, keep_going=None):
        t = time.monotonic()
        r = _sc(pi, keep_going=keep_going)
        trace["serial_called"] = True
        trace["serial_build_s"] = time.monotonic() - t
        trace["serial_none"] = r is None
        return r

    def rl(pi, ctl, hw):
        trace["hard_wall_arg"] = hw
        trace["legacy_tl_arg"] = ctl
        t = time.monotonic()
        r = _rl(pi, ctl, hw)
        trace["hedge_elapsed_s"] = time.monotonic() - t
        trace["hedge_drain_s"] = (time.monotonic() - t) - hw
        trace["hedge_result_none"] = r is None
        return r

    myalgorithm._serial_construction = sc
    myalgorithm._run_legacy_hard_walled = rl
    trace["serial_called"] = trace.get("serial_called", False)

n = len(prob.get("blocks") or ())
nb = max(1, len(prob.get("bays") or ()))
rec = {"prob": pid, "mode": mode, "line1": l1, "n": n, "bays": nb,
       "n2_over_bays": n * n / nb,
       "est_audit": 1.0e-5 * n * n / nb}
rec["tail_reserve"] = max(1.5, 3.0 * rec["est_audit"] + 0.6)

t0 = time.monotonic()
try:
    sol = myalgorithm.algorithm(prob, 60)
    rec["crash"] = None
except Exception as e:
    rec["crash"] = repr(e)
    sol = None
rec["wall"] = time.monotonic() - t0
rec["overran_raw_limit"] = rec["wall"] > 60.0
rec["is_none"] = sol is None
if isinstance(sol, dict):
    ops = sol.get("operations") or {}
    rec["n_time_keys"] = len(ops)
    rec["n_ops"] = sum(len(v) for v in ops.values())
    rec["is_empty_placeholder"] = (rec["n_ops"] == 0)
    try:
        res = utils.check_feasibility(prob, sol)
        rec["feasible"] = bool(res.get("feasible"))
        rec["objective"] = res.get("objective")
    except Exception as e:
        rec["feasible"] = "CHECKER_RAISED"
        rec["err"] = repr(e)
rec["trace"] = trace
print("FORCED " + json.dumps(rec))
