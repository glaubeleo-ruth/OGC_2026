# BLINDSPOT PASS 2026-07-27e — Task 1.2 merge-hypothesis gate (mandatory-window charging in the master)

**Analyst:** rex. **Stamp:** 2026-07-28 KST. **Tree measured:** `ogc2026/baseline/sub/` @ HEAD `d3000a4933150bab7ee0f91f4013bcf1285833f5`.
Dirty at snapshot: `ogc2026/REMAINING_TASKS.md`, `ogc2026/alg_tester/settings.json`. Untracked: `_to_delete/`, `ogc2026-grader-explainer.pdf`, `ogc2026/NIGHT_TRACK_B_20260728.md`, `ogc2026/baseline/submission_20260727-2116_962704c{,.zip}`, `ogc2026_rig.bundle`. None on any measured path.
**Path declaration:** `ogc2026/baseline/solver/` and `ogc2026/baseline/alns/` contain only `__pycache__` and are STALE. Every import resolves to `ogc2026/baseline/sub/`.
**Instrument:** macOS 8-core, machine free. Solver code untouched — Model B lives entirely in `scratch_rex/mergegate/`.
**Numbering discipline:** pass-local IDs `20260728e-N`. No F-numbers self-assigned.

---

## 0. Confounds controlled before any verdict

**Parity control 1 (transcription of the master model).** Model B with `windows=False` must be Model A. Measured at 30 s on prob_1/2/8/20/38: identical status (OPTIMAL 5/5), **bit-identical assignment**, identical layer bill (1 499 / 3 690 / 11 252 / 52 076 / 36 544). The model transcription is not a confound.

**Parity control 2 (transcription of the LB model).** `bounds.bay_lb` hard-codes 1 worker, so `_cumulative_lb` was transcribed with a workers knob. At 1 worker / 15 s on prob_38 the copy returns `18 [18,0,0]` — identical to `bounds.bay_lb`. It reproduces **part A's Σ LB_T exactly on both rows run** (prob_38 396, prob_27 210) at part A's setting.

**θ is inert, so omitting it is exact.** At iteration 0 there are no tardiness cuts, so `theta_cap = 0` and A's θ variables have domain `[0,0]`. A's iteration-0 objective *is* `w2·z2 + w3·z3`. B is comparable term-for-term.

**Determinism.** CP-SAT at 1 worker on a fixed model is deterministic; only cap-truncated rows can vary. N=3 repeats on prob_27/31/36/40/38: objective, bill and peak fill **bit-identical across all reps on every row**. Wall times are N=3 means with ranges.

---

## 1. The candidate as built

- Objective family `min w2·z2 + w3·z3`, θ omitted (inert at decision time — the disease).
- `M_i = [max(r_i, d_i − p_i), r_i + p_i)`, non-empty iff `slack_i < p_i` (`bounds.congestion_profile`'s certified definition, F32's counter-criterion).
- Buckets = intervals between **distinct window-boundary events**, so each bucket is wholly inside or wholly outside every `M_i`.
- Per bay `j`, layer `l`, bucket `b`: `Σ_{i: b ⊆ M_i} a_i^l · y_ij ≤ A_j + overflow_jlb`, `a_i^l = bounds._layer_demand` (min over orientations, floored).
- **Presolve reduction (sound):** triples whose max possible load ≤ `A_j` are dropped (96–556 per instance).
- **Pricing formula (gate parameter):** `penalty = Σ_{j,l,b} round( w1 · 10⁶ · len(b) / Ā ) · overflow_jlb`, `Ā = mean over blocks of max_l a_i^l`, micro-unit scaling matching `assignment._U_SCALE`. Intent: one average-block-area-day of excess ≈ w1. **See 20260728e-4 — realised charge is 1.62–2.32× that.**
- Variant **B2**: same constraints, hard (`≤ A_j`), no overflow.

**The constraint's blind spot, measured:** `M_i` is empty iff `slack_i ≥ p_i`. **Empty-window fraction = 0.0 % on all 11 gate instances.** A data property, not a guarantee (HYPOTHESIS: hidden wide-slack blocks are invisible to B, degrading B → A on them).

---

## 2. Pre-registered predictions, scored publicly

Registered in `scratch_rex/mergegate/PREREG.md` **before any `windows=True` solve**.

| # | Prediction | Outcome | Verdict |
|---|---|---|---|
| P1 | prob_1/2/8 OPTIMAL, wall ≤1.3× A | OPTIMAL 3/3, wall 0.00/0.02/0.00 vs A 0.01/0.02/0.01 | **CONFIRMED** |
| P2 | ≥5/8 tail rows OPTIMAL @8 s; at-risk order 40, 31, 36, 38 | **7/8** @8 s and @4 s, 6/8 @2 s; only prob_38 fails | **CONFIRMED, at-risk ordering WRONG** |
| P3 | peak fill down on every A>1.0 row; p38 ≤1.15, p31 ≤1.25, p27 ≥1.20 | 7/7 down; p38 **1.227**, p31 1.088, p27 1.396 | **CONFIRMED direction; p38 point MISSED** |
| P4 | p38 bill ∈ [3e5, 3e6], "within ~2× of the arm" → K3 fires | 294 154 / 303 268 / 350 700 — **7.0× BELOW the arm** | **K3 verdict REFUTED (my error)** |
| P4b | p20 bill rises above A's 52 076 | identical, 52 076 | **REFUTED** |
| P5 | p38 floor 100–350 (10–75 % cut), not zero | **92** (−76.8 %), not zero | **direction CONFIRMED; under-predicted B** |
| P6 | p20: <10 % of blocks moved | **0.0 %** moved | **CONFIRMED** |
| P7 | B2 INFEASIBLE on all 7 rows with A peak >1.0 | **2/7** (prob_27, prob_38) | **REFUTED** |

Two of seven predictions refuted in B's favour. Recorded as such.

---

## 3. Axis 1 — solve time and status, 1 thread, at caps

Caps 2/4/8/30 s. A = `AssignmentMaster._solve_cpsat(cap)` (includes Python build); B's solve column is CP-SAT wall, build timed separately (§3b).

| pid | A status | A wall | B @2 s | B @4 s | B @8 s | B @30 s | B wall (N=3 mean, range) |
|---|---|---|---|---|---|---|---|
| **1** | OPTIMAL | 0.01–0.05 | OPT | OPT | OPT | OPT | 0.00 |
| **2** | OPTIMAL | 0.02–0.03 | OPT | OPT | OPT | OPT | 0.02 |
| **8** | OPTIMAL | 0.01 | OPT | OPT | OPT | OPT | 0.00 |
| 20 | OPTIMAL | 0.09 | OPT | OPT | OPT | OPT | 0.14 |
| 21 | OPTIMAL | 0.01 | OPT | OPT | OPT | OPT | 0.10 |
| 26 | OPTIMAL | 0.02 | OPT | OPT | OPT | OPT | 0.09 |
| 27 | OPTIMAL | 0.01–0.17 | OPT | OPT | OPT | OPT | 1.71 (1.46–2.07) |
| 31 | OPTIMAL | 0.09–0.15 | OPT | OPT | OPT | OPT | 2.64 (2.57–2.74) |
| 36 | OPTIMAL | 0.11–0.20 | OPT | OPT | OPT | OPT | 0.66 (0.66–0.67) |
| **38** | OPTIMAL | 0.06–0.10 | **FEAS 9.69 %** | **FEAS 9.68 %** | **FEAS 9.39 %** | **FEAS 4.63 %** | pinned at cap |
| 40 | OPTIMAL | 0.12–0.19 | **FEAS 0.56 %** | OPT | OPT | OPT | 3.40 (3.37–3.58) |

**Certificate tier: B is structurally identical to A** — all 196/291/458 candidate window constraints are trivially satisfied and dropped, so B builds the same variables and constraints as A. Logic result, contention-immune.

**OPTIMAL-rate at the pipeline's real caps** (`api.py:155` first solve `min(8.0, 0.15·remaining)`; `lbbd.py:157` loop `min(4.0, 0.15·remaining)`): A 11/11 at both. B **10/11** at both.

**3b. Build time (instrument correction).** B's extra Python build measured separately: **+0.001 s (p1) to +0.119 s (p40)**, mean of 3. Negligible on this set (see 20260728e-3 for the extrapolated risk).

---

## 4. Axis 3 — anytime quality

On the ten rows where B reaches OPTIMAL, the answer at 2 s equals the answer at 30 s (bit-identical bill and peak fill): step function, not a ramp. On prob_38, B's first solution at 2 s already carries bill 294 154 and peak fill 1.270; 30 s more improves the CP-SAT objective by only 5 % (peak fill 1.270 → 1.227). **B's first feasible solution is usable — no F16 artifact.** One wobble: the layer bill is not monotone in the cap on prob_38 (294 154 @2/4 s, 350 700 @8 s, 303 268 @30 s) because B optimises bill + overflow, not bill.

---

## 5. Axis 4 — value proxies

**(a) Peak mandatory-window per-layer fill (`bounds.congestion_profile`), A → B.** Caveat: near-tautological — B constrains exactly this quantity; a did-the-constraint-work check, not independent evidence.

| pid | 1 | 2 | 8 | 20 | 21 | 26 | 27 | 31 | 36 | 38 | 40 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | .395 | .424 | .410 | .867 | 1.420 | 1.348 | 1.665 | 1.775 | 1.711 | 1.774 | 1.328 |
| B | .395 | .424 | .410 | .867 | **1.002** | **0.999** | **1.396** | **1.088** | **1.007** | **1.227** | **1.005** |

Every over-capacity row improves; every already-clear row untouched. Blocks moved vs A: 0.0 % on 1/2/8/20; 4.7–13.2 % elsewhere.

**(b) Layer bill `w2z2 + w3z3`.**

| pid | A | B | B/A | F17 arm (p38 only) |
|---|---|---|---|---|
| 1/2/8/20 | 1 499 / 3 690 / 11 252 / 52 076 | identical | 1.00× | — |
| 21 | 91 750 | 114 760 | 1.25× | — |
| 26 | 74 030 | 104 413 | 1.41× | — |
| 27 | 514 966 | 770 602 | 1.50× | — |
| 31 | 1 128 945 | 1 331 547 | 1.18× | — |
| 36 | 31 638 | 40 972 | 1.29× | — |
| **38** | 36 544 | **294 154–350 700** | 8.0–9.6× | **2 117 100** |
| 40 | 26 524 | 31 818 | 1.20× | — |

B's prob_38 bill is **6.0–7.2× below the arm's**, achieved by moving 10–13 % of blocks against the arm's wholesale re-partition.

**(c) Certified tardiness floor `Σ_j bounds.bay_lb` — the decisive axis.**

*Task premise corrected:* at 1 worker / 15 s floors are near-zero everywhere (A: p27 10, p38 18, p40 5, rest 0). Part A's 396 was at **8 workers / 120 s on the mass bay**. Re-run at part A's power, interleaved A/B:

| pid | A floor | A per bay (lb/status/blocks) | B floor | B per bay | Δ |
|---|---|---|---|---|---|
| **38** | **396** | 18/OPT/38 · **378/FEAS/132** · 0/OPT/80 | **92** | 41/OPT/38 · 27/FEAS/113 · 24/FEAS/99 | **−76.8 %** |
| **27** | **210** | 200/FEAS/75 · 10/OPT/75 | **69** | 45/FEAS/66 · 24/FEAS/84 | **−67.1 %** |

Both A values reproduce part A exactly — instrument validated.

**Caveat limiting the claim:** 65 of B's 92 and all 69 of prob_27's floor come from FEASIBLE-truncated bays — valid lower bounds, not proven tight. B's prob_38 bay 0 is certified **worse** than A's (41 vs 18, both OPTIMAL). So *"B's certified floor is materially lower"* = **measured true**; *"B's true minimum tardiness is lower"* = **NOT ESTABLISHED**. **Missing measurement:** an upper bound on B's partition (part A's fluid list-scheduler `plan_T`) — the single cheapest experiment converting suggestive → proved. prob_31 killed mid-run for budget.

---

## 6. Axis 5 — prob_20, the arm's +57.8 % catastrophe class

**B is bit-identical to A on prob_20** (0.0 % of 300 blocks moved, bill 52 076 both, peak fill 0.867 both) despite 266 non-trivial overflow constraints. Same on prob_1/2/8. **B keeps near-greedy assignments when windows do not bind** — precisely the property the F17 arm lacked.

---

## 7. Variant B2 (hard caps)

| | 1 | 2 | 8 | 20 | 21 | 26 | **27** | 31 | 36 | **38** | 40 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| status @8 s | OPT | OPT | OPT | OPT | OPT | OPT | **INFEAS** | OPT | OPT | **INFEAS** | OPT |
| wall | .00 | .02 | .00 | .13 | .08 | .08 | 0.00 | 3.62 | .27 | 0.23 | 1.21 |
| bill | =A | =A | =A | =A | 115 720 | 104 413 | — | 1 369 689 | 41 267 | — | 31 951 |

Infeasibility 2/11. On the 5 feasible over-capacity rows B2's bill is within 0.1–2.9 % of soft-B's — the soft price at ×1 already drives to the hard-constraint answer.

---

## 8. Kill criteria — verdicts

**K1 — DOES NOT FIRE.** Certificate tier: B OPTIMAL 3/3 at every cap, ≈1.0× A's wall, structurally identical model. *Caveat carried:* tail OPTIMAL 8/8 → 7/8, and B's prob_40 wall 3.40 s vs the loop's 4.0 s cap, on an 8-core box — the F33 exposure surface; unmeasured on ≤4-core hardware.

**K2 — DOES NOT FIRE.** prob_38 floor 396 → 92 (−76.8 %), prob_27 210 → 69 (−67.1 %), instrument validated. Windows move the schedule floor on the concentration class. Subject to §5(c)'s upper-bound caveat.

**K3 — DOES NOT FIRE.** prob_38 bill 6.0–7.2× below the arm's; B bit-identical to A wherever windows don't bind (incl. the arm's catastrophe row); 4.7–13.2 % of blocks moved where they do.

## VERDICT: **GATE PASSES.**

Margins: certificate tier unchanged (structurally identical, 0.00–0.02 s); tail OPTIMAL-rate 10/11 at both real caps; peak fill cleared to ≤1.007 on 4 of 7 over-capacity rows; certified floor −76.8 % / −67.1 % on the concentration class; layer bill 7× inside the arm's. **Implementation is a ◆ decision — to be taken together with 20260728e-1 and -2, which are conditions on the implementation, not the gate.**

---

## 9. Findings

### 20260728e-1 — SOUNDNESS (latent). `lbbd._master_bound` silently stops being a lower bound under Model B.
`_master_bound` (lbbd.py:51-60) returns the master argmin's layer cost; both stop rules consume it (`assignment_lb_reached` L124, `master_bound_closed` L182). Valid only if the argmin minimises exactly `w2·z2 + w3·z3`. Under B the argmin minimises bill + overflow, so the value is an **upper** estimate of the layer minimum. Measured inflation vs A's true optimum: p21 +25.1 %, p26 +41.0 %, p27 +49.6 %, p31 +17.9 %, p36 +29.5 %, **p38 +729.9 %**, p40 +20.0 %; 0 % on 1/2/8/20. Consequence: `assignment_lb_reached` can fire with a strictly better assignment unexplored — a claimed certificate that is not held. **Not −1** (audited incumbent + deadline unaffected) — P1 regression. Missing measurement: full-pipeline run where the incumbent lands between A's true LB and B's reported bound. **The F19/F24 shape.** Cheapest sound repairs for discussion: keep A's model alive purely for the bound, or a layer-only re-solve; CP-SAT's `BestObjectiveBound` on B does not decompose.

### 20260728e-2 — P1 REGRESSION (measured, N=3). Model B destroys prob_38's certificate.
A OPTIMAL in 0.10 s; B FEASIBLE at 9.68 % gap @4 s, 9.39 % @8 s, 4.63 % @30 s. `_master_bound` returns None unless OPTIMAL, so **both** stop rules are unavailable on that instance under B. Budget + certificate loss on exactly the targeted class; deterministic across reps.

### 20260728e-3 — −1 CANDIDATE, **HYPOTHESIS** (mechanism measured; magnitude extrapolated).
Nothing bounds bucket count except `2n`; constraints = O(buckets × bays × layers); build ≈ 0.2 ms/constraint (measured). Extrapolated: 400 blocks all-distinct boundaries × 5 bays × 4 layers ≈ 16 000 constraints ≈ **3.3 s pure Python build**, OUTSIDE `sub_budget` (which governs CP-SAT wall only). Construction attempt FAILED (perturbing prob_38 left buckets at 69–73). Until a synthetic ≥400-block all-distinct instance times `build()` alone, hypothesis not finding. **Implementation condition: build inside deadline accounting, or hard-cap buckets (coarsening is sound — merging only weakens the charge).**

### 20260728e-4 — GATE-PARAMETER MIS-CALIBRATION (measured; non-load-bearing here).
Stated calibration uses `Ā = mean peak layer demand` but the charge is levied per positive layer (1.83–3.01 per block): realised price 1.62–2.32× the stated one. Measured to not matter: a 16× price sweep moves p38's bill 1.78× and fill 1.270→1.232; hard caps land within 0.1–2.9 % of soft. Not a knife edge — but the docstring must state the realised behaviour.

### 20260728e-5 — F28 INTERACTION (measured; B2 only).
B2 INFEASIBLE on p27 (0.00 s) and p38 (0.23 s). In the shipped path INFEASIBLE triggers `assignment.py:215-226` → `self.rho = float("inf")` on the live master — F28 poisoning for the rest of the loop. **B2 must not ship in this shape** (18 % of train trips it). Soft-B never goes INFEASIBLE; `rho` stayed 1.0 on all rows. *Corollary opportunity:* B2's INFEASIBLE is a 0.00–0.23 s certificate that zero tardiness is impossible — cheaper triage than `pooled_lb`.

---

## 10. What would beat this? — HYPOTHESIS unless marked MEASURED

1. **The remaining prob_38 gap is not areal (MEASURED, inherited).** B clears peak fill to 1.227 and B2 proves no assignment clears it to 1.0. A's realised obj1 ~5 100 days vs certified floor 396; B moves the floor to 92 and cannot touch the ~4 700-day remainder. HYPOTHESIS: that remainder is F18/F32-Case-A shape-tiling, invisible to any per-layer area charge. Task 1.6 is the lever; B is not.
2. HYPOTHESIS: binding θ at iteration 0 (certified pooled-lb-style tardiness inside the master) gets the whole w1 signal; B is a surrogate.
3. HYPOTHESIS: hidden instances with `slack ≥ proc` blocks are invisible to B (0.0 % of train).
4. MEASURED, cheap for a rival: the formulation is a two-hour build, zero cost on the certificate tier. No moat.
5. HYPOTHESIS: B counts area but not when-in-window or ordering — F32's slack-ordering half untested (D6).

## 11. What makes this −1 on a hidden instance?

1. **Only credible path: 20260728e-3**, and construction failed. If implemented: build inside deadline accounting or bucket hard-cap.
2. Not −1 but precise: B never INFEASIBLE, never touched rho, worst wall 3.40 s vs 4.0 s cap on an 8-core box — **unknown on ≤4-core target**; the gauntlet box should re-run §3 before any ◆ implement.
3. B2 is −1-adjacent via F28 (2/11 trip rate). Do not ship B2.

## 12. Deferred register

| id | measurement | cost | settles |
|---|---|---|---|
| D1 | fluid `plan_T` on A's and B's p38/p27 partitions | ~5 min | K2 from "certified floor lower" → "true optimum lower" |
| D2 | prob_31 floors at 8 w/120 s | ~10 min | third K2 row |
| D3 | synthetic ≥400-block all-distinct instance; time `build()` | ~15 min | 20260728e-3 hypothesis → finding or dead |
| D4 | full pipeline under B, incumbent between A's LB and B's bound | ~30 min | 20260728e-1 latent → confirmed |
| D5 | §3 re-run on the Linux box at ≤4 cores | ~20 min | prob_40's 3.40/4.0 s margin on target hardware |
| D6 | B + slack-ascending construction order | ~30 min | whether ordering adds anything over charging |

**Files:** prototype + tooling `scratch_rex/mergegate/{mg_common,mg_stats,mg_a_base,mg_b_sweep,mg_b2,mg_price,mg_floors,mg_floors2,mg_build,mg_reps}.py`; pre-registration `PREREG.md`; journal `JOURNAL.md`; raw `A_base.txt`, `B_sweep.csv`, `floors.txt`, `floors2_live.txt`. Ground truth read, never modified: `sub/solver/{assignment,bounds,model,objective,lbbd,api,budget,rasters}.py`.

---

## D1 (deferred, run 2026-07-28) — boxing the fluid optimum: does K2 upgrade?

**Instrument note (the ask conflated two of part A's instruments).** Part A's `Σ plan_T` is **not** the list scheduler: it is the `ObjectiveValue` (incumbent) of the *same* per-bay per-layer cumulative CP-SAT whose `BestObjectiveBound` gives `LB_T` — p38's 584 = 566 (mass bay @8w/120s) + 18 + 0. The "fluid Σ T, best of 5 orders" list scheduler is a separate, weaker instrument in part A's assignment-counterfactual table (p38 master = 1150). Both are reported. Floors reused from §5(c), not re-run. Setting held constant A-vs-B: 8 workers / 120 s (60 s for the one prob_27 top-up).

**Instrument validation: the list scheduler reproduces part A's `fluid Σ T (master)` column EXACTLY, 3/3** — p38 1150, p27 626, p31 648.

### Per (instance, partition)

| instance | partition | Σ LB_T (floor) | plan_T (cumulative UB) | **box [LB, plan]** | list-sched UB |
|---|---|---|---|---|---|
| **prob_38** | **A** | **396** (18/378/0) | **635** | **[396, 635]** | 1150 |
| **prob_38** | **B** | 82 (36/26/20) | **180** (44/79/57) | **[82, 180]** | 348 |
| **prob_27** | **A** | **210** (200/10) | **383** | **[210, 383]** | 626 |
| **prob_27** | **B** | 63 (39/24) | **154** (126/28) | **[63, 154]** | 254 |
| prob_31 | A | not measured @8w | — | — | 648 |
| prob_31 | B | not measured @8w | — | — | 159 |

### Verdicts

- **prob_38 — D1 CONFIRMS K2 (proved).** Boxes **disjoint**: B's true fluid optimum ≤ **180**, A's ≥ **396** — the optimum itself is lower by ≥ 216 block-days (≥ 2.2×). The weak list instrument agrees independently (B 348 < A's LB 396), so the conclusion does not rest on the CP-SAT UB.
- **prob_27 — D1 CONFIRMS K2 (proved).** Disjoint: B ≤ **154** < A ≥ **210**. The list instrument alone would NOT have settled this row (overlap [210, 254]); the cumulative plan_T was required.
- **prob_31 — INCONCLUSIVE, as pre-registered.** A's 8-worker floor never measured. List UBs (648 → 159, −75.5 %) suggestive only. HYPOTHESIS, not a result.

### Effect on the pass

**§5(c)'s caveat is discharged on both rows it covered:** "B's true minimum tardiness is lower" is now **established on prob_38 and prob_27 by disjoint [LB, plan] boxes; still open on prob_31.** K2's no-fire verdict upgrades from suggestive to proved on the concentration class. **D2 (prob_31 floors @8w) is the only remaining gap** in the K2 chain.

### Pre-registration scored (registered before any B-partition UB was seen)

PD1-1 HIT (B p38 plan 180, inside the 100–300 band) · PD1-2 CONFIRMED (disjoint) · PD1-3 CONFIRMED (154 < 210) · PD1-4 CONFIRMED 3/3 · PD1-5 CONFIRMED (p31 inconclusive, as flagged). **5/5.**

### Two caveats that travel with these numbers

1. **B's prob_38 partition is not unique.** The 30 s diagnostic solve is cap-truncated and not deterministic: two runs gave 38/113/99 (floor 92) and 42/114/94 (floor 82, plan 180). Both boxes sit far below A's, so the verdict is robust — but no single prob_38 B partition should be quoted as "the" answer. At the pipeline's **real 4 s/8 s caps** B's prob_38 answer WAS bit-deterministic across 3 reps; shipped behaviour is stable, the 30 s diagnostic cap is what wobbles.
2. **A's prob_38 plan_T reads 635 here vs part A's 584.** Both valid UBs from truncated non-deterministic 8-worker runs. No verdict depends on it (all verdicts use A's LB, which reproduced part A exactly).

### Unchanged by D1

This bounds the **fluid per-layer-area relaxation** only. Against prob_38's realised obj1 ≈ 5 100 tardy days, A's fluid optimum is ≤ 635 and B's ≤ 180 — **D1 confirms B wins the assignment-layer argument while leaving ~4 500 realised tardy days unexplained by area at all.** That residual remains the F18/F32-Case-A shape-tiling share (§10.1, HYPOTHESIS); no window charge can see it. Task 1.6, not 1.2, is the lever there.

**D1 files:** `scratch_rex/mergegate/mg_d1.py`, `mg_d1b.py`, `d1_live.txt`, `JOURNAL.md`, `PREREG.md` (D1 section).

---

*Persisted verbatim by the architect session on rex's behalf, 2026-07-28 KST. Task 1.2 gate: PASSES; implementation is ◆-gated on findings -1/-2/-3 as conditions.*
