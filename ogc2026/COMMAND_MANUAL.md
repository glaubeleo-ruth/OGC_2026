# COMMAND_MANUAL.md — driving Claude Code on the OGC 2026 entry

Practical prompt reference. Copy-paste the templates; fill the ⟨brackets⟩. Claude Code
runs from `ogc2026/`; agents are `tom` (implement), `eva` (measure), `rex` (falsify).
Companion docs: CLAUDE.md (hard rules) · FINALE_PLAN.md (phase duties) ·
../DESIGN_FROM_SCRATCH_2026-07-24.md (spec + F-log) · ../PROPOSAL_FLUID_COMMAND.md (O11).

---

## 0 · Session start (every session, 30 seconds)

Paste:

> Read CLAUDE.md and FINALE_PLAN.md. Then: `git log --oneline -5`, `ls results/ | tail -3`,
> and tell me — current phase, last tagged version, last stamped panel, and any trust
> gates or pending A/Bs before we do anything new.

This forces the session to orient from the repo, not from memory. If the answer skips a
trust gate you know exists, stop and point at it.

## 1 · Invoking the agents — the shapes that work

**tom (implementation — only after direction is agreed in discussion):**

> Use the tom subagent. Approved change: ⟨one-sentence direction⟩, per
> ⟨design-doc section / F-finding / proposal name⟩. Scope: ⟨files⟩. Do not touch
> ⟨explicit exclusions⟩. Self-verify per your instructions (parity + smoke on prob_1 and
> one tail instance), then report files changed, which rule each timing change serves,
> and hand off to eva.

**eva (measurement — after every tom landing, before every submission):**

> Use the eva subagent. ⟨Panel type — see §2⟩ on ⟨instances⟩ at timelimit ⟨t⟩,
> N=⟨reps⟩, quiet machine (nothing else running). Stamp with the git hash AND the
> environment (OS, core count, isolation). If the environment is not Linux 4-core
> isolated, stamp the table **"local-only, not gauntlet-valid"**. Compare against
> ⟨previous stamped run / frozen control⟩. End with the explicit verdict.

**rex (falsification — after every load-bearing component, before every submission):**

> Use the rex subagent. Target: ⟨commit / component / claim / results table⟩.
> Load-bearing claims to attack: ⟨list, or "enumerate them yourself"⟩. Snapshot the tree
> first. Continue the F-log numbering. Answer the two standing questions (what would
> beat this / what makes this −1) even if no finding fires.

Rule of thumb: **direction → tom → eva → rex**, and nothing is "done" until all three
have spoken. Never run two agents that measure while one edits.

## 2 · Standard jobs (exact asks)

**Quick smoke (after any edit, 2 min):**
> tom: run the parity test and the headless smoke on prob_1 and prob_39 at 60s. Report
> feasible/objective/wall only.

**Decision A/B (ship/no-ship — the only kind that counts):**
> eva: paired A/B of ⟨variant⟩ vs ⟨control⟩ on ⟨panel⟩, N≥3 (N=5 if the delta claims a
> ship), quiet machine, fixed-work mode if available, same seeds where applicable.
> Decide on median; flag any instance regressing beyond the noise band. Verdict at the end.

**F17 assignment-arm A/B (the ACTIVE experiment — run this, not O11):**
> tom: expose a selectable arm inside `api.solve` — baseline master vs the
> congestion-aware assignment arm — behind a flag; no other changes; parity + smoke.
> eva: quiet machine, paired same-seed fixed-work, N≥3 (N≥5 for any ship claim),
> t ∈ {60, 300}, full screening sweep + re-measure high-variance instances, end-to-end
> through `api.solve` (never `conductor.run` direct). θ carries certified lower bounds
> only; realized results go to the incumbent and full-assignment no-goods, never into θ.
> The existing N=1 F17 numbers are a direction signal, not a ship basis.

**Full stamped panel (after a component lands):**
> eva: full sweep prob_1–40 at 60s, N=1 screening + N=3 on any instance whose delta vs
> the last stamped panel exceeds noise. LB-gap column, peak RSS, wall margins. Persist to
> results/ with timestamp+hash+environment stamp.

**Long-budget check (F10-class):**
> eva: prob_21, 26, 38, 40 at t ∈ {60, 300, 900}. Report objective vs t — any instance
> where 300s ≡ 60s is a finding for rex.

**Head-to-head / go-no-go:**
> eva: both entries (⟨A⟩ vs ⟨B⟩) on ⟨panel⟩, same protocol; per-instance winner table +
> rank-currency summary (count of strict wins each way).

**Pre-submission gauntlet (mandatory, no exceptions):**
> eva: gauntlet on the candidate zip: build via make_submission.sh, clean-dir unzip
> smoke, Linux 4-core isolated environment (taskset + thread caps) — without it the run
> is "local-only, not gauntlet-valid" and CANNOT make a zip eligible — full panel,
> walls, RSS, AND **non-inferiority vs the frozen control on the local proxy panel**.
> Verdict is **SUBMIT-ELIGIBLE / NOT** — never "beats standing": a candidate's
> hidden-set results are unknowable before submission; superiority is judged only from
> the reply email afterward, reconciled per-instance against the previous submission's
> reply. SUBMIT-INELIGIBLE if any −1, any wall > 0.90·t, RSS > 12 GB, or local-proxy
> inferiority vs the frozen control beyond noise.

**Blindspot pass (scheduled every ~3 leaderboard cycles, or on demand):**
> rex: full pass on ⟨scope⟩. Also run the opportunity sweep — measured objective left on
> the table under R−nb.

**O11 status (gate CLOSED 2026-07-27 — do not re-run it):**
> Part A verdict FINAL: headroom 4.6×–30×, geomean ~10.3× (the 10²–10³× claim is
> falsified, F14). **Part B is HELD.** Stage T is not a certificate producer on mass
> bays (F15) and its first solution is an artifact, not an optimal plan (F16) — it may
> be revisited only as a cost-capped heuristic under an explicit hard sub-budget, and
> only after the F17 A/B has a verdict and Part B's localization gate (F18) is designed.

## 3 · Decision rules (answers you give, so sessions don't relitigate them)

- A change ships only on a **decision A/B** (quiet, paired, N≥3/5, median) — never on a
  smoke, never on N=1, never on runs under load (~14–27% swings measured).
- Pre-submission, the strongest possible verdict is **submit-eligible** (safety + local
  non-inferiority vs the frozen control). "Beats the standing submission" is
  undecidable before the reply email — any argument that a candidate "wins by
  construction" is out of order. Post-submission, reconcile the reply email
  per-instance against the previous submission's reply; a regression there triggers the
  rollback discussion immediately.
- Results measured outside a Linux 4-core isolated environment are **"local-only, not
  gauntlet-valid"** — useful for direction, inadmissible for eligibility.
- "Proven/optimal/certificate" language is allowed only after **rex has attacked the
  premises** (cut soundness class of checks). Until then it's "candidate certificate".
- Falsification triggers are **honored, not argued with** (FINALE_PLAN escalation rules).
- `myalgorithm.py` entry changes and hedge-arm changes are **discussion-level decisions**
  — never delegated, never bundled into another change.
- The hedge arm is a **frozen reconstruction** of submission_5 — best-effort, since no
  tree/tag existed at the 07-24 submission, and the hard wall postdates it. Never call
  it "submission_5 bytes"; never tune it; it stays frozen until a gauntleted successor
  supersedes it.

## 4 · Anti-patterns (each one has already cost us something)

- ✗ Running smokes/panels while agents work — contention invalidates anytime measurements.
- ✗ Quoting a results table without its stamp — check the hash matches HEAD or say "stale".
- ✗ "Improved ~X%" without raw per-instance numbers and rep count.
- ✗ Committing tuning to the legacy arm — it is a frozen hedge, not a dev target.
- ✗ Fixing budget splits by constant (0.55) — splits are gap-aware or they're wrong.
- ✗ Letting a session "clean up" or refactor beyond the approved scope.
- ✗ Editing `.claude/agents/*` in one location only — both copies or none.
- ✗ Skipping git: every landing is a commit; every submission is a tag (`sub-YYYYMMDD-N`).
- ✗ Deciding under rank-recovery pressure — the bar is the rule, not the vibe. (2026-07-27:
  the architect recommended a "recovery" zip that failed his own rules on P5; adversarial
  review caught it. If a decision feels urgent because rank is bleeding, that is the
  moment to re-read §3, not to waive it.)
- ✗ Claiming a candidate "beats standing" pre-submission — hidden results don't exist
  yet; the claim is unfalsifiable at decision time and has already misled us once.

## 5 · Quick facts card (paste into any session that seems to have forgotten)

> Scoring: per instance R − nb; infeasible/timeout/crash = −1; leaderboard runs the
> LATEST ACCEPTED zip; 12h cooldown from acceptance. Server: 4 cores (firejail+cpulimit),
> 16GB, Ubuntu 24.04; hidden timelimits minutes→30min. Budget: max(1, 0.93·t − 1).
> utils.py is read-only ground truth. Entry signature is fixed. Never raise, never None,
> always utils-audited incumbent.

## 6 · Weekly hygiene (one prompt, start of the week)

> Housekeeping: confirm both .claude/agents copies match; results/ has no unstamped
> files; FINALE_PLAN phase status is current; the F-log has all findings from this
> week's passes; check the competition website + Discord for document revisions and
> submission-period dates, and report anything new.
