
"""
KALXA STORIES — R200 PERMANENT PUBLISHING INSTALLER

Self-contained installer for the existing Flask project.

Run:
    python apply_permanent_r200.py

NO permanent_r200_files DIRECTORY REQUIRED.

POLICY:
    R200 once-off per paid article.
    Permanent paid publication.
    No automatic paid article expiration.
    Stable published paid article slugs.
    Admin-controlled archive/deletion.
    Premium Restaurant integration remains independent.

SAFETY:
    - No database operations.
    - No migrations.
    - No Yoco API calls.
    - Does not overwrite paid modules with unknown code.
    - Validates changes before writing.
    - Creates source backups.
    - Prevents duplicate guard insertion.
    - Reports unresolved backend migration tasks.
"""

from pathlib import Path
import ast
import re
import shutil


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent

PRICE_RANDS = 200
PRICE_CENTS = 20000

CHANGES = {}

WARNINGS = []


# ============================================================
# FILE HELPERS
# ============================================================

def resolve_path(relative):

    relative = Path(relative)

    if relative.is_absolute():
        raise RuntimeError(
            f"Absolute path not allowed: {relative}"
        )

    if relative.parts and relative.parts[0] == "templates":
        relative = Path("app") / relative

    path = (ROOT / relative).resolve()
    root = ROOT.resolve()

    if not path.is_relative_to(root):
        raise RuntimeError(
            f"Path escapes project root: {relative}"
        )

    return path


def read_file(relative):

    path = resolve_path(relative)

    if not path.is_file():
        raise RuntimeError(
            f"Missing file: {path}"
        )

    return path.read_text(
        encoding="utf-8"
    )


def stage(relative, content):

    CHANGES[relative] = content


def replace_once(
    content,
    anchor,
    replacement,
    filename,
):

    count = content.count(anchor)

    if count != 1:
        raise RuntimeError(
            f"{filename}: expected one anchor, "
            f"found {count}. No files written."
        )

    return content.replace(
        anchor,
        replacement,
        1,
    )


# ============================================================
# REQUIRED FILES
# ============================================================

REQUIRED = [
    "app/paid/models.py",
    "app/paid/routes.py",
    "app/paid/service.py",
    "app/admin/routes.py",
    "app/public/routes.py",
    "templates/home.html",
    "templates/paid/submit.html",
    "templates/paid/admin_detail.html",
]


def validate_required_files():

    missing = []

    for filename in REQUIRED:
        path = resolve_path(filename)

        if not path.is_file():
            missing.append(str(path))

    if missing:
        raise RuntimeError(
            "Missing existing application files:\n"
            + "\n".join(missing)
            + "\n\nThis installer needs the Paid Stories "
              "module installed first."
        )


# ============================================================
# PRICE CONSTANT UPDATE
# ============================================================

# Only known, explicitly named publishing-price constants
# are changed automatically.
#
# Arbitrary numbers inside Yoco requests or verification
# are NOT replaced, since doing that without reviewing the
# backend could introduce payment vulnerabilities.

CENT_CONSTANTS = {
    "STORY_PRICE_CENTS",
    "PUBLISHING_PRICE_CENTS",
    "PAID_STORY_PRICE_CENTS",
    "PERMANENT_STORY_PRICE_CENTS",
    "STORY_PUBLISHING_PRICE_CENTS",
}

RAND_CONSTANTS = {
    "STORY_PRICE_RANDS",
    "PUBLISHING_PRICE_RANDS",
    "PAID_STORY_PRICE_RANDS",
    "PERMANENT_STORY_PRICE_RANDS",
}


def update_named_price_constants(content, filename):

    lines = content.splitlines(keepends=True)

    updated = []
    found = []

    for line in lines:

        match = re.match(
            r"^(\s*)([A-Z][A-Z0-9_]*)"
            r"(\s*(?::\s*int)?\s*=\s*)"
            r"(\d+)(\s*(?:#.*)?)(\r?\n?)$",
            line,
        )

        if match:

            indent, name, assignment, value, suffix, ending = (
                match.groups()
            )

            if name in CENT_CONSTANTS:

                line = (
                    f"{indent}{name}{assignment}"
                    f"{PRICE_CENTS}{suffix}{ending}"
                )

                found.append(name)

            elif name in RAND_CONSTANTS:

                line = (
                    f"{indent}{name}{assignment}"
                    f"{PRICE_RANDS}{suffix}{ending}"
                )

                found.append(name)

        updated.append(line)

    if found:
        print(
            "PRICE CONSTANTS:",
            filename,
            ", ".join(sorted(set(found))),
        )

    return "".join(updated), found


# ============================================================
# PAID SERVICE AND ROUTE INSPECTION
# ============================================================

def inspect_paid_backend():

    all_found = []

    for filename in [
        "app/paid/service.py",
        "app/paid/routes.py",
    ]:

        source = read_file(filename)

        updated, found = update_named_price_constants(
            source,
            filename,
        )

        stage(filename, updated)

        all_found.extend(found)

    if not all_found:

        WARNINGS.append(
            "No recognized publishing-price constant "
            "was found in service.py or routes.py. "
            "The Yoco checkout amount must be reviewed "
            "and set server-side to 20000 cents."
        )

    WARNINGS.append(
        "Confirm the Yoco payment verification compares "
        "the provider-confirmed amount and currency "
        "against the server-stored R200 payment record."
    )


# ============================================================
# HOME PAGE — PERMANENT R200 CTA
# ============================================================

PERMANENT_CTA = """
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
            PUBLISH WITH KALXA
        </span>

        <h2
            style="
                font-family:var(--kalxa-serif);
                font-size:clamp(37px,5vw,65px);
                font-weight:500;
                margin:20px 0;
            "
        >
            Your story deserves a permanent home.
        </h2>

        <p
            style="
                line-height:1.8;
                color:#c6bdb0;
                margin:20px auto 25px;
            "
        >
            Showcase your business, brand or
            creative journey on KALXA Stories.

            Publish once and keep sharing your
            story link without renewal fees.
        </p>

        <div
            style="
                font-family:var(--kalxa-serif);
                font-size:50px;
                color:#e6d4b7;
                margin-bottom:8px;
            "
        >
            R200
        </div>

        <p
            style="
                color:#c6bdb0;
                font-size:13px;
                margin-bottom:32px;
            "
        >
            Once-off publishing fee.
            No article expiry or renewal.
            Subject to editorial approval.
        </p>

        <a
            href="{{ url_for('paid_stories.submit_story') }}"
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
"""


def update_homepage():

    filename = "templates/home.html"

    source = read_file(filename)

    marker = (
        "<!-- KALXA PAID STORIES CALL TO ACTION -->"
    )

    if marker in source:

        if source.count(marker) != 1:
            raise RuntimeError(
                "Multiple Paid Stories CTA markers found."
            )

        # The known CTA contains nested divs, but no
        # nested section. Replace only its section.

        pattern = (
            r"<!-- KALXA PAID STORIES "
            r"CALL TO ACTION -->"
            r"\s*<section\b[^>]*>.*?</section>"
        )

        updated, count = re.subn(
            pattern,
            lambda match: PERMANENT_CTA.strip(),
            source,
            count=1,
            flags=re.DOTALL,
        )

        if count != 1:
            raise RuntimeError(
                "Existing Paid Stories CTA cannot be "
                "safely identified. Homepage unchanged."
            )

    else:

        closing = "{% endblock %}"

        position = source.rfind(closing)

        if position < 0:
            raise RuntimeError(
                "Homepage content block not found."
            )

        updated = (
            source[:position]
            + PERMANENT_CTA
            + "\n"
            + source[position:]
        )

    stage(filename, updated)


# ============================================================
# ARTICLE EDITOR — PERMANENT ARTICLE GUARD
# ============================================================

def update_admin_editor():

    filename = "app/admin/routes.py"

    source = read_file(filename)

    marker = "# PERMANENT PAID STORY GUARD R200"

    if marker not in source:

        anchor = (
            "    # --------------------------------------------------------\n"
            "    # ASSIGN\n"
            "    # --------------------------------------------------------"
        )

        guard = '''    # --------------------------------------------------------
    # PERMANENT PAID STORY GUARD R200
    # --------------------------------------------------------
    # Only articles associated with paid submissions are
    # affected. Premium Restaurant articles are unchanged.

    from app.paid.models import PaidStorySubmission

    if article.id is not None:

        paid_record = (
            PaidStorySubmission.query
            .filter_by(article_id=article.id)
            .first()
        )

        if paid_record is not None:

            # Paid stories cannot receive an expiry.
            if expires_at is not None:

                flash(
                    "Permanent paid stories cannot "
                    "have an expiration date.",
                    "error",
                )
                return False

            # Preserve original published URL.
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

            # Admin editor cannot bypass the paid
            # submission approval process.
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


'''

        source = replace_once(
            source,
            anchor,
            guard + anchor,
            filename,
        )

    # --------------------------------------------------------
    # QUICK-PUBLISH GUARD
    # --------------------------------------------------------

    quick_marker = (
        "# QUICK PUBLISH PAID SAFETY GUARD R200"
    )

    if quick_marker not in source:

        anchor = '''    article.status = (
        "published"
    )'''

        guard = '''    # --------------------------------------------------------
    # QUICK PUBLISH PAID SAFETY GUARD R200
    # --------------------------------------------------------
    # Paid articles must use the independent approval flow.

    from app.paid.models import PaidStorySubmission

    paid_submission = (
        PaidStorySubmission.query
        .filter_by(article_id=article.id)
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


'''

        source = replace_once(
            source,
            anchor,
            guard + anchor,
            filename,
        )

    stage(filename, source)


# ============================================================
# INSPECT LEGACY EXPIRATION REFERENCES
# ============================================================

def inspect_expiration_rules():

    # Do not blindly remove query conditions.
    #
    # Some existing expiry filters belong to Premium
    # Restaurant stories. Others may be required
    # by the earlier paid publication schema.

    filename = "app/public/routes.py"

    source = read_file(filename)

    if "PaidStoryPublication.ends_at" in source:

        WARNINGS.append(
            "app/public/routes.py still references "
            "PaidStoryPublication.ends_at. "
            "Review its query before removing the "
            "old duration-based publication column."
        )

    paid_files = [
        "app/paid/models.py",
        "app/paid/routes.py",
        "app/paid/service.py",
    ]

    legacy_terms = [
        "duration_days",
        "featured_duration_days",
        "ends_at",
        "expires_at",
        "duration_prices",
        "pricing_tiers",
    ]

    for name in paid_files:

        content = CHANGES.get(name)

        if content is None:
            content = read_file(name)

        found = [
            term
            for term in legacy_terms
            if term in content
        ]

        if found:

            WARNINGS.append(
                f"{name} contains legacy fields or logic: "
                + ", ".join(found)
                + ". Review before migration."
            )

    # Preserve all database model definitions until
    # Alembic migrations are prepared and inspected.
    stage(
        "app/public/routes.py",
        source,
    )


# ============================================================
# INSPECT PAID TEMPLATES
# ============================================================

def inspect_paid_templates():

    for filename in [
        "templates/paid/submit.html",
        "templates/paid/admin_detail.html",
    ]:

        content = read_file(filename)

        if re.search(
            r"duration|expires|renewal|R119",
            content,
            flags=re.IGNORECASE,
        ):

            WARNINGS.append(
                f"{filename} may still contain old "
                "duration or pricing text/fields. "
                "Review the form and admin display."
            )

        # Do not overwrite unknown paid templates.
        # Editing their input names without corresponding
        # backend changes could break submissions.


# ============================================================
# VALIDATE ALL PREPARED PYTHON SOURCES
# ============================================================

def validate_sources():

    for filename, content in CHANGES.items():

        if not filename.endswith(".py"):
            continue

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


# ============================================================
# WRITE BACKUPS AND FILES
# ============================================================

def apply_changes():

    updated_count = 0

    for filename, content in CHANGES.items():

        path = resolve_path(filename)

        existing = path.read_text(
            encoding="utf-8"
        )

        if existing == content:

            print(
                "UNCHANGED:",
                path.relative_to(ROOT),
            )
            continue

        backup = path.with_name(
            path.name
            + ".before_permanent_r200.bak"
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
            "UPDATED:",
            path.relative_to(ROOT),
        )

        updated_count += 1

    return updated_count


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("KALXA STORIES — R200 PERMANENT PUBLISHING")
    print("=" * 60)
    print()

    validate_required_files()

    update_homepage()

    update_admin_editor()

    inspect_paid_backend()

    inspect_expiration_rules()

    inspect_paid_templates()

    validate_sources()

    updated = apply_changes()

    print()
    print(
        f"Files updated: {updated}"
    )

    print(
        "Configured publishing policy: R200 once-off."
    )

    print(
        "Admin paid-story permanence guards installed."
    )

    print(
        "No migrations or database operations performed."
    )

    if WARNINGS:

        print()
        print("=" * 60)
        print("IMPORTANT — ITEMS REQUIRING REVIEW")
        print("=" * 60)

        for number, warning in enumerate(
            WARNINGS,
            start=1,
        ):
            print(
                f"{number}. {warning}"
            )

    print()
    print(
        "Do not deploy until payment, duration, "
        "and migration checks are complete."
    )


if __name__ == "__main__":
    main()
