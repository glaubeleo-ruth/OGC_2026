# OGC 2026 — Clean-Slate Design (utils.py as the only inherited artifact)

Date: 2026-07-24 · **v4** (red-team amendments folded in from BLINDSPOT_PASS_DESIGN_V3.md,
findings F1–F7 — see the amendment log at the end). Premise: forget the existing pipeline.
The only trusted objects are `utils.py` (the official oracle) and the problem definition.
Everything below is derived from those two sources plus measured statistics of six train
instances — and, as of v4, every load-bearing claim that could be measured has been.

---

# Part I — Ground truths the design must be built on

These are facts, not choices. Any architecture that ignores one of them is fighting the
problem instead of exploiting it.

**T1. Z2 and Z3 are pure functions of the assignment.**
obj2 = max over bay pairs of |u_j·ΣL_i| difference and obj3 = Σ(S_max − S_assigned) depend
*only* on which bay each block goes to — not on positions, orientations, or times. The full
objective splits as:

    objective(σ, geometry, times) = w1·Z1(times) + [w2·Z2(σ) + w3·Z3(σ)]

where σ is the assignment. Two-thirds of the objective is decided at a layer where the
problem is a small combinatorial assignment (n ≤ ~300, m ≤ ~5) — exactly solvable.

**T2 (amended, F3). Slack is near-zero on easy/mid instances; the tail has real temporal
freedom.**
Measured across prob_1/12/14/20/39/40: on easy/mid instances 51–59% of blocks have slack
(due − release − proc) ≤ 1 and ~100% ≤ 4 — there, entry ≈ release, exit ≈ entry + proc is
the right skeleton and time is a *repair* dimension only. But the tail breaks this:
prob_40 has only 21% of blocks at slack ≤ 1, 47% above 4, max 13 — **on tail instances,
which day each block enters is a real combinatorial decision** (ordering/queueing under
congestion). w1 remains enormous relative to w2/w3 (prob_1: 29091 vs 7/200), so the
zero-tardiness windows still bound the search — but wide-slack instances get a
queue-aware temporal construction, not a blind projection. Triage classifies the slack
profile per instance and selects the mode.

**T3. Everything relevant is small integers.**
Bays ≤ ~170 × 30 integer cells. Horizon (max due) ≈ 55–85 integer days. Positions are
integers (the server rounds x, y before checking). n ≤ ~300, m ≤ 5, orientations ≤ 8,
layers 1–4, polygons ~6–7 vertices. The entire spatio-temporal occupancy of one bay is
representable as ~85 bitmaps of ≤ 4,800 bits each — about 40 KB per bay.

**T4. Bays are independent given the assignment.**
All five checker stages operate per bay. Feasibility and Z1 decompose completely across
bays; only Z2/Z3 couple them — and those live at the assignment layer (T1).

**T5 (amended, F2). The crane rule collapses under a conservative footprint — but the
concession is bimodal, and the tail pays it.**
The j ≥ k descent rule means a 1-layer block entering must clear *every* layer of every
present block over its footprint. Define each block's **conservative footprint** = union of
all its layers' polygons (per orientation). If co-present blocks' conservative footprints
never interiorly overlap, then *no* layer-k-vs-layer-j pair can collide — Stages 2, 3, 4,
and 5 all pass automatically. Measured: the median block has perfectly nested layers
(union = base, conservative model exact for it), **but the p90 block's union is 1.6–3.4×
its base**, 83–98% of blocks are multi-layer, and the overhang-heavy share peaks exactly
on the tail (prob_14: 96%, prob_40: 98%, p90 union/base 3.1–3.4). Overhang blocks are
precisely the ones that fail to place. Design consequence: **conservative footprints
remain the default for the nested majority, but exact-layer tucking is a core oracle mode
— selected at triage by the instance's overhang share — not an optional unlock.** The
tuck-under capacity requires entry/exit ordering (the low block enters before the
overhanging one, leaves after); those ordering variables live in the cluster CP.

**T6. The oracle is expensive; the search must not call it.**
`utils.check_feasibility` rebuilds every Block (Shapely polygons cached at construction)
and runs polygon intersections per call — milliseconds to tens of milliseconds per call at
n = 250. Any architecture whose inner loop calls it is capped at ~10²–10³ evaluations per
second. The checker's role is a **final gate and a spot-audit**, never an inner loop.

**T7. Scoring is rank-based (R − nb per instance; −1 for infeasible/timeout/crash).**
Robustness is worth more than average quality; exactness on easy instances (where everyone
reaches Z1 = 0 and ranks are decided by Z2/Z3 dust) is worth disproportionate rank; the
hard tail is where large rank gaps open.

**T8. The evaluation budget is 4 cores × wall-clock, and the problem decomposes along it.**
The server grants exactly 400% CPU. A single-threaded solver forfeits 75% of the
evaluation budget; but more importantly, T4 (bay independence) and the cluster locality of
Part V mean this problem offers *structural* parallelism — independent subproblems — not
just the statistical parallelism (restart portfolios) that monolithic designs are limited
to. Cores are an instrument: per T9, their marginal use is to buy *exactness* (larger
exact windows, optimality certificates), and only then throughput or diversity.

**T9. The design objective is the true minimum, tardiness first — speed is instrumental.**
Given the w1 magnitudes (one tardy day ≈ 145× the maximum single-block Z3 swing on
prob_1) and rank scoring, the target is not "a good solution fast" but **Z1 at its
provable minimum — usually zero — and then Z2/Z3 exactly optimal given that**. Every
approximation in the pipeline must therefore be one-sided (never able to *create* a tardy
day silently) or be closed by an exact tier before a tardy day is accepted. Part III
turns this into a program.

---

# Part II — The shared engine both architectures need

## Bitset spatio-temporal occupancy (the incremental-evaluation core)

Per (bay, day): a bitmap over the bay at **sub-cell resolution** (F1: measured at unit
cells, the conservative cover taxes the median block +31–40% phantom area and the p90
block +50–75%, because blocks are small — median 31–77 cells; at ¼-cell resolution the
tax drops to ~8–10% while placements stay integer). At ¼-cell: ≤ ~77k bits ≈ 1.2k uint64
words per bay-day. Per block and orientation, precompute once: a **conservative raster
cover** — every sub-cell intersected by the union-of-layers polygon, dilated to dominate
the ≤ 4-decimal fractional vertices — stored as a bit-stamp plus its bounding box. The
resolution is chosen at milestone 1 by sweeping ½/¼/⅛ cell against the exit criterion:
**raster-reject rate < 5% on placements exact geometry accepts.**

- **Placement test** of block b at (x, y, o) over days [e, x): shift-AND the stamp against
  each day's bitmap → ~75·proc word ops ≈ **microseconds**. This is 10³–10⁴× faster than a
  Shapely path and 10⁵× faster than check_feasibility.
- **Commit / undo**: OR / AND-NOT the stamp into the day range. O(same).
- **Candidate generation**: skyline/anchor positions from the bitmap (positions adjacent
  to occupied cells or walls), not all ~4,800 cells — typically a few hundred candidates.
- **Soundness**: the raster is conservative (over-approximates the polygon), so a bitmap
  "fits" that is actually an overlap is impossible; false *negatives* (rejects of true
  fits) cost capacity — which is why the resolution is chosen by the < 5% reject-rate
  criterion, and why tier-1 exact rescue backs every tardiness-relevant rejection. On
  accept of a *final* solution, `utils.check_feasibility` remains the gate (Hard Rule).
- **Dirty-cell containment (F6)**: "conservative ⇒ no crane checks" is a *bay-wide*
  invariant, broken the moment tier-2 places one tucked cluster. Tucked placements mark
  their cells in a parallel **dirty mask**; any placement or removal touching dirty cells
  routes through the exact j ≥ k crane check (bounded — dirty regions are small and
  local). Invariant: clean cells ⇒ the bitmap is truth; dirty cells ⇒ exact check
  mandatory. Without this, mode-mixing is a silent-infeasibility (−1-class) path.
- **Horizon headroom (F7)**: tardy exits land beyond max_due; bitmaps span max_due +
  tardiness headroom and grow lazily on first access. An index crash on a tardy tail
  instance would itself be a −1.

Memory at ¼-cell: ~5 bays × ~100 days × ~150 KB ≈ 75 MB — comfortable within 16 GB, and
trivially forkable (copy-on-write) for parallel workers. Every architecture below assumes
this engine; it is the single highest-leverage build item in this document.

---

# Part III — The tardiness program: modeling Z1 to a provable minimum

This part is the core of the design under T9. It answers two questions no heuristic
answers on its own: *is every tardy day in our solution truly forced by the instance?*
and *how would we know?*

## III.1 The accuracy ladder — three sources of false tardiness, each closed

A block becomes tardy in our pipeline only if it cannot be placed inside its
zero-tardiness window. There are exactly three ways the pipeline could wrongly conclude
"cannot":

1. **Raster conservatism.** The dilated bit-stamp over-approximates the polygon; a
   placement that exactly fits can be raster-rejected. *Closure:* whenever raster search
   fails to place a block within its zero-tardiness window, an **exact-polygon rescue**
   (Shapely / no-fit-polygon over the true fractional geometry, integer anchor points)
   re-searches the same window before any delay is considered. The raster is a filter for
   speed; it is never allowed to be the *verdict* on tardiness.
2. **Conservative footprint (T5).** Union-of-layers gives up tuck-under-overhang
   capacity; on tight bays that concession can be the difference between fitting and
   delaying. *Closure:* **exact-layer mode** — the full j ≥ k crane model with entry/exit
   ordering variables — invoked per conflict cluster when the exact-polygon pass still
   fails. Ordering: cheap tier → exact geometry → exact geometry + exact crane model.
3. **Myopic packing order.** Greedy insertion can strand space so that a *later* block
   misses its window even though a different arrangement of *earlier* blocks would have
   fit everyone. *Closure:* the cluster CP-SAT solves are **exact within their window**
   (joint positions × orientations × entry days for all cluster members), and window size
   grows monotonically with remaining budget — the truncation is explicit and budgeted,
   never silent.

Only after all three tiers fail is a tardy day accepted — and then it is checked against
the lower bound below. Objective accounting itself is kept bit-identical to utils
(integer times, same rounding, same formulas), so "accuracy" includes never mis-pricing a
solution we already hold.

## III.2 Lower bounds — knowing the true minimum, not guessing it

**Per-bay cumulative relaxation — one constraint per layer index (F5).** Discard
geometry; keep aggregate area, *per layer*. utils checks collisions only between
same-index layers, so for each layer index l the layer-l polygons of co-present blocks
must be pairwise disjoint inside the bay — hence, for every l, Σ (layer-l areas of
present blocks having a layer l) ≤ A_j = W_j·H_j is valid. The LB model is a single
CP-SAT with **one cumulative constraint per layer index** (≤ 4 of them), shared interval
variables per block, minimizing Σ T_i (≤ ~80 tasks per bay, horizon ≤ ~100) — solvable to
optimality in seconds. Its value **LB_j(S_j) is a certified lower bound** under
assignment S_j.

*Soundness note (why not "largest-layer area" on one cumulative):* blocks can peak at
different layer indices and legally interleave — big-base X and big-top Y coexist with
their largest layers at different heights — so Σ max-areas can exceed A_j in a feasible
state. A bound built on it can exceed the true optimum and fabricate gap-0 certificates.
The per-layer formulation is both sound and tighter. Property test (milestone 2): LB must
never exceed the objective of any known-feasible schedule, checked over randomized
feasible bays.

Consequences:
- **Certificates.** If the achieved Z1_j equals LB_j (typically both zero), bay j is
  *proved* Z1-optimal — compute reallocates to Z2/Z3 with a clean conscience. No budget
  is ever spent chasing tardiness that cannot be reduced.
- **The KPI becomes the gap.** Every benchmark report carries Σ_j (Z1_j − LB_j) per
  instance, not just raw objective. "Extremely low" stops being a feeling; gap = 0 is a
  proof, gap > 0 is a work item with a known upper size.
- **Master guidance.** θ_j ≥ LB_j(S_j) cuts are sound and cheap to generate, giving the
  assignment master honest tardiness prices *before* any expensive geometric solve.
- **Instance triage (amended, F2/F3).** Three statistics computed once at start select
  the pipeline's modes: (1) the pooled relaxation (all bays as one per-layer resource) —
  if even it is tardy, zero-tardiness is impossible under *any* assignment and the
  pipeline opens in minimal-tardiness mode; (2) **overhang share** (fraction of blocks,
  and of area, with union/base > 1) — high values enable exact-layer tucking as a core
  oracle mode; (3) **slack profile** (share of blocks with slack > 4) — wide-slack
  instances get the queue-aware temporal construction instead of the blind
  entry = release projection.

**Tightening — required for the tail, not optional (F4).** Measured with the correct
per-layer fluid ratios, every sampled instance sits at ≤ 0.56 at every layer — including
prob_40, which the legacy pipeline diagnosed as 1.57-overloaded by summing all layers
against single-surface capacity (a triple-count). Two consequences: tail tardiness is
geometric (overhangs) and temporal (wide slack), *not* area shortage — genuine rank
upside, since near-zero Z1 may be attainable where legacy results suggested otherwise;
and the plain fluid LB will read 0 on the tail, useless as a certificate there. So the
sharper relaxations — 1-D width-profile strip projections and energetic reasoning over
congestion sub-horizons — are scheduled for the tail from the start. Every member of the
relaxation ladder remains a true bound; only tightness varies.

## III.3 Dominance rules — shrinking the space without losing the optimum

- **Exit-ASAP dominance (conservative mode).** Under conservative footprints, removing a
  block earlier only enlarges free space at all later times and cannot violate any crane
  rule (T5); hence exit_i = entry_i + p_i weakly dominates any loiter. One entire decision
  dimension is eliminated with a proof, not a hope. Scope: the rule is *invalid* in
  exact-layer mode (a tucked block may have to out-wait its overhang) — there, exit
  variables re-enter the cluster CP explicitly. Scoped dominance is accuracy; unscoped
  dominance would be a bug.
- **Zero-tardiness windows first.** entry_i ranges over [r_i, d_i − p_i] during
  construction; tardy entries exist only inside cluster solves that have already proved
  (via III.1's ladder) that no zero-tardiness completion exists. The search cannot drift
  into tardiness for convenience.
- **Symmetry.** Identical blocks (same shape set, r, p, d) are interchangeable; fixing
  their index order in cluster models removes factorial symmetry from CP-SAT — accuracy
  per second, since symmetric branches prove the same bound repeatedly.

## III.4 When zero is truly impossible — exact minimal-tardiness repair

All tardy days cost the same w1, so the question is the minimum total number of tardy
block-days that resolves congestion. Inside a cluster this is already the CP-SAT
objective (Σ T_i, exact). Across clusters and bays, certified cluster optima flow into
the master as *exact* θ_j values, so assignment comparisons trade true tardiness — not
heuristic estimates that would systematically mis-route blocks under pressure. The
formal property worth stating (and putting in the technical report): **with subproblems
solved exactly, the LBBD loop converges to the global optimum; the deployed solver is
that exact method truncated by budget** — an anytime exact algorithm, not a heuristic
retrofitted with accuracy.

---

# Part IV — Architecture A: LBBD-style two-level matheuristic
*(assignment master + per-bay packing oracles)*

## Motivation
T1 + T4 say the problem is an assignment problem whose "cost to serve" is a per-bay
packing feasibility/tardiness question. That is textbook **logic-based Benders /
cost-oracle assignment** structure. Attacking it at that level solves Z2/Z3 exactly
(rank-decisive on easy instances, T7) and turns the hard geometry into m independent
subproblems that parallelize onto the 4 cores.

## Key Insight
Since Z2/Z3 are assignment-pure and Z1 ≈ 0 is achievable on most instances (demand ratios
0.19–0.56 at layer-0), the optimal solution is usually: *the Z2/Z3-optimal assignment
among those whose per-bay packing admits Z1 = 0.* Search assignments, not operations.

## Mathematical Formulation
Master (MIP over y_{ij} ∈ {0,1}, block i → bay j):

    min  w2·Z2(y) + w3·Z3(y) + Σ_j θ_j
    s.t. Σ_j y_ij = 1                            ∀i
         (fluid capacity) Σ_i a_i·p_i·y_ij ≤ ρ·W_j·H_j·T   ∀j     [warm-start validity]
         θ_j ≥ tardiness cuts from the oracle
         no-good / conflict cuts: Σ_{i∈S} y_ij ≤ |S| − 1 for oracle-refuted sets S

Z2's max-abs is linearized with one aux variable and 2·C(m,2) constraints; Z3 is linear.
Subproblem per bay j: given S_j = {i : y_ij = 1}, find positions/orientations/times
minimizing Σ tardiness — the per-bay packing problem, solved by the oracle below.

## Search Space
Master: m^n assignments, but the MIP prunes via Z2/Z3 optimality + cuts; in practice the
master re-solves in ~seconds at n=300, m=5 (n·m binaries, CP-SAT or Gurobi, both on the
server). Oracle: per-bay insertion orders × skyline positions × ≤8 orientations × entry
delays 0–slack.

## Neighborhood Design (oracle = packing heuristic inside each bay)
Insertion order: by release, tie-break by area descending (T2 makes release ≈ entry).
Place at skyline candidates minimizing a spatial-congestion surrogate (leftmost-lowest +
contact-perimeter). If a block cannot fit on its release day: try (a) entry delay up to
slack, (b) evict-and-reinsert of ≤ K co-present blocks (bitset makes retries cheap),
(c) report the minimal conflicting set to the master as a cut. Local search inside a bay:
remove-reinsert of the ≤ 20 blocks adjacent (in time-space) to the worst tardiness.

## Incremental Evaluation Strategy
Entirely on the bitset engine (Part II). Z2/Z3 deltas are O(1) arithmetic on assignment
change. Z1 delta = per-block max(0, exit − due) — O(1) per move. check_feasibility only on
the final answer and once per accepted master iteration as an audit.

## Expected Complexity
Master solve: seconds (exact, small). One oracle pass over a bay of ~60–80 blocks:
~10⁴–10⁵ bitset tests ≈ tens of ms. Full LBBD round (master + m oracles in parallel):
well under a second. Hundreds of rounds fit in even a 3-minute budget; a 30-minute budget
buys thousands of rounds plus deep per-bay local search — the design is natively
**anytime and long-budget-scalable** (fixes the 60-s-tuning trap).

## Expected Bottlenecks
(1) Cut quality: naive no-goods (|S|−1) are weak; minimal infeasible subsets (drop blocks
greedily until packable) are needed for master progress. (2) Oracle optimism: the packing
heuristic proving "tardy" doesn't mean no Z1=0 packing exists — cuts must be *sound*, so
tardiness cuts should use a budgeted CP-SAT verification on small conflict clusters before
cutting, or be added as soft (θ_j) rather than hard no-goods. (3) Master degeneracy when
w2·Z2 has flat plateaus — break with lexicographic Z3 then Z2.

## Scalability
n=500, m=10 would grow the master trivially (5,000 binaries) and the oracles linearly.
The bitset engine is size-independent up to bay ~256×64 (one more word column). Degrades
gracefully: if the master stalls, the incumbent assignment's oracles keep polishing.

## Hidden-Test Robustness
Single bay (m=1): master is trivial, Z2 = 0 by definition, architecture reduces to the
per-bay oracle — no special-casing. Overloaded instances: fluid capacity + tardiness cuts
push excess load to cheap bays; the oracle's delay mechanism produces honest Z1. Weight
regimes: the master re-optimizes whatever w2/w3 mix the instance declares (no hardcoded
multipliers — the numbers that overfit train disappear entirely). Failure containment:
first feasible solution exists after the first oracle pass (~1 s); every later stage only
replaces it via the utils gate.

## What would beat Architecture A?
An opponent exploiting exact-layer tucking on genuinely overloaded instances (A's
conservative footprint concedes capacity), or one whose per-bay packing is exact rather
than heuristic on mid-size bays. Both are A's own extension points (T5 unlock; CP-SAT
oracle below).

---

# Part V — Architecture B: Conflict-cluster fix-and-optimize over a projected schedule
*(project times → pack → repair congestion exactly)*

## Motivation
T2 says time is nearly decided. B takes that literally: fix entry_i = release_i,
exit_i = release_i + proc_i for all blocks, and treat the whole problem as **placement
only**. Where the projection is geometrically impossible, repair *locally and exactly*.

## Key Insight
With times projected, each bay-day's contents are known up front; infeasibility manifests
as small, local, identifiable **conflict clusters** (blocks co-present in one bay whose
areas can't coexist). The global problem collapses into: assign (Z2/Z3), place (geometry),
and a sparse set of local conflicts to resolve by exact micro-optimization (CP-SAT over
positions × small delays for ≤ 15 blocks at a time).

## Mathematical Formulation
Stage 1: assignment as in A's master (Z2/Z3-exact, fluid capacity).
Stage 2: per bay, chronological insertion via bitset skyline — at projected times
(entry = release) on narrow-slack instances; on wide-slack instances (F3 triage) a
**queue-aware construction** first prices each block's entry day within its window by
per-day congestion (a small per-bay scheduling pass), so insertion starts near a good
temporal ordering instead of a blind projection.
Stage 3: for each unplaced/conflicted block set C (grown to its time-space neighbors),
solve exactly:

    min Σ_{i∈C} w1·T_i   s.t. positions on the raster grid, pairwise disjoint stamps,
    entry_i ∈ [release_i, release_i + slack_i + Δ], exit_i ≥ entry_i + proc_i

as CP-SAT with precomputed pairwise-compatible position literals (the fno idea — but as
the *primary* mechanism, budgeted per cluster, not a polish pass).

## Search Space / Neighborhood Design
No global metaheuristic walk at all. The only "neighborhood" is cluster selection:
worst-tardiness cluster first, then round-robin over residual conflicts; clusters overlap
so improvements propagate. Optionally a final Z2/Z3 reassignment pass for blocks with
geometric room in multiple bays.

## Incremental Evaluation Strategy
Same bitset engine; clusters lift a sub-bitmap, CP-SAT solves, commit re-stamps. Z-deltas
O(1) as in A.

## Expected Complexity
Stage 1+2: ~1 s total. Each cluster solve: 0.1–2 s budgeted. Even 60 s handles ~30–100
clusters; 30 min handles all clusters to proof or budget exhaustion.

## Expected Bottlenecks
Cluster explosion on heavily overloaded instances (ratio > 1): conflicts stop being
local, clusters merge, CP-SAT windows blow up — B degrades to A-style global reasoning
poorly. Cluster boundary effects: a locally-optimal repair can push congestion into the
next cluster (mitigate with overlapping windows and 2 sweeps).

## Scalability / Hidden-Test Robustness
Excellent on under-loaded and moderate instances (the majority: ratios 0.19–0.56);
fragile exactly where instances are overloaded. Verdict: B is not a standalone entry —
it is the **right oracle-and-repair layer inside A** for the easy/moderate regime.

---

# Part VI — The 4-core execution model (parallelism in service of exactness)

## Motivation
The legacy pipeline spent its cores on a *portfolio* — four seed strategies, four
independent ALNS chains — because a monolithic search offers nothing better than
best-of-k diversity. The clean-slate design has independent subproblems by construction
(T4, T8), so the same 4 cores buy near-linear throughput on the critical path. In rank
currency: 3–3.5× more search depth on every instance beats a best-of-4 lottery whose
variance you already measured to be seed-dominated.

## Key Insight
Every unit of work in Architectures A + B is already a small, self-contained task with
disjoint state: an ORACLE pass touches one bay's bitmaps; a CLUSTER solve touches one
sub-bitmap window; an AUDIT is a read-only utils re-verify; the MASTER re-solve touches
only assignment variables. A conductor + worker-pool over these four task types keeps
4 cores saturated for any timelimit without any shared-memory locking.

## Process topology
- **Conductor (parent process)**: deadline governor, incumbent store, final utils gate,
  and the master MIP re-solves. Owns the only authoritative copy of the solution.
- **3 forked workers**: consume a task queue. Fork inherits the precomputed raster stamps
  and instance data copy-on-write — zero serialization cost for the heavy read-only state
  (~tens of MB); task messages carry only assignment diffs and bitmap windows.
- **Task types, in priority order** (expected rank-gain per second, T9-ordered — note
  the ladder spends marginal cores on *exactness* before extra heuristic iterations):
  1. `ORACLE(bay, assignment_version, rng)` — initial/repacking pass of one bay;
  2. `RESCUE(bay, block, window)` — exact-polygon re-search of a zero-tardiness window
     the raster rejected (III.1 tier 1), then `TUCK` exact-layer mode (tier 2) if it
     still fails: the false-tardiness closure ladder, run *before* any delay is accepted;
  3. `CLUSTER(bay, window)` — budgeted exact CP-SAT conflict repair (0.1–2 s granularity —
     this, not whole bays, is the work-stealing unit, so load imbalance across unequal
     bays disappears); window sizes grow as budget allows (III.1 tier 3);
  4. `BOUND(bay, S_j)` — cumulative-relaxation LB solve (III.2): certificates that stop
     Z1 work where zero is proved, and θ_j cuts for the master;
  5. `AUDIT(candidate)` — utils.check_feasibility on a would-be incumbent, off the
     critical path so the oracle loop never pays checker latency;
  6. deep polish / k-best pool exploration — Z2/Z3 micro-reassignment, scheduled only
     when every open bay is either certified Z1-optimal or budget-saturated.

## Asynchronous LBBD (master–oracle overlap)
The conductor re-solves the master *while* workers evaluate the previous assignment.
Cuts stream back asynchronously and are applied at the next master wake-up. This is safe
by construction: feasibility/tardiness cuts are globally valid statements about block
subsets, so a cut derived under assignment version v is sound under version v+1 —
staleness costs freshness, never correctness. Master latency (seconds) is thus fully
hidden behind oracle work; the critical path is oracle throughput, which is the part that
parallelizes linearly.

## Principled diversity (what remains of the portfolio idea)
On Z2/Z3 plateaus the master holds many near-optimal assignments (T7 ties). Instead of
one assignment, the conductor maintains a **k-best assignment pool**; when the task queue
runs short, workers evaluate *different pool members* rather than re-polishing the
incumbent. This is the portfolio re-derived from structure: diversity over assignments
the master has already proven near-optimal on Z2/Z3, not diversity over hand-tuned
strategy constants. Oracle RNG restarts (multi-start) fill any remaining idle capacity.

## Expected speedup
Initial oracle phase: ~min(m, 3)× (m = 2–5 bays on trains). Cluster repair: ~3×
(clusters ≫ cores, disjoint windows). Master: hidden entirely. Net effect ≈ 3–3.5× search
depth at any timelimit; time-to-first-feasible-incumbent (~1 s) is unchanged, so the −1
containment story does not depend on parallelism at all.

## Guard rails (contract, carried over unchanged)
Exactly 4 processes total; every embedded solver capped to 1 thread (`num_search_workers
= 1` — the repair.py:616 bug class is outlawed by rule); `OMP_NUM_THREADS=1` and BLAS
caps exported before any import; fork context only, with the sequential single-process
fallback when fork is unavailable; bounded joins with best-so-far salvage; the 0.93·t − 1
budget governor and seed-fallback discipline untouched. On a 1–2-core dev box the same
code runs with a smaller pool — behavior differs only in throughput, never in code path
(closing the "slots 3–4 never tested" blindspot structurally).

## Timelimit scaling
At 60 s the queue drains roughly once (assignment → oracles → clusters → audit). At
1800 s the conductor cycles master ↔ oracles until cuts stop improving the master bound,
then reallocates workers down the priority ladder (TUCK, pool exploration, deep polish).
Cores are never idle by construction, at any budget — the task ladder, not tuned
constants, decides where marginal compute goes.

---

# Part VII — Comparison and recommendation

| Criterion (rank currency, T7) | A: LBBD two-level | B: project-and-repair | Legacy ALNS (reference) |
|---|---|---|---|
| Easy instances (Z2/Z3 decide) | exact assignment → top ranks | exact assignment → top ranks | heuristic dust → mid ranks |
| Hard tail (overloaded) | honest degradation via cuts/delays | degrades badly | seed-quality lottery |
| Evaluations/sec | ~10⁵–10⁶ (bitset) | ~10⁵–10⁶ (bitset) | ~10²–10³ (Shapely/checker) |
| 4-core usage (T8) | structural: parallel oracles/clusters, ~3–3.5× depth | same engine | statistical: best-of-4 portfolio |
| Z1 accuracy (T9) | certified: LB gap = 0 is a proof; anytime-exact LBBD | exact within clusters, no global proof | no bound — "low" is a feeling |
| 30-min budget behavior | native anytime, more rounds | finishes early, idles | untested, tuned at 60 s |
| Overfit surface | none (no instance-fitted constants) | none | ~10 hardcoded gates |
| −1 risk containment | first-pass incumbent in ~1 s | same | seed fallback (good) |
| Report/presentation value | LBBD + bitset engine: publishable | component of A | incremental ALNS: weak story |

**Recommendation: build Architecture A with B as its inner repair layer.**
Concretely: bitset engine → per-bay oracle (B's stages 2–3) → assignment master with cuts
(A). The legacy pipeline's genuinely validated parts port in as components, not as the
frame: the multi-start idea becomes RNG-seeded oracle restarts; fno's pairwise-compatible
CP-SAT trick becomes the cluster solver; the seed-fallback discipline and deadline
governor carry over unchanged (they are contract requirements, not architecture).

**What would beat the combined design?** (standing question)
A team that (1) additionally unlocks exact-layer tucking capacity on overloaded instances
(T5's concession — add as an oracle mode when conservative packing proves tardy), or
(2) proves per-bay optimality with a stronger exact packing (anchored-rectangle or
no-fit-polygon CP over the true polygons) on mid-size bays, or (3) out-engineers us in
pure iteration throughput with a C/Rust engine (your 2024 entry did exactly this — the
bitset engine in numpy/numba should close most of that gap; Cython is on the server if
profiling says otherwise).

---

# Part VIII — Experimental Plan (order of construction, each step falsifiable)

1. **Bitset engine + parity test.** Property test: 10⁵ random placements × agreement with
   utils on feasibility (conservative: engine-feasible ⇒ utils-feasible must hold 100%).
   Exit criteria (F1/F6/F7): resolution sweep ½/¼/⅛ cell with **raster-reject rate < 5%**
   on placements exact geometry accepts; dirty-mask crane containment implemented and
   property-tested (tucked cluster + later contacting entry/exit must route exact);
   lazy horizon growth exercised by a forced-tardy case. Kill criterion: any soundness
   violation.
2. **Per-bay oracle + LB harness** on all 40 train instances, single bay at a time:
   measure % blocks placed with Z1 = 0 vs (correct per-layer) demand ratio, and compute
   the **per-layer-cumulative LB_j** for every bay (III.2, F5 formulation) plus the three
   triage statistics (pooled LB, overhang share, slack profile). Property test: LB never
   exceeds the objective of any known-feasible schedule (randomized feasible bays). From
   this milestone on, **every result table reports the Z1-vs-LB gap per instance** — the
   gap, not the raw objective, is the primary KPI. Expectation: ≥ 95% placed on per-layer
   ratios < 0.5, and gap = 0 on the majority of train bays.
3. **Assignment master (Z2/Z3-exact + fluid capacity)** + oracle: full pipeline v0.
   Compare vs legacy on the 8-instance panel, N = 5 reps, median. Kill criterion: v0 worse
   on > 2 panel instances after cluster repair is on.
4. **Cuts loop (LBBD)**: measure master–oracle rounds/minute and objective trajectory at
   t ∈ {60, 300, 900, 1800} s. This bakes long-budget behavior in from day one.
5. **Overload mode**: exact-layer tucking + exact minimal-tardiness repair (III.4) on
   prob_39/40-class and synthetic ratio > 1 instances; report gaps against the tightened
   relaxations of III.2. Kill criterion for the closure ladder: any accepted tardy day
   that a longer exact solve later removes on the same instance (i.e., a tier gave a
   false "cannot") — that is a soundness bug in the ladder's budgeting, not noise.
6. **Parallel scaling test**: same panel at 1, 2, and 4 pinned cores (`taskset`), thread
   caps exported; measure depth (oracle rounds, clusters solved) and objective vs core
   count. Expectation: ≥ 2.5× depth at 4 cores vs 1; identical incumbents modulo RNG.
   Kill criterion: oversubscription symptoms (per-worker throughput < 0.8× solo) — hunt
   the stray thread pool before proceeding.
7. **Server parity + gate**: 4 pinned cores, thread caps, utils final gate, seed-fallback
   contract, dry-run submission zip.

Milestone 3 is the go/no-go: if v0 with repair beats legacy on the panel median, the
clean-slate line replaces the legacy line; otherwise the bitset engine and master still
graft onto the legacy pipeline (no work is stranded either way).

---

# Appendix — Red-team amendment log (v4, 2026-07-24)

Source: BLINDSPOT_PASS_DESIGN_V3.md (measurements on prob_1/12/14/20/39/40).

- **F1** (measured): unit-cell raster taxes the median block +31–40% phantom area
  (p90 +50–75%) → engine moved to sub-cell resolution, chosen by a < 5% reject-rate
  criterion. [Part II]
- **F2** (measured): overhangs are bimodal — median block nested, p90 union/base
  1.6–3.4×, heaviest on the tail → tucking promoted to a core, triage-selected oracle
  mode. [T5, III.2 triage]
- **F3** (measured): tail instances (prob_40: max slack 13) have real temporal freedom →
  T2 scoped; queue-aware temporal construction added for wide-slack instances.
  [T2, Part V stage 2]
- **F4** (measured): legacy demand ratio triple-counted layers (prob_40: 1.57 → ≤ 0.56
  per layer) → tail re-diagnosed as geometric + temporal, not overloaded; sharper
  relaxations scheduled for the tail from the start. [III.2]
- **F5** (soundness): largest-layer-area cumulative LB is invalid (blocks peaking at
  different layers interleave) → per-layer-index cumulative formulation, sound and
  tighter, with a never-exceeds-feasible property test. [III.2]
- **F6** (soundness): one tucked cluster voids the bay-wide "no crane checks" invariant →
  dirty-cell mask with mandatory exact checks on contact. [Part II]
- **F7** (robustness): bitmap horizon must extend past max_due, grown lazily. [Part II]

Standing protocol this log encodes: every load-bearing claim gets a number before
implementation, and each blindspot pass appends here rather than editing history away.
