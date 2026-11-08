from datetime import datetime, timezone

from app.extensions import db


class ScriptureContent(db.Model):
    __tablename__ = "scripture_content"

    # ==========================================
    # PRIMARY KEY
    # ==========================================

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # ==========================================
    # CATEGORY
    # ==========================================

    category_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "story_categories.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    category = db.relationship(
        "StoryCategory",
        backref=db.backref(
            "scripture_content",
            lazy=True,
        ),
    )

    # ==========================================
    # CONTENT
    # ==========================================

    title = db.Column(
        db.String(250),
        nullable=False,
    )

    content = db.Column(
        db.Text,
        nullable=False,
    )

    # ==========================================
    # BIBLE REFERENCE
    # ==========================================

    book = db.Column(
        db.String(100),
        nullable=False,
    )

    chapter = db.Column(
        db.Integer,
        nullable=False,
    )

    verse = db.Column(
        db.Integer,
        nullable=False,
    )

    verse_reference = db.Column(
        db.String(150),
        nullable=False,
    )

    # ==========================================
    # TRANSLATION
    # ==========================================

    translation = db.Column(
        db.String(50),
        nullable=False,
    )

    # ==========================================
    # EXTERNAL SOURCE
    # ==========================================

    source = db.Column(
        db.String(150),
        nullable=False,
        default="Free Use Bible API",
    )

    source_url = db.Column(
        db.Text,
        nullable=True,
    )

    # ==========================================
    # DISPLAY
    # ==========================================

    display_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    is_active = db.Column(
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
    # REPRESENTATION
    # ==========================================

    def __repr__(self):
        return (
            f"<ScriptureContent "
            f"id={self.id} "
            f"reference={self.verse_reference!r}>"
        )
