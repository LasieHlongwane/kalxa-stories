from app.extensions import db


# ============================================================
# KALXA STORIES - ARTICLE CATEGORIES
# ============================================================
#
# PURPOSE:
#
# Organise published Kalxa Stories into categories.
#
# Existing categories:
#
#   local
#   experiences
#   food
#   creators
#   news-kwandebele
#
# Special administrator category:
#
#   trending-now
#
# IMPORTANT:
#
# Trending Now is reserved for articles created or
# managed by the Kalxa administrator.
#
# Articles in this category must have an expiry date.
#
# The expiry date is stored in:
#
#   Article.expires_at
#
# This model does not automatically publish, expire,
# or remove articles from public discovery feeds.
#
# Those rules are enforced by the admin routes and
# the public article queries.
#
# ============================================================


# ============================================================
# SPECIAL CATEGORY SETTINGS
# ============================================================

TRENDING_NOW_CATEGORY_SLUG = "trending-now"

TRENDING_NOW_CATEGORY_NAME = "Trending Now"


class StoryCategory(db.Model):

    __tablename__ = "story_categories"

    # ========================================================
    # PRIMARY KEY
    # ========================================================

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # ========================================================
    # CATEGORY NAME
    # ========================================================

    name = db.Column(
        db.String(120),
        nullable=False,
    )

    # ========================================================
    # CATEGORY SLUG
    # ========================================================

    slug = db.Column(
        db.String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    # ========================================================
    # DESCRIPTION
    # ========================================================

    description = db.Column(
        db.Text,
        nullable=True,
    )

    # ========================================================
    # ACTIVE STATUS
    # ========================================================

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    # ========================================================
    # DISPLAY ORDER
    # ========================================================

    display_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    # ========================================================
    # ARTICLE RELATIONSHIP
    # ========================================================

    articles = db.relationship(
        "Article",
        back_populates="category",
        lazy=True,
    )

    # ========================================================
    # SPECIAL CATEGORY IDENTIFICATION
    # ========================================================

    @property
    def is_trending_now(self):
        """
        Identify the special Trending Now category.

        This category is intended for temporary,
        administrator-published articles.
        """

        return (
            self.slug
            == TRENDING_NOW_CATEGORY_SLUG
        )

    # ========================================================
    # EXPIRY REQUIREMENT
    # ========================================================

    @property
    def requires_expiry(self):
        """
        Indicate whether an article assigned to this
        category requires an expiry date.

        Validation must be implemented in the admin routes.
        """

        return self.is_trending_now

    # ========================================================
    # ADMINISTRATOR-ONLY CATEGORY
    # ========================================================

    @property
    def is_admin_only(self):
        """
        Identify categories restricted to Kalxa admins.

        This property does not enforce authorization.
        Admin and paid-submission routes must enforce
        the restriction when creating/editing articles.
        """

        return self.is_trending_now

    # ========================================================
    # HOMEPAGE TRENDING ELIGIBILITY
    # ========================================================

    @property
    def eligible_for_trending(self):
        """
        Indicate whether this category can qualify
        articles for the Trending Stories section.

        An article must still be:
            - Published
            - Not expired

        The public routes enforce these conditions.
        """

        return (
            self.is_active
            and self.is_trending_now
        )

    # ========================================================
    # REPRESENTATION
    # ========================================================

    def __repr__(self):

        return (
            f"<StoryCategory "
            f"id={self.id} "
            f"name={self.name!r} "
            f"slug={self.slug!r}>"
        )
