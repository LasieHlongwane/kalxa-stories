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
    # Initial Stage 5 events:
    #
    # article_view
    # restaurant_impression
    # restaurant_click
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
    # External ID.
    #
    # IMPORTANT:
    # This is NOT a database foreign key because the restaurant
    # belongs to Kalxa Ticketing.
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
            f"{self.event_type} "
            f"article={self.article_id}>"
        )
