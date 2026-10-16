"""
Add story reactions

Revision ID: 20fea38843d7
Revises: 74cc6b402336
Create Date: 2026-10-16 23:38:19.798160

Purpose:
    Add anonymous story reactions (likes) to Kalxa Stories.

    Each browser session can have one active reaction
    per article.

    Existing articles, restaurants, comments, analytics,
    and publishing records remain unchanged.
"""

from alembic import op
import sqlalchemy as sa


# ============================================================
# ALEMBIC REVISION IDENTIFIERS
# ============================================================

revision = "20fea38843d7"

down_revision = "74cc6b402336"

branch_labels = None

depends_on = None


# ============================================================
# UPGRADE
# ============================================================

def upgrade():

    # ========================================================
    # CREATE STORY REACTIONS TABLE
    # ========================================================

    op.create_table(

        "story_reactions",

        # ----------------------------------------------------
        # PRIMARY KEY
        # ----------------------------------------------------

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        # ----------------------------------------------------
        # ARTICLE REFERENCE
        # ----------------------------------------------------

        sa.Column(
            "article_id",
            sa.Integer(),
            nullable=False,
        ),

        # ----------------------------------------------------
        # ANONYMOUS BROWSER SESSION
        # ----------------------------------------------------

        sa.Column(
            "anonymous_session_id",
            sa.String(length=100),
            nullable=False,
        ),

        # ----------------------------------------------------
        # REACTION TYPE
        # ----------------------------------------------------

        sa.Column(
            "reaction_type",
            sa.String(length=20),
            nullable=False,
        ),

        # ----------------------------------------------------
        # CREATED TIMESTAMP
        # ----------------------------------------------------

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        # ----------------------------------------------------
        # FOREIGN KEY
        #
        # Deleting an article also deletes its reactions.
        # ----------------------------------------------------

        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            ondelete="CASCADE",
        ),

        # ----------------------------------------------------
        # PRIMARY KEY CONSTRAINT
        # ----------------------------------------------------

        sa.PrimaryKeyConstraint(
            "id",
        ),

        # ----------------------------------------------------
        # UNIQUE CONSTRAINT
        #
        # One reaction per article per anonymous session.
        # ----------------------------------------------------

        sa.UniqueConstraint(
            "article_id",
            "anonymous_session_id",
            name="uq_story_reaction_article_session",
        ),

    )

    # ========================================================
    # ARTICLE ID INDEX
    #
    # Improves performance when counting article likes.
    # ========================================================

    op.create_index(

        "ix_story_reactions_article_id",

        "story_reactions",

        ["article_id"],

        unique=False,

    )


# ============================================================
# DOWNGRADE
# ============================================================

def downgrade():

    # ========================================================
    # REMOVE ARTICLE INDEX
    # ========================================================

    op.drop_index(

        "ix_story_reactions_article_id",

        table_name="story_reactions",

    )

    # ========================================================
    # REMOVE REACTIONS TABLE
    #
    # WARNING:
    # Downgrading removes all stored story reactions.
    # ========================================================

    op.drop_table(
        "story_reactions"
    )