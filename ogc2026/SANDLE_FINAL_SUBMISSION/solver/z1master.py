"""
z1master.py -- EXPERIMENTAL time-indexed areal scheduling master (Z1-first).

Lives in solver/ as a pure function of Instance; imports nothing from the
package (no cycles) and guards its ortools import, so a missing CP-SAT can
never break the pipeline (same _HAS_CPSAT doctrine as assignment.py).

Decides (bay, entry_day) jointly, minimizing w1*tardiness + w3*demotion under
per-(bay, day) areal capacity with a packing-efficiency factor alpha.  Pure
area relaxation: geometry stays the oracle's job (same doctrine as
plan_entries / congestion.py).  Demand per block is the conservative union
footprint min over orientations -- the same quantity plan_entries prices.

Output feeds conductor-level hooks only (assignment= and preferred=); every
resulting solution still goes through the unmodified oracle, repair, emit and
the utils audit gate.  This module can therefore not create a -1 that the
existing pipeline couldn't.

UNVERIFIED: prototype for the Z1-focus experiment (container, 2026-07-27).
"""

from __future__ import annotations



def _demand(b) -> float:
    """Conservative union footprint (same as oracle.plan_entries.demand)."""
    R2 = float(b.stamps[0].resolution ** 2)
    return min(float(s.grid.sum()) / R2 for s in b.stamps)


def solve_z1_master(inst, time_cap: float = 60.0, alpha: float = 0.85,
                    tardy_span: int | None = None, n_workers: int = 2):
    """Return (assignment {bid: bay}, entries {bid: day}, info) or (None, None, info).

    CP-SAT model:
      x[i,j,e] = 1  iff block i enters bay j on day e
      sum_e x[i,j,e] = 1 (over compatible j, candidate e)
      for each bay j, day t: sum demand_i * x[i,j,e covering t] <= alpha*A_j
      min sum x * (w1 * max(0, e+proc-due) + w3 * (pref_max - prefs[j]))
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return None, None, {"error": "no cpsat"}

    blocks = inst.blocks
    bays = inst.bays
    max_proc = max(b.proc for b in blocks)
    horizon = inst.horizon + max_proc + 2
    if tardy_span is None:
        tardy_span = horizon  # allow arbitrarily late entries inside horizon

    SCALE = 100  # demands are floats; capacity constraints in int units
    dem = {b.id: int(round(_demand(b) * SCALE)) for b in blocks}
    cap = {bay.id: int(round(alpha * bay.area * SCALE)) for bay in bays}

    # Greedy warm start (leveling in slack order, congestion-style pricing):
    # gives CP-SAT a feasible-ish hint so search starts from a real schedule.
    import numpy as np
    load = {bay.id: np.zeros(horizon) for bay in bays}
    hint = {}
    for b in sorted(blocks, key=lambda b: (b.slack, -dem[b.id])):
        compat = inst.compatible_bays(b) or [max(bays, key=lambda y: y.area).id]
        zwle = max(b.release, b.zero_window_last_entry)
        best = None
        for j in compat:
            for e in range(b.release, zwle + tardy_span + 1):
                if e + b.proc > horizon:
                    break
                seg = load[j][e:e + b.proc]
                over = float(np.maximum(seg + dem[b.id] - cap[j], 0).sum())
                tardy = max(0, e + b.proc - b.due)
                c = inst.w1 * tardy + inst.w3 * (b.pref_max - b.prefs[j])
                key = (over, c, e, j)
                if best is None or key < best:
                    best = key
                if over == 0 and tardy == 0 and b.prefs[j] == b.pref_max:
                    break
        j, e = best[3], best[2]
        hint[b.id] = (j, e)
        load[j][e:e + b.proc] += dem[b.id]

    m = cp_model.CpModel()
    x = {}          # (bid, j, e) -> BoolVar
    by_day = {}     # (j, t) -> list[(coef, var)]
    cost_terms = []

    for b in blocks:
        compat = inst.compatible_bays(b) or [max(bays, key=lambda y: y.area).id]
        lits = []
        zwle = max(b.release, b.zero_window_last_entry)
        lo = b.release
        hi = min(horizon - b.proc, zwle + tardy_span)
        hi = max(hi, lo)
        hj, he = hint[b.id]
        for j in compat:
            for e in range(lo, hi + 1):
                if e > zwle and (e - zwle) % 2 == 0 and (j, e) != (hj, he):
                    continue  # sparsify tardy candidates (every other day)
                v = m.NewBoolVar(f"x_{b.id}_{j}_{e}")
                x[(b.id, j, e)] = v
                lits.append(v)
                tardy = max(0, e + b.proc - b.due)
                demote = b.pref_max - b.prefs[j]
                c = inst.w1 * tardy + inst.w3 * demote
                if c:
                    cost_terms.append((c, v))
                for t in range(e, min(e + b.proc, horizon)):
                    by_day.setdefault((j, t), []).append((dem[b.id], v))
        m.AddExactlyOne(lits)

    for (j, t), terms in by_day.items():
        m.Add(sum(c * v for c, v in terms) <= cap[j])

    m.Minimize(sum(c * v for c, v in cost_terms))

    for b in blocks:
        hj, he = hint[b.id]
        if (b.id, hj, he) in x:
            m.AddHint(x[(b.id, hj, he)], 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_cap)
    solver.parameters.num_search_workers = n_workers
    status = solver.Solve(m)
    name = solver.StatusName(status)
    info = {
        "z1master_status": name,
        "n_vars": len(x),
        "n_capacity": len(by_day),
        "alpha": alpha,
        "wall": solver.WallTime(),
        # BestObjectiveBound applies only to this time-indexed areal
        # surrogate.  Geometry, crane access, and Z2 are outside the model,
        # so it is not a certified lower bound for the official problem.
        "bound_scope": "z1r_surrogate_only",
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # HINT FALLBACK: the greedy leveling warm start is itself a valid
        # (assignment, entry-day) plan -- release-shift realization keeps
        # official feasibility for ANY plan, so a CP-SAT timeout (weak core,
        # tight cap) degrades to the leveled greedy schedule instead of a
        # skip.  Measured motivation: the eval-style tester hands the
        # algorithm a single core, where 120 s was not enough for FEASIBLE
        # on a 250-block instance at alpha=0.70 even on two cores.
        info["z1master_status"] = f"HINT_FALLBACK({name})"
        assignment = {bid: je[0] for bid, je in hint.items()}
        entries = {bid: je[1] for bid, je in hint.items()}
        info["planned_tardy_days"] = sum(
            max(0, entries[b.id] + b.proc - b.due) for b in blocks)
        info["planned_demoted"] = sum(
            1 for b in blocks if b.prefs[assignment[b.id]] != b.pref_max)
        return assignment, entries, info

    assignment, entries = {}, {}
    for (bid, j, e), v in x.items():
        if solver.Value(v):
            assignment[bid] = j
            entries[bid] = e
    info["model_objective"] = solver.ObjectiveValue()
    info["model_bound"] = solver.BestObjectiveBound()
    info["planned_tardy_days"] = sum(
        max(0, entries[b.id] + b.proc - b.due) for b in blocks)
    info["planned_demoted"] = sum(
        1 for b in blocks if b.prefs[assignment[b.id]] != b.pref_max)
    return assignment, entries, info
