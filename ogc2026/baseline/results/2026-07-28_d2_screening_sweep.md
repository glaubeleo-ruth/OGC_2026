# D2 — 34-instance screening sweep, both F17 arms (task 0.4b)

Closes rex's Buckets A and D/E (13 PENDING prediction rows) and the F29
oracle-strength confound detectors — the last of the three gates (with D1 done,
D3 pending) before any promote vote on the F17 arm family. **This report makes
no promote/reject call** — per the task brief, verdict scope is per-instance
winners + confound observations only; scoring rex's predictions CONFIRMED /
FALSIFIED is rex's job, not mine. All fields he needs are captured below.

## Stamp

- **git HEAD**: `00437cec5014ab31d576dc58558f77b5e9f28ac2` ("F17 assignment arm
  behind a flag, default baseline")
- **Tree state**: **DIRTY.** `git status --short` shows the same 2026-07-28
  `sub/` reorg as D1: `ogc2026/baseline/sub/` untracked, and
  `ogc2026/baseline/{myalgorithm.py,baseline_greedy.py,legacy_entry.py,utils.py}`
  deleted-uncommitted at the old path. **Re-verified before this run**:
  `diff` between `git show HEAD:ogc2026/baseline/solver/*.py` and the on-disk
  `ogc2026/baseline/sub/solver/{api,assignment,conductor,congestion,lbbd,
  budget,incumbent,emit}.py` is empty for every file (byte-identical,
  relocated only); same for `utils.py`. Every row below runs through
  `solver.api.solve` and `utils.check_feasibility` directly — never
  `myalgorithm.py` — so `myalgorithm.py`'s uncommitted divergence (tom's
  audit-ladder work, per the D1 note) is confirmed irrelevant to this
  measurement.
- **Entry point exercised**: `solver.api.solve(prob_info, timelimit,
  assign_arm=...)` — explicit kwarg passed positionally from the runner
  script (never `$OGC_ASSIGN_ARM`); every row's `arm_reported` column below is
  read from `info["assign_arm"]`, the flag actually recorded by the run, not
  the flag I intended to pass. Requested and reported arms matched on every
  one of the 90 rows (no silent baseline fallback).
- **timelimit**: 60s (all 34×2 screening/re-measure rows), 60s (calibration
  control, prob_5/baseline)
- **N**: 1 per (instance, arm) for the 29 non-flagged instances (screening
  grade, per task brief — this is a direction/coverage sweep, not a ship
  claim); **N=3** for the 5 instances whose |Δ| exceeded the noise band
  (prob_14, 20, 25, 30, 36); 2 calibration-control reps (start + end).
- **Date**: 2026-07-27 (run date; filename follows the task brief's requested
  `2026-07-28` stamp, matching the D1 convention)
- **Environment**: macOS (Darwin 25.5.0), 8 logical cores, no isolation
  (taskset/cpulimit) — **local-only, not gauntlet-valid.** Direction/coverage
  signal only; not admissible for a SUBMIT-ELIGIBLE or promote verdict.
- **Instrument caveat (stated up front)**: swap and load were non-trivial
  throughout, and **spiked hard mid-run** — this is worse contention than D1
  saw:
  - Start (13:18): swap 2704.81 MB / 4096 MB, load 1.58/1.72/2.45
  - After 14 calls (13:29): swap 2737.00 MB, load 2.33/2.46/2.56
  - After 32 calls (13:45): swap 2823.69 MB, load 3.00/2.91/2.95
  - After 40 calls (13:53): swap 2743.69 MB, load 1.90/2.35/2.65
  - After 56 calls (14:08): swap 2939.12 MB, load 2.20/2.37/2.57
  - After 62 calls (14:15): swap 3257.88 MB, **load 11.38/5.08/3.59** — a
    sharp spike, right before prob_35/36 ran. Both completed with normal
    walls (49.9s / 48.8–48.9s, no timeout) despite the spike — per the
    decision-asymmetry rule, a wall that stays flat despite a load spike is
    conservative-valid evidence against wall-inflation on those two rows, but
    the spike is exactly the kind of event that produces the ~14–27%
    contention swings on record, and it landed in the middle of the window
    that produced prob_36's baseline-side variance (see Bucket flags below).
  - End of screening sweep (14:24): swap 3161.81 MB, load 9.49/5.47/4.23 —
    still elevated.
  - End of re-measure phase (14:46): swap 2985.81 MB, load 2.67/2.83/3.27 —
    back to baseline-ish.
  - **Conservative reading**: take the re-measure (N=3, median) numbers over
    any single N=1 screening row wherever they disagree — this is exactly
    what happened for prob_14 (see below) and is the reason the 5-instance
    re-measure cap exists.
- **Calibration control** (prob_5 @ t=60, baseline arm): start 48.433s /
  obj=74937.0; end 50.844s / obj=75662.0. Wall drift +4.98%, objective drift
  +0.97%. Both readings stayed far under the ~110s stop threshold — machine
  judged runnable for the full session, but the objective/wall drift on this
  *single, easy* control is much tighter than what several full-tier
  instances showed under direct re-measurement (see prob_14/36 below) — the
  calibration control is not fully representative of the tail's sensitivity
  to timing.

## Runner / protocol notes

- One (instance, arm, rep) call per Bash invocation, hard external timeout
  65s (enforced by the tool's own timeout, not a `timeout` binary — none is
  installed on this box; confirmed via `which timeout gtimeout` → not found).
  Zero timeouts fired across all 90 calls.
- Runner script (never modifies solver code, reads only):
  `/private/tmp/.../scratchpad/run_one_d2.py`. Imports `solver.api` and
  `utils` directly from `ogc2026/baseline/sub/`, loads
  `../../train/prob_N.json`, calls `api.solve(prob_info, timelimit,
  assign_arm=arm)`, audits the *returned solution itself* a second time via
  `utils.check_feasibility` (independent of the store's own internal audits),
  and appends one row immediately to the scratch CSV. Every call's raw
  `info` dict (all of `info["passes"]`, `info["arm_info"]`, etc.) is also
  dumped verbatim to a per-call JSON file for provenance.
- Progress journal (append-only, every step logged):
  `/private/tmp/.../scratchpad/d2_progress_journal.txt`. Scratch CSV:
  `/private/tmp/.../scratchpad/d2_screening_scratch.csv`. Raw per-call JSON:
  `/private/tmp/.../scratchpad/d2_raw_info/`.
- **Zero −1s, zero timeouts, zero errors, zero infeasible rows** across all
  90 calls (88 screening/re-measure + 2 calibration). All feasible=True.
- Re-measure protocol: after the full 34×2 N=1 sweep, the 5 largest |Δ|
  instances (by absolute % objective delta) were re-run at 2 additional reps
  per arm (N=3 total), same protocol, sequential. Cap was 5 per the task
  brief; all other instances with a non-zero delta are listed in their own
  table below as "exceeds tighter band, not re-measured" (see Delta table).

## Per-instance objective, all 34 instances (N=1 screening; 5 flagged rows show N=3 median)

| instance | N (base/cong) | baseline obj (median) | congestion obj (median) | Δ% (cong vs base) | winner |
|---|---|---|---|---|---|
| prob_1  | 1/1 | 1,499      | 1,499      | +0.00  | TIE |
| prob_2  | 1/1 | 3,690      | 3,690      | +0.00  | TIE |
| prob_3  | 1/1 | 52,060     | 52,060     | +0.00  | TIE |
| prob_4  | 1/1 | 16,916     | 16,916     | +0.00  | TIE |
| prob_5  | 1/1 | 74,937     | 74,937     | +0.00  | TIE |
| prob_6  | 1/1 | 78,191     | 78,191     | +0.00  | TIE |
| prob_7  | 1/1 | 87,843     | 88,395     | +0.63  | baseline |
| prob_8  | 1/1 | 11,252     | 11,252     | +0.00  | TIE |
| prob_9  | 1/1 | 73,685     | 73,685     | +0.00  | TIE |
| prob_10 | 1/1 | 78,785     | 78,785     | +0.00  | TIE |
| prob_11 | 1/1 | 121,687    | 121,687    | +0.00  | TIE |
| prob_12 | 1/1 | 109,739    | 109,739    | +0.00  | TIE |
| prob_13 | 1/1 | 196,436    | 196,436    | +0.00  | TIE |
| **prob_14** | **3/3** | **255,376** (rep0=228,876; reps1-2=255,376) | **255,376** (rep0=252,700; reps1-2=255,376) | **+0.00 (median); N=1 screening row showed +10.41%** | **TIE at median — see note** |
| prob_15 | 1/1 | 60,069     | 60,069     | +0.00  | TIE |
| prob_16 | 1/1 | 73,564     | 73,564     | +0.00  | TIE |
| prob_17 | 1/1 | 61,760     | 61,760     | +0.00  | TIE |
| prob_18 | 1/1 | 86,098     | 86,098     | +0.00  | TIE |
| prob_19 | 1/1 | 81,726     | 79,063     | −3.26  | congestion |
| **prob_20** | **3/3** | **574,498 (x3, deterministic)** | **906,572 (x3, deterministic)** | **+57.80** | **baseline, large + confirmed** |
| prob_22 | 1/1 | 1,770,944  | 1,632,522  | −7.82  | congestion |
| prob_23 | 1/1 | 4,468,538  | 4,698,878  | +5.15  | baseline (F29 detector — own bucket) |
| prob_24 | 1/1 | 2,448,516  | 2,345,832  | −4.19  | congestion |
| **prob_25** | **3/3** | **546,120 (x3, deterministic)** | **447,363 (x3, deterministic)** | **−18.08** | **congestion, large + confirmed** |
| prob_28 | 1/1 | 6,205,116  | 5,988,862  | −3.49  | congestion |
| prob_29 | 1/1 | 1,375,150  | 1,494,382  | +8.67  | baseline (F29 detector — own bucket) |
| **prob_30** | **3/3** | **7,363,288 (x3, deterministic)** | **8,171,531/8,171,531/8,190,371** | **+10.98 (median)** | **baseline, confirmed** |
| prob_32 | 1/1 | 4,519,950  | 4,507,589  | −0.27  | congestion |
| prob_33 | 1/1 | 13,831,854 | 14,205,574 | +2.70  | baseline |
| prob_34 | 1/1 | 1,752,697  | 1,731,184  | −1.23  | congestion |
| prob_35 | 1/1 | 4,993,867  | 5,190,362  | +3.93  | baseline |
| **prob_36** | **3/3** | **812,284/896,066/865,899 (median 865,899)** | **447,856/447,856/449,857 (median 447,856)** | **−48.28 (median); N=1 screening row showed −44.86%** | **congestion, large + confirmed, but baseline itself is noisy on this instance (9.4% spread)** |
| prob_37 | 1/1 | 6,550,030  | 6,014,252  | −8.18  | congestion |
| prob_39 | 1/1 | 21,791,309 | 21,896,478 | +0.48  | baseline |

Strict per-instance win count (N=1 rows at face value, 5 flagged rows at
N=3 median): baseline strictly better on 8 (prob_7, 14→TIE not counted,
20, 23, 29, 30, 33, 35, 39 = 8 after excluding the corrected prob_14 tie),
congestion strictly better on 9 (prob_19, 22, 24, 25, 28, 32, 34, 36, 37),
ties on 17 (prob_1–6, 8–13, 14 [corrected], 15–18). This is a raw count for
rex's scoring convenience, **not a promote/reject signal** — see Verdict
scope below.

## Bucket A — prob_1, 2, 8 (certificate-loss prediction)

Fields rex's prediction keys on: objective tie, `assignment_lb_reached`
presence, wall.

| instance | arm | objective | stop_reason | assignment_lb | wall (s) | lbbd_iters | master_status_full |
|---|---|---|---|---|---|---|---|
| prob_1 | baseline   | 1,499  | `assignment_lb_reached` | 1499.0 | 0.806 | 0 | OPTIMAL |
| prob_1 | congestion | 1,499  | `master_bound_closed`   | 1499.0 | 1.155 | 1 | (none — arm skips master solve on the full pass) |
| prob_2 | baseline   | 3,690  | `assignment_lb_reached` | 3690.0 | 0.840 | 0 | OPTIMAL |
| prob_2 | congestion | 3,690  | `master_bound_closed`   | 3690.0 | 0.932 | 1 | (none) |
| prob_8 | baseline   | 11,252 | `assignment_lb_reached` | 11252.0 | 2.257 | 0 | OPTIMAL |
| prob_8 | congestion | 11,252 | `master_bound_closed`   | 11252.0 | 2.381 | 1 | (none) |

Raw facts, unscored: objective ties exactly on all three rows. On every one
of the three, the congestion arm's stop reason is `master_bound_closed`, and
`assignment_lb_reached` never appears under the congestion arm anywhere in
this bucket — the two stop types differ every time. Wall rises modestly
under congestion in all three (prob_1: 0.806→1.155s, +43%; prob_2:
0.840→0.932s, +11%; prob_8: 2.257→2.381s, +5.5%) but stays sub-3-second in
both arms, not into the multi-second range. `master_status_full` is only
populated under baseline (`OPTIMAL`) because the arm's full pass never
solves the master (per `api.py`'s own comment: "the master object is still
built... but is NOT solved here, so its certificate fields stay at their
'none' defaults").

## Bucket D/E at-risk — prob_10, prob_20

| instance | arm | objective | Δ% vs baseline | stop_reason | lbbd_iters | wall (s) |
|---|---|---|---|---|---|---|
| prob_10 | baseline   | 78,785  | — | NO_STOP_ENTRY | 34 | 48.425 |
| prob_10 | congestion | 78,785  | +0.00 | NO_STOP_ENTRY | 33 | 48.535 |
| prob_20 | baseline   | 574,498 (N=3, deterministic) | — | NO_STOP_ENTRY | 1 | 34.046 |
| prob_20 | congestion | 906,572 (N=3, deterministic) | **+57.80** | NO_STOP_ENTRY | 0 | 26.477 |

prob_10 ties exactly (|Δ|=0%, well inside any noise band). prob_20's delta is
large (+57.80%) and confirmed **deterministic** across N=3 (baseline
574,498/574,498/574,498; congestion 906,572/906,572/906,572 — bit-identical
across reps in both arms, so this is not measurement noise). Raw-info
inspection (both arms' `info["passes"]`, unscored, for rex):
- Baseline's seed differs from congestion's seed (baseline seed obj
  26,145,402 vs congestion seed obj 15,297,770 — congestion's seed is
  actually *better* pre-repair). Baseline's `full` pass invokes the CP-SAT
  master (`master: cpsat`, `master_status: OPTIMAL`, `master_theta: 0.0`)
  and lands at objective 574,498 directly; one `lbbd_0` iteration then runs
  and produces a *worse* proposal (698,467), which the incumbent store
  correctly rejects (best stays 574,498).
- Congestion's `full` pass never invokes the master at all
  (`assignment_source: external`, no `master_status` key present) — the
  external congestion-computed assignment is used as-is, repaired, and
  polished to objective 927,784; the eventual incumbent (906,572) is lower
  than that, meaning the improvement came from the `seed+repair` pass (whose
  audited objective is not logged in `info["passes"]` — see observability
  gap below). `lbbd_iters=0`: no `lbbd_0` entry was ever appended for this
  arm on this instance, and no `stop` entry either — the loop exited
  silently (deadline or empty-proposal path) before completing a first full
  cut→resolve→audit cycle.

## F29 oracle-strength confound detectors — prob_23, prob_29 (own bucket, excluded from headline)

| instance | arm | seed z1/z2/z3/obj | seed tie? | full z1/z2/z3/obj | full pass status | final (best_objective) | Δ% final |
|---|---|---|---|---|---|---|---|
| prob_23 | baseline   | 327→402/1010/0/5,457,788 (pre-repair seed) | — | 327/735/148/4,468,538 (assignment_source=None, master resolved) | completed | 4,468,538 | — |
| prob_23 | congestion | 402/1010/0/5,457,788 | **tie** | 351/520/332/4,829,249 (assignment_source=external, master NOT resolved) | completed | 4,698,878 | +5.15 |
| prob_29 | baseline   | 849/11828/0/11,355,201 | — | 55/4645/2093/1,375,150 (assignment_source=None) | completed | 1,375,150 | — |
| prob_29 | congestion | 849/11828/0/11,355,201 | **tie** | — | **aborted** | 1,494,382 | +8.67 |

Raw facts, unscored:
- The **seed pass ties bit-for-bit** between arms on both instances
  (identical z1/z2/z3/objective) — consistent with the premise that the
  arm's assignment equals greedy's at the seed stage on these two rows.
- On **prob_29**, congestion's `full` pass is logged as `{"aborted": True}` —
  it never completed. The final objective (1,494,382) therefore cannot come
  from `full`; it must come from `seed+repair` (the only other candidate
  pass), which is a clean, attributable explanation for that delta: a
  full-pass abort under the arm, not an assignment-quality difference at the
  seed.
- On **prob_23**, this attribution is **not clean**: congestion's `full` pass
  *did* complete (objective 4,829,249) but the final incumbent (4,698,878) is
  *lower* than that — meaning `seed+repair` beat `full` under both arms, and
  baseline's own incumbent (4,468,538) equals its `full` pass exactly (so
  baseline's provenance is unambiguous) while congestion's does not equal any
  single logged pass objective. **Root cause found: `info["passes"]`'s
  `seed+repair` entry never logs an `objective` field** (only
  `moves`/`z1_before`/`z1_after`/`polish_moves`/`feasible`) — this is an
  observability gap in `solver/api.py`'s own logging, not something touched
  or fixed in this run (eva does not modify solver code). Anyone drawing a
  provenance conclusion about the prob_23 delta from these fields alone will
  be guessing at the `seed+repair` stage; the raw JSON dumps (linked below)
  are the only artifact that could resolve it, and they don't carry the
  audited number either. **Flagging this gap explicitly** rather than
  papering over it with an inferred attribution.

## Delta table — every non-tie instance, ranked, re-measure disposition

| instance | |Δ%| (N=1 screening) | re-measured (N=3)? | disposition |
|---|---|---|---|
| prob_20 | 57.80 | **yes** | confirmed deterministic, direction/magnitude unchanged |
| prob_36 | 44.86 | **yes** | confirmed direction; magnitude shifts to 48.28% at median because baseline itself is noisy (9.4% spread across reps) |
| prob_25 | 18.08 | **yes** | confirmed deterministic, direction/magnitude unchanged |
| prob_30 | 10.98 | **yes** | confirmed deterministic (congestion has a trivial 0.23% rep-to-rep wobble), direction/magnitude unchanged |
| prob_14 | 10.41 | **yes** | **NOT confirmed** — median-of-3 verdict is a TIE (255,376 both arms); the N=1 screening row is the outlier rep (baseline rep0=228,876 vs reps1–2=255,376, i.e. baseline itself swung 10.4% between its own reps) |
| prob_29 | 8.67  | no | exceeds a tight (~5%) self-calibration band; cap reached at 5 — not re-measured. Own bucket (F29 detector) regardless. |
| prob_37 | 8.18  | no | exceeds tight band; cap reached — not re-measured |
| prob_22 | 7.82  | no | exceeds tight band; cap reached — not re-measured |
| prob_23 | 5.15  | no | exceeds tight band; cap reached — not re-measured. Own bucket (F29 detector) regardless. |
| prob_24 | 4.19  | no | exceeds tight band; cap reached — not re-measured |
| prob_35 | 3.93  | no | exceeds tight band; cap reached — not re-measured |
| prob_28 | 3.49  | no | exceeds tight band; cap reached — not re-measured |
| prob_19 | 3.26  | no | exceeds tight band; cap reached — not re-measured |
| prob_33 | 2.70  | no | at/near tight band; cap reached — not re-measured |
| prob_34 | 1.23  | no | inside the ~5% self-calibration band (own-drift measure — see calibration control, +0.97% obj / +4.98% wall) — likely noise, not re-measured |
| prob_7  | 0.63  | no | inside self-calibration band — likely noise |
| prob_39 | 0.48  | no | inside self-calibration band — likely noise |
| prob_32 | 0.27  | no | inside self-calibration band — likely noise |

Band used: task brief's ~14% historical-under-load figure would flag only
prob_20/36/25 (all 3 confirmed real above 14%); a tighter band derived from
this run's own calibration drift (~5% wall / ~1% objective on the easy
prob_5 control) would flag many more (everything ≥ ~3%) — I report both
readings rather than picking one, since **prob_14's re-measure result shows
the tighter band would have been the right call to make**: its 10.41%
screening delta, which sits comfortably inside the 14% historical band and
would have been left unflagged under that criterion, turned out to be pure
rep-to-rep noise once re-measured. The task brief's 5-instance cap was
applied by absolute screening-delta rank regardless of which band produced
it, per instruction.

## Verdict scope

**This report does not issue a promote/reject verdict on the F17 arm family
and does not score rex's predictions CONFIRMED/FALSIFIED — that scoring is
explicitly rex's, not eva's, per the task brief.** What this sweep shows,
stated as observations only:

- 90/90 calls returned feasible, audited solutions; zero −1s, zero timeouts,
  zero crashes, zero checker exceptions.
- 17 of 34 instances tie exactly between arms; 9 instances favor congestion
  strictly; 8 favor baseline strictly (using N=3 median where re-measured);
  the previously N=1-flagged prob_14 delta did not survive re-measurement and
  resolves to a tie.
- The three largest confirmed deltas (prob_20 +57.80%, prob_36 −48.28%
  median, prob_25 −18.08%) are all real (deterministic or directionally
  stable across N=3), not noise, and cut in **both directions** — congestion
  is much better on two of these three, much worse on the third. This is
  consistent with the standing 0.4 finding language ("congestion effect
  real/large/bidirectional") already recorded in `REMAINING_TASKS.md`.
- Bucket A (prob_1/2/8): objective ties hold on all three; the certificate
  *type* changes on all three (baseline: `assignment_lb_reached`; congestion:
  `master_bound_closed`) with a modest wall increase. Raw fields captured
  above for rex's scoring.
- F29 detectors (prob_23/29): seed-stage bit-identical assignment confirmed
  on both; final-objective deltas exist on both (+5.15%, +8.67%) but their
  provenance differs — prob_29's traces cleanly to a full-pass abort under
  the arm; prob_23's does **not** trace cleanly to any single logged pass,
  because `info["passes"]`'s `seed+repair` entries never log an `objective`
  field (a genuine logging gap, reported not fixed).

## What this does NOT show

- **Not gauntlet-valid**: macOS, 8 cores, no isolation, swap/load elevated
  and spiking mid-run (load hit 11.38 once). Direction/coverage signal only.
- **Not a t=300 result**: this is the t=60 screening tier only; D1 already
  showed the t=60 vs t=300 picture can reverse (prob_31 head-to-head lost at
  t=300 per the 0.4 verdict note) — nothing here should be read as
  contradicting or confirming that at other timelimits. D3 (prob_21/26 @
  t=300) is still pending and is the next gate in this sequence.
- **Not a promote/reject basis**: N=1 screening is direction-grade only, and
  even the N=3 re-measured rows are N=3 (ship-grade is N≥5 per the standing
  A/B protocol). The cap-at-5 re-measure list means 12 other non-tie
  instances (prob_19, 22, 23, 24, 28, 29, 33, 34, 35, 37, 39, 7, 32) were
  never re-measured and their N=1 deltas could individually be noise (per
  the prob_14 lesson, some plausibly are, especially the sub-5% ones).
- **Does not explain WHY** congestion helps or hurts on any given instance
  beyond what's directly visible in `info["passes"]` — the raw JSON per row
  is preserved for that follow-up but no causal model is proposed here.
- **Does not resolve the F29 prob_23 provenance question** — that requires
  either an `info["passes"]` logging fix (out of scope for eva) or a
  dedicated diagnostic pass, not this sweep.

## Files

- CSV (90 rows, `role` column tags `calibration_start` / `calibration_end` /
  `screening_n1` / `remeasure_extra`):
  `ogc2026/baseline/results/2026-07-28_d2_screening_sweep.csv`
- Progress journal (append-only, full run history + corrections):
  `/private/tmp/claude-501/-Users-jungwoosuh-Desktop-workspace-03-Projects-OGC-2026/6332b06e-d056-4262-9589-90fb10c82042/scratchpad/d2_progress_journal.txt`
- Per-call raw `info` JSON dumps (90 files):
  `/private/tmp/claude-501/-Users-jungwoosuh-Desktop-workspace-03-Projects-OGC-2026/6332b06e-d056-4262-9589-90fb10c82042/scratchpad/d2_raw_info/`
- Runner script: `/private/tmp/claude-501/-Users-jungwoosuh-Desktop-workspace-03-Projects-OGC-2026/6332b06e-d056-4262-9589-90fb10c82042/scratchpad/run_one_d2.py`
