# REMAINING_TASKS.md — the punch list to project completion

Created 2026-07-28. This is the flat, finite list of everything left, with owners,
done-criteria, and dependencies. ◆ marks a discussion-owned decision point — no task
below a ◆ starts until that decision is made. Check tasks off with date + commit/table
reference; FINALE_PLAN.md holds the phase philosophy, this file holds the work.

## T0 — In flight / immediate (order fixed)

- [x] **0.1 F17 A/B completes** — DONE 2026-07-27, `results/2026-07-27_f17_arm_ab.{md,csv}`
      @ 00437ce (gate panel N=5 clean; screening sweep blocked by the tree reorg →
      moved to 0.4b; hedge-time n/a, runs were api.solve-level).
- [x] **0.2 A/B integrity check** — DONE 2026-07-27: arms were explicit kwargs
      (verified from source), env fallback unreachable; per-row `assign_arm` evidence
      in `..._ab_audit.csv`. No rerun ordered.
- [x] **0.3 Score pre-registered predictions** — DONE 2026-07-28, published as
      `BLINDSPOT_PASS_2026-07-27b_f17_arm_scoring.md` (1 FALSIFIED / 2 CONFIRMED /
      3 conditional / 13 PENDING→0.4b; prob_38 corrected to a real 5/5 regression).
- [x] ◆ **0.4 A/B verdict — DECIDED 2026-07-28: DO NOT PROMOTE the arm; finding retained.**
      Congestion effect real/large/bidirectional, predictor unknown; t=60 advantage =
      budget starvation (arm at asymptote, baseline −62% with 5× budget); t=300
      head-to-head lost (prob_31: 15.02M vs 15.30M, 71% structural Z3); +36% wall.
      **Hybrid (congestion-seed / master-full) is the standing candidate — promote vote
      gated on D1/D2/D3 + M1 below.** Oracle-strength effect eliminated on measured
      rows; certificate-time effect (F25) still PENDING (prob_1/2/8 never ran).
- [x] **0.4a D1: prob_38 @ t=300** — DONE 2026-07-28, HYPOTHESIS REFUTED:
      `results/2026-07-28_d1_prob38_t300.{md,csv}` @ 00437ce. Arm walls 271.8–271.9s
      (deterministic, 33s inside the kill), marginally faster than baseline; 8/8
      feasible, 0×−1. t=300 objective reversal replicates (baseline −6.5%). Secondary
      → 0.4e: BOTH arms breach 0.90·t=270s by ~2s; structural candidate named —
      SAFETY_FACTOR 0.93 gives internal budget 278s > 270s at t=300 (margin-convention
      conflict, not load noise). Needs-idle-confirmation on exact magnitude.
- [ ] **0.4b D2: 34-instance sweep both arms** — closes Buckets A/D-E + the F29
      confound detectors (prob_23/29). RUNNING (eva, launched 2026-07-28).
- [ ] **0.4c D3: prob_21 + prob_26 @ t=300** — is the t=300 reversal general; what is
      the actual win feature (areal-fill identical, opposite outcomes at t=60).
- [ ] **0.4d LBBD-loop inertness investigation**: the cut loop iterated to zero profit
      on 74/74 rows at both timelimits — the "closes F8/F9/F10" and "long-budget
      consumer" stories currently rest on a loop that has never once helped. Why:
      cuts too weak / master too slow / stops unreachable?
- [ ] **0.4e Long-timelimit margin breach investigation**: baseline hit 272.1s at
      t=300 (past 0.90·t) on the dev box — a live submit-safety issue in the CURRENT
      solver, independent of the arm. Folds into 2.5, priority raised.
- [ ] **0.5 Commit the remediation** (tom): `UNVERIFIED:` marker; nothing builds on it.
      Done: hash exists.
- [ ] **0.6 Rex verifies 0.5 at its hash** → converts to landed. Done: pass report.
- [ ] **0.7 Soundness fixes — four separate commits** (tom, each rex-verified):
      (a) ρ-mutation try/finally (P1 — master lobotomy at hidden density 1.37× prob_38);
      (b) `open_below` audit gate (latent, severity set by M2);
      (c) no-good widening guard (`len(lits)!=len(prev)` → drop);
      (d) explicit `assign_arm="baseline"` from myalgorithm.py (env surface removed).
- [ ] **0.8 Deferred measurements as the machine frees** (eva/rex): M1 seed-pass
      feasibility both arms (~2 min — blocks any arm-derived ship), M2 audit-failure
      counts (free), M3 master-cap 4s vs 8s, M5 cut-loop replay prob_1/2/8, M6 ρ-poison
      end-to-end cost.
- [ ] **0.9 Linux 4-core parity rig** (eva). BLOCKER: nothing can be SUBMIT-ELIGIBLE
      without it. Done: one gauntlet-valid table produced on it.
- [ ] **0.10 Submission-window dates check** (Leo, 5 min, website + Discord — never yet
      done). A near deadline reorders everything below toward 2.2.
- [ ] **0.11 F-log fold** (discussion): F14 onward folded into the design doc with the
      single numbering authority; colliding pass docs get header notes. Done: appendix
      updated, renumbering table included.

## T1 — Decision-gated development (order chosen at ◆0.4; all pass tom→eva→rex)

- [ ] **1.1 [branch] Oracle-strength change**: grant the full-strength oracle
      (rescue+repair+polish+bounds) to the greedy/seed assignment — the cheap change, if
      the A/B attributes wins there. Done: decision A/B N≥5 shippable verdict.
- [ ] **1.2 [branch] Merge-hypothesis gate**: congestion into the master's objective
      (mandatory-window charging + slack ordering) measured for CP-SAT solve time,
      OPTIMAL-rate at caps, anytime quality — HYPOTHESIS until this passes. Then
      ◆ implement or drop.
- [ ] ◆ **1.3 Chimera v2 design session**: hedge-first, gap-aware split, P5-preservation
      mechanism named, solver arm = whatever T1 shipped. Output: reviewable design note.
- [ ] **1.4 Chimera v2 implementation** (tom) + decision A/B vs current entry (eva).
- [ ] **1.5 4-core conductor** (tom): worker pool, thread caps, same code path at any
      core count. Done: 1/2/4-core scaling table, no oversubscription (incl. legacy
      repair.py num_search_workers check).
- [ ] **1.6 Tuck + cluster CP (geometry ladder)**: the F18/F32 class-buying lever —
      **priority RAISED by ◆0.4**: prob_21 measured F18's geometry-not-area shape on a
      real instance (arm cleared areal overload, produced 34 MORE tardy days — areal
      signal anti-correlated with objective). The assignment-lever family is at its
      ceiling; this is where the class is won. Done: prob_14/21-class gap movement
      measured. Any merge-into-master gate must include prob_21 as a test row.
- [ ] **1.7 O11 Part B re-scope** (last): only behind a localization gate design, aimed
      at instances holding the residual ~10× headroom.

## T2 — Submission capability & leaderboard cycle

- [ ] **2.1 make_submission.sh hardening**: manifest generator + in-zip hash assertions
      vs the gauntleted commit (stale-zip class killed). Done: gauntlet consumes it.
- [ ] **2.2 First v2 submission**: gauntlet → SUBMIT-ELIGIBLE → Leo submits → tag.
      Displaces the standing regressed chimera.
- [ ] **2.3 Reply-email reconciliation** (eva, after every submission): per-instance diff
      vs previous reply into results/. Regression → ◆ rollback discussion immediately.
- [ ] **2.4 Synthetic instance generator** (rex): single-bay, many-bay, zero-slack,
      n≥500, w2-dominant, pathological shapes. Done: synthetics in eva's panel rotation.
- [ ] **2.5 Long-timelimit + RSS validation**: {60,300,900} axis + peak RSS on the tail
      panel, on the rig. Done: no wall/RSS surprises at 900s.
- [ ] **2.6 Cycle cadence** (standing): rex full pass every ~3 submission cycles;
      weekly hygiene incl. dates/doc-revision check.

## T3 — Final stage (dates from 0.10 govern)

- [ ] **3.1 Freeze policy armed**: last 72h only full-sweep-proven changes; last 24h
      nothing.
- [ ] **3.2 Freeze-candidate full sweep** (eva): prob_1–40, N≥5, parity rig — the
      competition's most important table.
- [ ] **3.3 Pre-freeze rex pass**: "which hidden profile hurts most; did synthetics
      cover it?"

## T4 — Finale deliverables (start during T2, not after)

- [ ] **4.1 Technical report** (architect+Leo): assembled from design doc vX + F-log +
      stamped tables; the self-falsification arc (O11 gate, chimera regression, caught
      overclaims) is the spine. Every number cites a stamped table.
- [ ] **4.2 Presentation**: architecture map (light theme) as skeleton; narrative
      "structure over search: proofs, certificates, and a red-team protocol."
- [ ] **4.3 Public-code cleanup** (tom): license, dead experiments stripped, README
      reproduces the panel. Eva verifies bit-identical panel pre/post.
- [ ] **4.4 Reproducibility appendix** (eva) + **mock Q&A** (rex, from the honest
      failure stories).

## Standing invariants (not tasks — conditions that must stay true)

Hedge stays frozen · no zip without the gauntlet · committed≠landed · transitions are
discussion-owned · results tables carry stamps or don't exist · pass findings use
pass-local IDs · the manual's anti-pattern list is live doctrine.
