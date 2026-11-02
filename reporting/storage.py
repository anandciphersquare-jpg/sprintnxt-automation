"""Report folder layout, per-worker result streaming, history/trend storage and housekeeping.

Layout (one folder per execution, so module-wise runs never overwrite each other)::

    reports/
    ├── index.html                     <- list of every run, newest first
    ├── history/history.json           <- trend data (last N runs + per-test statuses)
    ├── latest/                        <- copy of the most recent run folder
    └── runs/2026-10-15_14-30-05_registration/
        ├── html/index.html  html/report.pdf
        ├── json/results.json  json/results.csv  json/parts/*.jsonl
        ├── screenshots/  videos/  traces/  attachments/
        └── logs/execution.log  logs/browser.log
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

log = logging.getLogger("reporting")

SUBDIRS = ("html", "json", "screenshots", "videos", "traces", "attachments", "logs")


def slug(text: str, limit: int = 40) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:limit] or "run"


@dataclass(frozen=True)
class RunPaths:
    reports_root: Path
    run_dir: Path

    @property
    def run_id(self) -> str:
        return self.run_dir.name

    @property
    def html(self) -> Path: return self.run_dir / "html" / "index.html"
    @property
    def pdf(self) -> Path: return self.run_dir / "html" / "report.pdf"
    @property
    def results_json(self) -> Path: return self.run_dir / "json" / "results.json"
    @property
    def results_csv(self) -> Path: return self.run_dir / "json" / "results.csv"
    @property
    def parts_dir(self) -> Path: return self.run_dir / "json" / "parts"
    @property
    def logs_dir(self) -> Path: return self.run_dir / "logs"
    @property
    def pw_output(self) -> Path: return self.run_dir / ".pw-artifacts"
    @property
    def history_file(self) -> Path: return self.reports_root / "history" / "history.json"
    @property
    def latest_dir(self) -> Path: return self.reports_root / "latest"
    @property
    def index_html(self) -> Path: return self.reports_root / "index.html"

    @classmethod
    def create(cls, reports_root: Path, run_name: str) -> "RunPaths":
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        base = f"{stamp}_{slug(run_name)}"
        run_dir = reports_root / "runs" / base
        n = 1
        while run_dir.exists():                    # two runs in the same second (parallel CI jobs)
            n += 1
            run_dir = reports_root / "runs" / f"{base}-{n}"
        for sub in SUBDIRS:
            (run_dir / sub).mkdir(parents=True, exist_ok=True)
        (run_dir / "json" / "parts").mkdir(exist_ok=True)
        return cls(reports_root=reports_root, run_dir=run_dir)

    @classmethod
    def attach(cls, run_dir: Path) -> "RunPaths":
        """Used by xdist workers: the controller already created the folder."""
        return cls(reports_root=run_dir.parent.parent, run_dir=run_dir)


# --------------------------------------------------------------------------- streaming results
class ResultWriter:
    """Appends one JSON line per finished test. One file per process => safe under xdist."""

    def __init__(self, paths: RunPaths, worker_id: str):
        paths.parts_dir.mkdir(parents=True, exist_ok=True)
        self.file = paths.parts_dir / f"{worker_id}.jsonl"

    def write(self, record: dict[str, Any]) -> None:
        with self.file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_results(paths: RunPaths) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for part in sorted(paths.parts_dir.glob("*.jsonl")):
        for line_no, line in enumerate(part.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                log.warning("Skipping corrupt result line %s:%d", part.name, line_no)
    results.sort(key=lambda r: (r.get("start") or "", r.get("nodeid") or ""))
    return results


# --------------------------------------------------------------------------- history / trend
def load_history(paths: RunPaths) -> list[dict[str, Any]]:
    try:
        data = json.loads(paths.history_file.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def update_history(paths: RunPaths, entry: dict[str, Any], keep: int) -> list[dict[str, Any]]:
    history = [h for h in load_history(paths) if h.get("run_id") != entry["run_id"]]
    history.append(entry)
    history = history[-keep:]
    paths.history_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = paths.history_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, paths.history_file)            # atomic: a crashed run can't corrupt history
    return history


def per_test_history(history: Iterable[dict[str, Any]], limit: int) -> dict[str, list[str]]:
    """nodeid -> list of statuses, oldest first, from the last ``limit`` runs (including this one)."""
    runs = list(history)[-limit:]
    out: dict[str, list[str]] = {}
    for idx, run in enumerate(runs):
        for nodeid, status in (run.get("tests") or {}).items():
            out.setdefault(nodeid, ["-"] * idx).append(status)
        for statuses in out.values():
            if len(statuses) < idx + 1:
                statuses.append("-")         # test did not run in that execution
    return out


# --------------------------------------------------------------------------- housekeeping
def _rmtree(path: Path) -> None:
    def retry(func, p, _exc):                # Windows: clear the read-only bit and retry once
        try:
            os.chmod(p, 0o700)
            func(p)
        except Exception:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:  # pragma: no cover
        shutil.rmtree(path, onerror=retry)


def refresh_latest(paths: RunPaths) -> None:
    """Replace reports/latest with a copy of this run (a copy works everywhere, unlike symlinks)."""
    latest = paths.latest_dir
    staging = latest.with_name("latest.__staging")
    try:
        if staging.exists():
            _rmtree(staging)
        shutil.copytree(paths.run_dir, staging, ignore=shutil.ignore_patterns("parts", ".pw-artifacts"))
        if latest.exists():
            _rmtree(latest)
        os.replace(staging, latest)
        (latest / "LATEST_RUN.txt").write_text(paths.run_id + "\n", encoding="utf-8")
    except Exception as exc:  # e.g. a file in latest/ is open in a viewer on Windows
        log.warning("Could not refresh %s: %s", latest, exc)


def prune_runs(paths: RunPaths, keep: int) -> list[str]:
    if keep <= 0:
        return []
    runs = sorted((p for p in (paths.reports_root / "runs").iterdir() if p.is_dir()), key=lambda p: p.name)
    removed = []
    for old in runs[:-keep]:
        if old != paths.run_dir:
            _rmtree(old)
            removed.append(old.name)
    return removed


MEDIA_DIRS = ("screenshots", "videos")


def prune_media(paths: RunPaths, keep: int) -> list[str]:
    """Delete screenshots/ and videos/ of every run except the newest ``keep`` (this run always stays)."""
    if keep <= 0:
        return []
    runs = sorted((p for p in (paths.reports_root / "runs").iterdir() if p.is_dir()), key=lambda p: p.name)
    removed = []
    for old in runs[:-keep]:
        if old == paths.run_dir:
            continue
        dirs = [old / d for d in MEDIA_DIRS if (old / d).is_dir()]
        for d in dirs:
            _rmtree(d)
        if dirs:
            removed.append(old.name)
    return removed


def cleanup_scratch(paths: RunPaths) -> None:
    if paths.pw_output.exists():
        _rmtree(paths.pw_output)


def relocate(src: Path, dest_dir: Path, new_name: str) -> Optional[Path]:
    """Move an artifact produced by pytest-playwright into the run folder."""
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / new_name
        shutil.move(str(src), str(target))
        return target
    except Exception as exc:
        log.warning("Could not move artifact %s: %s", src, exc)
        return None
