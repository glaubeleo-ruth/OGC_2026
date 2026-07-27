# Prediction scoring — F17 arm A/B (REMAINING_TASKS 0.3; addendum to BLINDSPOT_PASS_2026-07-27b)

**Inputs:** `results/2026-07-27_f17_arm_ab.md`, `.../2026-07-27_f17_arm_ab.csv`, `.../2026-07-27_f17_arm_ab_audit.csv`. No solver imports (tree mid-reorg); arithmetic on eva's CSV plus the saved `p1_rows.json`. Scoring script: scratchpad `rex_f25/p8_score.py`.

**Instrument caveat first.** eva's stamp is local-only, not gauntlet-valid, swap 2.8–3.9 GB, load 1.9–4.4. Everything below is read **ordinally**. Two things in her table are contention-immune and are leaned on: the arms are **bit-deterministic** on most rows (prob_21 congestion 396 ×5; prob_31 both arms identical across all reps at both timelimits; prob_27 congestion 3150 ×4), and the *decompositions* (obj2/obj3 → layer cost) are pure functions of the shipped assignment, not of how much CPU it got.

**Numbering discipline note.** The 2026-07-27b pass used F25–F33 because the launching brief said "next free is F25". Treat **F25–F33 as proposed, not canonical**, and confirm at fold time (REMAINING_TASKS 0.11). The four new findings here carry pass-local IDs only.

---

## 0. The one correction to eva's report

### `20260727b-1` — prob_38 @ t=60 is a **real regression, 5/5**, not "inconclusive within noise"

eva scored the overlap on **obj1 ranges** (baseline [5144, 5374] contains congestion [5271, 5280] → overlap → inconclusive). The leaderboard scores `objective`, and there the ranges are **disjoint**:

```
baseline   objectives: 69,154,730  69,154,730  69,910,758  70,229,382  72,098,620
congestion objectives: 72,325,075  72,445,072  72,445,072  72,445,072  72,445,072
baseline WORST 72,098,620  <  congestion BEST 72,325,075     overlap: False
congestion worse in 5/5 pairwise reps
```

The separation comes from a channel obj1 cannot see: **obj3 = 6809 (congestion) vs 1724 (baseline)** at w3 = 300, a deterministic **+1.53 M** preference bill. Decomposition of the +2.53 M total delta: **40 % Z1, 60 % layer.** prob_38 is the one gate row where the *cost* term dominates, and it is exactly the row the registered arithmetic called.

**Gate-panel score is therefore 4 wins / 2 real regressions / 0 inconclusive**, not 4/1/1.

---

## 1. What the table actually isolates (this reframes everything)

`full_ran = False` on **60/60 gate-panel rows**, and `lbbd_ran = False` on **all 74 rows including the t=300 ones**. Consequences, all load-bearing:

- **At t=60 on the mass tail the baseline arm never solves the master either.** Both arms ship seed → repair → polish, from `AssignmentMaster._greedy()` (baseline) or `congestion_assignment` (arm), through the *identical* code path with the *identical* budget. The t=60 gate panel is therefore a **clean congestion-greedy vs preference-greedy A/B** — the purest possible test of the congestion rule itself.
- **The LBBD cut loop completes zero iterations on the mass tail at every timelimit tested**, including t=300 with the full pass running. So F26/F27/F28 (cut-loop / no-good / ρ-poisoning) are entirely **unexercised** by this table — neither confirmed nor refuted — and the cut loop's 2–40 iterations in the v0.4 sweep are an easy-tier-only phenomenon.
- **At t=300 prob_31 the full pass ran for both arms and LBBD did not.** That row is **master-assignment vs congestion-assignment, head to head, same oracle, same repair budget, 3/3 deterministic each side** — the single cleanest measurement of the F17 hypothesis in existence, and the master wins.

---

## 2. Per-row scoring against the registered La / breakeven / z1_slack

`layer = w2·obj2 + w3·obj3` (realized). `La` = registered proposal-layer floor for the congestion arm. `real/La` = realized layer ÷ proposal layer.

### Bucket B/C — the arm decides finally (t = 60)

| inst | prediction | breakeven | z1_slack | obj1 base→cong | Δobj | Δ% | Z1 share of Δ | La | realized layer | real/La | **VERDICT** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 21 | **win** | 376.1 | +14.1 | 362 → **396** | +431,712 | **+8.2 %** | **95 %** | 263,460 | 439,350 | 1.67 | **FALSIFIED** |
| 23 | confound row | 329.0 | +2.0 | — | — | — | — | 7,070 | — | — | **PENDING** (sweep never ran) |
| 24 | win | 178.8 | +16.8 | — | — | — | — | 65,215 | — | — | **PENDING** |
| 25 | coin flip | 743.7 | +1.7 | — | — | — | — | 25,729 | — | — | **PENDING** |
| 26 | **win** | 1640.7 | +17.7 | 1713 → **1461** | −3,265,403 | −14.0 % | 97 % | 301,801 | 653,546 | 2.17 | **CONFIRMED** |
| 27 | must beat z1 by **75 d** | 4405.3 | −74.7 | 4480 → **3150** | −16,689,254 | −27.4 % | 94 % | 2,055,264 | 2,142,584 | **1.04** | **CONFIRMED (conditional; condition met by 1330 d)** |
| 28 | win | 459.0 | +27.0 | — | — | — | — | 84,780 | — | — | **PENDING** |
| 29 | confound row | 100.5 | +45.5 | — | — | — | — | 35,484 | — | — | **PENDING** |
| 30 | near-tie | 550.0 | +6.0 | — | — | — | — | 29,996 | — | — | **PENDING** |
| 31 | **win, thin margin** | 2472.0 | +4.0 | 2468 → **1088** | −18,104,946 | −51.0 % | 98 % | 2,542,380 | 2,890,479 | 1.14 | **CONFIRMED at t=60** (see §4) |
| 32 | win | 1287.7 | +132.7 | — | — | — | — | 227,925 | — | — | **PENDING** |
| 33 | coin flip | 1927.9 | +1.9 | — | — | — | — | 195,110 | — | — | **PENDING** |
| 34 | win | 506.7 | +71.7 | — | — | — | — | 63,906 | — | — | **PENDING** |
| 35 | win | 349.2 | +17.2 | — | — | — | — | 73,915 | — | — | **PENDING** |
| 36 | win | 714.8 | +36.8 | — | — | — | — | 92,150 | — | — | **PENDING** |
| 37 | win | 1679.0 | +68.0 | — | — | — | — | 776,272 | — | — | **PENDING** |
| 38 | must beat z1 by **112 d** | 4987.9 | −112.1 | 5204 → **5280** | +2,534,314 | +3.6 % | 40 % | 2,126,484 | **2,046,832** | **0.96** | **CONFIRMED (conditional; condition FAILED — lost 76 d)** |
| 39 | win | 1503.5 | +26.5 | — | — | — | — | 104,858 | — | — | **PENDING** |
| 40 | must beat z1 by **56 d** | 8350.7 | −56.3 | 9365 → **5708** | −2,387,797 | −37.9 % | 98 % | 105,047 | 111,620 | 1.06 | **CONFIRMED (conditional; condition met by 3657 d)** |

**Scored: 1 FALSIFIED (21), 2 CONFIRMED (26, 31@t60), 3 CONFIRMED-conditional (27, 38, 40 — of the three at-risk rows named, exactly one, prob_38, went to the loss branch), 13 PENDING.**

### Buckets A and D/E — **PENDING, unscoreable**

The 34-instance screening sweep never started (the tree lost `utils.py` mid-run). Bucket A (**prob_1, 2, 8** — the F25 certificate-loss prediction) and Bucket D/E (**prob_3–20, 22** — LBBD-rescue, named at-risk rows prob_10 and prob_20) are untouched. **PENDING, not confirmed.** They re-arm the moment the sweep runs.

### INVALID ROWS (not counted either way)

- **prob_38 @ t=300, 5 of 6 reps**: `CRASH_INTERNAL / ModuleNotFoundError: No module named 'utils'` — caused by the concurrent reorg deleting `baseline/utils.py`. −1 rows in the CSV; must never be read as arm failures. 3 congestion + 2 baseline reps invalidated.
- **prob_21 reps 1–2 `lb_gap_note = "proof(zero-tardy)"`**: eva's own harness bug, label only; objective/obj1/wall unaffected and used above.
- **prob_38 @ t=300 baseline rep1 wall = 272.149 s** (breaches 0.90 × 300 = 270 s by 2.15 s): valid row, but an escalation about the *baseline*, orthogonal to the arm. Escalation seconded.

---

## 3. The prob_21 falsification — mechanism, named, not absorbed

Prediction was "win, z1_slack +14.1". Actual: **+8.2 %, deterministic, zero range overlap, 5/5.** Decomposition:

```
Δobjective  = +431,712
  from Z1   = +453,322   (obj1 362 → 396, i.e. +34 tardy days)      95 % of |Δ|
  from layer=  −21,810   (obj2 696→1230 costs +5,340; obj3 3028→2847 saves −27,150)
```

**The arm's assignment-layer cost was slightly BETTER than the baseline's. The entire regression is tardiness.** And from the p6 measurement, prob_21 is a row where the arm *did* do its job on its own statistic: peak commanded per-layer fill **1.79 → 1.00**. The arm removed the areal overload and produced **34 more tardy days**.

That is **F30 inversion 2 / F18 measured on a real instance for the first time**: *the congestion on prob_21 is geometric, not areal.* The three mechanism candidates, adjudicated:

- **Geometric-not-areal (F30 inv. 2): CONFIRMED as the mechanism.** 95 % Z1 share, layer improved, fill cleared.
- **Seed variance: RULED OUT.** Both arms bit-deterministic on prob_21 (baseline obj1 362 ×5, congestion 396 ×5).
- **The "La is a proposal floor" caveat: CONTRIBUTED, but does not explain it.** The arm's realized layer ran **1.67× La** on this row, which alone eats 13.2 of the 14.1 days of slack — the corrected slack was ≈ 0.9 days and the arm spent 34. The caveat should have converted "win" into "no call"; it does not explain the sign of ΔZ1.

**prob_21 and prob_26 have identical `fill_grd → fill_arm` (1.79 → 1.00) and opposite outcomes (+8.2 % vs −14.0 %).** The fill-reduction predictor offered in F30 is **falsified as a sufficient predictor**. The win feature remains unidentified.

### `20260727b-2` — the La/breakeven instrument bounds the arm's COST well and has zero predictive power over its BENEFIT

Measured `realized layer ÷ proposal layer`:

| | congestion arm | preference-greedy (baseline) |
|---|---|---|
| range | **0.96 – 2.17** (median ≈ 1.10) | **1.47 – 35.27** |
| best | prob_38: La 2,126,484 vs realized 2,046,832 (**−3.7 %**) | — |
| worst | prob_26: 301,801 → 653,546 (**+117 %**) | prob_27: 31,156 → 1,098,948 (**35×**) |

(a) `La` is a usable floor **only for the congestion arm** — for the greedy proposal it is meaningless, because `repair_tardiness` legitimately rewrites the partition to buy Z1 (prob_31 baseline: proposal z3 = 0 → shipped obj3 = 9626). (b) **ΔZ1 is 94–98 % of the total delta on 5 of the 6 gate rows**, and the instrument says nothing about ΔZ1. Every Bucket B/C row with |z1_slack| below ≈ 30 days — **12 of 19**, including 21, 23, 25, 26, 30, 31, 33 — was inside the instrument's own error bar and should have been registered as **NO CALL**. Over-labelled; owned. The instrument earned its keep on exactly one row, prob_38 — the only row where the cost term reached 60 % of the delta — and there it was accurate to 3.7 % and called the loss branch correctly.

---

## 4. The t=300 reversal on prob_31 — what it does to each prediction and to the promote case

Measured, N = 3 each side, both arms bit-deterministic, `full_ran = True` both, `lbbd_ran = False` both:

| arm | obj1 | obj2 | obj3 | layer | objective | wall | margin vs 270 s |
|---|---|---|---|---|---|---|---|
| baseline | 941 | 7440 | 9184 | 2,474,448 | **15,020,801** | 163–205 s | +65 … +107 s |
| congestion | 947 | 5919 | 9952 | 2,674,941 | 15,301,292 | **234–241 s** | **+29 … +36 s** |

Δ = **+280,491 (+1.9 %)**, of which **71 % is the layer** (obj3 +768 × w3 267 = +205,056) and 29 % is Z1 (+6 days).

**Budget elasticity — the promote-killer:**

| arm | obj1 t=60 → t=300 | objective t=60 → t=300 |
|---|---|---|
| baseline | 2468 → 941 (**−62 %**) | 35.50 M → 15.02 M (**−58 %**) |
| congestion | 1088 → 947 (**−13 %**) | 17.40 M → 15.30 M (**−12 %**) |

The arm's 56 % lead at t = 60 is **not an assignment-quality advantage; it is a head start**. Given 5× budget the baseline closes essentially the whole gap by itself, and what remains is the arm's structural Z3 bill. The arm is already near its asymptote at t = 60; the baseline is not.

**Effect on each prediction bucket:**

- **Bucket B/C (t=60) survives as scoped, and only as scoped** — valid evidence about t ≈ 60 and nothing else. The bucket definition ("instances where HEAD ran 0 LBBD iterations, so the arm's assignment is final") turns out to be a *timelimit-dependent* property, not an instance property — a defect, owned; buckets should have been keyed on `full_ran`.
- **prob_31's CONFIRMED at t=60 is downgraded to CONFIRMED-at-t60-only, REVERSED at t=300.** One row, N=3, deterministic — but it is the only row that tests the axis, and it points the wrong way.
- **Bucket A (F25, certificate-time) becomes more important, not less** — the t=300 wall data shows the arm consuming **+36 % wall** and **halving the safety margin** in exactly the regime hidden instances run in.
- **Hidden timelimits are minutes → 30 min.** The gate panel measured the arm at the one timelimit where it looks best, and the single point on the axis that matters reverses.

**HYPOTHESIS (labelled; not measured, do not quote as a conclusion):** if the arm's +36 % wall inflation on prob_31 @ t=300 generalizes, then prob_38 — where the *baseline* already breached 0.90 × 300 at 272.1 s — would land near 370 s under the arm, past the 305 s hard kill, i.e. a −1. Counter-evidence in the same table: at t=60 the arm's *seed* packs **faster** on prob_38 (`expected 14.5–17.4 s` vs baseline `15.5–19.1 s`), so the inflation may be prob_31-specific. **This is what the 5 crashed reps would have told us — top DEFERRED measurement.**

---

## 5. What survives for the ◆0.4 three-effect discussion

**(a) Congestion effect — real, large, bidirectional, predictor unknown.**
Cleanly isolated: at t=60 both arms shipped seed+repair+polish with no master (`full_ran=False`, 60/60), so this is congestion-greedy vs preference-greedy with everything else held constant. Result **4 W / 2 L**: wins prob_26 (−14.0 %), 27 (−27.4 %), 31 (−51.0 %), 40 (−37.9 %); losses prob_21 (+8.2 %) and prob_38 (+3.6 %, 5/5 on objective). Wins are 94–98 % Z1; the losses are 95 % Z1 (prob_21, geometric congestion) and 60 % layer (prob_38, Z3 bill). **The proposed predictor (areal fill reduction) is falsified** — prob_21 and prob_26 share `fill_grd = 1.79 → 1.00` and land on opposite sides. Do not promote on a feature we cannot name.

**(b) Oracle-strength effect (F29 confound) — ELIMINATED on everything measured, still live on everything unmeasured.**
No row in this table gives the arm an oracle the baseline did not get. F29 is **scoped down, not refuted**: it remains live only for the 34-instance screening sweep, specifically the 14 instances where `arm == AssignmentMaster._greedy()` bit-identically (prob_1, 2, 3, 4, 6, 8, 9, 11, 13, 14, 17, 18, 23, 29). **When the sweep runs, prob_23 and prob_29 are the confound detectors: if either moves materially, the effect is oracle strength and the cheap fix is to give the greedy seed the full-strength oracle, not to ship the arm.**

**(c) Certificate-time effect (F25) — entirely PENDING, with one adjacent measured signal.**
No row can exercise it (lives on prob_1/2/8, in the sweep that never ran). F25's mechanism is unchanged and still code-forced. The adjacent measured signal is the t=300 wall/margin inflation in §4. **Do not close F25 on this table.**

**Additional survivor:** the LBBD cut loop completed **zero iterations on all 74 rows** at both timelimits on the mass tail. Whatever the cut loop is worth, it is worth nothing on this instance class at these budgets — which weakens the "the loop will rescue the arm" premise underpinning the Bucket D/E predictions; re-check when the sweep runs.

---

## 6. Updated recommendation

**DO NOT PROMOTE the congestion arm as the default.** Grounds, in order:

1. In the regime hidden instances actually run in (minutes → 30 min), the only clean head-to-head — master assignment vs congestion assignment, same oracle, same budget, 3/3 deterministic — has the **master winning** (15.02 M vs 15.30 M), and 71 % of the arm's loss is a structural Z3 bill that more budget cannot remove.
2. Even in its best regime the arm is **4 W / 2 L**, not a clean win, and the losing mechanism on prob_21 (areal overload cleared, tardiness up 34 days) says the arm's objective function is not the objective.
3. The arm costs **+36 % wall and halves the safety margin** at t=300 on the one instance measured, on a machine where the baseline already breached 0.90 × timelimit once. Under R − nb, margin is worth more than 1.9 %.
4. The evidence base is 6 of 40 instances at t=60 and 1 of 40 at t=300, local-only, not gauntlet-valid.

**DO NOT REJECT the F17 finding.** The diagnosis is confirmed: on the mass tail at short budgets the master's assignment is bad enough that a greedy congestion rule beats it by up to 51 %. What is refuted is the *remedy* — replacing the master's assignment wholesale.

**The variant for the ◆0.4 table** (HYPOTHESIS as to value; the dominance argument is arithmetic): **use the congestion assignment for the SEED pass only, and leave the full pass on the master.** Where the full pass is budget-skipped (all 6 gate instances at t=60) it reproduces the congestion arm **bit for bit** — inheriting the whole 4 W / 2 L t=60 result including the prob_21 regression; where the full pass runs (t=300) it reproduces the baseline **bit for bit** — the prob_31 reversal disappears. It **strictly dominates the current congestion arm** and cannot be worse than baseline in the long-timelimit regime. It does not fix prob_21 or prob_38, and it is not a promote case on its own.

**Gate on before any promote vote:** (i) tree restored / canonical path confirmed, (ii) the 34-instance screening sweep (resolves Buckets A and D/E and the F29 confound detectors), (iii) prob_38 @ t=300 re-run (6 reps) with wall recorded — the −1 question.

**Updated DEFERRED list, re-ranked:**

| # | Measurement | Settles |
|---|---|---|
| **D1** | prob_38 @ t=300, both arms, N≥3, wall + margin recorded | The §4 HYPOTHESIS: does the arm's +36 % wall inflation generalize to a hard-kill −1 on the one instance already at 272 s? Top of the list. |
| **D2** | 34-instance screening sweep @ t=60, N=1, both arms | Buckets A and D/E (13 PENDING rows); F25's certificate-loss prediction on prob_1/2/8; the F29 confound detectors prob_23 / prob_29. |
| **D3** | prob_21 and prob_26 @ t=300, both arms | Whether the t=300 reversal is prob_31-specific or general — the highest-information addition to the promote case; also probes the missing win-feature. |
| **D4** | Seed-pass-only feasibility, both arms, all 40 (was M1) | The −1 containment question: does the arm's partition ever break the raster-only seed? |
| **D5** | (was M2) `"feasible": false` audit counts per arm from the info stream | F26 reachability. |
| **D6** | (was M3/M6) master `time_cap` 4 vs 8; ρ=1-infeasible synthetic end to end | F33, F28 — both now known **unexercised on the mass tail** (`lbbd_ran=False`, 74/74); demote to easy-tier scope. |

**New findings from this scoring pass (pass-local IDs; canonical numbers at fold time, task 0.11):**
`20260727b-1` prob_38 is a real 5/5 objective regression, not inconclusive · `20260727b-2` the La/breakeven instrument bounds cost (±4 %…+117 %) and has no power over ΔZ1 (94–98 % of every delta); 12/19 Bucket B/C rows should have read NO CALL · `20260727b-3` the t=60 gate panel eliminates the oracle-strength confound (`full_ran=False`, 60/60), scoping F29 to the unmeasured sweep; the t=300 prob_31 row is a clean master-vs-arm head-to-head that the master wins · `20260727b-4` the arm's advantage is budget elasticity, not assignment quality (baseline −62 % obj1 with 5× budget vs the arm's −13 %), and the arm costs +36 % wall / half the margin in that regime.

---

*Persisted verbatim by the architect session on rex's behalf, 2026-07-28.*
