"""FastAPI app: upload an .xer, get the check results as JSON. Serves the built
React UI from web/dist when it exists.

    uvicorn p6checker.api:app --reload
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from functools import lru_cache

from .chart import float_histogram, histogram_data
from .checks import run_checks, DEFAULT_HIGH_FLOAT_DAYS
from .parser import read_xer, XerFormatError, XerFile, LINE_KEY

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
FIXTURE_DIR = ROOT / "tests" / "fixtures"
WEB_DIST = ROOT / "web" / "dist"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

app = FastAPI(title="p6checker", version="0.1.0")

SAMPLES = {
    "terminal-building-airport.xer": DATA_DIR / "terminal-building-airport.xer",
    "hotel-project.xer": DATA_DIR / "hotel-project.xer",
    "planted-defects.xer": FIXTURE_DIR / "planted-defects.xer",
}


def check_path(path: Path, display_name: str, high_float_days: float) -> dict:
    try:
        xer = read_xer(path)
    except XerFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc).replace(path.name, display_name)) from exc
    result = run_checks(xer, high_float_days=high_float_days)
    payload = result.as_dict()
    payload["file"] = display_name
    payload["xer"] = {
        "version": xer.version,
        "export_date": xer.export_date,
        "encoding": xer.encoding,
        "line_count": xer.line_count,
        "projects": [
            {"id": r.get("proj_id", ""), "short_name": r.get("proj_short_name", ""), "name": r.get("proj_name", "")}
            for r in xer.table("PROJECT").rows
        ],
        "relationship_count": len(xer.table("TASKPRED")),
    }
    payload["broken_rows"] = [b.as_dict() for b in xer.broken]
    payload["external_links"] = [
        {"task_id": r.get("task_id", ""), "pred_task_id": r.get("pred_task_id", ""), "pred_proj_id": r.get("pred_proj_id", "")}
        for r in xer.external_links
    ]
    payload["histogram"] = histogram_data(result)
    payload["chart_png_base64"] = base64.b64encode(float_histogram(result)).decode("ascii")
    return payload


@app.get("/api/samples")
def list_samples() -> list[dict]:
    return [
        {"name": name, "bytes": path.stat().st_size, "kind": "fixture" if path.parent == FIXTURE_DIR else "public"}
        for name, path in SAMPLES.items()
    ]


Threshold = Query(DEFAULT_HIGH_FLOAT_DAYS, gt=0, le=100000, description="flag float above this many working days")


@app.get("/api/samples/{name}")
def check_sample(name: str, high_float_days: float = Threshold) -> dict:
    path = SAMPLES.get(name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"no bundled sample named {name!r}")
    return check_path(path, name, high_float_days)


@lru_cache(maxsize=8)
def _parsed_sample(name: str, mtime_ns: int) -> XerFile:
    """Parsed bundled file, cached per name and modification time so the
    preview endpoints do not re-read a 3.8 MB file on every page."""
    return read_xer(SAMPLES[name])


def _sample_xer(name: str) -> XerFile:
    path = SAMPLES.get(name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"no bundled sample named {name!r}")
    try:
        return _parsed_sample(name, path.stat().st_mtime_ns)
    except XerFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/samples/{name}/tables")
def sample_tables(name: str) -> dict:
    """What the parser read from the file: every table with its size. Rows
    that were quarantined are not counted here; they are in the check output."""
    xer = _sample_xer(name)
    return {
        "file": name,
        "xer": {"version": xer.version, "export_date": xer.export_date, "encoding": xer.encoding, "line_count": xer.line_count},
        "header": xer.header,
        "broken_row_count": len(xer.broken),
        "tables": [
            {"name": t.name, "rows": len(t.rows), "columns": len(t.fields)}
            for t in xer.tables.values()
        ],
    }


@app.get("/api/samples/{name}/tables/{table}")
def sample_table_rows(
    name: str,
    table: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    xer = _sample_xer(name)
    t = xer.tables.get(table)
    if t is None:
        raise HTTPException(status_code=404, detail=f"{name} has no table named {table!r}")
    page = t.rows[offset : offset + limit]
    return {
        "file": name,
        "table": t.name,
        "fields": t.fields,
        "total": len(t.rows),
        "offset": offset,
        "rows": [[r.get(f, "") for f in t.fields] for r in page],
        "lines": [int(r.get(LINE_KEY, 0)) for r in page],
    }


@app.post("/api/check")
def check_upload(file: UploadFile = File(...), high_float_days: float = Threshold) -> dict:
    # Plain `def`, so FastAPI runs the parse and the chart render in a worker
    # thread instead of blocking the event loop for the duration.
    name = file.filename or "upload.xer"
    if not name.lower().endswith(".xer"):
        raise HTTPException(status_code=422, detail=f"{name}: only .xer files are accepted")
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{name}: file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.xer"
        path.write_bytes(raw)
        return check_path(path, name, high_float_days)


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")
    _DIST = WEB_DIST.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail=f"no such API route: /{full_path}")
        candidate = (_DIST / full_path).resolve()
        # Only serve files that really live inside web/dist; anything else
        # (including "../" tricks) gets the single-page app shell.
        if full_path and candidate.is_relative_to(_DIST) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
