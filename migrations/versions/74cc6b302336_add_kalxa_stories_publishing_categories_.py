
"""
Add KALXA Stories publishing, categories, subscribers and notifications.

Revision ID: 74cc6b402336
Revises: 1aada11aef99
Create Date: 2026-10-15 23:17:17.313599

FEATURES:
- Editorial story categories
- R200 once-off paid story publishing
- Permanent paid article publication
- Yoco payment and webhook records
- Curated featured placements
- Location-based email subscribers
- Story notification campaigns and deliveries
- Restaurant analytics events

IMPORTANT:
- Existing Premium Restaurant tables are preserved.
- Existing ArticleRestaurant relationships are unchanged.
- Existing articles remain intact.
- Paid publications have no automatic expiration.
- Category assignment is optional for existing articles.
- Migration does not seed categories or send emails.
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# ALEMBIC REVISION
# ============================================================

revision = "74cc6b402336"

down_revision = "1aada11aef99"

branch_labels = None

depends_on = None


# ============================================================
# CONSTRAINT NAMES
# ============================================================

ARTICLE_CATEGORY_FK = (
    "fk_articles_category_id_story_categories"
)

NOTIFICATION_DELIVERY_UNIQUE = (
    "uq_story_notification_campaign_subscriber"
)


# ============================================================
# INDEX HELPER
# ============================================================

def create_indexes(table_name, columns, unique_columns=()):
    """
    Create named indexes for a newly created table.

    Index names match Flask-SQLAlchemy's common
    ix_<table>_<column> naming convention.
    """

    unique_columns = set(unique_columns)

    for column in columns:

        op.create_index(
            f"ix_{table_name}_{column}",
            table_name,
            [column],
            unique=column in unique_columns,
        )


def drop_indexes(table_name, columns):

    for column in reversed(columns):

        op.drop_index(
            f"ix_{table_name}_{column}",
            table_name=table_name,
        )


# ============================================================
# INDEX CONFIGURATION
# ============================================================

RESTAURANT_ANALYTICS_INDEXES = [
    "created_at",
    "event_type",
    "experience_post_id",
    "restaurant_advert_id",
    "session_id",
    "source",
    "source_session_id",
    "source_story_id",
]

STORY_CATEGORY_INDEXES = [
    "slug",
]

STORY_SUBSCRIBER_INDEXES = [
    "area",
    "email",
    "status",
]

NOTIFICATION_CAMPAIGN_INDEXES = [
    "article_id",
    "status",
]

NOTIFICATION_DELIVERY_INDEXES = [
    "campaign_id",
    "status",
    "subscriber_id",
]

PAID_SUBMISSION_INDEXES = [
    "payment_status",
    "reference",
    "review_status",
]

PAID_PAYMENT_INDEXES = [
    "submission_id",
]


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # ========================================================
    # 1. YOCO WEBHOOK IDEMPOTENCY RECORDS
    # ========================================================

    op.create_table(
        "paid_story_webhook_events",

        sa.Column(
            "event_id",
            sa.String(length=200),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.PrimaryKeyConstraint("event_id"),
    )

    # ========================================================
    # 2. RESTAURANT ANALYTICS
    # ========================================================
    #
    # This table was detected as missing by Alembic.
    #
    # It is separate from the Premium Restaurant
    # publication and subscription relationships.
    #
    # Verify it does not already exist in production
    # before applying this migration to Neon.
    # ========================================================

    op.create_table(
        "restaurant_analytics_events",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "restaurant_advert_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "event_type",
            sa.String(length=50),
            nullable=False,
        ),

        sa.Column(
            "experience_post_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
        ),

        sa.Column(
            "source_story_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "source_session_id",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "session_id",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "event_metadata",
            sa.JSON(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    create_indexes(
        "restaurant_analytics_events",
        RESTAURANT_ANALYTICS_INDEXES,
    )

    # ========================================================
    # 3. EDITORIAL STORY CATEGORIES
    # ========================================================

    op.create_table(
        "story_categories",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "name",
            sa.String(length=120),
            nullable=False,
        ),

        sa.Column(
            "slug",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
        ),

        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
        ),
    )

    create_indexes(
        "story_categories",
        STORY_CATEGORY_INDEXES,
        unique_columns=("slug",),
    )

    # ========================================================
    # 4. LOCATION-BASED EMAIL SUBSCRIBERS
    # ========================================================

    op.create_table(
        "story_email_subscribers",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "email",
            sa.String(length=254),
            nullable=False,
        ),

        sa.Column(
            "area",
            sa.String(length=40),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
        ),

        sa.Column(
            "consent_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "unsubscribed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )

    create_indexes(
        "story_email_subscribers",
        STORY_SUBSCRIBER_INDEXES,
        unique_columns=("email",),
    )

    # ========================================================
    # 5. STORY NOTIFICATION CAMPAIGNS
    # ========================================================

    op.create_table(
        "story_notification_campaigns",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "article_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "article_title",
            sa.String(length=250),
            nullable=False,
        ),

        sa.Column(
            "article_slug",
            sa.String(length=300),
            nullable=False,
        ),

        sa.Column(
            "subject",
            sa.String(length=200),
            nullable=False,
        ),

        sa.Column(
            "message",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "target_locations",
            sa.String(length=150),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
        ),

        sa.Column(
            "total_recipients",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    create_indexes(
        "story_notification_campaigns",
        NOTIFICATION_CAMPAIGN_INDEXES,
    )

    # ========================================================
    # 6. INDIVIDUAL NOTIFICATION DELIVERIES
    # ========================================================

    op.create_table(
        "story_notification_deliveries",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "campaign_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "subscriber_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
        ),

        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "last_error",
            sa.String(length=240),
            nullable=True,
        ),

        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["story_notification_campaigns.id"],
            ondelete="CASCADE",
            name="fk_story_notification_deliveries_campaign",
        ),

        sa.ForeignKeyConstraint(
            ["subscriber_id"],
            ["story_email_subscribers.id"],
            ondelete="RESTRICT",
            name="fk_story_notification_deliveries_subscriber",
        ),

        sa.UniqueConstraint(
            "campaign_id",
            "subscriber_id",
            name=NOTIFICATION_DELIVERY_UNIQUE,
        ),
    )

    create_indexes(
        "story_notification_deliveries",
        NOTIFICATION_DELIVERY_INDEXES,
    )

    # ========================================================
    # 7. PERMANENT PAID STORY SUBMISSIONS
    # ========================================================
    #
    # Amounts are recorded in cents.
    #
    # R200 = 20000 cents.
    #
    # The migration deliberately does not assign a
    # hard-coded price default to the database.
    #
    # The publishing service must validate the amount
    # server-side at checkout and payment verification.
    # ========================================================

    op.create_table(
        "paid_story_submissions",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "reference",
            sa.String(length=40),
            nullable=False,
        ),

        sa.Column(
            "access_token_hash",
            sa.String(length=64),
            nullable=False,
        ),

        sa.Column(
            "applicant_type",
            sa.String(length=20),
            nullable=False,
        ),

        sa.Column(
            "applicant_name",
            sa.String(length=150),
            nullable=False,
        ),

        sa.Column(
            "contact_name",
            sa.String(length=150),
            nullable=False,
        ),

        sa.Column(
            "email",
            sa.String(length=254),
            nullable=False,
        ),

        sa.Column(
            "whatsapp",
            sa.String(length=35),
            nullable=False,
        ),

        sa.Column(
            "location",
            sa.String(length=180),
            nullable=False,
        ),

        sa.Column(
            "category_slug",
            sa.String(length=40),
            nullable=False,
        ),

        sa.Column(
            "title",
            sa.String(length=250),
            nullable=False,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "website",
            sa.String(length=500),
            nullable=True,
        ),

        sa.Column(
            "amount_cents",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "payment_status",
            sa.String(length=25),
            nullable=False,
        ),

        sa.Column(
            "review_status",
            sa.String(length=25),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "article_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "admin_notes",
            sa.Text(),
            nullable=True,
        ),

        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            ondelete="SET NULL",
            name="fk_paid_story_submissions_article",
        ),

        sa.UniqueConstraint(
            "article_id",
            name="uq_paid_story_submissions_article_id",
        ),
    )

    create_indexes(
        "paid_story_submissions",
        PAID_SUBMISSION_INDEXES,
        unique_columns=("reference",),
    )

    # ========================================================
    # 8. PAID STORY PAYMENTS
    # ========================================================

    op.create_table(
        "paid_story_payments",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "submission_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "checkout_id",
            sa.String(length=160),
            nullable=True,
        ),

        sa.Column(
            "checkout_url",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "payment_id",
            sa.String(length=160),
            nullable=True,
        ),

        sa.Column(
            "amount_cents",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=25),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["paid_story_submissions.id"],
            name="fk_paid_story_payments_submission",
        ),

        sa.UniqueConstraint(
            "checkout_id",
            name="uq_paid_story_payments_checkout_id",
        ),

        sa.UniqueConstraint(
            "payment_id",
            name="uq_paid_story_payments_payment_id",
        ),
    )

    create_indexes(
        "paid_story_payments",
        PAID_PAYMENT_INDEXES,
    )

    # ========================================================
    # 9. PERMANENT PAID STORY PUBLICATIONS
    # ========================================================
    #
    # No ends_at or expiry date column.
    #
    # starts_at records the publication start.
    #
    # featured_until is separate from the article
    # lifetime, and may be NULL.
    # ========================================================

    op.create_table(
        "paid_story_publications",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "submission_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "article_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "starts_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "featured_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["paid_story_submissions.id"],
            name="fk_paid_story_publications_submission",
        ),

        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name="fk_paid_story_publications_article",
        ),

        sa.UniqueConstraint(
            "submission_id",
            name="uq_paid_story_publications_submission",
        ),

        sa.UniqueConstraint(
            "article_id",
            name="uq_paid_story_publications_article",
        ),
    )

    # ========================================================
    # 10. ADD OPTIONAL CATEGORY TO EXISTING ARTICLES
    # ========================================================
    #
    # Existing articles are retained.
    #
    # Existing articles receive NULL category_id.
    #
    # This does not alter ArticleRestaurant.
    # ========================================================

    with op.batch_alter_table(
        "articles",
        schema=None,
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "category_id",
                sa.Integer(),
                nullable=True,
            )
        )

        batch_op.create_index(
            "ix_articles_category_id",
            ["category_id"],
            unique=False,
        )

        batch_op.create_foreign_key(
            ARTICLE_CATEGORY_FK,
            "story_categories",
            ["category_id"],
            ["id"],
            ondelete="SET NULL",
        )


# ============================================================
# DOWNGRADE
# ============================================================
#
# WARNING:
# Downgrade removes the new Paid Stories, subscriber,
# notification, category and analytics records.
#
# Only use this in a controlled environment after
# making a database backup and reviewing its impact.
# ============================================================

def downgrade():

    # ========================================================
    # 1. REMOVE ARTICLE CATEGORY ASSOCIATION
    # ========================================================

    with op.batch_alter_table(
        "articles",
        schema=None,
    ) as batch_op:

        batch_op.drop_constraint(
            ARTICLE_CATEGORY_FK,
            type_="foreignkey",
        )

        batch_op.drop_index(
            "ix_articles_category_id"
        )

        batch_op.drop_column(
            "category_id"
        )

    # ========================================================
    # 2. REMOVE PAID STORY PUBLICATIONS
    # ========================================================

    op.drop_table(
        "paid_story_publications"
    )

    # ========================================================
    # 3. REMOVE PAID STORY PAYMENTS
    # ========================================================

    drop_indexes(
        "paid_story_payments",
        PAID_PAYMENT_INDEXES,
    )

    op.drop_table(
        "paid_story_payments"
    )

    # ========================================================
    # 4. REMOVE PAID STORY SUBMISSIONS
    # ========================================================

    drop_indexes(
        "paid_story_submissions",
        PAID_SUBMISSION_INDEXES,
    )

    op.drop_table(
        "paid_story_submissions"
    )

    # ========================================================
    # 5. REMOVE NOTIFICATION DELIVERIES
    # ========================================================

    drop_indexes(
        "story_notification_deliveries",
        NOTIFICATION_DELIVERY_INDEXES,
    )

    op.drop_table(
        "story_notification_deliveries"
    )

    # ========================================================
    # 6. REMOVE NOTIFICATION CAMPAIGNS
    # ========================================================

    drop_indexes(
        "story_notification_campaigns",
        NOTIFICATION_CAMPAIGN_INDEXES,
    )

    op.drop_table(
        "story_notification_campaigns"
    )

    # ========================================================
    # 7. REMOVE EMAIL SUBSCRIBERS
    # ========================================================

    drop_indexes(
        "story_email_subscribers",
        STORY_SUBSCRIBER_INDEXES,
    )

    op.drop_table(
        "story_email_subscribers"
    )

    # ========================================================
    # 8. REMOVE EDITORIAL CATEGORIES
    # ========================================================

    drop_indexes(
        "story_categories",
        STORY_CATEGORY_INDEXES,
    )

    op.drop_table(
        "story_categories"
    )

    # ========================================================
    # 9. REMOVE RESTAURANT ANALYTICS TABLE
    # ========================================================

    drop_indexes(
        "restaurant_analytics_events",
        RESTAURANT_ANALYTICS_INDEXES,
    )

    op.drop_table(
        "restaurant_analytics_events"
    )

    # ========================================================
    # 10. REMOVE YOCO WEBHOOK EVENT RECORDS
    # ========================================================

    op.drop_table(
        "paid_story_webhook_events"
    )
