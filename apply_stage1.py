
"""
KALXA STORIES — STAGE 1 INSTALLER

Adds editorial categories to the existing KALXA Stories app.

Run from the repository root:

    python apply_stage1.py

Actual project structure:

    kalxa-stories/
        apply_stage1.py
        config.py
        app/
            models/
            public/
            admin/
            templates/
                home.html
                admin/
                    article_form.html

IMPORTANT:
- Does not run database migrations.
- Does not modify the database.
- Does not alter the ArticleRestaurant model.
- Does not alter KALXA Ticketing API integrations.
- Does not modify Premium Restaurant eligibility.
- Preserves original source files as .stage1.bak.
- Safe to rerun when Stage 1 changes already exist.
"""

from pathlib import Path
import shutil


# ============================================================
# PROJECT PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

APP_DIR = ROOT / "app"

MODELS_DIR = APP_DIR / "models"

TEMPLATES_DIR = APP_DIR / "templates"

PUBLIC_ROUTES = APP_DIR / "public" / "routes.py"

ADMIN_ROUTES = APP_DIR / "admin" / "routes.py"


# ============================================================
# FILE HELPERS
# ============================================================

def read_source(path):

    return path.read_text(
        encoding="utf-8"
    )


def once_replace(
    content,
    old,
    new,
    label,
):

    count = content.count(old)

    if count != 1:

        raise RuntimeError(
            f"{label}: expected exactly one "
            f"insertion anchor, found {count}. "
            "No changes have been written."
        )

    return content.replace(
        old,
        new,
        1,
    )


def validate_required_files():

    required_files = [
        MODELS_DIR / "article.py",
        MODELS_DIR / "__init__.py",
        PUBLIC_ROUTES,
        ADMIN_ROUTES,
        TEMPLATES_DIR / "home.html",
        TEMPLATES_DIR / "admin" / "article_form.html",
    ]

    missing = [
        path
        for path in required_files
        if not path.is_file()
    ]

    if missing:

        missing_text = "\n".join(
            str(path.relative_to(ROOT))
            for path in missing
        )

        raise FileNotFoundError(
            "Required project files are missing:\n"
            + missing_text
        )


# ============================================================
# CATEGORY MODEL
# ============================================================

CATEGORY_MODEL = '''from app.extensions import db


# ============================================================
# KALXA STORIES — EDITORIAL CATEGORIES
# ============================================================
#
# Editorial categories are separate from the existing
# Premium Restaurant → KALXA Stories relationship.
# ============================================================

class StoryCategory(db.Model):

    __tablename__ = "story_categories"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    name = db.Column(
        db.String(120),
        nullable=False,
    )

    slug = db.Column(
        db.String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    display_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    articles = db.relationship(
        "Article",
        back_populates="category",
        lazy=True,
    )

    def __repr__(self):

        return (
            f"<StoryCategory "
            f"id={self.id} "
            f"name={self.name!r}>"
        )
'''


# ============================================================
# CATEGORY ARTICLE PAGE
# ============================================================

CATEGORY_TEMPLATE = '''{% extends "base.html" %}

{% block title %}
{{ category.name }} | KALXA Stories
{% endblock %}

{% block meta_description %}
{{ category.description or "Explore local stories on KALXA." }}
{% endblock %}

{% block extra_head %}

<style>

    .category-hero {
        padding: 90px 0 70px;
        background: var(--kalxa-cream);
        border-bottom: 1px solid var(--kalxa-border);
    }

    .category-label {
        color: var(--kalxa-gold-dark);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 2px;
        text-transform: uppercase;
    }

    .category-title {
        max-width: 900px;
        margin: 20px 0;
        font-family: var(--kalxa-serif);
        font-size: clamp(42px, 7vw, 80px);
        font-weight: 500;
        line-height: 1.08;
        letter-spacing: -2px;
    }

    .category-description {
        max-width: 640px;
        color: var(--kalxa-text-soft);
        font-size: 15px;
        line-height: 1.8;
    }

    .category-back {
        display: inline-block;
        margin-top: 25px;
        color: var(--kalxa-gold-dark);
        font-size: 12px;
        font-weight: 700;
    }

    .category-articles {
        padding: 75px 0 100px;
    }

    @media (max-width: 650px) {

        .category-hero {
            padding: 65px 0 50px;
        }

        .category-articles {
            padding: 45px 0 65px;
        }

    }

</style>

{% endblock %}


{% block content %}

<section class="category-hero">

    <div class="page-container">

        <div class="category-label">
            KALXA STORIES / EXPLORE
        </div>

        <h1 class="category-title">
            {{ category.name }}
        </h1>

        {% if category.description %}

        <p class="category-description">
            {{ category.description }}
        </p>

        {% endif %}

        <a
            class="category-back"
            href="{{ url_for('public.home') }}"
        >
            ← Back to Stories
        </a>

    </div>

</section>


<section class="category-articles">

    <div class="page-container">

        <div class="section-heading">
            <span>Stories in this category</span>
        </div>

        {% if articles %}

        <div class="story-grid">

            {% for article in articles %}

            <article class="story-card">

                <a
                    class="story-image-link"
                    href="{{ url_for(
                        'public.article_detail',
                        slug=article.slug
                    ) }}"
                >

                    <div class="story-image">

                        {% if article.display_cover_image_url %}

                        <img
                            src="{{ article.display_cover_image_url }}"
                            alt="{{ article.title }}"
                            loading="lazy"
                        >

                        {% else %}

                        <div class="image-placeholder small">
                            <span>K</span>
                        </div>

                        {% endif %}

                    </div>

                </a>

                <div class="story-card-content">

                    <div class="story-meta">

                        {% if article.is_sponsored %}

                        <span class="sponsored-label">
                            Sponsored
                        </span>

                        {% endif %}

                        <span>{{ category.name }}</span>

                    </div>

                    <h3>

                        <a href="{{ url_for(
                            'public.article_detail',
                            slug=article.slug
                        ) }}">
                            {{ article.title }}
                        </a>

                    </h3>

                    {% if article.excerpt %}

                    <p>{{ article.excerpt }}</p>

                    {% endif %}

                    <a
                        class="read-link"
                        href="{{ url_for(
                            'public.article_detail',
                            slug=article.slug
                        ) }}"
                    >
                        Read Story →
                    </a>

                </div>

            </article>

            {% endfor %}

        </div>

        {% else %}

        <div class="empty-state">

            <div class="empty-icon">K</div>

            <h2>Stories are coming.</h2>

            <p>
                New stories will appear here
                as they are published.
            </p>

        </div>

        {% endif %}

    </div>

</section>

{% endblock %}
'''


# ============================================================
# HOMEPAGE CATEGORY CSS
# ============================================================

CATEGORY_CSS = '''    /* =====================================================
       EDITORIAL CATEGORY NAVIGATION
    ====================================================== */

    .story-categories {
        padding: 65px 0 10px;
    }

    .story-categories-heading {
        margin: 0 0 12px;
        font-family: var(--kalxa-serif);
        font-size: clamp(32px, 4vw, 48px);
        font-weight: 500;
    }

    .story-categories-intro {
        margin: 0 0 29px;
        color: var(--kalxa-text-soft);
        font-size: 13px;
        line-height: 1.7;
    }

    .story-categories-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 15px;
    }

    .story-category-button {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 18px;
        min-height: 135px;
        padding: 25px 28px;
        background: var(--kalxa-paper);
        border: 1px solid var(--kalxa-border);
        transition:
            border-color .2s,
            transform .2s,
            box-shadow .2s;
    }

    .story-category-button:hover {
        border-color: var(--kalxa-gold);
        transform: translateY(-2px);
        box-shadow: var(--kalxa-shadow);
    }

    .story-category-button small {
        display: block;
        margin-bottom: 11px;
        color: var(--kalxa-gold-dark);
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
    }

    .story-category-button strong {
        display: block;
        color: var(--kalxa-ink);
        font-family: var(--kalxa-serif);
        font-size: clamp(19px, 2.2vw, 27px);
        font-weight: 500;
        line-height: 1.2;
    }

    .story-category-button .category-arrow {
        flex-shrink: 0;
        color: var(--kalxa-gold-dark);
        font-size: 26px;
    }

    @media (max-width: 650px) {

        .story-categories {
            padding: 42px 0 5px;
        }

        .story-categories-grid {
            grid-template-columns: 1fr;
        }

        .story-category-button {
            min-height: 112px;
            padding: 21px;
        }

    }


'''


# ============================================================
# HOMEPAGE CATEGORY MARKUP
# ============================================================

CATEGORY_MARKUP = '''<!-- =========================================================
     STORY CATEGORIES
========================================================== -->

<section
    class="story-categories"
    aria-labelledby="story-categories-heading"
>

    <div class="page-container">

        <div class="section-heading">
            <span>Explore the journal</span>
        </div>

        <h2
            class="story-categories-heading"
            id="story-categories-heading"
        >
            What would you like to discover?
        </h2>

        <p class="story-categories-intro">
            Explore the local people, places, events
            and experiences shaping our communities.
        </p>

        <div class="story-categories-grid">

            <a
                class="story-category-button"
                href="{{ url_for(
                    'public.story_category',
                    category_slug='local'
                ) }}"
            >
                <span>
                    <small>Local Discoveries</small>
                    <strong>
                        What is happening locally?
                    </strong>
                </span>

                <span class="category-arrow" aria-hidden="true">
                    ↗
                </span>
            </a>

            <a
                class="story-category-button"
                href="{{ url_for(
                    'public.story_category',
                    category_slug='experiences'
                ) }}"
            >
                <span>
                    <small>Events &amp; Experiences</small>
                    <strong>
                        What experiences can people attend?
                    </strong>
                </span>

                <span class="category-arrow" aria-hidden="true">
                    ↗
                </span>
            </a>

            <a
                class="story-category-button"
                href="{{ url_for(
                    'public.story_category',
                    category_slug='food'
                ) }}"
            >
                <span>
                    <small>Food &amp; Lifestyle</small>
                    <strong>
                        Where can people eat,
                        socialise and explore?
                    </strong>
                </span>

                <span class="category-arrow" aria-hidden="true">
                    ↗
                </span>
            </a>

            <a
                class="story-category-button"
                href="{{ url_for(
                    'public.story_category',
                    category_slug='creators'
                ) }}"
            >
                <span>
                    <small>Creators &amp; Culture</small>
                    <strong>
                        Who is creating, entertaining
                        and influencing locally?
                    </strong>
                </span>

                <span class="category-arrow" aria-hidden="true">
                    ↗
                </span>
            </a>

        </div>

    </div>

</section>


'''


# ============================================================
# ADMIN CATEGORY DROPDOWN
# ============================================================

ADMIN_CATEGORY_MARKUP = '''        <!-- =============================================
             EDITORIAL CATEGORY
             INDEPENDENT OF PREMIUM RESTAURANTS
        ============================================== -->

        <div class="form-section">

            <h2>Story Category</h2>

            <div class="field">

                <label for="story-category">
                    Show this story under
                </label>

                {% set current_category =
                    request.form.get(
                        'category_id',
                        article.category_id
                        if article and article.category_id
                        else ''
                    ) | string
                %}

                <select
                    id="story-category"
                    name="category_id"
                >

                    <option
                        value=""
                        {% if not current_category %}
                            selected
                        {% endif %}
                    >
                        No category (existing/default publishing)
                    </option>

                    {% for category in
                        story_categories | default([], true)
                    %}

                    <option
                        value="{{ category.id }}"
                        {% if
                            current_category == category.id|string
                        %}
                            selected
                        {% endif %}
                    >
                        {{ category.name }}
                    </option>

                    {% endfor %}

                </select>

                <div class="help">
                    Categories control where stories appear.
                    They do not change restaurant links,
                    Premium Restaurant benefits or payments.
                </div>

            </div>

        </div>


'''


# ============================================================
# UPDATE EXISTING SOURCES
# ============================================================

def update_sources():

    validate_required_files()

    edits = {}

    new_files = {}

    # ========================================================
    # 1. CREATE CATEGORY MODEL IF MISSING
    # ========================================================

    category_model_path = (
        MODELS_DIR / "story_category.py"
    )

    if not category_model_path.exists():

        new_files[category_model_path] = (
            CATEGORY_MODEL
        )

    else:

        existing = read_source(
            category_model_path
        )

        if (
            'class StoryCategory(db.Model)'
            not in existing
        ):

            raise RuntimeError(
                "Existing story_category.py does not "
                "contain the expected StoryCategory model. "
                "Review the file manually."
            )

    # ========================================================
    # 2. CREATE CATEGORY TEMPLATE IF MISSING
    # ========================================================

    category_template_path = (
        TEMPLATES_DIR / "category.html"
    )

    if not category_template_path.exists():

        new_files[category_template_path] = (
            CATEGORY_TEMPLATE
        )

    # ========================================================
    # 3. ARTICLE MODEL
    # ========================================================

    path = MODELS_DIR / "article.py"

    content = read_source(path)

    marker = (
        '    # ==========================================\n'
        '    # RESTAURANTS\n'
        '    # =========================================='
    )

    addition = '''    # ============================================================
    # EDITORIAL CATEGORY (INDEPENDENT OF PREMIUM RESTAURANTS)
    # ============================================================

    category_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "story_categories.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    category = db.relationship(
        "StoryCategory",
        back_populates="articles",
    )

'''

    if "category_id = db.Column" not in content:

        content = once_replace(
            content,
            marker,
            addition + marker,
            str(path),
        )

    edits[path] = content

    # ========================================================
    # 4. REGISTER CATEGORY MODEL
    # ========================================================

    path = MODELS_DIR / "__init__.py"

    content = read_source(path)

    category_import = (
        "from app.models.story_category "
        "import StoryCategory"
    )

    if category_import not in content:

        content = (
            category_import
            + "\n"
            + content
        )

    if '"StoryCategory"' not in content:

        content = once_replace(
            content,
            "__all__ = [",
            '__all__ = [\n    "StoryCategory",',
            str(path),
        )

    edits[path] = content

    # ========================================================
    # 5. PUBLIC ROUTES
    # ========================================================

    path = PUBLIC_ROUTES

    content = read_source(path)

    if "StoryCategory" not in content:

        content = once_replace(
            content,
            "    Article,\n    StoryAnalyticsEvent,",
            (
                "    Article,\n"
                "    StoryCategory,\n"
                "    StoryAnalyticsEvent,"
            ),
            str(path),
        )

    marker = (
        "# ============================================================\n"
        "# SUBMIT ARTICLE COMMENT\n"
        "# ============================================================"
    )

    category_route = '''# ============================================================
# EDITORIAL CATEGORY PAGE
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


'''

    if "def story_category(" not in content:

        content = once_replace(
            content,
            marker,
            category_route + marker,
            str(path),
        )

    edits[path] = content

    # ========================================================
    # 6. ADMIN ROUTES
    # ========================================================

    path = ADMIN_ROUTES

    content = read_source(path)

    if "StoryCategory" not in content:

        content = once_replace(
            content,
            (
                "    ArticleRestaurant,\n"
                "    StoryAnalyticsEvent,"
            ),
            (
                "    ArticleRestaurant,\n"
                "    StoryCategory,\n"
                "    StoryAnalyticsEvent,"
            ),
            str(path),
        )

    helper_marker = (
        "# ============================================================\n"
        "# CREATE ARTICLE\n"
        "# ============================================================"
    )

    helper = '''# ============================================================
# AVAILABLE EDITORIAL CATEGORIES
# ============================================================

def available_story_categories():

    return (
        StoryCategory.query
        .filter_by(is_active=True)
        .order_by(
            StoryCategory.display_order.asc(),
            StoryCategory.name.asc(),
        )
        .all()
    )


'''

    if "def available_story_categories(" not in content:

        content = once_replace(
            content,
            helper_marker,
            helper + helper_marker,
            str(path),
        )

    # Add categories to every existing article editor render,
    # but do not touch dashboard, authentication, or Ticketing.

    needle = '"admin/article_form.html",'

    if (
        "story_categories=available_story_categories(),"
        not in content
    ):

        count = content.count(needle)

        if count != 6:

            raise RuntimeError(
                f"{path}: expected 6 editor renders; "
                f"found {count}. "
                "No files have been changed."
            )

        content = content.replace(
            needle,
            (
                needle
                + "\n"
                + "                "
                + "story_categories="
                + "available_story_categories(),"
            ),
        )

    # Validate optional category selection.

    marker = (
        "    # --------------------------------------------------------\n"
        "    # DUPLICATE SLUG\n"
        "    # --------------------------------------------------------"
    )

    validation = '''    # --------------------------------------------------------
    # OPTIONAL EDITORIAL CATEGORY
    # --------------------------------------------------------

    raw_category_id = (
        request.form.get(
            "category_id",
            "",
        )
        .strip()
    )

    category_id = None

    if raw_category_id:

        try:

            category_id = int(
                raw_category_id
            )

        except ValueError:

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

        category_exists = (
            StoryCategory.query
            .filter_by(
                id=category_id,
                is_active=True,
            )
            .first()
        )

        if category_exists is None:

            flash(
                "Selected story category does not exist.",
                "error",
            )

            return False


'''

    if (
        'raw_category_id = ('
        not in content
        and
        'raw_category_id = request.form.get('
        not in content
    ):

        content = once_replace(
            content,
            marker,
            validation + marker,
            str(path),
        )

    marker = '''    article.article_type = (
        article_type
    )'''

    if "article.category_id = category_id" not in content:

        content = once_replace(
            content,
            marker,
            (
                marker
                + "\n\n"
                + "    article.category_id = category_id"
            ),
            str(path),
        )

    edits[path] = content

    # ========================================================
    # 7. ADMIN ARTICLE EDITOR TEMPLATE
    # ========================================================

    path = (
        TEMPLATES_DIR
        / "admin"
        / "article_form.html"
    )

    content = read_source(path)

    marker = (
        "        <!-- =============================================\n"
        "             SEO\n"
        "        ============================================== -->"
    )

    if 'id="story-category"' not in content:

        content = once_replace(
            content,
            marker,
            ADMIN_CATEGORY_MARKUP + marker,
            str(path),
        )

    edits[path] = content

    # ========================================================
    # 8. HOMEPAGE
    # ========================================================

    path = TEMPLATES_DIR / "home.html"

    content = read_source(path)

    css_marker = (
        "    /* =====================================================\n"
        "       FEATURED\n"
        "    ====================================================== */"
    )

    if ".story-categories-grid" not in content:

        content = once_replace(
            content,
            css_marker,
            CATEGORY_CSS + css_marker,
            str(path),
        )

    markup_marker = "{% if featured_article %}"

    if 'id="story-categories-heading"' not in content:

        content = once_replace(
            content,
            markup_marker,
            CATEGORY_MARKUP + markup_marker,
            str(path),
        )

    edits[path] = content

    # ========================================================
    # 9. PREFLIGHT
    # ========================================================

    # All modifications above are prepared in memory.
    # Validate the final Python sources before writing.

    import ast

    for target, source in edits.items():

        if target.suffix == ".py":

            try:

                ast.parse(
                    source,
                    filename=str(target),
                )

            except SyntaxError as error:

                raise RuntimeError(
                    f"Python syntax validation failed "
                    f"for {target}: {error}"
                ) from error

    for target, source in new_files.items():

        if target.suffix == ".py":

            ast.parse(
                source,
                filename=str(target),
            )

    # ========================================================
    # 10. APPLY CHANGES
    # ========================================================

    changed = 0

    for target, new_content in edits.items():

        old_content = read_source(target)

        if old_content == new_content:

            print(
                "UNCHANGED",
                target.relative_to(ROOT),
            )

            continue

        backup = target.with_name(
            target.name + ".stage1.bak"
        )

        if not backup.exists():

            shutil.copy2(
                target,
                backup,
            )

        target.write_text(
            new_content,
            encoding="utf-8",
        )

        print(
            "UPDATED",
            target.relative_to(ROOT),
        )

        changed += 1

    for target, content in new_files.items():

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target.write_text(
            content,
            encoding="utf-8",
        )

        print(
            "CREATED",
            target.relative_to(ROOT),
        )

        changed += 1

    print()
    print(
        f"Stage 1 complete: {changed} "
        "file(s) created or updated."
    )

    print(
        "No database migrations were run."
    )

    print(
        "Premium Restaurant integration preserved."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    update_sources()
