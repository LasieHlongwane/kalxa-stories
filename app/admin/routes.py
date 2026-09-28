from datetime import datetime, timezone
from functools import wraps

from sqlalchemy import func

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
    ArticleRestaurant,
    StoryAnalyticsEvent,
)

from app.kalxa.client import (
    get_restaurants_by_ids,
    search_restaurants,
)


admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
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
    # OVERALL ANALYTICS
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
    # OVERALL CTR
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
    # PERFORMANCE BY STORY
    # ========================================================

    article_rows = (
        db.session.query(
            Article.id,
            Article.title,
            Article.slug,

            func.sum(
                db.case(
                    (
                        StoryAnalyticsEvent.event_type
                        == "article_view",
                        1,
                    ),
                    else_=0,
                )
            ).label(
                "views"
            ),

            func.sum(
                db.case(
                    (
                        StoryAnalyticsEvent.event_type
                        == "restaurant_impression",
                        1,
                    ),
                    else_=0,
                )
            ).label(
                "impressions"
            ),

            func.sum(
                db.case(
                    (
                        StoryAnalyticsEvent.event_type
                        == "restaurant_click",
                        1,
                    ),
                    else_=0,
                )
            ).label(
                "clicks"
            ),
        )
        .outerjoin(
            StoryAnalyticsEvent,
            StoryAnalyticsEvent.article_id
            == Article.id,
        )
        .group_by(
            Article.id,
            Article.title,
            Article.slug,
        )
        .order_by(
            func.sum(
                db.case(
                    (
                        StoryAnalyticsEvent.event_type
                        == "article_view",
                        1,
                    ),
                    else_=0,
                )
            ).desc()
        )
        .all()
    )

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

        story_performance.append({
            "id": row.id,
            "title": row.title,
            "slug": row.slug,
            "views": views,
            "impressions": impressions,
            "clicks": clicks,
            "ctr": ctr,
        })


    # ========================================================
    # RESTAURANT PERFORMANCE
    # ========================================================

    restaurant_rows = (
        db.session.query(
            StoryAnalyticsEvent
            .kalxa_restaurant_id,

            func.sum(
                db.case(
                    (
                        StoryAnalyticsEvent.event_type
                        == "restaurant_impression",
                        1,
                    ),
                    else_=0,
                )
            ).label(
                "impressions"
            ),

            func.sum(
                db.case(
                    (
                        StoryAnalyticsEvent.event_type
                        == "restaurant_click",
                        1,
                    ),
                    else_=0,
                )
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
                db.case(
                    (
                        StoryAnalyticsEvent.event_type
                        == "restaurant_click",
                        1,
                    ),
                    else_=0,
                )
            ).desc()
        )
        .all()
    )


    # ========================================================
    # FETCH LIVE RESTAURANT NAMES FROM TICKETING
    # ========================================================

    restaurant_ids = [
        row.kalxa_restaurant_id
        for row in restaurant_rows
        if row.kalxa_restaurant_id is not None
    ]

    live_restaurants = []

    if restaurant_ids:

        try:

            live_restaurants = (
                get_restaurants_by_ids(
                    restaurant_ids
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


    restaurant_performance = []

    for row in restaurant_rows:

        restaurant_id = (
            row.kalxa_restaurant_id
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
        })


    # ========================================================
    # RECENT ANALYTICS ACTIVITY
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
            )

        db.session.add(
            article
        )

        # We need article.id before creating
        # ArticleRestaurant records.
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

        flash(
            "Article created.",
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
def article_edit(article_id):

    article = (
        db.session.get(
            Article,
            article_id,
        )
    )

    if article is None:

        abort(404)

    if request.method == "POST":

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
                page_mode="edit",
            )

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
        for relation in sorted(
            article.restaurants,
            key=lambda relation:
                relation.display_order,
        )
    )

    return render_template(
        "admin/article_form.html",
        article=article,
        restaurant_ids=restaurant_ids,
        page_mode="edit",
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

    restaurants = (
        search_restaurants(
            search
        )
    )

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

    article.status = "published"

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

    article.status = "archived"

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
# DELETE
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

    db.session.delete(
        article
    )

    db.session.commit()

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

    cover_image_url = (
        request.form
        .get(
            "cover_image_url",
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

        status = "draft"


    # --------------------------------------------------------
    # DUPLICATE SLUG
    # --------------------------------------------------------

    existing_article = (
        Article.query
        .filter(
            Article.slug == slug
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
            "Another article already uses that slug.",
            "error",
        )

        return False


    # --------------------------------------------------------
    # ASSIGN
    # --------------------------------------------------------

    article.title = title

    article.slug = slug

    article.excerpt = (
        excerpt
        or
        None
    )

    article.body = body

    article.cover_image_url = (
        cover_image_url
        or
        None
    )

    article.article_type = (
        article_type
    )

    article.status = status

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
# RESTAURANT LINKS
# ============================================================

def replace_restaurant_links(
    article,
    raw_restaurant_ids,
):

    # --------------------------------------------------------
    # PARSE
    #
    # Example:
    #
    # 12, 18, 24
    # --------------------------------------------------------

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
            display_order=index,
            is_primary=(
                index == 0
            ),
        )

        db.session.add(
            relation
        )
