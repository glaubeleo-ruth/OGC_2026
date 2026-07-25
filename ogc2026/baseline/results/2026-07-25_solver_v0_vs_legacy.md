# Solver v0 (clean-slate `solver/` package) — Milestone-2 Sweep + Panel Comparison

Run date: 2026-07-25. Engineer: eva (benchmark/verify only, no solver code touched).
Env: `ogc2026` conda env, `conda run -n ogc2026 python ...`, run from
`ogc2026/baseline/`. Every result below is judged by
`utils.check_feasibility(prob, sol)["feasible"]` on the returned solution —
never by the solver's own claim. Each instance ran in its own subprocess with
a hard external timeout of 65s (`timelimit=60`); instances ran strictly
sequentially (no core contention). Timeout/crash/`None` is recorded as
objective `-1`, never as a missing row.

Harness/driver scripts (outside the solver package, not committed to
`baseline/`): `harness_solve.py` (single-instance runner: imports
`solver.api.solve` or `myalgorithm.algorithm`, times it, audits with
`utils.check_feasibility`) and `driver.py` (subprocess orchestration with a
hard 65s timeout per run). Raw JSONL logs backing these tables:
`full_sweep.jsonl` (40 rows) and `panel.jsonl` (16 rows), retained in the
session scratch dir.

Scope note: `solver/` is **not** the submission entry point yet (`myalgorithm.py`
still points at the legacy pipeline). This report is milestone-3 go/no-go
evidence, not a pre-submission safety check on the live entry point.

---

## 1. Milestone-2 full sweep — prob_1 … prob_40, timelimit=60

CSV: `results/2026-07-25_solver_v0_full_sweep.csv`

Column notes: `wall` is process wall-clock time (external subprocess wall for
the two timeout rows, since the harness never got to print). `margin_vs_0.90x60`
= `54.0 − wall`; negative means the run breached the 90%-of-timelimit safety
margin. `total_z1_gap` is Σ per-bay `(z1_bay − lb_bay)` from `info["passes"][-1]["z1_gaps"]`:
**blank = 0 tardy blocks in that instance (gap trivially 0)**; a number = gap
computed and its value; **`n/a` = the instance had delayed blocks but the
bound pass never ran** (design's own guard: `compute_bounds and delayed and
deadline.remaining() > 5.0` — the deadline was too tight to afford the
LB certificate), so the true gap for that instance is **unknown**, not zero.

| instance | feasible | objective | obj1 | obj2 | obj3 | wall (s) | margin vs 0.90×60 | total z1 gap | delayed blocks |
|---|---|---|---|---|---|---|---|---|---|
| 1 | True | 59,681 | 2 | 157 | 2 | 1.00 | 53.00 | 2 | 1 |
| 2 | True | 3,690 | 0 | 144 | 15 | 0.38 | 53.62 |  | 0 |
| 3 | True | 599,057 | 21 | 2,330 | 105 | 5.16 | 48.84 | 21 | 9 |
| 4 | True | 125,536 | 5 | 2,278 | 0 | 3.10 | 50.90 | 5 | 3 |
| 5 | True | 1,300,788 | 79 | 2,534 | 127 | 6.16 | 47.84 | 79 | 17 |
| 6 | True | 2,342,617 | 78 | 3,211 | 60 | 4.87 | 49.13 | 78 | 13 |
| 7 | True | 2,552,881 | 142 | 2,215 | 86 | 9.32 | 44.68 | 142 | 25 |
| 8 | True | 11,252 | 0 | 2,413 | 8 | 0.76 | 53.24 |  | 0 |
| 9 | True | 210,481 | 12 | 2,147 | 265 | 3.17 | 50.83 | 12 | 5 |
| 10 | True | 1,125,667 | 73 | 2,856 | 330 | 3.51 | 50.49 | 73 | 13 |
| 11 | True | 1,607,998 | 70 | 213 | 49 | 7.65 | 46.35 | 70 | 15 |
| 12 | True | 8,102,840 | 368 | 3,540 | 92 | 12.81 | 41.19 | 365 | 43 |
| 13 | True | 1,733,628 | 91 | 4,364 | 141 | 12.31 | 41.69 | 91 | 22 |
| 14 | True | 2,271,262 | 126 | 2,310 | 148 | 14.57 | 39.43 | 126 | 21 |
| 15 | True | 962,868 | 63 | 4,149 | 66 | 8.43 | 45.57 | 63 | 16 |
| 16 | True | 301,910 | 31 | 3,887 | 52 | 4.78 | 49.22 | 31 | 11 |
| 17 | True | 359,863 | 32 | 7,103 | 159 | 4.41 | 49.59 | 32 | 10 |
| 18 | True | 1,020,543 | 75 | 4,876 | 8 | 14.33 | 39.67 | 75 | 25 |
| 19 | True | 2,933,504 | 272 | 6,291 | 52 | 17.92 | 36.08 | 266 | 28 |
| 20 | True | 6,798,827 | 253 | 3,721 | 238 | 17.68 | 36.32 | 253 | 49 |
| 21 | True | 22,944,512 | 1,714 | 6,340 | 189 | 55.22 | **-1.22** | n/a | 54 |
| 22 | True | 18,981,550 | 1,418 | 11,252 | 104 | 22.58 | 31.42 | 1,418 | 57 |
| 23 | True | 5,238,353 | 386 | 597 | 2 | 54.88 | **-0.88** | n/a | 44 |
| 24 | True | 9,211,192 | 689 | 3,451 | 25 | 51.61 | 2.39 | n/a | 34 |
| 25 | True | 1,030,059 | 1,536 | 5,067 | 24 | 56.00 | **-2.00** | n/a | 48 |
| 26 | True | 59,379,214 | 4,448 | 10,190 | 18 | 59.69 | **-5.69** | n/a | 96 |
| 27 | True | 61,660,104 | 4,586 | 5,883 | 1,258 | 56.95 | **-2.95** | n/a | 103 |
| 28 | True | 15,817,434 | 1,185 | 5,943 | 0 | 55.76 | **-1.76** | n/a | 82 |
| 29 | True | 12,101,147 | 905 | 11,594 | 0 | 55.02 | **-1.02** | n/a | 72 |
| 30 | True | 7,736,059 | 579 | 2,263 | 36 | 55.71 | **-1.71** | n/a | 83 |
| 31 | True | 81,246,942 | 6,009 | 21,294 | 3,989 | 57.74 | **-3.74** | n/a | 127 |
| 32 | True | 7,497,025 | 2,205 | 4,952 | 205 | 55.28 | **-1.28** | n/a | 114 |
| 33 | True | 16,836,024 | 2,522 | 1,045 | 76 | 61.50 | **-7.50** | n/a | 142 |
| 34 | True | 2,801,246 | 823 | 3,287 | 66 | 55.74 | **-1.74** | n/a | 83 |
| 35 | True | 12,315,971 | 922 | 4,229 | 12 | 56.13 | **-2.13** | n/a | 89 |
| 36 | True | 3,492,701 | 5,189 | 12,892 | 1,442 | 61.67 | **-7.67** | n/a | 139 |
| 37 | True | 10,805,263 | 3,223 | 13,801 | 13 | 55.98 | **-1.98** | n/a | 134 |
| **38** | **False** | **-1** | — | — | — | 65.02 | **-11.02** | n/a | n/a |
| 39 | True | 31,184,815 | 2,337 | 5,911 | 13 | 62.03 | **-8.03** | n/a | 150 |
| **40** | **False** | **-1** | — | — | — | 65.01 | **-11.01** | n/a | n/a |

Bold rows/cells mark safety-margin or feasibility failures.

### Wall-time / margin pattern

There is a clean regime change at roughly prob_20→21: instances 1–20 finish in
0.4–18s (huge margin), while **18 of the last 20 instances (21–40) breach the
0.90×60 = 54s safety margin**, and two (38, 40) blow through the 65s hard
external cutoff entirely. This tracks instance size (prob_21+ are the
larger/denser 200–250 block, 4-bay instances) — the pipeline's per-instance
cost is evidently super-linear enough in n/congestion that it saturates and
then exceeds the deadline governor's own budget on the hard tail.

---

## 2. Diagnostic: the two `-1` timeout rows (prob_38, prob_40)

Both were re-run standalone (no external hard cutoff other than a generous
one) at the same `timelimit=60` to see what the solver actually does past 65s:

| instance | actual wall (standalone) | requested timelimit | nominal budget (0.93×t−1) | overrun vs timelimit | feasible if allowed to finish |
|---|---|---|---|---|---|
| 38 | 66.99s | 60s | ~54.8s | +7.0s | True (obj 103,073,968) |
| 40 | 70.76s | 60s | ~54.8s | +10.8s | True (obj 6,528,440) |

Both instances *are* solvable and *do* return a feasible solution — the
`utils` audit passes once the pipeline is allowed to finish — but the wall
clock overruns the requested `timelimit` itself (not just the 0.93×t−1
governed budget), which is exactly the hard-rule-5 failure mode
(`CLAUDE.md` §5: "Overrun = -1"). There is no `utils` stage failure here
(stage/violations are N/A) — this is a **deadline-governor breach**, not a
geometric/assignment infeasibility. On the real eval server (`timelimit=60`,
`≤4` cores) this pattern would score **-1** on both instances if the overrun
holds or worsens under contended cores.

---

## 3. Gap-KPI summary (Σ per-bay `z1 − lb`, the certified Z1-optimality KPI)

Out of 40 instances:

- **2 instances (5%) — gap = 0 by construction** (no delayed blocks at all):
  prob_2, prob_8.
- **19 instances (47.5%) — gap computed and > 0** (a certified, sized work
  item — the LB proves zero-tardiness or lower-tardiness was reachable and
  the pipeline didn't find it): prob_1, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14,
  15, 16, 17, 18, 19, 20, 22.
  - Biggest gaps: **prob_22 → 1,418**, prob_12 → 365, prob_19 → 266,
    prob_20 → 253, prob_7 → 142.
- **19 instances (47.5%) — gap unknown ("n/a")**: prob_21, 23–39 (except 22)
  and both timeout rows (38, 40, listed here since they never reached the
  full pass). On every one of these the deadline was consumed by the
  packing/rescue stages before `compute_bounds`'s `deadline.remaining() > 5.0`
  guard could fire, so **the LB certificate step never ran** — these are not
  proven non-zero gaps, they are simply uncertified. This is the same
  hard-tail region as the wall-time breaches in §1: on the instances that
  most need the optimality certificate (large `obj1`, many delayed blocks),
  the budget is already spent before the certificate can be computed.
- **0 instances — gap proven exactly 0 despite delayed blocks** (i.e. no case
  where the solver hit a truly LB-forced tardy day and certified it as such).

Net read: where the KPI *is* observable, it is never zero-with-delay — every
instance that had delayed blocks and got a certificate shows a nonzero,
work-item gap, and the largest instances (which carry the most tardiness in
absolute terms) are exactly the ones where the certificate step starves.

---

## 4. Panel comparison vs legacy — prob_1, 2, 3, 4, 5, 10, 14, 40 (timelimit=60)

CSV: `results/2026-07-25_solver_v0_vs_legacy.csv`. Legacy
(`myalgorithm.algorithm`) uses its full 60s budget by design (portfolio +
ALNS loop); both walls reported as observed, not as a criticism of legacy's
budget use.

| instance | legacy obj | legacy wall | new obj | new wall | delta (new−legacy) | delta % | winner |
|---|---|---|---|---|---|---|---|
| 1 | 20,045 | 51.31s | 59,681 | 0.57s | +39,636 | +197.7% | legacy |
| 2 | 6,620 | 51.19s | 3,690 | 0.47s | -2,930 | -44.3% | **new** |
| 3 | 75,980 | 51.22s | 599,057 | 3.25s | +523,077 | +688.4% | legacy |
| 4 | 81,600 | 51.19s | 125,536 | 1.79s | +43,936 | +53.8% | legacy |
| 5 | 74,487 | 51.09s | 1,300,788 | 3.55s | +1,226,301 | +1646.3% | legacy |
| 10 | 91,224 | 51.32s | 1,125,667 | 2.03s | +1,034,443 | +1134.0% | legacy |
| 14 | 167,807 | 52.05s | 2,271,262 | 8.39s | +2,103,455 | +1253.5% | legacy |
| 40 | 5,186,325 | 53.80s | **-1 (timeout/infeasible)** | 65.01s (hard-cut) | — | — | legacy (new infeasible/timeout) |

**7 of 8 legacy wins, 1 new win (prob_2), 1 new failure (prob_40, hard
timeout on the panel's 65s external cutoff).** The magnitude of the legacy
wins is large — the new solver's `obj2` (bay-load imbalance) component in
particular runs 5–50× higher than legacy's on every panel instance, which is
the dominant driver of the objective gap (`w2` is comparatively small, but
`obj2` itself is enormous — the new assignment master appears to load-balance
far worse than the legacy ALNS repair). Legacy also finishes with 0 obj1
(zero tardiness) on 6 of 8 panel instances; the new solver has nonzero obj1
on all 8.

This is expected/tracked: `solver/README.md` lists `assignment.py` as
"single-shot; LBBD re-solve loop pending" and `cluster.py` (tier-3 CP-SAT
repair) as a milestone-3 stub — the objective gap here is consistent with
those documented gaps in the pipeline, not a surprise regression.

---

## 5. Infeasible/timeout cases — failing stage + first violations

Only two rows are not `feasible: True` in either sweep, and both are the same
underlying event (prob_38 in the full sweep, prob_40 in both the full sweep
and the panel):

| instance | context | utils stage | violations | root cause |
|---|---|---|---|---|
| 38 | full sweep | N/A (never reached utils — killed by external 65s timeout) | N/A | Deadline-governor overrun: 66.99s actual wall vs 60s requested (see §2) |
| 40 | full sweep + panel | N/A (never reached utils — killed by external 65s timeout) | N/A | Deadline-governor overrun: 70.76s actual wall vs 60s requested (see §2) |

No instance produced a solution that reached `utils.check_feasibility` and
*failed* a geometric/assignment stage — every completed run passed stage 5
(full replay). The only failure mode observed is **wall-clock overrun on the
largest instances**, not solution-quality infeasibility.

---

## 6. Verdict (informational — milestone-3 go/no-go input, not a live-submission gate)

`solver/` is not wired to `myalgorithm.py` yet (confirmed:
`myalgorithm.py` still imports the legacy pipeline; hard rule 1's signature is
untouched). This verdict is **informational for the milestone-3 decision**,
not a statement about the current submission's safety — the submission entry
point (`myalgorithm.algorithm`) was not modified and is not implicated by any
finding here.

**SOLVER-V0 STATUS: SUBMIT-UNSAFE (informational)** — if `solver/` were
promoted to the entry point today, unmodified, it would fail the CLAUDE.md
hard rules on multiple counts:

- **-1 / infeasible-by-timeout**: 2/40 instances (prob_38, prob_40) — hard
  rule 5 ("Overrun = -1").
- **wall > 0.90×timelimit**: 18/40 instances (prob_21, 23, 25–37, 39, 40) —
  a systemic hard-tail problem, not isolated noise; correlates with instance
  size (200–250 blocks, 4 bays).
- **objective regression vs legacy on panel instances**: 6/8 panel instances
  regress (prob_1, 3, 4, 5, 10, 14), by 54%–1646%; 1 panel instance times out
  outright (prob_40, the largest panel instance) where legacy stays feasible.
  Only prob_2 improves over legacy.

None of this blocks milestone-2 (full sweep + gap KPI, delivered above) or
disqualifies the architecture — the design doc itself flags `cluster.py`
(tier-3 CP-SAT repair) and the LBBD re-solve loop as not-yet-built, and the
wall-time/gap-KPI data in §1–§3 point at exactly those missing pieces (large,
congested instances are where both the deadline and the LB-certificate step
run out of budget). But as measured today, `solver/` is **not** ready to
replace `myalgorithm.py`: milestone 3 (cluster repair + panel comparison,
which this report partially pre-empts) should not green-light a swap until
(a) the deadline governor is proven to respect `timelimit` on the prob_21+
size class, and (b) the assignment master's `obj2` performance is closed or
explained relative to legacy.
