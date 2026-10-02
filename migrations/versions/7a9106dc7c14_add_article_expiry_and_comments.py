```python
"""add article expiry and comments

Revision ID: 7a9106dc7c14
Revises: 06421a763cf2
Create Date: 2026-10-03 01:14:34.777128

"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION IDENTIFIERS
# ============================================================

revision = "7a9106dc7c14"
down_revision = "06421a763cf2"
branch_labels = None
depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # ========================================================
    # ARTICLE COMMENTS
    # ========================================================
    #
    # Anonymous reader comments attached to Kalxa Stories.
    #
    # Comments are moderated before becoming publicly visible.
    #
    # article_id IS a real foreign key because both
    # article_comments and articles belong to the same
    # Kalxa Stories database.
    # ========================================================

    op.create_table(
        "article_comments",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "article_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "display_name",
            sa.String(length=80),
            nullable=False,
        ),

        sa.Column(
            "anonymous_session_id",
            sa.String(length=120),
            nullable=False,
        ),

        sa.Column(
            "comment_text",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "moderation_status",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id",
        ),
    )


    # ========================================================
    # ARTICLE COMMENT INDEXES
    # ========================================================

    with op.batch_alter_table(
        "article_comments",
        schema=None,
    ) as batch_op:

        batch_op.create_index(
            batch_op.f(
                "ix_article_comments_active"
            ),
            ["active"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f(
                "ix_article_comments_anonymous_session_id"
            ),
            ["anonymous_session_id"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f(
                "ix_article_comments_article_id"
            ),
            ["article_id"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f(
                "ix_article_comments_created_at"
            ),
            ["created_at"],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f(
                "ix_article_comments_moderation_status"
            ),
            ["moderation_status"],
            unique=False,
        )


    # ========================================================
    # ARTICLE EXPIRATION
    # ========================================================
    #
    # expires_at is optional.
    #
    # NULL:
    #     The story does not expire automatically.
    #
    # Date/time:
    #     Once the timestamp passes, the application can
    #     remove the story from active feeds and close
    #     comments while keeping the published URL available.
    #
    # Existing articles receive NULL automatically because
    # the new column is nullable.
    # ========================================================

    with op.batch_alter_table(
        "articles",
        schema=None,
    ) as batch_op:

        batch_op.add_column(
            sa.Column(
                "expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )

        batch_op.create_index(
            batch_op.f(
                "ix_articles_expires_at"
            ),
            ["expires_at"],
            unique=False,
        )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    # ========================================================
    # REMOVE ARTICLE EXPIRATION
    # ========================================================

    with op.batch_alter_table(
        "articles",
        schema=None,
    ) as batch_op:

        batch_op.drop_index(
            batch_op.f(
                "ix_articles_expires_at"
            )
        )

        batch_op.drop_column(
            "expires_at"
        )


    # ========================================================
    # REMOVE ARTICLE COMMENT INDEXES
    # ========================================================

    with op.batch_alter_table(
        "article_comments",
        schema=None,
    ) as batch_op:

        batch_op.drop_index(
            batch_op.f(
                "ix_article_comments_moderation_status"
            )
        )

        batch_op.drop_index(
            batch_op.f(
                "ix_article_comments_created_at"
            )
        )

        batch_op.drop_index(
            batch_op.f(
                "ix_article_comments_article_id"
            )
        )

        batch_op.drop_index(
            batch_op.f(
                "ix_article_comments_anonymous_session_id"
            )
        )

        batch_op.drop_index(
            batch_op.f(
                "ix_article_comments_active"
            )
        )


    # ========================================================
    # REMOVE ARTICLE COMMENTS TABLE
    # ========================================================

    op.drop_table(
        "article_comments"
    )
```