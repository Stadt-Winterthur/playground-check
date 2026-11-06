from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_environment(path: Path | None = None) -> None:
    """Load project-local settings without overriding the process environment."""
    dotenv_path = path or Path.cwd() / ".env"
    if path is None and not dotenv_path.is_file():
        dotenv_path = PROJECT_ROOT / ".env"
    load_dotenv(dotenv_path, override=False)


load_environment()


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}



def _security_key() -> str:
    key = (os.getenv("PLAYGROUND_SECURITY_KEY") or os.getenv("SecurityKey") or "").strip()
    if not key:
        raise RuntimeError(
            "PLAYGROUND_SECURITY_KEY must be set to a secret JWT signing key."
        )
    if len(key) < 32:
        raise RuntimeError(
            "PLAYGROUND_SECURITY_KEY must contain at least 32 characters."
        )
    return key


def _base_path(value: str | None) -> str:
    """Normalize an ASP.NET-style PathBase for the combined WSGI app."""
    value = (value or "").strip()
    if not value or value == "/":
        return ""
    return "/" + value.strip("/")


def _npgsql_to_libpq(value: str) -> str:
    """Accept the original Npgsql key/value connection-string format as well."""
    if not value or ";" not in value:
        return value
    names = {
        "host": "host", "server": "host", "port": "port",
        "database": "dbname", "username": "user", "user id": "user",
        "password": "password", "ssl mode": "sslmode", "search path": "options",
    }
    result: list[str] = []
    for part in value.split(";"):
        if "=" not in part:
            continue
        key, raw = part.split("=", 1)
        target = names.get(key.strip().lower())
        if not target:
            continue
        raw = raw.strip().replace("\\", "\\\\").replace("'", "\\'")
        if target == "options":
            raw = f"-c search_path={raw}"
        result.append(f"{target}='{raw}'")
    return " ".join(result)


@dataclass(frozen=True)
class Settings:
    root: Path
    host: str
    port: int
    postgres_dsn: str
    security_key: str
    salt: bytes
    title: str
    short_title: str
    playground_token_key: str
    playground_user_token_key: str
    hide_info_cookie_name: str
    auth_cookie_name: str
    cors_origin: str
    wms_url: str
    base_path: str
    token_issuer: str
    compatibility_bugs: bool
    service_worker_enabled: bool
    push_notifications: bool
    vapid_public_key: str
    service_description: str
    elk_url: str
    elk_verify_ssl: bool
    elk_environment: str
    elk_directory: str
    elk_service: str

    @classmethod
    def load(cls) -> "Settings":
        salt_raw = os.getenv("PLAYGROUND_SALT_BASE64", "cGxheWdyb3VuZC1jaGVjay1zYWx0")
        salt_raw = os.getenv("SaltBase64String", salt_raw)
        try:
            salt = base64.b64decode(salt_raw, validate=True)
        except Exception as exc:
            raise RuntimeError(
                "PLAYGROUND_SALT_BASE64 must contain valid Base64 data."
            ) from exc
        return cls(
            root=PROJECT_ROOT,
            host=os.getenv("PLAYGROUND_HOST", "127.0.0.1"),
            port=int(os.getenv("PLAYGROUND_PORT", "8010")),
            postgres_dsn=_npgsql_to_libpq(os.getenv("PLAYGROUND_POSTGRES_DSN", os.getenv("Postgres__ConnectionString", ""))),
            security_key=_security_key(),
            salt=salt,
            title=os.getenv("PLAYGROUND_TITLE", "Spielplatzkontrolle"),
            short_title=os.getenv("PLAYGROUND_SHORT_TITLE", "SPK"),
            playground_token_key=os.getenv("PLAYGROUND_TOKEN_KEY", "playground.token"),
            playground_user_token_key=os.getenv("PLAYGROUND_USER_TOKEN_KEY", "playground.user.token"),
            hide_info_cookie_name=os.getenv("PLAYGROUND_HIDE_INFO_COOKIE_NAME", "hide_info"),
            auth_cookie_name=os.getenv("PLAYGROUND_AUTH_COOKIE_NAME", "playground.auth"),
            cors_origin=os.getenv("PLAYGROUND_CORS_ORIGIN", "").strip(),
            wms_url=os.getenv("PLAYGROUND_WMS_URL", os.getenv("WMS__ServiceUrl", "http://stadtplan.winterthur.ch/wms/Spielplatzkarte")),
            base_path=_base_path(os.getenv("PLAYGROUND_BASE_PATH", os.getenv("URL__ServiceBasePath", ""))),
            token_issuer=os.getenv(
                "PLAYGROUND_SERVICE_URL",
                os.getenv("URL__ServiceDomain", "") + os.getenv("URL__ServiceBasePath", "/"),
            ),
            compatibility_bugs=_bool(os.getenv("PLAYGROUND_COMPATIBILITY_BUGS"), False),
            service_worker_enabled=_bool(os.getenv("PLAYGROUND_SERVICE_WORKER_ENABLED"), True),
            push_notifications=_bool(os.getenv("PLAYGROUND_FEATURE_PUSH_NOTIFICATIONS"), False),
            vapid_public_key=os.getenv(
                "PLAYGROUND_VAPID_PUBLIC_KEY",
                "BGwoqHwV5SrixvSr9YQ58M9U5MzFZ7m5rCrWrGBmMpPVkaWbCwJtL7KWAZFTeZps_2zcdguI1_R-ZtgpLIzPu6Y",
            ),
            service_description=os.getenv("PLAYGROUND_SERVICE_DESCRIPTION", os.getenv("ServiceDescription", "")),
            elk_url=os.getenv("PLAYGROUND_ELK_URL", os.getenv("ELK__Url", "")).strip(),
            elk_verify_ssl=_bool(os.getenv("PLAYGROUND_ELK_VERIFY_SSL", os.getenv("ELK__VerifySsl")), True),
            elk_environment=(
                os.getenv("PLAYGROUND_ELK_ENVIRONMENT", "").strip()
                or os.getenv("ELK__Environment", "").strip()
                or os.getenv("ASPNETCORE_ENVIRONMENT", "Production").lower()
            ),
            elk_directory=(
                os.getenv("PLAYGROUND_ELK_DIRECTORY", "").strip()
                or os.getenv("ELK__Directory", "").strip()
                or str(PROJECT_ROOT)
            ),
            elk_service=(
                os.getenv("PLAYGROUND_ELK_SERVICE", "").strip()
                or os.getenv("ELK__Service", "").strip()
                or "playground-check-service"
            ),
        )


settings = Settings.load()
