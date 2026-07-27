# Submission lineage — hidden-set (P1–P6) results, all attempts to date

**Stamp:** 2026-07-26, git HEAD `02080f2` (no commit exists at any submission
timestamp — see Process finding below; this is a mtime/reconciliation stamp,
not a claim that `02080f2` was the submitted code).
**Pipeline evaluated:** none locally — this table is **transcription only**.
Per P0(a) of the O11 falsification gate (PROPOSAL_FLUID_COMMAND.md v2.1,
COMMAND_MANUAL.md §2 "O11 falsification gate"), no solver was run to produce
these numbers. **rex is running concurrent CP solves on this machine as this
file is written; the machine is not quiet and no timing measurement is
attempted or implied anywhere below.**
**Provenance:** transcribed from `submission@optichallenge.com` acceptance/
rejection reply emails, account candorleo02@gmail.com, retrieved 2026-07-26.
Message-IDs: `19f833751bdb1aeb` (07-21), `19f8e7d6b9e385a7` (07-23),
`19f94bbdd6596b4a` (07-24), `19f9b06afeea0aa6` (07-25).

## Fact recorded for the first time: the hidden evaluation set is P1–P6

All submissions are scored against **six hidden instances (P1–P6)**, not the
40 train instances (`../../train/prob_1.json … prob_40.json`). Every train-set
panel in `results/` (chimera submit-safety, v0.4 LBBD sweep, etc.) is a proxy
measured on a *different* instance population from what the leaderboard
actually scores. This table is the first stamped record of that distinction.

## Lineage (all times UTC)

| attempt | timestamp (UTC) | outcome | reason (if rejected) |
|---|---|---|---|
| 1 | 2026-07-21 03:11:08 | REJECTED | `myalgorithm.py` inside a subdirectory (zip-layout error) |
| 2 | 2026-07-21 03:23:21 | accepted | — |
| 3 | 2026-07-23 03:17:18 | REJECTED | same zip-layout error as attempt 1 |
| 4 | 2026-07-23 04:31:35 | accepted | — |
| 5 | 2026-07-24 08:20:19 | accepted | — **submission_5**, frozen-hedge basis (COMMAND_MANUAL §3, PROPOSAL_FLUID_COMMAND §Falsification gate) |
| 6 | 2026-07-25 14:52:51 | accepted (evaluated 2026-07-25 20:45 UTC) | — chimera entry (commits `805613e`/`1a02fb2`); **current standing accepted zip** |

## Per-instance hidden-set objectives (accepted attempts only)

All six instances returned "Feasible solution found" on every accepted run —
**zero −1 anywhere** in this lineage.

| attempt | P1 | P2 | P3 | P4 | P5 | P6 |
|---|---|---|---|---|---|---|
| 2 (07-21 03:23:21) | 280,494.0 | 62,696.0 | 61,634,834.0 | 36,957,614.0 | 220,176,080.0 | 601,627,045.0 |
| 4 (07-23 04:31:35) | 26,150.0 | 37,748.0 | 515,798.0 | 11,570,444.0 | 34,867,084.0 | 57,616,192.0 |
| 5 (07-24 08:20:19) | 11,280.0 | 31,368.0 | 186,910.0 | 8,462,228.0 | 20,226,241.0 | 52,808,786.0 |
| 6 (07-25 14:52:51) | 11,280.0 | 32,068.0 | 376,241.0 | 10,854,126.0 | 18,630,178.0 | 52,828,500.0 |

## attempt 6 (chimera / standing) vs attempt 5 (submission_5 / frozen hedge)

| instance | submission_5 | chimera (standing) | delta | direction |
|---|---|---|---|---|
| P1 | 11,280.0 | 11,280.0 | 0 | tie |
| P2 | 31,368.0 | 32,068.0 | +700 | worse |
| P3 | 186,910.0 | 376,241.0 | +189,331 | worse (~2.0x) |
| P4 | 8,462,228.0 | 10,854,126.0 | +2,391,898 | worse |
| P5 | 20,226,241.0 | 18,630,178.0 | −1,596,063 | **better** |
| P6 | 52,808,786.0 | 52,828,500.0 | +19,714 | worse |

Net: chimera wins 1/6 instances (P5), ties 1/6 (P1), loses 4/6 (P2/P3/P4/P6).
This is the concrete instance the COMMAND_MANUAL/PROPOSAL "chimera incident"
precedent (Ship criterion) refers to: a technically feasible, fully-accepted
entry that lost per-instance rank on 4 of 6 hidden instances against the
previous accepted submission.

## Motivation-figure traceability (for PROPOSAL_FLUID_COMMAND §Motivation)

The proposal's "8.5M / 20M / 53M-class" tail figures are now traced to a
specific stamped source: they are **P4 / P5 / P6 of submission_5**
(8,462,228 / 20,226,241 / 52,808,786). This resolves the v2.1 provenance
caveat for those three numbers. It does **not** establish which train
instance(s) P4/P5/P6 correspond to, if any — the hidden set and the train set
are disjoint populations (see fact above); no correspondence should be
assumed without separate evidence.

## Pending: P0(b)

Local server-parity baseline of the **frozen submission_5 arm** on the O11
gate's train set (prob_21 / 26 / 27 / 31 / 38 / 40) is **PENDING**, blocked
until the machine is quiet (after rex's current concurrent CP-solve pass —
part A of the gate — completes). This table (P0(a)) supplies the hidden-set
comparison target; P0(b) will supply the train-set proxy measurement needed
to sanity-check gate instance selection against submission_5's own behavior,
as flagged in PROPOSAL_FLUID_COMMAND v2.1's P0 prerequisite.

## Process finding: no `sub-YYYYMMDD-N` tags exist

COMMAND_MANUAL.md §4 and FINALE_PLAN's tagging discipline call for a git tag
`sub-YYYYMMDD-N` at every submission. `git tag -l` returns only `v0.3-O1O6` —
**no submission tags exist in this repo.** Worse: the repository's initial
commit (`9319875`, 2026-07-25 18:39:18 +0900) **postdates all three of the
first submission attempts** (07-21 03:11, 07-21 03:23, 07-23 03:17 UTC) and
is contemporaneous with attempt 4 (07-23 04:31 UTC is ~14h before the initial
commit's timestamp in absolute terms — the repo did not exist yet at any of
attempts 1, 2, 3, or 4). Only attempts 5 and 6 fall inside the repo's
commit history window, and even for those no tag pins the exact submitted
tree — attempt 6 is inferred from commit-message content (`805613e`
"Chimera entry" + `1a02fb2` "chimera passes the submit-safety panel") and its
own acceptance timestamp (2026-07-25 14:52:51 UTC) falling between `805613e`
(21:05 JST = 12:05 UTC) and `1a02fb2` (21:47 JST = 12:47 UTC)... **note:**
attempt 6's acceptance timestamp (14:52:51 UTC) is *after* both those commit
UTC-equivalents (12:05, 12:47 UTC), consistent with `1a02fb2` being the
submitted tree, but this is circumstantial (timestamp ordering), not a tag.
**Conclusion: the mapping from submissions to commits is reconstructable
only approximately for attempts 5–6, and not reconstructable at all for
attempts 1–4 (pre-repo).** Recommend resuming the tagging discipline at the
next submission without exception.

## What this table establishes — and does not

**Establishes:** the hidden-set (P1–P6) per-instance objective baseline for
every accepted submission to date, including the frozen submission_5 arm
that the O11 falsification gate names as its comparison target
(PROPOSAL_FLUID_COMMAND §Falsification gate, "comparison target = frozen
submission_5 recorded results"), and the standing chimera entry's per-instance
delta against it. It also establishes, for the first time in `results/`, that
the hidden set is P1–P6 (six instances) — distinct from the 40-instance train
panel every other stamped file in this directory measures.

**Does not establish:** any train-instance (`prob_1`–`prob_40`) baseline for
submission_5 or any other submitted arm — that is P0(b), pending and blocked
on machine quiet. It does not establish any timing, wall, RSS, or feasibility-
stage-of-failure data (there is none to report; all runs above returned
feasible with no −1) beyond the binary "feasible" status transcribed from the
reply emails. It does not certify a mapping from hidden P1–P6 instances to
any train instance — no such mapping is claimed or implied. It does not
constitute a rex falsification pass; it is eva's P0(a) transcription step
only, per this task's explicit scope (transcription and stamping, no solver
compute).
