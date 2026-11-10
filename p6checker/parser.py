"""Reader for Primavera P6 .xer files.

An XER file is a tab-separated text file. The first line is an ``ERMHDR``
header. After that, each line starts with a record type:

    %T <table name>      start of a table
    %F <field> <field>…  column names for the current table
    %R <value> <value>…  one row of the current table
    %E                   end of file

P6 writes the file in Windows-1252, not UTF-8. Real exports are usually well
formed, but files that have been edited by hand, truncated, or exported by
third-party tools are not. Anything that does not fit the structure above, or
that would make a check produce a wrong number, is quarantined as a
``BrokenRow`` with the line number and a reason, and excluded from the checks.
The parser never silently drops data and never raises on a bad row; it only
raises when the whole file is unusable (no ERMHDR, empty, undecodable).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DATE_FORMAT = "%Y-%m-%d %H:%M"
LINE_KEY = "__line__"  # source line number, kept on every row for error messages

# Fields that a check depends on. A row missing one of these, or holding an
# unparseable value in one, cannot be checked and is quarantined.
REQUIRED_FIELDS = {
    "TASK": ("task_id", "task_code", "task_type", "status_code"),
    "TASKPRED": ("task_pred_id", "task_id", "pred_task_id"),
    "CALENDAR": ("clndr_id",),
    "PROJECT": ("proj_id",),
}
NUMERIC_FIELDS = {
    "TASK": ("total_float_hr_cnt", "free_float_hr_cnt"),
    "TASKPRED": ("lag_hr_cnt",),
    "CALENDAR": ("day_hr_cnt",),
}
DATE_FIELDS = {
    "TASK": ("early_start_date", "early_end_date", "late_start_date", "late_end_date"),
}


class XerFormatError(Exception):
    """The file is not an XER file at all (no header, empty, undecodable)."""


@dataclass
class BrokenRow:
    line_no: int
    table: str | None
    reason: str
    raw: str

    def as_dict(self) -> dict:
        return {"line": self.line_no, "table": self.table, "reason": self.reason, "raw": self.raw[:200]}


@dataclass
class Table:
    name: str
    fields: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.rows)


@dataclass
class XerFile:
    path: Path
    encoding: str
    header: list[str]
    tables: dict[str, Table]
    broken: list[BrokenRow]
    line_count: int

    def table(self, name: str) -> Table:
        """Return the table, or an empty one if the file does not have it."""
        return self.tables.get(name) or Table(name)

    @property
    def version(self) -> str:
        return self.header[1] if len(self.header) > 1 else "?"

    @property
    def export_date(self) -> str:
        return self.header[2] if len(self.header) > 2 else "?"


def decode_xer(raw: bytes) -> tuple[str, str]:
    """XER files are normally Windows-1252. Try UTF-8 first (it is strict and
    will reject genuine cp1252 bytes), then fall back. Returns (text, encoding)."""
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "cp1252"


def read_xer(path: str | Path) -> XerFile:
    path = Path(path)
    raw = path.read_bytes()
    if not raw.strip():
        raise XerFormatError(f"{path.name}: file is empty")
    text, encoding = decode_xer(raw)
    lines = text.splitlines()

    if not lines or not lines[0].startswith("ERMHDR"):
        raise XerFormatError(f"{path.name}: first line must start with ERMHDR; this is not a P6 XER export")
    header = lines[0].split("\t")

    tables: dict[str, Table] = {}
    broken: list[BrokenRow] = []
    current: Table | None = None
    saw_end = False

    for line_no, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue  # blank lines carry no data; not worth flagging
        if saw_end:
            broken.append(BrokenRow(line_no, None, "data after %E end-of-file marker", line))
            continue
        parts = line.split("\t")
        kind = parts[0]

        if kind == "%T":
            name = parts[1].strip() if len(parts) > 1 else ""
            if not name:
                broken.append(BrokenRow(line_no, None, "%T with no table name", line))
                current = None
                continue
            current = tables.setdefault(name, Table(name))
        elif kind == "%F":
            if current is None:
                broken.append(BrokenRow(line_no, None, "%F field list before any %T table", line))
                continue
            current.fields = [f.strip() for f in parts[1:]]
        elif kind == "%R":
            if current is None:
                broken.append(BrokenRow(line_no, None, "%R row before any %T table", line))
                continue
            if not current.fields:
                broken.append(BrokenRow(line_no, current.name, "%R row before the table's %F field list", line))
                continue
            values = parts[1:]
            if len(values) != len(current.fields):
                broken.append(
                    BrokenRow(
                        line_no,
                        current.name,
                        f"expected {len(current.fields)} fields, got {len(values)}",
                        line,
                    )
                )
                continue
            row = dict(zip(current.fields, values))
            reason = _validate_row(current.name, row)
            if reason:
                broken.append(BrokenRow(line_no, current.name, reason, line))
                continue
            row[LINE_KEY] = str(line_no)
            current.rows.append(row)
        elif kind == "%E":
            saw_end = True
        else:
            broken.append(BrokenRow(line_no, current.name if current else None, f"unknown record type {kind!r}", line))

    _validate_references(tables, broken)
    broken.sort(key=lambda b: b.line_no)

    return XerFile(
        path=path,
        encoding=encoding,
        header=header,
        tables=tables,
        broken=broken,
        line_count=len(lines),
    )


def _validate_row(table: str, row: dict[str, str]) -> str | None:
    """Return a reason string if this row cannot be trusted by the checks."""
    for name in REQUIRED_FIELDS.get(table, ()):
        if name not in row:
            return f"missing required column {name!r}"
        if row[name].strip() == "":
            return f"required field {name!r} is empty"
    for name in NUMERIC_FIELDS.get(table, ()):
        value = row.get(name, "")
        if value.strip() == "":
            continue  # P6 leaves float empty on unscheduled activities; that is legitimate
        try:
            float(value)
        except ValueError:
            return f"{name}={value!r} is not a number"
    for name in DATE_FIELDS.get(table, ()):
        value = row.get(name, "")
        if value.strip() == "":
            continue
        if parse_date(value) is None:
            return f"{name}={value!r} is not a P6 date (YYYY-MM-DD HH:MM)"
    return None


def _validate_references(tables: dict[str, Table], broken: list[BrokenRow]) -> None:
    """Cross-row checks: duplicate task ids and relationships that point at
    activities which do not exist. Both would corrupt the missing-links check."""
    task = tables.get("TASK")
    if task is None:
        return
    seen: dict[str, int] = {}
    kept: list[dict[str, str]] = []
    for row in task.rows:
        tid = row["task_id"]
        if tid in seen:
            first = kept[seen[tid]]
            broken.append(BrokenRow(_line(row), "TASK", f"duplicate task_id {tid!r} (already used by {first['task_code']!r} on line {_line(first)})", _raw(row)))
            continue
        seen[tid] = len(kept)
        kept.append(row)
    task.rows = kept

    pred = tables.get("TASKPRED")
    if pred is None:
        return
    ids = set(seen)
    kept = []
    for row in pred.rows:
        if row["task_id"] not in ids:
            broken.append(BrokenRow(_line(row), "TASKPRED", f"successor task_id {row['task_id']!r} does not exist in TASK", _raw(row)))
        elif row["pred_task_id"] not in ids:
            broken.append(BrokenRow(_line(row), "TASKPRED", f"predecessor task_id {row['pred_task_id']!r} does not exist in TASK", _raw(row)))
        else:
            kept.append(row)
    pred.rows = kept


def _line(row: dict[str, str]) -> int:
    return int(row.get(LINE_KEY, 0))


def _raw(row: dict[str, str]) -> str:
    return "\t".join(v for k, v in row.items() if k != LINE_KEY)


def parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.strip(), DATE_FORMAT)
    except ValueError:
        return None
