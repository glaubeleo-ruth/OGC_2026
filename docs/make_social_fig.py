"""Render docs/social_preview.png — 1280x640 (2:1) GitHub social preview.

Run from the repo root (python docs/make_social_fig.py) in the ogc2026 conda
env. Needs the local-only train/ directory. Single dark theme by design:
link cards render on arbitrary backgrounds, so the card commits to one look.
Upload manually: repo Settings -> General -> Social preview (the GitHub API
cannot set it).
"""
import json
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Rectangle

SURFACE = "#1a1a19"
INK = "#ffffff"
INK2 = "#c3c2b7"
MUTED = "#8a887e"
BAY = "#3987e5"
BAY_FILL = "#20262e"
BLUES = ["#3987e5", "#2c66b3", "#6ea6ea", "#1f4c85"]
ACCENT = "#d95926"
FONT = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]

d = json.load(open("train/prob_1.json"))
blocks = d["blocks"]
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


fig = plt.figure(figsize=(12.8, 6.4), dpi=100, facecolor=SURFACE)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_facecolor(SURFACE)
ax.set_xlim(0, 12.8)
ax.set_ylim(0, 6.4)
ax.axis("off")

# --- bay strip along the bottom --------------------------------------------
bx, by, bw, bh = 0.9, 0.55, 11.0, 2.0
ax.add_patch(Rectangle((bx, by), bw, bh, facecolor=BAY_FILL,
                       edgecolor=BAY, lw=2))
cell_w = bw / 8
for k, (bi, col, row) in enumerate(PLACED):
    cx = bx + ((col + 4 * row) + 0.5) * cell_w
    cy = by + bh / 2
    color = ACCENT if k == 5 else BLUES[k % len(BLUES)]
    for li, lay in enumerate(norm_layers(blocks[bi])):
        n = len(blocks[bi]["shape"][0]["layers"])
        shade = 0.55 + 0.45 * (li + 1) / n
        ax.add_patch(MplPolygon(
            [(cx + x * 1.35, cy + y * 1.35) for x, y in lay],
            closed=True, facecolor=color, alpha=shade,
            edgecolor=SURFACE, lw=0.9))

# --- title block ------------------------------------------------------------
x0 = 0.92
ax.text(x0, 5.62, "OPTIMIZATION GRAND CHALLENGE 2026",
        color=INK2, fontsize=15, family=FONT)
ax.plot([x0, x0 + 0.72], [5.38, 5.38], color=ACCENT, lw=4,
        solid_capstyle="butt")
ax.text(x0, 4.62, "The Grand Shipyard Puzzle",
        color=INK, fontsize=41, family=FONT, fontweight="bold")
ax.text(x0, 3.95, "Hybrid exact/metaheuristic solver for spatial block "
                  "scheduling in shipyard bays",
        color=INK2, fontsize=15.5, family=FONT)
ax.text(x0, 3.18, "LBBD matheuristic + ALNS  ·  100% feasible on every "
                  "official evaluation  ·  −99.6% objective on P3",
        color=MUTED, fontsize=12.5, family=FONT)

fig.savefig("docs/social_preview.png", facecolor=SURFACE)
print("written docs/social_preview.png (1280x640)")
