from datetime import datetime, timezone

from app.extensions import db


class ArticleImage(db.Model):

    __tablename__ = "article_images"

    # =========================================================
    # PRIMARY KEY
    # =========================================================

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # =========================================================
    # ARTICLE
    # =========================================================

    article_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "articles.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # =========================================================
    # CLOUDINARY
    # =========================================================

    cloudinary_public_id = db.Column(
        db.String(500),
        nullable=False,
    )

    image_url = db.Column(
        db.Text,
        nullable=False,
    )

    # =========================================================
    # PRESENTATION
    # =========================================================

    display_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    caption = db.Column(
        db.String(500),
        nullable=True,
    )

    width = db.Column(
        db.Integer,
        nullable=True,
    )

    height = db.Column(
        db.Integer,
        nullable=True,
    )

    file_bytes = db.Column(
        db.Integer,
        nullable=True,
    )

    # =========================================================
    # TIMESTAMP
    # =========================================================

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(
            timezone.utc
        ),
    )

    # =========================================================
    # RELATIONSHIP
    # =========================================================

    article = db.relationship(
        "Article",
        back_populates="images",
    )

    def __repr__(self):

        return (
            "<ArticleImage "
            f"id={self.id} "
            f"article={self.article_id} "
            f"order={self.display_order}>"
        )
