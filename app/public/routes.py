from datetime import datetime, timedelta, timezone
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)
from uuid import uuid4
import secrets

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from itsdangerous import URLSafeTimedSerializer
from markupsafe import escape

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db

from app.models import (
    Article,
    StoryAnalyticsEvent,
)

from app.models.article_comment import (
    ArticleComment,
    CommentUpvote,
)

from app.models.story_category import (
    StoryCategory,
    TRENDING_NOW_CATEGORY_SLUG,
)

from app.models.story_reaction import StoryReaction

from app.kalxa.client import (
    get_restaurants_by_ids,
)


# ============================================================
# PUBLIC BLUEPRINT
# ============================================================

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
# ATTRIBUTION SETTINGS
# ============================================================

KALXA_ATTRIBUTION_SALT = (
    "kalxa-restaurant-attribution"
)


# ============================================================
# STORY REACTION SETTINGS
# ============================================================

STORY_REACTION_CSRF_KEY = (
    "kalxa_story_reaction_csrf"
)


# ============================================================
# ACTIVE PUBLISHED ARTICLES
# ============================================================

def active_published_article_query():
    """
    Return published articles that have not expired.

    Rules:

    - Published, permanent articles remain visible.
    - Published articles with future expiry remain visible.
    - Expired articles disappear from active discovery feeds.
    - Expired published articles retain their original URLs.

    This query is shared by the homepage, category pages,
    related articles and general story listings.
    """

    now = datetime.now(timezone.utc)

    return (
        Article.query
        .filter(
            Article.status == "published",

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
# ANONYMOUS COMMENT / REACTION SESSION
# ============================================================

def get_anonymous_session_id():

    session_id = session.get(
        "kalxa_story_session_id"
    )

    if not session_id:

        session_id = uuid4().hex

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
        datetime.now(timezone.utc)
        - timedelta(
            minutes=ANALYTICS_DEDUPLICATION_MINUTES
        )
    )

    query = (
        StoryAnalyticsEvent.query
        .filter(
            StoryAnalyticsEvent.article_id == article_id,
            StoryAnalyticsEvent.event_type == event_type,
            StoryAnalyticsEvent.session_id == session_id,
            StoryAnalyticsEvent.created_at >= cutoff,
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
            StoryAnalyticsEvent.kalxa_restaurant_id
            == restaurant_id
        )

    return query.first() is not None


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

    session_id = get_analytics_session_id()

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
        kalxa_restaurant_id=restaurant_id,
        session_id=session_id,
        referrer=request.referrer,
        event_metadata=metadata or {},
    )

    try:

        db.session.add(event)
        db.session.commit()

        return True

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to record Kalxa Stories analytics event."
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
        current_app.config.get(
            "KALXA_ATTRIBUTION_SECRET",
            "",
        )
        or ""
    )

    secret = str(secret).strip()

    if not secret:

        current_app.logger.error(
            "KALXA_ATTRIBUTION_SECRET is not configured."
        )

        return None

    serializer = URLSafeTimedSerializer(
        secret,
        salt=KALXA_ATTRIBUTION_SALT,
    )

    payload = {
        "source": "kalxa_stories",
        "story_id": article.id,
        "restaurant_id": restaurant_id,
        "source_session_id": analytics_session_id,
    }

    try:

        return serializer.dumps(payload)

    except Exception:

        current_app.logger.exception(
            "Unable to create Kalxa Stories attribution token."
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

    token = build_attribution_token(
        article=article,
        restaurant_id=restaurant_id,
        analytics_session_id=analytics_session_id,
    )

    if not token:
        return profile_url

    try:

        parsed_url = urlsplit(profile_url)

        existing_query = dict(
            parse_qsl(
                parsed_url.query,
                keep_blank_values=True,
            )
        )

        # Remove legacy/raw attribution parameters.

        existing_query.pop("source", None)
        existing_query.pop("article_id", None)
        existing_query.pop("restaurant_id", None)
        existing_query.pop("source_session", None)

        # Send signed attribution token.

        existing_query["kat"] = token

        updated_query = urlencode(
            existing_query
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
            "Unable to build signed Kalxa Ticketing URL."
        )

        return profile_url


# ============================================================
# TRENDING NOW CATEGORY
# ============================================================

def get_trending_now_category():
    """
    Retrieve the special administrator-controlled category.

    The category must exist and be active.

    Its slug is:
        trending-now
    """

    return (
        StoryCategory.query
        .filter_by(
            slug=TRENDING_NOW_CATEGORY_SLUG,
            is_active=True,
        )
        .first()
    )


# ============================================================
# CURATED TRENDING STORIES
# ============================================================

def kalxa_trending_articles(limit=6):
    """
    Return articles eligible for the homepage Trending Stories.

    Priority:

        1. Active paid featured placements.
        2. Administrator-published Trending Now articles.
        3. Existing restaurant-linked stories.

    All candidates must be published and not expired.

    IMPORTANT:

    - Permanent paid publication is separate from temporary
      featured placement.

    - A paid story is not automatically featured forever.

    - Restaurant-linked stories retain their existing
      eligibility behavior.

    - Restaurant links alone do not prove that a restaurant
      currently has a valid Premium subscription.

    - Trending Now is curated by the administrator, not
      ranked by anonymous views or likes.

    - Expiry is enforced by the active published query.

    No background job is required.
    """

    from app.models.article_restaurant import (
        ArticleRestaurant,
    )

    from app.paid.models import (
        PaidStoryPublication,
    )

    now = datetime.now(
        timezone.utc
    )

    # ========================================================
    # ACTIVE TRENDING NOW CATEGORY
    # ========================================================

    trending_category = get_trending_now_category()

    trending_category_id = (
        trending_category.id
        if trending_category is not None
        else None
    )

    # ========================================================
    # RESTAURANT-LINKED ARTICLE IDS
    # ========================================================

    restaurant_article_ids = {
        row[0]

        for row in (
            db.session.query(
                ArticleRestaurant.article_id
            )
            .distinct()
            .all()
        )
    }

    # ========================================================
    # ACTIVE PAID FEATURED PLACEMENTS
    # ========================================================

    featured_article_ids = set()

    starts_at = getattr(
        PaidStoryPublication,
        "starts_at",
        None,
    )

    featured_until = getattr(
        PaidStoryPublication,
        "featured_until",
        None,
    )

    # A permanent paid article is not automatically featured.
    # There must be a supported featured_until field.

    if featured_until is not None:

        featured_query = db.session.query(
            PaidStoryPublication.article_id
        )

        if starts_at is not None:

            featured_query = featured_query.filter(
                starts_at <= now
            )

        featured_query = featured_query.filter(
            featured_until > now
        )

        featured_article_ids = {
            row[0]
            for row in featured_query.all()
        }

    # ========================================================
    # ELIGIBILITY CONDITIONS
    # ========================================================

    eligibility_conditions = []

    # --------------------------------------------------------
    # EXISTING RESTAURANT-LINKED ARTICLES
    # --------------------------------------------------------

    if restaurant_article_ids:

        eligibility_conditions.append(
            Article.id.in_(
                restaurant_article_ids
            )
        )

    # --------------------------------------------------------
    # PAID FEATURED ARTICLES
    # --------------------------------------------------------

    if featured_article_ids:

        eligibility_conditions.append(
            Article.id.in_(
                featured_article_ids
            )
        )

    # --------------------------------------------------------
    # NEW: TRENDING NOW ARTICLES
    # --------------------------------------------------------

    if trending_category_id is not None:

        # Trending Now articles must have an expiry date.
        # This prevents a mistakenly configured permanent
        # article from remaining in Trending Now forever.

        eligibility_conditions.append(
            (
                (Article.category_id == trending_category_id)
                & Article.expires_at.isnot(None)
                & (Article.expires_at > now)
            )
        )

    if not eligibility_conditions:
        return []

    # ========================================================
    # CANDIDATES
    # ========================================================

    candidates = (
        active_published_article_query()
        .filter(
            or_(
                *eligibility_conditions
            )
        )
        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )
        .limit(100)
        .all()
    )

    # ========================================================
    # PRIORITY CLASSIFICATION
    # ========================================================

    def trending_priority(article):

        # Paid featured placements have first priority.

        if article.id in featured_article_ids:
            return 0

        # Admin Trending Now stories follow.

        if (
            trending_category_id is not None
            and article.category_id == trending_category_id
            and article.expires_at is not None
        ):
            return 1

        # Existing restaurant-linked articles follow.

        return 2

    # Python sorting is stable.
    #
    # Within each priority group, the original database
    # ordering (newest first) remains preserved.

    candidates.sort(
        key=trending_priority
    )

    return candidates[:limit]


# ============================================================
# STORY REACTIONS — CSRF TOKEN
# ============================================================

def story_reaction_csrf_token():

    token = session.get(
        STORY_REACTION_CSRF_KEY
    )

    if not token:

        token = secrets.token_urlsafe(32)

        session[
            STORY_REACTION_CSRF_KEY
        ] = token

        session.modified = True

    return token


# ============================================================
# STORY ENGAGEMENT COUNTS
# ============================================================

def get_story_engagement(article_id):

    view_count = (
        StoryAnalyticsEvent.query
        .filter(
            StoryAnalyticsEvent.article_id == article_id,
            StoryAnalyticsEvent.event_type == "article_view",
            StoryAnalyticsEvent.kalxa_restaurant_id.is_(None),
        )
        .count()
    )

    like_count = (
        StoryReaction.query
        .filter_by(
            article_id=article_id,
            reaction_type="like",
        )
        .count()
    )

    return {
        "view_count": view_count,
        "like_count": like_count,
    }


# ============================================================
# CURRENT VISITOR LIKED STATE
# ============================================================

def visitor_liked_story(article_id):

    anonymous_session_id = (
        get_anonymous_session_id()
    )

    return (
        StoryReaction.query
        .filter_by(
            article_id=article_id,
            anonymous_session_id=anonymous_session_id,
            reaction_type="like",
        )
        .first()
        is not None
    )


# ============================================================
# TOGGLE STORY LIKE
# ============================================================

@public_bp.post(
    "/stories/<string:slug>/like"
)
def toggle_story_like(slug):

    # ========================================================
    # REQUEST SIZE
    # ========================================================

    if (
        request.content_length
        and request.content_length > 10000
    ):

        abort(413)

    # ========================================================
    # CSRF VALIDATION
    # ========================================================

    submitted_token = request.headers.get(
        "X-CSRF-Token",
        "",
    )

    expected_token = session.get(
        STORY_REACTION_CSRF_KEY,
        "",
    )

    if (
        not expected_token
        or not secrets.compare_digest(
            submitted_token,
            expected_token,
        )
    ):

        return jsonify({
            "ok": False,
            "error": "invalid_csrf",
            "message": (
                "Please refresh the page and try again."
            ),
        }), 400

    # ========================================================
    # PUBLISHED ARTICLE
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

        return jsonify({
            "ok": False,
            "error": "story_not_found",
        }), 404

    # ========================================================
    # ANONYMOUS SESSION
    # ========================================================

    anonymous_session_id = (
        get_anonymous_session_id()
    )

    # ========================================================
    # EXISTING REACTION
    # ========================================================

    existing_reaction = (
        StoryReaction.query
        .filter_by(
            article_id=article.id,
            anonymous_session_id=anonymous_session_id,
        )
        .first()
    )

    # ========================================================
    # REMOVE LIKE
    # ========================================================

    if existing_reaction is not None:

        try:

            db.session.delete(
                existing_reaction
            )

            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                "Unable to remove story like."
            )

            return jsonify({
                "ok": False,
                "error": "like_remove_failed",
            }), 500

        engagement = get_story_engagement(
            article.id
        )

        return jsonify({
            "ok": True,
            "article_id": article.id,
            "liked": False,
            **engagement,
        }), 200

    # ========================================================
    # ADD LIKE
    # ========================================================

    reaction = StoryReaction(
        article_id=article.id,
        anonymous_session_id=anonymous_session_id,
        reaction_type="like",
    )

    try:

        db.session.add(
            reaction
        )

        db.session.commit()

    except IntegrityError:

        # Concurrent duplicate likes are resolved by
        # reading the current database state.

        db.session.rollback()

        engagement = get_story_engagement(
            article.id
        )

        return jsonify({
            "ok": True,
            "article_id": article.id,
            "liked": visitor_liked_story(article.id),
            **engagement,
        }), 200

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to create story like."
        )

        return jsonify({
            "ok": False,
            "error": "like_save_failed",
        }), 500

    # ========================================================
    # SUCCESS
    # ========================================================

    engagement = get_story_engagement(
        article.id
    )

    return jsonify({
        "ok": True,
        "article_id": article.id,
        "liked": True,
        **engagement,
    }), 200


# ============================================================
# GET STORY ENGAGEMENT
# ============================================================

@public_bp.get(
    "/stories/<string:slug>/engagement"
)
def story_engagement(slug):

    article = (
        Article.query
        .filter_by(
            slug=slug,
            status="published",
        )
        .first_or_404()
    )

    engagement = get_story_engagement(
        article.id
    )

    return jsonify({
        "ok": True,
        "article_id": article.id,
        "liked": visitor_liked_story(article.id),
        **engagement,
    }), 200


# ============================================================
# HOME PAGE
# ============================================================

@public_bp.route("/")
def home():

    articles = (
        active_published_article_query()
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

    trending_articles = kalxa_trending_articles(
        limit=6
    )

    return render_template(
        "home.html",

        featured_article=featured_article,

        trending_articles=trending_articles,

        articles=remaining_articles,
    )


# ============================================================
# ALL ACTIVE STORIES
# ============================================================

@public_bp.route("/stories")
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
# STORY CATEGORY PAGE
# ============================================================

@public_bp.route(
    "/stories/category/<string:category_slug>"
)
def story_category(category_slug):

    category = (
        StoryCategory.query
        .filter_by(
            slug=category_slug,
            is_active=True,
        )
        .first_or_404()
    )

    articles = (
        active_published_article_query()
        .filter(
            Article.category_id == category.id
        )
        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )
        .all()
    )

    # Trending Now must never show permanent articles.
    # The admin form enforces expiry when publishing,
    # and this adds protection for old/manual records.

    if category.slug == TRENDING_NOW_CATEGORY_SLUG:

        articles = [
            article
            for article in articles
            if article.expires_at is not None
        ]

    return render_template(
        "category.html",
        category=category,
        articles=articles,
    )


# ============================================================
# SUBMIT ARTICLE COMMENT
# ============================================================

@public_bp.post(
    "/stories/<string:slug>/comment"
)
def article_comment(slug):

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
            "Comments are closed for this story.",
            "info",
        )

        return redirect(
            url_for(
                "public.article_detail",
                slug=article.slug,
            )
            + "#comments"
        )

    # ========================================================
    # FORM DATA
    # ========================================================

    display_name = (
        request.form.get(
            "display_name",
            "",
        ).strip()
    )

    comment_text = (
        request.form.get(
            "comment_text",
            "",
        ).strip()
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
            + "#comments"
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
            + "#comments"
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
            + "#comments"
        )

    if len(comment_text) > 1000:

        flash(
            "Comments cannot exceed 1000 characters.",
            "error",
        )

        return redirect(
            url_for(
                "public.article_detail",
                slug=article.slug,
            )
            + "#comments"
        )

    # ========================================================
    # CREATE PENDING COMMENT
    # ========================================================

    comment = ArticleComment(
        article_id=article.id,
        display_name=display_name,
        comment_text=comment_text,
        anonymous_session_id=get_anonymous_session_id(),
        moderation_status="pending",
        active=True,
    )

    try:

        db.session.add(comment)
        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to save Kalxa Stories comment."
        )

        flash(
            "Your comment could not be submitted. "
            "Please try again.",
            "error",
        )

        return redirect(
            url_for(
                "public.article_detail",
                slug=article.slug,
            )
            + "#comments"
        )

    flash(
        "Your comment was submitted "
        "and will appear after review.",
        "success",
    )

    return redirect(
        url_for(
            "public.article_detail",
            slug=article.slug,
        )
        + "#comments"
    )


# ============================================================
# TOGGLE COMMENT UPVOTE
# ============================================================

@public_bp.post(
    "/stories/<string:slug>/comments/<int:comment_id>/upvote"
)
def toggle_comment_upvote(
    slug,
    comment_id,
):

    article = (
        Article.query
        .filter_by(
            slug=slug,
            status="published",
        )
        .first()
    )

    if article is None:

        return jsonify({
            "ok": False,
            "error": "story_not_found",
        }), 404

    # ========================================================
    # COMMENTS MUST BE OPEN
    # ========================================================

    if not article.comments_open:

        return jsonify({
            "ok": False,
            "error": "comments_closed",
            "message": "Upvotes are closed for this story.",
        }), 403

    # ========================================================
    # APPROVED ACTIVE COMMENT
    # ========================================================

    comment = (
        ArticleComment.query
        .filter(
            ArticleComment.id == comment_id,
            ArticleComment.article_id == article.id,
            ArticleComment.moderation_status == "approved",
            ArticleComment.active.is_(True),
        )
        .first()
    )

    if comment is None:

        return jsonify({
            "ok": False,
            "error": "comment_not_found",
        }), 404

    # ========================================================
    # ANONYMOUS VISITOR
    # ========================================================

    anonymous_session_id = (
        get_anonymous_session_id()
    )

    existing_upvote = (
        CommentUpvote.query
        .filter_by(
            comment_id=comment.id,
            anonymous_session_id=anonymous_session_id,
        )
        .first()
    )

    # ========================================================
    # REMOVE UPVOTE
    # ========================================================

    if existing_upvote is not None:

        try:

            db.session.delete(existing_upvote)
            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                "Unable to remove Kalxa Stories comment upvote."
            )

            return jsonify({
                "ok": False,
                "error": "upvote_remove_failed",
            }), 500

        upvote_count = (
            CommentUpvote.query
            .filter_by(
                comment_id=comment.id
            )
            .count()
        )

        return jsonify({
            "ok": True,
            "comment_id": comment.id,
            "upvoted": False,
            "upvote_count": upvote_count,
        }), 200

    # ========================================================
    # ADD UPVOTE
    # ========================================================

    upvote = CommentUpvote(
        comment_id=comment.id,
        anonymous_session_id=anonymous_session_id,
    )

    try:

        db.session.add(upvote)
        db.session.commit()

    except IntegrityError:

        db.session.rollback()

        upvote_count = (
            CommentUpvote.query
            .filter_by(
                comment_id=comment.id
            )
            .count()
        )

        return jsonify({
            "ok": True,
            "comment_id": comment.id,
            "upvoted": True,
            "upvote_count": upvote_count,
        }), 200

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to save Kalxa Stories comment upvote."
        )

        return jsonify({
            "ok": False,
            "error": "upvote_save_failed",
        }), 500

    # ========================================================
    # SUCCESS
    # ========================================================

    upvote_count = (
        CommentUpvote.query
        .filter_by(
            comment_id=comment.id
        )
        .count()
    )

    return jsonify({
        "ok": True,
        "comment_id": comment.id,
        "upvoted": True,
        "upvote_count": upvote_count,
    }), 200


# ============================================================
# ARTICLE DETAIL
# ============================================================

@public_bp.route(
    "/stories/<string:slug>"
)
def article_detail(slug):

    # ========================================================
    # ARTICLE
    # ========================================================
    #
    # Published expired stories remain accessible through
    # their permanent URL.
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
    # ENGAGEMENT COUNTS
    # ========================================================

    engagement = get_story_engagement(
        article.id
    )

    story_view_count = engagement[
        "view_count"
    ]

    story_like_count = engagement[
        "like_count"
    ]

    story_is_liked = visitor_liked_story(
        article.id
    )

    reaction_csrf_token = (
        story_reaction_csrf_token()
    )

    # ========================================================
    # LINKED KALXA RESTAURANTS
    # ========================================================

    relations = sorted(
        article.restaurants,

        key=lambda relation: (
            relation.display_order
            if relation.display_order is not None
            else 999999
        ),
    )

    restaurant_ids = [
        relation.kalxa_restaurant_id

        for relation in relations

        if relation.kalxa_restaurant_id is not None
    ]

    # ========================================================
    # LIVE TICKETING LOOKUP
    # ========================================================

    live_restaurants = []

    if restaurant_ids:

        try:

            live_restaurants = (
                get_restaurants_by_ids(
                    restaurant_ids
                )
                or []
            )

        except Exception as error:

            current_app.logger.exception(
                "[Kalxa Stories] Unable to load "
                "linked restaurants for "
                "article_id=%s: %s",
                article.id,
                error,
            )

            live_restaurants = []

    # ========================================================
    # INDEX LIVE RESTAURANTS
    # ========================================================

    live_restaurants_by_id = {}

    for restaurant in live_restaurants:

        if not isinstance(restaurant, dict):
            continue

        restaurant_id = restaurant.get(
            "id"
        )

        if restaurant_id is None:
            continue

        try:

            restaurant_id = int(
                restaurant_id
            )

        except (TypeError, ValueError):
            continue

        live_restaurants_by_id[
            restaurant_id
        ] = restaurant

    # ========================================================
    # BUILD RESTAURANT CARDS
    # ========================================================

    featured_restaurants = []

    for relation in relations:

        restaurant_id = (
            relation.kalxa_restaurant_id
        )

        if restaurant_id is None:
            continue

        try:

            normalized_restaurant_id = int(
                restaurant_id
            )

        except (TypeError, ValueError):
            continue

        live_restaurant = (
            live_restaurants_by_id.get(
                normalized_restaurant_id
            )
        )

        # ----------------------------------------------------
        # FALLBACK DATA
        # ----------------------------------------------------

        restaurant = {

            "id": normalized_restaurant_id,

            "business_name": getattr(
                relation,
                "restaurant_name",
                None,
            ),

            "name": getattr(
                relation,
                "restaurant_name",
                None,
            ),

            "area": getattr(
                relation,
                "restaurant_area",
                None,
            ),

            "address": None,

            "headline": None,

            "price_text": None,

            "profile_url": None,
        }

        # ----------------------------------------------------
        # ENRICH WITH LIVE DATA
        # ----------------------------------------------------

        if live_restaurant:

            restaurant.update(
                live_restaurant
            )

            restaurant["id"] = (
                normalized_restaurant_id
            )

            if not restaurant.get(
                "business_name"
            ):

                restaurant["business_name"] = getattr(
                    relation,
                    "restaurant_name",
                    None,
                )

            if not restaurant.get(
                "name"
            ):

                restaurant["name"] = getattr(
                    relation,
                    "restaurant_name",
                    None,
                )

            if not restaurant.get(
                "area"
            ):

                restaurant["area"] = getattr(
                    relation,
                    "restaurant_area",
                    None,
                )

        featured_restaurants.append(
            restaurant
        )

    # ========================================================
    # RESTAURANT IMPRESSIONS
    # ========================================================

    for position, restaurant in enumerate(
        featured_restaurants,
        start=1,
    ):

        restaurant_id = restaurant.get(
            "id"
        )

        if restaurant_id is None:
            continue

        record_analytics_event(
            article=article,
            event_type="restaurant_impression",
            restaurant_id=restaurant_id,
            metadata={
                "position": position,
                "source": "article_restaurant_card",
            },
        )

    # ========================================================
    # APPROVED COMMENTS
    # ========================================================

    approved_comments = []

    comment_upvote_state = {}

    if not article.is_expired:

        approved_comments = (
            ArticleComment.query
            .filter_by(
                article_id=article.id,
                moderation_status="approved",
                active=True,
            )
            .order_by(
                ArticleComment.created_at.desc()
            )
            .all()
        )

        if approved_comments:

            anonymous_session_id = (
                get_anonymous_session_id()
            )

            comment_ids = [
                comment.id
                for comment in approved_comments
            ]

            visitor_upvotes = (
                CommentUpvote.query
                .filter(
                    CommentUpvote.comment_id.in_(
                        comment_ids
                    ),

                    CommentUpvote.anonymous_session_id
                    == anonymous_session_id,
                )
                .all()
            )

            visitor_upvoted_comment_ids = {
                upvote.comment_id
                for upvote in visitor_upvotes
            }

            comment_upvote_state = {
                comment.id: (
                    comment.id
                    in visitor_upvoted_comment_ids
                )

                for comment in approved_comments
            }

    # ========================================================
    # RELATED ACTIVE STORIES
    # ========================================================

    related_articles = (
        active_published_article_query()
        .filter(
            Article.id != article.id
        )
        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )
        .limit(3)
        .all()
    )

    # ========================================================
    # READING TIME
    # ========================================================

    plain_body = article.body.replace(
        "<",
        " <",
    )

    word_count = len(
        plain_body.split()
    )

    reading_minutes = max(
        1,
        round(word_count / 220),
    )

    # ========================================================
    # RENDER ARTICLE
    # ========================================================

    return render_template(
        "article.html",

        article=article,

        featured_restaurants=featured_restaurants,

        story_view_count=story_view_count,

        story_like_count=story_like_count,

        story_is_liked=story_is_liked,

        reaction_csrf_token=reaction_csrf_token,

        reading_minutes=reading_minutes,

        related_articles=related_articles,

        approved_comments=approved_comments,

        comment_upvote_state=comment_upvote_state,
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
    # PUBLISHED ARTICLE
    # ========================================================

    article = (
        Article.query
        .filter(
            Article.slug == slug,
            Article.status == "published",
        )
        .first_or_404()
    )

    # ========================================================
    # VERIFY LINKED RESTAURANT
    # ========================================================

    linked_restaurant_ids = set()

    for relation in article.restaurants:

        linked_id = (
            relation.kalxa_restaurant_id
        )

        if linked_id is None:
            continue

        try:

            linked_id = int(
                linked_id
            )

        except (TypeError, ValueError):
            continue

        linked_restaurant_ids.add(
            linked_id
        )

    if restaurant_id not in linked_restaurant_ids:
        abort(404)

    # ========================================================
    # TICKETING BASE URL
    # ========================================================

    ticketing_base_url = (
        current_app.config.get(
            "KALXA_TICKETING_URL"
        )
        or ""
    ).strip()

    if not ticketing_base_url:

        current_app.logger.error(
            "[Kalxa Stories] KALXA_TICKETING_URL "
            "is not configured. "
            "article_id=%s restaurant_id=%s",
            article.id,
            restaurant_id,
        )

        abort(500)

    ticketing_base_url = (
        ticketing_base_url.rstrip("/")
    )

    # ========================================================
    # RESTAURANT PROFILE
    # ========================================================
    #
    # Kalxa Ticketing uses:
    #
    #     /restaurant/<advert_id>
    #
    # Do not call the Ticketing API again here.
    # ========================================================

    profile_url = (
        f"{ticketing_base_url}"
        f"/restaurant/{restaurant_id}"
    )

    # ========================================================
    # ANALYTICS
    # ========================================================

    analytics_session_id = (
        get_analytics_session_id()
    )

    record_analytics_event(
        article=article,
        event_type="restaurant_click",
        restaurant_id=restaurant_id,
        metadata={
            "source": "article_restaurant_card",
            "destination": "kalxa_ticketing",
            "profile_path": (
                f"/restaurant/{restaurant_id}"
            ),
        },
        deduplicate=False,
    )

    # ========================================================
    # ATTRIBUTION
    # ========================================================

    attributed_url = build_attributed_ticketing_url(
        profile_url=profile_url,
        article=article,
        restaurant_id=restaurant_id,
        analytics_session_id=analytics_session_id,
    )

    if not attributed_url:

        attributed_url = profile_url

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
    """
    Sitemap includes all published stories,
    including expired published stories.

    Expired stories retain their permanent URLs.
    """

    articles = (
        Article.query
        .filter(
            Article.status == "published"
        )
        .order_by(
            Article.updated_at.desc(),
            Article.id.desc(),
        )
        .all()
    )

    urls = [
        {
            "location": url_for(
                "public.home",
                _external=True,
            ),
            "last_modified": None,
        },
        {
            "location": url_for(
                "public.stories",
                _external=True,
            ),
            "last_modified": None,
        },
    ]

    for article in articles:

        last_modified = (
            article.updated_at
            or article.published_at
            or article.created_at
        )

        urls.append({
            "location": url_for(
                "public.article_detail",
                slug=article.slug,
                _external=True,
            ),
            "last_modified": last_modified,
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
            "  <url>"
        )

        xml_parts.append(
            "    <loc>"
            + str(escape(item["location"]))
            + "</loc>"
        )

        if item["last_modified"]:

            last_modified = item[
                "last_modified"
            ]

            if last_modified.tzinfo is None:

                last_modified = (
                    last_modified.replace(
                        tzinfo=timezone.utc
                    )
                )

            xml_parts.append(
                "    <lastmod>"
                + last_modified.date().isoformat()
                + "</lastmod>"
            )

        xml_parts.append(
            "  </url>"
        )

    xml_parts.append(
        "</urlset>"
    )

    return Response(
        "\n".join(xml_parts),
        content_type="application/xml; charset=utf-8",
    )


# ============================================================
# ROBOTS
# ============================================================

@public_bp.route(
    "/robots.txt"
)
def robots_txt():

    robots = "\n".join([
        "User-agent: *",
        "Allow: /",
        "",
        (
            "Sitemap: "
            "https://kalxa-stories.onrender.com/"
            "sitemap.xml"
        ),
    ])

    return Response(
        robots,
        content_type="text/plain; charset=utf-8",
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
