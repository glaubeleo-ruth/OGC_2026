# OGC 2026 — Blindspot Pass (2026-07-27b): the F17 congestion-assignment arm

**Target:** `solver/congestion.py` + plumbing in `solver/api.py`, `solver/conductor.py`,
`solver/lbbd.py` at commit `00437ce` ("F17 assignment arm behind a flag, default baseline").
Diff base `44d5c1e`: 4 files, +217/−13.
**Tree snapshot at pass start:** `HEAD = 00437cec5014ab31d576dc58558f77b5e9f28ac2`; working tree
dirty in `alg_tester/settings.json` and `baseline/myalgorithm.py` (tom's audit-ladder package —
**declared out of scope, not read for attack, not imported**). Untracked: this pass's predecessors.
**Findings continue the F-log at F25** (F19–F24 in `BLINDSPOT_PASS_2026-07-27_audit_ladder.md`).

**Contention discipline.** eva is running the F17 decision A/B on this machine. Every measurement
below is pure arithmetic over `../train/*.json` + `solver/` imports, or a 4-block/8-block toy
CP-SAT model that solves in milliseconds. Total CPU for the whole pass ≈ 40 s at `nice -n 19`,
no pipeline invocation, no packing, no `api.solve`, no 60 s run. Everything that needed real
solver time is in the DEFERRED list.

Scratch (throwaway): `/private/tmp/claude-501/-Users-jungwoosuh-Desktop-workspace-03-Projects-OGC-2026/6332b06e-d056-4262-9589-90fb10c82042/scratchpad/rex_f25/`
— `PROGRESS.md`, `p1_layer_regret.py`, `p3_cap_and_regret.py`, `p4_nogood_semantics.py`,
`p5_adversarial.py`, `p6_order_and_tightness.py`, `p7_predictions.py`, `p1/p3/p6_rows.json`.

---

## Attack 1 — θ soundness in the arm path

Six load-bearing claims from tom, attacked one by one.

| # | Claim | Verdict |
|---|---|---|
| 1 | "The arm does not touch θ at all" | **CONFIRMED** |
| 2 | θ gets values only from `bounds.bay_lb` certified LBs via `lbbd.derive_cuts` | **CONFIRMED** |
| 3 | Realized congestion-arm costs flow only to `IncumbentStore` + `add_evaluated_nogood`, exact-match binding | **CONFIRMED (measured 1/16)**, with a latent widening trap → F27 |
| 4 | `proposal = master_assignment or proposed_assignment` changes who proposed, not what a cut asserts | **CONFIRMED** |
| 5 | Certificate fields can never report OPTIMAL off the greedy arm | **CONFIRMED**, but the arm makes one stop rule *unreachable* → F25, and leaves one over-claim open → F26 |
| 6 | Default path is bit-identical to HEAD | **CONFIRMED for the returned solution**, conditional on the grader's environment → F31 |

Detail on the ones that took work:

**(1)/(2).** `congestion.py` contains no reference to `theta`, `bay_lb`, `pooled_lb`, `_master_bound`
or `AssignmentMaster`. Its only import from the bounds layer is `_layer_demand`, a pure
per-block/per-layer floor. The single write path into θ is
`AssignmentMaster.add_tardiness_cut`, called from exactly one site (`lbbd.derive_cuts:100`) and
gated by `if lb is not None and lb > 0` where `lb = bounds.bay_lb(...)` returns
`ceil(BestObjectiveBound)` of the F5 per-layer cumulative model, or `0` on UNKNOWN. No realized
exit time, no `objective.z1_tardiness`, and no `info["z1"]` reaches the master.

**(4) — the premise-swap hunt (the F8 disease).** The failure I was looking for is a cut whose
validity premise is "assignment A" but which is imposed while the master reasons about B. It does
not occur. `derive_cuts` builds `bay_set` from the *same dict* that `conductor.run` used to build
`by_bay_ids`, and `delayed_by_bay` is `info["delayed_initial"]`, which is the **pre-repair** per-bay
delay list of that same packing. So cluster ⊆ (blocks the proposal put in bay j), and the cut is
the conditional `theta[j] ≥ lb·(Σ_{i∈S} y_ij − |S| + 1)`, valid for *any* assignment that keeps S
together in j by monotonicity of bay tardiness in the block set. The two info keys are mutually
exclusive by construction (`master_assignment` only in the `assignment is None and use_master`
branch, `proposed_assignment` only in the `else`), so the `or` is never a silent tie-break.
Empty-instance degradation is correct: `{} or absent → None → break`.

Cross-check that strengthens the k-best framing: **the arm's assignment satisfies the master's
own ρ=1 fluid capacity on all 40 train instances** (max per-bay load 0.827 of `A_j·H`, prob_40),
so the no-good genuinely removes a point that was inside the master's feasible region — it is a
real k-best step, not a cut on an already-excluded point. (By contrast the preference-greedy
*violates* that cap on prob_27/31/36/37/38/40, up to **4.00×** on prob_31.)

**(3) — measured, toy CP-SAT, 4 blocks × 2 bays.** After `add_evaluated_nogood(a0)`, brute-force
enumeration of all 2⁴ assignments against the model's own literal-selection logic gives
**exactly 1 of 16 points excluded**, and the re-solve returns a point differing from `a0` in
exactly 1 block. Exact-match binding CONFIRMED. Conditional θ semantics also behave: a cut
`theta_0 ≥ 7` on cluster {0,1,2} is evaded by the master moving block 2 to bay 1, and `theta`
stays 0 — i.e. the cut deactivates when a member leaves, as documented.

### F25 (−1-adjacent OPPORTUNITY, measured, code-forced) — under the arm, `assignment_lb` is structurally `None`, so the only *early* certificate stop in the pipeline becomes unreachable

`lbbd.cut_loop` computes `assignment_lb = _master_bound(inst, master)` **once, before the loop**.
`_master_bound` requires `master.last_status == "OPTIMAL"`. Under the congestion arm the full pass
takes `conductor.run(..., assignment=arm_assignment, ...)`, whose `else` branch never touches the
`master` kwarg, so the master arrives at `cut_loop` with `last_status = "none"` and
`last_z2 = None`. `assignment_lb` is therefore `None` for the entire loop, and it is never
recomputed even after the master solves at iteration 0. **`stop: assignment_lb_reached` cannot
fire under the congestion arm on any instance.**

This is not a wrong answer — the stop is a claim of optimality, and losing it errs conservative.
It is a measured behaviour change on the only three instances that carry the claim:

| instance | HEAD stop | HEAD wall | HEAD objective |
|---|---|---|---|
| prob_1 | `assignment_lb_reached`, lb = 1499 | **0.87 s** | 1499 |
| prob_2 | `assignment_lb_reached`, lb = 3690 | **0.88 s** | 3690 |
| prob_8 | `assignment_lb_reached`, lb = 11252 | **2.24 s** | 11252 |

Under the arm these three run to the `master_bound_closed` / budget path instead. The objective
should be recovered (the arm's assignment is not the master's argmin on any of them — arm layer
costs are 2065 / 6620 / 12412 versus the certified 1499 / 3690 / 11252, i.e. **+37.8 % / +79.4 % /
+10.3 %** if *not* recovered), but the certificate and the sub-second exit are gone.

The consequential part is the interaction, and it is outside `solver/` so I only flag it: the
committed `myalgorithm.py` header at `00437ce` prices its hedge on exactly this behaviour —
*"the solver runs first on `OGC_SOLVER_FRAC` … so when the solver stops early at a certificate"*
the remainder goes to the hedge. On the prob_1/2/8 class the arm deletes that donation. Whether
that is good or bad is eva's table's business; that it is an **unstated** side effect of a change
advertised as "assignment only" is mine.

### F26 (SOUNDNESS, latent, arm-amplified) — `open_below` is keyed on internal tardiness, not on the audit, so `master_bound_closed` can still over-claim

F11's fix tracks proposals that *packed tardy* and refuses to close while one sits below the
incumbent. The key is `if delayed:` where `delayed = result.info["delayed_initial"]` — an
**internal** quantity. It does **not** consult `utils.check_feasibility`.

The open case: a proposal that packs to internal `z1 = 0` (so it never enters `open_below`) but
whose emitted solution **fails the utils audit** (so it never enters the store either). It has
been excluded by no-good on the strength of a packing that produced no certified refutation and no
banked incumbent, and `master_bound_closed` then asserts "nothing evaluated or unevaluated can
win" over a region that no longer contains it. Its true cost could be its layer cost, below the
incumbent — F11's exact failure mode, one branch over.

Why the arm amplifies it: at iteration 0 under the arm, the proposal is the congestion assignment,
whose audit happened back in `api.solve`'s full pass. `cut_loop` receives `first_result` and has
**no channel at all** to learn whether that audit passed — `res` is discarded at `api.py:190`
except for the log line. Iteration 0's proposal is precisely the one proposal whose feasibility
`cut_loop` cannot observe, and under the arm it is also the one proposal the master never
generated and therefore has the least reason to trust.

**Reachability is unmeasured and is the weak link.** The raster over-approximates, so
raster-disjoint ⇒ polygon-disjoint, and audit-infeasible-after-internal-z1-0 should be rare.
**Missing measurement:** count of `"feasible": false` entries in `info["passes"]` across a full
panel, split by arm — this is free if eva's harness already keeps the info stream. Fix shape is
one line: gate `open_below` on the audit result, or record every excluded proposal's layer cost
regardless of `delayed`.

### F27 (SOUNDNESS, latent trap, measured on a toy) — `add_evaluated_nogood` silently *widens* when a `(block, bay)` pair has no `y` variable

`assignment.py:193` builds `lits = [y[i,j] for i,j in prev.items() if (i,j) in y]` and then
`Add(sum(lits) <= len(lits) - 1)`. If any pair is dropped, the constraint stops being
"not this exact point" and becomes "no assignment agreeing with `prev` on the *retained* blocks" —
a cut over 2^(#dropped) unevaluated points. Measured on the 4-block toy: injecting one
out-of-domain pair takes the exclusion from **1/16 to 2/16**.

Currently **unreachable**, and I want that on the record as a confirmation, not a scare:
`congestion._fallback_bay` is `max(inst.bays, key=lambda x: x.area).id`, character-for-character
the same expression `_solve_cpsat` uses for its own domain fallback, and `compatible_bays` is
called from the same `Instance`. Measured: **0 blocks with an empty compatible set on any of the
40 train instances**, so even the fallback never fires. It becomes reachable the instant any
future arm proposes a bay outside `compatible_bays(b) ∪ {argmax-area bay}` — a k-best pool
explorer, a repair-derived proposal, or a cached assignment from a differently-parsed instance.
The guard is one assertion: drop the whole no-good if `len(lits) != len(prev)`.

### F28 (−1 RISK, reproduced on a toy; pre-existing in `assignment.py`, surfaced by auditing the arm's loop) — one capacity-infeasible master solve permanently degrades the master to `_greedy()` for the rest of the run

`_solve_cpsat` handles a non-OPTIMAL/FEASIBLE status by setting **`self.rho = float("inf")`** and
delegating to a fresh `relaxed` object. `self.rho` is never restored. Every subsequent
`self.solve()` re-enters `_solve_cpsat`, evaluates `int(self.rho * bay.area * horizon)` →
`OverflowError: cannot convert float infinity to integer`, which `solve()`'s bare `except` swallows
and returns `_greedy()`.

Reproduced (8 blocks, 2 bays, cap deliberately infeasible):

```
solve1 status= INFEASIBLE  rho= inf
solve2 status= greedy      rho= inf
solve3 (with a no-good on solve2's answer) -> IDENTICAL assignment, same as a2? True
theta/z2/z3 fields: None None None
```

Consequences, in order of severity: (i) `AssignmentMaster` is dead for the remaining budget;
(ii) `_greedy()` ignores cuts and no-goods, so `cut_loop` re-packs a bit-identical assignment
every iteration until budget death, appending duplicate no-goods and burning `_MAX_LB_CALLS`
certified-LB solves per iteration on a set it has already bounded; (iii) `last_status` stays
`"greedy"`, so `_master_bound` returns `None` and no stop rule can fire — the loop cannot even
exit early. Note also that the *relaxed* solve's genuine OPTIMAL is discarded: it is written to
`relaxed.last_status`, never to `self`, so a valid certificate is lost on the same path.

**Latent on train:** the necessary condition for ρ=1 infeasibility (Σ maxla·proc > Σ A_j·H) is
satisfied by no train instance — worst is **prob_38 at 0.729**, then prob_27 0.693, prob_40 0.624.
A hidden instance **1.37× denser than prob_38** trips it, and per-bay compatibility can trip it far
earlier than the global ratio suggests. Not arm-specific (the baseline path degrades identically),
but it belongs in this pass because under the arm the master's *first* solve happens inside
`cut_loop`, where there is no other assignment source to fall back to. Fix is `try/finally` around
the ρ mutation, three lines.

---

## Attack 2 — train↔hidden generalization of the win pattern

### F29 (attribution defect in the A/B, measured) — on 14/40 train instances the arm's assignment is **bit-identical to `AssignmentMaster._greedy()`**, and on 29/40 it moves fewer than 5 % of blocks

This falls straight out of the arm's own key, `(over, -b.prefs[j], j)` minimized. While no
compatible bay is *strictly over* its per-layer area in the block's window, `over == 0` for all
candidates and the key collapses to "highest preference, then lowest bay id" — which is exactly
`_greedy`'s `max(compat, key=prefs)` including its tie-break. **The congestion term is inert until
a bay saturates.** The arm is not a congestion-aware assignment; it is the preference-greedy with a
saturation override.

Measured (`p1`, `p6`):

- `arm == _greedy()` exactly on **prob_1, 2, 3, 4, 6, 8, 9, 11, 13, 14, 17, 18, 23, 29** (14/40).
- Blocks moved relative to `_greedy()`: **< 5 % on 29/40**. Only 11 instances exceed it —
  prob_31 (66 %), 27 (51 %), 38 (45 %), 40 (44 %), 36 (40 %), 25 (21 %), 21 (17 %), 26 (17 %),
  22 (15 %), 37 (13 %), 33 (11 %).
- The arm never scores worse than `_greedy()` **or** than an LPT-balance heuristic on its own
  experienced-overload statistic on any instance (0/40 inversions) — so no falsification of the
  arm's internal greediness.

**Why this matters for the decision, not just the description.** `api.solve`'s seed pass at HEAD
already uses `_greedy()`. So on those 14 instances the arm's "full pass" re-packs the seed's
assignment — but now with `use_rescue=True`, repair, polish and bounds, which HEAD only ever grants
to the *master's* assignment. Any win eva measures on prob_23 or prob_29 (both `arm == greedy`
**and** in the arm-decides-finally tail) is therefore attributable to **"give the greedy assignment
the full-strength oracle"**, not to congestion awareness — and that is a strictly cheaper,
strictly safer change than the arm. The A/B's statistical power for the actual F17 hypothesis lives
in ~11 rows, not 40. None of the six F17 gate instances (21/26/27/31/38/40) are in the identical
set, so F17's original 6/6 is not touched by this; the *panel-wide* reading of eva's table is.

### F30 (generalization risk, measured — the win feature, and where it inverts)

The single statistic that separates win from no-op is the **peak commanded per-layer fill under the
preference-greedy**, `fill_grd = max over (bay, layer, day) of load / A_j` with each block charged
over `[release, release+proc)`. Measured across 40:

- `fill_grd > 1` on 26/40; the arm pulls it to **≤ 1.05 on 34/40**.
- The arm's win magnitude tracks `fill_grd` almost perfectly on the tail: prob_31 **7.70 → 1.00**,
  prob_27 3.74 → 1.55, prob_36 2.82 → 1.00, prob_38 2.59 → 1.69, prob_40 2.34 → 1.05,
  prob_25 2.33 → 1.34, prob_21 1.79 → 1.00, prob_26 1.79 → 1.00.
- Where `fill_grd ≤ 1` (the whole easy tier bar six), the arm has **nothing to do** and reduces to
  F29's no-op.

Three inversions, i.e. hidden-instance shapes where the feature is absent or backwards:

1. **`fill_grd ≤ 1` and w2- or w3-dominant.** The arm is the preference greedy, which is
   Z2-blind, while the master solves Z2/Z3 *exactly*. Measured cost of that blindness where the
   master's answer is certified: prob_1 arm layer 2065 vs certified optimum 1499 (**+37.8 %**),
   prob_2 6620 vs 3690 (**+79.4 %**), prob_8 12412 vs 11252 (**+10.3 %**). On train the LBBD loop
   recovers these; on a hidden instance where the budget dies before iteration 0 completes, it does
   not, and that penalty ships.
2. **High `fill_grd` but geometric, not areal, congestion.** F18 already measured this shape:
   under a balanced assignment the fluid ΣT is 0 on prob_21/26/31/40 while the realized obj1 is
   323 / 2661 / 2217 / 6496. The arm optimizes the areal statistic; F18 says the areal statistic is
   already at zero when thousands of tardy days remain. An instance whose overload is entirely
   shape-tiling gets the arm's full Z2/Z3 bill and none of its Z1 refund.
3. **Overload the arm cannot clear.** On prob_25 (1.34), 27 (1.55), 33 (1.03), 38 (1.69),
   39 (1.01), 40 (1.05) the arm ends still over capacity — it pays the preference bill *and* keeps
   the congestion. These are the rows where `breakeven − obj1_HEAD` goes negative (below).

### Registered predictions for eva's A/B — checkable row by row

Definitions, all from stamped `results/2026-07-25_solver_v0.4_lbbd_full_sweep.csv` (N=1) plus
pure arithmetic:

- `La = w2·Z2(arm) + w3·Z3(arm)` — the arm's assignment-layer **floor**: no packing can go below it.
- `breakeven = (objective_HEAD − La) / w1` — the most tardiness the arm may realize and still tie.
- `z1_slack = breakeven − obj1_HEAD` — how much *worse* the arm's tardiness may be than HEAD's.
  `z1_slack < 0` means the arm must beat HEAD's tardiness by that many block-days merely to tie.

**Bucket A — certificate loss, objective tie expected. prob_1, prob_2, prob_8.**
Predict: objective **identical** to HEAD (1499 / 3690 / 11252); `stop` field is **not**
`assignment_lb_reached` (F25); wall time rises from 0.87 / 0.88 / 2.24 s to seconds-to-full-budget;
`lbbd_iters ≥ 1` where HEAD had 0.
*Falsified if:* the objective moves at all (→ the loop does not recover the master's argmin, and
the +37.8 / +79.4 / +10.3 % floors ship), **or** `assignment_lb_reached` appears (→ my reading of
`_master_bound`'s `"none"` status is wrong).

**Bucket D/E — LBBD loop rescues; expect neutral, slightly negative. prob_3–20, prob_22.**
`HEAD lbbd_iters` ranges 1–40 here, so the master still gets its turn after the arm's pass.
Predict: **|Δobjective| ≤ 2 %** on most rows, with `lbbd_iters` down by roughly one iteration
(the arm consumes the first full pass). Named at-risk rows: **prob_10** (`z1_slack = −1.9`, arm
layer 106288 vs shipped 78785, i.e. **+34.9 %** if the loop fails to rescue) and **prob_20**
(only 2 iterations at HEAD → least rescue capacity, `z1_slack = +0.1`).
*Falsified if:* any easy-tier row moves by more than a few percent in either direction — a large
**win** there falsifies "the master is exact on this tier and the arm cannot beat it"; a large
**loss** falsifies "the loop rescues".

**Bucket B/C — the arm decides, finally: prob_21, 23–40 (19 rows).** HEAD ran **0 LBBD
iterations** on all of them, meaning the loop broke on the budget check *before* the first master
re-solve. Under the arm the master therefore **never solves at all** and the congestion assignment
is the shipped partition. Predict wins where `z1_slack` is comfortable, coin-flips where it is not:

| inst | moved% | fill_grd→fill_arm | La | HEAD obj / obj1 | breakeven | z1_slack | prediction |
|---|---|---|---|---|---|---|---|
| 21 | 17.0 | 1.79 → 1.00 | 263 460 | 5 277 656 / 362 | 376.1 | **+14.1** | win (F17 gate) |
| 23 | **0.0** | 0.99 → 0.99 | 7 070 | 4 468 538 / 327 | 329.0 | +2.0 | **confound row (F29)** — any Δ is oracle-strength, not congestion |
| 24 | 3.0 | 1.23 → 0.99 | 65 215 | 2 448 516 / 162 | 178.8 | +16.8 | mild win |
| 25 | 21.0 | 2.33 → **1.34** | 25 729 | 521 801 / 742 | 743.7 | +1.7 | **coin flip** |
| 26 | 16.7 | 1.79 → 1.00 | 301 801 | 22 177 532 / 1623 | 1640.7 | +17.7 | win (F17 gate) |
| 27 | 50.7 | 3.74 → **1.55** | 2 055 264 | 60 791 136 / 4480 | 4405.3 | **−74.7** | **must also beat HEAD's z1 by 75 days** |
| 28 | 3.3 | 1.21 → 1.00 | 84 780 | 6 205 116 / 432 | 459.0 | +27.0 | win |
| 29 | **0.0** | 0.94 → 0.94 | 35 484 | 1 375 150 / 55 | 100.5 | +45.5 | **confound row (F29)** |
| 30 | 0.7 | 1.05 → 0.99 | 29 996 | 7 363 288 / 544 | 550.0 | +6.0 | near-tie |
| 31 | 66.0 | **7.70** → 1.00 | 2 542 380 | 35 501 729 / 2468 | 2472.0 | +4.0 | biggest structural change; win expected but the *margin* is thin — arm's Z3 bill is 2.5 M |
| 32 | 1.0 | 1.16 → 0.99 | 227 925 | 4 519 950 / 1155 | 1287.7 | +132.7 | win |
| 33 | 10.5 | 1.45 → **1.03** | 195 110 | 13 048 722 / 1926 | 1927.9 | +1.9 | **coin flip** |
| 34 | 0.5 | 1.09 → 0.99 | 63 906 | 1 752 697 / 435 | 506.7 | +71.7 | win |
| 35 | 3.5 | 1.32 → 1.00 | 73 915 | 4 730 051 / 332 | 349.2 | +17.2 | win |
| 36 | 39.6 | 2.82 → 1.00 | 92 150 | 568 920 / 678 | 714.8 | +36.8 | win |
| 37 | 12.8 | 1.89 → 1.00 | 776 272 | 6 372 359 / 1611 | 1679.0 | +68.0 | win |
| 38 | 45.2 | 2.59 → **1.69** | 2 126 484 | 68 630 442 / 5100 | 4987.9 | **−112.1** | **must also beat HEAD's z1 by 112 days** |
| 39 | 3.2 | 1.25 → **1.01** | 104 858 | 20 151 141 / 1477 | 1503.5 | +26.5 | win |
| 40 | 44.0 | 2.34 → **1.05** | 105 047 | 5 674 974 / 8407 | 8350.7 | **−56.3** | **must also beat HEAD's z1 by 56 days** (tom's smoke says yes by ~2700; that would confirm) |

The three negative-slack rows (27, 38, 40) are the sharpest test in the table: the arm is not merely
"probably better" there, it is **provably worse unless it removes ≥ 75 / 112 / 56 tardy block-days**,
because its Z3 bill alone exceeds HEAD's total layer cost. If eva's table shows any of them
regressing, the mechanism is already named (F30 inversion 3) and no post-hoc explanation is needed.

Caveats stated up front: the HEAD column is the **N=1** v0.4 sweep at 60 s solver-only, taken at a
different commit and configuration than eva's A/B; `La` is a floor on the *proposal*, and repair
plus polish move blocks across bays afterwards, so a row may finish below `La`; and the
seed-variance F-log precedent (prob_1 seed Z1 36–44) applies to every non-`assignment_lb_reached`
row. **These predictions are ordinal (direction and named at-risk rows), not point estimates.**
Treat a bucket as falsified only on N ≥ 3.

---

## Attack 3 — losing-class hunt

Both constructions run **assignment only** (`congestion_assignment` is pure arithmetic, 0.003–0.024 s
measured across the 40 train instances). No packer, no full solver. Script: `p5_adversarial.py`.

### F32 (SOUNDNESS-of-heuristic + OPPORTUNITY, constructed and measured) — the arm's scoring function is blind on exactly the two axes that decide the objective

**Case A — area-blind geometry (F5/F18 turned on the arm's own statistic).**
Two identical 20×4 bays (`A_j = 80`). Four 6×3 blocks (`_layer_demand = 18` each), all preferring
bay 0, release 0, proc 10, due 20. Arm output:

```
arm assignment {0:0, 1:0, 2:0, 3:0}   experienced_overload = 0
bounds.congestion_profile peak days in bay0: []   max mandatory load 0.0 vs A_j 80
```

4 × 18 = 72 ≤ 80, so the arm reports **zero congestion** and commits all four to bay 0 with bay 1
sitting empty. Hand proof that this is un-packable without tardiness: every block is 3 tall in a
4-tall bay, so all four intersect the line y = 2; their widths must then sum along x, and
4 × 6 = 24 > 20. Bay 0 holds at most three at any instant. The arm's statistic, `bounds`'
certified mandatory-presence profile, and the master's fluid cap **all report zero** — the arm's
scoring function provides no signal whatsoever on the class F18 identified as the entire remaining
gap on the mass tail. Note the arm equals the greedy here, so this is inherited blindness, not new
error; it bounds what the arm can *ever* deliver.

**Case B — slack-blind window (arm-specific error, the baseline does not make it).**
Same two bays. Four wide-slack blocks (release 0, due 400, proc 10 → slack 390) plus **one
zero-slack block** (release 0, due 10, proc 10 → slack 0), all preferring bay 0 (prefs [100, 0]):

```
arm assignment {0:0, 1:0, 2:0, 3:0, 4:1}
ZERO-SLACK block 4 -> bay 1        arm Z3 = 100.0   pref-greedy Z3 = 0.0
certified mandatory peak days if ALL FIVE in bay0: []   max mandatory load 18.0 vs 80
```

The arm charges every block over `[release, release+proc)` and **never reads the due date**. The
four flexible blocks saturate bay 0's window, so the arm evicts the *only urgent* block to the
non-preferred bay and pays `w3 · 100`. `bounds.congestion_profile` — the shipped, certified notion
of mandatory presence, `[max(release, due−proc), release+proc)` — says the flexible blocks are
mandatorily present on **no day at all** and that bay 0 holds all five with zero tardiness. The arm
evicts on a statistic its own certificate layer contradicts. Its docstring's justification
("the packer's shipped skeleton is enter-ASAP, so `[release, release+proc)` is the interval the
oracle will actually try to use") is exactly the assumption that fails on wide-slack instances —
and `conductor.py:109` hard-disables the queue-aware construction (`use_queue = False and …`), so
the enter-ASAP premise is currently self-fulfilling rather than justified.

**Exposure on real instances, measured (`p6`).** The arm's insertion order is
`(release, −peak_layer_area, id)` with no urgency term. I counted, per instance, blocks served
after a **same-release** block with strictly more slack: **48.6 % mean across all 40**, range
34 % (prob_23/24/25) to 61 % (prob_19). On the wide-slack tail specifically —
`slack_gt4_share` 0.39–0.54 on prob_24/25/26/31/38/40 — roughly half of all blocks are served in
an urgency-inverted order. That is not a proof of harm (the inversion only bites once a bay
saturates during the window), but it is the mechanism's exposure surface, and it is large.

The cheap counter-criterion, stated so it can be attacked in turn: charge the *mandatory* window
`[max(release, due−proc), release+proc)` (`bounds.congestion_profile`'s own definition, so the arm
and the certificate would finally speak about the same resource, which is what the docstring
claims but does not do), and order by slack ascending within a release day.

### F31 (−1 RISK, low severity; claim-scope, measured) — `OGC_ASSIGN_ARM` is a live configuration surface inside the submitted artifact

`solve()` reads `os.environ.get("OGC_ASSIGN_ARM", "baseline")` whenever `assign_arm is None`, and
the committed `myalgorithm.py` at `00437ce` calls `solver.api.solve(prob_info, timelimit*frac)`
without the kwarg. So the arm selected on the evaluation host is a function of that host's
environment.

`_resolve_arm` itself is total and fail-closed — measured on 13 inputs including `None`, `0`, `1`,
a list, an `object()`, an empty string, `"conges"`, `"congestion;rm -rf"` and a `__str__` that
raises: **13/13 resolve to `"baseline"`** except the four genuinely-congestion spellings
(`"congestion"`, `"CONGESTION"`, `"  Congestion  "`, `"congestion\n"`). It is read once per
`solve()` call, so mid-run mutation cannot switch arms inside a call. No crash path, no `-1`.

Two real consequences remain. (i) "The default code path is bit-identical to HEAD" is true of the
returned solution but is **conditional on the grader's environment being clean** — the claim should
be stated that way, and a submission-time assertion (`assign_arm="baseline"` passed explicitly from
`myalgorithm.py`, or the env read confined to a `__main__` benchmark harness) makes it
unconditional. (ii) **Experiment integrity, live right now:** if eva selects the arm by
`export OGC_ASSIGN_ARM=congestion` and runs her baseline rows in a shell that inherits it, both
arms of the A/B are the congestion arm and the table will show a clean tie. Her runner should pass
`assign_arm=` explicitly on both arms, and the table should carry the `info["assign_arm"]` value
per row as evidence rather than as an assumption.

### F33 (OPPORTUNITY, code-level; magnitude DEFERRED) — the arm halves the master's first-solve budget cap

At HEAD the master's first solve is inside the full pass at `master_cap = min(8.0, 0.15·remaining)`.
Under the arm the full pass does not solve the master at all, so the first solve is the one inside
`lbbd.cut_loop` at `master_cap = min(4.0, 0.15·deadline.remaining())` — a **hard cap of 4.0 s
instead of 8.0 s**, taken at a point where `remaining` is already one full pass smaller, and then
further reduced by `solve()`'s `sub_budget(0.25, cap=time_cap)`. On the easy tier the master
appears to solve in ~1.5 s (30+ iterations inside 50 s at HEAD), so the cap probably does not bind
there; on a larger hidden instance it plausibly turns an OPTIMAL into a FEASIBLE, which sets
`_master_bound` to `None` and disables *every* stop rule (compounding F25). Not measurable without
CP-SAT time — see DEFERRED M3.

---

## What would beat this?

A team that treats the assignment as a *decision to be certified*, not a heuristic to be swapped.
Everything above says the F17 arm is one bit of a much larger lever pulled crudely: it is the
preference-greedy on 14/40 instances and moves under 5 % of blocks on 29/40, its congestion
statistic is inert below saturation, and where it does fire it optimizes an areal quantity that
F18 already measured to be at zero while thousands of realized tardy days remain. A rival who puts
the *congestion signal into the master's objective* — a per-bay per-layer-index area-time
constraint over the certified mandatory window, or θ cuts that actually bind at iteration 0 rather
than after a wasted pass — gets the arm's tail win **and** keeps the exact Z2/Z3 the master
already delivers, instead of trading one for the other. That is strictly dominant over the A/B's
better arm on every row of my prediction table, and it is roughly the same amount of code. Beyond
that, the winner on this class is still whoever closes the geometric gap: the arm's own scoring
function reports zero congestion on my Case A, which is provably tardy with a bay standing empty,
and no amount of assignment cleverness recovers that — it needs width-profile / strip relaxations
and exact-layer tucking, i.e. the III.2 ladder that remains unbuilt. Under R − nb, the arm buys a
one-time tail improvement on ~11 rows; the ladder buys the class.

## What makes this −1 on a hidden instance?

Three named paths, in descending order of my confidence. **First, F28**: an instance whose density
crosses the ρ=1 fluid cap (train tops out at 0.729 of the necessary condition, and per-bay
compatibility can trip it well below the global ratio) permanently poisons `self.rho` to infinity,
after which the master is a silent `_greedy()` that ignores cuts and no-goods, `cut_loop` repeats a
bit-identical pass until budget death, and *no stop rule can fire* because `last_status` is stuck
at `"greedy"`. That is not itself a −1 — the incumbent store still holds an audited answer — but it
converts the entire post-seed budget into a no-op on precisely the dense instances where the seed is
weakest, and it is the exact shape that produced the prob_38 TIMEOUT already stamped in
`2026-07-27_submission5_arm_gate_baseline.csv`. **Second, the seed pass**: the arm now decides the
seed as well as the full pass, and the seed runs `use_rescue=False`. The arm spreads mass off the
preferred bay on up to 66 % of blocks (prob_31), and the seed is the whole −1 containment story
(hard rule 3). I found no added geometric tightness by the orientation-count proxy — **0/40
instances where the arm sends more blocks into bays with ≤ 1 fitting orientation** — but that proxy
is weak, and a raster-only pack of an unfamiliar partition failing where the greedy's succeeded is
an untested path on the class the arm targets. **Third, F25 compounding with the timing ladder**:
prob_1/2/8 go from 0.87–2.24 s to full-budget under the arm, which deletes the budget donation the
committed hedge rationale is priced on; on a hidden easy instance where line 1 now consumes its
whole slice, the hedge child that F21 showed can be SIGKILLed loses the head start it was assumed
to have. None of the three is a crash; all three are ways the arm spends the budget that keeps us
off −1.

---

## DEFERRED measurements (need real solver time; register before running, do not run during eva's A/B)

| # | Measurement | Cost | Settles |
|---|---|---|---|
| **M1** | Seed-pass-only feasibility and pack wall, both arms, all 40 (`conductor.run(use_master=False/assignment=arm)`, no repair, no full pass) | ≈ 2 min total | The −1 containment question above: does the arm's partition ever break the raster-only seed? Highest value per second in this list. |
| **M2** | Count of `"feasible": false` audits in `info["passes"]`, per arm, across a full panel | Free if eva keeps the info stream | F26 reachability — whether an internal-z1-0 proposal ever fails the utils audit. |
| **M3** | `AssignmentMaster.solve` status and wall at `time_cap` 4.0 vs 8.0, prob_3–20 + prob_21/26/31/38/40 | ≈ 3–4 min CP-SAT | F33 magnitude: does the arm's halved cap flip OPTIMAL → FEASIBLE and thereby disable all stop rules? |
| **M4** | Full-solver run of `p5_adversarial.py` Case A and Case B through `api.solve` at both arms, tl = 10 s | ≈ 40 s | Converts F32 from "the arm's statistic is blind" (proved) to "the arm loses objective because of it" (not yet proved end to end). |
| **M5** | Replay `cut_loop` under the arm on prob_1/2/8 with cut and stop-record logging | ≈ 3 min | F25's tie prediction and whether `master_bound_closed` fires at iteration 0 as I expect. |
| **M6** | Synthetic ρ=1-infeasible instance through `api.solve` end to end, 60 s | ≈ 1 min | F28's downstream cost: how much budget the poisoned master burns before the deadline. |

Row-by-row check of the Bucket A/D-E/B-C predictions against eva's stamped table follows the moment it lands: per-row CONFIRMED / FALSIFIED with her numbers against the `La`, `breakeven` and `z1_slack` columns above.

---

*Persisted verbatim by the architect session on rex's behalf (rex's harness cannot write report files), 2026-07-27.*
