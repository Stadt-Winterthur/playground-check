"""Explicit API input checks, shared by native commands and their GUI adapter.

Only invalid input is translated to HTTP 400. Unexpected programming/database
errors reach the central server-error boundary; no blanket input-error catcher.
"""
import math
import re
from datetime import datetime

from rest_framework.exceptions import ParseError
from playground_check.http import JsonBodyError


def invalid_input():
    # Do not echo input, credentials, internal exception text or SQL to clients.
    raise ParseError({'errorMessage': 'Ungültige JSON-Daten oder Parameter.'})


def _json(request):
    try:
        return request.json()
    except JsonBodyError:
        invalid_input()


def integer(value):
    if isinstance(value, bool):
        invalid_input()
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r'[+-]?[0-9]+', value.strip()):
        try:
            return int(value)
        except ValueError:
            invalid_input()
    invalid_input()


def mapping(value, *, strings=(), integers=(), booleans=(), dates=()):
    if not isinstance(value, dict):
        invalid_input()
    for name in strings:
        if value.get(name) is not None and not isinstance(value[name], str):
            invalid_input()
    for name in integers:
        item = value.get(name)
        if item not in (None, ''):
            integer(item)
    for name in booleans:
        item = value.get(name)
        if item is None or isinstance(item, bool):
            continue
        if isinstance(item, int) and item in (0, 1):
            continue
        if isinstance(item, str) and item.lower() in {'1', '0', 'true', 'false', 'yes', 'no', 'on', 'off'}:
            continue
        invalid_input()
    for name in dates:
        item = value.get(name)
        if item in (None, ''):
            continue
        if not isinstance(item, str):
            invalid_input()
        try:
            datetime.fromisoformat(item.strip().replace('Z', '+00:00'))
        except ValueError:
            invalid_input()
    return value


def object_body(request, **fields):
    value = _json(request)
    return mapping({} if value is None else value, **fields)


def list_body(request, **fields):
    value = _json(request)
    # Keep the established missing/empty report response in the command.
    if value is None:
        return []
    if not isinstance(value, list):
        invalid_input()
    for item in value:
        mapping(item, **fields)
    return value


def positive_query_id(request, name):
    value = integer(request.query.get(name))
    if not 0 < value < 2**31:
        invalid_input()
    return value


def finite_query_number(query, name):
    try:
        value = float(query.get(name) or 0)
    except (ValueError, TypeError, OverflowError):
        invalid_input()
    if not math.isfinite(value):
        invalid_input()
    return value
