"""Render docs/results{,_dark}.png for the README results section.

Run from the repo root (python docs/make_results_fig.py) in the ogc2026
conda env. Reads the sweep CSVs in ogc2026/baseline/results/; the hidden-set
numbers are inlined from 2026-07-26_submission_lineage.md.
Emits a light and a dark variant; the README swaps them via <picture>.
"""
import csv
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e",
                  muted="#9a988f", grid="#e7e6e1", blue="#2a78d6",
                  orange="#eb6834",
                  series=["#2a78d6", "#eb6834", "#1baf7a",
                          "#eda100", "#e87ba4", "#008300"],
                  suffix=""),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7",
                 muted="#8a887e", grid="#2e2d2b", blue="#3987e5",
                 orange="#d95926",
                 series=["#3987e5", "#d95926", "#199e70",
                         "#c98500", "#d55181", "#3fae3f"],
                 suffix="_dark"),
}

# --- data: hidden-set lineage (results/2026-07-26_submission_lineage.md and
# results/2026-07-29_final_server_results.md) --------------------------------
attempts = ["#2\nJul 21", "#4\nJul 23", "#5\nJul 24", "#6\nJul 25",
            "final\nJul 29"]
hidden = {
    "P1": [280494, 26150, 11280, 11280, 11280],
    "P2": [62696, 37748, 31368, 32068, 32068],
    "P3": [61634834, 515798, 186910, 376241, 220494],
    "P4": [36957614, 11570444, 8462228, 10854126, 9289080],
    "P5": [220176080, 34867084, 20226241, 18630178, 18663403],
    "P6": [601627045, 57616192, 52808786, 52828500, 41948328],
}


def read_sweep(path):
    out = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            inst = int(row["instance"])
            out[inst] = float(row["objective"]) if row["feasible"] == "True" else None
    return out


v0 = read_sweep("ogc2026/baseline/results/2026-07-25_solver_v0_full_sweep.csv")
v04 = read_sweep("ogc2026/baseline/results/2026-07-25_solver_v0.4_lbbd_full_sweep.csv")


def render(t):
    fig = plt.figure(figsize=(12, 4.8), dpi=160, facecolor=t["surface"])
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.35], wspace=0.24,
                          left=0.06, right=0.985, top=0.82, bottom=0.14)

    # --- Panel A: hidden-set progression ------------------------------------
    ax = fig.add_subplot(gs[0])
    ax.set_facecolor(t["surface"])
    x = range(len(attempts))
    for k, (name, vals) in enumerate(hidden.items()):
        c = t["series"][k]
        ax.plot(x, vals, color=c, lw=2, marker="o", ms=4.5,
                markerfacecolor=c, markeredgecolor=t["surface"],
                markeredgewidth=1)
        ax.annotate(name, (len(attempts) - 1, vals[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center",
                    color=t["ink2"], fontsize=9)
    ax.set_yscale("log")
    ax.set_xticks(list(x), attempts)
    ax.set_xlim(-0.25, len(attempts) - 0.45)
    ax.set_ylabel("objective (log scale, lower is better)", color=t["ink2"],
                  fontsize=9)
    ax.tick_params(colors=t["ink2"], labelsize=8.5)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(axis="y", color=t["grid"], lw=0.7)
    ax.set_axisbelow(True)
    ax.set_title("Hidden-set score by accepted submission",
                 color=t["ink"], fontsize=11, loc="left", pad=18)
    ax.text(0, 1.045,
            "six hidden instances P1–P6 · official leaderboard evaluations",
            transform=ax.transAxes, color=t["ink2"], fontsize=8.5)

    # --- Panel B: train sweep, solver v0 -> v0.4 dumbbells ------------------
    ax = fig.add_subplot(gs[1])
    ax.set_facecolor(t["surface"])
    for i in sorted(v04):
        a, b = v0.get(i), v04[i]
        if a is not None and a != b:
            ax.plot([i, i], [a, b], color=t["grid"], lw=1.4, zorder=1)
            ax.plot(i, a, "o", color=t["muted"], ms=3.6, zorder=2)
        ax.plot(i, b, "o", color=t["blue"], ms=4.4, zorder=3,
                markeredgecolor=t["surface"], markeredgewidth=0.8)
    for i in (38, 40):  # infeasible under v0, fixed in v0.4
        ax.annotate("was −1", (i, v04[i]), xytext=(0, 8),
                    textcoords="offset points", ha="center",
                    color=t["orange"], fontsize=7.5)
    ax.set_yscale("log")
    ax.set_xlabel("train instance", color=t["ink2"], fontsize=9)
    ax.set_ylabel("objective (log scale)", color=t["ink2"], fontsize=9)
    ax.tick_params(colors=t["ink2"], labelsize=8.5)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(axis="y", color=t["grid"], lw=0.7)
    ax.set_axisbelow(True)
    ax.set_title("Train sweep: clean-slate solver v0 → v0.4",
                 color=t["ink"], fontsize=11, loc="left", pad=18)
    ax.text(0, 1.045,
            "gray = v0 · blue = v0.4 (LBBD) · 40/40 feasible, 36 improved, "
            "0 regressions",
            transform=ax.transAxes, color=t["ink2"], fontsize=8.5)

    fig.suptitle("Results", color=t["ink"], fontsize=13, x=0.06, ha="left")
    out = f"docs/results{t['suffix']}.png"
    fig.savefig(out, facecolor=t["surface"])
    plt.close(fig)
    print("written", out)


for theme in THEMES.values():
    render(theme)
