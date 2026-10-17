from datetime import datetime, timedelta, timezone
from functools import wraps
from zoneinfo import ZoneInfo
import hmac
import os

import click
import cloudinary
import cloudinary.uploader

from sqlalchemy import and_, case, func

from flask import (
    Blueprint,
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

from app.extensions import db

from app.models import (
    Article,
    ArticleImage,
    ArticleRestaurant,
    StoryCategory,
    StoryAnalyticsEvent,
)

from app.models.article_comment import ArticleComment

from app.models.story_category import (
    TRENDING_NOW_CATEGORY_SLUG,
    TRENDING_NOW_CATEGORY_NAME,
)

from app.kalxa.client import (
    get_restaurants_by_ids,
    get_story_conversion_analytics,
    search_restaurants,
)


# ============================================================
# ADMIN BLUEPRINT
# ============================================================

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
)


# ============================================================
# TRENDING NOW SETTINGS
# ============================================================

SOUTH_AFRICA_TIMEZONE = ZoneInfo(
    "Africa/Johannesburg"
)

TRENDING_NOW_DESCRIPTION = (
    "Temporary local stories, updates and announcements "
    "selected by the Kalxa editorial team."
)


# ============================================================
# STORY MEDIA SETTINGS
# ============================================================

STORY_MAX_IMAGES = 3

STORY_IMAGE_MAX_FILE_BYTES = (
    8 * 1024 * 1024
)

STORY_IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
}


# ============================================================
# CLOUDINARY CONFIGURATION
# ============================================================

CLOUDINARY_CLOUD_NAME = (
    os.environ.get(
        "CLOUDINARY_CLOUD_NAME",
        "",
    ).strip()
)

CLOUDINARY_API_KEY = (
    os.environ.get(
        "CLOUDINARY_API_KEY",
        "",
    ).strip()
)

CLOUDINARY_API_SECRET = (
    os.environ.get(
        "CLOUDINARY_API_SECRET",
        "",
    ).strip()
)

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True,
)


def cloudinary_story_images_configured():

    return all([
        CLOUDINARY_CLOUD_NAME,
        CLOUDINARY_API_KEY,
        CLOUDINARY_API_SECRET,
    ])


def allowed_story_image_filename(filename):

    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1,
    )[1].lower()

    return extension in STORY_IMAGE_EXTENSIONS


def get_uploaded_file_size(uploaded_file):

    uploaded_file.stream.seek(
        0,
        os.SEEK_END,
    )

    file_size = uploaded_file.stream.tell()

    uploaded_file.stream.seek(0)

    return file_size


def delete_cloudinary_story_image(public_id):

    if not public_id:
        return

    try:

        cloudinary.uploader.destroy(
            public_id,
            resource_type="image",
            invalidate=True,
        )

    except Exception:

        current_app.logger.exception(
            "Unable to remove Kalxa Stories "
            "Cloudinary image public_id=%s",
            public_id,
        )


# ============================================================
# TRENDING NOW HELPERS
# ============================================================

def is_trending_now_category(category):
    """
    Return True when a category is the special
    administrator-controlled Trending Now category.
    """

    return bool(
        category is not None
        and category.slug == TRENDING_NOW_CATEGORY_SLUG
    )


def normalise_datetime_to_utc(value):
    """
    Normalise stored datetimes to UTC.

    Existing application datetimes may be naive if they
    were returned by a database driver without tzinfo.

    The application stores expiry timestamps in UTC,
    so naive database values are treated as UTC.
    """

    if value is None:
        return None

    if value.tzinfo is None:

        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def parse_admin_expiry_datetime(raw_value):
    """
    Parse the admin form's datetime-local value.

    Input:
        2026-10-25T23:59

    The entered time is interpreted as SAST.

    Returned value:
        UTC-aware datetime.

    Raises:
        ValueError for an invalid value.
    """

    raw_value = (
        raw_value or ""
    ).strip()

    if not raw_value:
        return None

    parsed = None

    for date_format in (
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ):

        try:

            parsed = datetime.strptime(
                raw_value,
                date_format,
            )

            break

        except ValueError:
            continue

    if parsed is None:

        raise ValueError(
            "Invalid expiry date and time."
        )

    local_datetime = parsed.replace(
        tzinfo=SOUTH_AFRICA_TIMEZONE
    )

    return local_datetime.astimezone(
        timezone.utc
    )


def admin_expiry_input_value(value):
    """
    Convert an existing UTC expiry timestamp into
    South African time for the datetime-local input.
    """

    if value is None:
        return ""

    utc_datetime = normalise_datetime_to_utc(
        value
    )

    local_datetime = utc_datetime.astimezone(
        SOUTH_AFRICA_TIMEZONE
    )

    return local_datetime.strftime(
        "%Y-%m-%dT%H:%M"
    )


def validate_trending_now_expiry(
    category,
    expires_at,
    status,
):
    """
    Enforce the special category's expiry rules.

    Returns True when valid.

    Drafts must have an expiry date too, but are
    permitted to retain a past expiry date while
    being edited.

    Publishing requires an expiry in the future.
    """

    if not is_trending_now_category(category):
        return True

    if expires_at is None:

        flash(
            "Trending Now stories must have "
            "an expiry date and time.",
            "error",
        )

        return False

    if status == "published":

        now = datetime.now(
            timezone.utc
        )

        if normalise_datetime_to_utc(
            expires_at
        ) <= now:

            flash(
                "The expiry date for a Trending Now "
                "story must be in the future "
                "when publishing.",
                "error",
            )

            return False

    return True


def get_admin_article_comments(article_id):

    if article_id is None:
        return []

    return (
        ArticleComment.query
        .filter_by(
            article_id=article_id
        )
        .order_by(
            ArticleComment.created_at.desc()
        )
        .all()
    )


def get_admin_restaurant_ids(article):

    if article is None or article.id is None:
        return ""

    return ", ".join(
        str(relation.kalxa_restaurant_id)
        for relation in sorted(
            article.restaurants,
            key=lambda relation: relation.display_order,
        )
    )


def render_admin_article_form(
    article,
    page_mode,
    restaurant_ids="",
    article_comments=None,
):
    """
    Centralised article-form rendering.

    The existing template receives its original
    variables plus Trending Now metadata.
    """

    if article_comments is None:

        article_comments = get_admin_article_comments(
            article.id if article else None
        )

    expires_at_input = ""

    if request.method == "POST":

        expires_at_input = (
            request.form.get(
                "expires_at",
                "",
            ).strip()
        )

    elif article is not None:

        expires_at_input = admin_expiry_input_value(
            article.expires_at
        )

    return render_template(
        "admin/article_form.html",

        story_categories=available_story_categories(),

        article=article,

        restaurant_ids=restaurant_ids,

        page_mode=page_mode,

        article_comments=article_comments,

        trending_now_category_slug=(
            TRENDING_NOW_CATEGORY_SLUG
        ),

        trending_now_category_name=(
            TRENDING_NOW_CATEGORY_NAME
        ),

        south_africa_timezone_label="SAST (UTC+02:00)",

        expires_at_input=expires_at_input,
    )


# ============================================================
# CLI: CREATE TRENDING NOW CATEGORY
# ============================================================

@admin_bp.cli.command("seed-trending-now")
def seed_trending_now():
    """
    Idempotently create or activate the Trending Now
    category in the current database.

    Command:
        flask --app app admin seed-trending-now
    """

    category = (
        StoryCategory.query
        .filter_by(
            slug=TRENDING_NOW_CATEGORY_SLUG
        )
        .first()
    )

    if category is None:

        category = StoryCategory(
            name=TRENDING_NOW_CATEGORY_NAME,
            slug=TRENDING_NOW_CATEGORY_SLUG,
            description=TRENDING_NOW_DESCRIPTION,
            is_active=True,
            display_order=0,
        )

        db.session.add(category)

        action = "created"

    else:

        category.name = TRENDING_NOW_CATEGORY_NAME

        category.description = (
            category.description
            or TRENDING_NOW_DESCRIPTION
        )

        category.is_active = True

        action = "updated"

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to seed Trending Now category."
        )

        raise click.ClickException(
            "Unable to create Trending Now category."
        )

    click.echo(
        f"Trending Now category {action}. "
        f"Category ID: {category.id}"
    )


# ============================================================
# AUTHENTICATION
# ============================================================

def admin_required(view_function):

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):

        if not session.get(
            "kalxa_stories_admin"
        ):

            return redirect(
                url_for(
                    "admin.login",
                    next=request.path,
                )
            )

        return view_function(
            *args,
            **kwargs
        )

    return wrapped_view


# ============================================================
# LOGIN
# ============================================================

@admin_bp.route(
    "/login",
    methods=["GET", "POST"],
)
def login():

    if session.get(
        "kalxa_stories_admin"
    ):

        return redirect(
            url_for(
                "admin.dashboard"
            )
        )

    if request.method == "POST":

        username = (
            request.form.get(
                "username",
                "",
            ).strip()
        )

        password = request.form.get(
            "password",
            "",
        )

        expected_username = (
            current_app.config.get(
                "KALXA_STORIES_ADMIN_USERNAME"
            )
        )

        expected_password = (
            current_app.config.get(
                "KALXA_STORIES_ADMIN_PASSWORD"
            )
        )

        valid_username = (
            isinstance(expected_username, str)
            and bool(expected_username)
            and hmac.compare_digest(
                username,
                expected_username,
            )
        )

        valid_password = (
            isinstance(expected_password, str)
            and bool(expected_password)
            and hmac.compare_digest(
                password,
                expected_password,
            )
        )

        if valid_username and valid_password:

            session.clear()

            session[
                "kalxa_stories_admin"
            ] = True

            session[
                "kalxa_stories_admin_username"
            ] = username

            next_url = request.args.get(
                "next"
            )

            if (
                next_url
                and next_url.startswith("/")
                and not next_url.startswith("//")
                and not next_url.startswith("/\\")
            ):

                return redirect(
                    next_url
                )

            return redirect(
                url_for(
                    "admin.dashboard"
                )
            )

        flash(
            "Incorrect username or password.",
            "error",
        )

    return render_template(
        "admin/login.html"
    )


# ============================================================
# LOGOUT
# ============================================================

@admin_bp.route(
    "/logout",
    methods=["POST"],
)
@admin_required
def logout():

    session.clear()

    return redirect(
        url_for(
            "admin.login"
        )
    )


# ============================================================
# DASHBOARD
# ============================================================

@admin_bp.route("/")
@admin_required
def dashboard():

    # ========================================================
    # ANALYTICS PERIOD
    # ========================================================

    analytics_period = (
        request.args.get(
            "period",
            "30d",
        ).strip().lower()
    )

    allowed_analytics_periods = {
        "today",
        "7d",
        "30d",
        "all",
    }

    if analytics_period not in allowed_analytics_periods:
        analytics_period = "30d"

    analytics_now = datetime.now(
        timezone.utc
    )

    if analytics_period == "today":

        analytics_start = analytics_now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        analytics_period_label = "Today"

    elif analytics_period == "7d":

        analytics_start = (
            analytics_now
            - timedelta(days=7)
        )

        analytics_period_label = "Last 7 Days"

    elif analytics_period == "30d":

        analytics_start = (
            analytics_now
            - timedelta(days=30)
        )

        analytics_period_label = "Last 30 Days"

    else:

        analytics_start = None
        analytics_period_label = "All Time"

    # ========================================================
    # STORY COUNTS
    # ========================================================

    total_articles = Article.query.count()

    published_articles = (
        Article.query
        .filter_by(status="published")
        .count()
    )

    draft_articles = (
        Article.query
        .filter_by(status="draft")
        .count()
    )

    sponsored_articles = (
        Article.query
        .filter_by(is_sponsored=True)
        .count()
    )

    recent_articles = (
        Article.query
        .order_by(Article.created_at.desc())
        .limit(8)
        .all()
    )

    # ========================================================
    # ANALYTICS PERIOD FILTER HELPER
    # ========================================================

    def apply_analytics_period(query):

        if analytics_start is not None:

            query = query.filter(
                StoryAnalyticsEvent.created_at
                >= analytics_start
            )

        return query

    # ========================================================
    # OVERALL STORIES ANALYTICS
    # ========================================================

    story_views_query = (
        StoryAnalyticsEvent.query
        .filter(
            StoryAnalyticsEvent.event_type
            == "article_view"
        )
    )

    story_views_query = apply_analytics_period(
        story_views_query
    )

    total_story_views = story_views_query.count()

    restaurant_impressions_query = (
        StoryAnalyticsEvent.query
        .filter(
            StoryAnalyticsEvent.event_type
            == "restaurant_impression"
        )
    )

    restaurant_impressions_query = (
        apply_analytics_period(
            restaurant_impressions_query
        )
    )

    total_restaurant_impressions = (
        restaurant_impressions_query.count()
    )

    restaurant_clicks_query = (
        StoryAnalyticsEvent.query
        .filter(
            StoryAnalyticsEvent.event_type
            == "restaurant_click"
        )
    )

    restaurant_clicks_query = (
        apply_analytics_period(
            restaurant_clicks_query
        )
    )

    total_restaurant_clicks = (
        restaurant_clicks_query.count()
    )

    # ========================================================
    # UNIQUE STORY VISITORS
    # ========================================================

    unique_visitors_query = (
        db.session.query(
            func.count(
                func.distinct(
                    StoryAnalyticsEvent.session_id
                )
            )
        )
        .filter(
            StoryAnalyticsEvent.event_type
            == "article_view",

            StoryAnalyticsEvent.session_id
            .isnot(None),
        )
    )

    if analytics_start is not None:

        unique_visitors_query = (
            unique_visitors_query.filter(
                StoryAnalyticsEvent.created_at
                >= analytics_start
            )
        )

    unique_story_visitors = (
        unique_visitors_query.scalar()
        or 0
    )

    # ========================================================
    # RESTAURANT CTR
    # ========================================================

    if total_restaurant_impressions > 0:

        restaurant_ctr = round(
            (
                total_restaurant_clicks
                / total_restaurant_impressions
            ) * 100,
            1,
        )

    else:

        restaurant_ctr = 0.0

    # ========================================================
    # PERFORMANCE BY PUBLISHED STORY
    # ========================================================

    article_view_case = case(
        (
            StoryAnalyticsEvent.event_type
            == "article_view",
            1,
        ),
        else_=0,
    )

    restaurant_impression_case = case(
        (
            StoryAnalyticsEvent.event_type
            == "restaurant_impression",
            1,
        ),
        else_=0,
    )

    restaurant_click_case = case(
        (
            StoryAnalyticsEvent.event_type
            == "restaurant_click",
            1,
        ),
        else_=0,
    )

    article_event_join_conditions = [
        StoryAnalyticsEvent.article_id
        == Article.id
    ]

    if analytics_start is not None:

        article_event_join_conditions.append(
            StoryAnalyticsEvent.created_at
            >= analytics_start
        )

    article_rows = (
        db.session.query(
            Article.id,
            Article.title,
            Article.slug,

            func.sum(
                article_view_case
            ).label("views"),

            func.sum(
                restaurant_impression_case
            ).label("impressions"),

            func.sum(
                restaurant_click_case
            ).label("clicks"),
        )
        .outerjoin(
            StoryAnalyticsEvent,
            and_(
                *article_event_join_conditions
            ),
        )
        .filter(
            Article.status == "published"
        )
        .group_by(
            Article.id,
            Article.title,
            Article.slug,
        )
        .order_by(
            func.sum(
                article_view_case
            ).desc(),
            Article.id.desc(),
        )
        .all()
    )

    # ========================================================
    # TICKETING CONVERSION ANALYTICS
    # ========================================================

    published_story_ids = [
        row.id
        for row in article_rows
    ]

    ticketing_conversion_analytics = {}

    if published_story_ids:

        try:

            ticketing_conversion_analytics = (
                get_story_conversion_analytics(
                    published_story_ids
                )
            )

        except Exception:

            current_app.logger.exception(
                "Unable to retrieve Ticketing "
                "conversion analytics."
            )

            ticketing_conversion_analytics = {}

    ticketing_analytics_period_label = "All Time"

    # ========================================================
    # BUILD STORY PERFORMANCE
    # ========================================================

    story_performance = []

    for row in article_rows:

        views = int(row.views or 0)

        impressions = int(
            row.impressions or 0
        )

        clicks = int(
            row.clicks or 0
        )

        if impressions > 0:

            ctr = round(
                (clicks / impressions) * 100,
                1,
            )

        else:

            ctr = 0.0

        ticketing_story = (
            ticketing_conversion_analytics.get(
                row.id,
                {},
            )
        )

        ticketing_totals = (
            ticketing_story.get(
                "totals",
                {},
            )
            or {}
        )

        restaurant_views = int(
            ticketing_totals.get(
                "restaurant_views",
                0,
            ) or 0
        )

        experience_views = int(
            ticketing_totals.get(
                "experience_views",
                0,
            ) or 0
        )

        whatsapp_clicks = int(
            ticketing_totals.get(
                "whatsapp_clicks",
                0,
            ) or 0
        )

        phone_clicks = int(
            ticketing_totals.get(
                "phone_clicks",
                0,
            ) or 0
        )

        directions_clicks = int(
            ticketing_totals.get(
                "directions_clicks",
                0,
            ) or 0
        )

        meaningful_actions = int(
            ticketing_totals.get(
                "meaningful_actions",
                0,
            ) or 0
        )

        if clicks > 0:

            restaurant_view_rate = round(
                (
                    restaurant_views
                    / clicks
                ) * 100,
                1,
            )

        else:

            restaurant_view_rate = 0.0

        if restaurant_views > 0:

            action_rate = round(
                (
                    meaningful_actions
                    / restaurant_views
                ) * 100,
                1,
            )

        else:

            action_rate = 0.0

        story_performance.append({

            "id": row.id,

            "title": row.title,

            "slug": row.slug,

            "views": views,

            "impressions": impressions,

            "clicks": clicks,

            "ctr": ctr,

            "restaurant_views": restaurant_views,

            "experience_views": experience_views,

            "whatsapp_clicks": whatsapp_clicks,

            "phone_clicks": phone_clicks,

            "directions_clicks": directions_clicks,

            "meaningful_actions": meaningful_actions,

            "restaurant_view_rate": restaurant_view_rate,

            "action_rate": action_rate,
        })

    # ========================================================
    # OVERALL TICKETING TOTALS
    # ========================================================

    total_ticketing_restaurant_views = sum(
        item["restaurant_views"]
        for item in story_performance
    )

    total_experience_views = sum(
        item["experience_views"]
        for item in story_performance
    )

    total_whatsapp_clicks = sum(
        item["whatsapp_clicks"]
        for item in story_performance
    )

    total_phone_clicks = sum(
        item["phone_clicks"]
        for item in story_performance
    )

    total_directions_clicks = sum(
        item["directions_clicks"]
        for item in story_performance
    )

    total_meaningful_actions = sum(
        item["meaningful_actions"]
        for item in story_performance
    )

    if total_restaurant_clicks > 0:

        ticketing_visit_rate = round(
            (
                total_ticketing_restaurant_views
                / total_restaurant_clicks
            ) * 100,
            1,
        )

    else:

        ticketing_visit_rate = 0.0

    if total_ticketing_restaurant_views > 0:

        meaningful_action_rate = round(
            (
                total_meaningful_actions
                / total_ticketing_restaurant_views
            ) * 100,
            1,
        )

    else:

        meaningful_action_rate = 0.0

    # ========================================================
    # RESTAURANT PERFORMANCE
    # ========================================================

    restaurant_impression_case = case(
        (
            StoryAnalyticsEvent.event_type
            == "restaurant_impression",
            1,
        ),
        else_=0,
    )

    restaurant_click_case = case(
        (
            StoryAnalyticsEvent.event_type
            == "restaurant_click",
            1,
        ),
        else_=0,
    )

    restaurant_rows_query = (
        db.session.query(
            StoryAnalyticsEvent.kalxa_restaurant_id,

            func.sum(
                restaurant_impression_case
            ).label("impressions"),

            func.sum(
                restaurant_click_case
            ).label("clicks"),
        )
        .filter(
            StoryAnalyticsEvent.kalxa_restaurant_id
            .isnot(None)
        )
    )

    if analytics_start is not None:

        restaurant_rows_query = (
            restaurant_rows_query.filter(
                StoryAnalyticsEvent.created_at
                >= analytics_start
            )
        )

    restaurant_rows = (
        restaurant_rows_query
        .group_by(
            StoryAnalyticsEvent.kalxa_restaurant_id
        )
        .order_by(
            func.sum(
                restaurant_click_case
            ).desc(),

            StoryAnalyticsEvent
            .kalxa_restaurant_id
            .asc(),
        )
        .all()
    )

    # ========================================================
    # TICKETING TOTALS BY RESTAURANT
    # ========================================================

    ticketing_by_restaurant = {}

    for story_data in (
        ticketing_conversion_analytics.values()
    ):

        restaurants = (
            story_data.get(
                "restaurants",
                [],
            )
            or []
        )

        for restaurant_data in restaurants:

            restaurant_id = (
                restaurant_data.get(
                    "restaurant_id"
                )
            )

            if restaurant_id is None:
                continue

            try:

                restaurant_id = int(
                    restaurant_id
                )

            except (TypeError, ValueError):
                continue

            if (
                restaurant_id
                not in ticketing_by_restaurant
            ):

                ticketing_by_restaurant[
                    restaurant_id
                ] = {
                    "restaurant_views": 0,
                    "experience_views": 0,
                    "whatsapp_clicks": 0,
                    "phone_clicks": 0,
                    "directions_clicks": 0,
                    "meaningful_actions": 0,
                }

            totals = ticketing_by_restaurant[
                restaurant_id
            ]

            totals["restaurant_views"] += int(
                restaurant_data.get(
                    "restaurant_views",
                    0,
                ) or 0
            )

            totals["experience_views"] += int(
                restaurant_data.get(
                    "experience_views",
                    0,
                ) or 0
            )

            totals["whatsapp_clicks"] += int(
                restaurant_data.get(
                    "whatsapp_clicks",
                    0,
                ) or 0
            )

            totals["phone_clicks"] += int(
                restaurant_data.get(
                    "phone_clicks",
                    0,
                ) or 0
            )

            totals["directions_clicks"] += int(
                restaurant_data.get(
                    "directions_clicks",
                    0,
                ) or 0
            )

            totals["meaningful_actions"] += int(
                restaurant_data.get(
                    "meaningful_actions",
                    0,
                ) or 0
            )

    # ========================================================
    # FETCH RESTAURANT NAMES
    # ========================================================

    restaurant_ids = {
        row.kalxa_restaurant_id
        for row in restaurant_rows
        if row.kalxa_restaurant_id is not None
    }

    restaurant_ids.update(
        ticketing_by_restaurant.keys()
    )

    live_restaurants = []

    if restaurant_ids:

        try:

            live_restaurants = get_restaurants_by_ids(
                sorted(restaurant_ids)
            )

        except Exception:

            current_app.logger.exception(
                "Unable to retrieve restaurant "
                "names for analytics dashboard."
            )

            live_restaurants = []

    restaurant_lookup = {
        restaurant.get("id"): restaurant

        for restaurant in live_restaurants

        if restaurant.get("id") is not None
    }

    # ========================================================
    # STORIES RESTAURANT METRICS LOOKUP
    # ========================================================

    stories_restaurant_lookup = {}

    for row in restaurant_rows:

        restaurant_id = row.kalxa_restaurant_id

        stories_restaurant_lookup[
            restaurant_id
        ] = {
            "impressions": int(
                row.impressions or 0
            ),

            "clicks": int(
                row.clicks or 0
            ),
        }

    all_performance_restaurant_ids = set(
        stories_restaurant_lookup.keys()
    )

    all_performance_restaurant_ids.update(
        ticketing_by_restaurant.keys()
    )

    # ========================================================
    # BUILD RESTAURANT PERFORMANCE
    # ========================================================

    restaurant_performance = []

    for restaurant_id in sorted(
        all_performance_restaurant_ids
    ):

        stories_metrics = (
            stories_restaurant_lookup.get(
                restaurant_id,
                {},
            )
        )

        ticketing_metrics = (
            ticketing_by_restaurant.get(
                restaurant_id,
                {},
            )
        )

        impressions = int(
            stories_metrics.get(
                "impressions",
                0,
            ) or 0
        )

        clicks = int(
            stories_metrics.get(
                "clicks",
                0,
            ) or 0
        )

        restaurant_views = int(
            ticketing_metrics.get(
                "restaurant_views",
                0,
            ) or 0
        )

        experience_views = int(
            ticketing_metrics.get(
                "experience_views",
                0,
            ) or 0
        )

        whatsapp_clicks = int(
            ticketing_metrics.get(
                "whatsapp_clicks",
                0,
            ) or 0
        )

        phone_clicks = int(
            ticketing_metrics.get(
                "phone_clicks",
                0,
            ) or 0
        )

        directions_clicks = int(
            ticketing_metrics.get(
                "directions_clicks",
                0,
            ) or 0
        )

        meaningful_actions = int(
            ticketing_metrics.get(
                "meaningful_actions",
                0,
            ) or 0
        )

        if impressions > 0:

            ctr = round(
                (
                    clicks / impressions
                ) * 100,
                1,
            )

        else:

            ctr = 0.0

        if restaurant_views > 0:

            action_rate = round(
                (
                    meaningful_actions
                    / restaurant_views
                ) * 100,
                1,
            )

        else:

            action_rate = 0.0

        restaurant = restaurant_lookup.get(
            restaurant_id,
            {},
        )

        restaurant_performance.append({

            "restaurant_id": restaurant_id,

            "business_name": (
                restaurant.get("business_name")
                or f"Restaurant #{restaurant_id}"
            ),

            "area": (
                restaurant.get("area")
                or ""
            ),

            "impressions": impressions,

            "clicks": clicks,

            "ctr": ctr,

            "restaurant_views": restaurant_views,

            "experience_views": experience_views,

            "whatsapp_clicks": whatsapp_clicks,

            "phone_clicks": phone_clicks,

            "directions_clicks": directions_clicks,

            "meaningful_actions": meaningful_actions,

            "action_rate": action_rate,
        })

    restaurant_performance.sort(
        key=lambda item: (
            -item["meaningful_actions"],
            -item["restaurant_views"],
            -item["clicks"],
            item["restaurant_id"],
        )
    )

    # ========================================================
    # RECENT ANALYTICS ACTIVITY
    # ========================================================

    recent_events_query = (
        StoryAnalyticsEvent.query
    )

    if analytics_start is not None:

        recent_events_query = (
            recent_events_query.filter(
                StoryAnalyticsEvent.created_at
                >= analytics_start
            )
        )

    recent_events = (
        recent_events_query
        .order_by(
            StoryAnalyticsEvent.created_at.desc()
        )
        .limit(20)
        .all()
    )

    recent_article_ids = {
        event.article_id
        for event in recent_events
        if event.article_id is not None
    }

    recent_article_lookup = {}

    if recent_article_ids:

        recent_event_articles = (
            Article.query
            .filter(
                Article.id.in_(
                    recent_article_ids
                )
            )
            .all()
        )

        recent_article_lookup = {
            article.id: article
            for article in recent_event_articles
        }

    recent_restaurant_ids = {
        event.kalxa_restaurant_id

        for event in recent_events

        if event.kalxa_restaurant_id is not None
    }

    missing_restaurant_ids = [
        restaurant_id

        for restaurant_id in recent_restaurant_ids

        if restaurant_id not in restaurant_lookup
    ]

    if missing_restaurant_ids:

        try:

            additional_restaurants = (
                get_restaurants_by_ids(
                    missing_restaurant_ids
                )
            )

            for restaurant in additional_restaurants:

                restaurant_id = restaurant.get(
                    "id"
                )

                if restaurant_id is not None:

                    restaurant_lookup[
                        restaurant_id
                    ] = restaurant

        except Exception:

            current_app.logger.exception(
                "Unable to retrieve recent "
                "analytics restaurant data."
            )

    recent_activity = []

    for event in recent_events:

        article = recent_article_lookup.get(
            event.article_id
        )

        restaurant = None

        if event.kalxa_restaurant_id is not None:

            restaurant = restaurant_lookup.get(
                event.kalxa_restaurant_id
            )

        recent_activity.append({

            "event_type": event.event_type,

            "article_id": event.article_id,

            "article_title": (
                article.title
                if article
                else f"Story #{event.article_id}"
            ),

            "restaurant_id": event.kalxa_restaurant_id,

            "restaurant_name": (
                restaurant.get("business_name")
                if restaurant
                else None
            ),

            "created_at": event.created_at,
        })

    # ========================================================
    # TRENDING NOW DASHBOARD COUNTS
    # ========================================================

    trending_category = (
        StoryCategory.query
        .filter_by(
            slug=TRENDING_NOW_CATEGORY_SLUG
        )
        .first()
    )

    trending_now_total = 0

    trending_now_active = 0

    trending_now_expired = 0

    if trending_category is not None:

        now_utc = datetime.now(
            timezone.utc
        )

        trending_now_total = (
            Article.query
            .filter(
                Article.category_id
                == trending_category.id
            )
            .count()
        )

        trending_now_active = (
            Article.query
            .filter(
                Article.category_id
                == trending_category.id,

                Article.status
                == "published",

                Article.expires_at
                > now_utc,
            )
            .count()
        )

        trending_now_expired = (
            Article.query
            .filter(
                Article.category_id
                == trending_category.id,

                Article.expires_at
                <= now_utc,
            )
            .count()
        )

    # ========================================================
    # RENDER DASHBOARD
    # ========================================================

    return render_template(
        "admin/dashboard.html",

        analytics_period=analytics_period,

        analytics_period_label=(
            analytics_period_label
        ),

        analytics_start=analytics_start,

        analytics_now=analytics_now,

        ticketing_analytics_period_label=(
            ticketing_analytics_period_label
        ),

        total_articles=total_articles,

        published_articles=published_articles,

        draft_articles=draft_articles,

        sponsored_articles=sponsored_articles,

        recent_articles=recent_articles,

        total_story_views=total_story_views,

        unique_story_visitors=(
            unique_story_visitors
        ),

        total_restaurant_impressions=(
            total_restaurant_impressions
        ),

        total_restaurant_clicks=(
            total_restaurant_clicks
        ),

        restaurant_ctr=restaurant_ctr,

        total_ticketing_restaurant_views=(
            total_ticketing_restaurant_views
        ),

        total_experience_views=(
            total_experience_views
        ),

        total_whatsapp_clicks=(
            total_whatsapp_clicks
        ),

        total_phone_clicks=(
            total_phone_clicks
        ),

        total_directions_clicks=(
            total_directions_clicks
        ),

        total_meaningful_actions=(
            total_meaningful_actions
        ),

        ticketing_visit_rate=(
            ticketing_visit_rate
        ),

        meaningful_action_rate=(
            meaningful_action_rate
        ),

        story_performance=(
            story_performance
        ),

        restaurant_performance=(
            restaurant_performance
        ),

        recent_activity=recent_activity,

        trending_now_total=trending_now_total,

        trending_now_active=trending_now_active,

        trending_now_expired=trending_now_expired,
    )


# ============================================================
# ARTICLES LIST
# ============================================================

@admin_bp.route("/articles")
@admin_required
def articles():

    status = (
        request.args.get(
            "status",
            "",
        ).strip()
    )

    query = Article.query

    if status in {
        "draft",
        "published",
        "archived",
    }:

        query = query.filter_by(
            status=status
        )

    articles = (
        query
        .order_by(
            Article.created_at.desc()
        )
        .all()
    )

    return render_template(
        "admin/articles.html",

        articles=articles,

        selected_status=status,
    )


# ============================================================
# AVAILABLE EDITORIAL CATEGORIES
# ============================================================

def available_story_categories():

    return (
        StoryCategory.query
        .filter_by(
            is_active=True
        )
        .order_by(
            StoryCategory.display_order.asc(),
            StoryCategory.name.asc(),
        )
        .all()
    )


# ============================================================
# CREATE ARTICLE
# ============================================================

@admin_bp.route(
    "/articles/new",
    methods=["GET", "POST"],
)
@admin_required
def article_new():

    if request.method == "POST":

        article = Article()

        success = populate_article_from_form(
            article
        )

        if not success:

            return render_admin_article_form(
                article=article,
                page_mode="new",
                restaurant_ids=(
                    request.form.get(
                        "restaurant_ids",
                        "",
                    )
                ),
                article_comments=[],
            )

        try:

            db.session.add(article)

            db.session.flush()

            replace_restaurant_links(
                article=article,

                raw_restaurant_ids=(
                    request.form.get(
                        "restaurant_ids",
                        "",
                    )
                ),
            )

            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                "Unable to create story."
            )

            flash(
                "Unable to create the story.",
                "error",
            )

            return render_admin_article_form(
                article=article,
                page_mode="new",
                restaurant_ids=(
                    request.form.get(
                        "restaurant_ids",
                        "",
                    )
                ),
                article_comments=[],
            )

        flash(
            "Article created. You can now "
            "add story images.",
            "success",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    return render_admin_article_form(
        article=None,
        restaurant_ids="",
        page_mode="new",
        article_comments=[],
    )


# ============================================================
# EDIT ARTICLE
# ============================================================

@admin_bp.route(
    "/articles/<int:article_id>/edit",
    methods=["GET", "POST"],
)
@admin_required
def article_edit(article_id):

    article = db.session.get(
        Article,
        article_id,
    )

    if article is None:
        abort(404)

    if request.method == "POST":

        success = populate_article_from_form(
            article
        )

        if not success:

            db.session.rollback()

            return render_admin_article_form(
                article=article,
                page_mode="edit",
                restaurant_ids=(
                    request.form.get(
                        "restaurant_ids",
                        "",
                    )
                ),
            )

        try:

            replace_restaurant_links(
                article=article,

                raw_restaurant_ids=(
                    request.form.get(
                        "restaurant_ids",
                        "",
                    )
                ),
            )

            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                "Unable to update story."
            )

            flash(
                "Unable to update the story.",
                "error",
            )

            return render_admin_article_form(
                article=article,
                page_mode="edit",
                restaurant_ids=(
                    request.form.get(
                        "restaurant_ids",
                        "",
                    )
                ),
            )

        flash(
            "Article updated.",
            "success",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    return render_admin_article_form(
        article=article,
        restaurant_ids=get_admin_restaurant_ids(
            article
        ),
        page_mode="edit",
    )


# ============================================================
# APPROVE COMMENT
# ============================================================

@admin_bp.route(
    "/comments/<int:comment_id>/approve",
    methods=["POST"],
)
@admin_required
def article_comment_approve(comment_id):

    comment = db.session.get(
        ArticleComment,
        comment_id,
    )

    if comment is None:
        abort(404)

    article_id = comment.article_id

    comment.moderation_status = "approved"

    comment.active = True

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to approve story comment."
        )

        flash(
            "Unable to approve the comment.",
            "error",
        )

    else:

        flash(
            "Comment approved.",
            "success",
        )

    return redirect(
        url_for(
            "admin.article_edit",
            article_id=article_id,
        )
        + "#story-comments"
    )


# ============================================================
# REJECT COMMENT
# ============================================================

@admin_bp.route(
    "/comments/<int:comment_id>/reject",
    methods=["POST"],
)
@admin_required
def article_comment_reject(comment_id):

    comment = db.session.get(
        ArticleComment,
        comment_id,
    )

    if comment is None:
        abort(404)

    article_id = comment.article_id

    comment.moderation_status = "rejected"

    comment.active = True

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to reject story comment."
        )

        flash(
            "Unable to reject the comment.",
            "error",
        )

    else:

        flash(
            "Comment rejected.",
            "success",
        )

    return redirect(
        url_for(
            "admin.article_edit",
            article_id=article_id,
        )
        + "#story-comments"
    )


# ============================================================
# REMOVE COMMENT
# ============================================================

@admin_bp.route(
    "/comments/<int:comment_id>/remove",
    methods=["POST"],
)
@admin_required
def article_comment_remove(comment_id):

    comment = db.session.get(
        ArticleComment,
        comment_id,
    )

    if comment is None:
        abort(404)

    article_id = comment.article_id

    comment.active = False

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to remove story comment."
        )

        flash(
            "Unable to remove the comment.",
            "error",
        )

    else:

        flash(
            "Comment removed from public view.",
            "success",
        )

    return redirect(
        url_for(
            "admin.article_edit",
            article_id=article_id,
        )
        + "#story-comments"
    )


# ============================================================
# POPULATE ARTICLE FROM FORM
# ============================================================

def populate_article_from_form(article):

    # ========================================================
    # BASIC FIELDS
    # ========================================================

    title = (
        request.form.get(
            "title",
            "",
        ).strip()
    )

    slug = (
        request.form.get(
            "slug",
            "",
        ).strip().lower()
    )

    excerpt = (
        request.form.get(
            "excerpt",
            "",
        ).strip()
    )

    body = (
        request.form.get(
            "body",
            "",
        ).strip()
    )

    article_type = (
        request.form.get(
            "article_type",
            "restaurant_story",
        ).strip()
    )

    status = (
        request.form.get(
            "status",
            "draft",
        ).strip()
    )

    meta_title = (
        request.form.get(
            "meta_title",
            "",
        ).strip()
    )

    meta_description = (
        request.form.get(
            "meta_description",
            "",
        ).strip()
    )

    expires_at_raw = (
        request.form.get(
            "expires_at",
            "",
        ).strip()
    )

    raw_category_id = (
        request.form.get(
            "category_id",
            "",
        ).strip()
    )

    # ========================================================
    # REQUIRED FIELDS
    # ========================================================

    if not title:

        flash(
            "Title is required.",
            "error",
        )

        return False

    if not slug:

        flash(
            "Slug is required.",
            "error",
        )

        return False

    if not body:

        flash(
            "Article body is required.",
            "error",
        )

        return False

    # ========================================================
    # ARTICLE TYPE
    # ========================================================

    allowed_types = {
        "restaurant_story",
        "food_guide",
        "sponsored",
        "new_restaurant",
        "experience",
    }

    if article_type not in allowed_types:

        article_type = "restaurant_story"

    # ========================================================
    # STATUS
    # ========================================================

    allowed_statuses = {
        "draft",
        "published",
        "archived",
    }

    if status not in allowed_statuses:

        status = "draft"

    # ========================================================
    # EXPIRY DATE
    # ========================================================

    try:

        expires_at = parse_admin_expiry_datetime(
            expires_at_raw
        )

    except ValueError:

        flash(
            "Story expiration date/time is invalid. "
            "Use a valid South African date and time.",
            "error",
        )

        return False

    # ========================================================
    # EDITORIAL CATEGORY
    # ========================================================

    category_id = None

    category = None

    if raw_category_id:

        try:

            category_id = int(
                raw_category_id
            )

        except (TypeError, ValueError):

            flash(
                "Invalid story category.",
                "error",
            )

            return False

        if category_id <= 0:

            flash(
                "Invalid story category.",
                "error",
            )

            return False

        category = (
            StoryCategory.query
            .filter_by(
                id=category_id,
                is_active=True,
            )
            .first()
        )

        if category is None:

            flash(
                "Selected story category "
                "does not exist.",
                "error",
            )

            return False

    # ========================================================
    # TRENDING NOW VALIDATION
    # ========================================================

    if not validate_trending_now_expiry(
        category=category,
        expires_at=expires_at,
        status=status,
    ):

        return False

    # ========================================================
    # DUPLICATE SLUG
    # ========================================================

    existing_article = (
        Article.query
        .filter(
            Article.slug == slug
        )
        .first()
    )

    if (
        existing_article
        and existing_article.id != article.id
    ):

        flash(
            "Another article already "
            "uses that slug.",
            "error",
        )

        return False

    # ========================================================
    # PAID STORY LIFECYCLE PROTECTION
    # ========================================================
    #
    # Paid submissions remain permanent.
    #
    # They cannot be converted into Trending Now stories,
    # given expiry dates, or published through the normal
    # article editor before verification.
    #
    # Premium restaurant articles without paid-submission
    # records retain their existing publishing workflow.
    # ========================================================

    from app.paid.models import PaidStorySubmission

    if article.id is not None:

        paid_record = (
            PaidStorySubmission.query
            .filter_by(
                article_id=article.id
            )
            .first()
        )

        if paid_record is not None:

            if is_trending_now_category(category):

                flash(
                    "Permanent paid stories cannot "
                    "be assigned to Trending Now.",
                    "error",
                )

                return False

            if expires_at is not None:

                flash(
                    "Permanent paid stories cannot "
                    "have an expiration date.",
                    "error",
                )

                return False

            if (
                article.status == "published"
                and slug != article.slug
            ):

                flash(
                    "Published paid story URLs "
                    "cannot be changed.",
                    "error",
                )

                return False

            if (
                status == "published"
                and paid_record.review_status
                != "published"
            ):

                flash(
                    "Publish this paid story through "
                    "Paid Submissions after verification.",
                    "error",
                )

                return False

    # ========================================================
    # ASSIGN ARTICLE FIELDS
    # ========================================================

    article.title = title

    article.slug = slug

    article.excerpt = (
        excerpt or None
    )

    article.body = body

    article.article_type = article_type

    article.category_id = category_id

    article.status = status

    article.is_sponsored = (
        request.form.get(
            "is_sponsored"
        )
        == "on"
    )

    article.meta_title = (
        meta_title or None
    )

    article.meta_description = (
        meta_description or None
    )

    article.expires_at = expires_at

    # ========================================================
    # PUBLISHED DATE
    # ========================================================

    if (
        status == "published"
        and article.published_at is None
    ):

        article.published_at = datetime.now(
            timezone.utc
        )

    return True


# ============================================================
# UPLOAD ARTICLE IMAGES
# ============================================================

@admin_bp.route(
    "/articles/<int:article_id>/images/upload",
    methods=["POST"],
)
@admin_required
def article_images_upload(article_id):

    article = db.session.get(
        Article,
        article_id,
    )

    if article is None:
        abort(404)

    uploaded_files = [
        uploaded_file

        for uploaded_file
        in request.files.getlist(
            "story_images"
        )

        if (
            uploaded_file
            and uploaded_file.filename
        )
    ]

    if not uploaded_files:

        flash(
            "Choose at least one story image.",
            "error",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    if not cloudinary_story_images_configured():

        flash(
            "Story image storage is not configured.",
            "error",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    existing_count = (
        ArticleImage.query
        .filter_by(
            article_id=article.id
        )
        .count()
    )

    available_slots = (
        STORY_MAX_IMAGES
        - existing_count
    )

    if available_slots <= 0:

        flash(
            "This story already has the "
            "maximum of 3 images.",
            "error",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    if len(uploaded_files) > available_slots:

        flash(
            "Each story can contain a maximum "
            "of 3 images. "
            f"You can currently add "
            f"{available_slots} more.",
            "error",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    # ========================================================
    # VALIDATE FILES
    # ========================================================

    for uploaded_file in uploaded_files:

        if not allowed_story_image_filename(
            uploaded_file.filename
        ):

            flash(
                "Story images must be "
                "JPG, JPEG, PNG or WebP.",
                "error",
            )

            return redirect(
                url_for(
                    "admin.article_edit",
                    article_id=article.id,
                )
            )

        try:

            file_size = get_uploaded_file_size(
                uploaded_file
            )

        except Exception:

            current_app.logger.exception(
                "Unable to determine uploaded "
                "story image size."
            )

            flash(
                "Kalxa could not read one of "
                "the selected images.",
                "error",
            )

            return redirect(
                url_for(
                    "admin.article_edit",
                    article_id=article.id,
                )
            )

        if file_size <= 0:

            flash(
                "One of the selected images "
                "is empty or could not be read.",
                "error",
            )

            return redirect(
                url_for(
                    "admin.article_edit",
                    article_id=article.id,
                )
            )

        if file_size > STORY_IMAGE_MAX_FILE_BYTES:

            flash(
                "Each story image must be "
                "8 MB or smaller.",
                "error",
            )

            return redirect(
                url_for(
                    "admin.article_edit",
                    article_id=article.id,
                )
            )

    # ========================================================
    # UPLOAD IMAGES TO CLOUDINARY
    # ========================================================

    uploaded_public_ids = []

    try:

        next_order = (
            db.session.query(
                func.max(
                    ArticleImage.display_order
                )
            )
            .filter(
                ArticleImage.article_id
                == article.id
            )
            .scalar()
        )

        if next_order is None:

            next_order = 0

        else:

            next_order = int(next_order) + 1

        for uploaded_file in uploaded_files:

            uploaded_file.stream.seek(0)

            upload_result = (
                cloudinary.uploader.upload(
                    uploaded_file,

                    resource_type="image",

                    folder=(
                        "kalxa/"
                        "stories/"
                        f"{article.id}/"
                        "images"
                    ),

                    use_filename=True,
                    unique_filename=True,
                    overwrite=False,
                )
            )

            public_id = upload_result.get(
                "public_id"
            )

            secure_url = upload_result.get(
                "secure_url"
            )

            if not public_id or not secure_url:

                raise RuntimeError(
                    "Cloudinary did not return "
                    "the uploaded story image."
                )

            uploaded_public_ids.append(
                public_id
            )

            image = ArticleImage(
                article_id=article.id,

                cloudinary_public_id=public_id,

                image_url=secure_url,

                display_order=next_order,

                width=upload_result.get(
                    "width"
                ),

                height=upload_result.get(
                    "height"
                ),

                file_bytes=upload_result.get(
                    "bytes"
                ),
            )

            db.session.add(image)

            next_order += 1

        db.session.commit()

    except Exception:

        db.session.rollback()

        for public_id in uploaded_public_ids:

            delete_cloudinary_story_image(
                public_id
            )

        current_app.logger.exception(
            "Unable to upload Kalxa Stories images."
        )

        flash(
            "Kalxa could not upload the story "
            "images. Please choose them again "
            "and retry.",
            "error",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    uploaded_count = len(
        uploaded_files
    )

    if uploaded_count == 1:

        flash(
            "Story image uploaded.",
            "success",
        )

    else:

        flash(
            f"{uploaded_count} story "
            "images uploaded.",
            "success",
        )

    return redirect(
        url_for(
            "admin.article_edit",
            article_id=article.id,
        )
    )


# ============================================================
# DELETE ARTICLE IMAGE
# ============================================================

@admin_bp.route(
    "/articles/<int:article_id>/images/<int:image_id>/delete",
    methods=["POST"],
)
@admin_required
def article_image_delete(
    article_id,
    image_id,
):

    article = db.session.get(
        Article,
        article_id,
    )

    if article is None:
        abort(404)

    image = (
        ArticleImage.query
        .filter_by(
            id=image_id,
            article_id=article.id,
        )
        .first()
    )

    if image is None:
        abort(404)

    public_id = (
        image.cloudinary_public_id
    )

    try:

        db.session.delete(image)

        db.session.flush()

        remaining_images = (
            ArticleImage.query
            .filter(
                ArticleImage.article_id
                == article.id
            )
            .order_by(
                ArticleImage.display_order.asc(),
                ArticleImage.id.asc(),
            )
            .all()
        )

        for index, remaining_image in enumerate(
            remaining_images
        ):

            remaining_image.display_order = index

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to remove story image "
            "from database."
        )

        flash(
            "Unable to remove the story image.",
            "error",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    delete_cloudinary_story_image(
        public_id
    )

    flash(
        "Story image removed.",
        "success",
    )

    return redirect(
        url_for(
            "admin.article_edit",
            article_id=article.id,
        )
    )


# ============================================================
# RESTAURANT SEARCH
# ============================================================

@admin_bp.route("/api/restaurants")
@admin_required
def restaurant_search():

    search = (
        request.args.get(
            "q",
            "",
        ).strip()
    )

    try:

        restaurants = search_restaurants(
            search
        )

    except Exception:

        current_app.logger.exception(
            "Unable to search Kalxa restaurants."
        )

        restaurants = []

    return jsonify({
        "restaurants": restaurants
    })


# ============================================================
# QUICK PUBLISH
# ============================================================

@admin_bp.route(
    "/articles/<int:article_id>/publish",
    methods=["POST"],
)
@admin_required
def article_publish(article_id):

    article = db.session.get(
        Article,
        article_id,
    )

    if article is None:
        abort(404)

    # ========================================================
    # PAID STORY PROTECTION
    # ========================================================

    from app.paid.models import PaidStorySubmission

    paid_submission = (
        PaidStorySubmission.query
        .filter_by(
            article_id=article.id
        )
        .first()
    )

    if paid_submission is not None:

        flash(
            "Use Paid Submissions to publish "
            "this permanent paid article.",
            "error",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    # ========================================================
    # TRENDING NOW PROTECTION
    # ========================================================

    if not validate_trending_now_expiry(
        category=article.category,
        expires_at=article.expires_at,
        status="published",
    ):

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    article.status = "published"

    if article.published_at is None:

        article.published_at = datetime.now(
            timezone.utc
        )

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to publish article."
        )

        flash(
            "Unable to publish article.",
            "error",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    flash(
        "Article published.",
        "success",
    )

    return redirect(
        request.referrer
        or url_for(
            "admin.articles"
        )
    )


# ============================================================
# ARCHIVE ARTICLE
# ============================================================

@admin_bp.route(
    "/articles/<int:article_id>/archive",
    methods=["POST"],
)
@admin_required
def article_archive(article_id):

    article = db.session.get(
        Article,
        article_id,
    )

    if article is None:
        abort(404)

    article.status = "archived"

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to archive article."
        )

        flash(
            "Unable to archive article.",
            "error",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    flash(
        "Article archived.",
        "success",
    )

    return redirect(
        request.referrer
        or url_for(
            "admin.articles"
        )
    )


# ============================================================
# DELETE ARTICLE
# ============================================================

@admin_bp.route(
    "/articles/<int:article_id>/delete",
    methods=["POST"],
)
@admin_required
def article_delete(article_id):

    article = db.session.get(
        Article,
        article_id,
    )

    if article is None:
        abort(404)

    image_public_ids = [
        image.cloudinary_public_id

        for image in article.images

        if image.cloudinary_public_id
    ]

    try:

        db.session.delete(article)

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to delete story."
        )

        flash(
            "Unable to delete the article.",
            "error",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    for public_id in image_public_ids:

        delete_cloudinary_story_image(
            public_id
        )

    flash(
        "Article deleted.",
        "success",
    )

    return redirect(
        url_for(
            "admin.articles"
        )
    )


# ============================================================
# UPLOAD ARTICLE IMAGES HELPER
# ============================================================

def upload_article_images(
    article,
    uploaded_files,
):
    """
    Upload already-validated story images to Cloudinary.

    This helper does not commit or roll back.
    The calling route owns the database transaction.

    Maximum:
        3 images per article.

    Returns:
        List of uploaded Cloudinary public IDs.
    """

    if not cloudinary_story_images_configured():

        raise RuntimeError(
            "Story image storage is not configured."
        )

    existing_count = (
        ArticleImage.query
        .filter_by(
            article_id=article.id
        )
        .count()
    )

    available_slots = (
        STORY_MAX_IMAGES
        - existing_count
    )

    if len(uploaded_files) > available_slots:

        raise ValueError(
            "Each story can contain a "
            "maximum of 3 images."
        )

    next_order = (
        db.session.query(
            func.max(
                ArticleImage.display_order
            )
        )
        .filter(
            ArticleImage.article_id
            == article.id
        )
        .scalar()
    )

    if next_order is None:

        next_order = 0

    else:

        next_order = int(next_order) + 1

    uploaded_public_ids = []

    for uploaded_file in uploaded_files:

        uploaded_file.stream.seek(0)

        upload_result = (
            cloudinary.uploader.upload(
                uploaded_file,

                resource_type="image",

                folder=(
                    "kalxa/"
                    "stories/"
                    f"{article.id}/"
                    "images"
                ),

                use_filename=True,
                unique_filename=True,
                overwrite=False,
            )
        )

        public_id = upload_result.get(
            "public_id"
        )

        secure_url = upload_result.get(
            "secure_url"
        )

        if not public_id or not secure_url:

            raise RuntimeError(
                "Cloudinary did not return "
                "the uploaded story image."
            )

        uploaded_public_ids.append(
            public_id
        )

        image = ArticleImage(
            article_id=article.id,

            cloudinary_public_id=public_id,

            image_url=secure_url,

            display_order=next_order,

            width=upload_result.get(
                "width"
            ),

            height=upload_result.get(
                "height"
            ),

            file_bytes=upload_result.get(
                "bytes"
            ),
        )

        db.session.add(image)

        next_order += 1

    db.session.flush()

    return uploaded_public_ids


# ============================================================
# RESTAURANT LINKS
# ============================================================

def replace_restaurant_links(
    article,
    raw_restaurant_ids,
):

    restaurant_ids = []

    raw_restaurant_ids = (
        raw_restaurant_ids or ""
    )

    raw_values = (
        raw_restaurant_ids
        .replace(
            "\n",
            ",",
        )
        .split(",")
    )

    for raw_value in raw_values:

        value = raw_value.strip()

        if not value:
            continue

        try:

            restaurant_id = int(
                value
            )

        except ValueError:
            continue

        if restaurant_id <= 0:
            continue

        if restaurant_id not in restaurant_ids:

            restaurant_ids.append(
                restaurant_id
            )

    # ========================================================
    # DELETE EXISTING LINKS
    # ========================================================

    ArticleRestaurant.query.filter_by(
        article_id=article.id
    ).delete(
        synchronize_session=False
    )

    # ========================================================
    # CREATE NEW LINKS
    # ========================================================

    for index, restaurant_id in enumerate(
        restaurant_ids
    ):

        relation = ArticleRestaurant(
            article_id=article.id,

            kalxa_restaurant_id=restaurant_id,

            display_order=index,

            is_primary=(index == 0),
        )

        db.session.add(
            relation
        )
