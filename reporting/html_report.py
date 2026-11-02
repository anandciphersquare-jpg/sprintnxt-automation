"""Builds the single-file HTML report (CSS, JS and data inlined; images/videos linked relatively)."""
from __future__ import annotations

import base64
import html
import json
import mimetypes
from pathlib import Path
from typing import Any

TEMPLATES = Path(__file__).parent / "templates"


def _safe_json(payload: Any) -> str:
    """JSON that is safe inside <script type="application/json">."""
    text = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
    return text.replace("</", "<\\/").replace("<!--", "<\\!--")


def _embed_images(payload: dict[str, Any], run_dir: Path, everything: bool) -> None:
    """Inline screenshots as data: URIs. Non-passing tests are always inlined: later runs delete this
    run's screenshots/ folder (SNXT_REPORT_KEEP_MEDIA), and the failure evidence must survive that."""
    for test in payload.get("tests", []):
        if not everything and str(test.get("status", "")).upper() == "PASS":
            continue
        for art in test.get("artifacts", []):
            if art.get("kind") != "screenshot" or str(art.get("path", "")).startswith("data:"):
                continue
            file = run_dir / art["path"]
            if file.is_file():
                mime = mimetypes.guess_type(file.name)[0] or "image/png"
                art["path"] = f"data:{mime};base64,{base64.b64encode(file.read_bytes()).decode()}"


def render_report(payload: dict[str, Any], out_file: Path, *, run_dir: Path, embed_screenshots: bool) -> Path:
    payload = json.loads(json.dumps(payload, default=str))   # don't mutate the caller's copy
    _embed_images(payload, run_dir, everything=embed_screenshots)
    template = (TEMPLATES / "report.html").read_text(encoding="utf-8")
    css = (TEMPLATES / "report.css").read_text(encoding="utf-8")
    js = (TEMPLATES / "report.js").read_text(encoding="utf-8")
    run = payload.get("run", {})
    title = f"{run.get('project', 'Test')} · {run.get('name', '')} · {run.get('id', '')}"
    out = (template
           .replace("{{TITLE}}", html.escape(title))
           .replace("/*{{CSS}}*/", css)
           .replace("/*{{JS}}*/", js)
           .replace("{{DATA}}", _safe_json(payload)))
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(out, encoding="utf-8")
    return out_file


def render_index(history: list[dict[str, Any]], out_file: Path, project: str) -> Path:
    """reports/index.html - every run (newest first) with a link to its report."""
    rows = []
    for run in reversed(history):
        total = run.get("total", 0)
        rate = run.get("pass_rate", 0)
        report_link = run.get("report", "")
        rows.append(
            "<tr>"
            f"<td><a href='{html.escape(report_link)}'>{html.escape(run.get('name', ''))}</a>"
            f"<div class='sub'>{html.escape(run.get('run_id', ''))}</div></td>"
            f"<td>{html.escape(str(run.get('start', ''))[:19].replace('T', ' '))}</td>"
            f"<td>{html.escape(run.get('environment', ''))}</td><td>{html.escape(run.get('build', ''))}</td>"
            f"<td class='num'>{total}</td><td class='num'>{run.get('passed', 0)}</td>"
            f"<td class='num'>{run.get('failed', 0)}</td><td class='num'>{run.get('blocked', 0)}</td>"
            f"<td class='num'>{run.get('skipped', 0)}</td>"
            f"<td class='num'><span class='bar'><i style='width:{rate}%'></i></span>{rate}%</td>"
            f"<td class='num'>{round((run.get('duration_ms') or 0) / 1000)}s</td>"
            "</tr>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(project)} · Test runs</title>
<style>
:root{{color-scheme:light;--bg:#f9f9f7;--card:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e1e0d9;--accent:#2a78d6;--good:#0ca30c}}
@media (prefers-color-scheme:dark){{:root{{color-scheme:dark;--bg:#0d0d0d;--card:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#2c2c2a;--accent:#3987e5}}}}
body{{margin:0;padding:24px max(16px,4vw);background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
h1{{font-size:20px;margin:0 0 4px}} p{{color:var(--ink2);margin:0 0 20px}}
.wrap{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}}
table{{border-collapse:collapse;width:100%;min-width:860px}} th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{font-size:12px;color:var(--ink2);font-weight:600;text-transform:uppercase;letter-spacing:.04em}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}} a{{color:var(--accent);font-weight:600;text-decoration:none}}
.sub{{font-size:12px;color:var(--ink2)}} .bar{{display:inline-block;width:60px;height:6px;border-radius:3px;background:var(--line);margin-right:8px;vertical-align:middle;overflow:hidden}}
.bar i{{display:block;height:100%;background:var(--good)}}
</style></head><body>
<h1>{html.escape(project)} · Test execution reports</h1>
<p>{len(history)} recorded run(s). <a href="latest/html/index.html">Open the latest report →</a></p>
<div class="wrap"><table><thead><tr><th>Run</th><th>Started</th><th>Env</th><th>Build</th><th class="num">Total</th>
<th class="num">Pass</th><th class="num">Fail</th><th class="num">Blocked</th><th class="num">Skip</th><th class="num">Pass rate</th>
<th class="num">Duration</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
</body></html>"""
    out_file.write_text(page, encoding="utf-8")
    return out_file
