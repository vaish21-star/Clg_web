from datetime import datetime, timedelta

try:
    import bcrypt
except Exception:
    bcrypt = None

from werkzeug.security import check_password_hash, generate_password_hash

from enterprise.extensions import db
from enterprise.models.security import ActivityLog, FailedAttempt, SecurityEvent, SecurityPIN
from enterprise.services.audit_logger import log_activity
from enterprise.services.email_service import send_security_alert


def hash_pin(pin_value):
    if bcrypt is not None:
        return bcrypt.hashpw(pin_value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return generate_password_hash(pin_value)


def verify_pin(pin_value, pin_hash):
    if not pin_hash:
        return False
    if bcrypt is not None and pin_hash.startswith("$2"):
        return bcrypt.checkpw(pin_value.encode("utf-8"), pin_hash.encode("utf-8"))
    return check_password_hash(pin_hash, pin_value)


def set_security_pin(user, pin_value):
    record = SecurityPIN.query.filter_by(user_id=user.id).first()
    now = datetime.utcnow()
    if record is None:
        record = SecurityPIN(user_id=user.id, pin_hash=hash_pin(pin_value), created_at=now, last_changed_at=now)
        db.session.add(record)
    else:
        record.pin_hash = hash_pin(pin_value)
        record.last_changed_at = now
        record.failed_attempts = 0
        record.locked_until = None
        db.session.add(record)
    log_activity(user=user, module_name="security_pin", action_type="PIN_SET", status="success")
    return record


def pin_is_locked(pin_record):
    return bool(pin_record and pin_record.locked_until and pin_record.locked_until > datetime.utcnow())


def verify_operation_pin(user, candidate_pin, max_attempts=3, lock_minutes=10):
    record = SecurityPIN.query.filter_by(user_id=user.id).first()
    if record is None:
        return False, "Security PIN not configured"
    if pin_is_locked(record):
        return False, "PIN verification is temporarily locked"
    if verify_pin(candidate_pin, record.pin_hash):
        record.failed_attempts = 0
        record.locked_until = None
        db.session.add(record)
        return True, "PIN verified"

    record.failed_attempts += 1
    if record.failed_attempts >= max_attempts:
        record.locked_until = datetime.utcnow() + timedelta(minutes=lock_minutes)
        db.session.add(
            SecurityEvent(
                user_id=user.id,
                event_type="pin_locked",
                severity="warning",
                details={"reason": "max_attempts_exceeded", "failed_attempts": record.failed_attempts},
            )
        )
        db.session.add(
            FailedAttempt(
                user_id=user.id,
                attempt_type="pin_verification",
                identifier=user.email,
                failure_reason="Maximum PIN attempts exceeded",
                attempts=record.failed_attempts,
                locked_until=record.locked_until,
            )
        )
        if user.email:
            send_security_alert(user.email, "Security PIN Locked", "Your operation security PIN was locked after repeated failed attempts.")
    db.session.add(record)
    db.session.add(
        ActivityLog(
            user_id=user.id,
            user_type="admin",
            module_name="security_pin",
            action_type="PIN_VERIFY_FAILED",
            status="failed",
            remarks="Invalid security PIN",
        )
    )
    return False, "Invalid PIN"
