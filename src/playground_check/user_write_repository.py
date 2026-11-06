"""Existing PostgreSQL account writes. The caller owns the transaction and policy."""
from __future__ import annotations

from typing import Any
from .session_repository import revoke_user_sessions


def update_ui_language(db: Any, fid: int, language: str | None) -> int:
    """Preference-only update; authentication/session state remains unchanged."""
    return db.execute('UPDATE "wgr_sp_kontrolleur" SET ui_language=%s WHERE fid=%s',
                      (language, fid)).rowcount


def record_login_attempt(db: Any, email: str) -> None:
    db.execute(
        'UPDATE "wgr_sp_kontrolleur" SET letzter_anmeldeversuch=CURRENT_TIMESTAMP '
        'WHERE trim(lower(e_mail))=%s', (email,),
    )


def update_password(db: Any, email: str, password_hash: str) -> int:
    affected = db.execute(
        'UPDATE "wgr_sp_kontrolleur" SET pwd=%s WHERE trim(lower(e_mail))=%s',
        (password_hash, email),
    ).rowcount
    if affected:
        revoke_user_sessions(db, email)
    return affected


def register_pending_user(db: Any, last_name: str, first_name: str, email: str, password_hash: str) -> None:
    db.execute(
        '''INSERT INTO "wgr_sp_kontrolleur"
            (nachname, vorname, e_mail, pwd, rolle, aktiv, is_new)
            VALUES (%s, %s, %s, %s, 'inspector', false, true)''',
        (last_name, first_name, email, password_hash),
    )


def active_admin_count(db: Any) -> int:
    return db.execute(
        "SELECT count(*) AS count FROM \"wgr_sp_kontrolleur\" WHERE aktiv=true AND rolle='administrator'"
    ).fetchone()['count']


def update_user(db: Any, email: str, last_name: str, first_name: str, role: str,
                responsibility: str | None, active: bool, is_new: bool) -> int:
    affected = db.execute(
        '''UPDATE "wgr_sp_kontrolleur"
           SET nachname=%s, vorname=%s, rolle=%s, zustaendigkeit=%s, aktiv=%s, is_new=%s
           WHERE trim(lower(e_mail))=%s''',
        (last_name, first_name, role, responsibility, active, is_new, email),
    ).rowcount
    if affected:
        # Every administrative save revokes existing sessions, also preventing
        # old sessions from reviving after a deactivate/reactivate cycle.
        revoke_user_sessions(db, email)
    return affected


def deactivate_user(db: Any, email: str) -> int:
    affected = db.execute(
        'UPDATE "wgr_sp_kontrolleur" SET aktiv=false WHERE trim(lower(e_mail))=%s',
        (email,),
    ).rowcount
    if affected:
        revoke_user_sessions(db, email)
    return affected


def lock_account_changes(db: Any) -> None:
    """Serialize account policy checks through commit without locking logins."""
    db.execute('SELECT pg_advisory_xact_lock(1936747372)')
