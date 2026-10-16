
"""
KALXA STORIES — EMAIL NOTIFICATIONS INSTALLER

Safely registers the location-based email notification module.

Run from the KALXA Stories repository root:

    python apply_story_notifications.py

EXPECTED PROJECT STRUCTURE:

    kalxa-stories/
        apply_story_notifications.py
        app/
            __init__.py
            notifications/
                __init__.py
                models.py
                routes.py
            newsletter/
                models.py
                routes.py
            templates/
                admin/
                    base.html
                notifications/
                    list.html
                    new.html
                    detail.html

FEATURES:
    - Location-based email notifications.
    - KwaMhlanga subscribers.
    - Kwaggafontein subscribers.
    - Siyabuswa subscribers.
    - All locations.
    - Admin-controlled notification campaigns.
    - Email delivery tracking.

IMPORTANT:
    - No database operations.
    - No migrations generated or applied.
    - Does not modify Premium Restaurant publishing.
    - Does not modify ArticleRestaurant.
    - Does not modify Yoco or Paid Stories.
    - Does not modify existing story content.
    - Creates backups before changing files.
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
# PATH RESOLUTION
# ============================================================

def resolve_path(relative):
    """
    Resolve repository paths.

    Existing installer paths starting with templates/
    are mapped to app/templates/.

    Paths starting with app/ remain unchanged.
    """

    relative = Path(relative)

    if relative.is_absolute():
        raise RuntimeError(
            f"Absolute paths are not allowed: {relative}"
        )

    if relative.parts and relative.parts[0] == "templates":
        relative = Path("app") / relative

    path = (ROOT / relative).resolve()

    if not path.is_relative_to(ROOT.resolve()):
        raise RuntimeError(
            f"Path escapes project root: {relative}"
        )

    return path


# ============================================================
# READ FILE
# ============================================================

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
# VALIDATE REQUIRED FILES
# ============================================================

def validate_required_files():

    required = [
        "app/__init__.py",
        "app/notifications/__init__.py",
        "app/notifications/models.py",
        "app/notifications/routes.py",
        "app/newsletter/models.py",
        "app/newsletter/routes.py",
        "templates/admin/base.html",
        "templates/notifications/list.html",
        "templates/notifications/new.html",
        "templates/notifications/detail.html",
    ]

    missing = []

    for relative in required:

        path = resolve_path(relative)

        if not path.is_file():
            missing.append(str(path))

    if missing:

        raise RuntimeError(
            "Notification installation cannot proceed.\n"
            "The following files are missing:\n\n"
            + "\n".join(missing)
            + "\n\nMerge the notification and newsletter "
              "packages into the existing app/ directory "
              "before running this installer."
        )


# ============================================================
# SAFE ANCHOR REPLACEMENT
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
            f"anchor, found {count}.\n"
            "No files have been changed."
        )

    return content.replace(
        anchor,
        replacement,
        1,
    )


# ============================================================
# REGISTER EMAIL NOTIFICATION BLUEPRINT
# ============================================================

def update_app_registration():

    filename = "app/__init__.py"

    content = read_file(filename)

    registration_marker = (
        "app.register_blueprint(notification_bp)"
    )

    if registration_marker not in content:

        anchor = "    return app"

        registration = '''    # ========================================================
    # KALXA STORIES — EMAIL NOTIFICATIONS
    # ========================================================
    #
    # Location-based campaigns for confirmed subscribers.
    #
    # Independent of:
    # - Premium Restaurant subscriptions
    # - KALXA Ticketing restaurant integration
    # - Paid Stories payment processing
    # ========================================================

    from app.notifications.models import (
        StoryNotificationCampaign,
        StoryNotificationDelivery,
    )

    from app.notifications.routes import notification_bp

    app.register_blueprint(notification_bp)

'''

        content = replace_once(
            content,
            anchor,
            registration + anchor,
            filename,
        )

    CHANGES[filename] = content


# ============================================================
# ADD ADMIN NAVIGATION LINK
# ============================================================

def update_admin_navigation():

    filename = "templates/admin/base.html"

    content = read_file(filename)

    navigation_marker = (
        "story_notifications.listing"
    )

    if navigation_marker not in content:

        anchor = "        </nav>"

        navigation = '''            <a
                href="{{ url_for(
                    'story_notifications.listing'
                ) }}"
            >
                Story Notifications
            </a>

'''

        content = replace_once(
            content,
            anchor,
            navigation + anchor,
            filename,
        )

    CHANGES[filename] = content


# ============================================================
# VALIDATE CODE BEFORE WRITING
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
                    f"{error}"
                ) from error

    app_content = CHANGES.get(
        "app/__init__.py",
        "",
    )

    if (
        "app.register_blueprint(notification_bp)"
        not in app_content
    ):

        raise RuntimeError(
            "Notification blueprint registration "
            "was not inserted."
        )

    admin_content = CHANGES.get(
        "templates/admin/base.html",
        "",
    )

    if (
        "story_notifications.listing"
        not in admin_content
    ):

        raise RuntimeError(
            "Admin notification navigation "
            "was not inserted."
        )

    # Verify the notification models and routes can at
    # least be parsed as Python source files.
    # This does not import the app or access the database.

    additional_python_files = [
        "app/notifications/models.py",
        "app/notifications/routes.py",
        "app/newsletter/models.py",
        "app/newsletter/routes.py",
    ]

    for filename in additional_python_files:

        content = read_file(filename)

        try:

            ast.parse(
                content,
                filename=filename,
            )

        except SyntaxError as error:

            raise RuntimeError(
                f"Python syntax error in required module "
                f"{filename}: {error}"
            ) from error


# ============================================================
# WRITE FILES WITH BACKUPS
# ============================================================

def apply_changes():

    changed = 0

    for filename, new_content in CHANGES.items():

        path = resolve_path(filename)

        old_content = path.read_text(
            encoding="utf-8"
        )

        if old_content == new_content:

            print(
                "UNCHANGED:",
                path.relative_to(ROOT),
            )

            continue

        backup = path.with_name(
            path.name + ".notifications.bak"
        )

        if not backup.exists():

            shutil.copy2(
                path,
                backup,
            )

        path.write_text(
            new_content,
            encoding="utf-8",
        )

        print(
            "UPDATED:",
            path.relative_to(ROOT),
        )

        changed += 1

    print()
    print("=" * 60)
    print("KALXA STORIES — NOTIFICATION INSTALLATION COMPLETE")
    print("=" * 60)

    print(
        f"Files updated: {changed}"
    )

    print(
        "Notification module registered."
    )

    print(
        "Admin navigation updated."
    )

    print(
        "No database migrations generated or applied."
    )

    print(
        "Premium Restaurant integration unchanged."
    )

    print(
        "Do not deploy until combined migrations "
        "have been reviewed and applied."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("KALXA Stories — Email Notification Installer")
    print()

    validate_required_files()

    update_app_registration()

    update_admin_navigation()

    validate_changes()

    apply_changes()


if __name__ == "__main__":

    main()
