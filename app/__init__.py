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

    # Area-based email subscribers (independent of restaurant & paid articles)
    from app.newsletter.models import StoryEmailSubscriber  # register model with Alembic
    from app.newsletter.routes import newsletter_bp
    app.register_blueprint(newsletter_bp)

    # ========================================================
    # KALXA STORIES — INDEPENDENT PAID PUBLISHING
    # ========================================================
    #
    # Businesses and creators:
    # R200 once-off permanent publication.
    #
    # Existing Premium Restaurant integration is unaffected.
    # ========================================================

    from app.paid import models as paid_models  # noqa: F401

    from app.paid.routes import paid_bp

    app.register_blueprint(paid_bp)

    # ========================================================
    # KALXA STORIES — EMAIL NOTIFICATIONS
    # ========================================================
    #
    # Location-based campaigns for confirmed subscribers.
    #
    # Independent of:
    # - Premium Restaurant subscriptions
    # - KALXA Ticketing restaurant integration
    # - Paid Stories payment processing
    # ========================================================

    from app.notifications.models import (
        StoryNotificationCampaign,
        StoryNotificationDelivery,
    )

    from app.notifications.routes import notification_bp

    app.register_blueprint(notification_bp)

    return app
