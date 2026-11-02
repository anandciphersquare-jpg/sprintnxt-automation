"""Masks credentials before anything is written to disk.

Two layers:
* known secret *values* (from env vars named *PASS*/*TOKEN*/... ) are replaced anywhere they appear;
* sensitive header names and JSON keys (authorization, cookie, access_token ...) are masked.

Generated test data (random emails, invalid passwords under test) is deliberately NOT masked:
it is the evidence a QA reviewer needs.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

MASK = "••••••"

SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key", "x-auth-token",
                     "proxy-authorization", "x-access-token"}
_SENSITIVE_KEY = re.compile(r"^(authorization|access_?token|refresh_?token|id_?token|token|secret|"
                            r"client_?secret|api_?key|session_?id|jwt)$", re.I)


class Redactor:
    def __init__(self, secret_values: Iterable[str]):
        self._secrets = tuple(s for s in secret_values if s)

    def text(self, value: str) -> str:
        if not value:
            return value
        for secret in self._secrets:
            if secret in value:
                value = value.replace(secret, MASK)
        return value

    def headers(self, headers: dict[str, str]) -> dict[str, str]:
        return {k: (MASK if k.lower() in SENSITIVE_HEADERS else self.text(v)) for k, v in headers.items()}

    def body(self, body: str, limit: int) -> str:
        """Mask sensitive JSON keys (when the body is JSON), known secrets, then truncate."""
        if not body:
            return ""
        stripped = body.lstrip()
        if stripped[:1] in "{[":
            try:
                body = json.dumps(self._mask_json(json.loads(body)), ensure_ascii=False, indent=2)
            except ValueError:
                pass
        body = self.text(body)
        if len(body) > limit:
            body = body[:limit] + f"\n… [truncated {len(body) - limit} chars]"
        return body

    def value(self, value: Any) -> Any:
        """Redact an arbitrary (JSON-able) value used as test data / step params."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {k: (MASK if _SENSITIVE_KEY.match(str(k)) else self.value(v)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.value(v) for v in value]
        if value is None or isinstance(value, (int, float, bool)):
            return value
        return self.text(repr(value))

    def _mask_json(self, node: Any) -> Any:
        if isinstance(node, dict):
            return {k: (MASK if _SENSITIVE_KEY.match(str(k)) else self._mask_json(v)) for k, v in node.items()}
        if isinstance(node, list):
            return [self._mask_json(v) for v in node]
        return node
