"""Render the repo's header art — one composition, three outputs:

  docs/banner.png        2560x640 (4:1), light   — README header
  docs/banner_dark.png   2560x640 (4:1), dark    — README header (dark mode)
  docs/social_preview.png 1280x640 (2:1), dark   — GitHub social preview
                          (upload manually: Settings -> Social preview;
                           the GitHub API cannot set it)

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

LIGHT = dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e",
             muted="#9a988f", bay="#2a78d6", bay_fill="#eef3fa",
             blues=["#2a78d6", "#5b95dd", "#8db4e6", "#1e5ea8"],
             accent="#eb6834")
DARK = dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7",
            muted="#8a887e", bay="#3987e5", bay_fill="#20262e",
            blues=["#3987e5", "#2c66b3", "#6ea6ea", "#1f4c85"],
            accent="#d95926")

FONT = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]

d = json.load(open("train/prob_1.json"))
blocks = d["blocks"]

# real shapes: (block index, grid col, grid row); index 5 is the accent
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


def draw_bay(ax, t, bx, by, bw, bh, scale):
    ax.add_patch(Rectangle((bx, by), bw, bh, facecolor=t["bay_fill"],
                           edgecolor=t["bay"], lw=1.8))
    cell_w, cell_h = bw / 4, bh / 2
    for k, (bi, col, row) in enumerate(PLACED):
        cx = bx + (col + 0.5) * cell_w
        cy = by + (row + 0.5) * cell_h
        color = t["accent"] if k == 5 else t["blues"][k % len(t["blues"])]
        for li, lay in enumerate(norm_layers(blocks[bi])):
            n = len(blocks[bi]["shape"][0]["layers"])
            shade = 0.55 + 0.45 * (li + 1) / n
            ax.add_patch(MplPolygon(
                [(cx + x * scale, cy + y * scale) for x, y in lay],
                closed=True, facecolor=color, alpha=shade,
                edgecolor=t["surface"], lw=0.9))
    ax.text(bx + bw, by - 0.18, "block geometry from training instance prob_1",
            ha="right", va="top", color=t["muted"], fontsize=8, family=FONT)


def draw_text(ax, t, x0, cy):
    """Title block, vertically centered on cy (same content everywhere)."""
    ax.text(x0, cy + 1.14, "OPTIMIZATION GRAND CHALLENGE 2026",
            color=t["ink2"], fontsize=12.5, family=FONT)
    ax.plot([x0, x0 + 0.62], [cy + 0.94, cy + 0.94], color=t["accent"], lw=3,
            solid_capstyle="butt")
    ax.text(x0, cy + 0.30, "The Grand Shipyard Puzzle",
            color=t["ink"], fontsize=34, family=FONT, fontweight="bold")
    ax.text(x0, cy - 0.40, "Pack the block, beat the clock — hybrid "
                           "exact/metaheuristic\nsolver for spatial block "
                           "scheduling in shipyard bays.",
            color=t["ink2"], fontsize=13, family=FONT, va="top",
            linespacing=1.5)
    ax.text(x0, cy - 1.40,
            "TEAM SANDLE   ·   LBBD MATHEURISTIC   ·   ALNS   ·   CP-SAT",
            color=t["muted"], fontsize=10, family=FONT)


def render(t, w_in, h_in, out):
    fig = plt.figure(figsize=(w_in, h_in), dpi=160 if w_in == 16 else 100,
                     facecolor=t["surface"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(t["surface"])
    ax.set_xlim(0, w_in)
    ax.set_ylim(0, h_in)
    ax.axis("off")
    cy = h_in / 2
    draw_text(ax, t, 0.053 * w_in, cy)
    # bay on the right: same proportional position and aspect in both formats
    bx, bw = 0.57 * w_in, 0.388 * w_in
    bh = min(h_in - 1.4, bw * 0.41)
    draw_bay(ax, t, bx, cy - bh / 2, bw, bh, scale=bh * 0.46)
    fig.savefig(out, facecolor=t["surface"])
    plt.close(fig)
    print("written", out)


render(LIGHT, 16, 4, "docs/banner.png")
render(DARK, 16, 4, "docs/banner_dark.png")
render(DARK, 12.8, 6.4, "docs/social_preview.png")
