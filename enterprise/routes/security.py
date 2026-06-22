from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from enterprise.extensions import db
from enterprise.middleware.security import request_metadata
from enterprise.services.audit_logger import log_activity
from enterprise.services.otp_service import consume_otp, create_otp_record
from enterprise.services.pin_service import set_security_pin, verify_operation_pin

security_bp = Blueprint("security", __name__, url_prefix="/security")


@security_bp.route("/pin/setup", methods=["POST"])
@login_required
def pin_setup():
    pin_value = (request.json or {}).get("pin", "").strip()
    if len(pin_value) != 6 or not pin_value.isdigit():
        return jsonify({"ok": False, "message": "PIN must be 6 digits"}), 400
    record = set_security_pin(current_user, pin_value)
    db.session.commit()
    return jsonify({"ok": True, "message": "Security PIN saved", "pin_id": record.id})


@security_bp.route("/pin/verify", methods=["POST"])
@login_required
def pin_verify():
    candidate_pin = (request.json or {}).get("pin", "").strip()
    ok, message = verify_operation_pin(current_user, candidate_pin)
    if ok:
        db.session.commit()
        return jsonify({"ok": True, "message": message})
    db.session.rollback()
    return jsonify({"ok": False, "message": message}), 403


@security_bp.route("/pin/change/request-otp", methods=["POST"])
@login_required
def pin_change_request_otp():
    otp, record = create_otp_record(current_user.id, purpose="pin_change")
    log_activity(
        user=current_user,
        module_name="security_pin",
        action_type="PIN_CHANGE_OTP_REQUESTED",
        status="success",
        request_meta=request_metadata(),
    )
    db.session.commit()
    return jsonify({"ok": True, "message": "OTP created", "otp": otp, "otp_id": record.id})


@security_bp.route("/pin/change/verify-otp", methods=["POST"])
@login_required
def pin_change_verify_otp():
    payload = request.json or {}
    otp_value = payload.get("otp", "").strip()
    pin_value = payload.get("pin", "").strip()
    otp_id = payload.get("otp_id")
    from enterprise.models.security import OTPVerification

    record = OTPVerification.query.filter_by(id=otp_id, user_id=current_user.id, purpose="pin_change").first_or_404()
    if not consume_otp(record, otp_value):
        db.session.rollback()
        return jsonify({"ok": False, "message": "Invalid or expired OTP"}), 400
    if len(pin_value) != 6 or not pin_value.isdigit():
        db.session.rollback()
        return jsonify({"ok": False, "message": "PIN must be 6 digits"}), 400
    set_security_pin(current_user, pin_value)
    log_activity(
        user=current_user,
        module_name="security_pin",
        action_type="PIN_CHANGED",
        status="success",
        request_meta=request_metadata(),
    )
    db.session.commit()
    return jsonify({"ok": True, "message": "Security PIN updated"})

