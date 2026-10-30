from __future__ import annotations

import argparse
import html
import json
import logging
import mimetypes
import os
import secrets
import time
import traceback
import re
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

from . import __version__
from .config import settings
from .db import check_connection
from .http import JsonBodyError, Request, Response, Router, status_line
from .openapi import build_openapi_document, swagger_ui_html
from .logging_ext import configure_logging
from . import service


LOG = logging.getLogger("playground_check")
configure_logging(settings)


def create_router() -> Router:
    router = Router()
    router.add("POST", r"/Account/Login/?", service.login)
    router.add("GET", r"/Account/Me/?", service.get_current_account)
    router.add("POST", r"/Account/Logout/?", service.logout)
    router.add("GET", r"/Account/Users/?", service.get_users)
    router.add("GET", r"/Account/Users/Assignable/?", service.get_assignable_users)
    router.add("PUT", r"/Account/Users/?", service.update_user)
    router.add("DELETE", r"/Account/Users/?", service.delete_user)
    router.add("GET", r"/Inspection/types/?", service.inspection_types)
    router.add("GET", r"/Inspection/renovationtypes/?", service.renovation_types)
    router.add("POST", r"/Inspection/?", service.post_inspections)
    router.add("GET", r"/Collections/Playgrounds/Items/?", service.public_playgrounds)
    router.add("GET", r"/Collections/Playgrounds/Items/(?P<uuid>[^/]+)/?", service.public_playground)
    router.add("GET", r"/Playground/onlynames/?", service.only_names)
    router.add("GET", r"/Playground/byname/?", service.get_playground_by_name)
    router.add("GET", r"/Playground/byplaydevice/(?P<fid>\d+)/?", service.get_playground_by_device)
    router.add("GET", r"/Playground/mapimage/?", service.get_map_image)
    router.add("GET", r"/Playground/(?P<id>\d+)/?", service.get_playground_by_id)
    # ASP.NET's unconstrained {id} route also matches malformed values such as
    # "123&inspectiontype=...". [ApiController] then rejects the failed int
    # model binding with HTTP 400. Keep that legacy client bug observable.
    router.add("GET", r"/Playground/(?P<invalid_id>[^/]+)/?", service.invalid_playground_id)
    router.add("POST", r"/Playdevice/?", service.save_playdevice)
    router.add("PUT", r"/Playdevice/?", service.exchange_playdevice_picture)
    router.add("GET", r"/Playdevice/(?P<fid>\d+)/Picture/?", service.get_playdevice_picture)
    router.add("PUT", r"/Playdevice/(?P<fid>\d+)/Picture/?", service.put_playdevice_picture)
    router.add("GET", r"/Defect/Overview/?", service.get_defect_overview)
    router.add("GET", r"/Defect/?", service.get_defect)
    router.add("POST", r"/Defect/?", service.update_defect)
    router.add("PUT", r"/Defect/?", service.create_defect)
    router.add("POST", r"/Defect/(?P<tid>\d+)/send-mail/?", service.send_info_mail)
    router.add("POST", r"/Defect/(?P<tid>\d+)/accept/?", lambda r: service.assignment_status(r, True))
    router.add("POST", r"/Defect/(?P<tid>\d+)/reject/?", lambda r: service.assignment_status(r, False))
    router.add("GET", r"/Defect/Picture/(?P<tid>\d+)/?", service.get_defect_picture)
    router.add("PUT", r"/Defect/Picture/(?P<tid>\d+)/?", service.put_defect_picture)
    router.add("GET", r"/Document/(?P<fid>\d+)/?", service.get_document)
    router.add("POST", r"/Document/?", service.post_document)
    router.add("PUT", r"/Document/(?P<fid>\d+)/Name/?", service.rename_document)
    router.add("DELETE", r"/Document/(?P<fid>\d+)/?", service.delete_document)
    router.add("POST", r"/PushSubscription/Register/?", service.push_register)
    router.add("DELETE", r"/PushSubscription/Unregister/?", service.push_unregister)
    router.add("GET", r"/PushSubscription/Me/?", service.push_me)
    return router


class Application:
    def __init__(self) -> None:
        self.router = create_router()
        self.static_root = Path(__file__).with_name("static")

    def __call__(self, environ, start_response):
        started = time.perf_counter()
        external_request = Request(environ)
        request = self._path_base_request(external_request)
        if request is None:
            response = Response.text("Not found", 404)
        else:
            try:
                response = self.router.dispatch(request)
                if response is None:
                    allowed_methods = self.router.allowed_methods(request.path)
                    if allowed_methods:
                        response = Response.text("Method not allowed", 405)
                        response.headers.append(("Allow", ", ".join(allowed_methods)))
                    else:
                        response = self._frontend(request)
            except JsonBodyError as exc:
                response = Response.json({
                    "type": "https://tools.ietf.org/html/rfc7231#section-6.5.1",
                    "title": "One or more validation errors occurred.",
                    "status": 400,
                    "errors": {"$": [str(exc)]},
                }, 400)
            except ValueError as exc:
                response = Response.text(str(exc), 400)
            except Exception as exc:
                LOG.exception("Request failed: %s %s", request.method, request.path)
                response = self._exception_response(exc)
        headers = [
            ("Content-Type", response.content_type),
            ("Content-Length", str(len(response.body))),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "same-origin"),
            ("Permissions-Policy", "camera=(self), microphone=(), geolocation=()"),
        ]
        if settings.cors_origin:
            headers.append(("Access-Control-Allow-Origin", settings.cors_origin))
            headers.append(("Vary", "Origin"))
        headers.extend(response.headers)
        start_response(status_line(response.status), headers)
        elapsed_ms = (time.perf_counter() - started) * 1000
        LOG.info(
            "HTTP %s %s responded %s in %.4f ms",
            external_request.method, external_request.path, response.status, elapsed_ms,
            extra={"elk_details": [
                f"RequestMethod={external_request.method}",
                f"RequestPath={external_request.path}",
                f"StatusCode={response.status}",
                f"Elapsed={elapsed_ms:.4f}",
            ]},
        )
        return [response.body]

    @staticmethod
    def _exception_response(exc: Exception) -> Response:
        # The legacy ASP.NET service enables DeveloperExceptionPage only in DEV.
        # Outside Development, Kestrel/framework handling returns a bare 500 and
        # does not expose the exception message to the client.
        environment = os.getenv("ASPNETCORE_ENVIRONMENT", "Production")
        if environment.casefold() != "development":
            return Response(b"", 500, "text/plain; charset=utf-8")

        details = traceback.format_exc()
        body = (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<title>Unhandled exception</title></head><body>"
            "<h1>An unhandled exception occurred while processing the request.</h1>"
            f"<h2>{html.escape(type(exc).__name__)}: {html.escape(str(exc))}</h2>"
            f"<pre>{html.escape(details)}</pre>"
            "</body></html>"
        )
        return Response.text(body, 500, "text/html; charset=utf-8")

    def _path_base_request(self, request: Request) -> Request | None:
        base_path = settings.base_path
        if not base_path:
            return request
        path = request.path
        if path != base_path and not path.startswith(base_path + "/"):
            return None
        environ = dict(request.environ)
        environ["SCRIPT_NAME"] = (environ.get("SCRIPT_NAME", "") or "") + base_path
        environ["PATH_INFO"] = path[len(base_path):] or "/"
        return Request(environ)

    def _frontend(self, request: Request) -> Response:
        if request.path in {"/swagger", "/swagger/"}:
            response = Response.text("", 302)
            response.headers.append(("Location", (settings.base_path or "") + "/swagger/index.html"))
            return response
        if request.path == "/swagger/index.html":
            return Response.text(swagger_ui_html(settings.base_path), 200, "text/html; charset=utf-8")
        if request.path == "/swagger/v1/swagger.json":
            return Response.json(build_openapi_document())
        if request.path == "/api/health":
            return Response.json({"status":"ok","version":__version__})
        if request.path.startswith("/static/"):
            relative = request.path[len("/static/"):]
            target = (self.static_root / relative).resolve()
            if self.static_root.resolve() not in target.parents or not target.is_file():
                return Response.text("Not found", 404)
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            response = Response.file(target.read_bytes(), content_type)
            if relative == "sw.js":
                response.headers.append(("Service-Worker-Allowed", (settings.base_path or "") + "/"))
            return response
        if request.method != "GET":
            return Response.text("Not found", 404)
        prefix = settings.base_path or ""
        defect = re.fullmatch(r"/defect/\d+/(\d+)/?", request.path, re.IGNORECASE)
        destination = None
        if defect:
            destination = f"/defect/?tid={defect.group(1)}"
        elif request.path.rstrip("/") == "/users":
            destination = "/admin/users/"
        elif request.path.rstrip("/") == "/defects":
            destination = "/defects/"
        elif request.path.rstrip("/") in ("/assigned", "/playdevices", "/playgrounds"):
            destination = "/assigned/"
        elif request.path.rstrip("/") == "/inspections":
            destination = "/assigned/?mode=inspection"
        if destination is None:
            return Response.text("Not found", 404)
        response = Response.text("", 302)
        response.headers.append(("Location", prefix + destination))
        response.headers.append(("Cache-Control", "no-store"))
        return response

    @staticmethod
    def _is_api_path(path: str) -> bool:
        first_segment = path.lstrip("/").split("/", 1)[0].lower()
        return first_segment in {
            "account",
            "inspection",
            "collections",
            "playground",
            "playdevice",
            "defect",
            "document",
            "pushsubscription",
            "swagger",
            "api",
        }


application = Application()


class QuietHandler(WSGIRequestHandler):
    def log_message(self, fmt, *args):
        # Request completion is logged centrally above, equivalent to UseSerilogRequestLogging().
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Spielplatzkontrolle Python WebApp")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--check-database", action="store_true", help="PostgreSQL-Verbindung prüfen und beenden")
    args = parser.parse_args()
    if args.check_database:
        check_connection()
        print("PostgreSQL-Verbindung erfolgreich geprüft.")
        return
    print(f"Spielplatzkontrolle {__version__} läuft auf http://{args.host}:{args.port}")
    with make_server(args.host, args.port, application, handler_class=QuietHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer beendet.")


if __name__ == "__main__":
    main()
