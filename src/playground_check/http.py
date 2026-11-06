from __future__ import annotations

import json
import mimetypes
from decimal import Decimal
import re
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs


class JsonBodyError(ValueError):
    """Raised when the request body cannot be bound from JSON."""


class CaseInsensitiveJsonObject(dict[str, Any]):
    """Dictionary with ASP.NET/System.Text.Json-like case-insensitive property lookup."""

    def _matching_key(self, key: object) -> object:
        if not isinstance(key, str):
            return key
        lowered = key.casefold()
        for existing in self.keys():
            if isinstance(existing, str) and existing.casefold() == lowered:
                return existing
        return key

    def __getitem__(self, key: object) -> Any:
        return super().__getitem__(self._matching_key(key))

    def __contains__(self, key: object) -> bool:
        return super().__contains__(self._matching_key(key))

    def get(self, key: object, default: Any = None) -> Any:
        return super().get(self._matching_key(key), default)

    def pop(self, key: object, default: Any = None) -> Any:
        matching = self._matching_key(key)
        if super().__contains__(matching):
            return super().pop(matching)
        return default


def _case_insensitive_object(pairs: list[tuple[str, Any]]) -> CaseInsensitiveJsonObject:
    result = CaseInsensitiveJsonObject()
    for key, value in pairs:
        # System.Text.Json web defaults bind property names case-insensitively. If the
        # same logical property occurs more than once, keep the last value.
        existing = result._matching_key(key)
        if existing in result:
            dict.__delitem__(result, existing)
        dict.__setitem__(result, key, value)
    return result


@dataclass
class Request:
    environ: dict[str, Any]
    params: dict[str, str] = field(default_factory=dict)

    @property
    def method(self) -> str:
        return self.environ.get("REQUEST_METHOD", "GET").upper()

    @property
    def path(self) -> str:
        value = self.environ.get("PATH_INFO", "/") or "/"
        return re.sub(r"/{2,}", "/", value)

    @property
    def query(self) -> dict[str, str]:
        parsed = parse_qs(self.environ.get("QUERY_STRING", ""), keep_blank_values=True)
        return {key: values[-1] for key, values in parsed.items()}

    @property
    def headers(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in self.environ.items():
            if key.startswith("HTTP_"):
                result[key[5:].replace("_", "-").title()] = value
        if "CONTENT_TYPE" in self.environ:
            result["Content-Type"] = self.environ["CONTENT_TYPE"]
        return result

    def json(self) -> Any:
        try:
            size = int(self.environ.get("CONTENT_LENGTH") or 0)
            data = self.environ["wsgi.input"].read(size) if size else b""
            if not data:
                return None
            return json.loads(data.decode("utf-8"), object_pairs_hook=_case_insensitive_object)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JsonBodyError("The JSON value could not be converted.") from exc
        except (TypeError, ValueError) as exc:
            raise JsonBodyError("The request body is not valid JSON.") from exc


@dataclass
class Response:
    body: bytes = b""
    status: int = 200
    content_type: str = "application/json; charset=utf-8"
    headers: list[tuple[str, str]] = field(default_factory=list)

    @classmethod
    def json(cls, value: Any, status: int = 200) -> "Response":
        return cls(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_json_default).encode("utf-8"), status)

    @classmethod
    def text(cls, value: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> "Response":
        return cls(value.encode("utf-8"), status, content_type)

    @classmethod
    def file(cls, value: bytes, content_type: str, filename: str | None = None) -> "Response":
        headers = [("Content-Disposition", f'inline; filename="{filename}"')] if filename else []
        return cls(value, 200, content_type, headers)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(type(value).__name__)


Handler = Callable[[Request], Response | Any]


class Router:
    def __init__(self) -> None:
        self.routes: list[tuple[str, re.Pattern[str], Handler]] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        self.routes.append((method.upper(), re.compile(f"^{pattern}$", re.IGNORECASE), handler))

    def dispatch(self, request: Request) -> Response | None:
        for method, pattern, handler in self.routes:
            if method != request.method:
                continue
            match = pattern.match(request.path)
            if match:
                request.params = match.groupdict()
                result = handler(request)
                return result if isinstance(result, Response) else Response.json(result)
        return None

    def allowed_methods(self, path: str) -> list[str]:
        methods = {method for method, pattern, _ in self.routes if pattern.match(path)}
        return sorted(methods)


def status_line(code: int) -> str:
    try:
        phrase = HTTPStatus(code).phrase
    except ValueError:
        phrase = "Unknown"
    return f"{code} {phrase}"

