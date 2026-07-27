"""
bounds.py -- certified tardiness lower bounds (design III.2, F5 formulation).

Per-bay cumulative relaxation: discard geometry, keep aggregate area *per
layer index*.  utils checks collisions only between same-index layers, so for
every layer index l the layer-l polygons of co-present blocks must be
pairwise disjoint inside the bay -- hence Σ (layer-l areas of present blocks
having a layer l) <= A_j is valid for each l.  The model is one CP-SAT with
**one cumulative constraint per layer index** (<= ~4), shared interval
variables per block, minimizing Σ T_i.

F5 soundness note -- why NOT largest-layer-area on a single cumulative (the
v0 bug): blocks can peak at different layer indices and legally interleave
(big-base X under big-top Y), so Σ max-areas can exceed A_j in a feasible
state; a bound built on it can exceed the true optimum and fabricate wrong
certificates.  Per-layer demands use the *minimum* layer-l area across the
block's orientations (areas are rotation-invariant in practice, but min keeps
the relaxation valid regardless), floored (demand <= true consumption).

Its BestObjectiveBound (valid even on timeout) certifies:

  * gap = Z1_j - LB_j == 0  ->  bay j proved Z1-optimal; compute moves on.
  * pooled LB > 0 at start  ->  zero tardiness impossible under any
    assignment; the pipeline opens in minimal-tardiness mode (triage).

Every benchmark table reports the gap, not just raw Z1 (Part VIII m2).
Returns None when ortools is unavailable -- callers treat that as "no
certificate", never as LB = 0.
"""

from __future__ import annotations

import math

import numpy as np

from .model import BayInfo, Instance

try:
    from ortools.sat.python import cp_model
    _HAS_CPSAT = True
except Exception:                                        # pragma: no cover
    _HAS_CPSAT = False


def _layer_demand(block, layer_idx: int) -> int:
    """Floor of the min layer-`layer_idx` area across orientations; 0 when
    some orientation lacks that layer (a valid, weaker demand)."""
    areas = []
    for s in block.stamps:
        if layer_idx >= len(s.layer_areas):
            return 0
        areas.append(s.layer_areas[layer_idx])
    return max(0, int(math.floor(min(areas)))) if areas else 0


def _cumulative_lb(inst: Instance, block_ids, capacity: int,
                   time_cap: float) -> int | None:
    if not _HAS_CPSAT:
        return None
    if not block_ids:
        return 0
    horizon = inst.horizon + sum(inst.blocks[i].proc for i in block_ids)
    model = cp_model.CpModel()
    tards = []
    intervals = {}
    for i in block_ids:
        b = inst.blocks[i]
        start = model.NewIntVar(b.release, horizon, f"s_{i}")
        intervals[i] = model.NewFixedSizeIntervalVar(start, b.proc, f"iv_{i}")
        tard = model.NewIntVar(0, horizon, f"t_{i}")
        model.Add(tard >= start + b.proc - b.due)
        tards.append(tard)

    # F5: one cumulative per layer index over the blocks that have that layer.
    n_layers = max(len(s.layer_areas)
                   for i in block_ids for s in inst.blocks[i].stamps)
    for l in range(n_layers):
        ivs, dems = [], []
        for i in block_ids:
            d = _layer_demand(inst.blocks[i], l)
            if d > 0:
                ivs.append(intervals[i])
                dems.append(d)
        if ivs:
            model.AddCumulative(ivs, dems, capacity)

    model.Minimize(sum(tards))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.1, time_cap)
    solver.parameters.num_search_workers = 1   # guard rail: 1 thread per solver
    status = solver.Solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return int(math.ceil(solver.BestObjectiveBound() - 1e-9))
    return 0  # UNKNOWN etc.: 0 is always a sound lower bound


def congestion_profile(inst: Instance, bay: BayInfo, block_ids):
    """Per-day, per-layer *mandatory* area load vs bay capacity (O3/F4).

    A block must occupy the bay on every day common to all zero-tardiness
    schedules: days in [zero_window_last_entry, release + proc) (non-empty
    exactly when the window is tighter than the processing time).  Summing
    layer-l areas of those mandatory presences gives, for each (layer, day),
    a load that every zero-tardiness solution must fit under A_j -- a sound
    per-day energetic signal:

      * load > A_j at any (layer, day) certifies that zero tardiness is
        impossible for this bay-assignment (a valid LB >= 1 trigger);
      * the *peak windows* (days near capacity) are the congestion the
        queue-aware construction must steer wide-slack blocks away from.

    Returns (loads, peak_days): loads is a numpy array (n_layers, horizon);
    peak_days the sorted days where any layer exceeds capacity.
    """
    blocks = [inst.blocks[i] for i in block_ids]
    if not blocks:
        return np.zeros((1, inst.horizon)), []
    n_layers = max(len(s.layer_areas) for b in blocks for s in b.stamps)
    horizon = inst.horizon + max((b.proc for b in blocks), default=0)
    loads = np.zeros((n_layers, horizon))
    for b in blocks:
        lo = max(b.release, b.zero_window_last_entry)
        hi = min(b.release + b.proc, horizon)
        if lo >= hi:
            continue   # window wide enough that no day is mandatory
        for l in range(n_layers):
            d = _layer_demand(b, l)
            if d > 0:
                loads[l, lo:hi] += d
    over = (loads > bay.area).any(axis=0)
    peak_days = [int(t) for t in over.nonzero()[0]]
    return loads, peak_days


def bay_lb(inst: Instance, bay: BayInfo, block_ids, time_cap: float = 2.0) -> int | None:
    """Certified lower bound on total tardiness of bay `bay` under the given
    assignment (LB_j(S_j) of III.2)."""
    return _cumulative_lb(inst, list(block_ids), bay.area, time_cap)


def pooled_lb(inst: Instance, time_cap: float = 3.0) -> int | None:
    """All bays merged into one resource: instance-triage bound (III.2)."""
    capacity = sum(b.area for b in inst.bays)
    return _cumulative_lb(inst, [b.id for b in inst.blocks], capacity, time_cap)
