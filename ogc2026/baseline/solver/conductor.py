"""
conductor.py -- pipeline orchestration (design Part VI, sequential v0).

v0 executes the task ladder in-process and in priority order:

    master assignment -> per-bay ORACLE passes -> cross-bay tardiness REPAIR
    -> (BOUND certificates if budget remains) -> emit -> AUDIT (in
    incumbent.py / api.py)

Bay independence (T4) makes the ORACLE loop the natural fork point: the
target topology is a conductor + 3 forked workers consuming tasks.py units,
fork context only, copy-on-write instance state, sequential fallback when
fork is unavailable, every embedded solver capped to 1 thread.  That pool
replaces the `for bay in ...` loop below without changing any interface
(Part VIII milestone 6); on a 1-2 core dev box only throughput differs,
never the code path.

WATCHDOG rule served: deadline threading -- every stage receives the shared
Deadline plus a `reserve` margin (the time the caller still needs for
emission + utils audit after this pass), and each stage degrades or is
skipped rather than eat into that reserve.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import bounds, objective, repair
from .assignment import AssignmentMaster, _HAS_CPSAT
from .budget import Deadline
from .model import Instance
from .oracle import BayPacking, pack_bay, plan_entries

# O3/F3 triage threshold: measured slack profiles are bimodal (easy/mid
# instances ~0-0.1 share of slack > 4; the wide-slack tail 0.4+), so the
# cut sits in the empty middle rather than on a fitted boundary.
_WIDE_SLACK_SHARE = 0.30


@dataclass
class PipelineResult:
    assignment: dict                 # block_id -> bay_id
    placements: list                 # oracle.Placement, all bays
    info: dict = field(default_factory=dict)

    def exit_times(self) -> dict:
        return {p.block_id: p.exit for p in self.placements}


def run(inst: Instance, deadline: Deadline,
        assignment: dict | None = None,
        use_master: bool = True,
        use_rescue: bool = True,
        use_repair: bool = True,
        compute_bounds: bool = True,
        reserve: float = 0.0,
        master_cap: float = 8.0,
        abort_on_expire: bool = False) -> PipelineResult | None:
    """One full pass: assignment -> per-bay packing -> repair -> scoring.

    `reserve` is the wall-clock the caller still needs after this pass
    (emission + utils audit); every stage treats deadline-minus-reserve as
    its own hard stop.  `assignment` overrides the master (api's fallback
    seed pass; later, k-best pool exploration).  With abort_on_expire, a
    budget death during packing returns None instead of a rushed completion
    (callers keep their audited incumbent).
    """
    info: dict = {}

    if assignment is None:
        if use_master:
            master = AssignmentMaster(inst)
            assignment = master.solve(deadline, time_cap=master_cap)
            info["master"] = "cpsat" if _HAS_CPSAT else "greedy"
            # O1/O6: certification status + the assignment-layer optimum the
            # packed solution should be polished toward.
            info["master_status"] = master.last_status
            info["master_z2z3"] = (master.last_z2, master.last_z3)
        else:
            assignment = AssignmentMaster(inst)._greedy()
            info["master"] = "greedy"

    # ORACLE ladder step: per-bay packing (fork-pool extension point, T4/T8).
    by_bay_ids: dict = {bay.id: [] for bay in inst.bays}
    for bid, j in assignment.items():
        by_bay_ids[j].append(bid)

    # O3 status (2026-07-25): trigger OFF pending a clean A/B.  First
    # measurements of plan_entries-guided packing on prob_40 looked worse
    # than enter-ASAP, but they were taken under concurrent benchmark load --
    # repair/polish are deadline-bounded anytime loops, so contention
    # directly changes results.  Decision needs quiet-machine, N >= 3 pairs
    # (the cadence's own protocol).  Until then: enter-ASAP everywhere.
    use_queue = False and inst.slack_gt4_share > _WIDE_SLACK_SHARE
    info["queue_aware"] = use_queue
    info["slack_gt4_share"] = round(inst.slack_gt4_share, 3)

    packings: list[BayPacking] = []
    for bay in inst.bays:
        preferred = (plan_entries(inst, bay, by_bay_ids[bay.id])
                     if use_queue else None)
        pk = pack_bay(inst, bay, by_bay_ids[bay.id], deadline,
                      use_rescue=use_rescue, reserve=reserve,
                      abort_on_expire=abort_on_expire,
                      preferred=preferred)
        if pk is None:
            return None   # budget died mid-pack; caller keeps its incumbent
        packings.append(pk)

    by_bay = {pk.bay_id: list(pk.placements) for pk in packings}
    info["delayed_initial"] = {pk.bay_id: pk.delayed_ids
                               for pk in packings if pk.delayed_ids}

    # REPAIR ladder step: cross-bay tardiness repair (Z1-first, exact deltas),
    # then the O6 Z2/Z3 polish (zero-window moves; cannot create tardiness).
    if use_repair and any(info["delayed_initial"].values()) \
            and not deadline.expired(margin=reserve):
        info["repair"] = repair.repair_tardiness(inst, by_bay, deadline,
                                                 reserve=reserve)
    if use_repair and not deadline.expired(margin=reserve):
        info["polish"] = repair.polish_assignment(inst, by_bay, deadline,
                                                  reserve=reserve)

    placements = [p for ps in by_bay.values() for p in ps]
    assignment = {p.block_id: p.bay_id for p in placements}
    delayed = {
        j: [p.block_id for p in ps
            if p.exit > inst.blocks[p.block_id].due]
        for j, ps in by_bay.items()
    }
    delayed = {j: ids for j, ids in delayed.items() if ids}
    info["delayed"] = delayed

    result = PipelineResult(assignment=assignment, placements=placements, info=info)

    # Internal (utils-identical) scoring for logging and incumbent ranking.
    exits = result.exit_times()
    info["z1"] = objective.z1_tardiness(inst, exits)
    info["z2"] = objective.z2_imbalance(inst, assignment)
    info["z3"] = objective.z3_preference(inst, assignment)
    info["objective"] = objective.total(inst, assignment, exits)

    # BOUND ladder step: certificates for bays that ended tardy (III.2).
    # A certificate is a luxury, the incumbent is not: only with slack beyond
    # the caller's reserve.
    if compute_bounds and delayed and deadline.remaining() > reserve + 5.0:
        gaps = {}
        for bay_id in delayed:
            if deadline.remaining() <= reserve + 3.0:
                break
            lb = bounds.bay_lb(inst, inst.bays[bay_id],
                               [p.block_id for p in by_bay[bay_id]],
                               time_cap=min(2.0, deadline.sub_budget(0.1)))
            if lb is not None:
                z1_bay = sum(
                    max(0, p.exit - inst.blocks[p.block_id].due)
                    for p in by_bay[bay_id]
                )
                gaps[bay_id] = {"lb": lb, "z1": z1_bay, "gap": z1_bay - lb}
        info["z1_gaps"] = gaps

    return result
