
"""
KALXA STORIES — AREA NEWSLETTER INSTALLER

Safe, additive installer for location-based email subscriptions.

Run from your KALXA Stories repository root:

    python apply_area_newsletter.py

Expected project structure:

    kalxa-stories/
        apply_area_newsletter.py
        app/
            __init__.py
            newsletter/
                __init__.py
                models.py
                routes.py
            templates/
                home.html
                admin/
                    base.html
                newsletter/
                    ...

IMPORTANT:
- No database operations.
- No migrations.
- Does not modify Premium Restaurant relationships.
- Does not modify paid article publishing.
- Preserves existing Homepage and Trending Stories.
- Creates backups before modifications.
- Safe to rerun.
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
# PATH RESOLVER
# ============================================================

def resolve_path(relative):
    """
    Resolve project paths consistently.

    The KALXA Stories Flask project stores templates
    inside app/templates, not root/templates.
    """

    relative = Path(relative)

    if relative.is_absolute():
        raise RuntimeError(
            f"Absolute paths are not allowed: {relative}"
        )

    parts = relative.parts

    if parts and parts[0] == "templates":
        relative = Path("app") / relative

    resolved = (ROOT / relative).resolve()

    if not resolved.is_relative_to(ROOT.resolve()):
        raise RuntimeError(
            f"Path escapes project root: {relative}"
        )

    return resolved


# ============================================================
# READ FILE
# ============================================================

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
# VALIDATE REQUIRED FILES
# ============================================================

def validate_required_files():

    required_files = [
        "app/__init__.py",
        "app/newsletter/__init__.py",
        "app/newsletter/models.py",
        "app/newsletter/routes.py",
        "templates/home.html",
        "templates/admin/base.html",
    ]

    missing = []

    for relative in required_files:

        path = resolve_path(relative)

        if not path.is_file():
            missing.append(str(path))

    if missing:

        raise RuntimeError(
            "Required newsletter files are missing:\n"
            + "\n".join(missing)
            + "\n\nMerge the newsletter package into "
              "app/newsletter/ before running the installer."
        )


# ============================================================
# EXACT ANCHOR REPLACEMENT
# ============================================================

def replace_once(
    content,
    anchor,
    replacement,
    filename,
):

    count = content.count(anchor)

    if count != 1:

        raise RuntimeError(
            f"{filename}: expected exactly one insertion "
            f"anchor, found {count}. "
            "No source files have been modified."
        )

    return content.replace(
        anchor,
        replacement,
        1,
    )


# ============================================================
# UPDATE FLASK APPLICATION REGISTRATION
# ============================================================

def update_app_registration():

    filename = "app/__init__.py"

    content = read(filename)

    marker = (
        "app.register_blueprint(newsletter_bp)"
    )

    if marker not in content:

        anchor = "    return app"

        registration = '''    # ========================================================
    # KALXA STORIES — LOCATION NEWSLETTER
    # ========================================================
    #
    # Independent of:
    # - Premium Restaurant subscriptions
    # - KALXA Ticketing integrations
    # - Paid Story publishing
    # ========================================================

    from app.newsletter.models import StoryEmailSubscriber

    from app.newsletter.routes import newsletter_bp

    app.register_blueprint(newsletter_bp)

'''

        content = replace_once(
            content,
            anchor,
            registration + anchor,
            filename,
        )

    CHANGES[filename] = content


# ============================================================
# UPDATE HOMEPAGE
# ============================================================

def update_homepage():

    filename = "templates/home.html"

    content = read(filename)

    if 'id="kalxa-area-newsletter"' not in content:

        section = '''
<!-- =========================================================
     KALXA STORIES — LOCATION-BASED NEWSLETTER
========================================================== -->

<section
    id="kalxa-area-newsletter"
    style="
        padding:80px 0;
        background:var(--kalxa-cream);
        border-top:1px solid var(--kalxa-border);
    "
    aria-labelledby="kalxa-newsletter-title"
>

    <div
        class="page-container"
        style="
            max-width:780px;
            text-align:center;
        "
    >

        <span class="hero-label">
            LOCAL STORIES · YOUR INBOX
        </span>

        <h2
            id="kalxa-newsletter-title"
            style="
                font:500 clamp(34px,5vw,55px)/1.12
                var(--kalxa-serif);
                margin:12px 0 22px;
            "
        >
            Stay connected to your community.
        </h2>

        <p
            style="
                color:var(--kalxa-text-soft);
                line-height:1.75;
            "
        >
            Subscribe for local KALXA Stories updates.
            Choose your closest area:
            KwaMhlanga, Kwaggafontein or Siyabuswa.
        </p>

        <a
            href="{{ url_for('story_newsletter.signup_page') }}"
            style="
                display:inline-block;
                background:var(--kalxa-black);
                color:white;
                padding:16px 28px;
                margin-top:16px;
                font-weight:700;
                font-size:13px;
                text-decoration:none;
            "
        >
            Subscribe to local stories →
        </a>

    </div>

</section>

'''

        anchor = "{% endblock %}"

        position = content.rfind(anchor)

        if position == -1:

            raise RuntimeError(
                f"{filename}: no Jinja endblock found. "
                "Homepage was not modified."
            )

        content = (
            content[:position]
            + section
            + "\n"
            + content[position:]
        )

    CHANGES[filename] = content


# ============================================================
# UPDATE ADMIN NAVIGATION
# ============================================================

def update_admin_navigation():

    filename = "templates/admin/base.html"

    content = read(filename)

    marker = (
        "story_newsletter.admin_subscribers"
    )

    if marker not in content:

        anchor = "        </nav>"

        navigation_link = '''            <a
                href="{{ url_for(
                    'story_newsletter.admin_subscribers'
                ) }}"
            >
                Email Subscribers
            </a>

'''

        content = replace_once(
            content,
            anchor,
            navigation_link + anchor,
            filename,
        )

    CHANGES[filename] = content


# ============================================================
# VALIDATE PYTHON AND TEMPLATE SYNTAX
# ============================================================

def validate_changes():

    for filename, content in CHANGES.items():

        if filename.endswith(".py"):

            ast.parse(
                content,
                filename=filename,
            )

    # Confirm that the expected homepage and admin links exist.

    homepage = CHANGES.get(
        "templates/home.html",
        "",
    )

    if "story_newsletter.signup_page" not in homepage:

        raise RuntimeError(
            "Homepage newsletter URL was not inserted."
        )

    admin_base = CHANGES.get(
        "templates/admin/base.html",
        "",
    )

    if "story_newsletter.admin_subscribers" not in admin_base:

        raise RuntimeError(
            "Admin subscriber URL was not inserted."
        )


# ============================================================
# WRITE FILES WITH BACKUPS
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
            path.name + ".area-newsletter.bak"
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
    print("KALXA STORIES NEWSLETTER INSTALLATION COMPLETE")
    print("=" * 60)

    print(
        f"Files updated: {changed}"
    )

    print(
        "No database migration was performed."
    )

    print(
        "Premium Restaurant integration remains unchanged."
    )

    print(
        "Next: Validate application imports and routes."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("KALXA Stories — Area Newsletter Installer")
    print()

    # All expected files must exist before processing.
    validate_required_files()

    # Prepare changes in memory.
    update_app_registration()

    update_homepage()

    update_admin_navigation()

    # Validate before modifying existing files.
    validate_changes()

    # Only write after validations succeed.
    apply_changes()


if __name__ == "__main__":

    main()
