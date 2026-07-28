"""
api.py -- entry point with the hard-rule contract.

  * signature algorithm(prob_info, timelimit) -> dict, never raises, never
    returns None;
  * everything returned has been audited by utils.check_feasibility, except
    the absolute last resort (nothing audited feasible at all), where the
    best-effort construction is returned rather than None/crash;
  * seed-fallback discipline: a cheap greedy-assignment pass runs FIRST and
    is audited, so a feasible incumbent exists early regardless of what later
    stages do (-1 containment, T7);
  * the shared Deadline (0.93*t - 1) threads through every stage, together
    with a measured *reserve*: pass 1's audit wall-clock is timed and later
    stages are started only if pack + audit provably fit in the remaining
    budget, and are handed a reserve so their own degradation (oracle rushed
    mode, repair early-out, bounds skip) triggers before the reserve is
    touched.  WATCHDOG rules served: safety factor + deadline threading
    (fixes the prob_38/prob_40 overruns from the 2026-07-25 eva sweep).

myalgorithm.py still points at the legacy pipeline; switching it to
`from solver import algorithm` is the milestone-3 go/no-go decision.
"""

from __future__ import annotations

import os
import sys
import time

# utils.py lives next to myalgorithm.py, one directory above this package.
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)
import utils  # official oracle -- never modified, never re-implemented

from . import conductor, congestion, emit, lbbd, repair
from .assignment import AssignmentMaster
from .budget import Deadline
from .incumbent import IncumbentStore
from .model import Instance

# ---------------------------------------------------------------- F17 arm ---
# Selectable assignment arm for the F17 A/B (COMMAND_MANUAL section 2).
#   "baseline"   -- the LBBD assignment master decides the full pass (HEAD).
#   "congestion" -- congestion.congestion_assignment decides the full pass;
#                   the LBBD loop then continues from it (its cuts are
#                   certified LBs and its no-good is an evaluated point, so
#                   both stay sound under either arm).
# Default is "baseline" and the default code path is unchanged; the arm is
# chosen by solve(assign_arm=...) or the OGC_ASSIGN_ARM environment variable.
_ARMS = ("baseline", "congestion")


def _resolve_arm(assign_arm: str | None) -> str:
    """Never raises, never surprises: anything unrecognised is "baseline"."""
    try:
        arm = assign_arm if assign_arm is not None \
            else os.environ.get("OGC_ASSIGN_ARM", "baseline")
        arm = str(arm).strip().lower()
        return arm if arm in _ARMS else "baseline"
    except Exception:
        return "baseline"


def solve(prob_info: dict, timelimit: float = 60,
          assign_arm: str | None = None) -> tuple[dict, dict]:
    """Full pipeline; returns (solution, info). Used by tests/benchmarks.

    `assign_arm` selects the F17 assignment arm ("baseline" | "congestion");
    None falls back to $OGC_ASSIGN_ARM, then to "baseline".
    """
    arm = _resolve_arm(assign_arm)
    deadline = Deadline.from_timelimit(timelimit)
    store = IncumbentStore(prob_info, utils)
    info: dict = {"passes": [], "assign_arm": arm}
    last_construction: dict = {"operations": {}}

    inst = Instance.from_prob_info(prob_info)

    # F17 arm: one congestion assignment is computed up front and used by BOTH
    # non-master assignment sources (the seed pass and the full pass).  It has
    # to cover the seed too, or the arm is a no-op on exactly the instances
    # that motivated it: on the mass tail the full pass is often skipped for
    # budget (prob_31 @60s: "budget 4.9s < expected 11.4s") and the shipped
    # answer is the seed + repair.  Cost is pure arithmetic (~0.02 s at 200
    # blocks), so the -1 containment story of pass 1 is unchanged: same oracle,
    # same audit, same reserve.  Under "baseline" this stays None and every
    # call site below takes the untouched HEAD path.
    arm_assignment = None
    if arm == "congestion":
        try:
            arm_assignment, arm_info = congestion.congestion_assignment(
                inst, deadline, reserve=0.35 * deadline.budget)
            info["arm_info"] = arm_info
        except Exception as exc:           # never raise: degrade to baseline
            arm_assignment = None
            info["arm_info"] = {"arm": "congestion", "error": repr(exc)}

    # -- Pass 1: seed (greedy assignment, raster-only oracle) -----------------
    # Cheap and audited first: the -1 containment story never depends on the
    # master or the exact tiers.  Its own reserve is a budget fraction (no
    # audit measurement exists yet); its pack and audit walls calibrate every
    # later stage.
    t_pack1 = t_audit1 = 0.0
    seed = None
    try:
        t0 = time.monotonic()
        seed = conductor.run(inst, deadline, assignment=arm_assignment,
                             use_master=False,
                             use_rescue=False, use_repair=False,
                             compute_bounds=False,
                             reserve=0.35 * deadline.budget)
        sol = emit.build_solution(seed.placements)
        t_pack1 = time.monotonic() - t0
        last_construction = sol
        t0 = time.monotonic()
        res = store.audit_and_update(sol)
        t_audit1 = time.monotonic() - t0
        info["passes"].append({"pass": "seed", **seed.info,
                               "feasible": res.get("feasible"),
                               "pack_s": round(t_pack1, 2),
                               "audit_s": round(t_audit1, 2)})
    except Exception as exc:
        info["passes"].append({"pass": "seed", "error": repr(exc)})

    # -- Pass 2: seed+repair, then the full pipeline if it still fits ---------
    # Repair runs FIRST: it is anytime (per-move deadline polls), never
    # overruns, and Z1-first moves are the cheapest objective per second in
    # the pipeline -- on big instances it is the main event, on small ones it
    # costs a moment before the full pass.  The full re-pack then runs only
    # if affordable, and ABORTS (returns None) if the budget dies mid-pack --
    # a rushed completion of a re-pack measurably loses to the audited
    # incumbent already in the store.
    # Reserve = measured audit (1.5x safety) + emission slack + a small
    # per-block floor for the pack tail before the abort check fires.
    audit_reserve = 1.5 * t_audit1 + 1.0 + 0.02 * len(inst.blocks)

    if seed is not None and seed.info.get("delayed") \
            and not deadline.expired(margin=audit_reserve + 2.0):
        try:
            by_bay = {bay.id: [p for p in seed.placements if p.bay_id == bay.id]
                      for bay in inst.bays}
            stats = repair.repair_tardiness(inst, by_bay, deadline,
                                            reserve=audit_reserve)
            if not deadline.expired(margin=audit_reserve):
                stats.update(repair.polish_assignment(inst, by_bay, deadline,
                                                      reserve=audit_reserve))
            sol = emit.build_solution([p for ps in by_bay.values() for p in ps])
            res = store.audit_and_update(sol)
            info["passes"].append({"pass": "seed+repair", **stats,
                                   "feasible": res.get("feasible")})
        except Exception as exc:
            info["passes"].append({"pass": "seed+repair", "error": repr(exc)})

    master_cap = min(8.0, 0.15 * max(0.0, deadline.remaining()))
    expected = 1.2 * t_pack1 + master_cap + audit_reserve + 2.0
    if deadline.remaining() > expected:
        # The master outlives the full pass: lbbd.cut_loop keeps feeding it
        # cuts and re-solving while budget remains (F8/F9/F10).
        master = AssignmentMaster(inst)
        full = None
        try:
            t0 = time.monotonic()
            if arm_assignment is not None:
                # F17 arm: the congestion-aware greedy decides the full pass.
                # The master object is still built (the cut loop below needs
                # it) but is NOT solved here, so its certificate fields stay
                # at their "none" defaults -- a greedy assignment can never be
                # reported as OPTIMAL (F13).
                full = conductor.run(inst, deadline, assignment=arm_assignment,
                                     use_rescue=True, use_repair=True,
                                     compute_bounds=True,
                                     reserve=audit_reserve,
                                     abort_on_expire=True,
                                     master=master)
            else:
                full = conductor.run(inst, deadline, use_master=True,
                                     use_rescue=True, use_repair=True,
                                     compute_bounds=True,
                                     reserve=audit_reserve,
                                     master_cap=master_cap,
                                     abort_on_expire=True,
                                     master=master)
            t_full = time.monotonic() - t0
            if full is None:
                info["passes"].append({"pass": "full", "aborted": True})
            else:
                sol = emit.build_solution(full.placements)
                last_construction = sol
                res = store.audit_and_update(sol)
                info["passes"].append({"pass": "full", **full.info,
                                       "feasible": res.get("feasible")})
        except Exception as exc:
            info["passes"].append({"pass": "full", "error": repr(exc)})
        if full is not None:
            try:
                lbbd.cut_loop(inst, deadline, store, master, full,
                              info["passes"], reserve=audit_reserve,
                              first_iter_cost=1.3 * t_full + audit_reserve)
            except Exception as exc:
                info["passes"].append({"pass": "lbbd", "error": repr(exc)})
    else:
        info["passes"].append({"pass": "full", "skipped":
                               f"budget {deadline.remaining():.1f}s < "
                               f"expected {expected:.1f}s"})

    info["best_objective"] = store.best_objective
    info["elapsed"] = deadline.elapsed()

    if store.best_solution is not None:
        return store.best_solution, info
    return last_construction, info    # last resort: never None


def algorithm(prob_info: dict, timelimit: float = 60) -> dict:
    """Competition entry-point contract: never raise, never return None."""
    try:
        solution, _ = solve(prob_info, timelimit)
        return solution
    except Exception:
        return {"operations": {}}
