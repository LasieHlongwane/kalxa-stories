from app.extensions import db


class ArticleRestaurant(db.Model):

    __tablename__ = "article_restaurants"

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
    # KALXA TICKETING RESTAURANT
    # ==========================================

    # IMPORTANT:
    #
    # This is NOT a database foreign key.
    #
    # Kalxa Stories and Kalxa Ticketing are
    # separate applications/databases.
    #
    # This stores the restaurant ID belonging
    # to Kalxa Ticketing.

    kalxa_restaurant_id = db.Column(
        db.Integer,
        nullable=False,
        index=True,
    )

    # ==========================================
    # ARTICLE DISPLAY
    # ==========================================

    display_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    is_primary = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    # ==========================================
    # RELATIONSHIP
    # ==========================================

    article = db.relationship(
        "Article",
        back_populates="restaurants",
    )

    def __repr__(self):

        return (
            f"<ArticleRestaurant "
            f"article={self.article_id} "
            f"restaurant={self.kalxa_restaurant_id}>"
        )