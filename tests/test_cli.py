from pathlib import Path

from p6checker.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_cli_writes_reports(tmp_path, capsys):
    rc = main([str(FIXTURES / "planted-defects.xer"), "--out", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "broken rows quarantined: 9" in out
    assert "Negative float" in out
    assert (tmp_path / "planted-defects.html").exists()
    assert (tmp_path / "planted-defects.png").stat().st_size > 1000
    assert (tmp_path / "planted-defects.json").exists()
    html = (tmp_path / "planted-defects.html").read_text()
    assert "A020" in html and "data:image/png;base64," in html


def test_cli_reports_unreadable_file(tmp_path, capsys):
    bad = tmp_path / "bad.xer"
    bad.write_text("not an xer\n")
    rc = main([str(bad)])
    assert rc == 1
    assert "ERMHDR" in capsys.readouterr().err
