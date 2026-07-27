"""
ALNS objective evaluation helpers.

This module provides:
  - `objective(prob_info, sol)`: a thin, faithful wrapper around
    `utils.check_feasibility` that returns a (feasible, value, parts) tuple
    convenient for lower-is-better ALNS acceptance logic.
  - `tardiness_delta_lower_bound(...)`: a CHEAP pre-filter over the
    w1*obj1 (tardiness) term only, meant to let an ALNS controller skip a
    full `objective()` / `check_feasibility` call on moves that clearly
    cannot improve on the incumbent.

IMPORTANT LIMITATIONS of `tardiness_delta_lower_bound` (read before using):
  (a) It bounds ONLY the change in the w1*obj1 (tardiness) term. obj2
      (workload imbalance) is a floored GLOBAL MAX over bay pairs -- it is
      NOT separable per block and is NOT incremental, so it is deliberately
      left out of this bound (per project ADR: do not invent an incremental
      Z2). obj3 (preference penalty) is also left out. Both obj2 and obj3
      are non-negative and can move the true weighted objective in either
      direction relative to what this function returns.
  (b) It says NOTHING about feasibility. A move with a favorable tardiness
      delta can still be infeasible (crane collisions, boundary violations,
      etc.) -- those are only detected by `utils.check_feasibility`.
  (c) It is a FAST-REJECT filter only, never a fast-accept. Callers must
      still call `objective()` (i.e. run the true `check_feasibility`) for
      any real acceptance decision. This function exists purely to let a
      controller cheaply skip full evaluation of moves whose tardiness
      alone already makes them hopeless (e.g. delta far exceeds any
      plausible obj2/obj3 swing), never to certify a move as good.
"""

import os
import sys

_BASELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASELINE_DIR not in sys.path:
    sys.path.insert(0, _BASELINE_DIR)

import math

import utils  # noqa: E402  (import after sys.path fixup, by design)


def objective(prob_info: dict, sol: dict, deadline=None) -> tuple[bool, float, dict]:
    """
    Thin, faithful wrapper around `utils.check_feasibility`.

    Parameters
    ----------
    prob_info : instance JSON dict (see utils.check_feasibility).
    sol       : wire-format solution dict {"operations": {...}}.
    deadline  : optional alns.deadline.Deadline (WATCHDOG_SPEC.md hot spot
                #1). `check_feasibility`'s own cost scales with instance
                size and is not itself time-capped, so a full call late in
                an ALNS run can blow the budget on its own. When given:
                  - `deadline.check()` runs first, raising DeadlineExceeded
                    if the deadline has already passed -- the caller (the
                    ALNS loop) catches this and stops, rather than this
                    function silently starting an already-too-late check.
                  - if `not deadline.can_afford_check()`, this call is
                    SKIPPED entirely (no check_feasibility invocation at
                    all) and treated as rejected, since starting a check
                    that plausibly can't finish before the deadline is
                    exactly the failure mode this exists to prevent.

    Returns
    -------
    (feasible, value, parts)
        feasible : bool  -- result["feasible"] from check_feasibility (or
                   False if skipped due to `deadline`, see above).
        value    : float -- result["objective"] if feasible, else float("inf").
                   Using +inf for infeasible lets lower-is-better ALNS
                   acceptance/comparison code treat every feasible solution
                   as strictly better than any infeasible one, without ever
                   branching on the feasible flag separately.
        parts    : dict  -- {"obj1", "obj2", "obj3", "stage", "violations"}
                   copied straight from the check_feasibility result. When
                   infeasible, obj1/obj2/obj3 pass through as None (i.e.
                   whatever check_feasibility returned -- no substitution
                   or alternate computation is performed here). Same shape
                   when skipped due to `deadline`.
    """
    if deadline is not None:
        deadline.check()
        if not deadline.can_afford_check():
            return False, float("inf"), {
                "obj1": None, "obj2": None, "obj3": None,
                "stage": None,
                "violations": ["skipped: est_check_cost exceeds remaining deadline budget"],
            }

    result = utils.check_feasibility(prob_info, sol)

    feasible = result["feasible"]
    value = result["objective"] if feasible else float("inf")
    parts = {
        "obj1": result["obj1"],
        "obj2": result["obj2"],
        "obj3": result["obj3"],
        "stage": result["stage"],
        "violations": result["violations"],
    }
    return feasible, value, parts


def tardiness_delta_lower_bound(
    prob_info: dict,
    old_assignments: dict[int, dict],
    new_assignments: dict[int, dict],
) -> float:
    """
    Cheap pre-filter: weighted tardiness delta for blocks touched by a move.

    Computes Delta(w1 * obj1) restricted to the blocks present in
    `new_assignments` -- i.e. exactly the separable, incremental piece of
    the objective that CAN be computed without a full feasibility replay.
    See the module docstring for the three limitations (a)/(b)/(c) that
    apply to the result: it covers w1*obj1 only, says nothing about
    feasibility, and must never be used to accept a move -- only to
    fast-reject one before paying for `objective()` / `check_feasibility`.

    Formula
    -------
    For every block_id `bid` in `new_assignments`:
        due        = prob_info["blocks"][bid]["due_date"]
        new_tard   = max(0, new_assignments[bid]["exit_time"] - due)
        old_tard   = max(0, old_assignments[bid]["exit_time"] - due)
                     if bid in old_assignments else 0
        delta     += (new_tard - old_tard)
    return w1 * delta,  where w1 = prob_info["weights"]["w1"]

    A block newly introduced by the move (not present in `old_assignments`)
    contributes its full new tardiness (old_tard treated as 0), matching
    "this block didn't exist in the old solution, so it had no tardiness
    to compare against."  Blocks that exist in `old_assignments` but are
    NOT touched by the move (absent from `new_assignments`) are correctly
    excluded -- they contribute zero delta, since destroy/repair moves in
    ALNS only rewrite a subset of blocks and this function should report
    the incremental effect of exactly that subset.

    Parameters
    ----------
    prob_info       : instance JSON dict with "blocks" (list) and "weights".
    old_assignments : {block_id: {..., "exit_time": ...}} -- incumbent state
                       for (at least) the blocks affected by the move.
    new_assignments : {block_id: {..., "exit_time": ...}} -- candidate state
                       for the blocks affected by the move. Only block_ids
                       present here are considered.

    Returns
    -------
    float : Delta(w1 * obj1) lower bound (can be negative if the move
            reduces tardiness). This is exact for the w1*obj1 term alone,
            not a bound in the mathematical worst-case sense -- it is
            called a "lower bound" here in the ALNS-controller sense of
            "the true objective's w1*obj1 contribution, ignoring obj2/obj3
            which can only add further (non-negative-weighted) movement."
    """
    w1 = prob_info["weights"]["w1"]
    blocks_data = prob_info["blocks"]

    delta_tardiness = 0.0
    for bid, new_a in new_assignments.items():
        due_date = blocks_data[bid]["due_date"]
        new_tard = max(0.0, new_a["exit_time"] - due_date)

        if bid in old_assignments:
            old_tard = max(0.0, old_assignments[bid]["exit_time"] - due_date)
        else:
            old_tard = 0.0

        delta_tardiness += (new_tard - old_tard)

    return w1 * delta_tardiness


def fast_objective(prob_info: dict, assignments: dict[int, dict]) -> float:
    """
    O(n) objective computed directly from an assignments dict -- the EXACT
    same formula as utils.check_feasibility's objective section (obj1 sum,
    floored pairwise-max obj2, obj3 sum), with NO feasibility replay.

    For any feasible solution this returns exactly what check_feasibility
    would report, so values from this function and from objective() are
    directly comparable.  It says NOTHING about feasibility: callers must
    only use it on states produced by construction paths that enforce
    feasibility themselves (the v4+ placement kernel's bidirectional
    same-time + interaction checks), and must full-verify any state before
    promoting it to best/returning it.
    """
    blocks_data = prob_info["blocks"]
    bays_data   = prob_info["bays"]
    w  = prob_info.get("weights", {})
    w1 = w.get("w1", 1.0); w2 = w.get("w2", 1.0); w3 = w.get("w3", 1.0)
    n_bays = len(bays_data)

    obj1 = 0.0
    obj3 = 0.0
    bay_loads = [0.0] * n_bays
    for a in assignments.values():
        b = blocks_data[a["block_id"]]
        obj1 += max(0.0, a["exit_time"] - b["due_date"])
        bay_loads[a["bay_id"]] += b["workload"]
        prefs = b["bay_preferences"]
        obj3 += max(prefs) - prefs[a["bay_id"]]

    bay_areas = [bays_data[j]["width"] * bays_data[j]["height"] for j in range(n_bays)]
    avg_area  = sum(bay_areas) / n_bays
    u = [avg_area / a for a in bay_areas]
    if n_bays >= 2:
        obj2 = math.floor(max(
            abs(u[j1] * bay_loads[j1] - u[j2] * bay_loads[j2])
            for j1 in range(n_bays) for j2 in range(n_bays) if j1 != j2
        ))
    else:
        obj2 = 0.0

    return w1 * obj1 + w2 * obj2 + w3 * obj3
