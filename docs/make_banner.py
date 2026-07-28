"""Render docs/banner{,_dark}.png — README header banner.

Run from the repo root (python docs/make_banner.py) in the ogc2026 conda
env. Needs the local-only train/ directory: the geometry on the right is
real block polygons from train/prob_1.json. Titles prefer Helvetica Neue
(macOS) and fall back to the matplotlib default elsewhere.
"""
import json
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Rectangle

THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e",
                  muted="#9a988f", bay="#2a78d6", bay_fill="#eef3fa",
                  blues=["#2a78d6", "#5b95dd", "#8db4e6", "#1e5ea8"],
                  accent="#eb6834", suffix=""),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7",
                 muted="#8a887e", bay="#3987e5", bay_fill="#20262e",
                 blues=["#3987e5", "#2c66b3", "#6ea6ea", "#1f4c85"],
                 accent="#d95926", suffix="_dark"),
}

FONT = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]

d = json.load(open("train/prob_1.json"))
blocks = d["blocks"]

# hand-picked spread of shapes; (block index, grid col, grid row)
PLACED = [(0, 0, 0), (9, 1, 0), (27, 2, 0), (45, 0, 1),
          (63, 1, 1), (81, 2, 1), (36, 3, 0), (99, 3, 1)]


def norm_layers(blk):
    layers = blk["shape"][0]["layers"]
    xs = [p[0] for lay in layers for p in lay]
    ys = [p[1] for lay in layers for p in lay]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    s = 1.0 / max(w, h)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return [[((x - cx) * s, (y - cy) * s) for x, y in lay] for lay in layers]


def render(t):
    fig = plt.figure(figsize=(16, 4), dpi=160, facecolor=t["surface"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(t["surface"])
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 4)
    ax.axis("off")

    # --- right: a bay strip with real block polygons ------------------------
    bx, by, bw, bh = 9.1, 0.72, 6.2, 2.56
    ax.add_patch(Rectangle((bx, by), bw, bh, facecolor=t["bay_fill"],
                           edgecolor=t["bay"], lw=1.8))
    cell_w, cell_h = bw / 4, bh / 2
    for k, (bi, col, row) in enumerate(PLACED):
        cx = bx + (col + 0.5) * cell_w
        cy = by + (row + 0.5) * cell_h
        scale = 1.18
        color = t["accent"] if k == 5 else t["blues"][k % len(t["blues"])]
        for li, lay in enumerate(norm_layers(blocks[bi])):
            nl = len(blocks[bi]["shape"][0]["layers"])
            shade = 0.55 + 0.45 * (li + 1) / nl
            ax.add_patch(MplPolygon(
                [(cx + x * scale, cy + y * scale) for x, y in lay],
                closed=True, facecolor=color, alpha=shade,
                edgecolor=t["surface"], lw=0.9))
    ax.text(bx + bw, by - 0.18, "block geometry from training instance prob_1",
            ha="right", va="top", color=t["muted"], fontsize=8,
            family=FONT)

    # --- left: title block --------------------------------------------------
    x0 = 0.85
    ax.text(x0, 3.06, "OPTIMIZATION GRAND CHALLENGE 2026",
            color=t["ink2"], fontsize=12.5, family=FONT,
            fontweight="medium")
    # letter-spaced eyebrow effect: draw a thin rule under it instead
    ax.plot([x0, x0 + 0.62], [2.86, 2.86], color=t["accent"], lw=3,
            solid_capstyle="butt")
    ax.text(x0, 2.22, "The Grand Shipyard Puzzle",
            color=t["ink"], fontsize=34, family=FONT, fontweight="bold")
    ax.text(x0, 1.52, "Pack the block, beat the clock — hybrid exact/metaheuristic\n"
                      "solver for spatial block scheduling in shipyard bays.",
            color=t["ink2"], fontsize=13, family=FONT, va="top",
            linespacing=1.5)
    ax.text(x0, 0.52, "TEAM SANDLE   ·   LBBD MATHEURISTIC   ·   ALNS   ·   CP-SAT",
            color=t["muted"], fontsize=10, family=FONT)

    out = f"docs/banner{t['suffix']}.png"
    fig.savefig(out, facecolor=t["surface"])
    plt.close(fig)
    print("written", out)


for theme in THEMES.values():
    render(theme)
