# RIG_SETUP.md — running the gauntlet on the Linux box

Target machine: any Linux x86_64 with ≥4 cores and ≥16 GB RAM (GPU unused — the
solver is CPU/CP-SAT only). Total setup ≈ 10 min; gauntlet run ≈ 85 min.

## 1. Copy the code

On the Mac, the whole repo (code + all 40 train instances) is packed as a git
bundle at the repo root: `ogc2026_rig.bundle` (~75 MB). Copy it over, e.g.:

```bash
scp ogc2026_rig.bundle user@linuxbox:~/
```

On the Linux box:

```bash
git clone ogc2026_rig.bundle OGC_2026 && cd OGC_2026
git log --oneline -3   # confirm HEAD matches the hash the Mac reported
```

## 2. Environment (minimal — 3 packages)

The entry imports exactly: numpy, shapely, ortools (lazy). Python 3.12 to match
the official env. With conda/mamba/micromamba:

```bash
conda create -y -n ogc2026 python=3.12
conda activate ogc2026
pip install numpy "shapely>=2.1.0" ortools==9.15.6755
```

(The full official env is `ogc2026/ogc2026_env.yml` — it drags torch/tensorflow
and is NOT needed for the gauntlet.)

## 3. Run

```bash
conda activate ogc2026
bash ogc2026/rig/rig_gauntlet.sh
```

What it does, in order:
1. Builds the submission zip FRESH from `ogc2026/baseline/sub/` and byte-verifies
   the zip contents against a sha256 manifest of the tree (stale-zip guard —
   aborts on mismatch).
2. Runs the full 40-instance panel at t=60 plus spot checks (prob_21/31/38/40)
   at t=300, each run pinned with `taskset -c 0-3`, single-threaded solver env,
   hard external timeout t+5 (timeout ⇒ recorded as −1, never dropped).
3. Prints the eligibility checklist: 0×−1, RSS < 12 GB, wall lines at 0.90t and
   0.95t (the 0.93t−1 internal budget makes 0.90t breach BY DESIGN at t≥300 —
   Leo's margin ruling decides which line governs).

Overrides: `CORES=0-3 T=60 SPOT_T=300 SPOTS="21 31 38 40"` as env vars.

## 3b. Forced-kill wall measurement (one extra run, high value)

The entry's failure path (solver dead + hedge SIGKILLed) is DESIGNED to run to
~0.985× the raw timelimit and has never been measured on server-like hardware
(finding 20260727c-6). The natural gauntlet never enters it. Capture it once:

```bash
cd ogc2026/baseline/sub
PYTHONPATH=$PWD taskset -c 0-3 env OMP_NUM_THREADS=1 \
  python ../../rig/forced_kill_test.py prob_38 pure raise
```

PASS = the printed FORCED line shows `"feasible": true`, `"n_ops": 500`, and
`"overran_raw_limit": false` with wall < 60. Repeat for prob_17 if time allows.
Include the FORCED output line(s) in what you send back.

## 4. Send back

Two files: the results CSV (path printed at the end) and the built zip. The zip
is the exact artifact to submit if eva stamps SUBMIT-ELIGIBLE from the CSV.
Do not rebuild the zip on the Mac afterwards — the gauntleted bytes are the
submitted bytes.
