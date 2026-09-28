from datetime import datetime, timezone
from functools import wraps
from app.kalxa.client import (
    search_restaurants,
)
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

    return render_template(
        "admin/dashboard.html",
        total_articles=total_articles,
        published_articles=published_articles,
        draft_articles=draft_articles,
        sponsored_articles=sponsored_articles,
        recent_articles=recent_articles,
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

        success = populate_article_from_form(
            article
        )

        if not success:

            return render_template(
                "admin/article_form.html",
                article=article,
                restaurant_ids=request.form.get(
                    "restaurant_ids",
                    "",
                ),
                page_mode="new",
            )

        db.session.add(article)

        # We need article.id before
        # creating ArticleRestaurant records.
        db.session.flush()

        replace_restaurant_links(
            article=article,
            raw_restaurant_ids=request.form.get(
                "restaurant_ids",
                "",
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

        success = populate_article_from_form(
            article
        )

        if not success:

            return render_template(
                "admin/article_form.html",
                article=article,
                restaurant_ids=request.form.get(
                    "restaurant_ids",
                    "",
                ),
                page_mode="edit",
            )

        replace_restaurant_links(
            article=article,
            raw_restaurant_ids=request.form.get(
                "restaurant_ids",
                "",
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

    db.session.delete(article)

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

    raw_values = (
        raw_restaurant_ids
        .replace("\n", ",")
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
            kalxa_restaurant_id=restaurant_id,
            display_order=index,
            is_primary=(
                index == 0
            ),
        )

        db.session.add(
            relation
        )