"""Native Django template GUI backed by the established repositories."""
from __future__ import annotations

from playground_check.business_time import local_today

import logging
from pathlib import Path
from functools import wraps, partial

from django.http import HttpResponse, HttpResponseRedirect
from django.utils import translation
from django.utils.cache import patch_vary_headers
from .localization import CODES, LANGUAGES, COOKIE, language_for_request
from django.template import Context, Engine
from django.views.decorators.http import require_GET, require_http_methods

from playground_check import __version__
from playground_check.config import settings
from playground_check.db import connect
from playground_check.playdevice_service import save_device
from playground_check.domain_support import require_user, playground_by_name_data, playground_only_names_data
from playground_check.remaining_reads_repository import defect_overview_rows, playground_directory_rows
from playground_check.user_write_repository import update_ui_language
from playground_check.http import Request as LegacyRequest
from .ui_command_adapter import invoke

LOGGER = logging.getLogger(__name__)
TEMPLATE_ROOT = Path(__file__).resolve().parent / "ui_templates"
ENGINE = Engine(dirs=[str(TEMPLATE_ROOT)], autoescape=True,
                builtins=["playground_check.django_project.templatetags.ui_language"])


def _prefix(request):
    """Keep all links and assets under the actual reverse-proxy application path."""
    value = (request.META.get("SCRIPT_NAME") or settings.base_path or "").rstrip("/")
    return ("/" + value.lstrip("/")) if value else ""


def _render(request, template, data=None, *, status=200, partial=False):
    route = request.path_info.strip("/").split("/", 1)[0]
    nav = {"": "home", "assigned": "inspections" if request.GET.get("inspectiontype") or request.GET.get("mode") == "inspection" else "devices", "detail": "inspections" if request.GET.get("inspectiontype") else "devices", "inspection": "inspections", "defects": "defects", "defect": "defects", "admin": "users", "device": "devices"}.get(route, "")
    values = {"app_version": __version__, "service_worker_enabled": settings.service_worker_enabled, "prefix": _prefix(request), "page_title": "Spielplatzkontrolle", "active_nav": nav, "home_page": template == "home.html", "local_htmx_available": (Path(__file__).resolve().parents[1] / "static/vendor/htmx.min.js").is_file(), **(data or {})}
    if values.get("private") and "role" not in values:
        # Role information must be derived from the already validated identity.
        user = values.get("user") or getattr(request, "_ui_user", None)
        values["user"] = user
        values["role"] = user.get("role") if isinstance(user, dict) else ""
    user = values.get("user") or getattr(request, "_ui_user", None)
    language = language_for_request(request, user)
    values["language_code"] = language
    # Business errors are rendered in-place. Unexpected server failures must
    # remain genuine 5xx responses for monitoring and incident detection.
    if status >= 500:
        values["server_failure"] = True
    with translation.override(language):
        return _render_localized(request, template, values, status=status, partial=partial, language=language)


def _render_localized(request, template, values, *, status, partial, language):
    if partial:
        body = ENGINE.get_template(template).render(Context(values))
    else:
        values["body"] = ENGINE.get_template(template).render(Context(values))
        body = ENGINE.get_template("layout.html").render(Context(values))
    response = HttpResponse(body, status=status, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
        "manifest-src 'self'; worker-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    user = values.get("user") or getattr(request, "_ui_user", None)
    if isinstance(user, dict):
        preferred = user.get("uiLanguage")
        current = request.get_signed_cookie(COOKIE, default="", salt=COOKIE, max_age=31536000)
        if preferred in CODES and preferred != current:
            response.set_signed_cookie(COOKIE, preferred, salt=COOKIE, max_age=31536000,
                                       path=_prefix(request) + "/", secure=request.is_secure(),
                                       httponly=True, samesite="Lax")
        elif preferred not in CODES and request.COOKIES.get(COOKIE):
            response.delete_cookie(COOKIE, path=_prefix(request) + "/", samesite="Lax")
    response["Content-Language"] = language
    patch_vary_headers(response, ("Cookie", "Authorization", "HX-Request", "Accept-Language"))
    return response


def _identity(request):
    """Validate once per GUI request, including rejected credentials.

    The result lives only on this request. Every subsequent HTTP request
    revalidates the account and persistent session against the database.
    Authentication failures still propagate to the caller's error handling.
    """
    if not hasattr(request, "_ui_identity_result"):
        request._ui_identity_result = require_user(LegacyRequest(dict(request.META)))
    return request._ui_identity_result


def _private(request):
    try:
        user, error = _identity(request)
    except Exception:
        LOGGER.exception("GUI authentication failed")
        return None, _render(request, "error.html", {"message": "Anmeldung derzeit nicht möglich.", "private": True}, status=503)
    if error or not user:
        return None, _render(request, "login_required.html", {"private": True}, status=401)
    request._ui_user = user
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
def home(request):
    """Public welcome page; account data and workflows remain protected."""
    user = None
    if request.COOKIES.get(settings.auth_cookie_name):
        try:
            user, error = _identity(request)
            if error:
                user = None
        except Exception:
            LOGGER.exception("Authentication unavailable on public homepage")
    return _render(request, "home.html", {"private": bool(user), "user": user})


@require_GET
@ui_login_required
def playgrounds(request):
    """Authenticated lookup with bounded result set and HTMX progressive enhancement."""
    query = (request.GET.get("q") or "").strip()[:120]
    try:
        with connect() as db:
            rows = playground_directory_rows(db)
    except Exception:
        LOGGER.exception("Could not fetch public playground list")
        return _render(request, "error.html", {"message": "Daten vorübergehend nicht verfügbar.", "private": True}, status=503)
    found = [dict(x) for x in rows if query.casefold() in str(x.get("name") or "").casefold()][:200]
    context = {"query": query, "rows": found, "count": len(found), "private": True}
    partial = request.headers.get("HX-Request") == "true"
    return _render(request, "playgrounds_rows.html" if partial else "playgrounds.html", context, partial=partial)


@require_GET
def workspace(request):
    """Keep old bookmarks working after removing the duplicate welcome page."""
    response = HttpResponseRedirect(_prefix(request) + "/")
    response["Cache-Control"] = "no-store"
    return response


@require_GET
@ui_login_required
def assigned_playgrounds(request):
    """Bounded SQL pages; inspection assignment stays enforced server-side."""
    user, denied = _private(request)
    if denied is not None:
        return denied
    from playground_check.remaining_reads_repository import gui_playground_page, inspection_type_rows
    query = (request.GET.get("q") or "").strip()[:120]
    kind = (request.GET.get("inspectiontype") or "").strip()[:100]
    inspection_mode = request.GET.get("mode") == "inspection" or bool(kind)
    try:
        page = max(1, min(10000, int(request.GET.get("page", "1"))))
    except (TypeError, ValueError):
        page = 1
    size = 20
    rows, types = [], []
    try:
        with connect() as db:
            if inspection_mode and request.headers.get("HX-Request") != "true":
                types = [f"{r['value']} ({r['short_value']})" for r in inspection_type_rows(db)]
            # A malicious inspectiontype must never enable unrestricted playground access.
            if not inspection_mode or kind:
                raw = gui_playground_page(db, user, kind if inspection_mode else "", query,
                                          (page - 1) * size, size + 1)
                rows = [{"name": r["name"], "hasOpenDeviceDefects": bool(r["has_open"]),
                         "thumbnail_device_fid": r.get("thumbnail_device_fid"),
                         "inspectionSuspended": False} for r in raw[:size]]
                has_next = len(raw) > size
            else:
                has_next = False
    except Exception:
        LOGGER.exception("Could not load playground page")
        return _render(request, "error.html", {"message": "Spielplätze können derzeit nicht geladen werden.", "private": True}, status=503)
    data = {"rows": rows, "query": query, "inspection_type": kind, "inspection_mode": inspection_mode,
            "inspection_types": types, "page": page, "next": page + 1, "has_next": has_next,
            "user": user, "private": True}
    partial = request.headers.get("HX-Request") == "true"
    if partial and request.GET.get("append") == "1":
        template = "assigned_rows.html"
    else:
        template = "assigned_results.html" if partial else "assigned.html"
    return _render(request, template, data, partial=partial)


@require_http_methods(["GET", "POST"])
@ui_login_required
def playground_detail(request):
    """Authorized read of play devices and inspection history, no browser-side data duplication."""
    user, denied = _private(request)
    if denied: return denied
    source = request.GET if request.method == "GET" else request.POST
    name = (source.get("name") or "").strip()[:200]
    if not name:
        return _render(request, "error.html", {"message": "Kein Spielplatz ausgewählt.", "private": True}, status=400)
    kind = (source.get("inspectiontype") or "").strip()[:100]
    if kind and request.method == "GET":
        from urllib.parse import urlencode
        # Inspection links must enter the criterion editor, not the device/document view.
        # The destination revalidates assignment, type and device eligibility.
        return HttpResponseRedirect(_prefix(request) + "/inspection/?" + urlencode({"name": name, "inspectiontype": kind}))
    try:
        payload = playground_by_name_data({"name": name, "inspectiontype": kind, "withdefects": "true", "withinspections": "true"})
    except LookupError:
        return _render(request, "error.html", {"message": "Spielplatz nicht gefunden.", "private": True}, status=404)
    except Exception:
        LOGGER.exception("Could not load playground detail")
        return _render(request, "error.html", {"message": "Spielplatzdetails sind derzeit nicht verfügbar.", "private": True}, status=503)
    # A general playground listing is never an inspection authorization.
    # An explicit type must match an assignment for the authenticated user.
    can_inspect = False
    if kind and user.get("role") in {"inspector", "administrator"} and not payload.get("inspectionSuspended"):
        try:
            eligible = playground_only_names_data(user, {"inspectiontype": kind})
            can_inspect = any(
                row.get("name") == name and not row.get("inspectionSuspended")
                for row in eligible
            ) and kind in (payload.get("inspectionTypeOptions") or [])
        except Exception:
            LOGGER.exception("Could not establish inspection eligibility for detail")
    # Display labels belong to the GUI; keep the existing API attributes intact.
    renovation_labels = {
        str(option["id"]): option["value"]
        for option in payload.get("renovationTypeOptions") or []
    }
    current_year = local_today().year
    for device in payload.get("playdevices") or []:
        properties = device.get("properties") or {}
        try:
            renovation_year = int(properties.get("recommendedYearOfRenovation") or 0)
        except (TypeError, ValueError):
            renovation_year = 0
        properties["renovation_status"] = (
            "unplanned" if renovation_year <= 0 else
            "urgent" if renovation_year <= current_year + 1 else "future"
        )
        properties["renovation_type_label"] = renovation_labels.get(
            str(properties.get("renovationType")), "Nicht angegeben")
        construction = properties.get("constructionDate")
        year = getattr(construction, "year", None)
        if year is None and construction:
            try:
                year = int(str(construction)[:4])
            except (TypeError, ValueError):
                year = None
        properties["construction_year"] = year if year and year > 1 else None
    flash_notice = (request.GET.get("notice") or "").strip()[:180]
    flash_error = (request.GET.get("error") or "").strip()[:180]
    return _render(request, "detail.html", {"playground": payload, "kind": kind,
                                            "can_inspect": can_inspect, "private": True, "user": user,
                                            "flash_notice": flash_notice, "flash_error": flash_error,
                                            "documents_tab": request.GET.get("tab") == "documents" or bool(flash_notice or flash_error),
                                            "is_admin": user.get("role") == "administrator"})


@require_GET
@ui_login_required
def defects(request):
    """SQL-paginated defect overview with the existing state filter."""
    user, denied = _private(request)
    if denied is not None:
        return denied
    from playground_check.remaining_reads_repository import gui_defect_page
    query = (request.GET.get("q") or "").strip()[:120]
    state = (request.GET.get("state") or "open").strip().lower()
    if state not in {"open", "all", "done"}:
        state = "open"
    try:
        page = max(1, min(10000, int(request.GET.get("page", "1"))))
    except (TypeError, ValueError):
        page = 1
    priority_raw = (request.GET.get("priority") or "").strip()
    priority = int(priority_raw) if priority_raw in {"1", "2", "3"} else None
    size = 20
    try:
        with connect() as db:
            if priority is None:
                raw = gui_defect_page(db, query, state, (page - 1) * size, size + 1)
            else:
                raw = gui_defect_page(db, query, state, (page - 1) * size, size + 1, priority=priority)
    except Exception:
        LOGGER.exception("Could not load defect overview")
        return _render(request, "error.html", {"message": "Mängel sind derzeit nicht verfügbar.", "private": True}, status=503)
    # Compute age per record without a second database query. The SQL ordering
    # remains authoritative, including across HTMX pages.
    from datetime import date, datetime
    rows = [dict(item) for item in raw[:size]]
    today = local_today()
    for item in rows:
        created = item.get("date_creation")
        if isinstance(created, datetime):
            created = created.date()
        item["open_days"] = max(0, (today - created).days) if isinstance(created, date) and not item.get("done_by") else None
    data = {"rows": rows, "query": query, "state": state, "priority": priority_raw if priority is not None else "",
            "page": page, "next": page + 1, "has_next": len(raw) > size,
            "user": user, "private": True}
    partial = request.headers.get("HX-Request") == "true"
    template = ("defects_append.html" if request.GET.get("append") == "1" else "defects_results.html") if partial else "defects.html"
    return _render(request, template, data, partial=partial)


@require_http_methods(["GET", "POST"])
@ui_login_required
def inspection_editor(request):
    """HTTP boundary: retain authentication and compose inspection services."""
    from .inspection_device_commands import create_inspection
    from .inspection_ui import edit_inspection, InspectionServices
    user, denied = _private(request)
    if denied is not None:
        return denied
    services = InspectionServices(
        assignments=playground_only_names_data,
        playground=playground_by_name_data,
        save_checkability=_save_device_change,
        submit_reports=partial(invoke, request, create_inspection, url='/Inspection/'),
    )
    return edit_inspection(request, user, services, partial(_render, request))


def _save_device_change(properties):
    with connect() as db:
        save_device(db, properties)


@require_http_methods(["GET", "POST"])
@ui_login_required
def defect_detail(request):
    """HTTP boundary: retain authentication and delegate defect use cases."""
    from .defect_ui import DefectEditor
    user, denied = _private(request)
    if denied is not None:
        return denied
    return DefectEditor(request, user, partial(_render, request), _prefix(request), connect).dispatch()


@require_http_methods(["GET", "POST"])
@ui_login_required
def my_profile(request):
    """Minimal private account page: authenticated identity, no password exposure."""
    user, denial = _private(request)
    if denial is not None:
        return denial
    error = ""
    if request.method == "POST":
        language = request.POST.get("language", "")
        if language and language not in CODES:
            error = "Ungültige Sprachauswahl."
        elif "language" not in request.POST:
            error = "Ungültige Sprachauswahl."
        else:
            try:
                with connect() as db:
                    affected = update_ui_language(db, user["fid"], language or None)
                    if affected != 1:
                        raise ValueError("Language preference account not found")
                response = HttpResponseRedirect(_prefix(request) + "/profile/?language_saved=1")
                if language:
                    response.set_signed_cookie(COOKIE, language, salt=COOKIE, max_age=31536000,
                                               path=_prefix(request) + "/", secure=request.is_secure(),
                                               httponly=True, samesite="Lax")
                else:
                    response.delete_cookie(COOKIE, path=_prefix(request) + "/", samesite="Lax")
                return response
            except Exception:
                LOGGER.exception("Could not save language preference")
                error = "Sprachauswahl konnte nicht gespeichert werden. Bitte erneut versuchen."
    values = {"private": True, "user": user,
              "display_name": user.get("name") or user.get("mailAddress") or "Benutzer",
              "role": user.get("role") or "", "email": user.get("mailAddress") or "",
              "preferred_language": (request.POST.get("language") if request.method == "POST" and request.POST.get("language") in CODES else user.get("uiLanguage")) or "", "language_choices": LANGUAGES,
              "language_saved": request.GET.get("language_saved") == "1", "language_error": error}
    return _render(request, "profile.html", values, status=400 if error else 200)


@require_GET
@ui_login_required
def push_settings(request):
    """Private push controls; registration and deletion use existing authenticated API."""
    user, denied = _private(request)
    if denied is not None:
        return denied
    # The public VAPID key is intentionally public. Credentials and subscription
    # endpoints are never embedded into the HTML.
    public_key = settings.vapid_public_key if settings.service_worker_enabled else ""
    return _render(request, "push_settings.html", {
        "private": True, "user": user, "vapid_public_key": public_key,
        "push_enabled": bool(settings.service_worker_enabled and public_key),
    })
