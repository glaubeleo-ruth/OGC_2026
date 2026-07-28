"""
congestion.py -- the F17 assignment arm (selectable, OFF by default).

rex's blindspot pass 2026-07-26 (F17) measured that on the mass instances the
fluid tardiness is manufactured by the *assignment*, not by capacity: with
theta identically 0 the master minimises w2*Z2 + w3*Z3 alone and pours the
majority of the blocks into one bay, taking the entry=release per-layer load
to 1.3-2.1x that bay's area.  A congestion-aware greedy assignment removed
100% of the fluid tardiness on 4 of 6 gate instances and, end to end through
the unmodified conductor, beat the master assignment on 6/6 (N=1 -- direction
only, which is exactly why this ships as an A/B arm and not as the default).

The rule implemented here, stated as a criterion rather than a fitted recipe:

    process blocks in release order (ties: largest peak layer first, so the
    hardest-to-place mass claims space before the filler);
    send each block to the compatible bay where the *congestion it will
    experience* is smallest -- the per-layer excess area-days that bay would
    carry over the block's own occupancy window [release, release+proc) once
    the block is added; ties broken toward the block's bay preference (Z3),
    then bay id for determinism.

Why that window: the packer's shipped skeleton is enter-ASAP, so
[release, release+proc) is the interval the oracle will actually try to use.
Why "experienced" rather than "marginal" congestion: a bay already over its
per-layer area in the block's window will delay the block whether or not this
particular block is the marginal cause, and the arm's job is to keep blocks
out of those windows.  Demands are bounds._layer_demand (the min-over-
orientations floor, F5) and the capacity is the bay area per layer -- the same
quantities bounds.py's certified cumulative LB uses, so the arm and the bound
speak about the same resource.

No instance-fitted constants appear here: every number is instance data
(release, proc, layer areas, bay areas, preferences).

Soundness scope: this is a *heuristic assignment*, one input to the oracle.
It cannot create or hide tardiness by itself -- every placement it leads to is
packed by the same engine, priced by objective.py and audited by
utils.check_feasibility before it can become an incumbent.  It computes no
bounds and therefore contributes nothing to theta (F8 discipline): certified
lower bounds keep coming from bounds.py alone.
"""

from __future__ import annotations

import numpy as np

from .bounds import _layer_demand
from .budget import Deadline
from .model import Instance


def _n_layers(inst: Instance) -> int:
    return max((len(s.layer_areas) for b in inst.blocks for s in b.stamps),
               default=0)


def _peak_layer_area(block) -> float:
    return max((s.max_layer_area for s in block.stamps), default=0.0)


def _fallback_bay(inst: Instance) -> int:
    """Same degenerate-case rule the master uses: no orientation fits any bay
    -> hand it to the largest bay and let the oracle/utils gate decide."""
    return max(inst.bays, key=lambda x: x.area).id


def congestion_assignment(inst: Instance, deadline: Deadline | None = None,
                          reserve: float = 0.0) -> tuple[dict, dict]:
    """Return ({block_id: bay_id}, info).  Never raises.

    WATCHDOG rule served: deadline threading.  The loop polls the shared
    Deadline (minus the caller's reserve) once per block and degrades to the
    preference-greedy choice for whatever is left rather than running past the
    reserve; the arm is pure arithmetic, so this only ever fires on a budget
    that was already gone.
    """
    info: dict = {"arm": "congestion", "degraded": 0}
    n_layers = _n_layers(inst)
    if not inst.blocks or not inst.bays or n_layers == 0:
        info["degraded"] = len(inst.blocks)
        return ({b.id: _fallback_bay(inst) for b in inst.blocks} if inst.bays
                else {}), info

    max_proc = max(b.proc for b in inst.blocks)
    horizon = inst.horizon + max_proc + 2
    load = {bay.id: np.zeros((n_layers, horizon), dtype=np.int64)
            for bay in inst.bays}
    area = {bay.id: int(bay.area) for bay in inst.bays}

    order = sorted(inst.blocks, key=lambda b: (b.release, -_peak_layer_area(b),
                                               b.id))
    out: dict = {}
    overload_total = 0
    for k, b in enumerate(order):
        compat = inst.compatible_bays(b) or [_fallback_bay(inst)]
        if deadline is not None and deadline.expired(margin=reserve):
            # Budget died: finish with the cheap preference rule (no scans).
            for rest in order[k:]:
                rc = inst.compatible_bays(rest) or [_fallback_bay(inst)]
                out[rest.id] = max(rc, key=lambda j: (rest.prefs[j], -j))
                info["degraded"] += 1
            break

        dem = [_layer_demand(b, l) for l in range(n_layers)]
        lo = max(0, min(b.release, horizon - 1))
        hi = min(horizon, lo + b.proc)
        best_j, best_key = None, None
        for j in compat:
            over = 0
            if hi > lo:
                for l in range(n_layers):
                    if dem[l] > 0:
                        seg = load[j][l, lo:hi] + dem[l] - area[j]
                        if seg.size:
                            over += int(seg[seg > 0].sum())
            key = (over, -b.prefs[j], j)
            if best_key is None or key < best_key:
                best_key, best_j = key, j
        out[b.id] = best_j
        overload_total += best_key[0]
        if hi > lo:
            for l in range(n_layers):
                if dem[l] > 0:
                    load[best_j][l, lo:hi] += dem[l]

    info["experienced_overload"] = overload_total
    info["bay_sizes"] = {bay.id: sum(1 for j in out.values() if j == bay.id)
                         for bay in inst.bays}
    return out, info
