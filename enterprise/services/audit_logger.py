from enterprise.extensions import db
from enterprise.models.security import ActivityLog, SecurityEvent


def log_activity(user, module_name, action_type, previous_data=None, updated_data=None, status="success", remarks=None, request_meta=None):
    meta = request_meta or {}
    entry = ActivityLog(
        user_id=getattr(user, "id", None),
        user_type=meta.get("user_type", "unknown"),
        module_name=module_name,
        action_type=action_type,
        previous_data=previous_data,
        updated_data=updated_data,
        status=status,
        remarks=remarks,
        ip_address=meta.get("ip_address"),
        browser=meta.get("browser"),
        device=meta.get("device"),
    )
    db.session.add(entry)
    return entry


def log_security_event(user, event_type, severity="info", details=None, request_meta=None):
    meta = request_meta or {}
    entry = SecurityEvent(
        user_id=getattr(user, "id", None),
        event_type=event_type,
        severity=severity,
        details=details,
        ip_address=meta.get("ip_address"),
        browser=meta.get("browser"),
        device=meta.get("device"),
    )
    db.session.add(entry)
    return entry

