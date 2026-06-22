import os
import mysql.connector


def _try_connect(passwords):
    last_error = None

    for pwd in passwords:
        try:
            return mysql.connector.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", 3306)),
                user=os.environ.get("DB_USER", "root"),
                password=pwd,
                database=os.environ.get("DB_NAME", "defaultdb"),
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

    # Local development passwords (optional)
    candidates.extend([
        "Root@123",
        "naya@123jeev"
    ])

    # Remove duplicates
    unique = []
    seen = set()

    for p in candidates:
        if p not in seen:
            unique.append(p)
            seen.add(p)

    return _try_connect(unique)