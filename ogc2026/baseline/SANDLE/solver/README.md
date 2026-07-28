# solver/ — clean-slate architecture (DESIGN_FROM_SCRATCH_2026-07-24)

Architecture A (LBBD two-level matheuristic) with Architecture B
(project-and-repair) as its inner oracle, on the Part II conservative-raster
engine. The legacy pipeline (`myalgorithm.py` + `alns/`) is untouched:
milestone 3 of the experimental plan is the go/no-go before this package
becomes the entry point.

## Module → design-doc map

| Module | Design section | Status |
|---|---|---|
| `budget.py` | contract (0.93·t − 1 governor) | done |
| `model.py` | Part I ground truths as data | done |
| `rasters.py` | Part II conservative stamps (F1 ¼-cell) | done — reject rate 3.7% < 5% criterion (measured 2026-07-25) |
| `occupancy.py` | Part II spatio-temporal grids | done (¼-cell numpy bool; F6 dirty mask pending with tuck) |
| `candidates.py` | Part II placement search | done (FFT feasibility maps; bottom-left) |
| `objective.py` | T9 / III.1 utils-identical pricing | done |
| `assignment.py` | Part IV master (Z2/Z3 + fluid capacity + cut interface) | done (single-shot; LBBD re-solve loop pending) |
| `oracle.py` | Part V stages 2–3, Exit-ASAP dominance | done (deadline-threaded; rushed degradation mode) |
| `repair.py` | Part IV oracle neighborhood (Z1-first cross-bay repair) | done (raster-only; joint moves belong to cluster.py) |
| `rescue.py` | III.1 tier 1 (exact polygon) | done |
| `tuck.py` | III.1 tier 2 (exact layer) | **stub** (milestone 5) |
| `cluster.py` | III.1 tier 3 (CP-SAT cluster repair) | **stub** (milestone 3) |
| `bounds.py` | III.2 lower bounds / certificates (F5 per-layer) | done |
| `tasks.py` | Part VI task ladder types | done (types only) |
| `conductor.py` | Part VI orchestration | sequential v0; fork pool pending (milestone 6) |
| `incumbent.py` | utils audit gate | done |
| `emit.py` | wire format (EXIT before ENTRY) | done |
| `api.py` | entry contract + seed fallback | done |

## Soundness invariant (why v0 solutions pass utils by construction)

Raster stamps over-approximate the union-of-layers footprint (closed-cell
`intersects`), so raster-disjoint ⇒ polygon-disjoint conservative footprints
⇒ (T5) per-layer collision-free and crane-safe at any operation order.
Rescue-tier placements re-establish the same invariant with exact geometry.
`utils.check_feasibility` remains the only gate: every candidate incumbent is
audited before it can be returned (hard rule 4).

## Running

```bash
cd ogc2026/baseline/sub && conda run -n ogc2026 python - <<'EOF'
import json, time
from solver import algorithm
import utils
prob = json.load(open("../../../train/prob_1.json"))
t0 = time.monotonic(); sol = algorithm(prob, 60); wall = time.monotonic() - t0
res = utils.check_feasibility(prob, sol)
print(res["feasible"], res["objective"], res["obj1"], res["obj2"], res["obj3"], f"wall={wall:.1f}s")
EOF
```

Smoke: `python -m solver._smoke_test` · Parity (milestone 1):
`python -m solver._parity_test` (both from `baseline/sub/`, ogc2026 env).

## Next milestones (Part VIII)

2. LB harness sweep over all 40 train instances; report Z1-vs-LB gap per
   instance as the primary KPI.
3. Cluster repair (`cluster.py`) + panel comparison vs legacy → go/no-go.
4. LBBD cut loop (master re-solves with streamed cuts) at t ∈ {60…1800}s.
5. Exact-layer tucking (`tuck.py`) for overloaded instances.
6. Fork worker pool over `tasks.py` units; scaling test at 1/2/4 cores.
