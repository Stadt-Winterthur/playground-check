"""Opt-in Python-first UI preview, without replacing production SPA."""
from html import escape
from django.http import HttpResponse
from django.views.decorators.http import require_GET
from playground_check.db import connect
from playground_check.config import settings


def _url(request, suffix):
    """Build an application-relative URL for proxied and direct requests."""
    prefix = (request.META.get("SCRIPT_NAME") or settings.base_path or "").rstrip("/")
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    return prefix + suffix


def page(title, body, status=200, request=None):
    css_url = escape(_url(request, "/static/css/python-ui.css"), quote=True)
    home_url = escape(_url(request, "/__ui/"), quote=True)
    document = ('<!doctype html><html lang="de"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<link rel="stylesheet" href="{css_url}">'
                f'<title>{escape(title)}</title></head><body>'
                f'<header><a href="{home_url}">Spielplatzkontrolle Winterthur</a></header>'
                f'<main>{body}</main></body></html>')
    response = HttpResponse(document, status=status, content_type='text/html; charset=utf-8')
    response['Content-Security-Policy'] = ("default-src 'none'; style-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    return response


@require_GET
def home(request):
    playgrounds_url = escape(_url(request, "/__ui/playgrounds/"), quote=True)
    return page('Spielplatzkontrolle', '<h1>Neue Python-Oberfläche (Vorschau)</h1>'
                f'<p><a href="{playgrounds_url}">Öffentliche Spielplätze</a></p>'
                '<p>Die vollständigen Fachfunktionen bleiben in der bestehenden GUI.</p>', request=request)


@require_GET
def playgrounds(request):
    query = (request.GET.get('q') or '').strip()[:120]
    try:
        with connect() as db:
            rows = db.execute('SELECT name, strassenname AS street_name, hausnummer AS house_no '
                              'FROM "wgr_sp_spielplatz" ORDER BY name').fetchall()
    except Exception:
        return page('Spielplätze', '<p role="alert">Daten vorübergehend nicht verfügbar.</p>', 503, request=request)
    matches = [r for r in rows if query.casefold() in str(r.get('name') or '').casefold()]
    items = ''.join('<li><strong>' + escape(str(r.get('name') or '')) + '</strong> '
                    + escape(str(r.get('street_name') or '')) + ' '
                    + escape(str(r.get('house_no') or '')) + '</li>' for r in matches[:200])
    form = (f'<form method="get" action="{escape(_url(request, "/__ui/playgrounds/"), quote=True)}"><label for="q">Spielplatz suchen</label>'
            '<input id="q" name="q" maxlength="120" value="' + escape(query, quote=True)
            + '"><button>Suchen</button></form>')
    return page('Spielplätze', '<h1>Öffentliche Spielplätze</h1>' + form
                + '<ul>' + (items or '<li>Keine Treffer</li>') + '</ul>', request=request)
