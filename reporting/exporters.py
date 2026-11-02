"""Machine-readable exports (JSON, CSV) and the server-side PDF rendering of the HTML report."""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("reporting")

CSV_COLUMNS: list[tuple[str, str]] = [
    ("Test Case ID", "id"), ("Test Case Name", "title"), ("Module", "module"), ("Feature/Flow", "feature"),
    ("Type", "types"), ("Preconditions", "preconditions"), ("Test Data", "test_data"), ("Steps", "steps"),
    ("Expected Result", "expected"), ("Actual Result", "actual"), ("Status", "status"),
    ("Failure Reason", "failure_reason"), ("Failure Category", "failure_category"),
    ("Error / Stack Trace", "error"), ("Screenshots", "screenshots"), ("Video", "videos"), ("Trace", "traces"),
    ("Start", "start"), ("End", "end"), ("Duration (s)", "duration_s"), ("Browser", "browser"),
    ("Environment", "environment"), ("Executed By", "executed_by"), ("Build", "build"),
    ("API Calls", "api_count"), ("Console Errors", "console_count"), ("Network Failures", "network_count"),
    ("Retries", "retries"), ("Flaky", "flaky"), ("Node ID", "nodeid"),
]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _flatten(test: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    arts = test.get("artifacts") or []
    steps = [("  " * s.get("depth", 0)) + s.get("title", "") + ("" if s.get("status") != "failed" else " [FAILED]")
             for s in test.get("steps") or [] if s.get("kind") != "navigation"]
    return {
        **test,
        "types": ", ".join(test.get("types") or []),
        "preconditions": "\n".join(test.get("preconditions") or []),
        "test_data": "\n".join(f"{k} = {v}" for k, v in (test.get("test_data") or {}).items()),
        "steps": "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)),
        "screenshots": "\n".join(a["path"] for a in arts if a["kind"] == "screenshot"),
        "videos": "\n".join(a["path"] for a in arts if a["kind"] == "video"),
        "traces": "\n".join(a["path"] for a in arts if a["kind"] == "trace"),
        "duration_s": round((test.get("duration_ms") or 0) / 1000, 2),
        "environment": run.get("environment", ""),
        "executed_by": run.get("executed_by", ""),
        "build": run.get("build", ""),
        "api_count": len(test.get("api_logs") or []),
        "console_count": len(test.get("console") or []),
        "network_count": len(test.get("network_failures") or []),
        "error": (test.get("error") or "")[:30000],   # stay under Excel's 32,767-char cell limit
    }


def write_csv(path: Path, tests: list[dict[str, Any]], run: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel on Windows opens it with the right encoding
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow([header for header, _ in CSV_COLUMNS])
        for test in tests:
            flat = _flatten(test, run)
            writer.writerow([flat.get(key, "") for _, key in CSV_COLUMNS])


def write_pdf(html_path: Path, pdf_path: Path, timeout_ms: int = 120_000) -> bool:
    """Render the HTML report to PDF with headless Chromium (print layout: failures expanded)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        log.warning("Playwright not importable - PDF export skipped")
        return False
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page()
                page.goto(html_path.as_uri() + "?print=1", wait_until="load", timeout=timeout_ms)
                page.emulate_media(media="print")
                page.wait_for_function("window.__reportReady === true", timeout=timeout_ms)
                page.pdf(path=str(pdf_path), format="A4", print_background=True, landscape=False,
                         margin={"top": "12mm", "bottom": "14mm", "left": "10mm", "right": "10mm"},
                         display_header_footer=True,
                         header_template="<span></span>",
                         footer_template=("<div style='font-size:8px;width:100%;text-align:center;color:#888'>"
                                          "Page <span class='pageNumber'></span> / <span class='totalPages'></span>"
                                          "</div>"))
            finally:
                browser.close()
        return True
    except Exception as exc:
        log.warning("PDF export failed (%s). The HTML report is unaffected.", exc)
        return False
