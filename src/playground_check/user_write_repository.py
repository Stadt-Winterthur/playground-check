"""Existing PostgreSQL account writes. The caller owns the transaction and policy."""
from __future__ import annotations

from typing import Any


def record_login_attempt(db: Any, email: str) -> None:
    db.execute(
        'UPDATE "wgr_sp_kontrolleur" SET letzter_anmeldeversuch=CURRENT_TIMESTAMP '
        'WHERE trim(lower(e_mail))=%s', (email,),
    )


def update_password(db: Any, email: str, password_hash: str) -> int:
    return db.execute(
        'UPDATE "wgr_sp_kontrolleur" SET pwd=%s WHERE trim(lower(e_mail))=%s',
        (password_hash, email),
    ).rowcount


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
    return db.execute(
        '''UPDATE "wgr_sp_kontrolleur"
           SET nachname=%s, vorname=%s, rolle=%s, zustaendigkeit=%s, aktiv=%s, is_new=%s
           WHERE trim(lower(e_mail))=%s''',
        (last_name, first_name, role, responsibility, active, is_new, email),
    ).rowcount


def deactivate_user(db: Any, email: str) -> int:
    return db.execute(
        'UPDATE "wgr_sp_kontrolleur" SET aktiv=false WHERE trim(lower(e_mail))=%s',
        (email,),
    ).rowcount
