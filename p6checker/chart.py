"""One chart: the distribution of total float across the schedule.

Every scheduled activity contributes one value. Bars are coloured by band:
red for negative float, green for 0..threshold, amber above the threshold.
The same thresholds drive the negative-float and high-float checks, so the
chart and the finding counts always agree.
"""

from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless; no display needed
import matplotlib.pyplot as plt  # noqa: E402

from .checks import CheckResult  # noqa: E402

NEGATIVE = "#c0392b"
NORMAL = "#2e8b57"
HIGH = "#e67e22"


def float_histogram(result: CheckResult, title: str | None = None) -> bytes:
    """Render the histogram and return PNG bytes."""
    days = result.float_days
    thr = result.high_float_threshold_days

    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=120)
    if days:
        lo, hi = min(days), max(days)
        lo = min(lo, 0.0)
        hi = max(hi, thr * 1.1)
        bin_width = _nice_bin_width(hi - lo, thr)
        edges = _edges(lo, hi, bin_width)
        # An activity sitting exactly on the threshold is *not* high float (the
        # check is "above"), so keep it in the green bin to the left of the line.
        plotted = [d - 1e-9 if d == thr else d for d in days]
        counts, edges, patches = ax.hist(plotted, bins=edges, edgecolor="white", linewidth=0.6)
        for left, patch in zip(edges[:-1], patches):
            if left < 0:
                patch.set_facecolor(NEGATIVE)
            elif left >= thr:
                patch.set_facecolor(HIGH)
            else:
                patch.set_facecolor(NORMAL)
        ax.axvline(0, color=NEGATIVE, linestyle="--", linewidth=1)
        ax.axvline(thr, color=HIGH, linestyle="--", linewidth=1)
        ax.text(thr, ax.get_ylim()[1] * 0.95, f" high float > {thr:g} d", color=HIGH, va="top", fontsize=9)
        ax.text(0, ax.get_ylim()[1] * 0.95, " 0 d", color=NEGATIVE, va="top", ha="right", fontsize=9)
    else:
        ax.text(0.5, 0.5, "no scheduled activities (no float values in file)", ha="center", va="center", transform=ax.transAxes)

    n_neg = result.count("negative_float")
    n_high = result.count("high_float")
    n_ok = len(days) - n_neg - n_high
    ax.set_title(title or f"{result.file}: total float per activity")
    ax.set_xlabel("total float (working days, per activity calendar)")
    ax.set_ylabel("activities")
    ax.legend(
        handles=[
            plt.Rectangle((0, 0), 1, 1, color=NEGATIVE, label=f"negative: {n_neg}"),
            plt.Rectangle((0, 0), 1, 1, color=NORMAL, label=f"0 to {thr:g} d: {n_ok}"),
            plt.Rectangle((0, 0), 1, 1, color=HIGH, label=f"above {thr:g} d: {n_high}"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.22),
        ncol=3,
        frameon=False,
    )
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def save_chart(result: CheckResult, path: str | Path) -> Path:
    path = Path(path)
    path.write_bytes(float_histogram(result))
    return path


def _nice_bin_width(span: float, threshold: float) -> float:
    """Pick a bin width that divides the threshold exactly (so the threshold
    line always sits on a bar edge and no bar straddles it) and gives at most
    ~45 bars."""
    for divisor in (44, 22, 11, 4, 2, 1):
        w = threshold / divisor
        if w > 0 and span / w <= 45:
            return w
    w = threshold
    while span / w > 45:
        w *= 2
    return w


def _edges(lo: float, hi: float, w: float) -> list[float]:
    import math

    start = math.floor(lo / w) * w
    stop = math.ceil(hi / w) * w + w
    edges = []
    x = start
    while x <= stop:
        edges.append(x)
        x += w
    return edges
