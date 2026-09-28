from flask import (
    Blueprint,
    abort,
    render_template,
)

from app.models import Article
from app.kalxa.client import (
    get_restaurants_by_ids,
)

public_bp = Blueprint(
    "public",
    __name__,
)


# ============================================================
# HOME
# ============================================================

@public_bp.route("/")
def home():

    articles = (
        Article.query
        .filter_by(status="published")
        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )
        .limit(12)
        .all()
    )

    featured_article = (
        articles[0]
        if articles
        else None
    )

    remaining_articles = (
        articles[1:]
        if len(articles) > 1
        else []
    )

    return render_template(
        "home.html",
        featured_article=featured_article,
        articles=remaining_articles,
    )


# ============================================================
# ALL STORIES
# ============================================================

@public_bp.route("/stories")
def stories():

    articles = (
        Article.query
        .filter_by(status="published")
        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )
        .all()
    )

    return render_template(
        "stories.html",
        articles=articles,
    )



# ============================================================
# ARTICLE
# ============================================================

@public_bp.route(
    "/stories/<string:slug>"
)
def article_detail(slug):

    article = (
        Article.query
        .filter_by(
            slug=slug,
            status="published",
        )
        .first()
    )

    if article is None:

        abort(404)


    # ========================================================
    # KALXA TICKETING RESTAURANTS
    # ========================================================

    relations = sorted(
        article.restaurants,
        key=lambda relation:
            relation.display_order,
    )


    restaurant_ids = [

        relation.kalxa_restaurant_id

        for relation
        in relations

    ]


    featured_restaurants = (
        get_restaurants_by_ids(
            restaurant_ids
        )
    )


    # ========================================================
    # RELATED STORIES
    # ========================================================

    related_articles = (
        Article.query
        .filter(
            Article.status == "published",
            Article.id != article.id,
        )
        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )
        .limit(3)
        .all()
    )


    return render_template(
        "article.html",
        article=article,
        featured_restaurants=featured_restaurants,
        related_articles=related_articles,
    )
    
    
    
@public_bp.route(
    "/health"
)
def health():

    return {
        "status": "ok",
        "service": "kalxa-stories",
    }, 200