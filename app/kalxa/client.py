
import hashlib
import threading
import time

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests

from flask import current_app, g, has_request_context


# ============================================================
# KALXA STORIES — TICKETING API CLIENT
# ============================================================
#
# Features:
# - Public restaurant search
# - Individual restaurant profiles
# - Multiple restaurant lookups
# - Private restaurant conversion analytics
# - In-process response caching
# - Request-local duplicate prevention
# - HTTP 429 cooldown
# - Retry-After support
# - Graceful API error handling
#
# Existing function names and response structures preserved.
#
# No database migration required.
# ============================================================


# ============================================================
# DEFAULTS
# ============================================================

DEFAULT_TIMEOUT = 10

RESTAURANTS_ENDPOINT = (
    "/api/public/restaurants"
)

INTERNAL_RESTAURANT_ANALYTICS_ENDPOINT = (
    "/api/internal/restaurant-analytics"
)


# ============================================================
# CACHE CONFIGURATION
# ============================================================
#
# These caches are held in each Python process.
#
# They are not shared across multiple Gunicorn workers
# or separate Render instances.
#
# Public search results can temporarily use stale data
# during a Ticketing outage.
#
# Restaurant detail records do not use stale data because
# restaurant status may affect eligibility decisions.
# ============================================================

DETAIL_TTL = 90

SEARCH_TTL = 45

ANALYTICS_TTL = 30

STALE_DISPLAY_TTL = 300

MAX_CACHE_ENTRIES = 400

MAX_COOLDOWN_SECONDS = 300

DEFAULT_429_COOLDOWN_SECONDS = 30


_cache = {}

_cooldowns = {}

_lock = threading.RLock()


# ============================================================
# BASE URL
# ============================================================

def get_ticketing_base_url():
    """
    Return the configured Kalxa Ticketing base URL.

    Example:
        https://tickets.kalxa.co.za
    """

    base_url = (
        current_app.config.get(
            "KALXA_TICKETING_URL"
        )
        or ""
    ).strip().rstrip("/")

    if not base_url:

        current_app.logger.error(
            "KALXA_TICKETING_URL is not configured."
        )

    return base_url


# ============================================================
# INTERNAL API KEY
# ============================================================

def get_internal_api_key():
    """
    Retrieve the private service-to-service API key.

    Never expose this key in templates, public responses
    or application logs.
    """

    api_key = (
        current_app.config.get(
            "KALXA_INTERNAL_API_KEY"
        )
        or ""
    ).strip()

    if not api_key:

        current_app.logger.error(
            "KALXA_INTERNAL_API_KEY is not configured."
        )

    return api_key


# ============================================================
# BUILD API URL
# ============================================================

def build_api_url(path):

    base_url = get_ticketing_base_url()

    if not base_url:
        return ""

    return (
        f"{base_url}/"
        f"{path.lstrip('/')}"
    )


# ============================================================
# PUBLIC REQUEST HEADERS
# ============================================================

def get_public_headers():

    return {
        "Accept": "application/json",
        "User-Agent": "Kalxa-Stories/1.0",
    }


# ============================================================
# PRIVATE REQUEST HEADERS
# ============================================================

def get_internal_headers():

    api_key = get_internal_api_key()

    if not api_key:
        return None

    return {
        **get_public_headers(),
        "X-Kalxa-Internal-Key": api_key,
    }


# ============================================================
# CACHE HELPERS
# ============================================================

def _cache_get(
    key,
    allow_stale=False,
):
    """
    Retrieve a cached response.

    Standard reads respect the normal expiration time.
    Stale reads are used only where explicitly allowed.
    """

    now = time.monotonic()

    with _lock:

        record = _cache.get(key)

        if record is None:
            return None

        expires_at, stale_until, value = record

        if (
            now <= expires_at
            or (
                allow_stale
                and now <= stale_until
            )
        ):
            return value

        if now > stale_until:
            _cache.pop(key, None)

    return None


def _cache_put(
    key,
    value,
    ttl,
    stale_ttl=0,
):
    """
    Store a bounded, short-lived response.
    """

    now = time.monotonic()

    with _lock:

        if len(_cache) >= MAX_CACHE_ENTRIES:

            expired = [
                cache_key
                for cache_key, record in _cache.items()
                if record[1] < now
            ]

            for cache_key in expired:
                _cache.pop(cache_key, None)

            if len(_cache) >= MAX_CACHE_ENTRIES:
                _cache.pop(next(iter(_cache)))

        _cache[key] = (
            now + ttl,
            now + ttl + stale_ttl,
            value,
        )


# ============================================================
# RATE LIMIT HANDLING
# ============================================================

def _retry_after_seconds(header):
    """
    Parse HTTP Retry-After.

    Supports:
        Retry-After: 30

    Or an HTTP date.

    Caps the cooldown at five minutes.
    """

    if header:

        try:

            seconds = float(header)

            return max(
                1,
                min(
                    MAX_COOLDOWN_SECONDS,
                    seconds,
                ),
            )

        except (TypeError, ValueError):

            try:

                retry_date = parsedate_to_datetime(
                    header
                )

                seconds = (
                    retry_date
                    - datetime.now(timezone.utc)
                ).total_seconds()

                return max(
                    1,
                    min(
                        MAX_COOLDOWN_SECONDS,
                        seconds,
                    ),
                )

            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                pass

    return DEFAULT_429_COOLDOWN_SECONDS


def _cooldown_active(bucket):
    """
    Avoid repeated requests while an endpoint group
    is rate-limited.
    """

    with _lock:

        return (
            time.monotonic()
            < _cooldowns.get(bucket, 0)
        )


def _set_cooldown(
    bucket,
    response,
):
    """
    Activate a temporary cooldown when Ticketing
    returns HTTP 429.
    """

    delay = _retry_after_seconds(
        response.headers.get("Retry-After")
    )

    with _lock:

        _cooldowns[bucket] = max(
            _cooldowns.get(bucket, 0),
            time.monotonic() + delay,
        )

    current_app.logger.warning(
        "Kalxa Ticketing API rate-limited %s. "
        "Suppressing new requests for %.0f seconds.",
        bucket[1],
        delay,
    )


# ============================================================
# SHARED JSON REQUEST HELPER
# ============================================================

def _request_json(
    url,
    params=None,
    headers=None,
    cache_key=None,
    ttl=0,
    stale_display=False,
    bucket=None,
):
    """
    Make a GET request to Kalxa Ticketing.

    Cache lookup occurs before the network request.

    On 429:
        - Records a cooldown.
        - Does not immediately retry.
        - Returns stale public display results only
          where expressly permitted.

    Does not cache failed responses.
    """

    if not url:
        return None

    parsed_url = urlsplit(url)

    bucket = bucket or (
        parsed_url.netloc,
        parsed_url.path,
    )

    # --------------------------------------------------------
    # FRESH CACHE
    # --------------------------------------------------------

    if cache_key is not None:

        cached = _cache_get(cache_key)

        if cached is not None:
            return cached

    # --------------------------------------------------------
    # ACTIVE COOLDOWN
    # --------------------------------------------------------

    if _cooldown_active(bucket):

        if stale_display and cache_key is not None:

            return _cache_get(
                cache_key,
                allow_stale=True,
            )

        return None

    # --------------------------------------------------------
    # REQUEST
    # --------------------------------------------------------

    try:

        response = requests.get(
            url,
            params=params,
            timeout=DEFAULT_TIMEOUT,
            headers=headers or get_public_headers(),
        )

        # ----------------------------------------------------
        # RATE LIMIT
        # ----------------------------------------------------

        if response.status_code == 429:

            _set_cooldown(
                bucket,
                response,
            )

            if stale_display and cache_key is not None:

                return _cache_get(
                    cache_key,
                    allow_stale=True,
                )

            return None

        # ----------------------------------------------------
        # NOT FOUND
        # ----------------------------------------------------

        if response.status_code == 404:
            return None

        response.raise_for_status()

        payload = response.json()

        # ----------------------------------------------------
        # CACHE VALID JSON OBJECT
        # ----------------------------------------------------

        if (
            cache_key is not None
            and ttl > 0
            and isinstance(payload, dict)
        ):

            stale_ttl = (
                STALE_DISPLAY_TTL
                if stale_display
                else 0
            )

            _cache_put(
                cache_key,
                payload,
                ttl,
                stale_ttl,
            )

        return payload

    except (
        requests.Timeout,
        requests.ConnectionError,
    ) as error:

        current_app.logger.warning(
            "Kalxa Ticketing unavailable for %s: %s",
            bucket[1],
            type(error).__name__,
        )

    except requests.HTTPError as error:

        status = (
            error.response.status_code
            if error.response is not None
            else "unknown"
        )

        current_app.logger.warning(
            "Kalxa Ticketing HTTP %s for %s.",
            status,
            bucket[1],
        )

    except requests.RequestException as error:

        current_app.logger.warning(
            "Kalxa Ticketing request failed for %s: %s",
            bucket[1],
            type(error).__name__,
        )

    except ValueError:

        current_app.logger.warning(
            "Kalxa Ticketing returned invalid JSON "
            "for %s.",
            bucket[1],
        )

    # --------------------------------------------------------
    # OPTIONAL STALE DISPLAY FALLBACK
    # --------------------------------------------------------

    if stale_display and cache_key is not None:

        return _cache_get(
            cache_key,
            allow_stale=True,
        )

    return None


# ============================================================
# SEARCH RESTAURANTS
# ============================================================

def search_restaurants(search=""):
    """
    Search public Kalxa Ticketing restaurants.

    Uses a short-lived cache to avoid repeatedly
    requesting identical searches.

    Returns:
        list[dict]
    """

    url = build_api_url(
        RESTAURANTS_ENDPOINT
    )

    if not url:
        return []

    search = (
        search or ""
    ).strip()

    params = {}

    if search:
        params["q"] = search

    cache_key = (
        "restaurants-search",
        url,
        search.casefold(),
    )

    bucket = (
        urlsplit(url).netloc,
        RESTAURANTS_ENDPOINT,
    )

    payload = _request_json(
        url,
        params=params,
        headers=get_public_headers(),
        cache_key=cache_key,
        ttl=SEARCH_TTL,
        stale_display=True,
        bucket=bucket,
    )

    if not isinstance(payload, dict):
        return []

    restaurants = payload.get(
        "restaurants",
        [],
    )

    if not isinstance(restaurants, list):

        current_app.logger.warning(
            "Unexpected Ticketing restaurant search "
            "response format."
        )

        return []

    normalized = []

    for restaurant in restaurants:

        if not isinstance(restaurant, dict):
            continue

        normalized.append(
            normalize_restaurant(restaurant)
        )

    return normalized


# ============================================================
# GET ONE RESTAURANT
# ============================================================

def get_restaurant(restaurant_id):
    """
    Retrieve one public restaurant profile.

    Prevents duplicate lookups during the same
    Flask request and caches successful results briefly.

    Does not return stale restaurant detail records
    after their cache lifetime.
    """

    try:

        restaurant_id = int(restaurant_id)

        if restaurant_id <= 0:
            return None

    except (TypeError, ValueError):
        return None

    url = build_api_url(
        f"{RESTAURANTS_ENDPOINT}/{restaurant_id}"
    )

    if not url:
        return None

    cache_key = (
        "restaurant-detail",
        url,
    )

    # --------------------------------------------------------
    # REQUEST-LOCAL CACHE
    # --------------------------------------------------------

    request_cache = None

    if has_request_context():

        request_cache = getattr(
            g,
            "_kalxa_ticketing_details",
            None,
        )

        if request_cache is None:

            request_cache = {}

            g._kalxa_ticketing_details = (
                request_cache
            )

        if cache_key in request_cache:

            return request_cache[cache_key]

    # --------------------------------------------------------
    # API REQUEST
    # --------------------------------------------------------

    bucket = (
        urlsplit(url).netloc,
        RESTAURANTS_ENDPOINT,
    )

    payload = _request_json(
        url,
        headers=get_public_headers(),
        cache_key=cache_key,
        ttl=DETAIL_TTL,
        stale_display=False,
        bucket=bucket,
    )

    restaurant = (
        normalize_restaurant(payload)
        if isinstance(payload, dict)
        else None
    )

    if request_cache is not None:

        request_cache[cache_key] = restaurant

    return restaurant


# ============================================================
# GET MULTIPLE RESTAURANTS
# ============================================================

def get_restaurants_by_ids(restaurant_ids):
    """
    Retrieve restaurants while preserving input order.

    Removes duplicate and invalid IDs.

    Cached individual restaurant details are reused.
    """

    restaurants = []

    seen = set()

    for value in restaurant_ids or []:

        try:

            restaurant_id = int(value)

        except (TypeError, ValueError):
            continue

        if restaurant_id <= 0:
            continue

        if restaurant_id in seen:
            continue

        seen.add(restaurant_id)

        restaurant = get_restaurant(
            restaurant_id
        )

        if restaurant:

            restaurants.append(restaurant)

    return restaurants


# ============================================================
# NORMALIZE STORY IDS
# ============================================================

def normalize_story_ids(story_ids):
    """
    Convert story IDs into a unique list.

    Maximum:
        100 IDs
    """

    normalized_ids = []

    seen = set()

    for value in story_ids or []:

        try:

            story_id = int(value)

        except (TypeError, ValueError):
            continue

        if story_id <= 0:
            continue

        if story_id in seen:
            continue

        seen.add(story_id)

        normalized_ids.append(story_id)

        if len(normalized_ids) >= 100:
            break

    return normalized_ids


# ============================================================
# NORMALIZE ANALYTICS DATETIME
# ============================================================

def normalize_analytics_datetime(value):
    """
    Normalize a datetime to UTC ISO-8601.

    Naive datetimes are interpreted as UTC.
    """

    if value is None:
        return None

    if not isinstance(value, datetime):

        raise TypeError(
            "Analytics date filters must be "
            "datetime objects."
        )

    if value.tzinfo is None:

        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    ).isoformat()


# ============================================================
# EMPTY CONVERSION ANALYTICS
# ============================================================

def empty_story_conversion_analytics(story_id):
    """
    Return a predictable analytics structure when
    Ticketing is unavailable.
    """

    return {
        "story_id": story_id,

        "totals": {
            "restaurant_views": 0,
            "experience_views": 0,
            "whatsapp_clicks": 0,
            "phone_clicks": 0,
            "directions_clicks": 0,
            "meaningful_actions": 0,
            "unique_sessions": 0,
        },

        "restaurants": [],
    }


# ============================================================
# SAFE INTEGER
# ============================================================

def safe_int(value):
    """
    Convert invalid or negative values to zero.
    """

    try:

        return max(
            int(value or 0),
            0,
        )

    except (
        TypeError,
        ValueError,
        OverflowError,
    ):

        return 0


# ============================================================
# STORY CONVERSION ANALYTICS
# ============================================================

def get_story_conversion_analytics(
    story_ids,
    start_at=None,
    end_at=None,
):
    """
    Fetch aggregated conversion analytics from Ticketing.

    The endpoint is private and requires the internal key.

    Results are cached for 30 seconds.

    Each date range has its own cache entry.

    If Ticketing is unavailable, the function returns
    the original zero-value structure.
    """

    normalized_story_ids = normalize_story_ids(
        story_ids
    )

    if not normalized_story_ids:
        return {}

    # --------------------------------------------------------
    # DEFAULT RESULTS
    # --------------------------------------------------------

    results = {
        story_id: empty_story_conversion_analytics(
            story_id
        )
        for story_id in normalized_story_ids
    }

    # --------------------------------------------------------
    # DATE FILTERS
    # --------------------------------------------------------

    try:

        normalized_start_at = (
            normalize_analytics_datetime(start_at)
        )

        normalized_end_at = (
            normalize_analytics_datetime(end_at)
        )

    except TypeError:

        current_app.logger.warning(
            "Invalid Ticketing analytics date filters."
        )

        normalized_start_at = None
        normalized_end_at = None

    # --------------------------------------------------------
    # API URL
    # --------------------------------------------------------

    url = build_api_url(
        INTERNAL_RESTAURANT_ANALYTICS_ENDPOINT
    )

    if not url:
        return results

    headers = get_internal_headers()

    if not headers:
        return results

    # --------------------------------------------------------
    # PARAMETERS
    # --------------------------------------------------------

    params = {
        "story_ids": ",".join(
            str(story_id)
            for story_id in normalized_story_ids
        )
    }

    if normalized_start_at:

        params["start_at"] = normalized_start_at

    if normalized_end_at:

        params["end_at"] = normalized_end_at

    # --------------------------------------------------------
    # ANALYTICS CACHE KEY
    # --------------------------------------------------------
    #
    # The API key itself is never stored as a cache key.
    # Only a short SHA-256 fingerprint is used.
    # --------------------------------------------------------

    key_fingerprint = hashlib.sha256(
        headers["X-Kalxa-Internal-Key"].encode()
    ).hexdigest()[:16]

    cache_key = (
        "analytics",
        url,
        key_fingerprint,
        tuple(normalized_story_ids),
        normalized_start_at,
        normalized_end_at,
    )

    bucket = (
        urlsplit(url).netloc,
        INTERNAL_RESTAURANT_ANALYTICS_ENDPOINT,
    )

    # --------------------------------------------------------
    # REQUEST
    # --------------------------------------------------------

    payload = _request_json(
        url,
        params=params,
        headers=headers,
        cache_key=cache_key,
        ttl=ANALYTICS_TTL,
        stale_display=False,
        bucket=bucket,
    )

    if not isinstance(payload, dict):
        return results

    if payload.get("ok") is not True:
        return results

    stories = payload.get(
        "stories",
        [],
    )

    if not isinstance(stories, list):
        return results

    # --------------------------------------------------------
    # EXPECTED ANALYTICS FIELDS
    # --------------------------------------------------------

    total_keys = tuple(
        results[normalized_story_ids[0]]["totals"].keys()
    )

    # --------------------------------------------------------
    # NORMALIZE STORIES
    # --------------------------------------------------------

    for story in stories:

        if not isinstance(story, dict):
            continue

        try:

            story_id = int(
                story.get("story_id")
            )

        except (TypeError, ValueError):
            continue

        if story_id not in results:
            continue

        totals = story.get(
            "totals",
            {},
        )

        if not isinstance(totals, dict):
            totals = {}

        restaurants = story.get(
            "restaurants",
            [],
        )

        normalized_restaurants = []

        # ----------------------------------------------------
        # RESTAURANT ANALYTICS
        # ----------------------------------------------------

        if isinstance(restaurants, list):

            for restaurant in restaurants:

                if not isinstance(restaurant, dict):
                    continue

                try:

                    restaurant_id = int(
                        restaurant.get("restaurant_id")
                    )

                except (TypeError, ValueError):
                    continue

                if restaurant_id <= 0:
                    continue

                normalized_restaurants.append(
                    {
                        "restaurant_id": restaurant_id,

                        **{
                            key: safe_int(
                                restaurant.get(key)
                            )
                            for key in total_keys
                        },
                    }
                )

        # ----------------------------------------------------
        # STORY TOTALS
        # ----------------------------------------------------

        results[story_id] = {
            "story_id": story_id,

            "totals": {
                key: safe_int(
                    totals.get(key)
                )
                for key in total_keys
            },

            "restaurants": normalized_restaurants,
        }

    return results


# ============================================================
# NORMALIZE RESTAURANT
# ============================================================

def normalize_restaurant(data):
    """
    Preserve the restaurant fields expected by Stories.

    Converts profile_path into a complete Ticketing URL.
    """

    if not isinstance(data, dict):
        return None

    base_url = get_ticketing_base_url()

    restaurant_id = data.get("id")

    profile_path = (
        data.get("profile_path")
        or ""
    ).strip()

    # --------------------------------------------------------
    # PROFILE URL
    # --------------------------------------------------------

    if profile_path.startswith(
        ("http://", "https://")
    ):

        profile_url = profile_path

    elif profile_path:

        profile_url = (
            f"{base_url}/"
            f"{profile_path.lstrip('/')}"
        )

    elif restaurant_id is not None:

        profile_url = (
            f"{base_url}/restaurant/"
            f"{restaurant_id}"
        )

    else:

        profile_url = base_url

    # --------------------------------------------------------
    # NORMALIZED OUTPUT
    # --------------------------------------------------------

    return {
        **data,

        "id": restaurant_id,

        "business_name": (
            data.get("business_name")
            or "Restaurant"
        ),

        "headline": (
            data.get("headline")
            or ""
        ),

        "description": (
            data.get("description")
            or ""
        ),

        "price_text": (
            data.get("price_text")
            or ""
        ),

        "address": (
            data.get("address")
            or ""
        ),

        "area": (
            data.get("area")
            or ""
        ),

        "directions_url": (
            data.get("directions_url")
            or ""
        ),

        "active": bool(
            data.get("active", False)
        ),

        "profile_path": profile_path,

        "profile_url": profile_url,
    }
