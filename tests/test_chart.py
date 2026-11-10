"""The chart must agree with the counts at every threshold, not just 44."""

from pathlib import Path

import pytest

from p6checker import read_xer, run_checks
from p6checker.chart import _edges, _bin_width, float_histogram

FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parent.parent / "data"


@pytest.mark.parametrize("thr", [0.5, 1, 5, 14, 17, 30, 44, 44.5, 58, 69, 75, 106, 300, 1000])
def test_edges_are_exact_and_contain_zero_and_threshold(thr):
    result = run_checks(read_xer(FIXTURES / "planted-defects.xer"), high_float_days=thr)
    days = result.float_days
    lo, hi = min(min(days), 0.0), max(max(days), thr * 1.1)
    w = _bin_width(hi - lo, thr)
    edges = _edges(lo, hi, w)
    assert 0.0 in edges
    assert any(abs(e - thr) < 1e-9 for e in edges), (thr, w, edges)
    assert edges[0] <= lo and edges[-1] >= hi
    assert all(b - a == pytest.approx(w) for a, b in zip(edges, edges[1:]))


@pytest.mark.parametrize("name", ["terminal-building-airport.xer", "hotel-project.xer"])
@pytest.mark.parametrize("thr", [1, 5, 44, 58, 120, 500])
def test_real_files_render_at_many_thresholds(name, thr):
    result = run_checks(read_xer(DATA / name), high_float_days=thr)
    png = float_histogram(result)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_chart_rejects_bad_threshold():
    result = run_checks(read_xer(FIXTURES / "planted-defects.xer"))
    result.high_float_threshold_days = 0
    with pytest.raises(ValueError):
        float_histogram(result)
