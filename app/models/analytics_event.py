from datetime import datetime, timezone

from app.extensions import db


# ============================================================
# STORY ANALYTICS EVENT
# ============================================================

class StoryAnalyticsEvent(db.Model):

    __tablename__ = "story_analytics_events"


    # ========================================================
    # PRIMARY KEY
    # ========================================================

    id = db.Column(
        db.Integer,
        primary_key=True,
    )


    # ========================================================
    # ARTICLE
    # ========================================================
    #
    # This IS a real database foreign key because Article
    # belongs to the same Kalxa Stories database.
    # ========================================================

    article_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "articles.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )


    # ========================================================
    # EVENT TYPE
    # ========================================================
    #
    # Current / planned events:
    #
    # article_view
    # restaurant_impression
    # restaurant_click
    # comment_submit
    #
    # Later:
    #
    # whatsapp_click
    # directions_click
    # booking_click
    # menu_view
    # experience_view
    # ========================================================

    event_type = db.Column(
        db.String(50),
        nullable=False,
        index=True,
    )


    # ========================================================
    # KALXA TICKETING RESTAURANT
    # ========================================================
    #
    # External Kalxa Ticketing restaurant ID.
    #
    # IMPORTANT:
    #
    # This is deliberately NOT a database foreign key.
    #
    # Kalxa Stories and Kalxa Ticketing use separate
    # applications/databases.
    #
    # Example:
    #
    # kalxa_restaurant_id = 7
    #
    # means Restaurant #7 in Kalxa Ticketing.
    # ========================================================

    kalxa_restaurant_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )


    # ========================================================
    # ANONYMOUS SESSION
    # ========================================================
    #
    # Random anonymous browser/session identifier.
    #
    # We deliberately do not need the person's name,
    # email address or account to measure the funnel.
    # ========================================================

    session_id = db.Column(
        db.String(100),
        nullable=True,
        index=True,
    )


    # ========================================================
    # REFERRER
    # ========================================================

    referrer = db.Column(
        db.Text,
        nullable=True,
    )


    # ========================================================
    # EXTRA EVENT INFORMATION
    # ========================================================
    #
    # Examples:
    #
    # {
    #     "position": 1
    # }
    #
    # {
    #     "source": "restaurant_card"
    # }
    # ========================================================

    event_metadata = db.Column(
        db.JSON,
        nullable=True,
    )


    # ========================================================
    # CREATED
    # ========================================================

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(
            timezone.utc
        ),
        index=True,
    )


    # ========================================================
    # RELATIONSHIP
    # ========================================================
    #
    # This relationship is safe because Article belongs
    # to the same Kalxa Stories database.
    # ========================================================

    article = db.relationship(
        "Article",
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
            "<StoryAnalyticsEvent "
            f"id={self.id} "
            f"event={self.event_type} "
            f"article={self.article_id} "
            f"restaurant={self.kalxa_restaurant_id}>"
        )
