"""FastAPI app: upload an .xer, get the check results as JSON. Serves the built
React UI from web/dist when it exists.

    uvicorn p6checker.api:app --reload
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .chart import float_histogram
from .checks import run_checks, DEFAULT_HIGH_FLOAT_DAYS
from .parser import read_xer, XerFormatError

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
    payload["chart_png_base64"] = base64.b64encode(float_histogram(result)).decode("ascii")
    return payload


@app.get("/api/samples")
def list_samples() -> list[dict]:
    return [
        {"name": name, "bytes": path.stat().st_size, "kind": "fixture" if path.parent == FIXTURE_DIR else "public"}
        for name, path in SAMPLES.items()
    ]


@app.get("/api/samples/{name}")
def check_sample(name: str, high_float_days: float = DEFAULT_HIGH_FLOAT_DAYS) -> dict:
    path = SAMPLES.get(name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"no bundled sample named {name!r}")
    return check_path(path, name, high_float_days)


@app.post("/api/check")
async def check_upload(file: UploadFile = File(...), high_float_days: float = DEFAULT_HIGH_FLOAT_DAYS) -> dict:
    name = file.filename or "upload.xer"
    if not name.lower().endswith(".xer"):
        raise HTTPException(status_code=422, detail=f"{name}: only .xer files are accepted")
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{name}: file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.xer"
        path.write_bytes(raw)
        return check_path(path, name, high_float_days)


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        candidate = WEB_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
