"""
solver -- clean-slate architecture for OGC 2026 (DESIGN_FROM_SCRATCH_2026-07-24).

Architecture A (LBBD two-level matheuristic) with Architecture B
(project-and-repair) as its inner oracle layer, running on the Part II
conservative-raster occupancy engine.  utils.py remains the only feasibility
oracle: the engine is sound-by-construction (conservative) and every returned
solution passes through the utils gate in api.algorithm().

Module map (design-doc section in brackets):

    budget.py      deadline governor, 0.93*t - 1 effective budget   [contract]
    model.py       parsed instance: bays, blocks, geometry, weights [Part I]
    rasters.py     conservative raster stamps per orientation       [Part II]
    occupancy.py   per-bay spatio-temporal occupancy grids          [Part II]
    candidates.py  placement search over the occupancy window       [Part II]
    objective.py   Z1/Z2/Z3 accounting, bit-identical to utils      [T9/III.1]
    assignment.py  Z2/Z3-exact assignment master + cut interface    [Part IV]
    oracle.py      per-bay packing oracle (projected times)         [Part V]
    rescue.py      exact-polygon rescue tier                        [III.1 t1]
    tuck.py        exact-layer crane mode (stub)                    [III.1 t2]
    cluster.py     CP-SAT conflict-cluster repair (stub)            [III.1 t3]
    bounds.py      per-bay cumulative-relaxation lower bounds       [III.2]
    tasks.py       typed work units for the 4-core ladder           [Part VI]
    conductor.py   pipeline orchestration (sequential v0)           [Part VI]
    incumbent.py   incumbent store + utils audit gate               [contract]
    emit.py        solution-dict emission (EXIT-before-ENTRY)       [wire fmt]
    api.py         algorithm(prob_info, timelimit) entry point      [contract]

The legacy pipeline (myalgorithm.py + alns/) is untouched: per the
experimental plan (Part VIII), milestone 3 is the go/no-go before this
package replaces it as the entry point.
"""

from .api import algorithm, solve  # noqa: F401
