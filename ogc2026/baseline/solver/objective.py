"""
objective.py -- Z1/Z2/Z3 accounting, bit-identical to utils.check_feasibility.

III.1: "accuracy includes never mis-pricing a solution we already hold."
The formulas below mirror utils exactly -- including the floor() on obj2 and
the 1.0 weight defaults -- so internal scores always agree with the official
gate.  T1: Z2 and Z3 are pure functions of the assignment; Z1 depends only on
exit times.
"""

from __future__ import annotations

import math

from .model import Instance


def z1_tardiness(inst: Instance, exit_times: dict) -> float:
    """Sum of max(0, exit - due) over blocks. exit_times: block_id -> int."""
    return float(sum(max(0, exit_times[b.id] - b.due) for b in inst.blocks))


def z2_imbalance(inst: Instance, assignment: dict) -> float:
    """Max pairwise |u_j*load_j - u_k*load_k|, floored like utils.
    assignment: block_id -> bay_id."""
    m = len(inst.bays)
    if m < 2:
        return 0.0
    loads = [0.0] * m
    for b in inst.blocks:
        loads[assignment[b.id]] += b.workload
    return float(math.floor(max(
        abs(inst.u[j1] * loads[j1] - inst.u[j2] * loads[j2])
        for j1 in range(m) for j2 in range(m) if j1 != j2
    )))


def z3_preference(inst: Instance, assignment: dict) -> float:
    """Sum of (S_max - S_assigned) over blocks."""
    return float(sum(b.pref_max - b.prefs[assignment[b.id]] for b in inst.blocks))


def total(inst: Instance, assignment: dict, exit_times: dict) -> float:
    return (inst.w1 * z1_tardiness(inst, exit_times)
            + inst.w2 * z2_imbalance(inst, assignment)
            + inst.w3 * z3_preference(inst, assignment))
