
"""
KALXA STORIES — PAID PUBLISHING INSTALLER

Safely installs Paid Stories integration into the existing
KALXA Stories Flask application.

Run from the repository root:

    python apply_paid_stories.py

PROJECT STRUCTURE:

    kalxa-stories/
        apply_paid_stories.py
        app/
            __init__.py
            paid/
                __init__.py
                models.py
                routes.py
            public/
                routes.py
            admin/
                routes.py
            templates/
                home.html
                admin/
                    base.html

PUBLISHING POLICY:
    R200 once-off per article.
    No automatic expiration for paid articles.
    Admin approval required.
    Permanent published story URLs.

IMPORTANT:
    - Does not run migrations.
    - Does not modify the database.
    - Does not modify ArticleRestaurant.
    - Does not modify the Ticketing API.
    - Does not modify Premium Restaurant eligibility.
    - Does not require featured_helper.py.txt.
    - Preserves existing Trending Stories integration.
    - Creates backups of modified source files.
    - Can be rerun without duplicate insertions.
"""

from pathlib import Path
import ast
import shutil


# ============================================================
# PROJECT ROOT
# ============================================================

ROOT = Path(__file__).resolve().parent

CHANGES = {}


# ============================================================
# PATH RESOLUTION
# ============================================================

def resolve_path(relative):
    """
    Map installer template paths to app/templates/.

    All other application paths remain unchanged.
    """

    relative = Path(relative)

    if relative.is_absolute():
        raise RuntimeError(
            f"Absolute path not allowed: {relative}"
        )

    if relative.parts and relative.parts[0] == "templates":
        relative = Path("app") / relative

    path = (ROOT / relative).resolve()

    if not path.is_relative_to(ROOT.resolve()):
        raise RuntimeError(
            f"Path is outside repository: {relative}"
        )

    return path


def read(relative):

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
# REQUIRED FILES
# ============================================================

def validate_required_files():

    required = [
        "app/__init__.py",
        "app/paid/__init__.py",
        "app/paid/models.py",
        "app/paid/routes.py",
        "app/public/routes.py",
        "app/admin/routes.py",
        "templates/home.html",
        "templates/admin/base.html",
    ]

    missing = []

    for filename in required:

        path = resolve_path(filename)

        if not path.is_file():
            missing.append(str(path))

    if missing:

        raise RuntimeError(
            "Required files are missing:\n"
            + "\n".join(missing)
            + "\n\nMerge the Paid Stories package "
              "into app/paid/ before running this script."
        )


# ============================================================
# SAFE STRING REPLACEMENT
# ============================================================

def replace_once(
    content,
    needle,
    replacement,
    filename,
):

    count = content.count(needle)

    if count != 1:

        raise RuntimeError(
            f"{filename}: expected exactly one anchor "
            f"but found {count}.\n"
            "No source files have been written."
        )

    return content.replace(
        needle,
        replacement,
        1,
    )


# ============================================================
# PAID MODEL AND BLUEPRINT REGISTRATION
# ============================================================

def update_app_registration():

    filename = "app/__init__.py"

    content = read(filename)

    marker = "app.register_blueprint(paid_bp)"

    if marker not in content:

        registration = '''    # ========================================================
    # KALXA STORIES — INDEPENDENT PAID PUBLISHING
    # ========================================================
    #
    # Businesses and creators:
    # R200 once-off permanent publication.
    #
    # Existing Premium Restaurant integration is unaffected.
    # ========================================================

    from app.paid import models as paid_models  # noqa: F401

    from app.paid.routes import paid_bp

    app.register_blueprint(paid_bp)

'''

        anchor = "    return app"

        content = replace_once(
            content,
            anchor,
            registration + anchor,
            filename,
        )

    CHANGES[filename] = content


# ============================================================
# PAID SUBMISSIONS ADMIN LINK
# ============================================================

def update_admin_navigation():

    filename = "templates/admin/base.html"

    content = read(filename)

    marker = "paid_stories.admin_submissions"

    if marker not in content:

        navigation = '''            <a
                href="{{ url_for(
                    'paid_stories.admin_submissions'
                ) }}"
            >
                Paid Submissions
            </a>

'''

        anchor = "        </nav>"

        content = replace_once(
            content,
            anchor,
            navigation + anchor,
            filename,
        )

    CHANGES[filename] = content


# ============================================================
# PERMANENT PUBLISHING HOMEPAGE CTA
# ============================================================

PERMANENT_CTA = '''
<!-- KALXA PAID STORIES CALL TO ACTION -->

<section
    id="kalxa-paid-stories-cta"
    style="
        background:var(--kalxa-black);
        color:#f5efe3;
        padding:85px 0;
        text-align:center;
    "
>

    <div
        class="page-container"
        style="max-width:760px"
    >

        <span
            style="
                font-size:11px;
                letter-spacing:2px;
                text-transform:uppercase;
                color:#d0ab70;
            "
        >
            Publish with KALXA
        </span>

        <h2
            style="
                font-family:var(--kalxa-serif);
                font-size:clamp(37px,5vw,65px);
                font-weight:500;
                line-height:1.13;
                margin:20px 0;
            "
        >
            Have a story worth sharing?
        </h2>

        <p
            style="
                font-size:16px;
                line-height:1.8;
                color:#c6bdb0;
                margin:20px auto 25px;
            "
        >
            Give your business, brand or creative journey
            a permanent home on KALXA Stories.
            Publish once and share your story link
            whenever you want.
        </p>

        <div
            style="
                font-family:var(--kalxa-serif);
                font-size:48px;
                color:#e6d4b7;
                margin:0 0 8px;
            "
        >
            R200
        </div>

        <p
            style="
                color:#c6bdb0;
                font-size:13px;
                margin:0 0 32px;
            "
        >
            Once-off publishing fee.
            No monthly subscription or article renewal.
            Subject to editorial approval.
        </p>

        <a
            href="{{ url_for(
                'paid_stories.submit_story'
            ) }}"
            style="
                display:inline-block;
                background:#e6d4b7;
                color:#181511;
                padding:16px 28px;
                font-weight:700;
                text-decoration:none;
            "
        >
            Submit your story →
        </a>

    </div>

</section>
'''


def update_homepage():

    filename = "templates/home.html"

    content = read(filename)

    start_marker = (
        "<!-- KALXA PAID STORIES CALL TO ACTION -->"
    )

    end_marker = "</section>"

    if start_marker in content:

        # Update existing CTA instead of duplicating it.
        start = content.index(start_marker)

        end = content.find(
            end_marker,
            start,
        )

        if end == -1:

            raise RuntimeError(
                "Existing Paid Stories CTA does not "
                "have a closing section tag."
            )

        end += len(end_marker)

        existing_cta = content[start:end]

        if (
            'id="kalxa-paid-stories-cta"'
            not in existing_cta
            and
            "choose a publishing duration"
            not in existing_cta
        ):

            raise RuntimeError(
                "Existing Paid Stories CTA differs "
                "from the expected version. "
                "Review it manually before replacing."
            )

        content = (
            content[:start]
            + PERMANENT_CTA
            + content[end:]
        )

    else:

        anchor = "{% endblock %}"

        position = content.rfind(anchor)

        if position == -1:

            raise RuntimeError(
                "Homepage has no Jinja endblock."
            )

        content = (
            content[:position]
            + PERMANENT_CTA
            + "\n"
            + content[position:]
        )

    CHANGES[filename] = content


# ============================================================
# FEATURED STORIES INTEGRATION
# ============================================================

def update_featured_ordering():
    """
    Preserve existing featured-story ordering.

    The old Paid Stories installer required an additional
    file named featured_helper.py.txt.

    That legacy dependency has been removed.

    Featured placement and Trending Stories should be
    managed by the separate Trending Stories module.

    This function does not add new featured ordering,
    modify article queries, or change restaurant articles.
    """

    filename = "app/public/routes.py"

    content = read(filename)

    helper_marker = (
        "def order_by_active_paid_featured(articles):"
    )

    call_marker = (
        "articles = order_by_active_paid_featured(articles)"
    )

    # Detect an existing helper without modifying it.
    if helper_marker in content:

        print(
            "Existing featured-story helper detected. "
            "Preserving it."
        )

    elif call_marker in content:

        raise RuntimeError(
            "Featured ordering calls exist, but "
            "order_by_active_paid_featured() "
            "is missing.\n"
            "Review app/public/routes.py before proceeding."
        )

    else:

        print(
            "Skipping legacy paid featured ordering. "
            "Trending Stories handles featured articles."
        )

    CHANGES[filename] = content


# ============================================================
# PAID PUBLICATION SAFEGUARD
# ============================================================

def update_admin_publishing_guard():

    filename = "app/admin/routes.py"

    content = read(filename)

    marker = (
        "# PAID ARTICLE LIFECYCLE GUARD"
    )

    if marker not in content:

        anchor = '''    # --------------------------------------------------------
    # ASSIGN
    # --------------------------------------------------------'''

        guard = '''    # --------------------------------------------------------
    # PAID ARTICLE LIFECYCLE GUARD
    # --------------------------------------------------------
    #
    # Existing Premium Restaurant articles are unaffected.
    #
    # Paid articles must not be published before their
    # payment and review lifecycle has been completed.
    # --------------------------------------------------------

    from app.paid.models import PaidStorySubmission

    if article.id is not None:

        paid_submission = (
            PaidStorySubmission.query
            .filter_by(
                article_id=article.id
            )
            .first()
        )

        if (
            paid_submission is not None
            and status == "published"
            and paid_submission.review_status
                != "published"
        ):

            flash(
                "Publish paid stories through the "
                "Paid Submissions admin screen after "
                "payment verification.",
                "error",
            )

            return False


'''

        content = replace_once(
            content,
            anchor,
            guard + anchor,
            filename,
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

            except SyntaxError as exc:

                raise RuntimeError(
                    f"Python syntax error in {filename}: "
                    f"{exc}"
                ) from exc

    app_source = CHANGES.get(
        "app/__init__.py",
        "",
    )

    if "app.register_blueprint(paid_bp)" not in app_source:

        raise RuntimeError(
            "Paid blueprint registration is missing."
        )

    admin_source = CHANGES.get(
        "app/admin/routes.py",
        "",
    )

    if "# PAID ARTICLE LIFECYCLE GUARD" not in admin_source:

        raise RuntimeError(
            "Paid publishing guard is missing."
        )


# ============================================================
# WRITE ALL CHANGES
# ============================================================

def apply_changes():

    changed = 0

    for filename, content in CHANGES.items():

        path = resolve_path(filename)

        existing = path.read_text(
            encoding="utf-8"
        )

        if existing == content:

            print(
                "UNCHANGED",
                path.relative_to(ROOT),
            )

            continue

        backup = path.with_name(
            path.name + ".paid.bak"
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
        )

        changed += 1

    print()
    print("=" * 60)
    print("KALXA STORIES — PAID PUBLISHING INSTALLATION")
    print("=" * 60)

    print(
        f"Files updated: {changed}"
    )

    print(
        "Publishing policy: R200 once-off."
    )

    print(
        "Article lifetime: permanent."
    )

    print(
        "No database migrations performed."
    )

    print(
        "Premium Restaurant integration preserved."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("KALXA Stories — Paid Publishing Installer")
    print()

    validate_required_files()

    update_app_registration()

    update_admin_navigation()

    update_homepage()

    update_featured_ordering()

    update_admin_publishing_guard()

    validate_changes()

    apply_changes()


if __name__ == "__main__":

    main()
