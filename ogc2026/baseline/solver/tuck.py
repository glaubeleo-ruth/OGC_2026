"""
tuck.py -- exact-layer crane mode, tier 2 of the false-tardiness ladder (III.1).

NOT IMPLEMENTED in v0 (deliberate: design T5 measures the capacity given up
by conservative footprints as small on train instances; this tier is the
optional unlock for overloaded instances, Part VIII milestone 5).

Contract for the implementation:

  exact_layer_search(bay, block, co_present_blocks, e0, e1, deadline)
      -> (x, y, stamp, entry_order_constraints) | None

  * Full j >= k crane model over true per-layer polygons: a placement is
    feasible iff for the chosen entry/exit *ordering*, every layer k of the
    moving block is disjoint from every layer j >= k of blocks present at
    that operation instant (utils.check_entry / check_exit semantics).
  * Unlocks tuck-under-overhang capacity: a low block may slide under a
    taller block's overhang if it enters before and exits after it.
  * IMPORTANT (III.3): the Exit-ASAP dominance is INVALID in this mode --
    exit times re-enter the model as decision variables; callers must not
    assume exit == entry + proc for tuck placements.
  * Ordering: this tier runs only after rescue.exact_search failed, and its
    verdict feeds cluster.py (tier 3) before a tardy day is accepted.

Returning None (not raising) keeps the ladder graceful until implemented.
"""

from __future__ import annotations


def exact_layer_search(bay, block, co_present_blocks, e0, e1, deadline):
    """Tier-2 stub: no exact-layer capacity unlock yet. Always None."""
    return None
