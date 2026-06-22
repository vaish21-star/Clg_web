from datetime import datetime

from flask import request, session


def security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


def request_metadata():
    return {
        "ip_address": request.headers.get("X-Forwarded-For", request.remote_addr),
        "browser": request.user_agent.string,
        "device": request.user_agent.platform,
        "session_token": session.get("session_token"),
        "timestamp": datetime.utcnow().isoformat(),
    }

