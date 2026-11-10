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
