from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import Index, UniqueConstraint

from enterprise.extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, nullable=True, index=True)
    modified_by = db.Column(db.Integer, nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default="active", index=True)


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), nullable=False, unique=True, index=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    last_logout_at = db.Column(db.DateTime, nullable=True)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    pin_locked_until = db.Column(db.DateTime, nullable=True)
    current_session_token = db.Column(db.String(128), nullable=True, index=True)

    role = db.relationship("Role", back_populates="users", lazy="joined")
    admin_profile = db.relationship("Admin", back_populates="user", uselist=False, cascade="all, delete-orphan")
    student_profile = db.relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")
    staff_profile = db.relationship("Staff", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Admin(TimestampMixin, db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    full_name = db.Column(db.String(160), nullable=False)
    gmail_id = db.Column(db.String(255), nullable=False, index=True)
    mobile = db.Column(db.String(32), nullable=True)
    department = db.Column(db.String(120), nullable=True, index=True)

    user = db.relationship("User", back_populates="admin_profile", lazy="joined")


class Student(TimestampMixin, db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    admission_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    full_name = db.Column(db.String(160), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=True, index=True)
    branch = db.Column(db.String(120), nullable=True, index=True)
    college_reg_no = db.Column(db.String(64), nullable=True, unique=True, index=True)

    user = db.relationship("User", back_populates="student_profile", lazy="joined")


class Staff(TimestampMixin, db.Model):
    __tablename__ = "staff"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    employee_code = db.Column(db.String(64), nullable=False, unique=True, index=True)
    full_name = db.Column(db.String(160), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=True, index=True)
    department = db.Column(db.String(120), nullable=True, index=True)

    user = db.relationship("User", back_populates="staff_profile", lazy="joined")


class Role(TimestampMixin, db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True, index=True)
    description = db.Column(db.String(255), nullable=True)

    users = db.relationship("User", back_populates="role", lazy="select")
    permissions = db.relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(TimestampMixin, db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    module_name = db.Column(db.String(120), nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)

    roles = db.relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class RolePermission(TimestampMixin, db.Model):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = db.Column(db.Integer, db.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)

    role = db.relationship("Role", back_populates="permissions", lazy="joined")
    permission = db.relationship("Permission", back_populates="roles", lazy="joined")


class SecurityPIN(TimestampMixin, db.Model):
    __tablename__ = "security_pins"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    pin_hash = db.Column(db.String(255), nullable=False)
    last_changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", lazy="joined")


class OTPVerification(TimestampMixin, db.Model):
    __tablename__ = "otp_verifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose = db.Column(db.String(64), nullable=False, index=True)
    otp_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    is_used = db.Column(db.Boolean, nullable=False, default=False)

    user = db.relationship("User", lazy="joined")


class LoginHistory(TimestampMixin, db.Model):
    __tablename__ = "login_history"
    __table_args__ = (
        Index("ix_login_history_user_type_date", "user_type", "login_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_type = db.Column(db.String(32), nullable=False, index=True)
    username = db.Column(db.String(120), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=True, index=True)
    login_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    logout_at = db.Column(db.DateTime, nullable=True)
    session_duration_seconds = db.Column(db.Integer, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True, index=True)
    browser = db.Column(db.String(255), nullable=True)
    operating_system = db.Column(db.String(255), nullable=True)
    device_type = db.Column(db.String(120), nullable=True)
    mac_address = db.Column(db.String(64), nullable=True)
    login_status = db.Column(db.String(32), nullable=False, default="success", index=True)
    failure_reason = db.Column(db.String(255), nullable=True)
    location = db.Column(db.String(255), nullable=True)
    created_timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class ActivityLog(TimestampMixin, db.Model):
    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("ix_activity_logs_module_action", "module_name", "action_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_type = db.Column(db.String(32), nullable=False, index=True)
    module_name = db.Column(db.String(120), nullable=False, index=True)
    action_type = db.Column(db.String(120), nullable=False, index=True)
    previous_data = db.Column(db.JSON, nullable=True)
    updated_data = db.Column(db.JSON, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    ip_address = db.Column(db.String(64), nullable=True, index=True)
    browser = db.Column(db.String(255), nullable=True)
    device = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="success", index=True)
    remarks = db.Column(db.String(255), nullable=True)


class SecurityEvent(TimestampMixin, db.Model):
    __tablename__ = "security_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = db.Column(db.String(120), nullable=False, index=True)
    severity = db.Column(db.String(32), nullable=False, default="info", index=True)
    details = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True, index=True)
    browser = db.Column(db.String(255), nullable=True)
    device = db.Column(db.String(120), nullable=True)


class ActiveSession(TimestampMixin, db.Model):
    __tablename__ = "active_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_token = db.Column(db.String(128), nullable=False, unique=True, index=True)
    ip_address = db.Column(db.String(64), nullable=True, index=True)
    browser = db.Column(db.String(255), nullable=True)
    operating_system = db.Column(db.String(255), nullable=True)
    device_type = db.Column(db.String(120), nullable=True)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)


class FailedAttempt(TimestampMixin, db.Model):
    __tablename__ = "failed_attempts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    attempt_type = db.Column(db.String(64), nullable=False, index=True)
    identifier = db.Column(db.String(255), nullable=True, index=True)
    failure_reason = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True, index=True)
    browser = db.Column(db.String(255), nullable=True)
    attempts = db.Column(db.Integer, nullable=False, default=1)
    locked_until = db.Column(db.DateTime, nullable=True, index=True)


class Notification(TimestampMixin, db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type = db.Column(db.String(120), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    read_at = db.Column(db.DateTime, nullable=True, index=True)
    sent_via_email = db.Column(db.Boolean, nullable=False, default=False)


class BackupHistory(TimestampMixin, db.Model):
    __tablename__ = "backup_history"

    id = db.Column(db.Integer, primary_key=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    file_name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    file_path = db.Column(db.String(500), nullable=False)
    checksum = db.Column(db.String(128), nullable=True, index=True)
    backup_type = db.Column(db.String(64), nullable=False, default="manual", index=True)
    created_timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class RestoreHistory(TimestampMixin, db.Model):
    __tablename__ = "restore_history"

    id = db.Column(db.Integer, primary_key=True)
    restored_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source_backup_id = db.Column(db.Integer, db.ForeignKey("backup_history.id", ondelete="SET NULL"), nullable=True, index=True)
    restore_status = db.Column(db.String(32), nullable=False, default="success", index=True)
    remarks = db.Column(db.String(255), nullable=True)
    created_timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class PasswordHistory(TimestampMixin, db.Model):
    __tablename__ = "password_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class PinHistory(TimestampMixin, db.Model):
    __tablename__ = "pin_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pin_hash = db.Column(db.String(255), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class DeviceHistory(TimestampMixin, db.Model):
    __tablename__ = "device_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_fingerprint = db.Column(db.String(255), nullable=False, unique=True, index=True)
    device_type = db.Column(db.String(120), nullable=True, index=True)
    browser = db.Column(db.String(255), nullable=True)
    operating_system = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True, index=True)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

