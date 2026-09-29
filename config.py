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
    #
    # pool_pre_ping:
    # Checks whether a PostgreSQL connection is still alive
    # before SQLAlchemy gives it to the application.
    #
    # pool_recycle:
    # Prevents very old connections from sitting in the pool.
    #
    # pool_size:
    # Keep the pool small for the Render free instance.
    #
    # max_overflow:
    # Allows a couple of temporary additional connections.
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


    # --------------------------------------------------------
    # KALXA TICKETING
    # --------------------------------------------------------

    KALXA_TICKETING_URL = (
        os.getenv(
            "KALXA_TICKETING_URL",
            "http://127.0.0.1:5000",
        ).rstrip("/")
    )
