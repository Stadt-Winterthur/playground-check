"""Internal command invocation for the native Django GUI.

Transport-independent input: domain commands receive parsed JSON, preserved
identity headers and optional query parameters without constructing or routing
an artificial Django HTTP request. Public DRF views remain unchanged.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class CommandInput:
    """In-process command parameters; never a browser request or HTTP client."""
    META: dict
    body: bytes


def command_input(request, payload, *, method="POST", url="/"):
    parsed = urlsplit(url)
    body = json.dumps(payload).encode("utf-8")
    # Inherit only authenticated HTTP identity context. CSRF and content-length
    # from the browser form must NOT be copied to this internal JSON command.
    meta = {key: value for key, value in request.META.items()
            if key.startswith("HTTP_") and key not in
            {"HTTP_CONTENT_LENGTH", "HTTP_CONTENT_TYPE", "HTTP_X_CSRFTOKEN"}}
    meta.update({"REQUEST_METHOD": method.upper(), "PATH_INFO": parsed.path,
                 "QUERY_STRING": parsed.query, "CONTENT_TYPE": "application/json",
                 "CONTENT_LENGTH": str(len(body))})
    return CommandInput(meta, body)


def invoke(request, handler, payload, *, method="POST", url="/", kwargs=None):
    """Call the existing Python domain command directly, without RequestFactory."""
    return handler(command_input(request, payload, method=method, url=url),
                   **(kwargs or {}))
