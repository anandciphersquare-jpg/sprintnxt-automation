"""Typed records that make up a report. Everything serialises to plain JSON via ``to_dict``."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

Status = Literal["PASS", "FAIL", "BLOCKED", "SKIPPED"]
STATUSES: tuple[Status, ...] = ("PASS", "FAIL", "BLOCKED", "SKIPPED")


@dataclass
class StepRecord:
    title: str
    depth: int
    start_ms: int                       # offset from test start
    duration_ms: int = 0
    status: Literal["passed", "failed", "running"] = "running"
    kind: Literal["step", "navigation", "note"] = "step"
    params: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class ApiLog:
    method: str
    url: str
    status: Optional[int]
    duration_ms: Optional[float]
    at_ms: int
    resource_type: str
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: str = ""
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: str = ""
    failure: str = ""


@dataclass
class ConsoleEntry:
    level: str          # error | warning | pageerror
    text: str
    at_ms: int
    location: str = ""


@dataclass
class NetworkFailure:
    method: str
    url: str
    at_ms: int
    status: Optional[int] = None      # HTTP status for 4xx/5xx responses
    failure: str = ""                 # net::ERR_* for transport failures
    resource_type: str = ""


@dataclass
class Artifact:
    kind: Literal["screenshot", "video", "trace", "attachment"]
    title: str
    path: str                         # relative to the run folder (or a data: URI)
    mime: str = ""
    attempt: int = 1


@dataclass
class Attempt:
    attempt: int
    status: Status
    duration_ms: int
    failure_reason: str = ""
    failure_category: str = ""


@dataclass
class TestCaseResult:
    # identity / catalogue
    id: str
    nodeid: str
    title: str
    module: str
    feature: str
    types: list[str]
    preconditions: list[str]
    expected: str
    description: str
    file: str
    line: int
    markers: list[str]
    # execution
    status: Status
    actual: str
    failure_reason: str
    failure_category: str
    error: str
    test_data: dict[str, Any]
    steps: list[StepRecord]
    artifacts: list[Artifact]
    api_logs: list[ApiLog]
    console: list[ConsoleEntry]
    network_failures: list[NetworkFailure]
    captured_output: str
    start: str
    end: str
    duration_ms: int
    browser: str
    worker: str
    attempts: list[Attempt]
    retries: int
    flaky: bool
    user_properties: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
