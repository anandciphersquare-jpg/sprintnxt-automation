"""pytest plugin: hooks the reporter into every test's lifecycle and builds the report at session end.

Lifecycle (the pytest equivalent of Playwright Test's beforeEach / afterEach / reporter API):

    pytest_sessionstart         create the timestamped run folder, point pytest-playwright's
                                --output at it, open the execution log
    pytest_runtest_setup        (beforeEach) create + activate a TestCollector, record params as test data
    new_context fixture         every BrowserContext gets console / network / API listeners
    pytest_runtest_makereport   (afterEach, per phase) on failure: close open steps, take a screenshot
                                while the page is still alive, classify the failure
    makereport(teardown)        collect video / trace from pytest-playwright, finalise the attempt
    pytest_runtest_logfinish    merge retries (pytest-rerunfailures) and stream one JSON line
    pytest_sessionfinish        (controller only) merge worker files, update history, write
                                JSON / CSV / HTML / PDF, refresh reports/latest and reports/index.html

Works with pytest-xdist (-n auto): workers stream results to their own file, the controller merges.
"""
from __future__ import annotations

import logging
import platform
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

from . import collector as collector_mod
from .classify import PhaseFailure, categorize, resolve_status, short_reason, strip_ansi
from .collector import TestCollector, current
from .exporters import write_csv, write_json, write_pdf
from .html_report import render_index, render_report
from .summary_pdf import write_summary_pdf
from .metadata import BLOCKED_PREFIX, MARKER, collect_meta
from .models import STATUSES, Artifact, Attempt, TestCaseResult
from .redact import Redactor
from .settings import ReportSettings
from .storage import (ResultWriter, RunPaths, cleanup_scratch, per_test_history, prune_runs, read_results,
                      prune_media, refresh_latest, relocate, slug, update_history)

log = logging.getLogger("reporting")

COLLECTOR_KEY = pytest.StashKey[TestCollector]()
PHASES_KEY = pytest.StashKey[dict]()
PLUGIN_NAME = "snxt-html-reporter"
RUN_DIR_INPUT = "snxt_report_run_dir"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="milliseconds")


# =========================================================================== options / registration
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("snxt-report", "HTML execution report")
    group.addoption("--report-name", default=None,
                    help="Run name shown in the report and used in the run folder name "
                         "(default: derived from -m / the test paths).")
    group.addoption("--report-dir", default=None, help="Root folder for reports (default: ./reports or SNXT_REPORT_DIR).")
    group.addoption("--report-no-pdf", action="store_true", default=False, help="Skip the PDF export.")
    group.addoption("--no-html-report", action="store_true", default=False, help="Disable the reporter for this run.")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", f"{MARKER}(id, title, **meta): test-case catalogue metadata for the report")
    if config.getoption("--no-html-report") or config.option.collectonly or config.option.help:
        return
    if not config.pluginmanager.has_plugin(PLUGIN_NAME):
        config.pluginmanager.register(HtmlReporter(config), PLUGIN_NAME)


def _derive_run_name(config: pytest.Config) -> str:
    explicit = config.getoption("--report-name")
    if explicit:
        return explicit
    if config.option.markexpr:
        return config.option.markexpr
    rootdir = Path(str(config.rootpath))
    testpaths = {str((rootdir / p).resolve()) for p in (config.getini("testpaths") or [])}
    targets = []
    for arg in config.args:
        path = Path(arg.split("::")[0]).resolve()
        if path == rootdir or str(path) in testpaths:
            return "full-suite"
        name = path.stem.removeprefix("test_")
        if "::" in arg:
            name = arg.split("::")[-1].split("[")[0].removeprefix("test_")
        targets.append(name)
    if not targets:
        return "full-suite"
    return "+".join(targets[:3]) + (f"+{len(targets) - 3}more" if len(targets) > 3 else "")


# =========================================================================== fixtures
@pytest.fixture
def new_context(new_context: Callable[..., Any]) -> Callable[..., Any]:
    """Wraps pytest-playwright's ``new_context`` so every context (incl. the default ``context``/``page``)
    is watched for console errors, network failures and API traffic."""
    def factory(**kwargs: Any) -> Any:
        ctx = new_context(**kwargs)
        active = current()
        if active is not None:
            active.watch_context(ctx)
        return ctx
    return factory


@pytest.fixture
def reporter() -> TestCollector:
    """The running test's collector - the pytest equivalent of Playwright Test's ``test.info()``.

    ``reporter.data(k, v)``, ``reporter.attach(...)``, ``reporter.screenshot(...)``, ``reporter.set_actual(...)``
    """
    active = current()
    if active is None:  # reporter disabled (--no-html-report): hand back an inert collector
        raise pytest.UsageError("The reporter fixture needs the HTML reporter enabled")
    return active


# =========================================================================== the reporter
class HtmlReporter:
    def __init__(self, config: pytest.Config):
        self.config = config
        self.worker_id: str = getattr(config, "workerinput", {}).get("workerid", "main")
        self.is_controller = not hasattr(config, "workerinput")
        self.settings: Optional[ReportSettings] = None
        self.paths: Optional[RunPaths] = None
        self.writer: Optional[ResultWriter] = None
        self.redactor: Optional[Redactor] = None
        self.session_start = time.time()
        self.collection_errors: list[dict[str, Any]] = []
        self._pending: dict[str, list[dict[str, Any]]] = {}
        self._rerun_pending: set[str] = set()
        self._log_handler: Optional[logging.Handler] = None
        self._browser_log: Optional[Path] = None
        self.report_file: Optional[Path] = None
        self.pdf_file: Optional[Path] = None

    # ------------------------------------------------------------------ session start
    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionstart(self, session: pytest.Session) -> None:
        try:
            from dotenv import load_dotenv  # the project's config.py does this too; harmless if repeated
            load_dotenv()
        except ImportError:
            pass
        config = self.config
        self.settings = ReportSettings.resolve(report_dir=config.getoption("--report-dir"),
                                               run_name=_derive_run_name(config),
                                               no_pdf=config.getoption("--report-no-pdf"))
        self.redactor = Redactor(self.settings.secret_values)
        if self.is_controller:
            self.paths = RunPaths.create(self.settings.report_root, self.settings.run_name)
        else:
            self.paths = RunPaths.attach(Path(config.workerinput[RUN_DIR_INPUT]))  # type: ignore[attr-defined]
        self.writer = ResultWriter(self.paths, self.worker_id)

        # pytest-playwright writes video/trace into --output; give each process its own scratch folder
        # inside the run (it wipes --output at session start, which must not hit other workers).
        if getattr(config.option, "output", None) in (None, "test-results"):
            config.option.output = str(self.paths.pw_output / self.worker_id)

        suffix = "" if self.is_controller else f"-{self.worker_id}"
        handler = logging.FileHandler(self.paths.logs_dir / f"execution{suffix}.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s"))
        handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)
        if logging.getLogger().level > logging.INFO or logging.getLogger().level == logging.NOTSET:
            logging.getLogger().setLevel(logging.INFO)
        self._log_handler = handler
        self._browser_log = self.paths.logs_dir / f"browser{suffix}.log"
        log.info("Run %s started (worker=%s, reports=%s)", self.paths.run_id, self.worker_id, self.paths.run_dir)

    @pytest.hookimpl(optionalhook=True)
    def pytest_configure_node(self, node: Any) -> None:
        """pytest-xdist: hand the controller's run folder to every worker."""
        if self.paths is not None:
            node.workerinput[RUN_DIR_INPUT] = str(self.paths.run_dir)

    # ------------------------------------------------------------------ collection errors
    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if not report.failed or not self.is_controller:
            return
        text = strip_ansi(str(report.longrepr))
        self.collection_errors.append({
            "nodeid": report.nodeid, "message": short_reason("CollectionError", text.strip().splitlines()[-1]
                                                               if text.strip() else "Collection failed"),
            "error": text})

    # ------------------------------------------------------------------ beforeEach
    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        assert self.settings and self.paths and self.redactor
        for other in [n for n in self._pending if n != item.nodeid]:
            self._flush(other)                    # safety net: a test whose final logfinish we never saw
        meta = collect_meta(item)
        attempt = len(self._pending.get(item.nodeid, [])) + 1
        collector = TestCollector(test_id=meta.id, attempt=attempt, run_dir=self.paths.run_dir,
                                  settings=self.settings, redactor=self.redactor)
        if hasattr(item, "callspec"):
            for key, value in item.callspec.params.items():
                if key not in {"browser_name"}:
                    collector.data(key, value)
        item.stash[COLLECTOR_KEY] = collector
        item.stash[PHASES_KEY] = {"meta": meta}
        collector_mod._set_active(collector)
        log.info("START   %s  %s%s", meta.id, item.nodeid, f" (attempt {attempt})" if attempt > 1 else "")

    # ------------------------------------------------------------------ afterEach (per phase)
    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo[None]):
        report: pytest.TestReport = yield
        collector = item.stash.get(COLLECTOR_KEY, None)
        if collector is None:
            return report
        try:
            self._record_phase(item, call, report, collector)
        except Exception as exc:  # the reporter must never change a test's outcome
            log.exception("Reporter failed while recording %s/%s: %s", item.nodeid, call.when, exc)
        return report

    def _record_phase(self, item: pytest.Item, call: pytest.CallInfo[None], report: pytest.TestReport,
                      collector: TestCollector) -> None:
        phases = item.stash[PHASES_KEY]
        phases.setdefault("times", {})[call.when] = (call.start, call.stop)
        wasxfail = getattr(report, "wasxfail", None)
        if wasxfail is not None:
            phases["xfail"] = wasxfail or "expected failure"

        if report.skipped and wasxfail is None:
            reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr or "")
            reason = reason.removeprefix("Skipped: ").strip()
            phases[call.when] = PhaseFailure(call.when, "Skipped", reason, "", skipped=True, skip_reason=reason)
        elif report.failed:
            excinfo = call.excinfo
            exc_type = excinfo.typename if excinfo else "Error"
            message = str(excinfo.value) if excinfo else report.longreprtext
            phases[call.when] = PhaseFailure(call.when, exc_type, strip_ansi(message), strip_ansi(report.longreprtext))
            if call.when in ("setup", "call"):
                collector.close_open_steps()
                collector.screenshot("Failure screenshot" if call.when == "call" else "Setup failure screenshot")
        elif call.when == "call" and report.passed:
            phases["call_passed"] = True

        if call.when == "teardown":
            phases["sections"] = list(report.sections)
            phases["user_properties"] = dict(report.user_properties or [])
            self._finish_attempt(item, collector)

    def _collect_playwright_artifacts(self, item: pytest.Item, collector: TestCollector) -> None:
        """Move pytest-playwright's per-test video / trace / screenshots into the run folder."""
        assert self.paths
        try:
            from pytest_playwright.pytest_playwright import _truncate_file_name  # type: ignore
            from slugify import slugify
            out = Path(self.config.getoption("--output")).absolute() / _truncate_file_name(slugify(item.nodeid))
        except Exception:
            return
        if not out.is_dir():
            return
        base = f"{slug(collector.test_id, 50)}_a{collector.attempt}"
        for n, file in enumerate(sorted(out.iterdir()), 1):
            kind, folder, title, mime = {
                ".webm": ("video", "videos", "Video recording", "video/webm"),
                ".zip": ("trace", "traces", "Playwright trace", "application/zip"),
                ".png": ("screenshot", "screenshots", "End-of-test screenshot", "image/png"),
            }.get(file.suffix.lower(), (None, None, None, None))
            if kind is None:
                continue
            moved = relocate(file, self.paths.run_dir / folder, f"{base}_{n}{file.suffix.lower()}")
            if moved:
                collector.artifacts.append(Artifact(kind=kind, title=title,  # type: ignore[arg-type]
                                                    path=moved.relative_to(self.paths.run_dir).as_posix(),
                                                    mime=mime, attempt=collector.attempt))
        shutil.rmtree(out, ignore_errors=True)

    def _finish_attempt(self, item: pytest.Item, collector: TestCollector) -> None:
        phases = item.stash[PHASES_KEY]
        meta = phases["meta"]
        collector.close_open_steps()
        self._collect_playwright_artifacts(item, collector)

        status, decisive = resolve_status(phases.get("setup"), phases.get("call"), phases.get("teardown"),
                                          phases.get("call_passed", False), "xfail" in phases)
        redact = self.redactor.text if self.redactor else (lambda s: s)
        failure_reason = category = error = ""
        if decisive is not None and decisive.skipped:
            failure_reason = decisive.skip_reason.removeprefix(BLOCKED_PREFIX)
            category = "Precondition Not Met" if status == "BLOCKED" else ""
        elif decisive is not None:
            failure_reason = short_reason(decisive.exc_type, decisive.message)
            category = categorize(decisive, collector.network_failures)
            error = decisive.longrepr[:20000]
        if status == "SKIPPED" and "xfail" in phases:
            failure_reason = f"Expected failure (xfail): {phases['xfail']}"

        if collector.actual:
            actual = collector.actual
        elif status == "PASS":
            actual = "As expected: all checks passed." if meta.expected.startswith("All assertions") \
                else f"As expected: {meta.expected}"
        elif status == "FAIL":
            actual = f"Not as expected: {failure_reason}"
        elif status == "BLOCKED":
            actual = f"Not executed (blocked): {failure_reason}"
        else:
            actual = f"Not executed (skipped): {failure_reason}"

        times = phases.get("times", {})
        start_ts = min((t[0] for t in times.values()), default=collector.t0)
        end_ts = max((t[1] for t in times.values()), default=time.time())
        captured = "\n\n".join(f"----- {title} -----\n{content}" for title, content in phases.get("sections", []))

        result = TestCaseResult(
            id=meta.id, nodeid=item.nodeid, title=meta.title, module=meta.module, feature=meta.feature,
            types=meta.types, preconditions=meta.preconditions, expected=meta.expected,
            description=meta.description, file=meta.file, line=meta.line, markers=meta.markers,
            status=status, actual=redact(actual), failure_reason=redact(failure_reason),
            failure_category=category, error=redact(error), test_data=collector.test_data,
            steps=collector.steps, artifacts=collector.artifacts, api_logs=collector.api_logs,
            console=collector.console, network_failures=collector.network_failures,
            captured_output=redact(strip_ansi(captured))[:20000], start=_iso(start_ts), end=_iso(end_ts),
            duration_ms=int((end_ts - start_ts) * 1000), browser=collector.browser, worker=self.worker_id,
            attempts=[], retries=0, flaky=False,
            user_properties={k: (v if isinstance(v, (str, int, float, bool)) else repr(v))
                             for k, v in phases.get("user_properties", {}).items()},
        )
        self._pending.setdefault(item.nodeid, []).append(result.to_dict())
        self._append_browser_log(result)
        log.info("FINISH  %s  %s  %s  %.2fs%s", meta.id, status, item.nodeid, result.duration_ms / 1000,
                 f"  -> {failure_reason[:160]}" if failure_reason else "")
        collector_mod._set_active(None)

    def _append_browser_log(self, result: TestCaseResult) -> None:
        if not self._browser_log or not (result.console or result.network_failures):
            return
        lines = [f"===== {result.id}  {result.nodeid}  [{result.status}]"]
        lines += [f"  +{c.at_ms:>6}ms console.{c.level}: {c.text}" for c in result.console]
        lines += [f"  +{n.at_ms:>6}ms network {n.method} {n.url} -> {n.status or n.failure}"
                  for n in result.network_failures]
        with self._browser_log.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    # ------------------------------------------------------------------ one record per test (merges retries)
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.outcome == "rerun":           # pytest-rerunfailures: another attempt will follow
            self._rerun_pending.add(report.nodeid)

    def pytest_runtest_logfinish(self, nodeid: str, location: tuple) -> None:
        # rerunfailures calls logfinish after *every* attempt; only flush once the last one is done.
        if nodeid in self._rerun_pending:
            self._rerun_pending.discard(nodeid)
            return
        self._flush(nodeid)

    def _flush(self, nodeid: str) -> None:
        attempts = self._pending.pop(nodeid, None)
        if not attempts or not self.writer:
            return
        final = attempts[-1]
        final["attempts"] = [Attempt(attempt=i, status=a["status"], duration_ms=a["duration_ms"],
                                     failure_reason=a["failure_reason"],
                                     failure_category=a["failure_category"]).__dict__
                             for i, a in enumerate(attempts, 1)]
        final["retries"] = len(attempts) - 1
        final["flaky"] = final["status"] == "PASS" and any(a["status"] in ("FAIL", "BLOCKED") for a in attempts[:-1])
        if len(attempts) > 1:   # keep evidence from earlier failed attempts
            earlier = [art for a in attempts[:-1] for art in a["artifacts"]]
            final["artifacts"] = earlier + final["artifacts"]
            final["start"] = attempts[0]["start"]
        self.writer.write(final)

    # ------------------------------------------------------------------ session end
    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        for nodeid in list(self._pending):
            self._flush(nodeid)
        collector_mod._set_active(None)
        if self.is_controller and self.paths is not None:
            try:
                self._build_report(exitstatus)
            except Exception as exc:
                log.exception("Report generation failed: %s", exc)
                sys.stderr.write(f"\n[reporting] report generation failed: {exc}\n")
        if self._log_handler:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler.close()

    def _build_report(self, exitstatus: int) -> None:
        assert self.settings and self.paths
        settings, paths = self.settings, self.paths
        end = time.time()
        tests = read_results(paths)
        for n, err in enumerate(self.collection_errors, 1):
            tests.append(self._collection_error_record(n, err, end))

        summary = summarize(tests)
        browsers = sorted({t["browser"] for t in tests if t.get("browser")})
        run = {
            "id": paths.run_id, "name": settings.run_name, "project": settings.project_name,
            "start": _iso(self.session_start), "end": _iso(end), "duration_ms": int((end - self.session_start) * 1000),
            "environment": settings.environment, "base_url": settings.base_url, "build": settings.build_version,
            "executed_by": settings.executed_by, "browser": ", ".join(browsers) or "n/a",
            "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "python": platform.python_version(), "pytest": pytest.__version__, "playwright": _pkg_version("playwright"),
            "command": " ".join(["pytest", *self.config.invocation_params.args]),
            "markexpr": self.config.option.markexpr or "", "ci": settings.ci,
            "workers": len({t["worker"] for t in tests if t.get("worker")}) or 1, "exit_status": int(exitstatus),
            "hostname": platform.node(), "pdf": False, "generated": _iso(time.time()),
            "dir": _display_path(paths.run_dir),
        }

        history = update_history(paths, {
            "run_id": paths.run_id, "name": settings.run_name, "start": run["start"],
            "duration_ms": run["duration_ms"], "environment": settings.environment, "build": settings.build_version,
            "report": f"runs/{paths.run_id}/html/index.html",
            **{k: summary[k] for k in ("total", "passed", "failed", "blocked", "skipped", "pass_rate", "flaky")},
            "tests": {t["nodeid"]: t["status"] for t in tests},
        }, settings.history_size)
        payload = {
            "schema": 1, "run": run, "summary": summary, "tests": tests,
            "history": [{k: v for k, v in h.items() if k != "tests"} for h in history],
            "test_history": per_test_history(history, settings.test_history_size),
        }

        write_csv(paths.results_csv, tests, run)
        render_report(payload, paths.html, run_dir=paths.run_dir, embed_screenshots=settings.embed_screenshots)
        if settings.generate_pdf and tests:
            if write_pdf(paths.html, paths.pdf):
                run["pdf"] = True
                render_report(payload, paths.html, run_dir=paths.run_dir,
                              embed_screenshots=settings.embed_screenshots)  # re-render so the PDF button links it
                self.pdf_file = paths.pdf
        write_json(paths.results_json, payload)
        if settings.generate_pdf and tests:      # short shareable PDF next to the full one
            write_summary_pdf(payload, paths.run_dir, paths.html.parent / "summary.pdf")
        cleanup_scratch(paths)
        if paths.results_json.exists():          # merged; the per-worker stream files are no longer needed
            shutil.rmtree(paths.parts_dir, ignore_errors=True)
        render_index(history, paths.index_html, settings.project_name)
        removed = prune_runs(paths, settings.keep_runs)
        if removed:
            log.info("Pruned old runs: %s", ", ".join(removed))
        stripped = prune_media(paths, settings.keep_media_runs)
        if stripped:
            log.info("Deleted old screenshots/videos: %s", ", ".join(stripped))
        self.report_file = paths.html
        log.info("Report written: %s", paths.html)
        if settings.copy_latest:                 # last, so latest/logs/execution.log is complete
            refresh_latest(paths)

    def _collection_error_record(self, n: int, err: dict[str, Any], now: float) -> dict[str, Any]:
        return TestCaseResult(
            id=f"COLLECT-{n:03d}", nodeid=err["nodeid"] or f"collection-error-{n}",
            title=f"Collection error in {err['nodeid'] or 'test session'}", module="Collection",
            feature="Test discovery", types=["Functional"], preconditions=[], expected="Test module imports cleanly",
            description="", file=err["nodeid"], line=0, markers=[], status="BLOCKED",
            actual="Tests in this module could not be collected", failure_reason=err["message"],
            failure_category="Collection / Import Error", error=err["error"][:20000], test_data={}, steps=[],
            artifacts=[], api_logs=[], console=[], network_failures=[], captured_output="",
            start=_iso(now), end=_iso(now), duration_ms=0, browser="", worker="main", attempts=[], retries=0,
            flaky=False, user_properties={}).to_dict()

    def pytest_terminal_summary(self, terminalreporter: Any) -> None:
        if not self.is_controller or self.report_file is None or self.paths is None:
            return
        tr = terminalreporter
        tr.write_sep("-", "HTML execution report")
        tr.write_line(f"Report : {self.report_file.as_uri()}")
        tr.write_line(f"Latest : {(self.paths.latest_dir / 'html' / 'index.html').as_uri()}")
        if self.pdf_file:
            tr.write_line(f"PDF    : {self.pdf_file}")
        tr.write_line(f"Data   : {self.paths.results_json}  |  {self.paths.results_csv}")


# =========================================================================== helpers
def summarize(tests: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {s: sum(1 for t in tests if t["status"] == s) for s in STATUSES}
    executed = len(tests) - counts["SKIPPED"]
    modules: dict[str, dict[str, Any]] = {}
    for t in tests:
        m = modules.setdefault(t["module"], {"module": t["module"], "total": 0, "duration_ms": 0,
                                             **{s: 0 for s in STATUSES}})
        m["total"] += 1
        m[t["status"]] += 1
        m["duration_ms"] += t.get("duration_ms") or 0
    categories: dict[str, int] = {}
    for t in tests:
        if t["status"] in ("FAIL", "BLOCKED") and t.get("failure_category"):
            categories[t["failure_category"]] = categories.get(t["failure_category"], 0) + 1
    return {
        "total": len(tests), "passed": counts["PASS"], "failed": counts["FAIL"], "blocked": counts["BLOCKED"],
        "skipped": counts["SKIPPED"], "executed": executed,
        "pass_rate": round(counts["PASS"] * 100 / executed, 1) if executed else 0.0,
        "flaky": sum(1 for t in tests if t.get("flaky")), "retried": sum(1 for t in tests if t.get("retries")),
        "test_time_ms": sum(t.get("duration_ms") or 0 for t in tests),
        "modules": sorted(modules.values(), key=lambda m: m["module"]),
        "categories": dict(sorted(categories.items(), key=lambda kv: -kv[1])),
    }


def _display_path(path: Path) -> str:
    """Path relative to the working directory when possible (used in copy-paste commands)."""
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def _pkg_version(name: str) -> str:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return "unknown"
