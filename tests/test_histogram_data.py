"""The interactive chart's data must agree with the counts and with the PNG bins."""

from pathlib import Path

import pytest

from p6checker import read_xer, run_checks
from p6checker.chart import histogram_data, _edges, _bin_width

FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parent.parent / "data"


@pytest.mark.parametrize("name,thr", [
    ("tests/fixtures/planted-defects.xer", 44), ("tests/fixtures/planted-defects.xer", 10),
    ("data/terminal-building-airport.xer", 44), ("data/hotel-project.xer", 44), ("data/hotel-project.xer", 5),
])
def test_bins_sum_to_the_check_counts(name, thr):
    result = run_checks(read_xer(Path(__file__).parent.parent / name), high_float_days=thr)
    h = histogram_data(result)
    assert sum(b["negative"] for b in h["bins"]) == result.count("negative_float")
    assert sum(b["high"] for b in h["bins"]) == result.count("high_float")
    assert sum(b["ok"] for b in h["bins"]) == len(result.float_days) - result.count("negative_float") - result.count("high_float")
    assert sum(len(b["activities"]) for b in h["bins"]) == len(result.float_days)
    for b in h["bins"]:
        assert len(b["activities"]) == b["negative"] + b["ok"] + b["high"]
        for a in b["activities"]:
            assert b["lo"] <= a["days"] < b["hi"] or (a["days"] == b["hi"] and b is h["bins"][-1])


def test_bins_match_the_png_edges():
    result = run_checks(read_xer(FIXTURES / "planted-defects.xer"))
    h = histogram_data(result)
    days = result.float_days
    lo, hi = min(min(days), 0.0), max(max(days), 44 * 1.1)
    edges = _edges(lo, hi, _bin_width(hi - lo, 44))
    assert [b["lo"] for b in h["bins"]] == edges[:-1]
    assert h["bin_width"] == _bin_width(hi - lo, 44)


def test_exact_threshold_activity_is_ok_group():
    result = run_checks(read_xer(FIXTURES / "planted-defects.xer"))
    h = histogram_data(result)
    a040 = next(a for b in h["bins"] for a in b["activities"] if a["code"] == "A040")
    assert a040["days"] == 44.0 and a040["group"] == "ok"


def test_empty_schedule_gives_no_bins(tmp_path):
    p = tmp_path / "e.xer"
    p.write_text("ERMHDR\t6.0\n%T\tTASK\n%F\ttask_id\ttask_code\ttask_type\tstatus_code\ttotal_float_hr_cnt\n%R\t1\tA\tTT_Task\tTK_NotStart\t\n%E\n")
    assert histogram_data(run_checks(read_xer(p)))["bins"] == []
