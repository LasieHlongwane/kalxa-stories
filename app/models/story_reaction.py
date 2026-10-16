"""
KwaNdebele Kalxa Hub — Story Reactions

Anonymous story likes.

One active like per article and anonymous browser session.
"""

from datetime import datetime, timezone

from app.extensions import db


class StoryReaction(db.Model):

    __tablename__ = "story_reactions"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    article_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "articles.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    anonymous_session_id = db.Column(
        db.String(100),
        nullable=False,
    )

    reaction_type = db.Column(
        db.String(20),
        nullable=False,
        default="like",
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "article_id",
            "anonymous_session_id",
            name="uq_story_reaction_article_session",
        ),
    )

    article = db.relationship(
        "Article",
        backref=db.backref(
            "story_reactions",
            lazy="dynamic",
            passive_deletes=True,
        ),
    )

    def __repr__(self):

        return (
            f"<StoryReaction "
            f"article_id={self.article_id} "
            f"type={self.reaction_type}>"
        )
