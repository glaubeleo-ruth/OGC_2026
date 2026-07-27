# BLINDSPOT PASS 2026-07-27d — rung fix landing (re-verify of 6978ad4)

**Author:** rex · **Pass-local ID prefix:** `20260727d-N` · **Budget:** ~25 min
**Numbering note:** pass-local IDs only. Canonical F-numbers are assigned at fold time, by discussion (rule adopted 2026-07-28 after the F25–F28 collision). Earlier docs that self-assign F-numbers predate this rule.

## VERDICT (up front)

- **6978ad4 — LANDED.** Converts committed → landed. The gauntlet is unblocked from my side.
- **45f7771 — PASSES as tooling.** `_train_dir()` walk-up is correct, `_parity_test.py` is `-x`-excluded from the zip (`make_submission.sh:23`), no shipped-artifact byte changes; the documented invocation now runs and returns 0 violations.

No new finding fires. Two latent items recorded (`20260727d-1`, `20260727d-2`), neither a regression, neither blocking.

## 0. Snapshot / tree declaration

| item | value |
|---|---|
| repo HEAD at pass start | `45f7771` |
| target | `6978ad4` = `HEAD~1` |
| `git diff 6978ad4..HEAD` | **only** `ogc2026/baseline/sub/solver/_parity_test.py` (+21/−2) |
| `git status --porcelain ogc2026/baseline/sub/` | **clean** |
| **tree measured** | `ogc2026/baseline/sub/` (the 2026-07-28 canonical tree) |

Because the only delta from `6978ad4` to `HEAD` is a file excluded from the submission zip, **the `myalgorithm.py` on disk that I executed IS `6978ad4`'s** — function-level sha confirms it. Every runtime number below is at-hash. Out of scope: `alns/`, LBBD internals, F17 arm, objective quality, the D2 hybrid question.

Instrument caveat: machine free, no contention. Solver-time measurements taken serially, one process at a time, `conda run -n ogc2026`, `PYTHONPATH=<repo>/ogc2026/baseline/sub`, cwd `sub/`.

## 1. Claim 1 — gate no longer charges the drain; reserve family untouched · **CONFIRMED**

Mechanical check: AST-parsed both revisions, stripped docstrings/comments, `ast.unparse`d, diffed. **The entire executable delta `6176006 → 6978ad4` is −4/+10 lines:**

```
+_RUNG_BUILD_EQUIV = 1.0
+_RUNG_RETURN_SLACK_S = 0.05
+    def _rung_affordable(n_audits):
+        return _remaining() > n_audits * est_audit + _RUNG_RETURN_SLACK_S
-    def _offer(sol):                        +    def _offer(sol, audit_gate=None):
-        if _affordable(1):                  +        gate = _affordable if audit_gate is None else audit_gate
                                             +        if gate(1):
-        if best_sol is None and _affordable(2):
-            _offer(_serial_construction(prob_info, keep_going=lambda: _affordable(1)))
+        if best_sol is None and _rung_affordable(_RUNG_BUILD_EQUIV + 1.0):
+            _offer(_serial_construction(prob_info, keep_going=lambda: _rung_affordable(1)), audit_gate=_rung_affordable)
```

Nothing else executable changed. `_KILL_DRAIN_MARGIN_S = 0.6`, `_RESERVE_FLOOR_S = 1.5`, the `tail_reserve = max(_RESERVE_FLOOR_S, 3.0*est_audit + _KILL_DRAIN_MARGIN_S)` expression, and `_affordable`'s body are byte-identical. Reserve family **unchanged**, as claimed.

**20260727c-2 discipline — HOLDS-WITH-CAVEAT.** Gate constants round down, reserve constants round up, and the two are separate objects. But the discipline is not yet fully realised: **`_KILL_DRAIN_MARGIN_S` still serves both a reserve (`tail_reserve`) and a gate (`_affordable`).** Two `_affordable` call sites:

- L504, line-1 solver dict — drain is genuinely a *future* cost. Legitimate.
- L526, the hedge's *own* dict — `_run_legacy_hard_walled` has already returned and its `finally` has already killed + reaped, so the drain is already resolved. **The identical already-paid-drain shape as 20260727c-1, one rung higher.**

Attacked L526 for reachability. Gate fires iff `tail_reserve(e) − r > e + 0.6`, where `r` is the recv+join residue after `poll()` succeeds. Minimum slack over `e ∈ [0, 3]` is **+0.600 s exactly** (at `e = 0.30`, the kink of the `max`). If the child was killed, `leg is None` and `_offer` is never called at all.

> **`20260727d-1` · LATENT (not a regression, not blocking).** `_KILL_DRAIN_MARGIN_S` is still a single constant in both a reserve and a gate role. The gate role at L526 double-charges an already-paid drain. **Unreachable-to-harm at current sizing** (proved: ≥0.600 s slack for all `e ≥ 0`). Becomes reachable only if `tail_reserve` is ever reduced below `est_audit + 0.6 + d`. Anyone who touches `_RESERVE_FLOOR_S` downward must re-run this inequality.

## 2. Claim 2 — the `_offer(audit_gate=...)` contract change · **CONFIRMED, attacked three ways**

**(a) Call-site census.** Exactly three `_offer` call sites: L504 (solver), L526 (hedge), L543 (rung). Only the rung passes `audit_gate`. Default `None → _affordable`. **No other path reaches the weaker gate.**

**(b) A weaker gate cannot sneak an unaudited dict through — by construction.** `best_sol` is assigned only inside `if status == _AUDIT_FEASIBLE`, which requires `_audit()` → `utils.check_feasibility` returning feasible *and* a non-`None` objective. If the gate is False, the branch taken is `rank = _RANK_UNAUDITED`, which can only reach `fallback` — never `best_sol`. Relaxing a gate strictly *increases* the number of audits. **The direction of this kwarg is the soundness-safe direction.** Residual exposure is wall-clock, not correctness.

**(c) The audit is on the exact returned dict.** `_audit(prob_info, sol)` receives the same object bound to `best_sol` and returned by the ladder. No copy, no re-serialisation, no mutation between audit and return. Confirmed end-to-end: entry-level `check_feasibility` in the harness re-derives `feasible=True` and the same objective on the returned object.

**(d) Bonus invariant, unclaimed by tom.** The rung audits its own output iff build cost `b < est_audit e` — under BOTH gates (the slack constant cancels):
- new: entry `rem₀ > 2e+0.05`, audit `rem₀−b > e+0.05` ⟹ refused iff `b ≥ e`
- old: entry `rem₀ > 2e+0.6`, audit `rem₀−b > e+0.6` ⟹ refused iff `b ≥ e`

**The fix did not widen the unaudited-return window.** Measured `b < e` on 4/4 rows (prob_1 .028<.050, prob_38 .031<.208, prob_17 .053<.225, prob_20 .066<.180).

## 3. Claim 3 — independent acceptance re-run · **CONFIRMED, 5/5 pure + 2/2 instrumented**

Harness: `scratchpad/rex06_forcedkill.py`, unmodified. Real fork, real `killpg` SIGKILL, `tl=60`, line 1 forced dead, hedge forced to hang. Pure mode = return-value-only (verdict mode).

| prob | mode | line-1 | n/bays | est_audit | OLD gate needed | NEW gate needed | remaining post-kill | feasible | ops | objective | wall |
|---|---|---|---|---|---|---|---|---|---|---|---|
| prob_38 | **pure** | raise | 250/3 | 0.2083 | 1.0167 | **0.4667** | 0.984 | **True** | 500 | 2.9222e9 | 59.093 |
| prob_17 | **pure** | raise | 300/4 | 0.2250 | 1.0500 | **0.5000** | 0.982 | **True** | 600 | 8.6271e8 | 59.136 |
| prob_20 | **pure** | raise | 300/5 | 0.1800 | 0.9600 | **0.4100** | 0.983 | **True** | 600 | 1.7734e9 | 59.115 |
| prob_38 | **pure** | **none** | 250/3 | 0.2083 | 1.0167 | **0.4667** | 0.984 | **True** | 500 | 2.9222e9 | 59.098 |
| prob_17 | **pure** | **none** | 300/4 | 0.2250 | 1.0500 | **0.5000** | 0.983 | **True** | 600 | 8.6271e8 | 59.080 |
| prob_38 | instr | raise | 250/3 | — | — | — | drain **0.516** | True | 500 | 2.9222e9 | 59.071 |
| prob_17 | instr | raise | 300/4 | — | — | — | drain **0.518** | True | 600 | 8.6271e8 | 59.099 |

Instrumented diagnosis: `serial_called=True`, `serial_none=False`, `hedge_result_none=True` (child really killed), `hard_wall_arg=58.500`, `legacy_tl_arg=49.725`, `serial_build_s = 0.031 / 0.053`.

**Deficit → surplus.** prob_38: short 0.033 s → clears by **+0.517 s**. prob_17: short 0.068 s → clears by **+0.482 s**. Surplus ≈17× the observed drain spread (0.516–0.537, range 0.021). N≥3 satisfied on prob_38/17; prob_20's single pure rep is adequate (largest surplus, +0.573 s).

## 4. Claim 4 — dead-band arithmetic · **CONFIRMED, band is empty**

Exact model (validated: predicts 0.978 for prob_38 at `d=0.522`; measured 0.978):

```
remaining_post_kill = tail_reserve − d,   tail_reserve = max(1.5, 3e + 0.6),   e = 1e-5·n²/n_bays
```

| gate | branch `e ≤ 0.3` | branch `e > 0.3` | band non-empty iff |
|---|---|---|---|
| OLD `> 2e+0.6` | `e ≥ (0.9−d)/2` | `e ≤ d` | always (for `d ≥ 0.3`) → `e ∈ [(0.9−d)/2, d]` |
| **NEW `> 2e+0.05`** | `e ≥ (1.45−d)/2` | `e ≤ d − 0.55` | **`d ≥ 0.85`** |

**The new dead band is EMPTY for all `e ≥ 0` whenever `d < 0.85 s`.** Worst drain ever measured (M2 + this pass): **0.537 s** → margin **0.313 s, 58% headroom**. Train census: OLD band at `d=0.522` contained 6/40 (prob_17/18/19/37/38/39); NEW band at `d=0.54` contains **0/40**.

**Precise residual risk.** The band reopens at `d ≥ 0.85 s`, first point exactly `e = 0.30` (`n²/n_bays = 30000`, the kink of the `max`). At `d=0.90`: `[27500, 34999]`; at `d=1.00`: `[22500, 44999]`. Largest train instance is prob_17 at 22,500 — **the entire train set sits below the reopening point**; a hidden instance at n=300/3 bays or n≈350/4 bays lands on `e=0.30` and would be the first casualty if the drain ever reached 0.85 s. Stated so it is not rediscovered.

## 5. Claim 5 — no-regression spot checks · **CONFIRMED, 4/4**

| check | result |
|---|---|
| entry smoke prob_1 @60 s | feasible, obj **1499**, wall **43.63 s = 0.727×t** |
| entry smoke prob_38 @60 s | feasible, obj **7.357e7**, wall **49.90 s = 0.832×t** |
| **alive path** (real solver feasible + hedge hung/SIGKILLed), prob_1 | `line1_feasible=True`, **`returned_is_line1_object=True`** (object identity), **`serial_called=False`**, obj 1499, wall 59.03 s |
| parity `python -m solver._parity_test` from `sub/` | 3709 engine-accept trials, **0 soundness violations**, PARITY: PASS |

The alive-path case is the sharp one: `id()` comparison on `solver.api.solve`'s return object — the rung did NOT fire and the returned dict is literally line 1's object. `best_sol is None` remains the sole trigger.

## 6. Claim 6 — byte identity of the hard wall · **CONFIRMED, reproduced exactly**

Function-level sha256 (AST-bounded extraction), four revisions:

| function | 1a02fb2 | 6176006 | 6978ad4 | HEAD |
|---|---|---|---|---|
| `_run_legacy_hard_walled` | `d657244ec337` 1843 B | same | same | same |
| `_fork_context` | `90ac15b71d94` 198 B | same | same | same |
| `_serial_construction` | *did not exist* | `3884a93c61dc` | same | same |
| `_audit` | *did not exist* | `d207d85144a7` | same | same |
| `_emitter` | *did not exist* | `2e8b2f44c913` | same | same |
| `_audit_cost_estimate` | *did not exist* | `e1ce74090809` | same | same |

Reproduces tom's digest to the byte. Minor wording correction (not a defect): tom's "likewise identical" alongside a 1a02fb2 comparison — those four functions did not exist at 1a02fb2 (arrived at 44d5c1e); they are identical `6176006 → HEAD`, which is the claim that matters.

## 7. Standing items — restated, not re-litigated

- **`20260727c-6` (kill path runs to ≈0.985 raw `t`).** Confirmed unchanged and structural: `hard_wall_arg = 58.500` of a raw 60 — designed behaviour. Post-fix walls 59.07–59.14 vs pre-fix 59.02–59.11; the rung costs **~+0.08 s** of tail, as tom stated. Still the largest single risk on this path under a slower server. **Named missing measurement: the forced-kill sequence on the Linux 4-core parity rig.** Tonight's gauntlet CAN capture it — but not as configured: `rig_gauntlet.sh` exercises only the natural path (prob_38 answers at 49.9 s, inside the 58.5 s wall). `rex06_forcedkill.py` must be invoked once per band instance under the same taskset + thread caps. One prob_38 run is worth more than another 40-row natural sweep.
- **`20260727c-3` (est_audit escape hatch).** Unchanged, LATENT. On the solver-dead path no real audit ever runs, so `est_audit` is the pure `1e-5·n²/n_bays` model. The new gate depends on it the same way the old one did. **Named missing measurement: real parent-audit wall vs the model above `n²/n_bays = 22500`** (the train ceiling).
- **F19/F24 standing lens — clean.** `_RUNG_BUILD_EQUIV = 1.0` is a dimensionless multiplier on the instance statistic (F24-safe — cannot be destroyed by a line-1 collapse); `_RUNG_RETURN_SLACK_S = 0.05` is a fixed floor, not fitted. **The fix does not reintroduce the F19/F24 failure shape.**

> **`20260727d-2` · MAINTENANCE HAZARD (not a finding).** `_RUNG_BUILD_EQUIV` parameterises the entry gate only; `keep_going` and the rung's audit gate hard-code `1`. The docstring's "same gate at one audit-equivalent" is true today but silently decouples if anyone re-tunes `_RUNG_BUILD_EQUIV`. Cheap to make robust later; no action needed to ship.

## 8. Pre-registration, scored publicly — **6/6**

Registered before the instr/smoke/alive/parity results landed (the five pure rows were in hand and excluded from scoring):

| ID | prediction | outcome |
|---|---|---|
| I1 | prob_38 instr: serial_called, drain ∈ [0.50,0.56], build ∈ [0.02,0.09], feasible, 500 ops | ✅ T / 0.516 / 0.031 / T / 500 |
| I2 | prob_17 instr: serial_called, drain ∈ [0.50,0.56], build ∈ [0.03,0.10], feasible, 600 ops | ✅ T / 0.518 / 0.053 / T / 600 |
| E1 | prob_1 smoke feasible, wall < 54.0 s, obj ≈1499 | ✅ 43.63 s, 1499 |
| E2 | prob_38 smoke feasible, wall < 54.0 s | ✅ 49.90 s |
| A1 | alive prob_1: returned_is_line1_object AND NOT serial_called | ✅ T / False |
| P1 | parity 0 violations, PARITY: PASS | ✅ 0 / PASS |

## 9. What would beat this? — all HYPOTHESIS unless marked MEASURED

- **MEASURED, the only thing that beats the new gate:** a kill-drain `d ≥ 0.85 s`. Worst observed 0.537 s on this machine; **unmeasured on the Linux rig** — the single number most worth capturing tonight.
- **HYPOTHESIS:** an instance where serial build cost `b` exceeds one audit-equivalent `e` → rung builds, audit refused, unaudited construction returned at `_RANK_UNAUDITED`. Measured `b/e` 0.15–0.56, no crossing on train; window exactly as wide as pre-fix (§2d).
- **HYPOTHESIS:** `check_feasibility` real cost exceeding the `1e-5·n²/n_bays` model superlinearly → audit overruns the 0.05 s slack. Would need to miss the model by ~0.9 s; no constructible regime. `20260727c-3` in a different hat.
- **HYPOTHESIS:** `os.killpg` fails and `join(2.0)` returns with the child alive → serial build against a live orphan, wall inflates. Pre-existing (byte-identical since 1a02fb2), unmeasured, out of scope.

## 10. What makes this −1 on a hidden instance?

Ranked, honestly:

1. **The 0.985·t tail on the kill path (`20260727c-6`), MEASURED at 59.07–59.14 s of a raw 60.** Largest exposure; the fix makes it ~0.08 s worse. Mechanism measured, overrun NOT reproduced → **HOLDS-WITH-CAVEAT**. Missing measurement named in §7.
2. **Drain ≥ 0.85 s on the rig** reopening the band at `n²/n_bays ≈ 30000`. MEASURED-EMPTY here; UNMEASURED on Linux.
3. **`est_audit` model error above `n²/n_bays = 22500`.** UNMEASURED — no calibration point above the train ceiling.

None introduced by `6978ad4`. It removes a **measured, deterministic, 6/40-instance certain −1** and replaces it with audited-feasible returns on 7/7 forced runs. That trade is unambiguous.

---

**Artifacts:** journal `scratchpad/rex06_journal.txt` (REX 0.7 entries S0–S10); acceptance logs `rex07_accept.log`, `rex07_accept2.log`; scripts `rex07_run.sh`, `rex07_run2.sh`, `rex07_alive.py`, `rex07_band.py`, `rex07_gatecheck.py`, `rex07_exec_delta.py`, `rex07_fnsha.py`; reused unmodified `rex06_forcedkill.py`, `rex06_smoke.py`. Tree measured: `ogc2026/baseline/sub/`.

---

*Persisted verbatim by the architect session on rex's behalf, 2026-07-27 (KST). 6978ad4 LANDED; 45f7771 passes as tooling; gauntlet unblocked.*
