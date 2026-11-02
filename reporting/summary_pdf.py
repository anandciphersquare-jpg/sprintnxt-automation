"""Short, shareable PDF of a run: overview, module table, every test with its result, and one
screenshot per distinct failure reason. Built from results.json, so it can be regenerated later:

    python -m reporting.summary_pdf reports/runs/<run>      # -> <run>/html/summary.pdf
"""
from __future__ import annotations

import base64
import html
import io
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("reporting")

STATUS_ORDER = {"FAIL": 0, "BLOCKED": 1, "SKIPPED": 2, "PASS": 3}
STATUS_COLOR = {"PASS": "#1a7f37", "FAIL": "#cf222e", "BLOCKED": "#bc4c00", "SKIPPED": "#6e7781"}
MAX_EVIDENCE = 12          # screenshots in the evidence section (one per distinct failure reason)

CSS = """
@page { size: A4; margin: 14mm 12mm 16mm; }
* { box-sizing: border-box; }
body { font: 10pt/1.45 "Segoe UI", Arial, sans-serif; color: #1f2328; margin: 0; }
h1 { font-size: 20pt; margin: 0 0 2mm; }
h2 { font-size: 13pt; margin: 8mm 0 3mm; padding-bottom: 1.5mm; border-bottom: 1.5px solid #d0d7de; }
.sub { color: #57606a; margin: 0 0 5mm; }
.meta { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5mm 6mm; font-size: 9pt; margin-bottom: 5mm; }
.meta b { color: #57606a; font-weight: 600; display: block; font-size: 7.5pt; text-transform: uppercase; letter-spacing: .03em; }
.kpis { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 2.5mm; }
.kpi { border: 1px solid #d0d7de; border-radius: 2mm; padding: 3mm 1mm; text-align: center; }
.kpi .n { font-size: 18pt; font-weight: 700; display: block; }
.kpi .l { font-size: 8pt; color: #57606a; text-transform: uppercase; letter-spacing: .03em; }
table { width: 100%; border-collapse: collapse; font-size: 8.5pt; table-layout: fixed; }
td { word-break: break-word; }
th { text-align: left; background: #f6f8fa; font-weight: 600; }
th, td { padding: 1.6mm 2mm; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr { page-break-inside: avoid; }
thead { display: table-header-group; }
.st { font-weight: 700; font-size: 7.5pt; letter-spacing: .03em; }
.reason { color: #57606a; word-break: break-word; }
.note { background: #fff8c5; border: 1px solid #d4a72c; border-radius: 2mm; padding: 3mm; font-size: 9pt; }
.ev { page-break-inside: avoid; margin-bottom: 6mm; }
.ev h3 { font-size: 10pt; margin: 0 0 1mm; }
.ev p { margin: 0 0 2mm; font-size: 8.5pt; color: #57606a; }
.ev img { display: block; max-width: 100%; max-height: 105mm; border: 1px solid #d0d7de; border-radius: 1.5mm; }
.break { page-break-before: always; }
"""


def _e(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _fmt_dur(ms: float) -> str:
    s = int(round((ms or 0) / 1000))
    return f"{s // 3600}h {s % 3600 // 60}m" if s >= 3600 else f"{s // 60}m {s % 60}s" if s >= 60 else f"{s}s"


def _fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y, %H:%M")
    except Exception:
        return iso or ""


def _short_reason(test: dict[str, Any], limit: int = 160) -> str:
    """First line of the failure, prefixed with the step it failed in (readable for non-developers)."""
    text = (test.get("failure_reason") or "").strip().splitlines()
    first = text[0] if text else ""
    step = next((s.get("title") for s in test.get("steps") or []
                 if s.get("status") == "failed" and s.get("kind") != "navigation"), None)
    if step and test.get("status") == "FAIL":
        first = f"Failed at step \"{step}\": {first}"
    return first if len(first) <= limit else first[: limit - 1] + "…"


def _reason_key(test: dict[str, Any]) -> str:
    """Group failures that differ only in numbers/quoted values (e.g. timeouts, generated emails)."""
    key = re.sub(r"'[^']*'|\"[^\"]*\"|\d+", "#", _short_reason(test, 400))
    return f"{test.get('module')}|{test.get('failure_category')}|{key}"


def _image_data_uri(file: Path, width: int = 1100) -> str:
    """Downscaled JPEG keeps the PDF small; falls back to the original PNG without Pillow."""
    try:
        from PIL import Image
        with Image.open(file) as img:
            img = img.convert("RGB")
            if img.width > width:
                img = img.resize((width, round(img.height * width / img.width)))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=78, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        return "data:image/png;base64," + base64.b64encode(file.read_bytes()).decode()


def build_summary_html(payload: dict[str, Any], run_dir: Path) -> str:
    run, summary, tests = payload.get("run", {}), payload.get("summary", {}), payload.get("tests", [])
    tests = sorted(tests, key=lambda t: (STATUS_ORDER.get(t.get("status"), 9), t.get("module", ""), t.get("id", "")))
    parts: list[str] = [f"<title>{_e(run.get('project'))} test report - {_e(run.get('name'))}</title>",
                        f"<style>{CSS}</style>"]

    parts.append(f"<h1>{_e(run.get('project', 'Test'))} - Test Execution Report</h1>")
    parts.append(f"<p class='sub'>{_e(run.get('name'))} · {_e(_fmt_time(run.get('start', '')))}</p>")
    meta = [("Environment", run.get("environment")), ("Application URL", run.get("base_url")),
            ("Build", run.get("build")), ("Browser", run.get("browser")),
            ("Executed by", run.get("executed_by")), ("Duration", _fmt_dur(run.get("duration_ms", 0)))]
    parts.append("<div class='meta'>" + "".join(f"<div><b>{_e(k)}</b>{_e(v)}</div>" for k, v in meta) + "</div>")

    kpis = [("Total", summary.get("total", 0), "#1f2328"), ("Passed", summary.get("passed", 0), STATUS_COLOR["PASS"]),
            ("Failed", summary.get("failed", 0), STATUS_COLOR["FAIL"]),
            ("Blocked", summary.get("blocked", 0), STATUS_COLOR["BLOCKED"]),
            ("Skipped", summary.get("skipped", 0), STATUS_COLOR["SKIPPED"]),
            ("Pass rate", f"{summary.get('pass_rate', 0):g}%", "#1f2328")]
    parts.append("<div class='kpis'>" + "".join(
        f"<div class='kpi'><span class='n' style='color:{c}'>{_e(v)}</span><span class='l'>{_e(k)}</span></div>"
        for k, v, c in kpis) + "</div>")
    parts.append("<p class='sub' style='margin-top:3mm'>Pass rate = passed ÷ (total − skipped). "
                 "BLOCKED = the test could not run because a precondition was missing (e.g. credentials).</p>")

    # Module-wise
    parts.append("<h2>Results by module</h2><table><thead><tr><th>Module</th><th class='num'>Total</th>"
                 "<th class='num'>Passed</th><th class='num'>Failed</th><th class='num'>Blocked</th>"
                 "<th class='num'>Skipped</th><th class='num'>Duration</th></tr></thead><tbody>")
    for m in summary.get("modules", []):
        parts.append(f"<tr><td>{_e(m['module'])}</td><td class='num'>{m['total']}</td><td class='num'>{m['PASS']}</td>"
                     f"<td class='num'>{m['FAIL']}</td><td class='num'>{m['BLOCKED']}</td>"
                     f"<td class='num'>{m['SKIPPED']}</td><td class='num'>{_fmt_dur(m['duration_ms'])}</td></tr>")
    parts.append("</tbody></table>")

    # Failure reasons, grouped
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in tests:
        if t.get("status") in ("FAIL", "BLOCKED"):
            groups.setdefault(_reason_key(t), []).append(t)
    ordered = sorted(groups.values(), key=len, reverse=True)
    if ordered:
        parts.append("<h2>Failure reasons</h2><table><colgroup><col style='width:8%'><col style='width:15%'>"
                     "<col style='width:20%'><col style='width:57%'></colgroup><thead><tr><th class='num'>Tests</th><th>Module</th>"
                     "<th>Category</th><th>Reason (first test)</th></tr></thead><tbody>")
        for g in ordered:
            t = g[0]
            parts.append(f"<tr><td class='num'>{len(g)}</td><td>{_e(t.get('module'))}</td>"
                         f"<td>{_e(t.get('failure_category'))}</td><td class='reason'>{_e(_short_reason(t))}</td></tr>")
        parts.append("</tbody></table>")

    # Every test
    parts.append("<h2 class='break'>All test cases</h2><table><colgroup><col style='width:5%'>"
                 "<col style='width:15%'><col style='width:23%'><col style='width:11%'><col style='width:9%'>"
                 "<col style='width:6%'><col style='width:31%'></colgroup><thead><tr><th>#</th><th>ID</th><th>Test case</th>"
                 "<th>Module</th><th>Status</th><th class='num'>Time</th><th>Reason</th></tr></thead><tbody>")
    for n, t in enumerate(tests, 1):
        st = t.get("status", "")
        parts.append(f"<tr><td class='num'>{n}</td><td>{_e(t.get('id'))}</td><td>{_e(t.get('title'))}</td>"
                     f"<td>{_e(t.get('module'))}</td>"
                     f"<td class='st' style='color:{STATUS_COLOR.get(st, '#000')}'>{_e(st)}</td>"
                     f"<td class='num'>{_fmt_dur(t.get('duration_ms', 0))}</td>"
                     f"<td class='reason'>{_e(_short_reason(t, 120))}</td></tr>")
    parts.append("</tbody></table>")

    # Evidence: one screenshot per distinct failure reason
    evidence = []
    for g in ordered:
        for t in g:
            shot = next((a for a in t.get("artifacts", []) if a.get("kind") == "screenshot"), None)
            if shot and (run_dir / shot["path"]).is_file():
                evidence.append((t, len(g), run_dir / shot["path"]))
                break
        if len(evidence) >= MAX_EVIDENCE:
            break
    if evidence:
        parts.append("<h2 class='break'>Screenshots at the moment of failure</h2>"
                     "<p class='sub'>One example per failure reason. Every test's screenshot, video and "
                     "Playwright trace are in the HTML report.</p>")
        for t, count, file in evidence:
            others = f" (and {count - 1} more test{'s' if count > 2 else ''} with the same reason)" if count > 1 else ""
            parts.append(f"<div class='ev'><h3>{_e(t.get('id'))} - {_e(t.get('title'))}</h3>"
                         f"<p>{_e(t.get('status'))} · {_e(t.get('failure_category'))}{_e(others)}<br>"
                         f"{_e(_short_reason(t, 300))}</p><img src='{_image_data_uri(file)}'></div>")
    return "<!doctype html><html><head><meta charset='utf-8'>" + "".join(parts[:2]) + "</head><body>" \
        + "".join(parts[2:]) + "</body></html>"


def write_summary_pdf(payload: dict[str, Any], run_dir: Path, pdf_path: Path, timeout_ms: int = 120_000) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        log.warning("Playwright not importable - summary PDF skipped")
        return False
    try:
        page_html = build_summary_html(payload, run_dir)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content(page_html, wait_until="load", timeout=timeout_ms)
                run = payload.get("run", {})
                footer = (f"<div style='font-size:7px;width:100%;padding:0 12mm;color:#888;display:flex;"
                          f"justify-content:space-between'><span>{_e(run.get('project'))} · {_e(run.get('id'))}</span>"
                          "<span>Page <span class='pageNumber'></span> / <span class='totalPages'></span></span></div>")
                page.pdf(path=str(pdf_path), format="A4", print_background=True, prefer_css_page_size=True,
                         display_header_footer=True, header_template="<span></span>", footer_template=footer)
            finally:
                browser.close()
        return True
    except Exception as exc:
        log.warning("Summary PDF export failed (%s). The HTML report is unaffected.", exc)
        return False


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m reporting.summary_pdf <run folder>")
        return 2
    run_dir = Path(argv[0]).resolve()
    payload = json.loads((run_dir / "json" / "results.json").read_text(encoding="utf-8"))
    out = run_dir / "html" / "summary.pdf"
    if not write_summary_pdf(payload, run_dir, out):
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
