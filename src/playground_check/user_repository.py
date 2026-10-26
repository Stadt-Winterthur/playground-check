"""PostgreSQL reads for user/account endpoints; no transaction ownership."""
from __future__ import annotations

from typing import Any

USER_SELECT = '''SELECT fid, nachname AS last_name, vorname AS first_name,
    trim(lower(e_mail)) AS email, pwd, letzter_anmeldeversuch AS last_login_attempt,
    CURRENT_TIMESTAMP(0)::TIMESTAMP AS database_time, rolle AS role,
    zustaendigkeit AS responsibility, aktiv AS active, is_new
    FROM "wgr_sp_kontrolleur"'''


def user_by_email(db: Any, email: str):
    return db.execute(USER_SELECT + " WHERE trim(lower(e_mail))=%s", (email,)).fetchone()


def users_by_email(db: Any, email: str):
    return db.execute(USER_SELECT + " WHERE trim(lower(e_mail))=%s", (email,)).fetchall()


def users(db: Any, email: str = ""):
    sql, params = USER_SELECT, ()
    if email:
        sql += " WHERE trim(lower(e_mail))=%s"
        params = (email,)
    return db.execute(sql + " ORDER BY vorname, nachname", params).fetchall()


def assignable_users(db: Any):
    return db.execute(USER_SELECT + " WHERE aktiv=true ORDER BY vorname, nachname").fetchall()
