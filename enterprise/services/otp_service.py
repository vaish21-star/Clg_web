from datetime import datetime, timedelta
import secrets

try:
    import bcrypt
except Exception:
    bcrypt = None

from werkzeug.security import check_password_hash, generate_password_hash

from enterprise.extensions import db
from enterprise.models.security import OTPVerification


def generate_otp(length=6):
    upper = 10**length
    return str(secrets.randbelow(upper)).zfill(length)


def hash_token(value):
    if bcrypt is not None:
        return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return generate_password_hash(value)


def verify_token(value, hashed_value):
    if not hashed_value:
        return False
    if bcrypt is not None and hashed_value.startswith("$2"):
        return bcrypt.checkpw(value.encode("utf-8"), hashed_value.encode("utf-8"))
    return check_password_hash(hashed_value, value)


def create_otp_record(user_id, purpose, ttl_minutes=5):
    otp = generate_otp()
    record = OTPVerification(
        user_id=user_id,
        purpose=purpose,
        otp_hash=hash_token(otp),
        expires_at=datetime.utcnow() + timedelta(minutes=ttl_minutes),
    )
    db.session.add(record)
    db.session.flush()
    return otp, record


def consume_otp(record, otp_value):
    if record.is_used or record.used_at is not None:
        return False
    if datetime.utcnow() > record.expires_at:
        return False
    if not verify_token(otp_value, record.otp_hash):
        record.attempts += 1
        db.session.add(record)
        return False
    record.is_used = True
    record.used_at = datetime.utcnow()
    db.session.add(record)
    return True
