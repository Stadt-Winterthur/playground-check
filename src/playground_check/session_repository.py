"""Persistent login sessions. All writes share the caller's transaction.

Only a random session identifier and account FID are stored, never the JWT,
password, IP address or user agent. Absence of a row denies authentication.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any



def create_session(db: Any, token: str, user_fid: int) -> None:
    from .auth import decode_token
    claims = decode_token(token)
    if claims is None:
        raise ValueError("Cannot register an invalid token")
    # An indexed expiry column bounds retained data without storing revocations.
    # Deployments may also run this DELETE periodically during quiet periods.
    db.execute('''DELETE FROM "wgr_sp_auth_session"
                  WHERE fid_kontrolleur=%s AND expires_at <= CURRENT_TIMESTAMP''', (user_fid,))
    db.execute('''INSERT INTO "wgr_sp_auth_session" (session_id, fid_kontrolleur, expires_at)
                  VALUES (%s, %s, %s)''',
               (claims["jti"], user_fid, datetime.fromtimestamp(claims["exp"], timezone.utc)))


def is_active(db: Any, session_id: str, user_fid: int) -> bool:
    return db.execute('''SELECT 1 FROM "wgr_sp_auth_session"
                        WHERE session_id=%s AND fid_kontrolleur=%s
                          AND expires_at > CURRENT_TIMESTAMP''',
                      (session_id, user_fid)).fetchone() is not None


def revoke_session(db: Any, session_id: str) -> None:
    db.execute('DELETE FROM "wgr_sp_auth_session" WHERE session_id=%s', (session_id,))


def revoke_user_sessions(db: Any, email: str) -> None:
    db.execute('''DELETE FROM "wgr_sp_auth_session" WHERE fid_kontrolleur IN (
                    SELECT fid FROM "wgr_sp_kontrolleur" WHERE trim(lower(e_mail))=%s
                  )''', (email,))
