from flask import Flask

from config import Config

from app.extensions import (
    db,
    migrate,
)


def create_app():

    app = Flask(
        __name__
    )

    app.config.from_object(
        Config
    )

    # ========================================================
    # EXTENSIONS
    # ========================================================

    db.init_app(
        app
    )

    migrate.init_app(
        app,
        db,
    )

    # ========================================================
    # MODELS
    # ========================================================

    from app import models

    # ========================================================
    # PUBLIC BLUEPRINT
    # ========================================================

    from app.public.routes import (
        public_bp
    )

    app.register_blueprint(
        public_bp
    )

    # ========================================================
    # PUBLIC API BLUEPRINT
    # ========================================================

    from app.api.routes import (
        api_bp
    )

    app.register_blueprint(
        api_bp
    )

    # ========================================================
    # ADMIN BLUEPRINT
    # ========================================================

    from app.admin.routes import (
        admin_bp
    )

    app.register_blueprint(
        admin_bp
    )

    return app
