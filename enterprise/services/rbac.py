from functools import wraps

from flask import abort
from flask_login import current_user


def user_permissions():
    role = getattr(current_user, "role", None)
    permissions = []
    if not role:
        return permissions
    for rp in getattr(role, "permissions", []):
        permission = getattr(rp, "permission", None)
        if permission and permission.name:
            permissions.append(permission.name)
    return permissions


def permission_required(permission_name):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if permission_name not in user_permissions() and getattr(current_user, "role", None) and current_user.role.name not in {"Super Admin", "Admin"}:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator

