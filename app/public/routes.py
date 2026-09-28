from datetime import (
    datetime,
    timedelta,
    timezone,
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
)
from app.extensions import db

from app.models import (
    Article,
    StoryAnalyticsEvent,
)

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
# ANONYMOUS ANALYTICS SESSION
# ============================================================

def get_analytics_session_id():
    """
    Return an anonymous browser/session identifier.

    No name, email address, phone number or Kalxa account
    information is required.

    Flask stores this identifier inside the visitor's
    signed session cookie.
    """

    session_id = session.get(
        ANALYTICS_SESSION_KEY
    )

    if not session_id:

        session_id = uuid4().hex

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
        datetime.now(timezone.utc)
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

        query = query.filter(
            StoryAnalyticsEvent
            .kalxa_restaurant_id
            .is_(None)
        )

    else:

        query = query.filter(
            StoryAnalyticsEvent
            .kalxa_restaurant_id
            == restaurant_id
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

    Analytics should never prevent the visitor from
    reading a story or opening a restaurant.
    """

    session_id = (
        get_analytics_session_id()
    )

    if (
        deduplicate
        and recent_event_exists(
            article_id=article.id,
            event_type=event_type,
            session_id=session_id,
            restaurant_id=restaurant_id,
        )
    ):

        return False

    event = StoryAnalyticsEvent(
        article_id=article.id,
        event_type=event_type,
        kalxa_restaurant_id=(
            restaurant_id
        ),
        session_id=session_id,
        referrer=(
            request.referrer
            if request
            else None
        ),
        event_metadata=(
            metadata or {}
        ),
    )

    try:

        db.session.add(
            event
        )

        db.session.commit()

        return True

    except Exception:

        db.session.rollback()

        public_bp.logger.exception(
            "Unable to record Kalxa Stories "
            "analytics event."
        )

        return False


# ============================================================
# HOME
# ============================================================

@public_bp.route("/")
def home():

    articles = (
        Article.query
        .filter_by(
            status="published"
        )
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
        featured_article=(
            featured_article
        ),
        articles=remaining_articles,
    )


# ============================================================
# ALL STORIES
# ============================================================

@public_bp.route("/stories")
def stories():

    articles = (
        Article.query
        .filter_by(
            status="published"
        )
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
    # ARTICLE VIEW
    # ========================================================

    record_analytics_event(
        article=article,
        event_type="article_view",
        metadata={
            "source": "article_page",
        },
    )


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
    # RESTAURANT IMPRESSIONS
    # ========================================================
    #
    # At this stage an impression means that the restaurant
    # card was included on the rendered article page.
    #
    # Later, JavaScript/IntersectionObserver can make this
    # stricter by recording only cards actually visible in
    # the visitor's viewport.
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
            article=article,
            event_type=(
                "restaurant_impression"
            ),
            restaurant_id=(
                restaurant_id
            ),
            metadata={
                "position": position,
                "source": (
                    "article_restaurant_card"
                ),
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
        .limit(3)
        .all()
    )


    return render_template(
        "article.html",
        article=article,
        featured_restaurants=(
            featured_restaurants
        ),
        related_articles=(
            related_articles
        ),
    )


# ============================================================
# TRACK RESTAURANT CLICK
# ============================================================

@public_bp.route(
    (
        "/stories/<string:slug>"
        "/restaurants/<int:restaurant_id>"
    )
)
def restaurant_click(
    slug,
    restaurant_id,
):
    """
    Record a restaurant click and then redirect the visitor
    to the restaurant's Kalxa Ticketing page.
    """

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
    # VERIFY RESTAURANT BELONGS TO ARTICLE
    # ========================================================

    restaurant_ids = {

        relation.kalxa_restaurant_id

        for relation
        in article.restaurants

    }

    if restaurant_id not in restaurant_ids:

        abort(404)


    # ========================================================
    # GET LIVE RESTAURANT DATA
    # ========================================================

    restaurant = get_restaurant(
        restaurant_id
    )

    if restaurant is None:

        abort(404)


    profile_url = restaurant.get(
        "profile_url"
    )

    if not profile_url:

        abort(404)


    # ========================================================
    # RECORD CLICK
    # ========================================================

    record_analytics_event(
        article=article,
        event_type="restaurant_click",
        restaurant_id=restaurant_id,
        metadata={
            "source": (
                "article_restaurant_card"
            ),
        },

        # A visitor intentionally clicking a restaurant
        # several times can represent several genuine
        # actions, so clicks are not deduplicated.
        deduplicate=False,
    )


    # ========================================================
    # REDIRECT TO KALXA TICKETING
    # ========================================================

    return redirect(
        profile_url,
        code=302,
    )


# ============================================================
# HEALTH
# ============================================================

@public_bp.route(
    "/health"
)
def health():

    return {
        "status": "ok",
        "service": "kalxa-stories",
    }, 200
