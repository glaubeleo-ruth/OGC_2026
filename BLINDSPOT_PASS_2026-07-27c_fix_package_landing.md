# BLINDSPOT PASS 2026-07-27c — fix-package landing gate (task 0.6) + D2 prediction scoring

**Tree measured:** `ogc2026/baseline/sub/` (the 2026-07-28 canonical workspace). Not `baseline/`.
**HEAD at snapshot:** `b8f8d83fa10d2fb30cbc0fc146d574db2b2af43c`.
**Target commit:** `6176006`.
**Dirty:** `M ogc2026/REMAINING_TASKS.md`, `M ogc2026/alg_tester/settings.json`. **Untracked:** `_to_delete/`, `ogc2026-grader-explainer.pdf`, `ogc2026/baseline/results/2026-07-28_d2_screening_sweep.{md,csv}`, `ogc2026/baseline/submission.zip`, `ogc2026/rig/`. None mine; I wrote only scratchpad scripts.
**Out of scope:** solver internals beyond read-only inspection; the F17 arm's own merits (0.4 owns that); gauntlet validity (0.9 owns that — this box is macOS/8-core, so nothing here is SUBMIT-ELIGIBLE evidence).

**Instrument caveat.** Machine was free (load < 1, no swap pressure) — unlike the 07-27 and D2 sessions. All Part-1 timings are therefore *optimistic* relative to a loaded 4-core eval server, which is the conservative direction for every finding below (they all say "too little time remains", and a slower box leaves less). Part 2 inherits eva's contention caveat unchanged and is read ordinally.

**Numbering discipline.** Findings here carry pass-local IDs `20260727c-N`. Canonical F-numbers are assigned at fold time (0.11). **Note the live collision:** "F25" denotes the *reserve double-charge* in `BLINDSPOT_PASS_2026-07-27_audit_ladder.md` and the *certificate-loss prediction* in `BLINDSPOT_PASS_2026-07-27b_f17_arm_scoring.md`. I use "F25(ladder)" and "F25(cert)" below and nowhere rely on the bare token.

---

## PART 1 — TASK 0.6 SHIP GATE

### Verdict: **FAILED at 6176006.** Do not ship this entry tonight without the fix in `20260727c-1`.

The commit is **not** landed. The failing case is reproduced below at N=4, deterministic, at full scale, on the real code path.

### 0. Equivalence precondition — CONFIRMED

`myalgorithm.py` is byte-identical across all three:

```
6176006:ogc2026/baseline/sub/myalgorithm.py  c55af48315df672b23389063be096f4c82a764da9dd793988996d6f52665d8e6  22036 B
b8f8d83:ogc2026/baseline/sub/myalgorithm.py  c55af483…  (git diff 6176006 b8f8d83 -- <path> is empty)
on-disk  /…/sub/myalgorithm.py               c55af483…  22036 B
```

Everything below therefore verdicts 6176006 and HEAD simultaneously.

**Immediately relevant:** `c55af483` is the *same hash the 07-27 cold follow-up already flagged* when it raised F25(ladder). The fix package was never re-cut after that finding. F25(ladder) was not in tom's fix list, and the bytes confirm it was not silently fixed either.

### 1. Entry-level 60 s smokes — PASS (with one gap)

| instance | feasible | wall | wall/60 | < 0.9·t? | objective | crash | None |
|---|---|---|---|---|---|---|---|
| prob_1 | **True** | 43.519 s | 0.725 | yes | 1,499 (z1=0, z2=157, z3=2) | none | no |
| prob_38 | **True** | 49.974 s | 0.833 | yes | 72,098,620 (z1=5374, z2=4539, z3=1460) | none | no |

Both pass the stated criteria. **Gap, stated because it matters:** on prob_38 the hedge *answered* (wall 49.97 s vs a hard wall at ~58.5 s), so **the kill path was never exercised by this smoke**. The smoke does not evidence the kill path. Section 3 forces it, and it fails.

### 2. `python -m solver._parity_test` — PASS on soundness, but the harness itself is broken by the migration

Invoked exactly as commanded from `sub/`, it does not run:

```
FileNotFoundError: '/…/OGC_2026/ogc2026/train/prob_1.json'
```

`solver/_parity_test.py:40` computes `root = Path(__file__).resolve().parents[3]`. Pre-migration that resolved to the repo root; the `baseline/sub/` move inserted one level, so it now resolves to `ogc2026/`. It needs `parents[4]`. **This is `20260727c-5`.**

Run with the explicit path argument the signature already supports:

| instance | soundness violations | engine-accept trials | conservative over-rejects | result |
|---|---|---|---|---|
| prob_1 | **0** | 3,709 | 64 | PARITY: PASS |
| prob_38 | **0** | 3,381 | 32 | PARITY: PASS |

**0 violations, as required.** The separate-name emit module does not interfere: `solver/emit.py` imports only `__future__` and `collections.defaultdict` (verified from source, not memory), so loading it as `_ogc_emit` creates an independent module with no package side effects, and the package path still imports and runs cleanly under the parity harness.

`_parity_test.py` is excluded from the submission zip, so `20260727c-5` is a **P1 tooling regression, not a −1**: it silently disables a soundness gate that the manual treats as a kill criterion. A future session running the documented command gets a traceback, and the honest failure mode is that someone reads the traceback as "test broken, skip it."

### 3. Full-scale forced kill — **FAILED. This is the ship gate.**

Method: real `_run_legacy_hard_walled`, real forked child, real `os.killpg` SIGKILL, `tl=60`, entry called through `myalgorithm.algorithm`. Line 1 forced dead by patching `solver.api.solve` to raise; hedge forced to hang by patching `legacy_entry.algorithm` in the parent before fork (the child's `import legacy_entry` is then a `sys.modules` hit). Three reps in `pure` mode observe **only the return value** — no `myalgorithm` internals touched — so the primary result is instrument-free. A fourth `instr` rep adds pass-through wrappers for diagnosis only.

| instance | n / bays | est_audit | gate needs | measured drain | remaining at gate | serial rung fired | returned | feasible | wall |
|---|---|---|---|---|---|---|---|---|---|
| **prob_38** rep1 | 250/3 | 0.2083 | > 1.0167 | — | 0.979 | — | `{"operations": {}}` | **False** | 59.021 s |
| **prob_38** rep2 | 250/3 | 0.2083 | > 1.0167 | — | 0.976 | — | `{"operations": {}}` | **False** | 59.024 s |
| **prob_38** rep3 | 250/3 | 0.2083 | > 1.0167 | — | 0.979 | — | `{"operations": {}}` | **False** | 59.021 s |
| **prob_38** instr | 250/3 | 0.2083 | > 1.0167 | 0.522 s | 0.978 | **NO** | `{"operations": {}}` | **False** | 59.022 s |
| prob_1 instr | 100/2 | 0.0500 | > 0.7000 | 0.526 s | 0.974 | yes (0.028 s) | 200 ops | True (obj 5.50e8) | 59.074 s |
| prob_20 instr | 300/5 | 0.1800 | > 0.9600 | 0.525 s | 0.975 | yes (0.064 s) | 600 ops | True (obj 1.77e9) | 59.114 s |

**F19 (cost-based gate): CONFIRMED landed.** The kill-drain lands the entry at R ≈ 0.975 s and the *hedge* audit gate `_affordable(1)` (needs > est + 0.6 = 0.808 s on prob_38) would now pass. F19's specific defect is fixed.

**F20 (tri-state audit): CONFIRMED landed** by source review — `_audit` returns three statuses, `_RANK_AUDIT_ERROR = 2 > _RANK_REJECTED = 1`, and the crash branch is unreachable from the infeasible branch. tom's 14/14 forced-path matrix covers this and I found no counter-path.

**F24 (statistic-based reserve): CONFIRMED landed in mechanism, but see `20260727c-3`** — the statistic is real and survives a line-1 collapse, which was the point. The *rescue* it was supposed to enable does not.

**F21/F22 (terminal rung): REFUTED at 6176006.** The rung exists and is correct — it fires on prob_1 and prob_20 and produces audited-feasible solutions in 28–64 ms. It is **switched off on prob_38**, which is exactly the dense class F21 named as the compounding-failure instance and exactly the class the hedge exists for. The measured result on the F21 path is `{"operations": {}}`, `feasible=False`: **a certain −1, with the reserve unspent** — the identical outcome F21 reported, now with a serial constructor sitting one branch away, unreached.

---

### `20260727c-1` — **−1 RISK, CONFIRMED (forced, N=4, deterministic).** The terminal rung is disabled precisely on the dense class it was built for. F25(ladder) is unfixed at 6176006.

This is the ship gate and the pre-registered prediction P1 (registered before the runs; see scoring below).

Arithmetic, with `d` = measured kill drain and `e` = `est_audit`:

```
tail_reserve  R = max(1.5, 3e + 0.6)                 # myalgorithm.py:449-450
remaining at the terminal gate ≈ R − d
gate requires   R − d  >  2e + 0.6                   # _affordable(2), myalgorithm.py:397,470
```

Solving both branches at the measured `d = 0.522 s`:

- `e < 0.30` (reserve at its 1.5 s floor): rung fires iff `e < (0.9 − d)/2 = 0.189`
- `e ≥ 0.30` (adaptive term engaged): rung fires iff `e > d = 0.522`

**Dead band: `e ∈ [0.189, 0.522]`, i.e. `n²/n_bays ∈ [18,900, 52,200]`.** This is not a knife edge; it is a 33,000-wide interval on the instance statistic, and it sits directly on top of the largest train instances:

| status | instances | n / bays | n²/n_bays | est_audit |
|---|---|---|---|---|
| **DEAD** | prob_17, 18, 19 | 300/4 | 22,500 | 0.2250 |
| **DEAD** | prob_37, 38, 39 | 250/3 | 20,833 | 0.2083 |
| ALIVE, margin 0.015 s | prob_20 | 300/5 | 18,000 | 0.1800 |
| ALIVE | 33 others | — | ≤ 15,625 | ≤ 0.1562 |

**6/40 train instances lose the terminal rung on the solver-dead + hedge-killed path.** prob_20 clears by **15 ms** and flips into the band whenever `d ≥ 0.540 s`; M2's own measured drain range tops out at **0.537 s**. Call it **7/40 at risk**, and note the hidden set is not train.

**Mechanism — the `0.6 s` kill-drain margin is charged twice.** `_KILL_DRAIN_MARGIN_S` is included in `tail_reserve` *before* the hedge launches, correctly reserving for a drain that has not happened yet. It is then included again in `_affordable(2)` *after* the kill has already been paid, reserving for a second drain that can never occur — the hedge is already reaped and nothing downstream can be SIGKILLed. The entry demands `2e + 0.6` from a pot of `1.5 − 0.522`, so `0.6 s` of the 1.5 s reserve is spent twice on the same event. This is precisely the repair the 07-27 addendum specified ("model pre-hedge and post-kill reserve separately") and it was not made.

**Acceptance test for the fix** (unchanged from the addendum, now with numbers): forced `solver raises + hedge SIGKILL` at `tl=60` on **prob_38** must return an audited-feasible dict with 500 ops. Also test prob_17 and prob_20 — prob_17 is the deepest point in the band and prob_20 is the boundary. Scratch harness: `scratchpad/rex06_forcedkill.py` runs it in one command.

---

### 4. Standing lens (F19/F24 class): safety machinery calibrated by measurements that vanish when load-bearing

Two hits. Both are the reason `20260727c-1` exists.

### `20260727c-2` — **SOUNDNESS, confirmed (mechanism forced).** Two safety constants each carry two opposite-signed safety roles, so "conservative" is undefined for them.

- **`_AUDIT_COST_COEFF_S = 1.0e-5`** is documented as conservative because it is the swap-inflated fit. That is true where `est_audit` sizes the **reserve** — bigger estimate, bigger reserve, safer. It is **false** where the same `est_audit` sizes the **gate**: a bigger estimate makes `_affordable(n)` more restrictive, so the entry refuses work it can afford. That is the F19 failure shape, re-introduced through the constant that was supposed to fix it. Concretely: prob_38's audit really costs **0.172–0.221 s** (M1) and the rung's build+audit really costs **≤ 0.169 s** (M6), yet the gate demands **1.0167 s** and refuses. The entry declines a 0.2 s job with 0.98 s in hand.
- **`_KILL_DRAIN_MARGIN_S = 0.6`** is conservative in `tail_reserve` (must cover a future drain) and anti-conservative in `_affordable` (charges for a drain already paid). Same constant, opposite signs.

A single constant cannot be safety-calibrated in both directions. Reserve-sizing and gate-sizing need separate constants derived from separate measurements, and the gate constant must be calibrated *downward*-conservative (under-estimate the cost, so you attempt the audit) while the reserve constant is calibrated upward.

### `20260727c-3` — **SOUNDNESS, latent.** F24's own fix reproduces F24's shape: the only escape from the dead band is a measurement that is destroyed on the path where it is load-bearing.

`est_audit` is floored upward by any real audit: `est_audit = max(est_audit, dt)` (line 415). On a slow 4-core server a real line-1 audit of prob_38 could measure `dt ≈ 0.6 s`, which pushes `e > d` and lands the entry in the *upper* alive region — the rung would fire. So the band **is** escapable, by measurement.

But `_offer` only runs `_audit` when line 1 hands back a non-empty dict. On the F21 path — line 1 raises, returns `None`, or returns `{"operations": {}}` — `_offer` returns before any audit, **no measurement is ever taken**, and `est_audit` stays pinned at the statistic 0.2083, squarely inside the dead band. The escape hatch is nailed shut on exactly the path that needs it, which is the sentence F24 was written to retire.

**Missing measurement (named, per protocol):** the real distribution of `dt` for a *successful* line-1 audit on the eval server's hardware. If it clusters above 0.522 s the band shrinks on every path where line 1 survives — and stays fully open on every path where it does not. Not measured here; this box is faster than the target, which biases `dt` down, i.e. toward the band.

### `20260727c-6` — **−1 RISK, latent (mechanism measured, server reachability not).** The kill path runs to 0.984–0.985 × the raw timelimit with no safety factor applied anywhere.

All three forced-kill runs walled at **59.02–59.11 s of a raw 60 s limit**. `_remaining()` uses the **raw** `timelimit`; CLAUDE.md rule 5 sets the effective budget at `timelimit·0.93 − 1.0 = 54.8 s` at t=60, and every other component in the tree honours it. The parent ladder does not. `hard_wall = _remaining() − 1.5` puts the hedge kill at 58.5 s by construction, so this is the designed behaviour of the kill path, not an overshoot.

On this box that leaves 0.9 s. On a 4-core eval server, any fixed cost in the reap-and-return sequence that inflates — pipe teardown, process reaping under load, interpreter shutdown — comes straight out of that 0.9 s and the entry overruns the raw limit by itself. **Missing measurement:** the same forced-kill sequence on the 0.9 parity rig. This should be a named row in that gauntlet, because it is unobservable from any normal run — the smokes in §1 finish at 43–50 s and show nothing.

Note this interacts with `20260727c-1` in the worst way: the fix for `20260727c-1` must give the terminal rung *more* time, and there is 0.9 s of raw budget left to give it. The right fix reclaims the double-charged 0.6 s rather than extending the wall.

### 5. Stale-zip audit — **`sub/submission_20260727-1400_00437ce.zip` is MISLABELED. Payload is CURRENT.**

| artifact | sha256 of `myalgorithm.py` | bytes | has `_serial_construction` |
|---|---|---|---|
| inside the zip | `c55af483…` | 22,036 | yes |
| `6176006:sub/myalgorithm.py` | `c55af483…` | 22,036 | yes |
| `00437ce:baseline/myalgorithm.py` | `1cdc728f…` | 10,833 | no |

Full-tree `diff -rq` of the unzipped payload against `git archive 6176006 ogc2026/baseline/sub`: **byte-identical on all 38 shipped files.** The only differences are three files absent from the zip — `make_submission.sh`, `solver/_parity_test.py`, `solver/_smoke_test.py` — all three intentionally excluded by the builder's own `-x` rules and file list. `00437ce` has no `sub/` tree at all.

**Verdict: not stale — mislabeled.** The zip contains the 6176006 fix package under a filename claiming an unrelated commit whose entry point is a different 10,833-byte file.

### `20260727c-4` — **P1 provenance regression.** `make_submission.sh` stamps a commit hash onto a zip built from the working tree, with no dirty check.

```bash
REV="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
OUT="submission_${STAMP}_${REV}.zip"
```

At 14:00 on 07-27, HEAD was `00437ce` while `baseline/sub/` was entirely untracked. The builder zipped uncommitted code and labelled it with a commit that did not contain it. This is the stale-zip class in mirror image, and the mirror is not benign: the same line produces a zip labelled with a *new* hash containing *old* code whenever the tree is behind, which is the −1-adjacent direction. Already scoped as task **2.1**; this pass supplies the concrete instance and the exact line. Minimum fix: fail on a dirty tree for any path inside the zip, or name the artifact by a content hash rather than a commit hash.

Practical note: because the payload is current, **this particular zip is not dangerous — it is simply not evidence of anything.** Tonight's build is fresh regardless. The finding is about the builder, not the file.

### 6. Part 1 verdict table

| # | Claim under test | Verdict | Number |
|---|---|---|---|
| 0 | 6176006's `myalgorithm.py` == HEAD's == on-disk | **CONFIRMED** | sha256 `c55af483…`, 22,036 B, three-way identical |
| 1 | Entry-level 60 s smokes pass on prob_1 and prob_38 | **CONFIRMED** | feasible 2/2; wall 43.52 s (0.725·t) and 49.97 s (0.833·t); no crash, no None |
| 1b | The hedge kill path forfeits cleanly on prob_38 | **NOT EXERCISED by the smoke** — forced separately, see 3 | hedge answered at 49.97 s vs 58.5 s wall |
| 2 | `python -m solver._parity_test` → 0 violations | **HOLDS-WITH-CAVEAT** | 0 violations on prob_1 and prob_38 — but the documented invocation crashes (`20260727c-5`); required an explicit path argument |
| 2b | The file-loaded emit module does not interfere | **CONFIRMED** | `emit.py` imports only `__future__`, `collections`; package path unaffected; parity PASS both instances |
| 3a | F19 cost-based gate lands | **CONFIRMED** | hedge audit affordable at R = 0.975 s (needs 0.808 s on prob_38) |
| 3b | F20 tri-state audit lands | **CONFIRMED** | source; `_RANK_AUDIT_ERROR=2 > _RANK_REJECTED=1`; no counter-path found |
| 3c | F24 statistic-based reserve lands | **HOLDS-WITH-CAVEAT** | statistic survives line-1 collapse as designed; the rescue it enables does not (`20260727c-3`) |
| 3d | **F21/F22 terminal rung returns an audited feasible construction inside the reserve on solver-dead + hedge-killed** | **REFUTED** | prob_38 4/4 reps: `{"operations": {}}`, `feasible=False`, rung never called, 0.978 s of reserve unspent |
| 4 | No safety constant is calibrated by a measurement that vanishes when load-bearing | **REFUTED** | `20260727c-2` (two constants, opposite-signed roles), `20260727c-3` (escape depends on a vanishing `dt`) |
| 5 | The pre-built zip matches its claimed hash | **REFUTED** | payload == 6176006 (38/38 byte-identical); name claims 00437ce, a different entry point (`20260727c-4`) |

**Task 0.6 verdict: FAILED at 6176006.** The commit stays `UNVERIFIED` / committed-not-landed. Blocking item is `20260727c-1` alone; `20260727c-4`/`-5` are P1 process/tooling and do not by themselves block a fresh build.

**Recommended minimal unblock** (tom, one commit, rex-verified at its hash): stop charging `_KILL_DRAIN_MARGIN_S` in the post-kill terminal-rung gate. Gate the rung on build + audit + a small final slack only. That single change moves prob_38's requirement from 1.0167 s to ~0.42 s against 0.978 s available, clears all 6 dead-band instances, and costs nothing on the 34 alive ones. It does not touch the hedge's hard wall, so the `1a02fb2` bit-identity claim in the header survives.

---

## PART 2 — D2 PREDICTION SCORING

**Input:** `ogc2026/baseline/results/2026-07-28_d2_screening_sweep.{md,csv}`, 90 rows. Read ordinally per eva's contention caveat (load spiked to 11.38 mid-run). Scored from the CSV directly.

### Bucket A (prob_1 / 2 / 8) — **CONFIRMED, 3/3 on all three sub-claims**

| instance | obj base | obj cong | Δ | stop base | stop cong | wall base → cong |
|---|---|---|---|---|---|---|
| prob_1 | 1,499 | 1,499 | **exact tie** | `assignment_lb_reached` | `master_bound_closed` | 0.806 → 1.155 s (**+43.3 %**) |
| prob_2 | 3,690 | 3,690 | **exact tie** | `assignment_lb_reached` | `master_bound_closed` | 0.840 → 0.932 s (**+11.0 %**) |
| prob_8 | 11,252 | 11,252 | **exact tie** | `assignment_lb_reached` | `master_bound_closed` | 2.257 → 2.381 s (**+5.5 %**) |

- *Objective ties*: **CONFIRMED**, exact on 3/3 (identical z1/z2/z3 as well).
- *`assignment_lb_reached` absent under the arm*: **CONFIRMED, and stronger than registered** — across **all 88 rows**, `assignment_lb_reached` appears exactly three times, all baseline. The arm never earns this certificate on any instance measured.
- *Wall rising*: **CONFIRMED**, 3/3, monotone.

**Reading.** The arm trades a genuine optimality certificate for a weaker stop reason, pays +5.5 % to +43.3 % wall, and returns a bit-identical objective. Pure cost. F25(cert) **CONFIRMED as a mechanism**, with the caveat that at t=60 on these three the loss is free in score terms; the residual risk is larger instances where `master_bound_closed` arrives late and the early-stop budget donation to the hedge is lost.

### Bucket D/E (prob_3–20, 22) — **CONFIRMED-WITH-CAVEAT.** The rescue premise is CONFIRMED, and the one loop-dead row blows up.

Unconditional: **16/19 within ±2 %** (15 exact ties). Breaches: prob_19 −3.26 %, **prob_20 +57.80 %**, prob_22 −7.82 %.

| loop state under the arm | instances | Δ outcome |
|---|---|---|
| **active** (6–40 iterations) | 18 of 19 | 16 within ±2 % (15 exact ties); prob_19 −3.26 %, prob_22 −7.82 % (1 iteration) |
| **dead** (0 iterations) | 1 of 19 — **prob_20** | **+57.80 %**, deterministic across N=3 |

Where the loop runs, the arm is neutralised to an exact tie 15/18; where it does not, the arm's assignment ships unmediated and costs 57.8 %. At-risk naming: prob_20 → **hit** (worst row of the sweep); prob_10 → miss (exact tie, loop active). Two unnamed breaches (prob_19, prob_22). Correction to carry: key buckets on `lbbd_iters > 0`, not instance lists.

### `20260727c-8` — **correction to REMAINING_TASKS 0.4d.** "LBBD loop inert on 74/74 rows" is scope-limited to the gate-panel mass tail.

D2 shows `lbbd_iters` of 6–40 on 18 of 19 Bucket D/E instances. Accurate statement: **the loop runs frequently on prob_3–19 and is inert on the prob_21–40 mass tail at every timelimit tested.** Whether it *helps* where it runs is unmeasured (15 of those rows tie exactly both arms).

### Confound detectors prob_23 / prob_29 — **INCONCLUSIVE. The detector is unsound as designed; retired.**

Measured: prob_23 +5.15 %, prob_29 +8.67 % — both N=1, not established (prob_14's 10.41 % N=1 delta dissolved at N=3 in this same table). More importantly: the seed pass ties bit-for-bit on both (detector premise holds at the seed), but the arms **diverge downstream** — prob_23's baseline full pass resolves the master (OPTIMAL) while congestion's never solves it; prob_29's congestion full pass aborts. A delta on these rows is fully explained by full-pass *path* divergence, zero oracle-strength content. **`20260727c-7`: F29's detector design is REFUTED as an instrument** — replace, don't scope down: a valid oracle-strength test compares the same assignment through two oracle strengths (task 1.1's A/B), not two arms through one pipeline.

**prob_23's non-tracing delta** (eva's observability gap: `info["passes"]` seed+repair entries never log an objective) is confirmed from the CSV. One-line logging fix (task 0.4b-i); currently blocks causal attribution on an unknown number of rows.

### Effect on ◆0.4 (no-promote) — **UNCHANGED. D2 strengthens it.**

- prob_20 +57.80 %, deterministic both arms, mechanism identified: the arm displaces a solved master (baseline full pass = OPTIMAL → 574,498) and loses by 58 %.
- Bucket A: certificate lost, wall up, objective identical — pure cost.
- Bidirectionality confirmed at N=3 both directions (prob_36 −48.28 %, prob_25 −18.08 %, prob_30 +10.98 %, prob_20 +57.80 %), no predictor.

### Effect on the hybrid candidate — **weakened, not helped.**

Partition of the 34 instances on whether the arm displaces a *solved* master:

**Group A — hybrid reverts to master, does NOT inherit the delta (n = 23):** includes prob_20's +57.80 % — the sweep's worst row is not the hybrid's problem.

**Group B — no solved master anywhere; hybrid ≡ arm (n = 11):** prob_25 −18.08, prob_28 −3.49, prob_29 +8.67, prob_30 **+10.98**, prob_32 −0.27, prob_33 +2.70, prob_34 −1.23, prob_35 +3.93, prob_36 **−48.28**, prob_37 −8.18, prob_39 +0.48.

Beyond ±2 %: 4 wins / 4 losses. Magnitude favours the hybrid only via prob_36 (−48.28), which is the noisiest row eva measured (baseline spread 9.4 % across its own reps, sampled during the load-11.38 spike). **Excluding prob_36: −13.1 pp of wins vs +26.3 pp of losses — net unfavourable.** The hybrid stays gated; D3 matters more now. **HYPOTHESIS:** prob_36's full-pass skip (`budget 5.5–6.1 s < expected 13.1–17.1 s`) likely flips to Group A at t=300, evaporating the hybrid's best row — D3 should spend a row on prob_36 rather than prob_26.

### Prediction scorecard (Part 1, pre-registered)

| # | prediction | outcome | score |
|---|---|---|---|
| P1 | prob_38: rung SKIPPED, `{"operations": {}}`, n_ops=0 | exactly that, 4/4, wall 59.02 s | **CONFIRMED** |
| P2 | prob_1: rung FIRES, feasible, 200 ops, obj in M6 band | fired 0.028 s, obj 5.50e8, in band | **CONFIRMED** |
| P3 | prob_20: MARGINAL, mostly fires | fired, cleared by 0.015 s | **CONFIRMED** |

Part 2: Bucket A **CONFIRMED** (3/3 × 3); Bucket D/E **CONFIRMED-WITH-CAVEAT**; confound detectors **INCONCLUSIVE, instrument REFUTED** (`20260727c-7`).

---

## What would beat this?

**Measured:** an entry whose terminal rung actually fires — ours is correct, cheap (28–64 ms), and unreachable on 6/40 train instances; a naive always-on serial fallback strictly dominates us on the dense tail at zero cost. Worse than F21's position, because it looks fixed. **Measured:** an entry that does not run to 0.985 × its raw timelimit on its failure path. **HYPOTHESIS (unmeasured):** an entry that spends the hedge's budget on the solver (solver ≥ legacy on all 40 train at v0.4; solver-only at t=60 not measured). **HYPOTHESIS:** if D3 confirms the t=300 reversal generalises, the F17 family is a t=60 artifact and the hybrid's Group-B advantage disappears with prob_36.

## What makes this −1 on a hidden instance?

**Measured, not hypothetical.** Dense enough that the seed pass cannot bank an audited incumbent in its 0.55·t slice → line 1 dead + hedge SIGKILLed → drain lands the entry at R ≈ 0.975 s → terminal gate demands 1.0167 s → `{"operations": {}}` at 59.02 s. Forced at full scale on prob_38, 4/4 deterministic. Any hidden instance with `n²/n_bays ∈ [18,900, 52,200]` (≈ n 250–300 in 3–5 bays, the most common large shape) is in the band; prob_20's shape flips in if the drain reaches 0.540 s (measured up to 0.537 s). Latent second route: the kill path's 0.9 s raw-budget slack on a slower server (`20260727c-6`). Latent third: the band's width on the eval server depends on a `dt` never measured there (`20260727c-3`).

---

## Files

- Progress journal: scratchpad `rex06_journal.txt` (12 entries)
- Forced-kill harness (acceptance test for `20260727c-1`): scratchpad `rex06_forcedkill.py`
- Smoke harness / logs: scratchpad `rex06_smoke.py`, `rex06_smokes.log`, `rex06_parity.log`
- Unzipped candidate for the hash audit: scratchpad `zipx/`
- Broken harness: `sub/solver/_parity_test.py:40` · Mislabeled artifact: `sub/submission_20260727-1400_00437ce.zip` · Builder needing dirty check: `sub/make_submission.sh`

No file under `solver/`, `alns/`, `myalgorithm.py`, `legacy_entry.py`, `baseline_greedy.py`, `utils.py`, or `results/` was modified by rex.

---

*Persisted verbatim by the architect session on rex's behalf, 2026-07-27 (KST). Task 0.6: FAILED at 6176006; fix in flight.*
