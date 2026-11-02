"""Per-test evidence collector and the public in-test API (steps, test data, attachments).

One :class:`TestCollector` exists per test *attempt*. The pytest plugin creates it before fixture
setup and activates it, so page objects can call :func:`step` without being handed anything.
"""
from __future__ import annotations

import functools
import inspect
import mimetypes
import re
import shutil
import time
from contextlib import ContextDecorator
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar, Union, overload

from .models import ApiLog, Artifact, ConsoleEntry, NetworkFailure, StepRecord
from .redact import Redactor

if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import BrowserContext, Page

    from .settings import ReportSettings

F = TypeVar("F", bound=Callable[..., Any])

_ACTIVE: Optional["TestCollector"] = None


def current() -> Optional["TestCollector"]:
    """The collector of the test that is running right now (``None`` outside a test)."""
    return _ACTIVE


def _set_active(collector: Optional["TestCollector"]) -> None:
    global _ACTIVE
    _ACTIVE = collector


def _safe_name(value: str, limit: int = 60) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")[:limit] or "item"


class TestCollector:
    """Accumulates everything observed while one test attempt runs."""

    __test__ = False  # stop pytest from trying to collect this class

    def __init__(self, *, test_id: str, attempt: int, run_dir: Path, settings: "ReportSettings",
                 redactor: Redactor):
        self.test_id = test_id
        self.attempt = attempt
        self.run_dir = run_dir
        self.settings = settings
        self.redactor = redactor
        self.max_events = settings.max_events_per_test
        self.full_page_screenshot = settings.full_page_screenshot

        self.t0 = time.time()
        self.steps: list[StepRecord] = []
        self.test_data: dict[str, Any] = {}
        self.artifacts: list[Artifact] = []
        self.api_logs: list[ApiLog] = []
        self.console: list[ConsoleEntry] = []
        self.network_failures: list[NetworkFailure] = []
        self.pages: list["Page"] = []
        self.browser: str = ""
        self.actual: Optional[str] = None
        self.dropped_events = 0
        self._depth = 0
        self._shot_seq = 0

    # ----------------------------------------------------------------- time helpers
    def offset_ms(self) -> int:
        return int((time.time() - self.t0) * 1000)

    def _bounded_append(self, bucket: list, item: Any) -> None:
        if len(bucket) < self.max_events:
            bucket.append(item)
        else:
            self.dropped_events += 1

    # ----------------------------------------------------------------- public API
    def data(self, key: str, value: Any) -> None:
        """Record a piece of test data shown in the report's *Test Data* table."""
        self.test_data[key] = self.redactor.value(value)

    def set_actual(self, text: str) -> None:
        """Override the *Actual Result* text (defaults are derived from the outcome)."""
        self.actual = self.redactor.text(str(text))

    def note(self, text: str) -> None:
        """Add an informational line to the step timeline."""
        self.steps.append(StepRecord(title=self.redactor.text(text), depth=self._depth,
                                     start_ms=self.offset_ms(), status="passed", kind="note"))

    def attach(self, name: str, *, path: Union[str, Path, None] = None, body: Union[str, bytes, None] = None,
               mime: str = "") -> Optional[Artifact]:
        """Copy a file (or write ``body``) into the run's attachments folder and link it in the report."""
        target_dir = self.run_dir / "attachments"
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            if path is not None:
                src = Path(path)
                target = target_dir / f"{_safe_name(self.test_id)}_{_safe_name(src.name)}"
                shutil.copy2(src, target)
                mime = mime or (mimetypes.guess_type(src.name)[0] or "application/octet-stream")
            elif body is not None:
                ext = mimetypes.guess_extension(mime or "text/plain") or ".txt"
                target = target_dir / f"{_safe_name(self.test_id)}_{_safe_name(name)}{ext}"
                if isinstance(body, bytes):
                    target.write_bytes(body)
                else:
                    target.write_text(self.redactor.text(body), encoding="utf-8")
                mime = mime or "text/plain"
            else:
                raise ValueError("attach() needs either path= or body=")
        except Exception as exc:  # never fail a test because of reporting
            self.note(f"Attachment '{name}' could not be saved: {exc}")
            return None
        artifact = Artifact(kind="attachment", title=name, path=target.relative_to(self.run_dir).as_posix(),
                            mime=mime, attempt=self.attempt)
        self.artifacts.append(artifact)
        return artifact

    def screenshot(self, title: str = "Screenshot", page: Optional["Page"] = None) -> Optional[Artifact]:
        """Capture a screenshot of ``page`` (default: the most recent open page)."""
        target_page = page or next((p for p in reversed(self.pages) if not p.is_closed()), None)
        if target_page is None:
            return None
        self._shot_seq += 1
        stamp = time.strftime("%H%M%S")
        rel = Path("screenshots") / f"{stamp}_{_safe_name(self.test_id)}_a{self.attempt}_{self._shot_seq}.png"
        target = self.run_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target_page.screenshot(path=str(target), full_page=self.full_page_screenshot,
                                   timeout=10_000, animations="disabled")
        except Exception as exc:
            self.note(f"Screenshot '{title}' failed: {exc.__class__.__name__}")
            return None
        artifact = Artifact(kind="screenshot", title=title, path=rel.as_posix(), mime="image/png",
                            attempt=self.attempt)
        self.artifacts.append(artifact)
        return artifact

    def watch_context(self, context: "BrowserContext") -> "BrowserContext":
        """Start capturing console errors, network failures and API calls of ``context``."""
        from .capture import watch_context  # local import keeps playwright optional for unit use
        watch_context(context, self)
        return context

    # ----------------------------------------------------------------- steps
    def _open_step(self, title: str, params: dict[str, Any]) -> StepRecord:
        record = StepRecord(title=self.redactor.text(title), depth=self._depth, start_ms=self.offset_ms(),
                            params=self.redactor.value(params) if params else {})
        self.steps.append(record)
        self._depth += 1
        return record

    def _close_step(self, record: StepRecord, error: Optional[BaseException]) -> None:
        self._depth = max(0, self._depth - 1)
        record.duration_ms = self.offset_ms() - record.start_ms
        if error is None:
            record.status = "passed"
        else:
            record.status = "failed"
            message = str(error).split("\nCall log:")[0].strip()
            record.error = self.redactor.text(f"{error.__class__.__name__}: {message}"[:500])

    def close_open_steps(self) -> None:
        """Mark steps left 'running' (test aborted mid-step) as failed."""
        for record in self.steps:
            if record.status == "running":
                record.status = "failed"
                record.duration_ms = self.offset_ms() - record.start_ms
        self._depth = 0


# ===================================================================== step()
_PARAM_SKIP = {"self", "cls"}


def _humanize(name: str) -> str:
    words = name.strip("_").replace("_", " ")
    return words[:1].upper() + words[1:]


class _Step(ContextDecorator):
    """``with step("Login"):`` *or* ``@step("Fill {email}")`` on a function / page-object method."""

    def __init__(self, title: Optional[str] = None, *, capture_args: bool = True):
        self.title = title
        self.capture_args = capture_args
        self._records: list[tuple[Optional[TestCollector], Optional[StepRecord]]] = []

    # context-manager use -------------------------------------------------
    def __enter__(self) -> "_Step":
        collector = current()
        record = collector._open_step(self.title or "Step", {}) if collector else None
        self._records.append((collector, record))
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        collector, record = self._records.pop()
        if collector and record:
            collector._close_step(record, exc)
        return False

    # decorator use -------------------------------------------------------
    def __call__(self, func: F) -> F:  # type: ignore[override]
        signature = inspect.signature(func)
        template = self.title or _humanize(func.__name__)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            collector = current()
            if collector is None:
                return func(*args, **kwargs)
            params: dict[str, Any] = {}
            try:
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()
                params = {k: v for k, v in bound.arguments.items()
                          if k not in _PARAM_SKIP and isinstance(v, (str, int, float, bool, type(None)))}
            except TypeError:
                pass
            try:
                title = template.format(**params)
            except (KeyError, IndexError, ValueError):
                title = template
            record = collector._open_step(title, params if self.capture_args else {})
            try:
                result = func(*args, **kwargs)
            except BaseException as exc:
                collector._close_step(record, exc)
                raise
            collector._close_step(record, None)
            return result

        return wrapper  # type: ignore[return-value]


@overload
def step(title: F) -> F: ...
@overload
def step(title: Optional[str] = None, *, capture_args: bool = True) -> _Step: ...


def step(title: Union[str, F, None] = None, *, capture_args: bool = True):
    """Record a reporting step.

    Usage::

        with step("Open the signup page"):
            ...

        class LoginPage(BasePage):
            @step("Log in as {email}")
            def login(self, email, password): ...

        @step                       # bare decorator: title derived from the function name
        def fill_basic(self, ...): ...
    """
    if callable(title):
        return _Step(None, capture_args=capture_args)(title)
    return _Step(title, capture_args=capture_args)


# ===================================================================== report facade
class _ReportFacade:
    """``from reporting import report`` - thin proxy onto the active collector (no-op outside tests)."""

    def data(self, key: str, value: Any) -> None:
        if (c := current()) is not None:
            c.data(key, value)

    def actual(self, text: str) -> None:
        if (c := current()) is not None:
            c.set_actual(text)

    def note(self, text: str) -> None:
        if (c := current()) is not None:
            c.note(text)

    def attach(self, name: str, *, path: Union[str, Path, None] = None, body: Union[str, bytes, None] = None,
               mime: str = "") -> Optional[Artifact]:
        return c.attach(name, path=path, body=body, mime=mime) if (c := current()) is not None else None

    def screenshot(self, title: str = "Screenshot", page: Optional["Page"] = None) -> Optional[Artifact]:
        return c.screenshot(title, page) if (c := current()) is not None else None


report = _ReportFacade()
