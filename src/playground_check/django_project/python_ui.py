"""Opt-in Django template GUI. Read-only views reuse the established repositories.

The old SPA must remain available until browser functionality and offline sync have
been rebuilt and acceptance-tested. Never expose private data to unauthenticated users.
"""
from __future__ import annotations

import logging
import os
import json
from pathlib import Path
from functools import wraps

from django.http import HttpResponse
from django.test import RequestFactory
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect
from django.template import Context, Engine
from django.views.decorators.http import require_GET, require_http_methods

from playground_check.config import settings
from playground_check.db import connect
from playground_check.domain_support import require_user, playground_by_name_data, playground_only_names_data
from playground_check.remaining_reads_repository import defect_overview_rows
from playground_check.http import Request as LegacyRequest

LOGGER = logging.getLogger(__name__)
TEMPLATE_ROOT = Path(__file__).resolve().parent / "ui_templates"
ENGINE = Engine(dirs=[str(TEMPLATE_ROOT)], autoescape=True)


def _prefix(request):
    """Keep all links and assets under the actual reverse-proxy application path."""
    value = (request.META.get("SCRIPT_NAME") or settings.base_path or "").rstrip("/")
    return ("/" + value.lstrip("/")) if value else ""


def _render(request, template, data=None, *, status=200, partial=False):
    values = {"prefix": _prefix(request), "page_title": "Spielplatzkontrolle", **(data or {})}
    if partial:
        body = ENGINE.get_template(template).render(Context(values))
    else:
        values["body"] = ENGINE.get_template(template).render(Context(values))
        body = ENGINE.get_template("layout.html").render(Context(values))
    response = HttpResponse(body, status=status, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    response["Vary"] = "Cookie, Authorization, HX-Request"
    return response


def _identity(request):
    """Use the same validated cookie/JWT and database revalidation as the DRF API."""
    return require_user(LegacyRequest(dict(request.META)))


def _private(request):
    try:
        user, error = _identity(request)
    except Exception:
        LOGGER.exception("GUI authentication failed")
        return None, _render(request, "error.html", {"message": "Anmeldung derzeit nicht möglich.", "private": True}, status=503)
    if error or not user:
        return None, _render(request, "login_required.html", {"private": True}, status=401)
    return user, None


def ui_login_required(view):
    """Fail closed before ANY GUI view performs a query or renders an HTMX fragment.

    Existing JWT/cookie credentials are revalidated through the established
    domain auth layer; no parallel, weaker test-only authentication exists.
    """
    @wraps(view)
    def guarded(request, *args, **kwargs):
        _user, denial = _private(request)
        if denial is not None:
            return denial
        return view(request, *args, **kwargs)
    return guarded


@require_GET
@ui_login_required
def home(request):
    return _render(request, "home.html", {"private": True})


@require_GET
@ui_login_required
def playgrounds(request):
    """Authenticated lookup with bounded result set and HTMX progressive enhancement."""
    query = (request.GET.get("q") or "").strip()[:120]
    try:
        with connect() as db:
            rows = db.execute('SELECT name, strassenname AS street_name, hausnummer AS house_no '
                              'FROM "wgr_sp_spielplatz" ORDER BY name').fetchall()
    except Exception:
        LOGGER.exception("Could not fetch public playground list")
        return _render(request, "error.html", {"message": "Daten vorübergehend nicht verfügbar.", "private": True}, status=503)
    found = [dict(x) for x in rows if query.casefold() in str(x.get("name") or "").casefold()][:200]
    context = {"query": query, "rows": found, "count": len(found), "private": True}
    partial = request.headers.get("HX-Request") == "true"
    return _render(request, "playgrounds_rows.html" if partial else "playgrounds.html", context, partial=partial)


@require_GET
@ui_login_required
def workspace(request):
    user, denied = _private(request)
    if denied: return denied
    return _render(request, "workspace.html", {"user": user, "private": True})


@require_GET
@ui_login_required
def assigned_playgrounds(request):
    """Authorized inspection-specific playground selector from the shared domain service."""
    user, denied = _private(request)
    if denied: return denied
    query = (request.GET.get("q") or "").strip()[:120]
    inspection_type = (request.GET.get("inspectiontype") or "").strip()[:100]
    try:
        rows = playground_only_names_data(user, {"inspectiontype": inspection_type})
    except Exception:
        LOGGER.exception("Could not load assigned playgrounds")
        return _render(request, "error.html", {"message": "Spielplätze können derzeit nicht geladen werden.", "private": True}, status=503)
    found = [x for x in rows if query.casefold() in str(x.get("name") or "").casefold()][:200]
    context = {"rows": found, "query": query, "inspection_type": inspection_type, "user": user, "private": True}
    partial = request.headers.get("HX-Request") == "true"
    return _render(request, "assigned_rows.html" if partial else "assigned.html", context, partial=partial)


@require_GET
@ui_login_required
def playground_detail(request):
    """Authorized read of play devices and inspection history, no browser-side data duplication."""
    user, denied = _private(request)
    if denied: return denied
    name = (request.GET.get("name") or "").strip()[:200]
    if not name:
        return _render(request, "error.html", {"message": "Kein Spielplatz ausgewählt.", "private": True}, status=400)
    kind = (request.GET.get("inspectiontype") or "").strip()[:100]
    try:
        payload = playground_by_name_data({"name": name, "inspectiontype": kind, "withdefects": "true", "withinspections": "true"})
    except LookupError:
        return _render(request, "error.html", {"message": "Spielplatz nicht gefunden.", "private": True}, status=404)
    except Exception:
        LOGGER.exception("Could not load playground detail")
        return _render(request, "error.html", {"message": "Spielplatzdetails sind derzeit nicht verfügbar.", "private": True}, status=503)
    return _render(request, "detail.html", {"playground": payload, "kind": kind, "private": True, "user": user})


@require_GET
@ui_login_required
def defects(request):
    """Private defect overview with bounded display and progressive-enhancement search.

    Uses the same read-only repository as the DRF defect overview; no direct SQL
    in templates and no mutation endpoints exposed by this page.
    """
    user, denied = _private(request)
    if denied:
        return denied
    query = (request.GET.get("q") or "").strip()[:120]
    state = (request.GET.get("state") or "open").strip().lower()
    if state not in {"open", "all", "done"}:
        state = "open"
    try:
        page = max(1, min(10000, int(request.GET.get("page", "1"))))
    except (TypeError, ValueError):
        page = 1
    try:
        with connect() as db:
            rows = defect_overview_rows(db)
    except Exception:
        LOGGER.exception("Could not load defect overview")
        return _render(request, "error.html", {"message": "Mängel sind derzeit nicht verfügbar.", "private": True}, status=503)
    filtered = []
    for item in rows:
        row = dict(item)
        done = row.get("done_by") is not None
        if (state == "open" and done) or (state == "done" and not done):
            continue
        if query and query.casefold() not in " ".join(str(row.get(key) or "") for key in ("playground_name", "playdevice_type", "description", "responsible_user_name")).casefold():
            continue
        filtered.append(row)
    size = 30
    count = len(filtered)
    offset = (page - 1) * size
    values = {"rows": filtered[offset:offset + size], "query": query, "state": state,
              "page": page, "has_previous": page > 1, "has_next": offset + size < count,
              "previous": page - 1, "next": page + 1, "count": count,
              "private": True, "user": user}
    partial = request.headers.get("HX-Request") == "true"
    return _render(request, "defects_rows.html" if partial else "defects.html", values, partial=partial)


@csrf_protect
@require_http_methods(["GET", "POST"])
@ui_login_required
def inspection_editor(request):
    """Logged-in, CSRF-protected inspection form; writes via tested domain command.

    Always re-resolve the playground and eligible device IDs on POST: never
    accept a client-provided device set, inspection type or playground identity.
    """
    from .inspection_device_commands import create_inspection
    user, denied = _private(request)
    if denied is not None:
        return denied
    if user.get("role") not in {"inspector", "administrator"}:
        return _render(request, "error.html", {"message": "Keine Berechtigung für Inspektionen.", "private": True}, status=403)
    source = request.POST if request.method == "POST" else request.GET
    name = (source.get("name") or "").strip()[:200]
    kind = (source.get("inspectiontype") or "").strip()[:100]
    if not name or not kind:
        return _render(request, "error.html", {"message": "Spielplatz und Inspektionsart erforderlich.", "private": True}, status=400)
    try:
        permitted = playground_only_names_data(user, {"inspectiontype": kind})
        if not any(x.get("name") == name and not x.get("inspectionSuspended") for x in permitted):
            return _render(request, "error.html", {"message": "Inspektion für diesen Spielplatz nicht freigegeben.", "private": True}, status=403)
        payload = playground_by_name_data({"name": name, "inspectiontype": kind, "withdefects": "true", "withinspections": "true"})
    except Exception:
        LOGGER.exception("Failed to prepare inspection editor")
        return _render(request, "error.html", {"message": "Inspektion derzeit nicht verfügbar.", "private": True}, status=503)
    if payload.get("inspectionSuspended"):
        return _render(request, "error.html", {"message": "Inspektionen sind ausgesetzt.", "private": True}, status=403)
    options = payload.get("inspectionTypeOptions") or []
    if kind not in options:
        return _render(request, "error.html", {"message": "Unbekannte Inspektionsart.", "private": True}, status=400)
    devices = []
    for item in payload.get("playdevices") or []:
        try:
            fid = int(item.get("fid") or 0)
        except (TypeError, ValueError):
            continue
        if fid > 0:
            props = item.get("properties") or item
            groups = (("generalInspectionCriteria", ""),
                      ("mainFallProtectionInspectionCriteria", "Hauptfallschutz"),
                      ("secondaryFallProtectionInspectionCriteria", "Nebenfallschutz"))
            checks = []
            for group, fall in groups:
                for index, criterion in enumerate(props.get(group) or []):
                    checks.append({"index": len(checks), "group": group, "fall": fall,
                                   "label": criterion.get("checkShortText") or criterion.get("check") or "Prüfung",
                                   "realm": criterion.get("realm") or "",
                                   "check": criterion.get("check") or "",
                                   "maintenance": criterion.get("maintenance") or ""})
            devices.append({"fid": fid, "name": item.get("name") or props.get("type", {}).get("description") or f"Spielgerät {fid}",
                            "checks": checks, "not_to_be_checked": bool(props.get("notToBeChecked")),
                            "cannot_be_checked": bool(props.get("cannotBeChecked"))})
    if not devices or len(devices) > 300 or len({d["fid"] for d in devices}) != len(devices):
        return _render(request, "error.html", {"message": "Keine gültige Geräteliste verfügbar.", "private": True}, status=400)
    context = {"name": name, "kind": kind, "devices": devices, "private": True, "user": user}
    if request.method == "GET":
        context["csrf_token_value"] = get_token(request)
        return _render(request, "inspection_editor.html", context)
    # Keep writes disabled until full criteria and browser acceptance are verified.
    if os.environ.get("PLAYGROUND_UI_INSPECTION_WRITE_ENABLED", "").lower() != "true":
        return _render(request, "error.html", {"message": "Speicherung in der neuen Oberfläche ist noch nicht freigegeben.", "private": True}, status=403)
    if request.content_type != "application/x-www-form-urlencoded":
        return _render(request, "error.html", {"message": "Ungültiger Formularinhalt.", "private": True}, status=400)
    if len(request.body) > 200000:
        return _render(request, "error.html", {"message": "Formular ist zu gross.", "private": True}, status=413)
    reports = []
    for device in devices:
        fid = device["fid"]
        if device["not_to_be_checked"]:
            continue
        if device["cannot_be_checked"]:
            return _render(request, "error.html", {"message": "Nicht prüfbare Geräte müssen zuerst in den Stammdaten bearbeitet werden.", "private": True}, status=409)
        for criterion in device["checks"]:
            i = criterion["index"]
            key = f"{fid}_{i}"
            comment = (request.POST.get(f"comment_{key}") or "").strip()
            maintenance_comment = (request.POST.get(f"maintenance_comment_{key}") or "").strip()
            if len(comment) > 2000 or len(maintenance_comment) > 2000:
                return _render(request, "error.html", {"message": "Kommentar zu lang.", "private": True}, status=400)
            if request.POST.get(f"inspection_done_{key}") != "on" or request.POST.get(f"maintenance_done_{key}") != "on":
                return _render(request, "error.html", {"message": "Alle Prüf- und Wartungspositionen müssen abgeschlossen sein.", "private": True}, status=400)
            reports.append({"inspectionType": kind, "playdeviceFid": fid,
                            "inspectionText": criterion["check"],
                            "maintenanceText": criterion["maintenance"],
                            "fallProtectionType": criterion["fall"],
                            "inspectionDone": True, "maintenanceDone": True,
                            "inspectionComment": comment,
                            "maintenanceComment": maintenance_comment})
    if not reports:
        return _render(request, "error.html", {"message": "Keine Prüfkriterien vorhanden.", "private": True}, status=400)
    if request.POST.get("confirm") != "yes":
        return _render(request, "error.html", {"message": "Bitte die Speicherung bestätigen.", "private": True}, status=400)
    # Reuse the existing DRF command and its authorization, duplicate detection,
    # table locks, and FID/TID rules. No independent SQL write implementation.
    meta = {k: v for k, v in request.META.items() if k.startswith("HTTP_") and k != "HTTP_CONTENT_LENGTH"}
    native_request = RequestFactory().post("/Inspection/", data=json.dumps(reports),
                                           content_type="application/json", **meta)
    result = create_inspection(native_request)
    try:
        result_data = json.loads(result.content)
    except (TypeError, ValueError):
        result_data = {}
    if result.status_code != 200 or result_data.get("errorMessage") != "":
        LOGGER.warning("Inspection was rejected with status %s", result.status_code)
        return _render(request, "error.html", {"message": "Inspektion konnte nicht gespeichert werden. Bitte Berechtigung, Datum und Eingaben prüfen.", "private": True}, status=409)
    return _render(request, "inspection_success.html", {"name": name, "kind": kind, "private": True})


@csrf_protect
@require_http_methods(["GET", "POST"])
@ui_login_required
def defect_detail(request):
    """Authenticated defect detail and explicit assignment decision.

    Mutation goes exclusively through the native assignment command; the browser
    never provides a user FID, an SQL field name, or authorization context.
    """
    from .defect_native import assignment_status
    user, denied = _private(request)
    if denied is not None:
        return denied
    source = request.POST if request.method == "POST" else request.GET
    try:
        tid = int(source.get("tid", ""))
    except (TypeError, ValueError):
        return _render(request, "error.html", {"message": "Ungültige Mangelnummer.", "private": True}, status=400)
    if not 0 < tid < 2**31:
        return _render(request, "error.html", {"message": "Ungültige Mangelnummer.", "private": True}, status=400)
    if request.method == "POST":
        action = request.POST.get("action")
        if action not in {"accept", "reject"}:
            return _render(request, "error.html", {"message": "Ungültige Aktion.", "private": True}, status=400)
        if request.content_type != "application/x-www-form-urlencoded" or len(request.body) > 12000:
            return _render(request, "error.html", {"message": "Ungültiger Formularinhalt.", "private": True}, status=400)
        comment = (request.POST.get("comment") or "").strip()
        if len(comment) > 1000:
            return _render(request, "error.html", {"message": "Kommentar zu lang.", "private": True}, status=400)
        native_request = RequestFactory().post(
            f"/Defect/{tid}/{'accept' if action == 'accept' else 'reject'}/",
            data=json.dumps({"assignmentComment": comment}),
            content_type="application/json",
            **{k: v for k, v in request.META.items() if k.startswith("HTTP_") and k != "HTTP_CONTENT_LENGTH"},
        )
        try:
            result = assignment_status(native_request, tid, accepted=action == "accept")
            body = json.loads(result.content)
        except Exception:
            LOGGER.exception("Assignment action failed")
            return _render(request, "error.html", {"message": "Zuweisung konnte nicht gespeichert werden.", "private": True}, status=503)
        if result.status_code != 200 or body.get("errorMessage") != "":
            return _render(request, "error.html", {"message": "Aktion nicht zulässig oder nicht erfolgreich.", "private": True}, status=403)
    try:
        with connect() as db:
            from playground_check.inspection_defect_repository import defect_by_tid
            from playground_check.domain_support import _defect_dict
            row = defect_by_tid(db, tid)
            data = _defect_dict(db, row) if row else None
    except Exception:
        LOGGER.exception("Defect detail lookup failed")
        return _render(request, "error.html", {"message": "Mangel derzeit nicht verfügbar.", "private": True}, status=503)
    if not data:
        return _render(request, "error.html", {"message": "Mangel nicht gefunden.", "private": True}, status=404)
    return _render(request, "defect_detail.html", {"defect": data, "tid": tid,
                    "csrf_token_value": get_token(request), "private": True, "user": user,
                    "saved": request.method == "POST"})


@require_GET
@ui_login_required
def my_profile(request):
    """Minimal private account page: authenticated identity, no password exposure."""
    user, denial = _private(request)
    if denial is not None:
        return denial
    values = {"private": True, "display_name": user.get("name") or user.get("mailAddress") or "Benutzer",
              "role": user.get("role") or "", "email": user.get("mailAddress") or ""}
    return _render(request, "profile.html", values)
