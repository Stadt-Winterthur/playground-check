"""Persistence for web-push subscriptions. The caller owns the transaction."""

from __future__ import annotations

from typing import Any

from psycopg import Connection


def register_subscription(
    db: Connection, user_fid: int, endpoint: str, p256dh: str, auth: str,
    user_agent: str | None,
) -> None:
    """Create or reactivate an endpoint, preserving existing ON CONFLICT semantics."""
    db.execute('''INSERT INTO "wgr_sp_push_subscription"
        (fid_kontrolleur, endpoint, p256dh, auth, user_agent, aktiv,
         datum_registrierung, datum_letzte_verwendung, datum_deaktivierung)
        VALUES (%s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP, NULL, NULL)
        ON CONFLICT (endpoint) DO UPDATE SET
         fid_kontrolleur=EXCLUDED.fid_kontrolleur, p256dh=EXCLUDED.p256dh,
         auth=EXCLUDED.auth, user_agent=EXCLUDED.user_agent, aktiv=true,
         datum_letzte_verwendung=CURRENT_TIMESTAMP, datum_deaktivierung=NULL''', (user_fid, endpoint, p256dh, auth, user_agent))


def unregister_subscription(db: Connection, user_fid: int, endpoint: str) -> None:
    """Deactivate an endpoint belonging to the authenticated user."""
    db.execute('''UPDATE "wgr_sp_push_subscription"
        SET aktiv=false, datum_deaktivierung=CURRENT_TIMESTAMP
        WHERE fid_kontrolleur=%s AND endpoint=%s''', (user_fid, endpoint))


def active_subscriptions(db: Connection, user_fid: int) -> list[dict[str, Any]]:
    """Return active subscriptions without altering the existing response schema."""
    return db.execute('''SELECT endpoint, p256dh, auth, COALESCE(user_agent,'') AS user_agent
        FROM "wgr_sp_push_subscription" WHERE fid_kontrolleur=%s AND aktiv=true''', (user_fid,)).fetchall()
