"""Reporter configuration, resolved once per run from CLI options and environment variables.

Every knob has a sensible default, so the reporter works with zero configuration locally and
picks up CI metadata (build number, actor, pipeline URL) automatically on GitHub Actions,
Azure DevOps, GitLab CI and Jenkins.
"""
from __future__ import annotations

import getpass
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _first_env(*names: str) -> str:
    for name in names:
        value = _env(name)
        if value:
            return value
    return ""


def detect_ci() -> dict[str, str]:
    """Return {provider, url, build} for the CI system we are running in (empty dict locally)."""
    if _env("GITHUB_ACTIONS") == "true":
        url = ""
        if _env("GITHUB_REPOSITORY") and _env("GITHUB_RUN_ID"):
            server = _env("GITHUB_SERVER_URL", "https://github.com")
            url = f"{server}/{_env('GITHUB_REPOSITORY')}/actions/runs/{_env('GITHUB_RUN_ID')}"
        return {"provider": "GitHub Actions", "url": url, "build": _env("GITHUB_RUN_NUMBER")}
    if _env("TF_BUILD"):
        url = ""
        if _env("SYSTEM_COLLECTIONURI") and _env("BUILD_BUILDID"):
            url = (f"{_env('SYSTEM_COLLECTIONURI')}{_env('SYSTEM_TEAMPROJECT')}"
                   f"/_build/results?buildId={_env('BUILD_BUILDID')}")
        return {"provider": "Azure DevOps", "url": url, "build": _env("BUILD_BUILDNUMBER")}
    if _env("GITLAB_CI"):
        return {"provider": "GitLab CI", "url": _env("CI_PIPELINE_URL"), "build": _env("CI_PIPELINE_IID")}
    if _env("JENKINS_URL"):
        return {"provider": "Jenkins", "url": _env("BUILD_URL"), "build": _env("BUILD_NUMBER")}
    if _env("CI"):
        return {"provider": "CI", "url": "", "build": ""}
    return {}


def _project_base_url() -> str:
    """Fall back to the framework's own Config default when SNXT_BASE_URL is not exported."""
    try:
        from config import Config  # project-level config.py; optional for other projects
        return str(getattr(Config(), "base_url", "") or "")
    except Exception:
        return ""


def _derive_environment(base_url: str) -> str:
    """Best-effort environment label from the app URL when SNXT_ENV is not set."""
    host = (urlparse(base_url).hostname or "").lower()
    for needle, label in (("uat", "UAT"), ("stag", "Staging"), ("qa", "QA"), ("dev", "DEV"),
                          ("localhost", "Local"), ("127.0.0.1", "Local")):
        if needle in host:
            return label
    return host or "Unknown"


def _executed_by() -> str:
    who = _first_env("SNXT_EXECUTED_BY", "GITHUB_ACTOR", "BUILD_REQUESTEDFOR",
                     "GITLAB_USER_LOGIN", "BUILD_USER", "USERNAME", "USER")
    if who:
        return who
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover - exotic environments without a login user
        return "unknown"


# Environment variables whose *values* must never appear in a report (passwords, tokens ...).
_SECRET_ENV_PATTERN = re.compile(r"(PASS|PASSWORD|SECRET|TOKEN|API_KEY|APIKEY)", re.I)


def _secret_values() -> tuple[str, ...]:
    values = {v for k, v in os.environ.items() if _SECRET_ENV_PATTERN.search(k) and len(v) >= 4}
    # Longest first so overlapping secrets are fully masked.
    return tuple(sorted(values, key=len, reverse=True))


@dataclass(frozen=True)
class ReportSettings:
    """Immutable reporter settings. Build with :meth:`resolve`."""

    report_root: Path
    run_name: str
    project_name: str
    environment: str
    base_url: str
    build_version: str
    executed_by: str
    ci: dict[str, str] = field(default_factory=dict)

    generate_pdf: bool = True
    embed_screenshots: bool = False
    full_page_screenshot: bool = True
    copy_latest: bool = True
    keep_runs: int = 0              # 0 = keep every run folder
    keep_media_runs: int = 1        # newest N runs keep screenshots/ + videos/; 0 = keep media of every run
    history_size: int = 30          # runs kept in history/history.json
    test_history_size: int = 10     # per-test status dots shown in the report

    max_events_per_test: int = 200  # console / network / API entries kept per test
    api_body_limit: int = 4000      # chars of request/response body kept per API call
    api_url_filter: Optional[re.Pattern[str]] = None
    ignore_aborted_requests: bool = True
    secret_values: tuple[str, ...] = ()

    @classmethod
    def resolve(cls, *, report_dir: Optional[str], run_name: str, no_pdf: bool) -> "ReportSettings":
        base_url = _first_env("SNXT_BASE_URL") or _project_base_url()
        ci = detect_ci()
        api_filter = _env("SNXT_REPORT_API_FILTER")
        return cls(
            report_root=Path(report_dir or _env("SNXT_REPORT_DIR", "reports")).resolve(),
            run_name=run_name,
            project_name=_env("SNXT_PROJECT_NAME", "SprintNXT"),
            environment=_env("SNXT_ENV") or _derive_environment(base_url),
            base_url=base_url,
            build_version=_first_env("SNXT_BUILD_VERSION", "BUILD_VERSION")
                          or (f"{ci['provider']} #{ci['build']}" if ci.get("build") else "local"),
            executed_by=_executed_by(),
            ci=ci,
            generate_pdf=not no_pdf and _env_bool("SNXT_REPORT_PDF", True),
            embed_screenshots=_env_bool("SNXT_REPORT_EMBED_SCREENSHOTS", False),
            full_page_screenshot=_env_bool("SNXT_REPORT_FULL_PAGE", True),
            copy_latest=_env_bool("SNXT_REPORT_COPY_LATEST", True),
            keep_runs=max(0, _env_int("SNXT_REPORT_KEEP_RUNS", 0)),
            keep_media_runs=max(0, _env_int("SNXT_REPORT_KEEP_MEDIA", 1)),
            history_size=max(1, _env_int("SNXT_REPORT_HISTORY", 30)),
            test_history_size=max(1, _env_int("SNXT_REPORT_TEST_HISTORY", 10)),
            max_events_per_test=max(10, _env_int("SNXT_REPORT_MAX_EVENTS", 200)),
            api_body_limit=max(200, _env_int("SNXT_REPORT_API_BODY_LIMIT", 4000)),
            api_url_filter=re.compile(api_filter) if api_filter else None,
            ignore_aborted_requests=_env_bool("SNXT_REPORT_IGNORE_ABORTED", True),
            secret_values=_secret_values(),
        )
