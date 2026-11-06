"""One diagnostic boundary for unexpected API and GUI-command failures.

Input validation and domain errors keep their explicit responses. Only database
connection failures become 503; programming and other unexpected errors are 500.
Callers may retain a historical JSON, text or binary error envelope.
"""
from functools import wraps
import logging

from django.db import InterfaceError as DjangoInterfaceError
from django.db import OperationalError as DjangoOperationalError
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from psycopg import InterfaceError, OperationalError
from rest_framework.exceptions import APIException

LOGGER = logging.getLogger(__name__)
CONNECTION_ERRORS = (InterfaceError, OperationalError,
                     DjangoInterfaceError, DjangoOperationalError)


def server_error(exc, response=None, *, operation='API'):
    status = 503 if isinstance(exc, CONNECTION_ERRORS) else 500
    # Log a fixed operation name and traceback, never request bodies, tokens,
    # headers or query strings. Client responses contain no exception details.
    LOGGER.error('Operation %s failed (HTTP %s)', operation, status,
                 exc_info=(type(exc), exc, exc.__traceback__))
    if response is None:
        response = JsonResponse({'errorMessage': 'SPK-3'})
    response.status_code = status
    response['Cache-Control'] = 'no-store'
    return response


def operation_errors(response_factory=None):
    """Also cover direct GUI command calls, outside DRF exception handling."""
    def decorate(handler):
        @wraps(handler)
        def guarded(*args, **kwargs):
            try:
                return handler(*args, **kwargs)
            except (APIException, Http404, PermissionDenied):
                # ParseError, upload limits and other expected HTTP errors
                # belong to the existing API/GUI transport adapter.
                raise
            except Exception as exc:
                response = response_factory() if response_factory else None
                return server_error(exc, response, operation=handler.__name__)
        return guarded
    return decorate
