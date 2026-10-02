from datetime import datetime, timezone
from functools import wraps
import os
from app.models.article_comment import (
    ArticleComment,
)
import cloudinary
import cloudinary.uploader
from sqlalchemy import case, func

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
    StoryAnalyticsEvent,
)

from app.kalxa.client import (
    get_restaurants_by_ids,
    get_story_conversion_analytics,
    search_restaurants,
)


admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
)


# ============================================================
# STORY MEDIA
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
# CLOUDINARY
# ============================================================

CLOUDINARY_CLOUD_NAME = (
    os.environ.get(
        "CLOUDINARY_CLOUD_NAME",
        "",
    )
    .strip()
)

CLOUDINARY_API_KEY = (
    os.environ.get(
        "CLOUDINARY_API_KEY",
        "",
    )
    .strip()
)

CLOUDINARY_API_SECRET = (
    os.environ.get(
        "CLOUDINARY_API_SECRET",
        "",
    )
    .strip()
)


cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True,
)


def cloudinary_story_images_configured():

    return all(
        [
            CLOUDINARY_CLOUD_NAME,
            CLOUDINARY_API_KEY,
            CLOUDINARY_API_SECRET,
        ]
    )


def allowed_story_image_filename(
    filename,
):

    if (
        not filename
        or
        "." not in filename
    ):

        return False

    extension = (
        filename
        .rsplit(
            ".",
            1,
        )[1]
        .lower()
    )

    return (
        extension
        in STORY_IMAGE_EXTENSIONS
    )


def get_uploaded_file_size(
    uploaded_file,
):

    uploaded_file.stream.seek(
        0,
        os.SEEK_END,
    )

    file_size = (
        uploaded_file.stream.tell()
    )

    uploaded_file.stream.seek(
        0
    )

    return file_size


def delete_cloudinary_story_image(
    public_id,
):

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
# AUTHENTICATION DECORATOR
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
    methods=[
        "GET",
        "POST",
    ],
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
            request.form
            .get(
                "username",
                "",
            )
            .strip()
        )

        password = (
            request.form
            .get(
                "password",
                "",
            )
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

        if (
            username == expected_username
            and
            password == expected_password
            and
            expected_password
        ):

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
                and
                next_url.startswith("/")
                and
                not next_url.startswith("//")
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
    # STORY COUNTS
    # ========================================================

    total_articles = (
        Article.query.count()
    )

    published_articles = (
        Article.query
        .filter_by(
            status="published"
        )
        .count()
    )

    draft_articles = (
        Article.query
        .filter_by(
            status="draft"
        )
        .count()
    )

    sponsored_articles = (
        Article.query
        .filter_by(
            is_sponsored=True
        )
        .count()
    )

    recent_articles = (
        Article.query
        .order_by(
            Article.created_at.desc()
        )
        .limit(8)
        .all()
    )


    # ========================================================
    # OVERALL STORIES ANALYTICS
    # ========================================================

    total_story_views = (
        StoryAnalyticsEvent.query
        .filter_by(
            event_type="article_view"
        )
        .count()
    )

    total_restaurant_impressions = (
        StoryAnalyticsEvent.query
        .filter_by(
            event_type="restaurant_impression"
        )
        .count()
    )

    total_restaurant_clicks = (
        StoryAnalyticsEvent.query
        .filter_by(
            event_type="restaurant_click"
        )
        .count()
    )


    # ========================================================
    # UNIQUE STORY VISITORS
    # ========================================================

    unique_story_visitors = (
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
        .scalar()
        or 0
    )


    # ========================================================
    # OVERALL RESTAURANT CTR
    # ========================================================

    if total_restaurant_impressions > 0:

        restaurant_ctr = round(
            (
                total_restaurant_clicks
                /
                total_restaurant_impressions
            )
            * 100,
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

    article_rows = (
        db.session.query(
            Article.id,
            Article.title,
            Article.slug,

            func.sum(
                article_view_case
            ).label(
                "views"
            ),

            func.sum(
                restaurant_impression_case
            ).label(
                "impressions"
            ),

            func.sum(
                restaurant_click_case
            ).label(
                "clicks"
            ),
        )
        .outerjoin(
            StoryAnalyticsEvent,
            StoryAnalyticsEvent.article_id
            == Article.id,
        )
        .filter(
            Article.status
            == "published"
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


    # ========================================================
    # BUILD STORY PERFORMANCE
    # ========================================================

    story_performance = []

    for row in article_rows:

        views = int(
            row.views or 0
        )

        impressions = int(
            row.impressions or 0
        )

        clicks = int(
            row.clicks or 0
        )

        if impressions > 0:

            ctr = round(
                (
                    clicks
                    /
                    impressions
                )
                * 100,
                1,
            )

        else:

            ctr = 0.0


        ticketing_story = (
            ticketing_conversion_analytics
            .get(
                row.id,
                {},
            )
        )

        ticketing_totals = (
            ticketing_story.get(
                "totals",
                {},
            )
            or
            {}
        )

        restaurant_views = int(
            ticketing_totals.get(
                "restaurant_views",
                0,
            )
            or 0
        )

        experience_views = int(
            ticketing_totals.get(
                "experience_views",
                0,
            )
            or 0
        )

        whatsapp_clicks = int(
            ticketing_totals.get(
                "whatsapp_clicks",
                0,
            )
            or 0
        )

        phone_clicks = int(
            ticketing_totals.get(
                "phone_clicks",
                0,
            )
            or 0
        )

        directions_clicks = int(
            ticketing_totals.get(
                "directions_clicks",
                0,
            )
            or 0
        )

        meaningful_actions = int(
            ticketing_totals.get(
                "meaningful_actions",
                0,
            )
            or 0
        )


        # ----------------------------------------------------
        # CLICK → RESTAURANT VIEW RATE
        # ----------------------------------------------------

        if clicks > 0:

            restaurant_view_rate = round(
                (
                    restaurant_views
                    /
                    clicks
                )
                * 100,
                1,
            )

        else:

            restaurant_view_rate = 0.0


        # ----------------------------------------------------
        # RESTAURANT VIEW → MEANINGFUL ACTION RATE
        # ----------------------------------------------------

        if restaurant_views > 0:

            action_rate = round(
                (
                    meaningful_actions
                    /
                    restaurant_views
                )
                * 100,
                1,
            )

        else:

            action_rate = 0.0


        story_performance.append({
            "id":
                row.id,

            "title":
                row.title,

            "slug":
                row.slug,

            "views":
                views,

            "impressions":
                impressions,

            "clicks":
                clicks,

            "ctr":
                ctr,

            "restaurant_views":
                restaurant_views,

            "experience_views":
                experience_views,

            "whatsapp_clicks":
                whatsapp_clicks,

            "phone_clicks":
                phone_clicks,

            "directions_clicks":
                directions_clicks,

            "meaningful_actions":
                meaningful_actions,

            "restaurant_view_rate":
                restaurant_view_rate,

            "action_rate":
                action_rate,
        })


    # ========================================================
    # OVERALL TICKETING CONVERSION TOTALS
    # ========================================================

    total_ticketing_restaurant_views = sum(
        item[
            "restaurant_views"
        ]
        for item
        in story_performance
    )

    total_experience_views = sum(
        item[
            "experience_views"
        ]
        for item
        in story_performance
    )

    total_whatsapp_clicks = sum(
        item[
            "whatsapp_clicks"
        ]
        for item
        in story_performance
    )

    total_phone_clicks = sum(
        item[
            "phone_clicks"
        ]
        for item
        in story_performance
    )

    total_directions_clicks = sum(
        item[
            "directions_clicks"
        ]
        for item
        in story_performance
    )

    total_meaningful_actions = sum(
        item[
            "meaningful_actions"
        ]
        for item
        in story_performance
    )


    # ========================================================
    # OVERALL DOWNSTREAM CONVERSION RATES
    # ========================================================

    if total_restaurant_clicks > 0:

        ticketing_visit_rate = round(
            (
                total_ticketing_restaurant_views
                /
                total_restaurant_clicks
            )
            * 100,
            1,
        )

    else:

        ticketing_visit_rate = 0.0


    if total_ticketing_restaurant_views > 0:

        meaningful_action_rate = round(
            (
                total_meaningful_actions
                /
                total_ticketing_restaurant_views
            )
            * 100,
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

    restaurant_rows = (
        db.session.query(
            StoryAnalyticsEvent
            .kalxa_restaurant_id,

            func.sum(
                restaurant_impression_case
            ).label(
                "impressions"
            ),

            func.sum(
                restaurant_click_case
            ).label(
                "clicks"
            ),
        )
        .filter(
            StoryAnalyticsEvent
            .kalxa_restaurant_id
            .isnot(None)
        )
        .group_by(
            StoryAnalyticsEvent
            .kalxa_restaurant_id
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
        ticketing_conversion_analytics
        .values()
    ):

        restaurants = (
            story_data.get(
                "restaurants",
                [],
            )
            or
            []
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

            except (
                TypeError,
                ValueError,
            ):

                continue

            if (
                restaurant_id
                not in ticketing_by_restaurant
            ):

                ticketing_by_restaurant[
                    restaurant_id
                ] = {
                    "restaurant_views":
                        0,

                    "experience_views":
                        0,

                    "whatsapp_clicks":
                        0,

                    "phone_clicks":
                        0,

                    "directions_clicks":
                        0,

                    "meaningful_actions":
                        0,
                }

            totals = (
                ticketing_by_restaurant[
                    restaurant_id
                ]
            )

            totals[
                "restaurant_views"
            ] += int(
                restaurant_data.get(
                    "restaurant_views",
                    0,
                )
                or 0
            )

            totals[
                "experience_views"
            ] += int(
                restaurant_data.get(
                    "experience_views",
                    0,
                )
                or 0
            )

            totals[
                "whatsapp_clicks"
            ] += int(
                restaurant_data.get(
                    "whatsapp_clicks",
                    0,
                )
                or 0
            )

            totals[
                "phone_clicks"
            ] += int(
                restaurant_data.get(
                    "phone_clicks",
                    0,
                )
                or 0
            )

            totals[
                "directions_clicks"
            ] += int(
                restaurant_data.get(
                    "directions_clicks",
                    0,
                )
                or 0
            )

            totals[
                "meaningful_actions"
            ] += int(
                restaurant_data.get(
                    "meaningful_actions",
                    0,
                )
                or 0
            )


    # ========================================================
    # FETCH LIVE RESTAURANT NAMES FROM TICKETING
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

            live_restaurants = (
                get_restaurants_by_ids(
                    sorted(
                        restaurant_ids
                    )
                )
            )

        except Exception:

            current_app.logger.exception(
                "Unable to retrieve restaurant "
                "names for analytics dashboard."
            )

            live_restaurants = []

    restaurant_lookup = {
        restaurant.get("id"):
            restaurant

        for restaurant
        in live_restaurants

        if restaurant.get("id")
        is not None
    }


    # ========================================================
    # STORIES RESTAURANT METRICS LOOKUP
    # ========================================================

    stories_restaurant_lookup = {}

    for row in restaurant_rows:

        restaurant_id = (
            row.kalxa_restaurant_id
        )

        stories_restaurant_lookup[
            restaurant_id
        ] = {
            "impressions":
                int(
                    row.impressions
                    or 0
                ),

            "clicks":
                int(
                    row.clicks
                    or 0
                ),
        }


    # ========================================================
    # BUILD RESTAURANT PERFORMANCE
    # ========================================================

    all_performance_restaurant_ids = set(
        stories_restaurant_lookup.keys()
    )

    all_performance_restaurant_ids.update(
        ticketing_by_restaurant.keys()
    )

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
            )
            or 0
        )

        clicks = int(
            stories_metrics.get(
                "clicks",
                0,
            )
            or 0
        )

        restaurant_views = int(
            ticketing_metrics.get(
                "restaurant_views",
                0,
            )
            or 0
        )

        experience_views = int(
            ticketing_metrics.get(
                "experience_views",
                0,
            )
            or 0
        )

        whatsapp_clicks = int(
            ticketing_metrics.get(
                "whatsapp_clicks",
                0,
            )
            or 0
        )

        phone_clicks = int(
            ticketing_metrics.get(
                "phone_clicks",
                0,
            )
            or 0
        )

        directions_clicks = int(
            ticketing_metrics.get(
                "directions_clicks",
                0,
            )
            or 0
        )

        meaningful_actions = int(
            ticketing_metrics.get(
                "meaningful_actions",
                0,
            )
            or 0
        )


        if impressions > 0:

            ctr = round(
                (
                    clicks
                    /
                    impressions
                )
                * 100,
                1,
            )

        else:

            ctr = 0.0


        if restaurant_views > 0:

            action_rate = round(
                (
                    meaningful_actions
                    /
                    restaurant_views
                )
                * 100,
                1,
            )

        else:

            action_rate = 0.0


        restaurant = (
            restaurant_lookup.get(
                restaurant_id,
                {},
            )
        )

        restaurant_performance.append({
            "restaurant_id":
                restaurant_id,

            "business_name":
                restaurant.get(
                    "business_name"
                )
                or
                f"Restaurant #{restaurant_id}",

            "area":
                restaurant.get(
                    "area"
                )
                or
                "",

            "impressions":
                impressions,

            "clicks":
                clicks,

            "ctr":
                ctr,

            "restaurant_views":
                restaurant_views,

            "experience_views":
                experience_views,

            "whatsapp_clicks":
                whatsapp_clicks,

            "phone_clicks":
                phone_clicks,

            "directions_clicks":
                directions_clicks,

            "meaningful_actions":
                meaningful_actions,

            "action_rate":
                action_rate,
        })


    restaurant_performance.sort(
        key=lambda item: (
            -item[
                "meaningful_actions"
            ],
            -item[
                "restaurant_views"
            ],
            -item[
                "clicks"
            ],
            item[
                "restaurant_id"
            ],
        )
    )


    # ========================================================
    # RECENT STORIES ANALYTICS ACTIVITY
    # ========================================================

    recent_events = (
        StoryAnalyticsEvent.query
        .order_by(
            StoryAnalyticsEvent
            .created_at
            .desc()
        )
        .limit(20)
        .all()
    )


    # ========================================================
    # ARTICLE LOOKUP FOR RECENT EVENTS
    # ========================================================

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
            article.id:
                article

            for article
            in recent_event_articles
        }


    # ========================================================
    # RESTAURANT LOOKUP FOR RECENT EVENTS
    # ========================================================

    recent_restaurant_ids = {
        event.kalxa_restaurant_id

        for event
        in recent_events

        if event.kalxa_restaurant_id
        is not None
    }

    missing_restaurant_ids = [
        restaurant_id

        for restaurant_id
        in recent_restaurant_ids

        if restaurant_id
        not in restaurant_lookup
    ]

    if missing_restaurant_ids:

        try:

            additional_restaurants = (
                get_restaurants_by_ids(
                    missing_restaurant_ids
                )
            )

            for restaurant in (
                additional_restaurants
            ):

                restaurant_id = (
                    restaurant.get(
                        "id"
                    )
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


    # ========================================================
    # BUILD RECENT ACTIVITY
    # ========================================================

    recent_activity = []

    for event in recent_events:

        article = (
            recent_article_lookup.get(
                event.article_id
            )
        )

        restaurant = None

        if (
            event.kalxa_restaurant_id
            is not None
        ):

            restaurant = (
                restaurant_lookup.get(
                    event.kalxa_restaurant_id
                )
            )

        recent_activity.append({
            "event_type":
                event.event_type,

            "article_id":
                event.article_id,

            "article_title":
                (
                    article.title
                    if article
                    else
                    f"Story #{event.article_id}"
                ),

            "restaurant_id":
                event.kalxa_restaurant_id,

            "restaurant_name":
                (
                    restaurant.get(
                        "business_name"
                    )
                    if restaurant
                    else
                    None
                ),

            "created_at":
                event.created_at,
        })


    # ========================================================
    # RENDER DASHBOARD
    # ========================================================

    return render_template(
        "admin/dashboard.html",

        total_articles=(
            total_articles
        ),

        published_articles=(
            published_articles
        ),

        draft_articles=(
            draft_articles
        ),

        sponsored_articles=(
            sponsored_articles
        ),

        recent_articles=(
            recent_articles
        ),

        total_story_views=(
            total_story_views
        ),

        unique_story_visitors=(
            unique_story_visitors
        ),

        total_restaurant_impressions=(
            total_restaurant_impressions
        ),

        total_restaurant_clicks=(
            total_restaurant_clicks
        ),

        restaurant_ctr=(
            restaurant_ctr
        ),

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

        recent_activity=(
            recent_activity
        ),
    )


# ============================================================
# ARTICLES
# ============================================================

@admin_bp.route(
    "/articles"
)
@admin_required
def articles():

    status = (
        request.args
        .get(
            "status",
            "",
        )
        .strip()
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
# CREATE ARTICLE
# ============================================================

# ============================================================
# CREATE ARTICLE
# ============================================================

@admin_bp.route(
    "/articles/new",
    methods=[
        "GET",
        "POST",
    ],
)
@admin_required
def article_new():

    if request.method == "POST":

        article = Article()

        success = (
            populate_article_from_form(
                article
            )
        )

        if not success:

            return render_template(
                "admin/article_form.html",
                article=article,
                restaurant_ids=(
                    request.form.get(
                        "restaurant_ids",
                        "",
                    )
                ),
                page_mode="new",
                article_comments=[],
            )

        try:

            db.session.add(
                article
            )

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

            return render_template(
                "admin/article_form.html",
                article=article,
                restaurant_ids=(
                    request.form.get(
                        "restaurant_ids",
                        "",
                    )
                ),
                page_mode="new",
                article_comments=[],
            )

        flash(
            (
                "Article created. "
                "You can now add story images."
            ),
            "success",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )

    return render_template(
        "admin/article_form.html",
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
    methods=[
        "GET",
        "POST",
    ],
)
@admin_required
def article_edit(
    article_id,
):

    article = (
        db.session.get(
            Article,
            article_id,
        )
    )

    if article is None:

        abort(
            404
        )

    if request.method == "POST":

        success = (
            populate_article_from_form(
                article
            )
        )

        if not success:

            article_comments = (
                ArticleComment.query

                .filter_by(
                    article_id=article.id
                )

                .order_by(
                    ArticleComment
                    .created_at
                    .desc()
                )

                .all()
            )

            return render_template(
                "admin/article_form.html",
                article=article,
                restaurant_ids=(
                    request.form.get(
                        "restaurant_ids",
                        "",
                    )
                ),
                page_mode="edit",
                article_comments=(
                    article_comments
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

            article_comments = (
                ArticleComment.query

                .filter_by(
                    article_id=article.id
                )

                .order_by(
                    ArticleComment
                    .created_at
                    .desc()
                )

                .all()
            )

            return render_template(
                "admin/article_form.html",
                article=article,
                restaurant_ids=(
                    request.form.get(
                        "restaurant_ids",
                        "",
                    )
                ),
                page_mode="edit",
                article_comments=(
                    article_comments
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

    restaurant_ids = ", ".join(
        str(
            relation.kalxa_restaurant_id
        )
        for relation
        in sorted(
            article.restaurants,
            key=lambda relation:
                relation.display_order,
        )
    )

    article_comments = (
        ArticleComment.query

        .filter_by(
            article_id=article.id
        )

        .order_by(
            ArticleComment
            .created_at
            .desc()
        )

        .all()
    )

    return render_template(
        "admin/article_form.html",
        article=article,
        restaurant_ids=restaurant_ids,
        page_mode="edit",
        article_comments=(
            article_comments
        ),
    )


# ============================================================
# APPROVE COMMENT
# ============================================================

@admin_bp.route(
    "/comments/<int:comment_id>/approve",
    methods=["POST"],
)
@admin_required
def article_comment_approve(
    comment_id,
):

    comment = (
        db.session.get(
            ArticleComment,
            comment_id,
        )
    )

    if comment is None:

        abort(
            404
        )

    article_id = (
        comment.article_id
    )

    comment.moderation_status = (
        "approved"
    )

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
        +
        "#story-comments"
    )


# ============================================================
# REJECT COMMENT
# ============================================================

@admin_bp.route(
    "/comments/<int:comment_id>/reject",
    methods=["POST"],
)
@admin_required
def article_comment_reject(
    comment_id,
):

    comment = (
        db.session.get(
            ArticleComment,
            comment_id,
        )
    )

    if comment is None:

        abort(
            404
        )

    article_id = (
        comment.article_id
    )

    comment.moderation_status = (
        "rejected"
    )

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
        +
        "#story-comments"
    )


# ============================================================
# DELETE / DEACTIVATE COMMENT
# ============================================================

@admin_bp.route(
    "/comments/<int:comment_id>/remove",
    methods=["POST"],
)
@admin_required
def article_comment_remove(
    comment_id,
):

    comment = (
        db.session.get(
            ArticleComment,
            comment_id,
        )
    )

    if comment is None:

        abort(
            404
        )

    article_id = (
        comment.article_id
    )

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
        +
        "#story-comments"
    )


# ============================================================
# FORM HELPERS
# ============================================================

def populate_article_from_form(
    article
):

    title = (
        request.form
        .get(
            "title",
            "",
        )
        .strip()
    )

    slug = (
        request.form
        .get(
            "slug",
            "",
        )
        .strip()
        .lower()
    )

    excerpt = (
        request.form
        .get(
            "excerpt",
            "",
        )
        .strip()
    )

    body = (
        request.form
        .get(
            "body",
            "",
        )
        .strip()
    )

    article_type = (
        request.form
        .get(
            "article_type",
            "restaurant_story",
        )
        .strip()
    )

    status = (
        request.form
        .get(
            "status",
            "draft",
        )
        .strip()
    )

    meta_title = (
        request.form
        .get(
            "meta_title",
            "",
        )
        .strip()
    )

    meta_description = (
        request.form
        .get(
            "meta_description",
            "",
        )
        .strip()
    )

    expires_at_raw = (
        request.form
        .get(
            "expires_at",
            "",
        )
        .strip()
    )

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

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

    allowed_types = {
        "restaurant_story",
        "food_guide",
        "sponsored",
        "new_restaurant",
        "experience",
    }

    if article_type not in allowed_types:

        article_type = (
            "restaurant_story"
        )

    allowed_statuses = {
        "draft",
        "published",
        "archived",
    }

    if status not in allowed_statuses:

        status = (
            "draft"
        )

    # --------------------------------------------------------
    # EXPIRATION DATE
    # --------------------------------------------------------

    expires_at = None

    if expires_at_raw:

        try:

            expires_at = (
                datetime.strptime(
                    expires_at_raw,
                    "%Y-%m-%dT%H:%M",
                )
            )

            # The editor currently treats entered times
            # as UTC.
            #
            # This keeps storage consistent with the rest
            # of the application's timezone-aware fields.
            expires_at = (
                expires_at.replace(
                    tzinfo=timezone.utc
                )
            )

        except ValueError:

            flash(
                (
                    "Story expiration date/time "
                    "is invalid."
                ),
                "error",
            )

            return False

    # --------------------------------------------------------
    # DUPLICATE SLUG
    # --------------------------------------------------------

    existing_article = (
        Article.query

        .filter(
            Article.slug
            == slug
        )

        .first()
    )

    if (
        existing_article
        and
        existing_article.id
        != article.id
    ):

        flash(
            (
                "Another article already "
                "uses that slug."
            ),
            "error",
        )

        return False

    # --------------------------------------------------------
    # ASSIGN
    # --------------------------------------------------------

    article.title = (
        title
    )

    article.slug = (
        slug
    )

    article.excerpt = (
        excerpt
        or
        None
    )

    article.body = (
        body
    )

    article.article_type = (
        article_type
    )

    article.status = (
        status
    )

    article.is_sponsored = (
        request.form.get(
            "is_sponsored"
        )
        == "on"
    )

    article.meta_title = (
        meta_title
        or
        None
    )

    article.meta_description = (
        meta_description
        or
        None
    )

    article.expires_at = (
        expires_at
    )

    # --------------------------------------------------------
    # PUBLISHED DATE
    # --------------------------------------------------------

    if (
        status == "published"
        and
        article.published_at is None
    ):

        article.published_at = (
            datetime.now(
                timezone.utc
            )
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
def article_images_upload(
    article_id,
):

    article = (
        db.session.get(
            Article,
            article_id,
        )
    )

    if article is None:

        abort(404)


    # ========================================================
    # RECEIVE IMAGE FILES
    # ========================================================

    uploaded_files = [
        uploaded_file

        for uploaded_file
        in request.files.getlist(
            "story_images"
        )

        if (
            uploaded_file
            and
            uploaded_file.filename
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


    # ========================================================
    # CLOUDINARY CONFIGURATION
    # ========================================================

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


    # ========================================================
    # CURRENT IMAGE COUNT
    # ========================================================

    existing_count = (
        ArticleImage.query
        .filter_by(
            article_id=article.id
        )
        .count()
    )

    available_slots = (
        STORY_MAX_IMAGES
        -
        existing_count
    )


    if available_slots <= 0:

        flash(
            "This story already has the maximum of 3 images.",
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
            (
                "Each story can contain a maximum "
                "of 3 images. "
                f"You can currently add "
                f"{available_slots} more."
            ),
            "error",
        )

        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )


    # ========================================================
    # VALIDATE ALL FILES BEFORE CLOUDINARY UPLOAD
    # ========================================================

    for uploaded_file in uploaded_files:

        if not allowed_story_image_filename(
            uploaded_file.filename
        ):

            flash(
                (
                    "Story images must be JPG, JPEG, "
                    "PNG or WebP."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "admin.article_edit",
                    article_id=article.id,
                )
            )


        try:

            file_size = (
                get_uploaded_file_size(
                    uploaded_file
                )
            )

        except Exception:

            current_app.logger.exception(
                "Unable to determine uploaded "
                "story image size."
            )

            flash(
                (
                    "Kalxa could not read one of the "
                    "selected images. Please choose "
                    "the image again."
                ),
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
                (
                    "One of the selected images is empty "
                    "or could not be read."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "admin.article_edit",
                    article_id=article.id,
                )
            )


        if (
            file_size
            >
            STORY_IMAGE_MAX_FILE_BYTES
        ):

            flash(
                (
                    "Each story image must be "
                    "8 MB or smaller."
                ),
                "error",
            )

            return redirect(
                url_for(
                    "admin.article_edit",
                    article_id=article.id,
                )
            )


    # ========================================================
    # UPLOAD TO CLOUDINARY
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

            next_order = (
                int(next_order)
                + 1
            )


        for uploaded_file in uploaded_files:

            # ------------------------------------------------
            # RESET FILE STREAM
            # ------------------------------------------------
            #
            # get_uploaded_file_size() reads the stream to
            # determine its size and resets it. Reset once more
            # immediately before Cloudinary for safety.
            # ------------------------------------------------

            uploaded_file.stream.seek(
                0
            )


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


            public_id = (
                upload_result.get(
                    "public_id"
                )
            )

            secure_url = (
                upload_result.get(
                    "secure_url"
                )
            )


            if (
                not public_id
                or
                not secure_url
            ):

                raise RuntimeError(
                    "Cloudinary did not return "
                    "the uploaded story image."
                )


            uploaded_public_ids.append(
                public_id
            )


            image = ArticleImage(
                article_id=article.id,

                cloudinary_public_id=(
                    public_id
                ),

                image_url=(
                    secure_url
                ),

                display_order=(
                    next_order
                ),

                width=(
                    upload_result.get(
                        "width"
                    )
                ),

                height=(
                    upload_result.get(
                        "height"
                    )
                ),

                file_bytes=(
                    upload_result.get(
                        "bytes"
                    )
                ),
            )


            db.session.add(
                image
            )

            next_order += 1


        db.session.commit()


    except Exception:

        db.session.rollback()


        # ====================================================
        # CLEAN UP CLOUDINARY ASSETS
        # ====================================================
        #
        # If Cloudinary successfully accepted one image but a
        # later upload/database operation failed, remove the
        # already-uploaded assets.
        # ====================================================

        for public_id in (
            uploaded_public_ids
        ):

            delete_cloudinary_story_image(
                public_id
            )


        current_app.logger.exception(
            "Unable to upload Kalxa Stories images."
        )


        flash(
            (
                "Kalxa could not upload the story "
                "images. Please choose them again "
                "and retry."
            ),
            "error",
        )


        return redirect(
            url_for(
                "admin.article_edit",
                article_id=article.id,
            )
        )


    # ========================================================
    # SUCCESS
    # ========================================================

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
            f"{uploaded_count} story images uploaded.",
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
    (
        "/articles/<int:article_id>"
        "/images/<int:image_id>/delete"
    ),
    methods=["POST"],
)
@admin_required
def article_image_delete(
    article_id,
    image_id,
):

    article = (
        db.session.get(
            Article,
            article_id,
        )
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

        db.session.delete(
            image
        )

        db.session.flush()


        # ====================================================
        # REORDER REMAINING IMAGES
        # ====================================================

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

            remaining_image.display_order = (
                index
            )


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


    # ========================================================
    # REMOVE CLOUDINARY ASSET
    # ========================================================
    #
    # Database deletion has already succeeded.
    # Cloudinary cleanup is intentionally best-effort.
    # ========================================================

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

@admin_bp.route(
    "/api/restaurants"
)
@admin_required
def restaurant_search():

    search = (
        request.args
        .get(
            "q",
            "",
        )
        .strip()
    )

    try:

        restaurants = (
            search_restaurants(
                search
            )
        )

    except Exception:

        current_app.logger.exception(
            "Unable to search Kalxa restaurants."
        )

        restaurants = []


    return jsonify({
        "restaurants":
            restaurants
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

    article = (
        db.session.get(
            Article,
            article_id,
        )
    )

    if article is None:

        abort(404)

    article.status = (
        "published"
    )

    if article.published_at is None:

        article.published_at = (
            datetime.now(
                timezone.utc
            )
        )

    db.session.commit()

    flash(
        "Article published.",
        "success",
    )

    return redirect(
        request.referrer
        or
        url_for(
            "admin.articles"
        )
    )


# ============================================================
# ARCHIVE
# ============================================================

@admin_bp.route(
    "/articles/<int:article_id>/archive",
    methods=["POST"],
)
@admin_required
def article_archive(article_id):

    article = (
        db.session.get(
            Article,
            article_id,
        )
    )

    if article is None:

        abort(404)

    article.status = (
        "archived"
    )

    db.session.commit()

    flash(
        "Article archived.",
        "success",
    )

    return redirect(
        request.referrer
        or
        url_for(
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

    article = (
        db.session.get(
            Article,
            article_id,
        )
    )

    if article is None:

        abort(404)


    # ========================================================
    # SAVE CLOUDINARY IDS BEFORE DATABASE DELETE
    # ========================================================

    image_public_ids = [
        image.cloudinary_public_id

        for image in article.images

        if image.cloudinary_public_id
    ]


    try:

        db.session.delete(
            article
        )

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


    # ========================================================
    # REMOVE CLOUDINARY ASSETS
    # ========================================================
    #
    # ArticleImage records are deleted through the Article
    # relationship cascade. Cloudinary files are external,
    # therefore they must be cleaned up separately.
    # ========================================================

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
# FORM HELPERS
# ============================================================




# ============================================================
# STORY IMAGE UPLOAD HELPER
# ============================================================

def upload_article_images(
    article,
    uploaded_files,
):
    """
    Upload already-validated story images to Cloudinary.

    IMPORTANT:
        This helper does NOT commit or rollback.

        The calling route owns the database transaction.

    Maximum:
        3 images total per article.

    Returns:
        List of Cloudinary public IDs uploaded during this
        operation. The caller can use these for cleanup if a
        later database operation fails.
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
        -
        existing_count
    )


    if len(uploaded_files) > available_slots:

        raise ValueError(
            (
                "Each story can contain a maximum "
                "of 3 images."
            )
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

        next_order = (
            int(next_order)
            + 1
        )


    uploaded_public_ids = []


    for uploaded_file in uploaded_files:

        uploaded_file.stream.seek(
            0
        )


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


        public_id = (
            upload_result.get(
                "public_id"
            )
        )

        secure_url = (
            upload_result.get(
                "secure_url"
            )
        )


        if (
            not public_id
            or
            not secure_url
        ):

            raise RuntimeError(
                "Cloudinary did not return "
                "the uploaded story image."
            )


        uploaded_public_ids.append(
            public_id
        )


        image = ArticleImage(
            article_id=article.id,

            cloudinary_public_id=(
                public_id
            ),

            image_url=(
                secure_url
            ),

            display_order=(
                next_order
            ),

            width=(
                upload_result.get(
                    "width"
                )
            ),

            height=(
                upload_result.get(
                    "height"
                )
            ),

            file_bytes=(
                upload_result.get(
                    "bytes"
                )
            ),
        )


        db.session.add(
            image
        )

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
        raw_restaurant_ids
        or
        ""
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

        value = (
            raw_value.strip()
        )

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

        if (
            restaurant_id
            not in restaurant_ids
        ):

            restaurant_ids.append(
                restaurant_id
            )


    # --------------------------------------------------------
    # DELETE EXISTING LINKS
    # --------------------------------------------------------

    ArticleRestaurant.query.filter_by(
        article_id=article.id
    ).delete(
        synchronize_session=False
    )


    # --------------------------------------------------------
    # CREATE NEW LINKS
    # --------------------------------------------------------

    for index, restaurant_id in enumerate(
        restaurant_ids
    ):

        relation = ArticleRestaurant(
            article_id=article.id,

            kalxa_restaurant_id=(
                restaurant_id
            ),

            display_order=(
                index
            ),

            is_primary=(
                index == 0
            ),
        )

        db.session.add(
            relation
        )
