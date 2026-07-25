# OGC 2026 — Blindspot Pass (2026-07-24)

Scope of this audit: `problem-statement.pdf` (v1.2, all 15 pages), `myalgorithm.py`, the full
`alns/` stack, `CLAUDE.md`, both `tom.md`/`eva.md` copies, git state, and the on-disk repo layout.
Findings are ordered by expected leaderboard impact, not by how easy they are to fix.

---

## 1. The scoring is rank-based — and nothing in your repo knows it

Per instance, the leaderboard score is **R − nb** (teams evaluated minus teams strictly better),
and **−1** for infeasible/timeout/crash. This is the single most consequential fact in the PDF and
it appears nowhere in CLAUDE.md, tom.md, or eva.md. Consequences you are currently not optimizing for:

- **One −1 on one hidden instance can outweigh ten marginal wins.** The robustness machinery you
  built (seed fallback, deadline governor) is correctly aimed — but every *new* risk (portfolio
  paths untested on 4 cores, 30-min runs untested, memory) is a −1 risk, and −1 is catastrophic in
  rank currency, not just "bad".
- **An objective improvement only scores if it crosses another team's value.** On easy instances
  every competent team reaches Z1 = 0 and ranks are decided by Z2/Z3 dust. Your Class A insight is
  exactly right — but rank scoring says push it to *exactness* (lexicographic CP-SAT close-out on
  the assignment layer), because "small Z3" vs "zero Z3" can be many rank places.
- **Ties share points.** Instances with an obvious optimum differentiate nobody; the hard tail
  (prob_39/40-like) is where ranks are won. Budget your attention accordingly.
- The public leaderboard shows **tiers only** (top 10/20/30). You cannot observe marginal external
  gains — your internal measurement is the only signal you have, which raises the stakes on §5.

**Fix:** add a distilled `RULES.md` (rank scoring, −1 semantics, server spec, cooldown, timelimit
range, integer rounding, 16 GB cap) and make CLAUDE.md point at it. Right now tom and eva operate
without the meta-game.

## 2. You test at 60 s; the server runs "a few minutes to half an hour"

Every calibrated constant in myalgorithm.py was measured at timelimit = 60: seed_frac 0.25/0.65,
FNO share 0.4/0.6, K 15→8, the prob_40 "seed-only at 45 s beats the pipeline" diagnosis, eva's
default sweep. The PDF says hidden limits range from a few minutes to 30 minutes. Unknowns at
1800 s that nobody has looked at:

- Does "seed keeps improving with budget" (the 0.65 overload split) still hold when 0.65 means
  ~19 minutes of greedy? That finding was extrapolated from a 60 s experiment.
- SA cooling is geometric in elapsed/deadline — at 30 min the walk may spend most of its time
  effectively cold or effectively random; nobody has plotted acceptance rates over a long run.
- **Memory is a −1 you've never measured.** 16 GB cap, 4 forked children, CP-SAT models, 30-minute
  accumulation. An OOM kill reads as "process terminated unexpectedly" = −1.
- `est_check_cost` is measured in the first seconds; on a 30-min run the state it prices drifts.

**Fix:** eva's protocol gains a timelimit axis: {60, 300, 900, 1800} on a small panel, with peak-RSS
logging (`/usr/bin/time -v` or `resource.getrusage`). Once, soon — before it's urgent.

## 3. Your dev machine never executes the code path the server will execute

Comments in myalgorithm.py say it plainly: "a 2-core dev box reproduces the pre-NFP stack exactly"
and NFP-slide "rides slots 3–4, so it engages only where ≥3 cores exist". Translation: **the
portfolio configuration that actually runs on the 4-core eval server is the one you test least.**
Same for A-Assign (slot swap) and the 4-chain ALNS phase. Additional server-parity gaps:

- Enforcement is **firejail + cpulimit (400%)**. If firejail pins affinity to 4 CPUs, your
  `sched_getaffinity` sizing is correct. If it's cpulimit-style throttling (SIGSTOP/SIGCONT bursts
  over all 32 threads of the 9955WX), wall-clock progress is bursty and your near-deadline timing
  measurements distort. You don't know which — worth a Discord question or a probe submission
  (print affinity + cpu_count in a log line on a real run... you can't see stdout, so instead
  encode it locally: reproduce both regimes and check margins).
- **Thread oversubscription:** `repair.py:616` sets CP-SAT `num_search_workers = 4`. Inside 4
  parallel ALNS chains that is up to 16 solver threads against a 400% cap — exactly the
  oversubscription collapse you measured yourself at the seed level (0.46× throughput). fno and
  bayassign correctly use 1; the MILP repair doesn't. Also no `OMP_NUM_THREADS` /
  `OPENBLAS_NUM_THREADS` caps anywhere — numpy in each forked child may spawn its own thread pool.
- Dev is macOS; eval is Ubuntu 24.04. fork-on-macOS quirks aside, single-core speed and BLAS
  builds differ. Your 0.93 factor is a guess, not a measurement.

**Fix:** a server-parity rig: Linux, `taskset -c 0-3` (and once with cpulimit to compare), env caps
`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`, `num_search_workers=1` in chain context. Note the
Cowork cloud container eva could run in *is* Linux and can pin cores — a candidate for exactly this.

## 4. Zero commits, no results/, ghost specs — the process layer is thinner than the code layer

Verified on your disk today:

- **The git repo has no commits at all.** Branch `main`, everything staged, nothing committed.
  No known-good version, no bisecting a regression, no tag for "what we last submitted". With a
  12 h submission cooldown, accidentally overwriting your best-known state is expensive in both
  directions (code and leaderboard).
- **`results/` does not exist.** Eva's own definition says persist every sweep to results/ with a
  timestamped name; no sweep has ever been persisted. Cross-session comparisons currently live in
  code comments and memory.
- **WATCHDOG_SPEC.md and ADR-001 are ghost references.** myalgorithm.py and CLAUDE.md cite them
  as governing documents; neither exists (CLAUDE.md itself was reconstructed from code comments
  after the originals vanished). Institutional knowledge is stored exclusively in comment blocks.
- **Two divergent tom.md files.** Claude Code runs from `ogc2026/`, so it loads
  `ogc2026/.claude/agents/tom.md` — the *stale* 741-byte version (model: opus, no smoke-test
  protocol). Your improved 2612-byte tom (model: sonnet, hard rules, handoff protocol) sits unused
  at the repo root `.claude/agents/`. The mv workaround from memory apparently never landed for tom.

**Fix (an afternoon):** initial commit + `.gitignore` (`__pycache__`, `.DS_Store`); tag every
submission (`sub-YYYYMMDD`); commit results/ CSVs; recreate WATCHDOG_SPEC.md and an ADR log as real
files; delete the stale tom.md.

## 5. Statistical discipline: you know the variance and the protocol ignores it

myalgorithm.py documents that seed Z1 on prob_1 varies **~36–44 across identical runs** — yet
ship/no-ship decisions throughout the code cite "measured ×2" (two repetitions). With ~10–20%
run-to-run noise, 2 reps has a high false-positive rate; some shipped "wins" are plausibly noise.
Compounding it, the pipeline is now steered by point-calibrated gates fitted to named train
instances: ratio thresholds 0.55/0.70, `max_pref_ratio < 1.0`, K = 8, w3_mult ∈ {3, 5, 8},
w1_mult = 1e6 — classic overfit surface against hidden instances explicitly "designed to include
various challenging aspects".

**Fix:** eva's acceptance rule becomes: fixed panel, N ≥ 5 paired runs, decide on median delta,
reject on any instance regressing beyond noise. And build a **synthetic instance generator** —
single bay (Z2 degenerate: only one u_j), many bays (8–10), zero-slack due dates, n = 500,
w2-dominant weights, pathological polygons. It is the cheapest insurance against distribution
shift, and nobody on the leaderboard is limited to the 40 train instances either.

## 6. The submission pipeline itself is an untested code path

As far as the repo shows, no dry-run submission has been made. Failure modes the PDF enumerates
that your loop doesn't cover: zip layout (myalgorithm.py at root, alns/ + baseline_greedy.py
included), 15 MB cap, fresh-env execution (missing-dependency = failure but latest *accepted*
submission still ranks — i.e., a broken accepted zip silently keeps scoring for you… as −1s),
email from the registered address, 12 h cooldown starting only on acceptance, hourly leaderboard
aggregation, and **document revisions** (you have v1.2 — the PDF says participants are responsible
for checking the website; there's also a Discord worth being in).

Also: final judgment = leaderboard **+ technical report + presentation + code review**, and all
finalist code is publicly disclosed. Your comment-dense style is an asset here; an experiment
ledger (§7) writes the technical report for you.

**Fix:** a `make_submission.sh` that builds the zip, unzips into a clean temp dir, and smoke-runs
prob_1 under Linux/4-core parity; then one *early real submission* purely to de-risk the pipeline.

## 7. Small but checkable: integer rounding of x, y

The server rounds location values before check_feasibility. CP-SAT paths emit ints; verify the
greedy/NFP-slide paths do too, and confirm `utils.check_feasibility` applies the same rounding
locally — a float that survives your verify but flips feasibility after server-side rounding would
be an invisible −1. One grep + one assertion at serialization time closes it forever.

---

## What would beat this algorithm?

Asked per your standing rule. Four answers, most dangerous first:

1. **Full per-bay decomposition.** Given the assignment, bays are *independent* for feasibility
   and Z1; only Z2/Z3 couple them. A competitor searching the assignment layer (MIP/LNS over
   assignments) with per-bay exact packing/scheduling as the evaluation oracle attacks the
   problem's actual structure; seed + destroy/repair ALNS attacks its surface. Your bayassign.py
   is the first step onto that ladder — the ceiling is much higher.
2. **Exactness on easy instances.** Rank scoring makes "Z1 = 0, then exactly minimize
   w2·Z2 + w3·Z3 at the assignment layer" a rank machine on Class A instances. You're heuristic
   there; someone will be exact.
3. **Exact EXIT/ENTRY retiming as an inner loop.** Tardiness depends only on EXIT; blocks may
   loiter; EXITs precede ENTRYs each day. For *fixed geometry*, optimal retiming is a clean
   per-bay subproblem (DP/CP over the crane-feasibility DAG). Running it after every accepted
   geometric move — not just inside fno — turns every ALNS accept into its best temporal self.
4. **30-minute-native designs.** A pipeline tuned at 60 s meets teams whose architecture was built
   for the long budget (massive restart portfolios, exhaustive fix-and-optimize schedules). §2 is
   the defense.

---

## How to prompt me better (the actual ask)

1. **State the currency.** "Optimize expected leaderboard rank under rank-based scoring" produces
   different advice than "improve the objective" — it re-weights robustness vs. average quality in
   everything I propose. Put it in CLAUDE.md so tom/eva inherit it too.
2. **Feed me the meta-game, not just the code.** The rules facts (§1, §6) were sitting in a PDF I
   had to read cold. A RULES.md in context changes every design conversation.
3. **Give raw numbers, not summaries.** "prob_39: 5.07M/5.64M vs 5.96M/6.04M over 2 reps" lets me
   judge noise; "improved ~5%" doesn't. Best: point me at eva's results/ CSVs (once they exist).
4. **Ask for kill criteria before code.** "Design the cheapest experiment that could falsify this
   idea; run it before tom implements." This inverts the current flow, where calibration happens
   after implementation and 2 reps decide.
5. **Schedule the red-team.** After each shipped change: "list the hidden-instance profiles where
   this loses, and every path by which it could produce a −1." And run *this* pass — a blindspot
   audit — on a cadence (e.g., weekly), not once. Unknown unknowns regenerate.
6. **Maintain the ledger in the repo, not in chat.** EXPERIMENTS.md: date, hypothesis, protocol,
   numbers, decision. It survives sessions, feeds the technical report, and lets any future
   conversation start from evidence instead of recollection.
7. **Session-start template.** Three lines: current best panel results, last submission tag, what
   changed since. (Cheap once §4 exists — I can read git log + results/ myself.)

---

## Priority order

1. Git: initial commit, .gitignore, submission tags. (§4 — enables everything else)
2. Server-parity rig: Linux, 4 pinned cores, thread caps; fix `repair.py` `num_search_workers=4`
   in chain context. (§3 — direct −1 risk)
3. Timelimit sweep {300, 900, 1800} + peak-RSS. (§2 — direct −1 risk)
4. Dry-run submission through a scripted zip. (§6)
5. Fix tom.md divergence; add RULES.md + EXPERIMENTS.md. (§4, §1, §7)
6. Eva stats protocol (N≥5, median, no-regression) + results/ persistence. (§5)
7. Synthetic instance generator. (§5)
8. Integer-rounding assertion. (§7)
