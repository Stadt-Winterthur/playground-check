"""PostgreSQL writes for acceptance and certificate documents.

Exception to the Oracle FID policy: document FIDs are deliberately assigned
in PostgreSQL. The caller owns the connection and transaction.
"""
from __future__ import annotations

from typing import Any

from psycopg import Connection


_DOCUMENT_COLUMNS = {
    "wgr_sp_abnahmen": "abnahmedokument",
    "wgr_sp_zertifikat": "zertifikatsdokument",
}


def _checked(table: str, column: str | None = None) -> tuple[str, str]:
    expected = _DOCUMENT_COLUMNS.get(table)
    if expected is None or (column is not None and column != expected):
        raise ValueError("Unsupported document table or column")
    return table, expected


def insert_document(db: Connection, table: str, column: str, playground_id: int, content: bytes) -> int:
    """Allocate a document FID under a table lock, then insert atomically."""
    table, column = _checked(table, column)
    db.execute(f'LOCK TABLE "{table}" IN EXCLUSIVE MODE')
    next_row = db.execute(f'SELECT COALESCE(MAX(fid), 0) + 1 AS fid FROM "{table}"').fetchone()
    fid = int(next_row["fid"])
    db.execute(
        f'INSERT INTO "{table}" (fid, fid_spielplatz, {column}) VALUES (%s, %s, %s)',
        (fid, playground_id, content),
    )
    return fid


def document_content(db: Connection, table: str, column: str, fid: int) -> dict[str, Any] | None:
    table, column = _checked(table, column)
    return db.execute(f'SELECT {column} AS content FROM "{table}" WHERE fid=%s', (fid,)).fetchone()


def rename_document(db: Connection, table: str, column: str, fid: int, content: bytes) -> None:
    table, column = _checked(table, column)
    db.execute(f'UPDATE "{table}" SET {column}=%s WHERE fid=%s', (content, fid))


def delete_document(db: Connection, table: str, fid: int) -> dict[str, Any] | None:
    table, _ = _checked(table)
    return db.execute(f'DELETE FROM "{table}" WHERE fid=%s RETURNING fid', (fid,)).fetchone()
