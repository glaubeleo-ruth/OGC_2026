# BLINDSPOT PASS 2026-07-26 — O11 falsification gate, part A (Stage-T-only headroom)

**Target:** PROPOSAL_FLUID_COMMAND.md v2.1, §Falsification gate part A. Gate set prob_21/26/27/31/38/40. Findings continue the F-log at **F14**. Tree snapshot: `02080f2`, comparison target `results/2026-07-25_solver_v0.4_lbbd_full_sweep.csv` @ `9a824ba` (**provisional** — eva's P0(b) submission_5 parity baseline still absent, so no verdict here is final).

Scripts (all scratch, throwaway):
- `/private/tmp/claude-501/-Users-jungwoosuh-Desktop-workspace-03-Projects-OGC-2026/6332b06e-d056-4262-9589-90fb10c82042/scratchpad/rex_o11_partA.py` — Stage T per bay, three-quantity bookkeeping
- `.../rex_o11_analytic.py` — entry=release per-layer load (no CP, contention-immune)
- `.../rex_o11_ladder.py` — budget / horizon / worker ladder on the mass bay
- `.../rex_o11_greedyfluid.py` — fluid earliest-fit list scheduler (5 orders)
- `.../rex_o11_counterfactual.py` — congestion-aware assignment vs master, fluid cost + exact Z2/Z3
- `.../rex_o11_endtoend.py` — controlled A/B through the real conductor + utils audit
- `.../rex_o11_table.py`, `.../out_master_300.json`, `.../ladder_w8_sound.txt`, `.../e2e.txt`

Ground truth read, not remembered: `utils.check_feasibility` stage-1 timing rules (entry ≥ release, exit − entry ≥ proc, obj1 = Σ max(0, exit − due)), `solver/bounds.py` (`_layer_demand` reused verbatim, model shape mirrored), `solver/assignment.py`, `solver/conductor.py`, `solver/model.py`, `solver/objective.py`.

## Load-bearing claims and verdicts

| # | Claim (proposal) | Verdict |
|---|---|---|
| C1 | Stage-T plan cost sits 10²–10³× below shipped w1·obj1 | **FALSIFIED** — 4.6×–30×, geomean 10.1× |
| C2 | Stage T is "seconds to OPTIMAL on train-size bays" | **FALSIFIED** — mass bay of 6/6 is FEASIBLE-with-bound-0 at 300 s, 1 thread |
| C3 | The 100× "lives in the schedule" (chronological-greedy cascade) | **FALSIFIED as stated** — it lives in the *assignment*, then in *geometry*; not in the temporal relaxation |
| C4 | Stage T is degenerate on the tail (my own prior, from F4's ≤0.56 fluid load) | **REFUTED** — peak per-layer load at entry=release is 1.30–2.13 on the mass bays; capacity genuinely binds |
| C5 | Bookkeeping is separable in practice (LB vs plan vs status) | **CONFIRMED, and load-bearing** — conflating them would have produced a fake 10.1× "exact" result |
| C6 | Kill criterion (within ~3× ⇒ mirage) | **not triggered**, but it was nearly triggered by an artifact (2.97× at 1 thread) |

## Measurements

**Stage T per bay, master assignment (`AssignmentMaster.solve`, status OPTIMAL on all six, pipeline-faithful `time_cap=8.0`).** 20 bays: 14 OPTIMAL (11 with plan 0; prob_27 bay1 LB=plan=10, prob_38 bay0 LB=plan=18, prob_40 bay0 LB=plan=5 — genuine exact non-zero certificates), 6 FEASIBLE — one per instance, always the bay holding 50–90% of the blocks.

Sound aggregate (mass bay at 8 workers/120 s, wide `bounds.py` horizon; all other bays OPTIMAL at 300 s/1 worker). w1 cancels in the ratios:

| inst | shipped obj1 | w1·obj1 | Σ LB_T | Σ plan_T | Σ plan_T @1 thread | shipped/plan | shipped/LB | 100× needs obj1 ≤ | reachable? |
|---|---|---|---|---|---|---|---|---|---|
| 21 | 362 | 4,826,546 | 39 | 78 | 122 | 4.64× | 9.3× | 3.6 | **NO** |
| 26 | 1623 | 21,639,459 | 55 | 159 | 219 | 10.21× | 29.5× | 16.2 | **NO** |
| 27 | 4480 | 59,731,840 | 210 | 368 | 409 | 12.17× | 21.3× | 44.8 | **NO** |
| 31 | 2468 | 32,905,844 | 214 | 352 | 399 | 7.01× | 11.5× | 24.7 | **NO** |
| 38 | 5100 | 67,998,300 | 396 | 584 | 760 | 8.73× | 12.9× | 51.0 | **NO** |
| 40 | 8407 | 5,607,469 | 124 | 280 | 397 | 30.02× | 67.8× | 84.1 | **NO** |

Geomean: **10.1×** to Σ plan_T (range 4.64–30.0), **19.7×** to Σ LB_T (range 9.3–67.8). Best-case *total* objective under perfect realization of the plan on the master's assignment: 3.5×–22.3× (prob_21 5.28M → 1.49M; prob_38 68.6M → 8.4M).

Soundness of the LB side: demands are `_layer_demand` (min layer-l area across orientations, floored) on one cumulative per layer index — the F5 shape; horizon `inst.horizon + Σp` cannot cut off an optimum (any schedule left-shifts into `max r + Σp` without increasing tardiness); `BestObjectiveBound` is valid on timeout. So Σ LB_T is a **certified** floor on Z1 for that assignment. All six "NO" cells are proofs, not estimates.

**Budget / horizon / worker ladder on the mass bay** (1 thread, wide horizon): plan_T identical at 2 s, 10 s, 30 s, 300 s on all six, and identical again under a 12–25× horizon reduction (H 1562→123, 3123→123); LB stayed 0 throughout. At 8 workers/120 s both sides move hard: prob_21 122→**78** with LB 0→**39**; prob_38 742→**566**, LB 0→**378**. At the pipeline's actual bounds budget (`conductor` calls `bounds.bay_lb(time_cap=min(2.0, …))`), prob_21 bay1 returns **UNKNOWN — no schedule at all**.

**Assignment counterfactual** (congestion-aware greedy vs master; fluid cost from the pure-Python list scheduler, best of 5 orders; Z2/Z3 priced with `solver.objective`):

| inst | fluid Σ T (master) | fluid Σ T (balance) | fluid total obj (master) | fluid total obj (balance) |
|---|---|---|---|---|
| 21 | 122 | **0** | 1,718,376 | 263,460 |
| 26 | 318 | **0** | 4,313,924 | 301,801 |
| 27 | 626 | 142 | 8,861,424 | 3,948,550 |
| 31 | 648 | **0** | 9,768,729 | 2,542,380 |
| 38 | 1150 | 529 | 15,369,494 | 9,179,641 |
| 40 | 566 | **0** | 404,046 | 105,047 |

Σ T = 0 is exact (a non-negative quantity with a feasible 0 is optimal — no CP needed).

**End-to-end A/B through the real conductor** (identical code path and budget, only the input assignment differs; utils-audited, all feasible, N=1):

| inst | master | balance | Δ |
|---|---|---|---|
| 21 | 5,856,717 | 4,751,739 | −18.9% |
| 26 | 59,312,549 | 35,780,914 | −39.7% |
| 27 | 60,112,787 | 47,587,459 | −20.8% |
| 31 | 70,553,876 | 32,101,641 | −54.5% |
| 38 | 89,274,313 | 80,911,181 | −9.4% |
| 40 | 5,871,445 | 4,437,879 | −24.4% |

## Findings

**F14 (OVERFIT-of-expectation / claim falsification) — the 10²–10³× headroom does not exist; it is 4.6×–30×, and 100× is provably out of reach on all six.** Under the master's own OPTIMAL assignment, the certified per-bay LBs force Z1 ≥ 39/55/210/214/396/124 block-days, while 100× would demand 3.6/16.2/44.8/24.7/51.0/84.1. The proposal's motivating arithmetic ("energetic excess ≈ 10² displaced block-days ≈ 10⁴–10⁵ objective versus 5–7M shipped") is off because it priced displaced block-days without w1: 10² block-days × w1 = 13333 is already 1.3M, not 10⁴–10⁵. Scope: conditional on this S_j — see F17, where other assignments push the fluid bound to 0 and the relaxation certifies nothing.

**F15 (−1 RISK + claim falsification) — Stage T is not tractable at the shipped thread budget on precisely the bays that carry the objective.** 300 s at `num_search_workers=1` (the standing guard rail) returns FEASIBLE with `BestObjectiveBound = 0` on the mass bay of 6/6 instances; the interval [0, plan] is fully open, so nothing is certified. Every non-zero certificate I obtained required 8 workers — a guard-rail violation and infeasible under the fork-pool topology (conductor + 3 workers, 1 thread each). Consequence for O11 as designed: Stage T runs once per (bay, assignment-version); at 4 bays × the pipeline's 2 s bounds budget it produces either nothing (prob_21: UNKNOWN) or an uncertified guess, and at a budget where it produces certificates it has eaten the whole 60 s. That is the −1 path: a planning stage whose cost is unbounded in the only regime where its output matters.

**F16 (SOUNDNESS of the "command" concept, not of an answer) — plan_cost is a first-solution artifact, and T2 as written is unimplementable.** Identical plan at 2/10/30/300 s and across a 25× horizon change means CP-SAT emits its first heuristic solution and never improves it; a five-line EDD earliest-fit list scheduler *ties it exactly* on prob_21 bay1 (122 = 122). So the "fluid command" the architecture proposes to obey is, at the shipped configuration, the output of an arbitrary first-solution heuristic that a trivial greedy matches, and it is 36% (prob_21) / 24% (prob_38) worse than the same model's own 8-worker incumbent. Stage T2 ("among T1-optimal schedules, tie-break toward realizable days") has no T1-optimal set to work in — status is never OPTIMAL on these bays. The v2 parenthetical "(or T1-cost-capped)" is the only survivable form and must become the primary definition, with the cap and its provenance recorded.

**F17 (OPPORTUNITY, the largest measured today) — the fluid tardiness is manufactured by the assignment master, not by capacity.** With θ ≡ 0 on the tail (the v0.4 sweep's empty `lb` column and `lbbd_iters=0` mean no tardiness cut ever fires), the master minimizes w2·Z2 + w3·Z3 only and pours 67/100, 113/150, 88/200 (into A=592!), 132/250 and 146/250 blocks into one bay, taking entry=release peak per-layer load to 1.30–2.13. A congestion-aware greedy assignment removes **100% of fluid tardiness on 4 of 6** gate instances and 54–58% on the other two, and end-to-end through the unmodified conductor it beats the master assignment on **6/6** by 9.4–54.5% total objective (sign test p ≈ 0.016 on direction; magnitudes are N=1 and noisy). The cheap intervention is at the assignment layer — a per-bay area-time congestion constraint replacing the `max_layer_area`-based fluid capacity (itself the F5-unsound shape, per BLINDSPOT_2026-07-25b), or making θ actually bind. That is a change in one file, versus O11's realization stack. Expected rank impact under R − nb: the six gate instances hold the bulk of the objective mass; a 9–55% cut there is worth more than any Stage-T refinement, and it is available before any realization code exists.

**F18 (kills the part-B premise as scoped) — area-feasible ≠ packable by the entire objective.** Under the balance assignment, fluid Σ T = **0** on prob_21/26/31/40, yet the shipped geometry engine (raster + tier-1 rescue, enter-ASAP) realizes obj1 = 323 / 2661 / 2217 / 6496 tardy days. Under O11's own bookkeeping (`realized − LB` is the only certified gap) that is a realization gap of 2217 days on prob_31 against a commanded and certified 0. The tardiness on this class is therefore *geometric*, not temporal: the fluid polytope has already given everything it can and the remainder is shape tiling, crane paths, and conservative footprints. Caveat, stated plainly: my e2e arms do **not** follow a fluid command (they use enter-ASAP within the zero window), so this bounds the *available* gap, it does not measure cohort-realization efficiency — that is still part B. But part B's central premise ("exceptions are local and small") now has to explain a gap equal to 100% of the objective, not a correction to it.

## Caveats on my own instrument

The machine was **not** quiet — eva wrote `results/2026-07-26_submission_lineage.md` during the run. Only OPTIMAL objective values are contention-immune; every FEASIBLE plan and every bound is effort-limited and therefore contention-sensitive. Two mitigations: the mass-bay plans reproduced identically across six independent configurations (2/10/30/300 s × wide/tight horizon), so those values are real; and contention biases plan_cost *upward*, i.e. toward the kill verdict — the 2.97× reading at 1 thread that nearly triggered the kill was an artifact that better search erased (4.64×). My e2e arms are also both far worse than the stamped panel (prob_26 59.3M vs 22.2M) because `conductor.run` alone lacks api.solve's seed pass, incumbent store and repair-first path; the arm-vs-arm comparison is valid, the absolute levels are not comparable to shipped, and F17 needs re-measurement inside `api.solve` (tom would have to expose an assignment arm; eva then N≥3). Verdict remains **provisional** until eva's P0(b) submission_5 baseline lands.

## What would beat this?

A team that treats the bay partition as the primary decision and the schedule as its consequence. Every number above says the mass instances are decided at assignment time: the same geometry engine, same budget, same everything, delivers 9–55% better objective purely from a different partition, and the fluid relaxation's own certificate collapses from 396 forced tardy days to 0 when the partition changes. A rival who writes an area-time-congestion-aware assignment model (per-bay per-layer Σ a_i·p_i ≤ A_j·H with congestion windows, or lazily generated θ cuts that actually bind) gets our 10× before we finish building Stage G. Beyond that, the winner on this class is whoever closes the geometric gap F18 exposes — 2217 realized days against a certified 0 is a packing problem, and it will be beaten by better shape reasoning (exact-layer tucking, strip/energetic per-layer relaxations that see width profiles, not areas), not by better temporal reasoning. Our own III.2 tightening ladder is the right instrument and it is still unbuilt.

## What makes this −1 on a hidden instance?

Stage T itself. On the mass bay of every gate instance the relaxation is a 67–146-task, 4-resource cumulative over a 1562–3123-day horizon that 300 s of single-threaded CP-SAT cannot close, and at the pipeline's real 2 s allowance it returned **UNKNOWN — no schedule** — on prob_21. Wire that in front of realization and the hidden-instance failure mode is a planning stage that consumes the budget and hands back either nothing or an uncertified guess, with the geometry stage then starting from zero with no time left; a rushed re-pack measurably loses to the audited incumbent (that is why `abort_on_expire` exists) and an overrun is −1 outright. The model build itself is a second hazard: horizon scales as `inst.horizon + Σp`, so a hidden instance with 400 blocks in one bay builds a ~5000-day, 400-interval model whose construction cost is unbudgeted and whose memory is unmeasured. Mandatory containment before any O11 build: Stage T behind a hard sub-budget with a cost-capped fallback (the EDD list scheduler that already ties it), a `num_search_workers` decision recorded against the 4-core rule, the horizon tightened for the *plan* while the wide horizon is kept for the *bound* (they are different models — a restriction's bound is not a lower bound, which is a trap I nearly walked into myself and flag here), and the seed-fallback path untouched.

---

**VERDICT: HEADROOM CERTIFIED — but re-scoped, and the proposal's magnitude claim is falsified.** Σ plan_T sits **4.64×–30.0× (geomean 10.1×)** below shipped w1·obj1, with a certified ceiling of **9.3×–67.8× (geomean 19.7×)**; the ~3× kill criterion is **not** triggered (nearest miss 4.64× on prob_21, and 2.97× at 1 thread was an artifact). The expected 10²–10³× is **FALSIFIED with certificates on all six instances**. Part B must not proceed as written: the measured lever is F17 (congestion-aware assignment: −9.4% to −54.5% end-to-end, 6/6, on the unmodified engine), and F18 shows part B's local-repair premise now owes an explanation for a realization gap equal to the whole objective. Recommended order: F17 first (one file, biggest measured win), then the III.2 geometric relaxation ladder, then Stage T only as a cost-capped heuristic behind a hard sub-budget — never as a certificate producer at 1 thread. Verdict stays **provisional** pending eva's P0(b) submission_5 baseline.

---

*Persisted verbatim by the architect session on rex's behalf (rex's harness could not write repo files this run), 2026-07-27.*
