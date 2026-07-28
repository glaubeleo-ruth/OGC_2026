"""Render docs/results.png for the README results section.

Run from the repo root (python docs/make_results_fig.py) in the ogc2026
conda env. Reads the sweep CSVs in ogc2026/baseline/results/; the hidden-set
numbers are inlined from 2026-07-26_submission_lineage.md.
"""
import csv
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#9a988f"
GRID = "#e7e6e1"
# categorical slots 1-6 (light mode)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
BLUE = "#2a78d6"

# --- data: hidden-set lineage (results/2026-07-26_submission_lineage.md) ----
attempts = ["#2\nJul 21", "#4\nJul 23", "#5\nJul 24", "#6\nJul 25"]
hidden = {
    "P1": [280494, 26150, 11280, 11280],
    "P2": [62696, 37748, 31368, 32068],
    "P3": [61634834, 515798, 186910, 376241],
    "P4": [36957614, 11570444, 8462228, 10854126],
    "P5": [220176080, 34867084, 20226241, 18630178],
    "P6": [601627045, 57616192, 52808786, 52828500],
}

# --- data: train sweeps ------------------------------------------------------
def read_sweep(path):
    out = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            inst = int(row["instance"])
            out[inst] = float(row["objective"]) if row["feasible"] == "True" else None
    return out

v0 = read_sweep("ogc2026/baseline/results/2026-07-25_solver_v0_full_sweep.csv")
v04 = read_sweep("ogc2026/baseline/results/2026-07-25_solver_v0.4_lbbd_full_sweep.csv")

fig = plt.figure(figsize=(12, 4.8), dpi=160, facecolor=SURFACE)
gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.35], wspace=0.24,
                      left=0.06, right=0.985, top=0.82, bottom=0.14)

# --- Panel A: hidden-set progression ----------------------------------------
ax = fig.add_subplot(gs[0])
ax.set_facecolor(SURFACE)
x = range(len(attempts))
for k, (name, vals) in enumerate(hidden.items()):
    ax.plot(x, vals, color=SERIES[k], lw=2, marker="o", ms=4.5,
            markerfacecolor=SERIES[k], markeredgecolor=SURFACE, markeredgewidth=1)
    ax.annotate(name, (len(attempts) - 1, vals[-1]), xytext=(8, 0),
                textcoords="offset points", va="center",
                color=INK2, fontsize=9)
ax.set_yscale("log")
ax.set_xticks(list(x), attempts)
ax.set_xlim(-0.25, len(attempts) - 0.45)
ax.set_ylabel("objective (log scale, lower is better)", color=INK2, fontsize=9)
ax.tick_params(colors=INK2, labelsize=8.5)
for s in ax.spines.values():
    s.set_visible(False)
ax.grid(axis="y", color=GRID, lw=0.7)
ax.set_axisbelow(True)
ax.set_title("Hidden-set score by accepted submission",
             color=INK, fontsize=11, loc="left", pad=18)
ax.text(0, 1.045, "six hidden instances P1–P6 · official leaderboard evaluations",
        transform=ax.transAxes, color=INK2, fontsize=8.5)

# --- Panel B: train sweep, solver v0 -> v0.4 dumbbells ----------------------
ax = fig.add_subplot(gs[1])
ax.set_facecolor(SURFACE)
insts = sorted(v04)
for i in insts:
    a, b = v0.get(i), v04[i]
    if a is not None and a != b:
        ax.plot([i, i], [a, b], color=GRID, lw=1.4, zorder=1)
        ax.plot(i, a, "o", color=MUTED, ms=3.6, zorder=2)
    ax.plot(i, b, "o", color=BLUE, ms=4.4, zorder=3,
            markeredgecolor=SURFACE, markeredgewidth=0.8)
for i in (38, 40):  # infeasible under v0, fixed in v0.4
    ax.annotate("was −1", (i, v04[i]), xytext=(0, 8), textcoords="offset points",
                ha="center", color="#eb6834", fontsize=7.5)
ax.set_yscale("log")
ax.set_xlabel("train instance", color=INK2, fontsize=9)
ax.set_ylabel("objective (log scale)", color=INK2, fontsize=9)
ax.tick_params(colors=INK2, labelsize=8.5)
for s in ax.spines.values():
    s.set_visible(False)
ax.grid(axis="y", color=GRID, lw=0.7)
ax.set_axisbelow(True)
ax.set_title("Train sweep: clean-slate solver v0 → v0.4",
             color=INK, fontsize=11, loc="left", pad=18)
ax.text(0, 1.045,
        "gray = v0 · blue = v0.4 (LBBD) · 40/40 feasible, 36 improved, 0 regressions",
        transform=ax.transAxes, color=INK2, fontsize=8.5)

fig.suptitle("Results", color=INK, fontsize=13, x=0.06, ha="left")
fig.savefig("docs/results.png", facecolor=SURFACE)
print("written docs/results.png")
