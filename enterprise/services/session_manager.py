import secrets
from datetime import datetime, timedelta

from flask import session

from enterprise.extensions import db
from enterprise.models.security import ActiveSession, SecurityEvent


def regenerate_session(user, ip_address=None, browser=None, operating_system=None, device_type=None, ttl_minutes=30):
    session.clear()
    token = secrets.token_urlsafe(32)
    session["session_token"] = token
    session.permanent = True
    session.modified = True
    expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes)
    active = ActiveSession(
        user_id=user.id,
        session_token=token,
        ip_address=ip_address,
        browser=browser,
        operating_system=operating_system,
        device_type=device_type,
        expires_at=expires_at,
    )
    db.session.add(active)
    db.session.add(
        SecurityEvent(
            user_id=user.id,
            event_type="session_regenerated",
            severity="info",
            details={"expires_at": expires_at.isoformat()},
            ip_address=ip_address,
            browser=browser,
            device=device_type,
        )
    )
    return active

