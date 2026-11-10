"""Terminal summary and a self-contained HTML report (chart embedded as base64)."""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

from .checks import CheckResult, CHECK_NAMES, CHECK_LABELS
from .chart import float_histogram
from .parser import XerFile


def terminal_summary(xer: XerFile, result: CheckResult) -> str:
    projects = ", ".join(r.get("proj_short_name", "?") for r in xer.table("PROJECT").rows) or "?"
    lines = [
        f"{xer.path.name}  (XER {xer.version}, exported {xer.export_date}, {xer.encoding}, {xer.line_count} lines)",
        f"  projects: {projects}",
        f"  activities: {result.activity_count}   relationships: {len(xer.table('TASKPRED'))}   "
        f"unscheduled (no float): {result.unscheduled_count}",
        f"  broken rows quarantined: {len(xer.broken)}",
    ]
    for b in xer.broken[:10]:
        lines.append(f"    line {b.line_no:>6}  {b.table or '-':9s} {b.reason}")
    if len(xer.broken) > 10:
        lines.append(f"    ... and {len(xer.broken) - 10} more (see HTML report)")
    for c in CHECK_NAMES:
        label = CHECK_LABELS[c]
        if c == "high_float":
            label += f" (> {result.high_float_threshold_days:g} days)"
        lines.append(f"  {label:28s} {result.count(c):>6}")
    return "\n".join(lines)


def write_json(xer: XerFile, result: CheckResult, path: Path) -> None:
    payload = result.as_dict()
    payload["broken_rows"] = [b.as_dict() for b in xer.broken]
    payload["xer"] = {"version": xer.version, "export_date": xer.export_date, "encoding": xer.encoding}
    path.write_text(json.dumps(payload, indent=2))


def write_html(xer: XerFile, result: CheckResult, path: Path, png: bytes | None = None) -> None:
    png = png or float_histogram(result)
    img = base64.b64encode(png).decode("ascii")
    e = html.escape
    projects = ", ".join(f"{e(r.get('proj_short_name', '?'))} ({e(r.get('proj_id', ''))})" for r in xer.table("PROJECT").rows)

    def table(rows: list[list[str]], head: list[str]) -> str:
        if not rows:
            return "<p class='empty'>none</p>"
        h = "".join(f"<th>{e(x)}</th>" for x in head)
        b = "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in rows)
        return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"

    sections = []
    for c in CHECK_NAMES:
        fs = result.findings[c]
        label = CHECK_LABELS[c]
        if c == "high_float":
            label += f" (above {result.high_float_threshold_days:g} working days)"
        rows = [[f.task_code, f.task_name, f.task_type, f.detail, f.line] for f in fs]
        sections.append(f"<h2>{e(label)} <span class='n'>{len(fs)}</span></h2>" + table(rows, ["Activity", "Name", "Type", "Detail", "Line"]))

    broken_rows = [[b.line_no, b.table or "", b.reason, b.raw[:120]] for b in xer.broken]

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{e(xer.path.name)} schedule check</title>
<style>
 body{{font:14px/1.45 Geist,-apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:0;padding:24px;max-width:1100px;color:#171717;background:#fffcf7}}
 h1{{font-size:22px;margin:0 0 4px;color:#0f2a4a}} h2{{font-size:17px;margin:28px 0 8px;color:#0f2a4a}} .n{{color:#8f877b;font-weight:400}}
 .meta{{color:#665f55;margin-bottom:16px}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}}
 .card{{border:1px solid #d9d1c2;border-radius:8px;padding:10px 14px;min-width:150px;background:#fff}}
 .card b{{display:block;font-size:24px}} .card.bad b{{color:#b5440d}} .card.warn b{{color:#d98c00}} .card.ok b{{color:#2f8f62}}
 table{{border-collapse:collapse;width:100%;font-size:13px;background:#fff}} th,td{{border-bottom:1px solid #ece6da;padding:5px 8px;text-align:left;vertical-align:top}}
 th{{background:#f7f3ea;color:#665f55}} td:last-child{{white-space:nowrap}} .empty{{color:#8f877b}}
 img{{max-width:100%;border:1px solid #d9d1c2;border-radius:8px;background:#fff}}
</style></head><body>
<h1>{e(xer.path.name)}</h1>
<div class="meta">XER {e(xer.version)} · exported {e(xer.export_date)} · decoded as {e(xer.encoding)} · {xer.line_count} lines · projects: {projects or '?'}</div>
<div class="cards">
 <div class="card"><span>activities checked</span><b>{result.activity_count}</b></div>
 <div class="card"><span>relationships</span><b>{len(xer.table('TASKPRED'))}</b></div>
 <div class="card {'bad' if xer.broken else 'ok'}"><span>broken rows quarantined</span><b>{len(xer.broken)}</b></div>
 <div class="card {'bad' if result.count('missing_links') else 'ok'}"><span>missing links</span><b>{result.count('missing_links')}</b></div>
 <div class="card {'bad' if result.count('negative_float') else 'ok'}"><span>negative float</span><b>{result.count('negative_float')}</b></div>
 <div class="card {'warn' if result.count('high_float') else 'ok'}"><span>high float</span><b>{result.count('high_float')}</b></div>
</div>
<img alt="total float distribution" src="data:image/png;base64,{img}">
<p class="meta">{result.unscheduled_count} activities have no float value in the file (never scheduled) and are excluded from the float checks and the chart.</p>
{''.join(sections)}
<h2>Broken rows quarantined <span class='n'>{len(xer.broken)}</span></h2>
<p class="meta">Rows that could not be trusted were excluded from every check rather than guessed at.</p>
{table(broken_rows, ["Line", "Table", "Reason", "Raw (truncated)"])}
</body></html>"""
    path.write_text(doc, encoding="utf-8")
