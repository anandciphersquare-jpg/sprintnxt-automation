"""Test-case catalogue metadata: explicit ``@tc(...)`` decorators plus smart fallbacks.

(The helper is called ``tc`` rather than ``testcase`` because pytest would collect a function named
``testcase`` imported into a test module as a test.)

Every field is optional. Anything a test does not declare is derived from markers, fixtures,
file names and docstrings, so un-annotated tests still produce a complete report row.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Union

import pytest

MARKER = "testcase"

TEST_TYPES = ("Functional", "UI/UX", "Validation", "Security", "API", "Regression", "Integration",
              "Smoke", "Boundary", "Negative", "End-to-End", "Performance", "Accessibility")

# pytest marker -> report "Type of Test Case"
MARKER_TYPES: dict[str, str] = {
    "smoke": "Smoke",
    "positive": "Functional",
    "negative": "Negative",
    "security": "Security",
    "e2e": "End-to-End",
    "regression": "Regression",
    "api": "API",
    "ui": "UI/UX",
    "boundary": "Boundary",
    "validation": "Validation",
    "integration": "Integration",
}

# pytest marker -> module name (first match wins; ordered by specificity)
MARKER_MODULES: dict[str, str] = {
    "registration": "Registration",
    "login": "Login",
    "change_password": "Change Password",
    "forgot_password": "Forgot Password",
    "admin": "Admin",
    "e2e": "End-to-End",
}

# fixture name -> precondition sentence (shown when a test does not declare preconditions)
FIXTURE_PRECONDITIONS: dict[str, str] = {
    "page": "Browser launched with a fresh context (geolocation granted)",
    "logged_in_page": "Seeded merchant is logged in (SNXT_MERCHANT_EMAIL / SNXT_MERCHANT_PASS)",
    "reg": "Signup page is open",
    "login": "Login page is open",
    "fp": "Forgot-password page is open",
    "cp": "Merchant is logged in and the Change Password page is open",
    "admin": "Admin is logged in (SNXT_ADMIN_URL / USER / PASS configured)",
}

# test-id prefix per module (for auto-generated IDs)
MODULE_PREFIX: dict[str, str] = {
    "Registration": "REG", "Login": "LOGIN", "Change Password": "CPW", "Forgot Password": "FPW",
    "Admin": "ADM", "End-to-End": "E2E",
}


def tc(id: Optional[str] = None, title: Optional[str] = None, *, module: Optional[str] = None,
             feature: Optional[str] = None, types: Union[str, Sequence[str], None] = None,
             preconditions: Union[str, Sequence[str], None] = None, expected: Optional[str] = None,
             description: Optional[str] = None) -> pytest.MarkDecorator:
    """Attach catalogue metadata to a test. ``id`` receives the parametrize suffix automatically.

    Example::

        @tc("REG-001", "Register a new merchant with valid details",
                  feature="Merchant signup", types=["Functional", "Smoke"],
                  preconditions=["Signup page is open", "UAT OTP is 123456"],
                  expected="'Registration Successful' page is shown")
        def test_register_happy_path(reg): ...
    """
    kwargs: dict[str, Any] = {k: v for k, v in dict(
        id=id, title=title, module=module, feature=feature, types=types,
        preconditions=preconditions, expected=expected, description=description).items() if v is not None}
    return getattr(pytest.mark, MARKER)(**kwargs)


def block(reason: str) -> None:
    """Stop the test as **BLOCKED** (precondition not met) instead of SKIPPED.

    pytest still counts it as skipped; the report shows BLOCKED with this reason.
    """
    pytest.skip(f"{BLOCKED_PREFIX}{reason}")


BLOCKED_PREFIX = "BLOCKED: "


@dataclass
class CaseMeta:
    id: str
    title: str
    module: str
    feature: str
    types: list[str]
    preconditions: list[str]
    expected: str
    description: str
    markers: list[str]
    file: str
    line: int


def _as_list(value: Union[str, Iterable[str], None]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def _humanize(text: str) -> str:
    text = re.sub(r"^test_", "", text).replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def _docstring(item: pytest.Item) -> str:
    func = getattr(item, "function", None)
    doc = (getattr(func, "__doc__", None) or "").strip()
    return re.sub(r"\s+", " ", doc)


def _param_id(item: pytest.Item) -> str:
    """Parametrize id without pytest-playwright's browser prefix (kept only for multi-browser runs)."""
    callspec = getattr(item, "callspec", None)
    if callspec is None:
        return ""
    param_id = callspec.id
    browser = callspec.params.get("browser_name")
    try:
        multi_browser = len(item.config.getoption("--browser") or []) > 1
    except ValueError:
        multi_browser = False
    if browser and not multi_browser:
        if param_id == browser:
            return ""
        param_id = param_id.removeprefix(f"{browser}-")
    return param_id


def collect_meta(item: pytest.Item) -> CaseMeta:
    explicit: dict[str, Any] = {}
    for mark in reversed(list(item.iter_markers(MARKER))):  # closest marker wins
        explicit.update(mark.kwargs)
        if mark.args:
            explicit.setdefault("id", mark.args[0])
            if len(mark.args) > 1:
                explicit.setdefault("title", mark.args[1])

    marker_names = sorted({m.name for m in item.iter_markers()
                           if m.name not in {MARKER, "parametrize", "usefixtures", "filterwarnings", "flaky"}})
    path = Path(str(getattr(item, "path", item.fspath)))
    file_stem = path.stem
    func_name = getattr(item, "originalname", None) or item.name.split("[")[0]
    param_id = _param_id(item)

    module = explicit.get("module") or next(
        (name for marker, name in MARKER_MODULES.items() if marker in marker_names), None) \
        or _humanize(file_stem)
    feature = explicit.get("feature") or _humanize(file_stem)

    types = _as_list(explicit.get("types"))
    if not types:
        types = [MARKER_TYPES[m] for m in marker_names if m in MARKER_TYPES]
        if hasattr(item, "callspec") and "Negative" in types and "Validation" not in types:
            types.append("Validation")   # data-driven negative cases are input validation checks
        types = types or ["Functional"]

    base_id = explicit.get("id")
    if not base_id:
        prefix = MODULE_PREFIX.get(module, re.sub(r"[^A-Z]", "", module.upper())[:4] or "TC")
        digest = hashlib.sha1(f"{path.name}::{func_name}".encode()).hexdigest()[:5].upper()
        base_id = f"{prefix}-{digest}"
    case_id = f"{base_id}[{param_id}]" if param_id else base_id

    doc = _docstring(item)
    title = explicit.get("title") or (doc.split(". ")[0].rstrip(".") if doc else _humanize(func_name))
    if param_id and explicit.get("title"):
        title = f"{title} [{param_id}]"
    elif param_id and not doc:
        title = f"{title} [{param_id}]"

    preconditions = _as_list(explicit.get("preconditions"))
    if not preconditions:
        fixtures = getattr(item, "fixturenames", [])
        preconditions = [text for name, text in FIXTURE_PRECONDITIONS.items() if name in fixtures]

    try:
        line = int(item.location[1] or 0) + 1
    except Exception:
        line = 0

    return CaseMeta(
        id=case_id, title=title, module=module, feature=feature, types=types,
        preconditions=preconditions,
        expected=explicit.get("expected") or "All assertions in the test pass",
        description=explicit.get("description") or doc,
        markers=marker_names, file=item.location[0] if item.location else path.name, line=line,
    )
