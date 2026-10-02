from datetime import (
    datetime,
    timedelta,
    timezone,
)

from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)

from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    session,
    flask,
    url_for,
)

from itsdangerous import (
    URLSafeTimedSerializer,
)

from app.extensions import db

from app.models import (
    Article,
    StoryAnalyticsEvent,
)

from app.models.article import Article
from app.models.article_comment import ArticleComment

from app.kalxa.client import (
    get_restaurant,
    get_restaurants_by_ids,
)


public_bp = Blueprint(
    "public",
    __name__,
)


# ============================================================
# ANALYTICS SETTINGS
# ============================================================

ANALYTICS_SESSION_KEY = (
    "kalxa_stories_analytics_session"
)

ANALYTICS_DEDUPLICATION_MINUTES = 30


# ============================================================
# KALXA CROSS-APP ATTRIBUTION SETTINGS
# ============================================================
#
# IMPORTANT:
#
# Kalxa Stories and Kalxa Ticketing MUST use the same:
#
# KALXA_ATTRIBUTION_SECRET
#
# The secret itself must live in the environment and must
# never be committed to GitHub.
#
# The salt must also match the salt used by Ticketing.
# ============================================================

KALXA_ATTRIBUTION_SALT = (
    "kalxa-restaurant-attribution"
)


# ============================================================
# ANONYMOUS ANALYTICS SESSION
# ============================================================

def get_analytics_session_id():
    """
    Return an anonymous Kalxa Stories browser/session ID.

    No name, email address, phone number or Kalxa account
    information is required.

    Flask stores this identifier inside the visitor's signed
    session cookie.
    """

    session_id = (
        session.get(
            ANALYTICS_SESSION_KEY
        )
    )


    if not session_id:

        session_id = (
            uuid4().hex
        )

        session[
            ANALYTICS_SESSION_KEY
        ] = session_id

        session.modified = True


    return session_id


# ============================================================
# CHECK RECENT EVENT
# ============================================================

def recent_event_exists(
    article_id,
    event_type,
    session_id,
    restaurant_id=None,
):
    """
    Check whether the same anonymous session has already
    generated this event recently.

    This prevents repeated refreshes from immediately
    inflating analytics numbers.
    """

    cutoff = (
        datetime.now(
            timezone.utc
        )
        -
        timedelta(
            minutes=(
                ANALYTICS_DEDUPLICATION_MINUTES
            )
        )
    )


    query = (
        StoryAnalyticsEvent.query

        .filter(
            StoryAnalyticsEvent.article_id
            == article_id,

            StoryAnalyticsEvent.event_type
            == event_type,

            StoryAnalyticsEvent.session_id
            == session_id,

            StoryAnalyticsEvent.created_at
            >= cutoff,
        )
    )


    if restaurant_id is None:

        query = (
            query.filter(
                StoryAnalyticsEvent
                .kalxa_restaurant_id
                .is_(None)
            )
        )

    else:

        query = (
            query.filter(
                StoryAnalyticsEvent
                .kalxa_restaurant_id
                == restaurant_id
            )
        )


    return (
        query.first()
        is not None
    )


# ============================================================
# RECORD ANALYTICS EVENT
# ============================================================

def record_analytics_event(
    article,
    event_type,
    restaurant_id=None,
    metadata=None,
    deduplicate=True,
):
    """
    Store one anonymous Kalxa Stories analytics event.

    Returns True when a new event is recorded.

    Returns False when the event is skipped or could not
    safely be recorded.

    Analytics must never prevent the visitor from reading
    a story or opening a restaurant.
    """

    session_id = (
        get_analytics_session_id()
    )


    if (
        deduplicate
        and
        recent_event_exists(
            article_id=(
                article.id
            ),
            event_type=(
                event_type
            ),
            session_id=(
                session_id
            ),
            restaurant_id=(
                restaurant_id
            ),
        )
    ):

        return False


    event = (
        StoryAnalyticsEvent(
            article_id=(
                article.id
            ),

            event_type=(
                event_type
            ),

            kalxa_restaurant_id=(
                restaurant_id
            ),

            session_id=(
                session_id
            ),

            referrer=(
                request.referrer
                if request
                else None
            ),

            event_metadata=(
                metadata
                or
                {}
            ),
        )
    )


    try:

        db.session.add(
            event
        )

        db.session.commit()

        return True


    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to record Kalxa Stories "
            "analytics event."
        )

        return False


# ============================================================
# BUILD SIGNED ATTRIBUTION TOKEN
# ============================================================

def build_attribution_token(
    article,
    restaurant_id,
    analytics_session_id,
):
    """
    Create a signed Kalxa Stories attribution token.

    Kalxa Ticketing verifies this token before accepting
    Stories attribution.

    The token contains only anonymous attribution data.

    Payload example:

        {
            "source": "kalxa_stories",
            "story_id": 7,
            "restaurant_id": 2,
            "source_session_id": "abc123..."
        }

    No customer name, email address, phone number or IP
    address is included.
    """

    # ========================================================
    # ATTRIBUTION SECRET
    # ========================================================

    secret = (
        current_app.config
        .get(
            "KALXA_ATTRIBUTION_SECRET",
            "",
        )
    )


    if secret:

        secret = (
            str(
                secret
            )
            .strip()
        )


    if not secret:

        current_app.logger.error(
            "KALXA_ATTRIBUTION_SECRET "
            "is not configured."
        )

        return None


    # ========================================================
    # SERIALIZER
    # ========================================================

    serializer = (
        URLSafeTimedSerializer(
            secret,
            salt=(
                KALXA_ATTRIBUTION_SALT
            ),
        )
    )


    # ========================================================
    # SIGNED PAYLOAD
    # ========================================================

    payload = {
        "source":
            "kalxa_stories",

        "story_id":
            article.id,

        "restaurant_id":
            restaurant_id,

        "source_session_id":
            analytics_session_id,
    }


    # ========================================================
    # CREATE TOKEN
    # ========================================================

    try:

        return serializer.dumps(
            payload
        )

    except Exception:

        current_app.logger.exception(
            "Unable to create Kalxa Stories "
            "attribution token."
        )

        return None


# ============================================================
# BUILD ATTRIBUTED TICKETING URL
# ============================================================

def build_attributed_ticketing_url(
    profile_url,
    article,
    restaurant_id,
    analytics_session_id,
):
    """
    Add a signed Kalxa Stories attribution token to the
    Ticketing restaurant URL.

    Existing query parameters are preserved.

    Example:

        https://tickets.kalxa.co.za/restaurant/2
            ?kat=<SIGNED_TOKEN>

    If attribution cannot be generated, the visitor can
    still reach the restaurant through the original
    profile URL.
    """

    if not profile_url:

        return None


    # ========================================================
    # BUILD SIGNED TOKEN
    # ========================================================

    token = (
        build_attribution_token(
            article=(
                article
            ),

            restaurant_id=(
                restaurant_id
            ),

            analytics_session_id=(
                analytics_session_id
            ),
        )
    )


    # ========================================================
    # ATTRIBUTION FAILURE
    # ========================================================
    #
    # Analytics must never prevent restaurant discovery.
    #
    # If signing fails, redirect to the normal restaurant
    # profile without attribution.
    # ========================================================

    if not token:

        return profile_url


    try:

        # ====================================================
        # PARSE PROFILE URL
        # ====================================================

        parsed_url = (
            urlsplit(
                profile_url
            )
        )


        # ====================================================
        # PRESERVE EXISTING QUERY PARAMETERS
        # ====================================================

        existing_query = dict(
            parse_qsl(
                parsed_url.query,
                keep_blank_values=True,
            )
        )


        # ====================================================
        # REMOVE LEGACY UNSIGNED ATTRIBUTION
        # ====================================================
        #
        # These parameters were used by the earlier Stage 6
        # implementation.
        #
        # They are removed so the signed token becomes the
        # single source of truth.
        # ====================================================

        existing_query.pop(
            "source",
            None,
        )

        existing_query.pop(
            "article_id",
            None,
        )

        existing_query.pop(
            "restaurant_id",
            None,
        )

        existing_query.pop(
            "source_session",
            None,
        )


        # ====================================================
        # ADD SIGNED ATTRIBUTION
        # ====================================================

        existing_query[
            "kat"
        ] = token


        # ====================================================
        # REBUILD QUERY
        # ====================================================

        updated_query = (
            urlencode(
                existing_query
            )
        )


        # ====================================================
        # REBUILD URL
        # ====================================================

        return (
            urlunsplit(
                (
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    updated_query,
                    parsed_url.fragment,
                )
            )
        )


    except Exception:

        current_app.logger.exception(
            "Unable to build signed "
            "Kalxa Ticketing URL."
        )

        return profile_url


# ============================================================
# HOME
# ============================================================

@public_bp.route("/")
def home():

    articles = (
        Article.query

        .filter_by(
            status=(
                "published"
            )
        )

        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )

        .limit(
            12
        )

        .all()
    )


    featured_article = (
        articles[0]
        if articles
        else None
    )


    remaining_articles = (
        articles[1:]
        if len(
            articles
        ) > 1
        else []
    )


    return render_template(
        "home.html",

        featured_article=(
            featured_article
        ),

        articles=(
            remaining_articles
        ),
    )


# ============================================================
# ALL STORIES
# ============================================================

@public_bp.route(
    "/stories"
)
def stories():

    articles = (
        Article.query

        .filter_by(
            status=(
                "published"
            )
        )

        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )

        .all()
    )


    return render_template(
        "stories.html",

        articles=(
            articles
        ),
    )


# ============================================================
# ARTICLE
# ============================================================

@public_bp.route(
    "/stories/<string:slug>"
)
def article_detail(
    slug,
):

    article = (
        Article.query

        .filter_by(
            slug=(
                slug
            ),

            status=(
                "published"
            ),
        )

        .first()
    )


    if article is None:

        abort(
            404
        )


    # ========================================================
    # ARTICLE VIEW
    # ========================================================

    record_analytics_event(
        article=(
            article
        ),

        event_type=(
            "article_view"
        ),

        metadata={
            "source":
                "article_page",
        },
    )


    # ========================================================
    # KALXA TICKETING RESTAURANTS
    # ========================================================

    relations = (
        sorted(
            article.restaurants,

            key=lambda relation:
                relation.display_order,
        )
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
    # RESTAURANT IMPRESSIONS
    # ========================================================
    #
    # For the current MVP an impression means that the
    # restaurant card was included in the rendered article.
    #
    # Later this can be upgraded to IntersectionObserver
    # tracking so an impression only counts once the card
    # actually enters the visitor's viewport.
    # ========================================================

    for position, restaurant in enumerate(
        featured_restaurants,
        start=1,
    ):

        restaurant_id = (
            restaurant.get(
                "id"
            )
        )


        if restaurant_id is None:

            continue


        record_analytics_event(
            article=(
                article
            ),

            event_type=(
                "restaurant_impression"
            ),

            restaurant_id=(
                restaurant_id
            ),

            metadata={
                "position":
                    position,

                "source":
                    "article_restaurant_card",
            },
        )


    # ========================================================
    # RELATED STORIES
    # ========================================================

    related_articles = (
        Article.query

        .filter(
            Article.status
            == "published",

            Article.id
            != article.id,
        )

        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )

        .limit(
            3
        )

        .all()
    )

    # ========================================================
# READING TIME
# ========================================================

    plain_body = (
        article.body
        .replace(
          "<",
         " <",
        )
    )

    word_count = len(
        plain_body.split()
    )

    reading_minutes = max(
      1,
      round(
        word_count
        /
        220
      ),
    )


    # ========================================================
    # RENDER
    # ========================================================

    return render_template(
        "article.html",

        article=(
            article
        ),

        featured_restaurants=(
            featured_restaurants
        ),

        reading_minutes=(
            reading_minutes
        ),

        related_articles=(
            related_articles
        ),
    )


# ============================================================
# TRACK RESTAURANT CLICK
# ============================================================

@public_bp.route(
    "/stories/<string:slug>/restaurants/<int:restaurant_id>"
)
def restaurant_click(
    slug,
    restaurant_id,
):

    # ========================================================
    # STORY
    # ========================================================

    article = (
        Article.query

        .filter(
            Article.slug
            == slug,

            Article.status
            == "published",
        )

        .first_or_404()
    )


    # ========================================================
    # VERIFY RESTAURANT BELONGS TO STORY
    # ========================================================

    linked_restaurant_ids = {

        relation.kalxa_restaurant_id

        for relation
        in article.restaurants

    }


    if (
        restaurant_id
        not in linked_restaurant_ids
    ):

        abort(
            404
        )


    # ========================================================
    # GET LIVE RESTAURANT FROM KALXA TICKETING
    # ========================================================

    restaurant = (
        get_restaurant(
            restaurant_id
        )
    )


    if not restaurant:

        abort(
            404
        )


    profile_url = (
        restaurant.get(
            "profile_url"
        )
    )


    if not profile_url:

        abort(
            404
        )


    # ========================================================
    # ANONYMOUS STORIES SESSION
    # ========================================================

    analytics_session_id = (
        get_analytics_session_id()
    )


    # ========================================================
    # RECORD STORIES RESTAURANT CLICK
    # ========================================================

    record_analytics_event(
        article=(
            article
        ),

        event_type=(
            "restaurant_click"
        ),

        restaurant_id=(
            restaurant_id
        ),

        metadata={
            "source":
                "article_restaurant_card",

            "destination":
                "kalxa_ticketing",
        },

        deduplicate=False,
    )


    # ========================================================
    # BUILD SIGNED TICKETING URL
    # ========================================================
    #
    # Example:
    #
    # https://tickets.kalxa.co.za/restaurant/2
    #     ?kat=<SIGNED_TOKEN>
    #
    # Kalxa Ticketing verifies this token using the same
    # KALXA_ATTRIBUTION_SECRET.
    # ========================================================

    attributed_url = (
        build_attributed_ticketing_url(
            profile_url=(
                profile_url
            ),

            article=(
                article
            ),

            restaurant_id=(
                restaurant_id
            ),

            analytics_session_id=(
                analytics_session_id
            ),
        )
    )


    if not attributed_url:

        abort(
            404
        )


    # ========================================================
    # REDIRECT TO KALXA TICKETING
    # ========================================================

    return redirect(
        attributed_url
    )


# ============================================================
# HEALTH
# ============================================================

@public_bp.route(
    "/health"
)
def health():

    return {
        "status":
            "ok",

        "service":
            "kalxa-stories",
    }, 200
