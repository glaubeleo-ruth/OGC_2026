# prob_38 — why blocks concentrate into a single bay despite geometric freedom elsewhere

**Stamp:** 2026-07-27 (KST) · git HEAD `962704c` · tree: `baseline/sub/` workspace, sub/ clean ·
macOS 8-core, local-only (structural analysis — values are contention-immune: exact data
reads, one OPTIMAL CP-SAT solve, pure-arithmetic assignments; no timing claims).
**Analyst:** architect session (direct), scripts `an38.py` / `an38b.py` in session job tmp.
**Ground truth read, not remembered:** `utils.check_feasibility` source (obj2 definition),
`solver/assignment.py` (`AssignmentMaster.solve`, `_greedy`), `solver/congestion.py`.

## Instance facts (from prob_38.json)

| | bay 0 | bay 1 | bay 2 |
|---|---|---|---|
| area (W×H) | 68×16 = **1088** | 104×24 = **2496** | 109×27 = **2943** |
| blocks whose TOP preference is this bay | 36 | **142 (57%)** | 72 |
| workload share at pure top-preference | 0.114 | **0.621** | 0.265 |

Weights: **w1 = 13,333** (tardiness/day) · **w2 = 2** (imbalance) · **w3 = 300** (preference).
Preference margin (top vs 2nd bay, per block): median **52**, mean 52, range 0–100.

## Measured assignments (n = 250)

| strategy | counts (bay 0/1/2) | workload | z2 (proposal) | w2·z2 | z3 (proposal) | w3·z3 |
|---|---|---|---|---|---|---|
| `AssignmentMaster` (status **OPTIMAL**, Deadline(60), cap 8 s) | 38 / **132** / 80 | 3382 / 15840 / 8974 | 7172 | 14,344 | 74 | 22,200 |
| `_greedy` (pure top-preference) | 36 / **142** / 72 | 3215 / 17515 / 7466 | 9747 | 19,494 | 0 | 0 |
| `congestion_assignment` (F17 arm) | 61 / 88 / 101 | 6521 / 10383 / 11292 | 4692 | 9,384 | 7057 | **2,117,100** |

(z2/z3 are proposal-level via `solver.objective` on the assignment; realized values differ
after repair. The counts are the load-bearing result.)

## The causal chain

**1. The data concentrates desire.** 57% of blocks top-prefer bay 1 — the *middle* bay
(38% of total area) — and the preferences are strong (median margin 52 points).

**2. The objective prices deviation savagely and balance at almost nothing.** Moving one
median block to its 2nd-choice bay costs w3·52 ≈ **15,600**. The entire balance term is
w2·obj2 with w2 = 2, and obj2 (per `utils`) is the **floored MAX over bay pairs** of
normalized workload imbalance, `u_j = avg_bay_area / area_j` — a max, not a sum, so
marginal concentration beyond the extreme pair is nearly free. The whole realized balance
budget (~9–19K) is worth roughly **one block's** preference concession. Under this price
system, concentration is the optimum, and the master proves it (OPTIMAL).

**3. The capacity restraint is fluid, not geometric.** The master's only physical
constraint is the ρ=1 area-time cap (Σ block-area·days ≤ A_j·H). It trimmed greedy's 142
to the master's 132 — exactly the area-day overflow, and no more. But area-time-feasible ≠
packable: under the greedy assignment prob_38's peak per-layer daily fill reaches **2.59×
capacity** (BLINDSPOT_PASS_2026-07-27b, F30 measurement) because release/due windows pile
into the same weeks while the cap averages over the whole horizon. The geometry engine
downstream physically cannot place the cohort on time; the queue cascades; obj1 = ~5,374
tardy days.

**4. The one term that would forbid this is structurally mute.** Tardiness carries
w1 = 13,333/block-day — ~95% of prob_38's shipped objective. The exchange rate is ~1.2:1
(one tardy day 13,333 vs one median preference move 15,600), so concentration that
manufactures thousands of tardy days to save preference points is catastrophically wrong
under the full objective. The master hears none of it: tardiness enters only through θ
cuts from the LBBD loop, and the loop completes **zero iterations on this instance class
at every timelimit measured** (74/74 rows, F17 A/B + D1/D3). θ ≡ 0 at decision time.

**5. Geometric freedom elsewhere cannot rescue it.** Bays 0/2 sit at 11%/26% workload —
but the pipeline decides the partition first, on Z2/Z3 + fluid area alone; geometry only
sees the per-bay subsets it is handed. Downstream re-partitioning exists only in repair —
a local polish on an already-cascaded schedule (O11 gate: repair cannot recover this
class).

**6. Naive spreading also fails (measured).** The congestion arm's balanced answer
(61/88/101) clears the areal overload but pays w3·7057 ≈ **2.1M** in preference penalty —
and loses to baseline on this exact instance 5/5 on objective at t=60
(`2026-07-27_f17_arm_ab`, scoring pass `20260727b-1`), because the Z1 refund does not
cover the layer bill; per F18/F32 part of the congestion is shape-tiling, not area, so
spreading area cannot buy the full refund.

## What this does and does not establish

Establishes: the concentration is the *provably optimal* behaviour of the current master
objective (Z2/Z3 + fluid cap, θ inert) on prob_38's data; the mechanism is priced in the
instance weights and the obj2 max-form; the failure is upstream of geometry.
Does NOT establish: that any specific remedy wins — the measured candidates are task 1.2
(congestion/tardiness signal inside the master: mandatory-window charging, θ binding at
iteration 0) and task 1.6 (geometry ladder for the non-areal share). The F17 arm
(wholesale replacement) is measured NOT to be the remedy on this instance (◆0.4).

Cross-references: BLINDSPOT_PASS_2026-07-26_o11_gate_partA.md (F17/F18),
BLINDSPOT_PASS_2026-07-27b_f17_arm.md (F29/F30/F32 + scoring),
results/2026-07-27_f17_arm_ab.md, results/2026-07-28_d1_prob38_t300.md,
results/2026-07-27_d3_t300_reversal.md.
