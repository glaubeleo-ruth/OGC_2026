# CLAUDE.md — OGC 2026 (Grand Shipyard Puzzle)

Competition entry: blocks must ENTER a shipyard bay, be placed (x, y, orient_idx),
and later EXIT, subject to crane entry/exit feasibility, collision, and boundary
constraints. Leaderboard score is the weighted objective; **infeasible, timeout,
or crash = -1**, so feasibility always outranks objective quality.

## Repo layout

- `baseline/sub/myalgorithm.py` — competition entry point (chimera: solver + frozen legacy hedge).
- `baseline/sub/baseline_greedy.py` — legacy seed construction.
- `baseline/sub/alns/` — legacy ALNS controller, destroy/repair operators, deadline, state, evaluation.
- `baseline/sub/solver/` — clean-slate solver, repair, bounds, and optional F17 experiment arm.
- `baseline/sub/utils.py` — official feasibility checker + geometry. **Same file used for official scoring.**
- `alg_tester/` — GUI tester: `conda activate ogc2026 && python alg_tester_app.py`.
- `../train/prob_1.json … prob_40.json` — training instances.
- `../problem-statement.pdf` — full rules and submission format.

## Hard rules (violating any of these can zero out a submission)

1. **Never change the entry-point signature**: `algorithm(prob_info: dict, timelimit: float) -> dict`.
2. **Never modify `utils.py`** — it is overwritten server-side; local edits silently diverge from official scoring.
3. `algorithm()` must **never raise and never return None**. Always keep a verified-feasible
   fallback (the seed) and return it if anything downstream fails or regresses.
4. **Verify before returning**: whatever is about to be returned must pass
   `utils.check_feasibility(prob_info, solution)["feasible"]`.
5. **Respect the deadline**: all ALNS work goes through the shared monotonic
   `alns.deadline.Deadline`. Effective budget is `max(1.0, timelimit * 0.93 - 1.0)`
   (server-speed safety factor — eval server has ≤4 cores). Overrun = -1.
6. **Multiprocessing uses the fork context only** (`_fork_context()` in myalgorithm.py).
   macOS spawn re-imports the main module and breaks under the test harness; no fork → sequential fallback.

## Solution wire format

```python
{"operations": {str(time_int): [op, ...]}}
# ENTRY op: {"type": "ENTRY", "block_id", "bay_id", "x", "y", "orient_idx"}
# EXIT  op: {"type": "EXIT",  "block_id", "bay_id"}
```

## Feasibility & objective (see utils.check_feasibility docstring)

Five ordered stages: (1) assignment validity, (2) crane entry, (3) crane exit,
(4) spatial collision/boundary, (5) sequential replay. Checker returns the
*earliest* failing stage plus violations.

- `obj1` = total tardiness Σ max(0, exit_time − due_date)
- `obj2` = max pairwise normalized bay-load imbalance
- `obj3` = bay-preference penalty Σ (S_max − S_assigned)
- `objective = w1·obj1 + w2·obj2 + w3·obj3` (weights come from the instance; lower is better)

## Headless test loop (preferred over the GUI for batch work)

```bash
cd baseline/sub && conda run -n ogc2026 python - <<'EOF'
import json, time
from myalgorithm import algorithm
import utils
prob = json.load(open("../../../train/prob_1.json"))
t0 = time.monotonic(); sol = algorithm(prob, 60); wall = time.monotonic() - t0
res = utils.check_feasibility(prob, sol)
print(res["feasible"], res["objective"], res["obj1"], res["obj2"], res["obj3"], f"wall={wall:.1f}s")
EOF
```

Always report: feasible?, objective + components, wall time vs limit, and delta vs
the untouched baseline (`baseline_greedy` with `improve=False` seed only).

## Working agreements

- **FINALE_PLAN.md defines each agent's current duties — check your phase before
  starting work.** It also holds the standing cadence, submission discipline, and
  escalation rules.
- Direction is decided in discussion first; **tom** (`.claude/agents/tom.md`) implements
  approved changes; **eva** (`.claude/agents/eva.md`) runs benchmark sweeps and verifies;
  **rex** (`.claude/agents/rex.md`) red-teams load-bearing claims and runs blindspot
  passes (findings continue the F-log in `../DESIGN_FROM_SCRATCH_2026-07-24.md`).
- Any timing-related change must state which WATCHDOG rule it serves (safety factor,
  seed-budget floor, deadline threading, infeasible-seed retry).
- Never delete or weaken the seed-fallback path to buy objective quality.
- Benchmark on multiple instances (small: prob_1–5, large: prob_10/14/40) before
  calling a change an improvement; single-instance wins are noise.
