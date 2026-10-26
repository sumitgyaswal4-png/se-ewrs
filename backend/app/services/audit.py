"""Audit-log helper.

The MySQL triggers in ``database/triggers.sql`` capture row-level changes
to the sensitive tables regardless of which client made them. This helper
records the *application-level* events a trigger cannot see -- sign-ins,
recalculation runs, report exports -- and gives the SQLite test-suite the
same audit coverage the triggers provide on MySQL.
"""

import json
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

from app.models import AuditLog

MAX_JSON = 60_000
#: Never written to the audit trail, whatever the caller passes.
_REDACT = {"password", "password_hash", "new_password", "current_password", "access_token"}


def _dump(payload: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not payload:
        return None
    safe = {k: ("***" if k in _REDACT else v) for k, v in payload.items()}
    text = json.dumps(safe, default=str, ensure_ascii=False)
    return text[:MAX_JSON]


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: Optional[Any] = None,
    user_id: Optional[int] = None,
    old_values: Optional[Mapping[str, Any]] = None,
    new_values: Optional[Mapping[str, Any]] = None,
    ip_address: Optional[str] = None,
    commit: bool = False,
) -> AuditLog:
    """Append one audit row. The caller normally commits with its own work."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id)[:60],
        old_values=_dump(old_values),
        new_values=_dump(new_values),
        ip_address=(ip_address or None),
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
