"""add article images

Revision ID: 06421a763cf2
Revises: acbab0da5249
Create Date: 2026-09-30 02:37:27.320013
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# REVISION IDENTIFIERS
# ============================================================

revision = "06421a763cf2"
down_revision = "acbab0da5249"
branch_labels = None
depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # ========================================================
    # ARTICLE IMAGES
    # ========================================================
    #
    # Stores Cloudinary-backed images belonging to a Kalxa
    # Stories article.
    #
    # One article may have multiple images.
    #
    # display_order controls the order in which images appear
    # inside the story/editor.
    #
    # Cloudinary public IDs are stored so that images can be
    # removed from Cloudinary when they are replaced/deleted.
    # ========================================================

    op.create_table(
        "article_images",

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
            "cloudinary_public_id",
            sa.String(
                length=500
            ),
            nullable=False,
        ),

        sa.Column(
            "image_url",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "caption",
            sa.String(
                length=500
            ),
            nullable=True,
        ),

        sa.Column(
            "width",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "height",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "file_bytes",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            [
                "article_id",
            ],
            [
                "articles.id",
            ],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),
    )


    # ========================================================
    # INDEXES
    # ========================================================

    with op.batch_alter_table(
        "article_images",
        schema=None,
    ) as batch_op:

        batch_op.create_index(
            "ix_article_images_article_id",
            [
                "article_id",
            ],
            unique=False,
        )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    # ========================================================
    # REMOVE INDEX
    # ========================================================

    with op.batch_alter_table(
        "article_images",
        schema=None,
    ) as batch_op:

        batch_op.drop_index(
            "ix_article_images_article_id"
        )


    # ========================================================
    # REMOVE TABLE
    # ========================================================

    op.drop_table(
        "article_images"
    )