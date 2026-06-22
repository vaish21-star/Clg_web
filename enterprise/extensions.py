try:
    from flask_login import LoginManager
except Exception:
    class LoginManager:  # pragma: no cover
        def __init__(self):
            self.login_view = None

        def init_app(self, app):
            return None


try:
    from flask_mail import Mail
except Exception:
    class Mail:  # pragma: no cover
        def init_app(self, app):
            return None

        def send(self, message):
            return None


try:
    from flask_migrate import Migrate
except Exception:
    class Migrate:  # pragma: no cover
        def init_app(self, app, db):
            return None


try:
    from flask_sqlalchemy import SQLAlchemy
except Exception:
    class _FallbackQuery:
        def __getattr__(self, name):
            raise RuntimeError("Flask-SQLAlchemy is required for enterprise models.")

    class _FallbackDB:
        Model = object

        def __init__(self):
            self.session = None

        def init_app(self, app):
            return None

        def __getattr__(self, name):
            if name == "Column":
                return lambda *args, **kwargs: None
            if name in {"Integer", "String", "DateTime", "Boolean", "Text", "JSON"}:
                return object
            if name in {"ForeignKey", "Index", "UniqueConstraint"}:
                return lambda *args, **kwargs: None
            if name == "relationship":
                return lambda *args, **kwargs: None
            return _FallbackQuery()

    SQLAlchemy = _FallbackDB


try:
    from flask_wtf import CSRFProtect
except Exception:
    class CSRFProtect:  # pragma: no cover
        def init_app(self, app):
            return None

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()
