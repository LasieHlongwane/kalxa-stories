import os
from dotenv import load_dotenv

# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

# ============================================================
# DATABASE URL
# ============================================================

def get_database_url():
    database_url = os.getenv(
        "DATABASE_URL",
        "sqlite:///kalxa_stories.db",
    )

    # Support older PostgreSQL URL format.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1,
        )

    return database_url

# ============================================================
# CONFIG
# ============================================================

class Config:

    # --------------------------------------------------------
    # FLASK
    # --------------------------------------------------------

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "kalxa-stories-development-key",
    )


    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    SQLALCHEMY_DATABASE_URI = get_database_url()

    SQLALCHEMY_TRACK_MODIFICATIONS = False


    # --------------------------------------------------------
    # SQLALCHEMY CONNECTION POOL
    # --------------------------------------------------------

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 2,
        "pool_timeout": 30,
    }


    # --------------------------------------------------------
    # KALXA STORIES ADMIN
    # --------------------------------------------------------

    KALXA_STORIES_ADMIN_USERNAME = os.getenv(
        "KALXA_STORIES_ADMIN_USERNAME",
        "admin",
    )

    KALXA_STORIES_ADMIN_PASSWORD = os.getenv(
        "KALXA_STORIES_ADMIN_PASSWORD",
        "",
    )

    KALXA_ATTRIBUTION_SECRET = os.getenv(
        "KALXA_ATTRIBUTION_SECRET",
        "",
    )

    KALXA_INTERNAL_API_KEY = os.getenv(
        "KALXA_INTERNAL_API_KEY",
        "",
    )


    # --------------------------------------------------------
    # KALXA TICKETING
    # --------------------------------------------------------

    KALXA_TICKETING_URL = (
        os.getenv(
            "KALXA_TICKETING_URL",
            "http://127.0.0.1:5000",
        ).rstrip("/")
    )


    # --------------------------------------------------------
    # SCRIPTURE SYNCHRONISATION
    # --------------------------------------------------------

    SCRIPTURE_SYNC_TOKEN = os.getenv(
        "SCRIPTURE_SYNC_TOKEN",
        "",
    )

    BIBLE_API_TRANSLATION = os.getenv(
        "BIBLE_API_TRANSLATION",
        "ENGWEBP",
    )
