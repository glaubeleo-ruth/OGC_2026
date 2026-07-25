"""
lbbd.py -- the LBBD cut loop (design Part IV; closes F8/F9/F10).

The master's "OPTIMAL" under the fluid relaxation certifies only the Z2/Z3
assignment layer; on the easy tier its argmin is often geometrically
un-packable without tardiness (F8: prob_3-7 ship 2-3x the fluid bound).
This loop is the bridge:

    master -> pack -> derive cuts from what the packing realised -> re-solve

Two cut families, both SOUND (Part IV "Expected Bottlenecks": the packer
proving "tardy" never justifies a hard no-good by itself):

  * theta cuts -- for each tardy block in a packed proposal, take the small
    conflict CLUSTER (same-bay blocks whose zero-tardiness windows overlap
    its own) and ask bounds.py's per-layer cumulative CP-SAT for a certified
    tardiness LB of that cluster alone.  Bay tardiness is monotone in the
    block set (removing blocks never hurts a schedule), so lb >= 1 for the
    cluster is valid whenever the whole cluster shares the bay -- exactly
    AssignmentMaster.add_tardiness_cut's conditional form.  The master then
    prices that tardiness at w1 instead of walking into it again.

  * evaluated-assignment no-goods -- every proposal this loop has already
    packed and audited is excluded from the next solve.  That is k-best
    enumeration, not a feasibility claim: it removes only evaluated points,
    so when no theta cut is provable (pure geometric congestion the area
    relaxation cannot see) the loop still walks the next-best Z2/Z3
    assignment and lets the oracle vote on it.

The loop is also the long-budget consumer F10 asked for: it runs while a
full iteration provably fits (measured, 1.3x safety) and the IncumbentStore
keeps the best audited result, so surplus budget buys assignment-space
search instead of idling after repair converges.
"""

from __future__ import annotations

import math

from . import bounds, conductor, emit, objective
from .assignment import AssignmentMaster
from .budget import Deadline
from .incumbent import IncumbentStore
from .model import Instance

_MAX_CLUSTER = 24      # cluster blocks handed to the LB solver (subset stays sound)
_MAX_LB_CALLS = 6      # certified-LB attempts per iteration (budget discipline)
_LB_TIME_CAP = 0.8     # seconds per LB attempt


def _master_bound(inst: Instance, master: AssignmentMaster) -> float | None:
    """Exact-floor pricing of the master's last OPTIMAL argmin.  On the first
    solve (no cuts, no no-goods) this is the assignment-layer LB of the whole
    instance (F8's honest certificate, rho-caveat aside); on later solves it
    bounds every not-yet-evaluated assignment under the accumulated cuts."""
    if master.last_status != "OPTIMAL" or master.last_z2 is None:
        return None
    return (inst.w1 * (master.last_theta or 0.0)
            + inst.w2 * math.floor(master.last_z2)
            + inst.w3 * master.last_z3)


def _conflict_cluster(inst: Instance, bay_block_ids, tardy_id: int) -> list:
    """Same-bay blocks whose zero-tardiness windows overlap the tardy
    block's window -- the small set that plausibly forced its delay."""
    t = inst.blocks[tardy_id]
    lo, hi = t.release, max(t.due, t.release + t.proc)

    def overlap(i: int) -> int:
        b = inst.blocks[i]
        return min(hi, max(b.due, b.release + b.proc)) - max(lo, b.release)

    cluster = [i for i in bay_block_ids if i != tardy_id and overlap(i) > 0]
    if len(cluster) > _MAX_CLUSTER - 1:
        cluster = sorted(cluster, key=overlap, reverse=True)[:_MAX_CLUSTER - 1]
    return sorted(cluster + [tardy_id])


def derive_cuts(inst: Instance, master: AssignmentMaster, proposal: dict,
                delayed_by_bay: dict, deadline: Deadline,
                reserve: float) -> int:
    """Certified theta cuts from one packed proposal; returns how many landed."""
    existing = {(c.bay, c.block_ids) for c in master.tardiness_cuts}
    added = calls = 0
    for bay_id, tardy_ids in delayed_by_bay.items():
        bay_set = [i for i, j in proposal.items() if j == bay_id]
        for tid in tardy_ids:
            if calls >= _MAX_LB_CALLS or deadline.expired(margin=reserve + 1.0):
                return added
            cluster = _conflict_cluster(inst, bay_set, tid)
            key = (bay_id, tuple(cluster))
            if len(cluster) < 2 or key in existing:
                continue
            existing.add(key)
            calls += 1
            lb = bounds.bay_lb(inst, inst.bays[bay_id], cluster,
                               time_cap=min(_LB_TIME_CAP,
                                            deadline.sub_budget(0.05)))
            if lb is not None and lb > 0:
                master.add_tardiness_cut(bay_id, cluster, lb)
                added += 1
    return added


def cut_loop(inst: Instance, deadline: Deadline, store: IncumbentStore,
             master: AssignmentMaster, first_result, info_passes: list,
             reserve: float, first_iter_cost: float,
             max_iters: int = 40) -> None:
    """Iterate master -> pack -> cuts from `first_result` (the full pass)
    while a whole iteration provably fits inside deadline-minus-reserve."""
    result = first_result
    iter_cost = first_iter_cost
    # First-solve bound = the instance's assignment-layer LB: once the
    # audited incumbent reaches it there is nothing left to search for.
    # Certificate honesty (rex F11/F12): both stops carry floor_slack = w2
    # (the master minimizes UNfloored z2, so any "reached" claim is exact
    # only to within one floor granule), and master_bound_closed further
    # requires that no evaluated-but-tardy proposal still has an
    # assignment-layer cost below the incumbent -- its no-good excluded it
    # from the walk, but nothing proved it cannot pack to z1=0.
    assignment_lb = _master_bound(inst, master)
    open_below = []          # (iter, layer_cost) of tardy-packed proposals
    for it in range(max_iters):
        if assignment_lb is not None \
                and store.best_objective <= assignment_lb + 1e-6:
            info_passes.append({"pass": "lbbd", "stop": "assignment_lb_reached",
                                "lb": assignment_lb,
                                "best": store.best_objective,
                                "floor_slack": inst.w2})
            break
        proposal = result.info.get("master_assignment")
        if not proposal:
            break                       # greedy fallback path: nothing to cut
        delayed = result.info.get("delayed_initial") or {}
        if delayed:
            open_below.append(
                (it, inst.w2 * objective.z2_imbalance(inst, proposal)
                 + inst.w3 * objective.z3_preference(inst, proposal)))
        n_cuts = derive_cuts(inst, master, proposal, delayed,
                             deadline, reserve) if delayed else 0
        master.add_evaluated_nogood(proposal)

        if deadline.remaining() <= reserve + iter_cost:
            break
        t0 = deadline.elapsed()
        try:
            nxt = conductor.run(inst, deadline, use_master=True,
                                use_rescue=True, use_repair=True,
                                compute_bounds=False,
                                reserve=reserve,
                                master_cap=min(4.0, 0.15 * deadline.remaining()),
                                abort_on_expire=True,
                                master=master)
        except Exception as exc:
            info_passes.append({"pass": f"lbbd_{it}", "error": repr(exc)})
            break
        if nxt is None:
            info_passes.append({"pass": f"lbbd_{it}", "aborted": True,
                                "new_cuts": n_cuts})
            break
        sol = emit.build_solution(nxt.placements)
        res = store.audit_and_update(sol)
        info_passes.append({
            "pass": f"lbbd_{it}", "new_cuts": n_cuts,
            "cuts_total": len(master.tardiness_cuts),
            "nogoods": len(master.evaluated_nogoods),
            "master_status": nxt.info.get("master_status"),
            "master_theta": nxt.info.get("master_theta"),
            "objective": nxt.info.get("objective"),
            "z1": nxt.info.get("z1"),
            "feasible": res.get("feasible"),
        })
        # With cuts + no-goods the master bound only rises; once it clears
        # the incumbent AND no tardy-evaluated proposal is still open below
        # it (F11), nothing evaluated or unevaluated can win -- stop.
        cur_bound = _master_bound(inst, master)
        if cur_bound is not None and cur_bound >= store.best_objective - 1e-6:
            still_open = [(i, c) for i, c in open_below
                          if c < store.best_objective - 1e-6]
            if not still_open:
                info_passes.append({"pass": "lbbd",
                                    "stop": "master_bound_closed",
                                    "bound": cur_bound,
                                    "best": store.best_objective,
                                    "floor_slack": inst.w2})
                break
            # Honest partial certificate: optimum is boxed but not closed.
            info_passes.append({"pass": "lbbd",
                                "stop": "bound_closed_with_open_candidates",
                                "bound": cur_bound,
                                "best": store.best_objective,
                                "open_below_best": len(still_open),
                                "open_min_layer_cost": min(c for _, c
                                                           in still_open),
                                "floor_slack": inst.w2})
            break
        # Adaptive per-iteration cost: last measured wall, 1.3x safety.
        iter_cost = 1.3 * (deadline.elapsed() - t0)
        result = nxt
