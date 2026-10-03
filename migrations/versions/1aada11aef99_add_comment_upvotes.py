"""add comment upvotes

Revision ID: 1aada11aef99
Revises: 7a9106dc7c14
Create Date: 2026-10-03 03:21:46.561772

"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION IDENTIFIERS
# ============================================================

revision = "1aada11aef99"
down_revision = "7a9106dc7c14"
branch_labels = None
depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # ========================================================
    # COMMENT UPVOTES
    # ========================================================

    op.create_table(
        "comment_upvotes",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "comment_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "anonymous_session_id",
            sa.String(length=120),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["comment_id"],
            ["article_comments.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),

        sa.UniqueConstraint(
            "comment_id",
            "anonymous_session_id",
            name=(
                "uq_comment_upvote_"
                "comment_session"
            ),
        ),
    )

    # ========================================================
    # INDEXES
    # ========================================================

    with op.batch_alter_table(
        "comment_upvotes",
        schema=None,
    ) as batch_op:

        batch_op.create_index(
            batch_op.f(
                "ix_comment_upvotes_"
                "anonymous_session_id"
            ),
            [
                "anonymous_session_id",
            ],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f(
                "ix_comment_upvotes_"
                "comment_id"
            ),
            [
                "comment_id",
            ],
            unique=False,
        )

        batch_op.create_index(
            batch_op.f(
                "ix_comment_upvotes_"
                "created_at"
            ),
            [
                "created_at",
            ],
            unique=False,
        )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    # ========================================================
    # REMOVE INDEXES
    # ========================================================

    with op.batch_alter_table(
        "comment_upvotes",
        schema=None,
    ) as batch_op:

        batch_op.drop_index(
            batch_op.f(
                "ix_comment_upvotes_"
                "created_at"
            )
        )

        batch_op.drop_index(
            batch_op.f(
                "ix_comment_upvotes_"
                "comment_id"
            )
        )

        batch_op.drop_index(
            batch_op.f(
                "ix_comment_upvotes_"
                "anonymous_session_id"
            )
        )

    # ========================================================
    # REMOVE TABLE
    # ========================================================

    op.drop_table(
        "comment_upvotes"
    )