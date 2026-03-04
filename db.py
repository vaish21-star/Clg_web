import os
import mysql.connector


def _try_connect(passwords):
    last_error = None
    for pwd in passwords:
        try:
            return mysql.connector.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                user=os.environ.get("DB_USER", "root"),
                password=pwd,
                database=os.environ.get("DB_NAME", "svp_college"),
            )
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("No database password configured")


def get_db():
    env_pwd = os.environ.get("DB_PASSWORD")
    candidates = []
    if env_pwd:
        candidates.append(env_pwd)
    # Keep both project defaults so either setup can run.
    candidates.extend(["Root@123", "naya@123jeev"])
    seen = set()
    unique = []
    for p in candidates:
        if p not in seen:
            unique.append(p)
            seen.add(p)
    return _try_connect(unique)
