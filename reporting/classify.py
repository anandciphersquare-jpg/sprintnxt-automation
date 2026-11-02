"""Turns raw pytest outcomes into report statuses, failure reasons and failure categories."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import NetworkFailure, Status

ANSI = re.compile(r"\x1b\[[0-9;]*m")

LOCATOR_HINTS = ("waiting for locator", "waiting for get_by", "strict mode violation", "element is not visible",
                 "element is not enabled", "not attached to the dom", "intercepts pointer events",
                 "element is outside of the viewport", "waiting for selector")


@dataclass
class PhaseFailure:
    phase: str               # setup | call | teardown
    exc_type: str
    message: str
    longrepr: str
    skipped: bool = False
    skip_reason: str = ""


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text or "")


def short_reason(exc_type: str, message: str, limit: int = 400) -> str:
    """One readable line: drop Playwright's verbose 'Call log', collapse whitespace."""
    head = message.split("\nCall log:")[0]
    head = re.sub(r"\s+", " ", strip_ansi(head)).strip()
    if not head:
        head = exc_type or "Unknown error"
    elif exc_type and exc_type not in ("AssertionError", "Failed") and not head.startswith(exc_type):
        head = f"{exc_type}: {head}"
    return head[:limit] + ("…" if len(head) > limit else "")


def categorize(failure: PhaseFailure, network: list[NetworkFailure]) -> str:
    text = f"{failure.exc_type} {failure.message}".lower()
    if failure.phase == "setup":
        if any(n.status == 429 for n in network):
            return "Rate Limited (HTTP 429)"
        return "Setup / Precondition"
    if failure.phase == "teardown":
        return "Teardown Error"
    if any(n.status == 429 for n in network):
        return "Rate Limited (HTTP 429)"
    is_assert = failure.exc_type in ("AssertionError",) or text.startswith("assert")
    if "timeout" in failure.exc_type.lower() or ("timeout" in text and "exceeded" in text):
        if any(h in text for h in LOCATOR_HINTS):
            return "Element Not Found / Not Actionable"
        return "Timeout"
    if any(h in text for h in LOCATOR_HINTS):
        return "Element Not Found / Not Actionable"
    if "net::err_" in text or "ns_error" in text or ("navigation" in text and "fail" in text):
        return "Navigation / Network"
    if not is_assert and any((n.status or 0) >= 500 for n in network):
        return "Server Error (5xx)"
    if is_assert:
        return "Assertion Failure"
    return "Script / Unexpected Error"


def resolve_status(setup: Optional[PhaseFailure], call: Optional[PhaseFailure],
                   teardown: Optional[PhaseFailure], call_passed: bool,
                   wasxfail: bool) -> tuple[Status, Optional[PhaseFailure]]:
    """Map the three pytest phases to PASS / FAIL / BLOCKED / SKIPPED (+ the deciding failure)."""
    from .metadata import BLOCKED_PREFIX

    for phase in (setup, call):
        if phase and phase.skipped:
            return ("BLOCKED" if phase.skip_reason.startswith(BLOCKED_PREFIX) else "SKIPPED"), phase
    if setup is not None:
        return "BLOCKED", setup          # fixture/precondition broke - the test never really ran
    if call is not None:
        return "FAIL", call
    if teardown is not None:
        return "FAIL", teardown
    if wasxfail:
        return "SKIPPED", None
    return ("PASS" if call_passed else "SKIPPED"), None
