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
import secrets

from app.models.story_reaction import StoryReaction

from uuid import uuid4

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

from itsdangerous import (
    URLSafeTimedSerializer,
)

from markupsafe import escape

from sqlalchemy import (
    or_,
)

from sqlalchemy.exc import (
    IntegrityError,
)

from app.extensions import db

from app.models import (
    Article,
    StoryAnalyticsEvent,
)

from app.models.article_comment import (
    ArticleComment,
    CommentUpvote,
)
from app.models.story_category import StoryCategory

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

    This means:

        Home feed:
            active published stories only.

        Stories feed:
            active published stories only.

        Permanent story URL:
            all published stories, including expired stories.

        Sitemap:
            all published stories, including expired stories.
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

        # Remove legacy/raw attribution values if they exist.
        # Only the signed attribution token should be sent.

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
# KALXA CURATED TRENDING STORIES
# ============================================================

def kalxa_trending_articles(limit=6):
    """
    Return articles eligible for curated Trending display.

    Includes:
        1. Published restaurant-linked stories.
        2. Published paid stories with active featured status.

    Permanent paid publishing:
        No PaidStoryPublication.ends_at dependency.

    Important:
        Association with a restaurant does not establish
        whether that restaurant currently has a valid
        Premium subscription.

        The existing restaurant entitlement integration
        remains the source of truth for that eligibility.

    This is a curated display, not a popularity ranking.
    """

    from datetime import datetime, timezone

    from sqlalchemy import or_

    from app.models.article_restaurant import ArticleRestaurant

    from app.paid.models import PaidStoryPublication

    now = datetime.now(timezone.utc)

    # --------------------------------------------------------
    # RESTAURANT-LINKED ARTICLE IDs
    # --------------------------------------------------------

    restaurant_article_ids = (
        db.session.query(
            ArticleRestaurant.article_id
        )
        .distinct()
        .subquery()
    )

    # --------------------------------------------------------
    # FEATURED PAID PUBLICATIONS
    # --------------------------------------------------------

    # Use only publication and featured-placement columns
    # that exist on the installed PaidStoryPublication model.

    featured_filters = []

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

    if starts_at is not None:
        featured_filters.append(
            starts_at <= now
        )

    if featured_until is not None:
        featured_filters.append(
            featured_until > now
        )

    # Never treat every permanent paid article as featured.
    # If featured_until does not exist, do not infer an
    # active paid featured placement.
    if featured_until is None:

        featured_article_ids = set()

    else:

        featured_query = db.session.query(
            PaidStoryPublication.article_id
        )

        if featured_filters:
            featured_query = featured_query.filter(
                *featured_filters
            )

        featured_article_ids = {
            item[0]
            for item in featured_query.all()
        }

    # --------------------------------------------------------
    # CURATED TRENDING CANDIDATES
    # --------------------------------------------------------

    if featured_article_ids:

        eligibility_filter = or_(
            Article.id.in_(
                db.session.query(
                    restaurant_article_ids.c.article_id
                )
            ),
            Article.id.in_(
                featured_article_ids
            ),
        )

    else:

        eligibility_filter = Article.id.in_(
            db.session.query(
                restaurant_article_ids.c.article_id
            )
        )

    candidates = (
        active_published_article_query()
        .filter(
            eligibility_filter
        )
        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )
        .limit(100)
        .all()
    )

    # --------------------------------------------------------
    # DISPLAY ORDER
    # --------------------------------------------------------

    # Featured articles appear first.
    # The database query already orders the remaining
    # candidates from newest to oldest.
    #
    # Python sort is stable, preserving newest-first order
    # within each group.

    candidates.sort(
        key=lambda article: (
            article.id not in featured_article_ids
        )
    )

    return candidates[:limit]





# ============================================================
# STORY REACTIONS — CSRF TOKEN
# ============================================================

STORY_REACTION_CSRF_KEY = (
    "kalxa_story_reaction_csrf"
)


def story_reaction_csrf_token():

    token = session.get(
        STORY_REACTION_CSRF_KEY
    )

    if not token:

        token = secrets.token_urlsafe(32)

        session[
            STORY_REACTION_CSRF_KEY
        ] = token

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
#
# POST /stories/<slug>/like
# ============================================================

@public_bp.post(
    "/stories/<string:slug>/like"
)
def toggle_story_like(slug):

    # --------------------------------------------------------
    # REQUEST SIZE
    # --------------------------------------------------------

    if (
        request.content_length
        and request.content_length > 10000
    ):
        abort(413)

    # --------------------------------------------------------
    # VALIDATE CSRF
    # --------------------------------------------------------

    submitted_token = (
        request.headers.get(
            "X-CSRF-Token",
            "",
        )
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
            "message": "Please refresh the page and try again.",
        }), 400

    # --------------------------------------------------------
    # PUBLISHED ARTICLE
    #
    # Expired published articles may still receive likes.
    # Their comments remain governed by comments_open.
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ANONYMOUS SESSION
    # --------------------------------------------------------

    anonymous_session_id = (
        get_anonymous_session_id()
    )

    # --------------------------------------------------------
    # CHECK EXISTING LIKE
    # --------------------------------------------------------

    existing_reaction = (
        StoryReaction.query
        .filter_by(
            article_id=article.id,
            anonymous_session_id=anonymous_session_id,
        )
        .first()
    )

    # --------------------------------------------------------
    # REMOVE EXISTING LIKE
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ADD NEW LIKE
    # --------------------------------------------------------

    reaction = StoryReaction(
        article_id=article.id,
        anonymous_session_id=anonymous_session_id,
        reaction_type="like",
    )

    try:

        db.session.add(reaction)

        db.session.commit()

    except IntegrityError:

        # A concurrent request may have inserted the like.
        # Return the actual stored state.

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

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

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
#
# GET /stories/<slug>/engagement
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
        trending_articles=kalxa_trending_articles(),
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
# TOGGLE COMMENT UPVOTE
# ============================================================

@public_bp.post(
    (
        "/stories/<string:slug>"
        "/comments/<int:comment_id>/upvote"
    )
)
def toggle_comment_upvote(
    slug,
    comment_id,
):

    # ========================================================
    # ARTICLE
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

        return jsonify(
            {
                "ok": False,
                "error": "story_not_found",
            }
        ), 404


    # ========================================================
    # COMMENTS MUST STILL BE OPEN
    # ========================================================
    #
    # Expired stories remain accessible as archive pages,
    # but their conversation is closed.
    # ========================================================

    if not article.comments_open:

        return jsonify(
            {
                "ok": False,
                "error": "comments_closed",
                "message": (
                    "Upvotes are closed for this story."
                ),
            }
        ), 403


    # ========================================================
    # APPROVED ACTIVE COMMENT
    # ========================================================
    #
    # The article_id condition is important.
    #
    # It prevents someone from taking a valid comment ID from
    # another story and submitting it through this story URL.
    # ========================================================

    comment = (
        ArticleComment.query

        .filter(
            ArticleComment.id
            == comment_id,

            ArticleComment.article_id
            == article.id,

            ArticleComment.moderation_status
            == "approved",

            ArticleComment.active
            .is_(True),
        )

        .first()
    )

    if comment is None:

        return jsonify(
            {
                "ok": False,
                "error": "comment_not_found",
            }
        ), 404


    # ========================================================
    # ANONYMOUS VISITOR SESSION
    # ========================================================

    anonymous_session_id = (
        get_anonymous_session_id()
    )


    # ========================================================
    # EXISTING UPVOTE
    # ========================================================

    existing_upvote = (
        CommentUpvote.query

        .filter_by(
            comment_id=comment.id,
            anonymous_session_id=(
                anonymous_session_id
            ),
        )

        .first()
    )


    # ========================================================
    # REMOVE EXISTING UPVOTE
    # ========================================================

    if existing_upvote is not None:

        try:

            db.session.delete(
                existing_upvote
            )

            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                "Unable to remove Kalxa Stories "
                "comment upvote."
            )

            return jsonify(
                {
                    "ok": False,
                    "error": (
                        "upvote_remove_failed"
                    ),
                }
            ), 500


        upvote_count = (
            CommentUpvote.query

            .filter_by(
                comment_id=comment.id,
            )

            .count()
        )


        return jsonify(
            {
                "ok": True,
                "comment_id": comment.id,
                "upvoted": False,
                "upvote_count": (
                    upvote_count
                ),
            }
        ), 200


    # ========================================================
    # CREATE NEW UPVOTE
    # ========================================================

    upvote = CommentUpvote(
        comment_id=comment.id,
        anonymous_session_id=(
            anonymous_session_id
        ),
    )

    try:

        db.session.add(
            upvote
        )

        db.session.commit()

    except IntegrityError:

        # ====================================================
        # DUPLICATE PROTECTION
        # ====================================================
        #
        # The database has a UNIQUE constraint on:
        #
        #   comment_id + anonymous_session_id
        #
        # This protects against rapid duplicate requests,
        # multiple tabs, or accidental double-clicks.
        #
        # If another request inserted the upvote first,
        # rollback and return the current state.
        # ====================================================

        db.session.rollback()

        upvote_count = (
            CommentUpvote.query

            .filter_by(
                comment_id=comment.id,
            )

            .count()
        )

        return jsonify(
            {
                "ok": True,
                "comment_id": comment.id,
                "upvoted": True,
                "upvote_count": (
                    upvote_count
                ),
            }
        ), 200

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to save Kalxa Stories "
            "comment upvote."
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "upvote_save_failed"
                ),
            }
        ), 500


    # ========================================================
    # UPDATED COUNT
    # ========================================================

    upvote_count = (
        CommentUpvote.query

        .filter_by(
            comment_id=comment.id,
        )

        .count()
    )


    # ========================================================
    # RESPONSE
    # ========================================================

    return jsonify(
        {
            "ok": True,
            "comment_id": comment.id,
            "upvoted": True,
            "upvote_count": (
                upvote_count
            ),
        }
    ), 200

# ============================================================
# KALXA STORIES - CATEGORY ARTICLES
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

    return render_template(
        "category.html",
        category=category,
        articles=articles,
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
    # STORY ENGAGEMENT
    # ========================================================

    story_engagement = get_story_engagement(
        article.id
    )

    story_view_count = (
        story_engagement["view_count"]
    )

    story_like_count = (
        story_engagement["like_count"]
    )

    story_is_liked = visitor_liked_story(
        article.id
    )

    reaction_csrf_token = (
        story_reaction_csrf_token()
    )

    # ========================================================
    # LINKED KALXA RESTAURANTS
    # ========================================================
    #
    # The ArticleRestaurant relationship is the permanent
    # source of truth that tells Stories which restaurants
    # belong to this article.
    #
    # Live Kalxa Ticketing data is then used to enrich the
    # restaurant card.
    #
    # IMPORTANT:
    #
    # Previously, if the Ticketing lookup returned no data,
    # featured_restaurants became empty and the entire
    # "Places from this story" section disappeared.
    #
    # We now preserve the article's stored restaurant
    # relationship as a fallback.
    # ========================================================

    relations = sorted(
        article.restaurants,
        key=lambda relation:
            (
                relation.display_order
                if relation.display_order
                is not None
                else 999999
            ),
    )


    restaurant_ids = [

        relation.kalxa_restaurant_id

        for relation
        in relations

        if relation.kalxa_restaurant_id
        is not None

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
                (
                    "[Kalxa Stories] "
                    "Unable to load linked restaurants "
                    "for article_id=%s: %s"
                ),
                article.id,
                error,
            )

            live_restaurants = []


    # ========================================================
    # INDEX LIVE RESTAURANTS BY ID
    # ========================================================

    live_restaurants_by_id = {}

    for restaurant in live_restaurants:

        if not isinstance(
            restaurant,
            dict,
        ):

            continue


        restaurant_id = (
            restaurant.get(
                "id"
            )
        )


        if restaurant_id is None:

            continue


        try:

            restaurant_id = int(
                restaurant_id
            )

        except (
            TypeError,
            ValueError,
        ):

            continue


        live_restaurants_by_id[
            restaurant_id
        ] = restaurant


    # ========================================================
    # BUILD FEATURED RESTAURANTS
    # ========================================================
    #
    # Always preserve the restaurant relationship stored in
    # Kalxa Stories.
    #
    # When Ticketing responds successfully, its live fields
    # override / enrich the fallback values.
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

        except (
            TypeError,
            ValueError,
        ):

            continue


        live_restaurant = (
            live_restaurants_by_id.get(
                normalized_restaurant_id
            )
        )


        # ====================================================
        # FALLBACK DATA FROM ARTICLE RELATIONSHIP
        # ====================================================

        restaurant = {

            "id":
                normalized_restaurant_id,

            "business_name":
                getattr(
                    relation,
                    "restaurant_name",
                    None,
                ),

            "name":
                getattr(
                    relation,
                    "restaurant_name",
                    None,
                ),

            "area":
                getattr(
                    relation,
                    "restaurant_area",
                    None,
                ),

            "address":
                None,

            "headline":
                None,

            "price_text":
                None,

            "profile_url":
                None,

        }


        # ====================================================
        # ENRICH WITH LIVE TICKETING DATA
        # ====================================================

        if live_restaurant:

            restaurant.update(
                live_restaurant
            )


            # Ensure the canonical linked ID remains present.

            restaurant["id"] = (
                normalized_restaurant_id
            )


            # Keep stored fallback values when Ticketing
            # returns a field as blank / None.

            if not restaurant.get(
                "business_name"
            ):

                restaurant[
                    "business_name"
                ] = getattr(
                    relation,
                    "restaurant_name",
                    None,
                )


            if not restaurant.get(
                "name"
            ):

                restaurant[
                    "name"
                ] = getattr(
                    relation,
                    "restaurant_name",
                    None,
                )


            if not restaurant.get(
                "area"
            ):

                restaurant[
                    "area"
                ] = getattr(
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
    #
    # Expired stories remain available as permanent archive
    # pages, but their comments are hidden and closed.
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
                ArticleComment
                .created_at
                .desc()
            )

            .all()
        )


        # ====================================================
        # CURRENT VISITOR UPVOTE STATE
        # ====================================================

        if approved_comments:

            anonymous_session_id = (
                get_anonymous_session_id()
            )


            comment_ids = [

                comment.id

                for comment
                in approved_comments

            ]


            visitor_upvotes = (
                CommentUpvote.query

                .filter(

                    CommentUpvote.comment_id
                    .in_(
                        comment_ids
                    ),

                    CommentUpvote
                    .anonymous_session_id
                    == anonymous_session_id,

                )

                .all()
            )


            visitor_upvoted_comment_ids = {

                upvote.comment_id

                for upvote
                in visitor_upvotes

            }


            comment_upvote_state = {

                comment.id:
                    (
                        comment.id
                        in
                        visitor_upvoted_comment_ids
                    )

                for comment
                in approved_comments

            }


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

        story_view_count=story_view_count,

        story_like_count=story_like_count,

        story_is_liked=story_is_liked,

        reaction_csrf_token=reaction_csrf_token,

        reading_minutes=(
            reading_minutes
        ),

        related_articles=(
            related_articles
        ),

        approved_comments=(
            approved_comments
        ),

        comment_upvote_state=(
            comment_upvote_state
        ),
    )




# ============================================================
# TRACK RESTAURANT CLICK
# ============================================================
#
# PURPOSE:
#
# Redirect a reader from a Kalxa Story directly to the linked
# restaurant profile on Kalxa Ticketing.
#
# IMPORTANT:
#
# This route deliberately does NOT call:
#
#     get_restaurant()
#
# The ArticleRestaurant relationship already proves that the
# restaurant belongs to this story.
#
# Avoiding another Ticketing API lookup prevents temporary
# API errors such as HTTP 429 Too Many Requests from breaking
# the "View restaurant" CTA.
#
# Public Ticketing restaurant route:
#
#     /restaurant/<int:advert_id>
#
# Example:
#
#     https://tickets.kalxa.co.za/restaurant/5
#
# Attribution parameters are still added before redirecting,
# allowing Kalxa Ticketing to capture the Stories referral.
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

    # ========================================================
    # ARTICLE
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
    # VERIFY RESTAURANT IS LINKED TO ARTICLE
    # ========================================================
    #
    # The redirect must only work for restaurants actually
    # connected to this story.
    #
    # This prevents somebody from manually changing:
    #
    #     /restaurants/5
    #
    # to:
    #
    #     /restaurants/999
    #
    # and using the Stories redirect route for an unrelated
    # restaurant.
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

        except (
            TypeError,
            ValueError,
        ):

            continue


        linked_restaurant_ids.add(
            linked_id
        )


    if (
        restaurant_id
        not in linked_restaurant_ids
    ):

        abort(
            404
        )


    # ========================================================
    # KALXA TICKETING BASE URL
    # ========================================================
    #
    # Expected environment/config value:
    #
    #     KALXA_TICKETING_URL=
    #         https://tickets.kalxa.co.za
    #
    # Do not call the Ticketing API here.
    # ========================================================

    ticketing_base_url = (
        current_app.config.get(
            "KALXA_TICKETING_URL"
        )
        or ""
    ).strip()


    if not ticketing_base_url:

        current_app.logger.error(
            (
                "[Kalxa Stories] "
                "KALXA_TICKETING_URL is not configured. "
                "Unable to redirect article_id=%s "
                "restaurant_id=%s."
            ),
            article.id,
            restaurant_id,
        )

        abort(
            500
        )


    ticketing_base_url = (
        ticketing_base_url.rstrip(
            "/"
        )
    )


    # ========================================================
    # RESTAURANT PROFILE URL
    # ========================================================
    #
    # Confirmed Kalxa Ticketing public route:
    #
    #     /restaurant/<int:advert_id>
    #
    # restaurant_id in Stories corresponds to advert_id in
    # Kalxa Ticketing.
    # ========================================================

    profile_url = (
        f"{ticketing_base_url}"
        f"/restaurant/{restaurant_id}"
    )


    # ========================================================
    # ANALYTICS SESSION
    # ========================================================
    #
    # This session ID allows Stories -> Ticketing activity to
    # remain attributable across the redirect.
    # ========================================================

    analytics_session_id = (
        get_analytics_session_id()
    )


    # ========================================================
    # RECORD STORIES RESTAURANT CLICK
    # ========================================================
    #
    # This records the outbound click inside Kalxa Stories
    # before the visitor leaves for Kalxa Ticketing.
    # ========================================================

    record_analytics_event(
        article=article,

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

            "profile_path":
                (
                    f"/restaurant/"
                    f"{restaurant_id}"
                ),
        },

        deduplicate=False,
    )


    # ========================================================
    # BUILD ATTRIBUTED TICKETING URL
    # ========================================================
    #
    # Existing helper is preserved.
    #
    # It should add the Stories attribution parameters used by
    # Ticketing's:
    #
    #     capture_restaurant_attribution(advert)
    #
    # Example conceptual destination:
    #
    # https://tickets.kalxa.co.za/restaurant/5
    #     ?utm_source=kalxa_stories
    #     &...
    #
    # Exact parameters remain controlled by the existing
    # build_attributed_ticketing_url() helper.
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


    # ========================================================
    # ATTRIBUTION FALLBACK
    # ========================================================
    #
    # A tracking/helper problem should never prevent the user
    # from opening the restaurant.
    #
    # If attribution URL generation unexpectedly fails, send
    # the visitor to the normal restaurant profile.
    # ========================================================

    if not attributed_url:

        current_app.logger.warning(
            (
                "[Kalxa Stories] "
                "Unable to build attributed restaurant URL. "
                "Falling back to direct Ticketing profile. "
                "article_id=%s restaurant_id=%s"
            ),
            article.id,
            restaurant_id,
        )


        attributed_url = (
            profile_url
        )


    # ========================================================
    # REDIRECT TO KALXA TICKETING
    # ========================================================

    return redirect(
        attributed_url
    )

    # ========================================================
    # TICKETING BASE URL
    # ========================================================
    #
    # Example:
    #
    # KALXA_TICKETING_URL=https://tickets.kalxa.co.za
    #
    # We intentionally avoid get_restaurant() here because
    # clicking the CTA should not depend on another API call.
    # ========================================================

    ticketing_base_url = (
        current_app.config.get(
            "KALXA_TICKETING_URL"
        )
        or ""
    ).strip()


    if not ticketing_base_url:

        current_app.logger.error(
            (
                "[Kalxa Stories] "
                "KALXA_TICKETING_URL is not configured."
            )
        )

        abort(
            500
        )


    ticketing_base_url = (
        ticketing_base_url.rstrip(
            "/"
        )
    )


    # ========================================================
    # RESTAURANT PROFILE URL
    # ========================================================
    #
    # IMPORTANT:
    #
    # Use the actual public restaurant profile route used by
    # Kalxa Ticketing.
    #
    # If your Ticketing restaurant pages are:
    #
    #   /restaurants/5
    #
    # keep this as-is.
    #
    # If Ticketing uses another path such as:
    #
    #   /restaurant/5
    #   /r/5
    #
    # change ONLY this line.
    # ========================================================

    profile_url = (
        f"{ticketing_base_url}"
        f"/restaurants/{restaurant_id}"
    )


    # ========================================================
    # ANALYTICS SESSION
    # ========================================================

    analytics_session_id = (
        get_analytics_session_id()
    )


    # ========================================================
    # RECORD RESTAURANT CLICK
    # ========================================================

    record_analytics_event(
        article=article,

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
    # ATTRIBUTION
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

        current_app.logger.error(
            (
                "[Kalxa Stories] "
                "Unable to build attributed Ticketing URL "
                "for article_id=%s restaurant_id=%s."
            ),
            article.id,
            restaurant_id,
        )

        # ----------------------------------------------------
        # FALLBACK
        # ----------------------------------------------------
        #
        # Even if attribution construction fails, don't prevent
        # the reader from reaching the restaurant.
        # ----------------------------------------------------

        attributed_url = (
            profile_url
        )


    # ========================================================
    # REDIRECT
    # ========================================================

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
    XML sitemap for Kalxa Stories.

    IMPORTANT:

    Unlike the home page and /stories discovery feed,
    the sitemap deliberately contains ALL published stories,
    including stories whose expires_at date has passed.

    Story expiration removes a story from active discovery.
    It does not delete or archive its permanent public URL.
    """

    # ========================================================
    # ALL PUBLISHED STORIES
    # ========================================================

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


    # ========================================================
    # BUILD SITEMAP URL DATA
    # ========================================================

    urls = [
        {
            "location":
                url_for(
                    "public.home",
                    _external=True,
                ),

            "last_modified":
                None,
        },

        {
            "location":
                url_for(
                    "public.stories",
                    _external=True,
                ),

            "last_modified":
                None,
        },
    ]

    for article in articles:

        last_modified = (
            article.updated_at
            or
            article.published_at
            or
            article.created_at
        )

        urls.append(
            {
                "location":
                    url_for(
                        "public.article_detail",
                        slug=article.slug,
                        _external=True,
                    ),

                "last_modified":
                    last_modified,
            }
        )


    # ========================================================
    # XML DOCUMENT
    # ========================================================

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',

        (
            '<urlset '
            'xmlns="http://www.sitemaps.org/'
            'schemas/sitemap/0.9">'
        ),
    ]


    # ========================================================
    # XML URL ENTRIES
    # ========================================================

    for item in urls:

        xml_parts.append(
            "  <url>"
        )

        xml_parts.append(
            "    <loc>"
            +
            str(
                escape(
                    item["location"]
                )
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
                "    <lastmod>"
                +
                last_modified
                .date()
                .isoformat()
                +
                "</lastmod>"
            )

        xml_parts.append(
            "  </url>"
        )

    xml_parts.append(
        "</urlset>"
    )


    # ========================================================
    # RESPONSE
    # ========================================================

    response = Response(
        "\n".join(
            xml_parts
        ),
        content_type=(
            "application/xml; charset=utf-8"
        ),
    )

    return response


# ============================================================
# ROBOTS
# ============================================================

@public_bp.route(
    "/robots.txt"
)
def robots_txt():

    robots = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "",
            (
                "Sitemap: "
                "https://kalxa-stories.onrender.com/"
                "sitemap.xml"
            ),
        ]
    )

    return Response(
        robots,
        content_type=(
            "text/plain; charset=utf-8"
        ),
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
