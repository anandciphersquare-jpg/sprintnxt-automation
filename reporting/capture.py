"""Browser-side evidence capture: console errors, uncaught page errors, network failures, API calls.

Listeners are attached to the BrowserContext (not individual pages) so pop-ups and new tabs are
covered automatically. Every handler is defensive: a reporting problem must never fail a test.
"""
from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Callable

from .models import ApiLog, ConsoleEntry, NetworkFailure

if TYPE_CHECKING:  # pragma: no cover
    from playwright.sync_api import BrowserContext, ConsoleMessage, Page, Request, Response, WebError

    from .collector import TestCollector

API_RESOURCE_TYPES = {"xhr", "fetch"}
TEXTUAL_CONTENT = ("json", "text", "xml", "javascript", "x-www-form-urlencoded", "graphql")
KEPT_RESPONSE_HEADERS = {"content-type", "content-length", "x-request-id", "x-correlation-id",
                         "retry-after", "x-ratelimit-remaining", "x-ratelimit-limit", "location"}


def _guard(func: Callable[..., None]) -> Callable[..., None]:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            func(*args, **kwargs)
        except Exception:  # noqa: BLE001 - evidence capture is strictly best-effort
            pass
    return wrapper


def _is_capturable(url: str) -> bool:
    return not url.startswith(("data:", "blob:", "chrome-extension:", "about:"))


def watch_context(context: "BrowserContext", collector: "TestCollector") -> None:
    settings = collector.settings
    settings_filter = settings.api_url_filter
    ignore_aborted = settings.ignore_aborted_requests
    body_limit = settings.api_body_limit
    redactor = collector.redactor

    # ---------------------------------------------------------------- browser identity
    try:
        browser = context.browser
        if browser is not None and not collector.browser:
            collector.browser = f"{browser.browser_type.name} {browser.version}"
    except Exception:
        pass

    # ---------------------------------------------------------------- pages / navigation
    @_guard
    def on_page(page: "Page") -> None:
        if page in collector.pages:
            return
        collector.pages.append(page)

        @_guard
        def on_nav(frame: Any) -> None:
            if frame == page.main_frame and _is_capturable(frame.url):
                from .models import StepRecord
                title = f"Navigated to {redactor.text(frame.url)}"
                last_nav = next((s for s in reversed(collector.steps) if s.kind == "navigation"), None)
                if last_nav is not None and last_nav.title == title and collector.offset_ms() - last_nav.start_ms < 2000:
                    return  # SPA hash routing fires framenavigated twice for one navigation
                collector.steps.append(StepRecord(title=title,
                                                  depth=collector._depth, start_ms=collector.offset_ms(),
                                                  status="passed", kind="navigation"))
        page.on("framenavigated", on_nav)

    for existing in context.pages:
        on_page(existing)
    context.on("page", on_page)

    # ---------------------------------------------------------------- console + page errors
    @_guard
    def on_console(msg: "ConsoleMessage") -> None:
        if msg.type not in ("error", "warning", "assert"):
            return
        loc = msg.location or {}
        where = f"{loc.get('url', '')}:{loc.get('lineNumber', '')}" if loc.get("url") else ""
        collector._bounded_append(collector.console, ConsoleEntry(
            level=msg.type, text=redactor.text(msg.text[:2000]), at_ms=collector.offset_ms(), location=where))

    @_guard
    def on_weberror(err: "WebError") -> None:
        error = err.error
        text = f"{getattr(error, 'name', 'Error')}: {getattr(error, 'message', str(error))}"
        stack = getattr(error, "stack", "") or ""
        collector._bounded_append(collector.console, ConsoleEntry(
            level="pageerror", text=redactor.text((text + ("\n" + stack if stack else ""))[:3000]),
            at_ms=collector.offset_ms()))

    context.on("console", on_console)
    context.on("weberror", on_weberror)

    # ---------------------------------------------------------------- network
    def is_api(request: "Request") -> bool:
        if request.resource_type not in API_RESOURCE_TYPES or not _is_capturable(request.url):
            return False
        return settings_filter.search(request.url) is not None if settings_filter else True

    def duration(request: "Request") -> float | None:
        timing = request.timing or {}
        end = timing.get("responseEnd", -1)
        return round(end, 1) if end is not None and end >= 0 else None

    def request_body(request: "Request") -> str:
        try:
            return redactor.body(request.post_data or "", body_limit)
        except Exception:
            return "[binary body]"

    @_guard
    def on_response(response: "Response") -> None:
        # HTTP 4xx/5xx. Uses the 'response' event because Chromium reports some failed sub-resources
        # (e.g. a 404 script) as requestfailed/ERR_ABORTED and never fires requestfinished for them.
        if response.status < 400 or not _is_capturable(response.url):
            return
        request = response.request
        collector._bounded_append(collector.network_failures, NetworkFailure(
            method=request.method, url=redactor.text(response.url), at_ms=collector.offset_ms(),
            status=response.status, resource_type=request.resource_type))

    @_guard
    def on_finished(request: "Request") -> None:
        if not is_api(request):
            return
        response = request.response()
        status = response.status if response else None
        at = collector.offset_ms()
        resp_headers: dict[str, str] = {}
        resp_body = ""
        if response is not None:
            all_headers = response.headers
            resp_headers = {k: v for k, v in all_headers.items() if k.lower() in KEPT_RESPONSE_HEADERS}
            content_type = all_headers.get("content-type", "")
            if any(t in content_type for t in TEXTUAL_CONTENT) or not content_type:
                try:
                    resp_body = redactor.body(response.text(), body_limit)
                except Exception:
                    resp_body = "[body unavailable]"
            else:
                resp_body = f"[{content_type} body not captured]"
        collector._bounded_append(collector.api_logs, ApiLog(
            method=request.method, url=redactor.text(request.url), status=status,
            duration_ms=duration(request), at_ms=at, resource_type=request.resource_type,
            request_headers=redactor.headers(request.headers), request_body=request_body(request),
            response_headers=redactor.headers(resp_headers), response_body=resp_body))

    @_guard
    def on_failed(request: "Request") -> None:
        if not _is_capturable(request.url):
            return
        failure = request.failure or "unknown failure"
        if ignore_aborted and ("ERR_ABORTED" in failure or "NS_BINDING_ABORTED" in failure):
            return  # requests cancelled by navigation - noise, not failures
        at = collector.offset_ms()
        collector._bounded_append(collector.network_failures, NetworkFailure(
            method=request.method, url=redactor.text(request.url), at_ms=at, failure=failure,
            resource_type=request.resource_type))
        if is_api(request):
            collector._bounded_append(collector.api_logs, ApiLog(
                method=request.method, url=redactor.text(request.url), status=None, duration_ms=None,
                at_ms=at, resource_type=request.resource_type,
                request_headers=redactor.headers(request.headers), request_body=request_body(request),
                failure=failure))

    context.on("response", on_response)
    context.on("requestfinished", on_finished)
    context.on("requestfailed", on_failed)
