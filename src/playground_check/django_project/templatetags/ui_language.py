from django import template
from django.utils import translation
from django.utils.html import json_script
from playground_check.django_project.localization import tr, catalogs

register = template.Library()
register.simple_tag(tr, name='tr')
register.filter('ui', tr)

@register.filter
def ui_default(value, fallback):
    """Translate a missing-value label without translating stored user data."""
    return value if value else tr(fallback)

@register.simple_tag
def ui_messages():
    code = (translation.get_language() or 'de').split('-')[0]
    # Only browser-generated messages, not the full UI catalog, are sent to JS.
    return json_script({key: tr(key, code) for key in catalogs().get('js_keys', [])}, 'ui-translations')
