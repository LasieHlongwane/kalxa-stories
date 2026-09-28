import os

from dotenv import load_dotenv


load_dotenv()


def get_database_url():

    database_url = os.getenv(
        "DATABASE_URL",
        "sqlite:///kalxa_stories.db",
    )

    # SQLAlchemy prefers postgresql://
    # instead of the legacy postgres:// scheme.

    if database_url.startswith(
        "postgres://"
    ):

        database_url = (
            database_url.replace(
                "postgres://",
                "postgresql://",
                1,
            )
        )

    return database_url


class Config:

    # ========================================================
    # CORE
    # ========================================================

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "kalxa-stories-development-key",
    )

    # ========================================================
    # DATABASE
    # ========================================================

    SQLALCHEMY_DATABASE_URI = (
        get_database_url()
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ========================================================
    # ADMIN
    # ========================================================

    KALXA_STORIES_ADMIN_USERNAME = (
        os.getenv(
            "KALXA_STORIES_ADMIN_USERNAME",
            "admin",
        )
    )

    KALXA_STORIES_ADMIN_PASSWORD = (
        os.getenv(
            "KALXA_STORIES_ADMIN_PASSWORD",
            "",
        )
    )

    # ========================================================
    # KALXA TICKETING
    # ========================================================

    KALXA_TICKETING_URL = (
        os.getenv(
            "KALXA_TICKETING_URL",
            "http://127.0.0.1:5000",
        )
        .rstrip("/")
    )