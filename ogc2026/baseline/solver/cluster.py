"""
cluster.py -- CP-SAT conflict-cluster repair, tier 3 of the ladder (III.1,
Part V stage 3).

NOT IMPLEMENTED in v0.  The greedy oracle is myopic: a different arrangement
of earlier blocks could have fit everyone.  This tier closes that gap with an
exact joint solve over a small conflict cluster.

Contract for the implementation:

  repair(inst, bay, occupancy, placements, cluster_ids, deadline, budget)
      -> list[Placement] | None

  * cluster_ids: the delayed block plus its time-space neighbors (blocks
    whose stamps touch the congested window), typically <= 15 blocks.
  * Model: joint positions x orientations x entry days for all cluster
    members, pairwise-disjoint raster stamps as precomputed compatible
    position literals (the fno pairwise-compatibility trick), entries in
    [release, release + slack + delta], exit = entry + proc (conservative
    mode), objective min sum w1 * T_i.  Exact within its window: window size
    grows with remaining budget, so the truncation is explicit and budgeted,
    never silent (III.1 tier 3).
  * A repair returning tardiness == cluster LB (bounds.bay_lb on the cluster)
    is a certificate; the conductor then stops spending on this cluster.
  * Solver guard rails: num_search_workers = 1, max_time_in_seconds = budget.

Returns None (no improvement found / not implemented) -- callers keep the
greedy packing.
"""

from __future__ import annotations


def repair(inst, bay, occupancy, placements, cluster_ids, deadline, budget):
    """Tier-3 stub: keep the oracle's packing. Always None."""
    return None
