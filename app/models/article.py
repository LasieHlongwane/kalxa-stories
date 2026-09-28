from datetime import datetime, timezone

from app.extensions import db


class Article(db.Model):

    __tablename__ = "articles"

    # ==========================================
    # PRIMARY KEY
    # ==========================================

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # ==========================================
    # ARTICLE CONTENT
    # ==========================================

    title = db.Column(
        db.String(250),
        nullable=False,
    )

    slug = db.Column(
        db.String(300),
        unique=True,
        nullable=False,
        index=True,
    )

    excerpt = db.Column(
        db.Text,
        nullable=True,
    )

    body = db.Column(
        db.Text,
        nullable=False,
    )

    cover_image_url = db.Column(
        db.Text,
        nullable=True,
    )

    # ==========================================
    # ARTICLE TYPE
    # ==========================================

    article_type = db.Column(
        db.String(50),
        nullable=False,
        default="restaurant_story",
        index=True,
    )

    # Possible values:
    #
    # restaurant_story
    # food_guide
    # sponsored
    # new_restaurant
    # experience

    # ==========================================
    # PUBLISHING
    # ==========================================

    status = db.Column(
        db.String(30),
        nullable=False,
        default="draft",
        index=True,
    )

    # draft
    # published
    # archived

    is_sponsored = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    # ==========================================
    # FUTURE ADVERTISING
    # ==========================================

    campaign_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    # ==========================================
    # SEO
    # ==========================================

    meta_title = db.Column(
        db.String(250),
        nullable=True,
    )

    meta_description = db.Column(
        db.String(320),
        nullable=True,
    )

    # ==========================================
    # TIMESTAMPS
    # ==========================================

    published_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ==========================================
    # RELATIONSHIPS
    # ==========================================

    restaurants = db.relationship(
        "ArticleRestaurant",
        back_populates="article",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def __repr__(self):

        return (
            f"<Article "
            f"id={self.id} "
            f"title={self.title!r}>"
        )