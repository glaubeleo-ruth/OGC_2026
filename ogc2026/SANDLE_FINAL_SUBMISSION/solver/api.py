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

import copy
import os
import sys
import time

# utils.py lives next to myalgorithm.py, one directory above this package.
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)
import utils  # noqa: E402  # official oracle -- never modified/reimplemented

from . import conductor, congestion, emit, lbbd, repair, z1master  # noqa: E402
from .assignment import AssignmentMaster  # noqa: E402
from .budget import Deadline  # noqa: E402
from .incumbent import IncumbentStore  # noqa: E402
from .model import Instance  # noqa: E402

# ------------------------------------------------------------- z1r pass ----
# EXPERIMENTAL (2026-07-27, container 5/5 sweep -29%..-65%, UNVERIFIED on the
# rig): time-indexed areal scheduling master + release-enforced realization.
# Fixed constants, never instance-fitted.  The pass runs AFTER seed+repair
# and BEFORE the full pass, iff the seed showed tardiness and enough budget
# remains; its output goes through the same emit + utils audit gate, so it
# can only ever replace the incumbent by beating it under the official
# checker.  At timelimit=60 (remaining after seed << gate) the pass never
# fires and the pipeline is byte-identical to HEAD behavior.
_Z1R_MIN_REMAINING = 120.0   # s left after seed, else skip
_Z1R_ALPHA = 0.75            # areal packing-efficiency factor (measured dial)
_Z1R_MASTER_CAP = 120.0      # CP-SAT cap; also capped at 0.5*remaining
_Z1R_MIN_CAP = 90.0          # below this cap the model returns junk-quality
                             # plans (measured: 65s/1-worker plan ~= greedy
                             # hint, realized WORSE than baseline) -- skip
                             # instead and leave the budget to seed+repair
_Z1R_PLAN_RATIO = 0.45       # realize only if planned tardy <= ratio*seed_z1
                             # (measured realization inflation 1.4-1.8x; a
                             # plan above this cannot beat the repaired seed
                             # and would burn pack budget on a discard)


class _Z1rSkip(Exception):
    """Internal control flow: a z1r guard declined the pass (logged skip)."""

# ---------------------------------------------------------------- F17 arm ---
# Selectable assignment arm for the F17 A/B (COMMAND_MANUAL section 2).
#   "baseline"   -- the LBBD assignment master decides the full pass (HEAD).
#   "congestion" -- congestion.congestion_assignment decides the full pass;
#                   the LBBD loop then continues from it (its cuts are
#                   certified LBs and its no-good is an evaluated point, so
#                   both stay sound under either arm).
# "auto" routes only the measured mass class.  On the train generator this is
# exactly the six high-density instances with at least 250 blocks and 70 blocks
# per bay; the criterion is an instance statistic, not a problem-name lookup.
# Quiet A/Bs:
# prob_17 tied, prob_38 -22.9%, prob_39 -12.4%, and the earlier six-instance
# diagnostic had congestion <= baseline on 6/6.
_ARMS = ("auto", "baseline", "congestion")
_CONGESTION_MIN_BLOCKS = 250
_CONGESTION_BLOCKS_PER_BAY = 70.0


def _resolve_arm(assign_arm: str | None) -> str:
    """Never raises, never surprises: anything unrecognised is "baseline"."""
    try:
        arm = assign_arm if assign_arm is not None \
            else os.environ.get("OGC_ASSIGN_ARM", "auto")
        arm = str(arm).strip().lower()
        return arm if arm in _ARMS else "baseline"
    except Exception:
        return "baseline"


def solve(prob_info: dict, timelimit: float = 60,
          assign_arm: str | None = None,
          z1r: str = "auto") -> tuple[dict, dict]:
    """Full pipeline; returns (solution, info). Used by tests/benchmarks.

    `z1r` gates the experimental temporal-master pass: "auto" (default; runs
    only when the budget gate passes) or "off" (byte-identical HEAD path).

    `assign_arm` selects "auto" | "baseline" | "congestion"; None falls back
    to $OGC_ASSIGN_ARM, then to the density-based automatic route.
    """
    requested_arm = _resolve_arm(assign_arm)
    deadline = Deadline.from_timelimit(timelimit)
    store = IncumbentStore(prob_info, utils)
    last_construction: dict = {"operations": {}}

    inst = Instance.from_prob_info(prob_info)
    density = len(inst.blocks) / max(1, len(inst.bays))
    arm = requested_arm
    if arm == "auto":
        arm = ("congestion"
               if (len(inst.blocks) >= _CONGESTION_MIN_BLOCKS
                   and density >= _CONGESTION_BLOCKS_PER_BAY)
               else "baseline")
    info: dict = {
        "passes": [],
        "assign_arm": arm,
        "assign_arm_requested": requested_arm,
        "blocks_per_bay": round(density, 3),
    }

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

    # -- Pass 1.5 (EXPERIMENTAL): z1r -- temporal master, release-enforced ---
    # Runs BEFORE seed+repair on purpose: repair is an anytime loop that on
    # the mass tail consumes the whole remaining budget (measured prob_38:
    # ~250 s), which would starve this pass behind it.  Gate: the seed showed
    # tardiness AND >= _Z1R_MIN_REMAINING s remain AND z1r != "off".  Any
    # failure degrades to a logged skip; seed+repair and every later pass
    # then see exactly the budget z1r left them, and the incumbent store
    # keeps whichever construction audits best.  At timelimit=60 the gate
    # can never pass (seed alone spends most of the budget), so the t=60
    # path is byte-identical to HEAD.
    # Long-budget aggression (2026-07-28, rank push): at hidden limits of
    # 900-1800 s the single 120 s rung leaves most of the slice idle.  Two
    # escalations, BOTH gated on remaining budget so every t<=300 path stays
    # exactly as measured tonight: (1) the master cap may grow to 180 s when
    # >=600 s remain; (2) after the first rung, a second rung at alpha=0.85
    # runs iff a full master+realization still fits.  The store keeps the
    # audited best of all rungs.
    _z1r_rungs = [_Z1R_ALPHA, 0.85]
    if (z1r != "off" and seed is not None and seed.info.get("delayed")
            and deadline.remaining() >= _Z1R_MIN_REMAINING):
        seed_z1 = seed.info.get("z1") or 0.0
        try:
            n_cores = len(os.sched_getaffinity(0))
        except AttributeError:
            n_cores = os.cpu_count() or 1
        for _rung_i, _alpha in enumerate(_z1r_rungs):
            if _rung_i > 0 and deadline.remaining() < _Z1R_MIN_REMAINING:
                break
            try:
                t0 = time.monotonic()
                # Reserve realization time BEFORE sizing the master cap
                # (measured failure: 1-core, good plan, pack aborted, 200 s
                # bought nothing).  Cap may stretch to 180 s only when the
                # budget is deep (>=600 s remaining) -- t<=300 paths keep
                # tonight's measured behavior exactly.
                realization_est = 2.0 * t_pack1 + 10.0
                cap_ceiling = (180.0 if deadline.remaining() >= 600.0
                               else _Z1R_MASTER_CAP)
                cap = min(cap_ceiling,
                          deadline.remaining() - realization_est
                          - audit_reserve - 5.0)
                if cap < _Z1R_MIN_CAP:
                    raise _Z1rSkip(f"cap {cap:.0f}s < {_Z1R_MIN_CAP:.0f}s "
                                   f"(realization est {realization_est:.0f}s)")
                z_assign, z_entries, z_info = z1master.solve_z1_master(
                    inst, time_cap=cap, alpha=_alpha,
                    n_workers=max(1, min(4, n_cores)))
                if z_assign is None:
                    raise _Z1rSkip(f"master not feasible "
                                   f"({z_info.get('z1master_status')})")
                if (seed_z1 > 0 and z_info.get("planned_tardy_days", 0)
                        > _Z1R_PLAN_RATIO * seed_z1):
                    raise _Z1rSkip(
                        f"plan quality guard "
                        f"({z_info.get('planned_tardy_days')} planned > "
                        f"{_Z1R_PLAN_RATIO} * seed z1 {seed_z1:.0f})")
                mod = copy.deepcopy(prob_info)
                for bid, e in z_entries.items():
                    blk = mod["blocks"][bid]
                    blk["release_time"] = max(blk["release_time"], int(e))
                inst2 = Instance.from_prob_info(mod)
                # Complete-mode pack (the seed pass's own pattern): a rushed
                # completion still reaches the audit gate, where the store
                # keeps it only if it actually wins.
                zres = conductor.run(inst2, deadline, assignment=z_assign,
                                     use_rescue=True, use_repair=True,
                                     compute_bounds=False,
                                     reserve=audit_reserve,
                                     abort_on_expire=False)
                if zres is not None:
                    sol = emit.build_solution(zres.placements)
                    res = store.audit_and_update(sol)
                    planned_z1 = z_info.get("planned_tardy_days")
                    realized_z1 = zres.info.get("z1")
                    if planned_z1 is not None and realized_z1 is not None:
                        z_info["realized_tardy_days"] = realized_z1
                        z_info["realization_ratio"] = round(
                            realized_z1 / max(1.0, float(planned_z1)), 4)
                    info["passes"].append({
                        "pass": "z1r", "alpha": _alpha, **z_info,
                        "feasible": res.get("feasible"),
                        "audited_objective": res.get("objective"),
                        "wall_s": round(time.monotonic() - t0, 2)})
                else:
                    info["passes"].append({"pass": "z1r", "alpha": _alpha,
                                           **z_info, "aborted": True})
            except _Z1rSkip as skip:
                info["passes"].append({"pass": "z1r", "alpha": _alpha,
                                       "skipped": str(skip)})
                break            # a skipped rung means later rungs skip too
            except Exception as exc:
                info["passes"].append({"pass": "z1r", "alpha": _alpha,
                                       "error": repr(exc)})
                break
    else:
        info["passes"].append({"pass": "z1r", "skipped":
                               f"gate (remaining {deadline.remaining():.1f}s, "
                               f"z1r={z1r})"})

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
