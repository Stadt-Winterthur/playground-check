"""Opt-in Python-first UI preview, without replacing production SPA."""
from html import escape
from django.http import HttpResponse
from django.views.decorators.http import require_GET
from playground_check.db import connect


def page(title, body, status=200):
    document = ('<!doctype html><html lang="de"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<link rel="stylesheet" href="/static/css/python-ui.css">'
                f'<title>{escape(title)}</title></head><body>'
                '<header><a href="/__ui/">Spielplatzkontrolle Winterthur</a></header>'
                f'<main>{body}</main></body></html>')
    response = HttpResponse(document, status=status, content_type='text/html; charset=utf-8')
    response['Content-Security-Policy'] = ("default-src 'none'; style-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    return response


@require_GET
def home(request):
    return page('Spielplatzkontrolle', '<h1>Neue Python-Oberfläche (Vorschau)</h1>'
                '<p><a href="/__ui/playgrounds/">Öffentliche Spielplätze</a></p>'
                '<p>Die vollständigen Fachfunktionen bleiben in der bestehenden GUI.</p>')


@require_GET
def playgrounds(request):
    query = (request.GET.get('q') or '').strip()[:120]
    try:
        with connect() as db:
            rows = db.execute('SELECT name, strassenname AS street_name, hausnummer AS house_no '
                              'FROM "wgr_sp_spielplatz" ORDER BY name').fetchall()
    except Exception:
        return page('Spielplätze', '<p role="alert">Daten vorübergehend nicht verfügbar.</p>', 503)
    matches = [r for r in rows if query.casefold() in str(r.get('name') or '').casefold()]
    items = ''.join('<li><strong>' + escape(str(r.get('name') or '')) + '</strong> '
                    + escape(str(r.get('street_name') or '')) + ' '
                    + escape(str(r.get('house_no') or '')) + '</li>' for r in matches[:200])
    form = ('<form method="get"><label for="q">Spielplatz suchen</label>'
            '<input id="q" name="q" maxlength="120" value="' + escape(query, quote=True)
            + '"><button>Suchen</button></form>')
    return page('Spielplätze', '<h1>Öffentliche Spielplätze</h1>' + form
                + '<ul>' + (items or '<li>Keine Treffer</li>') + '</ul>')
