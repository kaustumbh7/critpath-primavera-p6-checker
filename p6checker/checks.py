"""Schedule-health checks run over a parsed XerFile.

Three checks, all deterministic and all computed from the file's own numbers:

* missing links   - activities with no predecessor or no successor
                    (open ends make the critical path meaningless)
* negative float  - total float below zero (the activity is already late
                    against a constraint or deadline)
* high float      - total float above a threshold, 44 working days by default
                    (the DCMA 14-point assessment threshold; usually means
                    the activity is not properly tied into the network)

Float is stored in the file in hours. It is converted to working days using
the activity's own calendar (CALENDAR.day_hr_cnt), so an 8h/day activity and
a 10h/day activity are compared on the same footing.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from .parser import XerFile, LINE_KEY

DEFAULT_HIGH_FLOAT_DAYS = 44.0
DEFAULT_HOURS_PER_DAY = 8.0

# Level-of-effort and WBS-summary "activities" take their dates from other
# activities and are not expected to carry logic, so they are skipped by the
# missing-links check. Milestones are real schedule points and are included.
NON_LOGIC_TASK_TYPES = {"TT_LOE", "TT_WbsSumm"}

CHECK_NAMES = ("missing_links", "negative_float", "high_float")
CHECK_LABELS = {
    "missing_links": "Missing links",
    "negative_float": "Negative float",
    "high_float": "High float",
}


@dataclass
class Finding:
    check: str
    task_code: str
    task_name: str
    task_type: str
    detail: str
    value: float | None = None  # float in days where relevant
    line: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class CheckResult:
    file: str
    activity_count: int  # activities that took part in the checks
    unscheduled_count: int  # activities with no float value (never scheduled)
    high_float_threshold_days: float
    findings: dict[str, list[Finding]]
    float_days: list[float]  # one value per scheduled activity, for the chart

    def count(self, check: str) -> int:
        return len(self.findings[check])

    def as_dict(self) -> dict:
        return {
            "file": self.file,
            "activity_count": self.activity_count,
            "unscheduled_count": self.unscheduled_count,
            "high_float_threshold_days": self.high_float_threshold_days,
            "counts": {c: self.count(c) for c in CHECK_NAMES},
            "findings": {c: [f.as_dict() for f in fs] for c, fs in self.findings.items()},
        }


def calendar_hours_per_day(xer: XerFile) -> dict[str, float]:
    """clndr_id -> working hours per day, from the CALENDAR table."""
    hours: dict[str, float] = {}
    for row in xer.table("CALENDAR").rows:
        value = row.get("day_hr_cnt", "").strip()
        if value:
            h = float(value)
            if h > 0:
                hours[row["clndr_id"]] = h
    return hours


def float_in_days(task: dict[str, str], hours_per_day: dict[str, float]) -> float | None:
    raw = task.get("total_float_hr_cnt", "").strip()
    if raw == "":
        return None
    per_day = hours_per_day.get(task.get("clndr_id", ""), DEFAULT_HOURS_PER_DAY)
    return float(raw) / per_day


def run_checks(xer: XerFile, high_float_days: float = DEFAULT_HIGH_FLOAT_DAYS) -> CheckResult:
    tasks = xer.table("TASK").rows
    hours_per_day = calendar_hours_per_day(xer)

    findings: dict[str, list[Finding]] = {c: [] for c in CHECK_NAMES}
    float_days: list[float] = []
    unscheduled = 0

    # --- missing links -----------------------------------------------------
    has_pred: set[str] = set()
    has_succ: set[str] = set()
    for rel in xer.table("TASKPRED").rows:
        has_pred.add(rel["task_id"])
        has_succ.add(rel["pred_task_id"])

    for t in tasks:
        if t["task_type"] in NON_LOGIC_TASK_TYPES:
            continue
        missing = []
        if t["task_id"] not in has_pred:
            missing.append("no predecessor")
        if t["task_id"] not in has_succ:
            missing.append("no successor")
        if missing:
            findings["missing_links"].append(_finding("missing_links", t, " and ".join(missing)))

    # --- float checks ------------------------------------------------------
    for t in tasks:
        days = float_in_days(t, hours_per_day)
        if days is None:
            unscheduled += 1
            continue
        float_days.append(days)
        if days < 0:
            findings["negative_float"].append(_finding("negative_float", t, f"total float {days:.1f} days", days))
        elif days > high_float_days:
            findings["high_float"].append(
                _finding("high_float", t, f"total float {days:.1f} days (threshold {high_float_days:g})", days)
            )

    for fs in findings.values():
        fs.sort(key=lambda f: (f.value if f.value is not None else 0, f.task_code))
    findings["high_float"].reverse()  # largest float first

    return CheckResult(
        file=xer.path.name,
        activity_count=len(tasks),
        unscheduled_count=unscheduled,
        high_float_threshold_days=high_float_days,
        findings=findings,
        float_days=float_days,
    )


def _finding(check: str, t: dict[str, str], detail: str, value: float | None = None) -> Finding:
    return Finding(
        check=check,
        task_code=t.get("task_code", ""),
        task_name=t.get("task_name", ""),
        task_type=t.get("task_type", ""),
        detail=detail,
        value=None if value is None else round(value, 2),
        line=int(t.get(LINE_KEY, 0)),
    )
