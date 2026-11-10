"""One chart: the distribution of total float across the schedule.

Every scheduled activity contributes one value. The activities are split into
the same three groups the checks use (negative, 0..threshold, above threshold)
and drawn as a stacked histogram, so a bar's colour is decided per activity and
can never disagree with the finding counts, whatever the bin edges are.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

from matplotlib.figure import Figure
from matplotlib.patches import Patch

from .checks import CheckResult

# Status colours, validated for colour-vision deficiency and contrast against a
# light surface. The same three are used by the web UI.
NEGATIVE = "#b42318"
NORMAL = "#047857"
HIGH = "#d97706"


def histogram_data(result: CheckResult) -> dict:
    """The histogram as data, for the interactive chart in the web UI. The PNG
    below is drawn from exactly the same bins, so the two always agree.

    Each bin lists the activities that fall in it, grouped the same way the
    checks group them, so a click on a bar can show who is behind it."""
    thr = result.high_float_threshold_days
    if not (math.isfinite(thr) and thr > 0):
        raise ValueError(f"threshold must be a positive number, got {thr!r}")
    acts = result.activities  # (code, name, days), one per scheduled activity
    days = [d for _, _, d in acts]
    if not days:
        return {"threshold": thr, "bin_width": thr, "bins": []}
    lo = min(min(days), 0.0)
    hi = max(max(days), thr * 1.1)
    w = _bin_width(hi - lo, thr)
    edges = _edges(lo, hi, w)
    bins = [
        {"lo": a, "hi": b, "negative": 0, "ok": 0, "high": 0, "activities": []}
        for a, b in zip(edges, edges[1:])
    ]
    first = edges[0]
    for code, name, d in sorted(acts, key=lambda a: a[2]):
        i = min(int((d - first) // w), len(bins) - 1)
        # guard against float error at an exact edge
        if d < bins[i]["lo"] and i > 0:
            i -= 1
        elif d >= bins[i]["hi"] and i < len(bins) - 1:
            i += 1
        group = "negative" if d < 0 else "high" if d > thr else "ok"
        bins[i][group] += 1
        bins[i]["activities"].append({"code": code, "name": name, "days": round(d, 2), "group": group})
    return {"threshold": thr, "bin_width": w, "bins": bins}


def float_histogram(result: CheckResult, title: str | None = None) -> bytes:
    """Render the histogram and return PNG bytes."""
    days = result.float_days
    thr = result.high_float_threshold_days
    if not (math.isfinite(thr) and thr > 0):
        raise ValueError(f"threshold must be a positive number, got {thr!r}")

    neg = [d for d in days if d < 0]
    high = [d for d in days if d > thr]
    ok = [d for d in days if 0 <= d <= thr]

    # Using the Figure API directly (not pyplot) keeps this safe to call from
    # worker threads, which the web server does.
    fig = Figure(figsize=(9, 4.6), dpi=120)
    ax = fig.subplots()
    if days:
        lo = min(min(days), 0.0)
        hi = max(max(days), thr * 1.1)
        edges = _edges(lo, hi, _bin_width(hi - lo, thr))
        ax.hist([neg, ok, high], bins=edges, stacked=True, color=[NEGATIVE, NORMAL, HIGH], edgecolor="white", linewidth=0.6)
        top = ax.get_ylim()[1]
        ax.axvline(0, color=NEGATIVE, linestyle="--", linewidth=1)
        ax.axvline(thr, color=HIGH, linestyle="--", linewidth=1)
        ax.text(thr, top * 0.95, f" high float > {thr:g} d", color=HIGH, va="top", fontsize=9)
        ax.text(0, top * 0.95, "0 d ", color=NEGATIVE, va="top", ha="right", fontsize=9)
    else:
        ax.text(0.5, 0.5, "no scheduled activities (no float values in file)", ha="center", va="center", transform=ax.transAxes)

    ax.set_title(title or f"{result.file}: total float per activity")
    ax.set_xlabel("total float (working days, per activity calendar)")
    ax.set_ylabel("activities")
    ax.legend(
        handles=[
            Patch(color=NEGATIVE, label=f"negative: {len(neg)}"),
            Patch(color=NORMAL, label=f"0 to {thr:g} d: {len(ok)}"),
            Patch(color=HIGH, label=f"above {thr:g} d: {len(high)}"),
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
    return buf.getvalue()


def save_chart(result: CheckResult, path: str | Path) -> Path:
    path = Path(path)
    path.write_bytes(float_histogram(result))
    return path


def _bin_width(span: float, threshold: float) -> float:
    """A bin width that divides the threshold exactly, so the threshold line
    sits on a bar edge, giving at most ~45 bars where that is possible."""
    for divisor in (44, 22, 11, 4, 2, 1):
        w = threshold / divisor
        if span / w <= 45:
            return w
    # Very wide spread relative to the threshold: keep the threshold as an
    # edge and accept more bars rather than a straddling bar.
    return threshold


def _edges(lo: float, hi: float, w: float) -> list[float]:
    """Bin edges as exact multiples of w (no floating accumulation), covering
    [lo, hi] with 0 always on an edge."""
    first = math.floor(lo / w)
    last = math.ceil(hi / w) + 1
    return [i * w for i in range(first, last + 1)]
