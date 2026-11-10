from pathlib import Path

from p6checker import read_xer, run_checks
from p6checker.checks import float_in_days

FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parent.parent / "data"


def codes(result, check):
    return [f.task_code for f in result.findings[check]]


def test_negative_float_uses_calendar_hours():
    result = run_checks(read_xer(FIXTURES / "planted-defects.xer"))
    assert codes(result, "negative_float") == ["A020"]
    assert result.findings["negative_float"][0].value == -5.0  # -40h on an 8h calendar


def test_high_float_threshold_is_exclusive_and_calendar_aware():
    result = run_checks(read_xer(FIXTURES / "planted-defects.xer"))
    # A030: 500h on a 10h/day calendar = 50 days -> high
    # A050: 360h on 8h = 45 days -> high
    # A040: 352h on 8h = exactly 44 days -> not high (threshold is "above")
    assert codes(result, "high_float") == ["A030", "A050"]
    assert result.findings["high_float"][0].value == 50.0


def test_high_float_threshold_is_configurable():
    result = run_checks(read_xer(FIXTURES / "planted-defects.xer"), high_float_days=10)
    assert codes(result, "high_float") == ["A030", "A050", "A040"]


def test_missing_links_skips_loe_and_reports_which_side():
    result = run_checks(read_xer(FIXTURES / "planted-defects.xer"))
    found = {f.task_code: f.detail for f in result.findings["missing_links"]}
    # A000 start milestone has no predecessor (legitimately), A999 finish has no successor
    assert found["A000"] == "no predecessor"
    assert found["A999"] == "no successor"
    assert found["A050"] == "no predecessor and no successor"
    assert "LOE1" not in found  # level of effort carries no logic
    # the dangling relationships (999 <- 104, 104 <- 998) were quarantined, so A040
    # must still be seen as linked through its good relationships only
    assert "A040" not in found
    assert len(found) == 3


def test_unscheduled_activities_are_counted_not_flagged():
    result = run_checks(read_xer(FIXTURES / "planted-defects.xer"))
    assert result.unscheduled_count == 1  # LOE1 has an empty float
    assert result.activity_count == 8
    assert len(result.float_days) == 7


def test_float_in_days_falls_back_to_8h():
    assert float_in_days({"total_float_hr_cnt": "16", "clndr_id": "missing"}, {}) == 2.0
    assert float_in_days({"total_float_hr_cnt": "", "clndr_id": "10"}, {"10": 8}) is None


def test_real_airport_export_numbers():
    # Hand-checked against the raw file: 66 activities, all on 8h calendars,
    # max float 856h = 107 days, no negative float, 10 activities above 44 days,
    # one open start (first milestone) and one open end (last milestone).
    result = run_checks(read_xer(DATA / "terminal-building-airport.xer"))
    assert result.activity_count == 66
    assert result.unscheduled_count == 0
    assert result.count("negative_float") == 0
    assert result.count("high_float") == 10
    assert max(result.float_days) == 107.0
    assert sorted(f.detail for f in result.findings["missing_links"]) == ["no predecessor", "no successor"]
