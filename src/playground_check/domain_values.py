"""Shared domain constants and value conversions; no HTTP dispatch or DB access."""
from datetime import date, datetime
from email.errors import HeaderParseError
from email.headerregistry import Address
from typing import Any

UNAUTHORIZED = "Sie sind entweder nicht als Kontrolleur in der Spielplatzkontrolle-Datenbank erfasst oder Sie haben keine Zugriffsberechtigung."
DOTNET_MIN_DATE = "0001-01-01T00:00:00"
VALID_ROLES = {"administrator", "inspector", "maintenance"}
VALID_RESPONSIBILITIES = {
    "Revier Mitte", "Revier Süd", "Revier West", "Revier Ost", "Dispo",
    "Revier", "Spielplatzverantwortlicher", "Projektleiter",
}


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _date_value(value: Any) -> date | datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return date.fromisoformat(text[:10])


def _valid_mail_address(value: str) -> bool:
    try:
        parsed = Address(addr_spec=value)
    except (TypeError, ValueError, HeaderParseError, IndexError):
        return False
    return parsed.addr_spec == value
