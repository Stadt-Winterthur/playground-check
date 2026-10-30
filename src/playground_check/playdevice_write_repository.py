"""PostgreSQL writes for existing playground devices.

FID values are supplied by the Oracle master and are never generated here.
The caller owns the database connection and transaction.
"""
from __future__ import annotations

from typing import Any


def update_playdevice(
    db: Any,
    recommended_year: Any,
    renovation_type: Any,
    comment: Any,
    cannot_be_checked: bool,
    cannot_be_checked_reason: str,
    fid: int,
) -> None:
    db.execute('''UPDATE "gr_v_spielgeraete" SET
                empfohlenes_sanierungsjahr=%s, id_sanierungsart=%s,
                bemerkung_empf_sanierung=%s, nicht_pruefbar=%s,
                grund_nicht_pruefbar=%s WHERE fid=%s''',
               (recommended_year, renovation_type, comment,
                cannot_be_checked, cannot_be_checked_reason, fid))



def update_renovation_only(db: Any, recommended_year: Any, renovation_type: Any,
                           comment: Any, fid: int) -> None:
    """Renovation edits MUST NOT rewrite inspection-specific checkability state."""
    db.execute("""UPDATE "gr_v_spielgeraete" SET
                  empfohlenes_sanierungsjahr=%s, id_sanierungsart=%s,
                  bemerkung_empf_sanierung=%s WHERE fid=%s""",
               (recommended_year, renovation_type, comment, fid))


def update_checkability_only(db: Any, cannot_be_checked: bool,
                              reason: str, fid: int) -> None:
    """Inspection checkability edits MUST NOT rewrite renovation state."""
    db.execute("""UPDATE "gr_v_spielgeraete" SET
                  nicht_pruefbar=%s, grund_nicht_pruefbar=%s WHERE fid=%s""",
               (cannot_be_checked, reason, fid))
