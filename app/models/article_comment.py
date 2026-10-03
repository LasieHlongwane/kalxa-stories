from datetime import datetime, timezone

from app.extensions import db


# ============================================================
# ARTICLE COMMENT
# ============================================================

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
    # RELATIONSHIPS
    # ==========================================

    article = db.relationship(
        "Article",
        back_populates="comments",
    )

    upvotes = db.relationship(
        "CommentUpvote",
        back_populates="comment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )

    # ==========================================
    # HELPERS
    # ==========================================

    @property
    def upvote_count(self):

        return len(
            self.upvotes
        )

    def is_upvoted_by(
        self,
        anonymous_session_id,
    ):

        if not anonymous_session_id:

            return False

        return any(
            upvote.anonymous_session_id
            ==
            anonymous_session_id

            for upvote in self.upvotes
        )

    # ==========================================
    # REPRESENTATION
    # ==========================================

    def __repr__(self):

        return (
            f"<ArticleComment "
            f"id={self.id} "
            f"article={self.article_id} "
            f"upvotes={self.upvote_count}>"
        )


# ============================================================
# COMMENT UPVOTE
# ============================================================

class CommentUpvote(db.Model):

    __tablename__ = "comment_upvotes"

    # ==========================================
    # TABLE CONSTRAINTS
    # ==========================================

    __table_args__ = (

        db.UniqueConstraint(
            "comment_id",
            "anonymous_session_id",
            name=(
                "uq_comment_upvote_"
                "comment_session"
            ),
        ),

    )

    # ==========================================
    # PRIMARY KEY
    # ==========================================

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # ==========================================
    # COMMENT
    # ==========================================

    comment_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "article_comments.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # ==========================================
    # ANONYMOUS VISITOR
    # ==========================================

    anonymous_session_id = db.Column(
        db.String(120),
        nullable=False,
        index=True,
    )

    # ==========================================
    # TIMESTAMP
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

    comment = db.relationship(
        "ArticleComment",
        back_populates="upvotes",
    )

    # ==========================================
    # REPRESENTATION
    # ==========================================

    def __repr__(self):

        return (
            f"<CommentUpvote "
            f"id={self.id} "
            f"comment={self.comment_id}>"
        )
