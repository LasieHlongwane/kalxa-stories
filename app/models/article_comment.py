from datetime import datetime, timezone

from app.extensions import db


class ArticleComment(db.Model):

    __tablename__ = "article_comments"

    # ==========================================
    # PRIMARY KEY
    # ==========================================

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # ==========================================
    # ARTICLE
    # ==========================================

    article_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "articles.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # ==========================================
    # COMMENTER
    # ==========================================

    display_name = db.Column(
        db.String(80),
        nullable=False,
    )

    anonymous_session_id = db.Column(
        db.String(120),
        nullable=False,
        index=True,
    )

    # ==========================================
    # COMMENT
    # ==========================================

    comment_text = db.Column(
        db.Text,
        nullable=False,
    )

    # ==========================================
    # MODERATION
    # ==========================================

    moderation_status = db.Column(
        db.String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    # pending
    # approved
    # rejected

    active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    # ==========================================
    # TIMESTAMPS
    # ==========================================

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(
            timezone.utc
        ),
        index=True,
    )

    # ==========================================
    # RELATIONSHIP
    # ==========================================

    article = db.relationship(
        "Article",
        back_populates="comments",
    )

    def __repr__(self):

        return (
            f"<ArticleComment "
            f"id={self.id} "
            f"article={self.article_id}>"
        )
