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

    # =========================================================
    # LEGACY COVER IMAGE
    # =========================================================
    #
    # Keep this field for backward compatibility with stories
    # created before ArticleImage existed.
    #
    # New stories should use ArticleImage.
    # =========================================================

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
        default=lambda: datetime.now(
            timezone.utc
        ),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(
            timezone.utc
        ),
        onupdate=lambda: datetime.now(
            timezone.utc
        ),
    )

    # ==========================================
    # RESTAURANTS
    # ==========================================

    restaurants = db.relationship(
        "ArticleRestaurant",
        back_populates="article",
        cascade="all, delete-orphan",
        lazy=True,
    )

    # ==========================================
    # STORY IMAGES
    # ==========================================

    images = db.relationship(
        "ArticleImage",
        back_populates="article",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="ArticleImage.display_order",
    )

    # ==========================================
    # DISPLAY COVER
    # ==========================================

    @property
    def display_cover_image_url(self):
        """
        Prefer the first ArticleImage.

        Fall back to the old cover_image_url so existing
        published stories continue working.
        """

        if self.images:

            first_image = min(
                self.images,
                key=lambda image:
                    image.display_order,
            )

            return first_image.image_url

        return self.cover_image_url

    def __repr__(self):

        return (
            f"<Article "
            f"id={self.id} "
            f"title={self.title!r}>"
        )
