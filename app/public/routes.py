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
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from itsdangerous import (
    URLSafeTimedSerializer,
)

from sqlalchemy import (
    or_,
)

from app.extensions import db

from app.models import (
    Article,
    StoryAnalyticsEvent,
)

from app.models.article_comment import (
    ArticleComment,
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
# KALXA CROSS-APP ATTRIBUTION
# ============================================================

KALXA_ATTRIBUTION_SALT = (
    "kalxa-restaurant-attribution"
)


# ============================================================
# ACTIVE PUBLISHED STORY FILTER
# ============================================================

def active_published_article_query():
    """
    Return published stories that have not expired.

    Expired published stories remain accessible through their
    permanent article URL, but they are removed from active
    discovery feeds.
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
# ANONYMOUS ANALYTICS SESSION
# ============================================================

def get_analytics_session_id():

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
# ANONYMOUS COMMENT SESSION
# ============================================================

def get_anonymous_session_id():

    session_id = (
        session.get(
            "kalxa_story_session_id"
        )
    )

    if not session_id:

        session_id = (
            uuid4().hex
        )

        session[
            "kalxa_story_session_id"
        ] = session_id

        session.modified = True

    return session_id


# ============================================================
# CHECK RECENT ANALYTICS EVENT
# ============================================================

def recent_event_exists(
    article_id,
    event_type,
    session_id,
    restaurant_id=None,
):

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

    session_id = (
        get_analytics_session_id()
    )

    if (
        deduplicate
        and
        recent_event_exists(
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
        kalxa_restaurant_id=restaurant_id,
        session_id=session_id,
        referrer=request.referrer,
        event_metadata=(
            metadata
            or
            {}
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

    serializer = (
        URLSafeTimedSerializer(
            secret,
            salt=(
                KALXA_ATTRIBUTION_SALT
            ),
        )
    )

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

    if not profile_url:

        return None

    token = (
        build_attribution_token(
            article=article,
            restaurant_id=restaurant_id,
            analytics_session_id=(
                analytics_session_id
            ),
        )
    )

    if not token:

        return profile_url

    try:

        parsed_url = (
            urlsplit(
                profile_url
            )
        )

        existing_query = dict(
            parse_qsl(
                parsed_url.query,
                keep_blank_values=True,
            )
        )

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

        existing_query[
            "kat"
        ] = token

        updated_query = (
            urlencode(
                existing_query
            )
        )

        return urlunsplit(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                updated_query,
                parsed_url.fragment,
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
        active_published_article_query()

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
        if len(articles) > 1
        else []
    )

    return render_template(
        "home.html",
        featured_article=featured_article,
        articles=remaining_articles,
    )


# ============================================================
# ALL ACTIVE STORIES
# ============================================================

@public_bp.route(
    "/stories"
)
def stories():

    articles = (
        active_published_article_query()

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
# SUBMIT ARTICLE COMMENT
# ============================================================

@public_bp.post(
    "/stories/<string:slug>/comment"
)
def article_comment(
    slug,
):

    article = (
        Article.query

        .filter_by(
            slug=slug,
            status="published",
        )

        .first_or_404()
    )

    # ========================================================
    # COMMENTS CLOSED / STORY EXPIRED
    # ========================================================

    if not article.comments_open:

        flash(
            (
                "Comments are closed for this story."
            ),
            "info",
        )

        return redirect(
            url_for(
                "public.article_detail",
                slug=article.slug,
            )
            +
            "#comments"
        )

    # ========================================================
    # FORM DATA
    # ========================================================

    display_name = (
        request.form
        .get(
            "display_name",
            "",
        )
        .strip()
    )

    comment_text = (
        request.form
        .get(
            "comment_text",
            "",
        )
        .strip()
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    if not display_name:

        flash(
            "Please enter your name.",
            "error",
        )

        return redirect(
            url_for(
                "public.article_detail",
                slug=article.slug,
            )
            +
            "#comments"
        )

    if len(display_name) > 80:

        flash(
            "Your name is too long.",
            "error",
        )

        return redirect(
            url_for(
                "public.article_detail",
                slug=article.slug,
            )
            +
            "#comments"
        )

    if not comment_text:

        flash(
            "Please write a comment.",
            "error",
        )

        return redirect(
            url_for(
                "public.article_detail",
                slug=article.slug,
            )
            +
            "#comments"
        )

    if len(comment_text) > 1000:

        flash(
            (
                "Comments cannot exceed "
                "1000 characters."
            ),
            "error",
        )

        return redirect(
            url_for(
                "public.article_detail",
                slug=article.slug,
            )
            +
            "#comments"
        )

    # ========================================================
    # CREATE PENDING COMMENT
    # ========================================================

    comment = ArticleComment(
        article_id=article.id,
        display_name=display_name,
        comment_text=comment_text,
        anonymous_session_id=(
            get_anonymous_session_id()
        ),
        moderation_status="pending",
        active=True,
    )

    try:

        db.session.add(
            comment
        )

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to save Kalxa Stories comment."
        )

        flash(
            (
                "Your comment could not be submitted. "
                "Please try again."
            ),
            "error",
        )

        return redirect(
            url_for(
                "public.article_detail",
                slug=article.slug,
            )
            +
            "#comments"
        )

    flash(
        (
            "Your comment was submitted "
            "and will appear after review."
        ),
        "success",
    )

    return redirect(
        url_for(
            "public.article_detail",
            slug=article.slug,
        )
        +
        "#comments"
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

    # ========================================================
    # ARTICLE
    # ========================================================
    #
    # IMPORTANT:
    #
    # Expired published stories remain accessible.
    #
    # This preserves their permanent URL for readers and
    # search engines.
    # ========================================================

    article = (
        Article.query

        .filter_by(
            slug=slug,
            status="published",
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
        article=article,
        event_type="article_view",
        metadata={
            "source":
                "article_page",
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
            restaurant_id=restaurant_id,
            metadata={
                "position":
                    position,

                "source":
                    "article_restaurant_card",
            },
        )

    # ========================================================
    # APPROVED COMMENTS
    # ========================================================

    approved_comments = []

    if not article.is_expired:

        approved_comments = (
            ArticleComment.query

            .filter_by(
                article_id=article.id,
                moderation_status="approved",
                active=True,
            )

            .order_by(
                ArticleComment
                .created_at
                .desc()
            )

            .all()
        )

    # ========================================================
    # RELATED ACTIVE STORIES
    # ========================================================

    related_articles = (
        active_published_article_query()

        .filter(
            Article.id
            != article.id
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
        article=article,
        featured_restaurants=(
            featured_restaurants
        ),
        reading_minutes=(
            reading_minutes
        ),
        related_articles=(
            related_articles
        ),
        approved_comments=(
            approved_comments
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

    analytics_session_id = (
        get_analytics_session_id()
    )

    record_analytics_event(
        article=article,
        event_type="restaurant_click",
        restaurant_id=restaurant_id,
        metadata={
            "source":
                "article_restaurant_card",

            "destination":
                "kalxa_ticketing",
        },
        deduplicate=False,
    )

    attributed_url = (
        build_attributed_ticketing_url(
            profile_url=profile_url,
            article=article,
            restaurant_id=restaurant_id,
            analytics_session_id=(
                analytics_session_id
            ),
        )
    )

    if not attributed_url:

        abort(
            404
        )

    return redirect(
        attributed_url
    )


# ============================================================
# SITEMAP
# ============================================================

@public_bp.route(
    "/sitemap.xml"
)
def sitemap():

    articles = (
        Article.query

        .filter(
            Article.status
            == "published"
        )

        .order_by(
            Article.updated_at.desc(),
            Article.id.desc(),
        )

        .all()
    )

    urls = []

    urls.append({
        "location":
            url_for(
                "public.home",
                _external=True,
            ),

        "last_modified":
            None,
    })

    urls.append({
        "location":
            url_for(
                "public.stories",
                _external=True,
            ),

        "last_modified":
            None,
    })

    for article in articles:

        last_modified = (
            article.updated_at
            or
            article.published_at
            or
            article.created_at
        )

        urls.append({
            "location":
                url_for(
                    "public.article_detail",
                    slug=article.slug,
                    _external=True,
                ),

            "last_modified":
                last_modified,
        })

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<urlset '
            'xmlns="http://www.sitemaps.org/'
            'schemas/sitemap/0.9">'
        ),
    ]

    for item in urls:

        xml_parts.append(
            "<url>"
        )

        xml_parts.append(
            "<loc>"
            +
            item["location"]
            .replace(
                "&",
                "&amp;",
            )
            +
            "</loc>"
        )

        if item["last_modified"]:

            last_modified = (
                item[
                    "last_modified"
                ]
            )

            if (
                last_modified.tzinfo
                is None
            ):

                last_modified = (
                    last_modified.replace(
                        tzinfo=timezone.utc
                    )
                )

            xml_parts.append(
                "<lastmod>"
                +
                last_modified
                .date()
                .isoformat()
                +
                "</lastmod>"
            )

        xml_parts.append(
            "</url>"
        )

    xml_parts.append(
        "</urlset>"
    )

    return Response(
        "\n".join(
            xml_parts
        ),
        mimetype="application/xml",
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
