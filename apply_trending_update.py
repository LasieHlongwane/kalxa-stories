
"""
KALXA STORIES — NEWS + TRENDING INSTALLER

Adds:
    1. Latest News in KwaNdebele category.
    2. Fifth homepage category navigation card.
    3. Trending Stories homepage section.
    4. Curated Trending Stories backend.

Compatible with:
    - Flask app/templates/ directory.
    - GitHub Codespaces.
    - Permanent R200 paid publishing.
    - Existing KALXA Premium Restaurant integration.

PUBLISHING POLICY:
    Paid stories: R200 once-off.
    Paid article publication: permanent.
    Featured visibility: separate from publication lifetime.

Run:
    python apply_trending_update.py

IMPORTANT:
    - Does not run migrations.
    - Does not seed categories.
    - Does not modify the database.
    - Does not modify ArticleRestaurant.
    - Does not change restaurant subscription eligibility.
    - Does not modify Yoco payments.
    - Backs up files before writing.
    - Can be rerun safely.
"""

from pathlib import Path
import ast
import re
import shutil


# ============================================================
# PROJECT CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent

CHANGES = {}


# ============================================================
# PATH RESOLUTION
# ============================================================

def resolve_path(relative):

    relative = Path(relative)

    if relative.is_absolute():
        raise RuntimeError(
            f"Absolute path not allowed: {relative}"
        )

    # Your KALXA Stories templates live inside app/.
    if relative.parts and relative.parts[0] == "templates":
        relative = Path("app") / relative

    path = (ROOT / relative).resolve()

    if not path.is_relative_to(ROOT.resolve()):
        raise RuntimeError(
            f"Path escapes repository: {relative}"
        )

    return path


def read_file(relative):

    path = resolve_path(relative)

    if not path.is_file():
        raise RuntimeError(
            f"Missing required file: {relative}\n"
            f"Expected location: {path}"
        )

    return path.read_text(
        encoding="utf-8"
    )


# ============================================================
# SAFE REPLACEMENT
# ============================================================

def replace_once(
    content,
    original,
    replacement,
    filename,
):

    count = content.count(original)

    if count != 1:
        raise RuntimeError(
            f"{filename}: expected exactly one anchor, "
            f"found {count}. No files written."
        )

    return content.replace(
        original,
        replacement,
        1,
    )


# ============================================================
# REQUIRED FILES
# ============================================================

REQUIRED_FILES = [
    "seed_story_categories.py",
    "app/paid/service.py",
    "app/paid/models.py",
    "app/public/routes.py",
    "app/models/article_restaurant.py",
    "templates/home.html",
]


def validate_required_files():

    missing = []

    for filename in REQUIRED_FILES:

        path = resolve_path(filename)

        if not path.is_file():
            missing.append(str(path))

    if missing:
        raise RuntimeError(
            "Missing required KALXA Stories files:\n"
            + "\n".join(missing)
            + "\n\nInstall Stage 1 and Paid Stories "
              "source files before running Trending."
        )


# ============================================================
# 1. ADD FIFTH CATEGORY TO SEEDER
# ============================================================

def update_category_seeder():

    filename = "seed_story_categories.py"

    content = read_file(filename)

    news_slug = "news-kwandebele"

    if news_slug not in content:

        # Match the existing creators tuple independently
        # of whitespace and multiline formatting.
        pattern = (
            r"(?P<indent>^[ \t]*)"
            r"(?P<entry>\("
            r"\s*['\"]creators['\"]"
            r"\s*,[^\n]*\)"
            r"\s*,?)"
        )

        matches = list(
            re.finditer(
                pattern,
                content,
                flags=re.MULTILINE,
            )
        )

        if len(matches) != 1:

            raise RuntimeError(
                f"{filename}: unable to identify exactly "
                "one creators category tuple.\n"
                "Review the category seeder."
            )

        match = matches[0]

        indent = match.group("indent")

        entry = match.group("entry")

        # Ensure the existing tuple is followed by a
        # comma before adding the next tuple.
        if not entry.rstrip().endswith(","):
            entry = entry.rstrip() + ","

        news_entry = (
            '\n'
            + indent
            + '("news-kwandebele", '
            + '"Latest news in KwaNdebele", '
            + '"News, developments and community '
              'announcements across KwaNdebele.", 5),'
        )

        content = (
            content[:match.start("entry")]
            + entry
            + news_entry
            + content[match.end("entry"):]
        )

    content = content.replace(
        "Four KALXA Stories categories are ready.",
        "Five KALXA Stories categories are ready.",
    )

    CHANGES[filename] = content


# ============================================================
# 2. ADD NEWS CATEGORY TO PAID SUBMISSION OPTIONS
# ============================================================

def update_paid_categories():

    filename = "app/paid/service.py"

    content = read_file(filename)

    if "'news-kwandebele':" not in content and (
        '"news-kwandebele":' not in content
    ):

        # Support either single or double quoted dictionary
        # keys and values.
        pattern = (
            r"(?P<indent>^[ \t]*)"
            r"(?P<entry>"
            r"['\"]creators['\"]\s*:\s*"
            r"['\"][^\n]*?['\"]\s*,?)"
        )

        matches = list(
            re.finditer(
                pattern,
                content,
                flags=re.MULTILINE,
            )
        )

        if len(matches) != 1:

            raise RuntimeError(
                f"{filename}: could not locate exactly "
                "one creators category dictionary entry.\n"
                "No files have been modified."
            )

        match = matches[0]

        entry = match.group("entry")

        if not entry.rstrip().endswith(","):
            entry = entry.rstrip() + ","

        addition = (
            "\n"
            + match.group("indent")
            + "'news-kwandebele': "
            + "'Latest news in KwaNdebele',"
        )

        content = (
            content[:match.start("entry")]
            + entry
            + addition
            + content[match.end("entry"):]
        )

    CHANGES[filename] = content


# ============================================================
# 3. FIFTH CATEGORY HOMEPAGE CARD
# ============================================================

NEWS_CARD = '''
            <a
                class="story-category-button"
                href="{{ url_for(
                    'public.story_category',
                    category_slug='news-kwandebele'
                ) }}"
            >
                <span>
                    <small>KwaNdebele News</small>

                    <strong>
                        Latest news in KwaNdebele
                    </strong>
                </span>

                <span
                    class="category-arrow"
                    aria-hidden="true"
                >
                    ↗
                </span>
            </a>
'''


# ============================================================
# 4. TRENDING STORIES HOMEPAGE SECTION
# ============================================================

TRENDING_SECTION = '''
<!-- =========================================================
     KALXA TRENDING STORIES

     Curated restaurant-linked stories and featured paid stories.

     Featured visibility is independent of the permanent
     publication lifetime of a paid story.
========================================================== -->

{% if trending_articles %}

<section
    class="latest-section trending-section"
    aria-labelledby="trending-stories-heading"
>

    <div class="page-container">

        <div class="latest-header">

            <div class="latest-header-copy">

                <span>
                    From our community
                </span>

                <h2
                    class="latest-heading-title"
                    id="trending-stories-heading"
                >
                    Trending Stories
                </h2>

            </div>

            <a href="{{ url_for('public.stories') }}">
                Explore all stories →
            </a>

        </div>

        <div class="story-grid">

            {% for article in trending_articles %}

            <article class="story-card">

                <a
                    class="story-image-link"
                    href="{{ url_for(
                        'public.article_detail',
                        slug=article.slug
                    ) }}"
                    aria-label="Read {{ article.title }}"
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

                        <span>
                            {{ article.category.name
                               if article.category
                               else article.article_type
                                   .replace('_', ' ')
                                   .title() }}
                        </span>

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

                    <p>
                        {{ article.excerpt }}
                    </p>

                    {% endif %}

                    <a
                        class="read-link"
                        href="{{ url_for(
                            'public.article_detail',
                            slug=article.slug
                        ) }}"
                    >
                        Read story <span>→</span>
                    </a>

                </div>

            </article>

            {% endfor %}

        </div>

    </div>

</section>

{% endif %}
'''


# ============================================================
# HOMEPAGE UPDATE
# ============================================================

def update_homepage():

    filename = "templates/home.html"

    content = read_file(filename)

    # --------------------------------------------------------
    # INSERT FIFTH CATEGORY
    # --------------------------------------------------------

    if "category_slug='news-kwandebele'" not in content:

        category_end = "</section>"

        # Find the existing Stage 1 category section.
        category_marker = 'id="story-categories-heading"'

        marker_pos = content.find(category_marker)

        if marker_pos == -1:

            raise RuntimeError(
                "Homepage is missing Stage 1 "
                "category navigation.\n"
                "Run apply_stage1.py first."
            )

        section_end = content.find(
            category_end,
            marker_pos,
        )

        if section_end == -1:

            raise RuntimeError(
                "Could not locate category section end."
            )

        # Insert before category-grid closing div.
        # This preserves existing category buttons.
        category_html = content[
            marker_pos:section_end
        ]

        # Locate the final anchor, which is the creators card.
        creator_marker = "category_slug='creators'"

        creator_pos = category_html.find(
            creator_marker
        )

        if creator_pos == -1:

            raise RuntimeError(
                "Could not locate creators category card."
            )

        # Find the closing </a> for creators.
        creator_absolute = (
            marker_pos + creator_pos
        )

        creator_close = content.find(
            "</a>",
            creator_absolute,
        )

        if (
            creator_close == -1
            or creator_close >= section_end
        ):

            raise RuntimeError(
                "Could not identify creators card end."
            )

        creator_close += len("</a>")

        content = (
            content[:creator_close]
            + "\n"
            + NEWS_CARD
            + content[creator_close:]
        )

    # --------------------------------------------------------
    # INSERT TRENDING AFTER CATEGORY SECTION
    # --------------------------------------------------------

    if 'id="trending-stories-heading"' not in content:

        category_marker = 'id="story-categories-heading"'

        category_pos = content.find(
            category_marker
        )

        section_end = content.find(
            "</section>",
            category_pos,
        )

        if (
            category_pos == -1
            or section_end == -1
        ):

            raise RuntimeError(
                "Cannot locate homepage category section "
                "for Trending placement."
            )

        section_end += len("</section>")

        content = (
            content[:section_end]
            + "\n\n"
            + TRENDING_SECTION
            + "\n"
            + content[section_end:]
        )

    CHANGES[filename] = content


# ============================================================
# 5. TRENDING BACKEND HELPER
# ============================================================

TRENDING_HELPER = '''
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
'''


# ============================================================
# PUBLIC ROUTES UPDATE
# ============================================================

def update_public_routes():

    filename = "app/public/routes.py"

    content = read_file(filename)

    helper_marker = (
        "def kalxa_trending_articles("
    )

    if helper_marker not in content:

        marker = (
            "# ============================================================\n"
            "# HOME\n"
            "# ============================================================"
        )

        content = replace_once(
            content,
            marker,
            TRENDING_HELPER + "\n" + marker,
            filename,
        )

    # Add Trending articles only to the existing homepage
    # render context.
    #
    # Do not modify restaurant detail routes,
    # attribution, comments, or analytics.

    trending_argument = (
        "trending_articles=kalxa_trending_articles(),"
    )

    if trending_argument not in content:

        # Locate the public homepage function.
        home_match = re.search(
            r"^def home\(\):",
            content,
            flags=re.MULTILINE,
        )

        if not home_match:

            raise RuntimeError(
                "Could not locate def home() "
                "in app/public/routes.py."
            )

        # Find the next top-level function or route
        # following home().
        next_function = re.search(
            r"^(?:@public_bp\.route|def )",
            content[home_match.end():],
            flags=re.MULTILINE,
        )

        if next_function:

            end = (
                home_match.end()
                + next_function.start()
            )

        else:

            end = len(content)

        home_code = content[
            home_match.start():end
        ]

        needle = (
            "featured_article=featured_article,"
        )

        if home_code.count(needle) != 1:

            raise RuntimeError(
                "Could not safely locate the homepage "
                "featured_article render argument."
            )

        home_code = home_code.replace(
            needle,
            (
                needle
                + "\n        "
                + trending_argument
            ),
            1,
        )

        content = (
            content[:home_match.start()]
            + home_code
            + content[end:]
        )

    CHANGES[filename] = content


# ============================================================
# VALIDATE PREPARED CHANGES
# ============================================================

def validate_changes():

    for filename, content in CHANGES.items():

        if filename.endswith(".py"):

            try:

                ast.parse(
                    content,
                    filename=filename,
                )

            except SyntaxError as error:

                raise RuntimeError(
                    f"Python syntax error in {filename}: "
                    f"{error}. No files written."
                ) from error

    homepage = CHANGES[
        "templates/home.html"
    ]

    if "category_slug='news-kwandebele'" not in homepage:
        raise RuntimeError(
            "KwaNdebele news card missing."
        )

    if 'id="trending-stories-heading"' not in homepage:
        raise RuntimeError(
            "Trending section missing."
        )

    routes = CHANGES[
        "app/public/routes.py"
    ]

    if "def kalxa_trending_articles(" not in routes:
        raise RuntimeError(
            "Trending backend helper missing."
        )

    if (
        "trending_articles=kalxa_trending_articles(),"
        not in routes
    ):
        raise RuntimeError(
            "Homepage Trending template argument missing."
        )


# ============================================================
# APPLY CHANGES WITH BACKUPS
# ============================================================

def apply_changes():

    changed = 0

    for filename, content in CHANGES.items():

        path = resolve_path(filename)

        old_content = path.read_text(
            encoding="utf-8"
        )

        if old_content == content:

            print(
                "UNCHANGED",
                path.relative_to(ROOT),
            )
            continue

        backup = path.with_name(
            path.name + ".trending.bak"
        )

        if not backup.exists():

            shutil.copy2(
                path,
                backup,
            )

        path.write_text(
            content,
            encoding="utf-8",
        )

        print(
            "UPDATED",
            path.relative_to(ROOT),
            "(backup:",
            backup.name + ")",
        )

        changed += 1

    print()
    print("=" * 60)
    print("KALXA STORIES — TRENDING UPDATE COMPLETE")
    print("=" * 60)

    print(
        f"Files updated: {changed}"
    )

    print(
        "Five-category navigation prepared."
    )

    print(
        "Trending Stories homepage section prepared."
    )

    print(
        "Permanent paid publishing preserved."
    )

    print(
        "No database migrations or seeding performed."
    )

    print(
        "Premium Restaurant publishing integration "
        "was not modified."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("KALXA Stories — KwaNdebele News + Trending")
    print()

    validate_required_files()

    update_category_seeder()

    update_paid_categories()

    update_homepage()

    update_public_routes()

    validate_changes()

    apply_changes()


if __name__ == "__main__":

    main()
