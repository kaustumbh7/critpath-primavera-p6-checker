from pathlib import Path

from fastapi.testclient import TestClient

from p6checker.api import app

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


def test_samples_listed():
    names = [s["name"] for s in client.get("/api/samples").json()]
    assert "hotel-project.xer" in names and "planted-defects.xer" in names


def test_check_sample_returns_counts_and_chart():
    r = client.get("/api/samples/terminal-building-airport.xer")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"] == {"missing_links": 2, "negative_float": 0, "high_float": 10}
    assert body["xer"]["projects"][0]["short_name"] == "TERMINAL-2"
    assert body["chart_png_base64"].startswith("iVBOR")  # PNG magic, base64


def test_upload_planted_defects():
    with open(FIXTURES / "planted-defects.xer", "rb") as f:
        r = client.post("/api/check", files={"file": ("planted-defects.xer", f, "application/octet-stream")})
    assert r.status_code == 200
    body = r.json()
    assert len(body["broken_rows"]) == 13
    assert body["counts"]["negative_float"] == 1


def test_upload_rejects_non_xer():
    r = client.post("/api/check", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 422
    r = client.post("/api/check", files={"file": ("x.xer", b"hello\tworld\n", "application/octet-stream")})
    assert r.status_code == 422
    assert "ERMHDR" in r.json()["detail"]


def test_bad_threshold_is_a_422_not_a_crash():
    for bad in ("0", "-5", "nan", "inf", "abc"):
        r = client.get(f"/api/samples/terminal-building-airport.xer?high_float_days={bad}")
        assert r.status_code == 422, bad


def test_spa_never_serves_files_outside_dist():
    # httpx normalises "..", so build the raw path the way an attacker would
    from p6checker.api import WEB_DIST

    if not WEB_DIST.exists():
        return
    r = client.get("/..%2F..%2Fpyproject.toml")
    assert "[project]" not in r.text
    r = client.get("/%2e%2e/%2e%2e/p6checker/api.py")
    assert "FastAPI" not in r.text or "<!doctype html>" in r.text.lower()
    assert client.get("/api/nope").status_code == 404


def test_sample_tables_lists_every_table_with_sizes():
    body = client.get("/api/samples/terminal-building-airport.xer/tables").json()
    tables = {t["name"]: t for t in body["tables"]}
    assert tables["TASK"] == {"name": "TASK", "rows": 66, "columns": 61}
    assert tables["TASKPRED"]["rows"] == 84
    assert body["broken_row_count"] == 0
    assert body["xer"]["line_count"] == 382


def test_sample_table_rows_are_paginated_and_exclude_internal_keys():
    r = client.get("/api/samples/hotel-project.xer/tables/TASK?offset=4200&limit=50")
    body = r.json()
    assert body["total"] == 4236 and body["offset"] == 4200
    assert len(body["rows"]) == 36 and len(body["lines"]) == 36
    assert len(body["fields"]) == 61 and "__line__" not in body["fields"]
    assert all(len(row) == 61 for row in body["rows"])
    assert body["lines"][0] > 0
    assert client.get("/api/samples/hotel-project.xer/tables/NOPE").status_code == 404
    assert client.get("/api/samples/hotel-project.xer/tables/TASK?limit=0").status_code == 422


def test_quarantined_rows_are_not_in_the_preview():
    body = client.get("/api/samples/planted-defects.xer/tables").json()
    tables = {t["name"]: t["rows"] for t in body["tables"]}
    assert tables["TASK"] == 8 and tables["TASKPRED"] == 5
    assert body["broken_row_count"] == 13
