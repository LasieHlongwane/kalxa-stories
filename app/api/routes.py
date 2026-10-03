from datetime import (
    datetime,
    timezone,
)

from flask import (
    Blueprint,
    jsonify,
    request,
    url_for,
)

from sqlalchemy import (
    or_,
)

from app.models import (
    Article,
)


# ============================================================
# API BLUEPRINT
# ============================================================

api_bp = Blueprint(
    "api",
    __name__,
    url_prefix="/api/public",
)


# ============================================================
# API SETTINGS
# ============================================================

DEFAULT_STORY_LIMIT = 8
MAX_STORY_LIMIT = 20


# ============================================================
# ACTIVE PUBLISHED STORY FILTER
# ============================================================

def active_published_story_query():
    """
    Return stories that are:

        1. Published
        2. Not expired

    Expired stories remain accessible through their permanent
    public URLs, but they should not be promoted through the
    Kalxa Discovery feed.
    """

    now = datetime.now(
        timezone.utc
    )

    return (
        Article.query

        .filter(
            Article.status
            == "published",

            or_(
                Article.expires_at.is_(None),
                Article.expires_at > now,
            ),
        )
    )


# ============================================================
# SERIALIZE STORY
# ============================================================

def serialize_story(
    article,
):
    """
    Convert an Article into the small public representation
    required by Kalxa Discovery.

    Do not expose article.body here.

    Discovery only needs enough information to display the
    story card and send the visitor to Kalxa Stories.
    """

    story_url = url_for(
        "public.article_detail",
        slug=article.slug,
        _external=True,
    )

    return {

        "id":
            article.id,

        "title":
            article.title,

        "slug":
            article.slug,

        "excerpt":
            article.excerpt,

        "cover_image_url":
            article.display_cover_image_url,

        "article_type":
            article.article_type,

        "is_sponsored":
            bool(
                article.is_sponsored
            ),

        "published_at":
            (
                article.published_at.isoformat()
                if article.published_at
                else None
            ),

        "story_url":
            story_url,
    }


# ============================================================
# PUBLIC STORIES FEED
# ============================================================

@api_bp.get(
    "/stories"
)
def public_stories():
    """
    Public Kalxa Stories discovery feed.

    Used by Kalxa Discovery to display a horizontally
    swipeable Stories section.

    Example:

        GET /api/public/stories

        GET /api/public/stories?limit=6
    """

    # ========================================================
    # LIMIT
    # ========================================================

    requested_limit = (
        request.args.get(
            "limit",
            default=DEFAULT_STORY_LIMIT,
            type=int,
        )
    )

    if requested_limit is None:

        requested_limit = (
            DEFAULT_STORY_LIMIT
        )

    limit = max(
        1,
        min(
            requested_limit,
            MAX_STORY_LIMIT,
        ),
    )


    # ========================================================
    # STORIES
    # ========================================================

    articles = (
        active_published_story_query()

        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )

        .limit(
            limit
        )

        .all()
    )


    # ========================================================
    # SERIALIZE
    # ========================================================

    stories = [

        serialize_story(
            article
        )

        for article
        in articles

    ]


    # ========================================================
    # RESPONSE
    # ========================================================

    return jsonify(
        {
            "ok":
                True,

            "count":
                len(
                    stories
                ),

            "stories":
                stories,
        }
    ), 200
