"""Download the pinned upstream HTMX release for local, CDN-free hosting.

Run once in a network-enabled development environment. The vendored artifact
must be committed to the repository and served from the application's own host.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from urllib.request import Request, urlopen

VERSION = "2.0.11"
URL = f"https://cdn.jsdelivr.net/npm/htmx.org@{VERSION}/dist/htmx.min.js"
# Official upstream documentation's SRI for HTMX 2.0.11 (SHA-384).
EXPECTED_SRI = "sha384-2OatzQy1H+Zd/IIrjr1TcuDGqLXeHhbooAyJY1KdQMKnr4LZ22k31GBLdYKHmVjg"
DESTINATION = Path(__file__).resolve().parents[1] / "src/playground_check/static/vendor/htmx.min.js"


def verify(data: bytes) -> None:
    if not 10_000 < len(data) < 200_000:
        raise ValueError("Unexpected HTMX release size")
    actual = "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode("ascii")
    if actual != EXPECTED_SRI:
        raise ValueError("HTMX integrity check failed; local file not changed")


def main() -> None:
    request = Request(URL, headers={"User-Agent": "Spielplatzkontrolle-HTMX-vendor/1.0"})
    with urlopen(request, timeout=20) as response:
        content = response.read(200_001)
    verify(content)
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporary = DESTINATION.with_suffix(".js.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(DESTINATION)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"HTMX {VERSION} verified and installed at {DESTINATION}")
    print(f"SHA256: {hashlib.sha256(content).hexdigest()}")


if __name__ == "__main__":
    main()
