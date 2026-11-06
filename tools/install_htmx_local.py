"""Vendor an official locally downloaded HTMX distribution, not a CDN runtime dependency.
Usage: python tools/install_htmx_local.py /path/to/official/htmx.min.js
"""
from pathlib import Path
import hashlib
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: python tools/install_htmx_local.py /path/to/htmx.min.js")
source = Path(sys.argv[1])
data = source.read_bytes()
if not (10000 < len(data) < 150000) or b"htmx" not in data.lower():
    raise SystemExit("Unexpected HTMX file; refusing to install")
dest = Path(__file__).resolve().parents[1] / "src/playground_check/static/vendor/htmx.min.js"
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_bytes(data)
print("Installed:", dest, "SHA256:", hashlib.sha256(data).hexdigest())
print("IMPORTANT: Verify the SHA256 against the official release before committing.")
