from app.extensions import db


# ============================================================
# KALXA STORIES - ARTICLE CATEGORIES
# ============================================================

class StoryCategory(db.Model):

    __tablename__ = "story_categories"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    name = db.Column(
        db.String(120),
        nullable=False,
    )

    slug = db.Column(
        db.String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    display_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    articles = db.relationship(
        "Article",
        back_populates="category",
        lazy=True,
    )

    def __repr__(self):

        return (
            f"<StoryCategory "
            f"id={self.id} "
            f"name={self.name!r}>"
        )
