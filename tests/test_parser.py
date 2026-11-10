from pathlib import Path

import pytest

from p6checker.parser import read_xer, XerFormatError, decode_xer

FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parent.parent / "data"


def test_parses_tables_and_quarantines_broken_rows():
    xer = read_xer(FIXTURES / "planted-defects.xer")
    assert xer.version == "6.0"
    assert set(xer.tables) == {"PROJECT", "CALENDAR", "TASK", "TASKPRED"}
    # 8 good TASK rows survive: 100..107
    assert [r["task_code"] for r in xer.table("TASK").rows] == [
        "A000", "A010", "A020", "A030", "A040", "A050", "LOE1", "A999",
    ]
    # 5 good relationships survive; the two dangling ones are quarantined
    assert len(xer.table("TASKPRED")) == 5

    reasons = {(b.table, b.reason.split(" ")[0], b.reason) for b in xer.broken}
    texts = [b.reason for b in xer.broken]
    assert any("total_float_hr_cnt='lots' is not a number" in t for t in texts)
    assert any("early_start_date='06/01/2024' is not a P6 date" in t for t in texts)
    assert any("duplicate task_id '101'" in t for t in texts)
    assert any("expected 10 fields, got 6" in t for t in texts)
    assert any("required field 'task_code' is empty" in t for t in texts)
    assert any("unknown record type 'this line is garbage'" in t for t in texts)
    assert any("successor task_id '999' does not exist" in t for t in texts)
    assert any("predecessor task_id '998' does not exist" in t for t in texts)
    assert any("data after %E" in t for t in texts)
    assert len(xer.broken) == 9, texts


def test_broken_rows_carry_line_numbers():
    xer = read_xer(FIXTURES / "planted-defects.xer")
    by_reason = {b.reason: b.line_no for b in xer.broken}
    garbage = next(v for k, v in by_reason.items() if "garbage" in k)
    assert garbage > 0
    dangling = next(v for k, v in by_reason.items() if "'999'" in k)
    assert dangling > garbage  # TASKPRED comes after TASK in the file


def test_rejects_non_xer_file(tmp_path):
    p = tmp_path / "notes.xer"
    p.write_text("hello\tworld\n")
    with pytest.raises(XerFormatError, match="ERMHDR"):
        read_xer(p)
    p.write_text("")
    with pytest.raises(XerFormatError, match="empty"):
        read_xer(p)


def test_decodes_windows_1252():
    raw = "ERMHDR\t6.0\n%T\tPROJECT\n%F\tproj_id\tproj_short_name\n%R\t1\tCafé £\n%E\n".encode("cp1252")
    text, enc = decode_xer(raw)
    assert enc == "cp1252"
    assert "Café £" in text
    text, enc = decode_xer("ERMHDR\t6.0\n".encode("utf-8"))
    assert enc == "utf-8"


@pytest.mark.parametrize(
    "name,tasks,rels,projects",
    [
        ("terminal-building-airport.xer", 66, 84, 1),
        ("hotel-project.xer", 4236, 7586, 4),
    ],
)
def test_real_exports_parse_cleanly(name, tasks, rels, projects):
    xer = read_xer(DATA / name)
    assert xer.encoding == "cp1252"
    assert xer.broken == []
    assert len(xer.table("TASK")) == tasks
    assert len(xer.table("TASKPRED")) == rels
    assert len(xer.table("PROJECT")) == projects
