from datetime import datetime

from app.extensions import db


class RestaurantAnalyticsEvent(db.Model):

    __tablename__ = "restaurant_analytics_events"


    # ========================================================
    # PRIMARY KEY
    # ========================================================

    id = db.Column(
        db.Integer,
        primary_key=True,
    )


    # ========================================================
    # RESTAURANT
    # ========================================================

    restaurant_advert_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "restaurant_adverts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )


    # ========================================================
    # EVENT
    # ========================================================

    event_type = db.Column(
        db.String(50),
        nullable=False,
        index=True,
    )


    # ========================================================
    # OPTIONAL EXPERIENCE
    # ========================================================

    experience_post_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )


    # ========================================================
    # ATTRIBUTION SOURCE
    # ========================================================
    #
    # Examples:
    #
    # kalxa_stories
    # direct
    # qr
    # kalxa_discovery
    #
    # ========================================================

    source = db.Column(
        db.String(50),
        nullable=False,
        default="direct",
        index=True,
    )


    # ========================================================
    # KALXA STORIES ATTRIBUTION
    # ========================================================
    #
    # IMPORTANT:
    #
    # This is NOT a database foreign key.
    #
    # Kalxa Stories and Kalxa Ticketing have separate
    # databases.
    #
    # This stores the Article.id from Kalxa Stories.
    #
    # ========================================================

    source_story_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )


    # ========================================================
    # ANONYMOUS ATTRIBUTION SESSION
    # ========================================================
    #
    # No customer name, phone number or email address.
    #
    # This lets us connect:
    #
    # Story
    #   ↓
    # Restaurant
    #   ↓
    # WhatsApp / Directions / Experience
    #
    # without identifying the person.
    #
    # ========================================================

    source_session_id = db.Column(
        db.String(100),
        nullable=True,
        index=True,
    )


    # ========================================================
    # TICKETING SESSION
    # ========================================================

    session_id = db.Column(
        db.String(100),
        nullable=True,
        index=True,
    )


    # ========================================================
    # OPTIONAL EVENT METADATA
    # ========================================================

    event_metadata = db.Column(
        db.JSON,
        nullable=True,
    )


    # ========================================================
    # CREATED
    # ========================================================

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )


    # ========================================================
    # RELATIONSHIP
    # ========================================================

    restaurant = db.relationship(
        "RestaurantAdvert",
        backref=db.backref(
            "analytics_events",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )


    # ========================================================
    # REPRESENTATION
    # ========================================================

    def __repr__(self):

        return (
            "<RestaurantAnalyticsEvent "
            f"id={self.id} "
            f"restaurant={self.restaurant_advert_id} "
            f"event={self.event_type} "
            f"source={self.source}>"
        )
