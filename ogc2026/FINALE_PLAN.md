# FINALE_PLAN.md — OGC 2026: from v0.2 to the podium

Created 2026-07-25. Owner: the architect discussion (Leo + Claude). Executors: **tom**
(implements), **eva** (measures), **rex** (falsifies). This file is the standing answer
to "what should I be doing right now?" for every agent, phase by phase. Update it when a
phase gate passes; never delete a phase — mark it DONE with the date and evidence.

Competition facts that shape everything (problem-statement.pdf v1.2 — re-check the
website for revisions; announcements also land on the competition Discord):
score per instance = R − nb, any failure = −1 · hidden timelimits "minutes to 30 min" ·
server = 4 cores / 16 GB / Ubuntu 24.04 · email submission, 12 h cooldown, **latest
accepted zip ranks** · final judgment = leaderboard + technical report + presentation +
code review, all finalist code goes public.

---

## Standing cadence (all phases, no exceptions)

Every component: **discussion approves → tom implements (parity + smoke green) → eva
panels it (stamped, N ≥ 3, LB-gap column) → rex passes it when it's load-bearing**.
Findings fold into DESIGN_FROM_SCRATCH's F-log via discussion. Every submission gets a
git tag (`sub-YYYYMMDD-N`) before the email goes out. Only Leo sends submission emails
(registered address). A result without a version stamp does not exist.

---

## Phase 1 — Build-out to v0.3/v0.4 (now)

Goal: land the two rank-winning components and close the known tail gaps.
Order: O1 → (O2 + O3 together) → tuck/cluster (F2) → O4/O6/O7 riders → 4-core conductor.

- **tom**: implement, in order: (1) assignment master with Z3=0 probe + Z2 floor
  targeting (O1+O6); (2) weight-regime triage + honest-θ joint objective mode (O2) and
  queue-aware construction aimed at measured peak windows (O3, incl. per-day energetic
  LB in bounds.py); (3) tuck + cluster as load-bearing tiers (today they are stubs);
  (4) same-day handoff anchors (O4), phase-dependent raster resolution (O7); (5) the
  conductor's 4-core worker pool (design Part VI — thread caps everywhere).
- **eva**: panel after each landing, head-to-head vs legacy with the rank-currency
  summary. Track the pre-registered targets: prob_1 ≤ ~200 after O1; prob_39 Z1 = 0
  after O3; prob_14 gap closing after tuck; prob_40 back under 6.91M. Weekly: one
  {300, 900, 1800} axis run + peak RSS.
- **rex**: pass each landed component (master cuts soundness; queue construction vs
  the congestion profiles; tuck's dirty-mask containment; pool oversubscription).
  Also: build the **synthetic instance generator** (single bay, m = 8–10, zero slack,
  n = 500, w2-dominant, pathological polygons) — rex owns hidden-test paranoia.
- **Gate to Phase 2**: prob_14 within ~1.1× of legacy or better, prob_40 ≥ parity with
  v0.1, no parity violations, at least one pre-registered target hit.

## Phase 2 — Submission capability (overlaps Phase 1; do not wait for its gate)

Goal: a tested pipeline from repo to accepted submission — before quality peaks.

- **tom**: (1) the **chimera entry** (`baseline/sub/myalgorithm.py`): runs solver first, legacy with the
  remaining budget, returns best verified per instance — dominates both lines under
  R − nb at near-zero risk; (2) `make_submission.sh`: builds the zip (entry + both
  pipelines, no tests/results/tester), unzips to a clean temp dir, smoke-runs prob_1
  there. Zip layout: myalgorithm.py at root, ≤ 15 MB, relative paths only.
- **eva**: the release gauntlet on every submission candidate, in server-parity mode
  (taskset 4 cores, thread caps): full panel at 60 s + spot checks at 900/1800 s +
  peak RSS < 12 GB + the SUBMIT-UNSAFE checklist. Verdict recorded in results/.
- **rex**: one pass dedicated to the submission path itself: what makes the *zip* fail
  (imports, paths, missing files, cold-start cost, ortools availability assumptions)?
- **Leo**: send one **early real submission** (the chimera) as a pipeline test — the
  first submission's job is de-risking the channel, not ranking. Join the Discord;
  bookmark the doc-updates page.
- **Gate**: an accepted submission email with per-instance statuses and no failures.

## Phase 3 — Preliminary stage: the leaderboard cycle

Goal: climb tiers with the 12 h cooldown as a strategic resource (max ~2 shots/day).

- Rhythm per cycle: eva's gauntlet passes → Leo tags + submits → read the reply email's
  per-instance statuses (the only per-instance signal we get — tiers hide ranks) → any
  failure or surprise goes to rex as a finding → discussion picks the next component.
- **tom**: keeps building Phase-1 leftovers + whatever rex's findings demand. Never
  edits between eva's gauntlet and Leo's submission of that tag.
- **eva**: after each reply email, reconcile: any instance whose status surprised us
  (unexpected −1, unexpectedly weak class) becomes a panel/synthetic reproduction task.
- **rex**: scheduled pass every ~3 cycles even if nothing "changed" — drift, stale
  assumptions, and doc revisions are his beat. Re-run the weight-regime and slack
  statistics if the organizers revise instances or the document version bumps.
- Submission discipline: **never submit a tag eva hasn't gauntleted**; remember the
  leaderboard runs the *latest accepted* zip — an experimental submission overwrites a
  good one for at least 12 h.
- **Gate**: advancement to the final stage (top 30–40, committee code check).

## Phase 4 — Final stage: quality + freeze discipline

- Same cycle as Phase 3, plus a **freeze policy**: in the last 72 h, only changes that
  eva shows beyond-noise-safe on the FULL sweep (prob_1–40, N ≥ 5, server parity) may be
  submitted; in the last 24 h, submit nothing new — the standing accepted zip is the
  result. The cooldown makes late gambles unrecoverable.
- **rex**: final pre-freeze pass with one question: "which single hidden-instance
  profile would hurt us most, and did the synthetics cover it?"
- **eva**: the freeze-candidate report is her most important table of the competition —
  it is the evidence the final zip stands on.

## Phase 5 — Finale deliverables (report · presentation · public code)

Judgment = leaderboard + technical report + presentation + code review. Start drafting
DURING Phase 3 — the raw material already exists and accretes by protocol.

- **Architect + Leo**: technical report assembled from: design doc v4+ (ground truths
  T1–T9, architecture, anytime-exact LBBD framing), the F-log + blindspot passes (a
  ready-made "method validation" section — measured self-falsification is rare in
  competition reports and the committee explicitly values novel rigor), and eva's
  results/ history (every claim in the report cites a stamped table). Presentation:
  the algorithm-map artifact (light theme) is the skeleton; the narrative is
  "structure over search: proofs, certificates, and a red-team protocol."
- **tom**: code-disclosure pass — the repo goes public if we final: license header
  decision with Leo, strip dead experiments, make README.md reproduce the panel
  (env, commands, expected numbers). No behavior changes during cleanup (eva verifies
  bit-identical panel results pre/post).
- **eva**: reproducibility appendix — exact env, seeds, commands, and the final panel
  re-run whose numbers appear in the report.
- **rex**: adversarial read of the report draft — every number traceable to a stamped
  table, every claim survivable in Q&A; then a mock-Q&A list ("why not pure CP-SAT?",
  "how do you know the LB is sound?", "what failed?"— the honest failure stories are
  presentation gold).

---

## Escalation rules (any phase)

- Any −1 anywhere (local or in a reply email): everything stops until rex names the
  mechanism and tom lands the fix; eva reproduces both the failure and the fix.
- Any parity violation: same, at highest priority — the engine's soundness is the
  architecture's identity.
- Any falsification trigger from the go/no-go list fires (tuck lands but prob_14
  doesn't move; master lands but prob_1 doesn't): discussion reconvenes on the
  architecture itself before more building. Falsifiers are honored, not argued with.
