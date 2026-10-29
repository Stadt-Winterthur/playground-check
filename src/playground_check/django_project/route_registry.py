"""Central method-aware mapping from legacy URLs to canonical Django routes.

Only explicitly migrated method/path pairs go to Django. Every other request
keeps the original WSGI handler (including 400/401/404/405 and SPA fallbacks).
"""
from __future__ import annotations

import re

# Path patterns are case-insensitive and allow legacy trailing slash variants.
# Canonical paths are passed to Django without altering the query string/body.
ROUTES = (
    (r"/__django/health", "GET", "/__django/health"),
    (r"/api/health", "GET", "/api/health"),
    (r"/Inspection/types", "GET", "/Inspection/types/"),
    (r"/Inspection/renovationtypes", "GET", "/Inspection/renovationtypes/"),
    (r"/Inspection", "POST", "/Inspection/"),
    (r"/Playground/mapimage", "GET", "/Playground/mapimage/"),
    (r"/Playground/byname", "GET", "/Playground/byname/"),
    (r"/Playground/onlynames", "GET", "/Playground/onlynames/"),
    (r"/Playground/byplaydevice/(?P<fid>\d+)", "GET", "/Playground/byplaydevice/{fid}/"),
    (r"/Playground/(?P<fid>\d+)", "GET", "/Playground/{fid}/"),
    (r"/Playground/(?P<invalid_id>[^/]+)", "GET", "/Playground/{invalid_id}/"),
    (r"/Collections/Playgrounds/Items", "GET", "/Collections/Playgrounds/Items/"),
    (r"/Collections/Playgrounds/Items/(?P<uuid>[^/]+)", "GET", "/Collections/Playgrounds/Items/{uuid}/"),
    (r"/Defect", "GET POST PUT", "/Defect/"),
    (r"/Defect/Overview", "GET", "/Defect/Overview/"),
    (r"/Defect/Picture/(?P<tid>\d+)", "GET PUT", "/Defect/Picture/{tid}/"),
    (r"/Defect/(?P<tid>\d+)/send-mail", "POST", "/Defect/{tid}/send-mail/"),
    (r"/Defect/(?P<tid>\d+)/accept", "POST", "/Defect/{tid}/accept/"),
    (r"/Defect/(?P<tid>\d+)/reject", "POST", "/Defect/{tid}/reject/"),
    (r"/Account/Login", "POST", "/Account/Login/"),
    (r"/Account/Logout", "POST", "/Account/Logout/"),
    (r"/Account/Me", "GET", "/Account/Me/"),
    (r"/Account/Users/Assignable", "GET", "/Account/Users/Assignable/"),
    (r"/Account/Users", "GET PUT DELETE", "/Account/Users/"),
    (r"/Document/(?P<fid>\d+)/Name", "PUT", "/Document/{fid}/Name/"),
    (r"/Document/(?P<fid>\d+)", "GET DELETE", "/Document/{fid}/"),
    (r"/Document", "POST", "/Document/"),
    (r"/PushSubscription/Register", "POST", "/PushSubscription/Register/"),
    (r"/PushSubscription/Unregister", "DELETE", "/PushSubscription/Unregister/"),
    (r"/PushSubscription/Me", "GET", "/PushSubscription/Me/"),
    (r"/Playdevice", "POST PUT", "/Playdevice/"),
    (r"/Playdevice/(?P<fid>\d+)/Picture", "GET PUT", "/Playdevice/{fid}/Picture/"),
)
_COMPILED = tuple((re.compile(pattern + r"/?", re.IGNORECASE), frozenset(methods.split()), target)
                  for pattern, methods, target in ROUTES)


def migrated_path(path: str, method: str) -> str | None:
    for pattern, allowed, target in _COMPILED:
        if method in allowed:
            match = pattern.fullmatch(path)
            if match:
                return target.format(**match.groupdict())
    return None


def canonical_path(path: str) -> str | None:
    """Canonicalize known API URLs regardless of method (Django owns 405)."""
    for pattern, _allowed, target in _COMPILED:
        match = pattern.fullmatch(path)
        if match:
            return target.format(**match.groupdict())
    return None
