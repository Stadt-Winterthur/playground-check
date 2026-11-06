from __future__ import annotations

import json
import logging
import os
import queue
import socket
import ssl
import sys
import threading
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings


_LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}


class ElkLogHandler(logging.Handler):
    """Non-blocking HTTP log sink compatible with the legacy GDIW ELK payload."""

    def __init__(self, *, url: str, verify_ssl: bool, environment: str,
                 directory: str, service: str, hostname: str | None = None) -> None:
        super().__init__(level=logging.INFO)
        self.url = url
        self.verify_ssl = verify_ssl
        self.environment = environment
        self.directory = directory
        self.service = service
        self.hostname = hostname or socket.gethostname()
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=1024)
        self._worker = threading.Thread(target=self._process_queue, name="playground-elk-log", daemon=True)
        self._worker.start()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = self.build_payload(record)
            self._queue.put_nowait(payload)
        except queue.Full:
            # Legacy sink uses TryAdd: dropping a log event is preferable to blocking requests.
            return
        except Exception:
            self.handleError(record)

    def build_payload(self, record: logging.LogRecord) -> dict[str, Any]:
        details: list[str] = []
        if record.exc_info:
            details.append("".join(traceback.format_exception(*record.exc_info)).rstrip())
        details.extend(str(value) for value in getattr(record, "elk_details", []) if value is not None)

        payload: dict[str, Any] = {
            "@timestamp": datetime.fromtimestamp(record.created, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "host": self.hostname,
            "environment": self.environment,
            "level": _LEVEL_NAMES.get(record.levelno, record.levelname.upper()),
            "message": record.getMessage(),
            "directory": self.directory,
            "service": self.service,
        }
        if details:
            payload["details"] = details
        return payload

    def close(self) -> None:
        if getattr(self, "_worker", None) is not None and self._worker.is_alive():
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
            self._worker.join(timeout=5)
        super().close()

    def _process_queue(self) -> None:
        while True:
            payload = self._queue.get()
            if payload is None:
                return
            try:
                self._post(payload)
            except Exception as exc:
                # Keep logging failures isolated from application requests, like the legacy sink.
                print(f"Warnung: Log-Sendung an ELK fehlgeschlagen: {exc}", file=sys.stderr)

    def _post(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        context = None
        if self.url.lower().startswith("https://") and not self.verify_ssl:
            context = ssl._create_unverified_context()  # noqa: SLF001 - explicit legacy VerifySsl=false support
        with urllib.request.urlopen(request, timeout=10, context=context) as response:
            response.read(1)


def configure_logging(settings: Settings) -> None:
    """Configure console logging and the optional legacy-compatible ELK sink once."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if not any(getattr(handler, "_playground_console", False) for handler in root.handlers):
        console = logging.StreamHandler()
        console._playground_console = True  # type: ignore[attr-defined]
        console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root.addHandler(console)

    is_development = os.getenv("ASPNETCORE_ENVIRONMENT", "Production").lower() == "development"
    if settings.elk_url and not is_development and not any(isinstance(handler, ElkLogHandler) for handler in root.handlers):
        root.addHandler(ElkLogHandler(
            url=settings.elk_url,
            verify_ssl=settings.elk_verify_ssl,
            environment=settings.elk_environment,
            directory=settings.elk_directory,
            service=settings.elk_service,
        ))
