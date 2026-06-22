from .extensions import csrf, db, login_manager, mail, migrate


def init_app(app):
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from .routes.security import security_bp

    app.register_blueprint(security_bp)

