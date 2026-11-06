"""WMS map-image lookup shared by legacy WSGI and Django REST Framework.

The public contract is a JSON string containing base64-encoded upstream bytes,
not a raw image response. Do not change WMS parameters or exception handling
without comparing both entry points.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping
from urllib.error import HTTPError
from urllib.request import urlopen

from .config import settings


def map_image_base64(query: Mapping[str, str], *, endpoint_override: str | None = None) -> str:
    x = float(query.get("x", "0") or 0)
    y = float(query.get("y", "0") or 0)
    if x == 0 or y == 0:
        return ""
    endpoint = (endpoint_override or settings.wms_url).strip()
    if not endpoint.lower().startswith(("http://", "https://")):
        endpoint = "http://" + endpoint
    if not endpoint.rstrip("/").endswith("Spielplatzkarte"):
        endpoint = endpoint.rstrip("/") + "/Spielplatzkarte"
    url = endpoint + "?LAYERS=AV_UEP_Landeskarten,Spielplatz&VERSION=1.1.1&DPI=96&TRANSPARENT=TRUE&FORMAT=image%2Fpng&" \
        "SERVICE=WMS&REQUEST=GetMap&STYLES=&SRS=EPSG%3A2056&" \
        f"BBOX={x-10},{y-5},{x+10},{y+5}&WIDTH=800&HEIGHT=400"
    try:
        response = urlopen(url, timeout=20)
    except HTTPError as exc:
        response = exc
    with response:
        return base64.b64encode(response.read()).decode("ascii")
