import requests

from datetime import datetime, timezone

from flask import current_app


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
# BASE URL
# ============================================================

def get_ticketing_base_url():
    """
    Return the configured Kalxa Ticketing base URL.

    Production example:
    https://tickets.kalxa.co.za

    The API path must NOT be included in the environment
    variable because this client adds it automatically.
    """

    base_url = current_app.config.get(
        "KALXA_TICKETING_URL",
        "",
    )

    if not base_url:

        current_app.logger.error(
            "KALXA_TICKETING_URL is not configured."
        )

        return ""

    return base_url.strip().rstrip("/")


# ============================================================
# INTERNAL API KEY
# ============================================================

def get_internal_api_key():
    """
    Return the private Kalxa service-to-service API key.

    This key is used only when Kalxa Stories communicates
    with private Kalxa Ticketing endpoints.

    It must never be exposed to:
    - browser JavaScript
    - Jinja templates
    - public API responses
    - URLs
    """

    api_key = current_app.config.get(
        "KALXA_INTERNAL_API_KEY",
        "",
    )

    if not api_key:

        current_app.logger.error(
            "KALXA_INTERNAL_API_KEY "
            "is not configured."
        )

        return ""

    return api_key.strip()


# ============================================================
# BUILD API URL
# ============================================================

def build_api_url(
    path,
):
    """
    Build a complete Kalxa Ticketing API URL.
    """

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
    """
    Headers used for public Kalxa Ticketing API requests.
    """

    return {
        "Accept":
            "application/json",

        "User-Agent":
            "Kalxa-Stories/1.0",
    }


# ============================================================
# INTERNAL REQUEST HEADERS
# ============================================================

def get_internal_headers():
    """
    Headers used for private Kalxa service-to-service
    API requests.

    Returns None when the internal API key is unavailable.
    """

    api_key = get_internal_api_key()

    if not api_key:

        return None

    return {
        "Accept":
            "application/json",

        "User-Agent":
            "Kalxa-Stories/1.0",

        "X-Kalxa-Internal-Key":
            api_key,
    }


# ============================================================
# SEARCH RESTAURANTS
# ============================================================

def search_restaurants(
    search="",
):
    """
    Retrieve active restaurants from Kalxa Ticketing.

    If search is supplied, it is passed to Ticketing using
    the q query parameter.

    Examples:

    /api/public/restaurants

    /api/public/restaurants?q=Mthunzini
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

    current_app.logger.info(
        "Requesting Kalxa Ticketing restaurants: %s",
        url,
    )

    try:

        response = requests.get(
            url,
            params=params,
            timeout=DEFAULT_TIMEOUT,
            headers=get_public_headers(),
        )

        current_app.logger.info(
            "Kalxa Ticketing restaurant API "
            "returned status %s.",
            response.status_code,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(
            data,
            dict,
        ):

            current_app.logger.error(
                "Unexpected Kalxa Ticketing "
                "restaurant response type: %s",
                type(data).__name__,
            )

            return []

        restaurants = data.get(
            "restaurants",
            [],
        )

        if not isinstance(
            restaurants,
            list,
        ):

            current_app.logger.error(
                "Kalxa Ticketing response "
                "'restaurants' is not a list."
            )

            return []

        normalized_restaurants = []

        for restaurant in restaurants:

            if not isinstance(
                restaurant,
                dict,
            ):

                continue

            normalized_restaurants.append(
                normalize_restaurant(
                    restaurant
                )
            )

        current_app.logger.info(
            "Retrieved %s restaurant(s) "
            "from Kalxa Ticketing.",
            len(
                normalized_restaurants
            ),
        )

        return normalized_restaurants

    except requests.Timeout:

        current_app.logger.exception(
            "Kalxa Ticketing restaurant "
            "request timed out. URL: %s",
            url,
        )

        return []

    except requests.ConnectionError:

        current_app.logger.exception(
            "Unable to connect to "
            "Kalxa Ticketing. URL: %s",
            url,
        )

        return []

    except requests.HTTPError:

        current_app.logger.exception(
            "Kalxa Ticketing returned an "
            "HTTP error. URL: %s",
            url,
        )

        return []

    except requests.RequestException:

        current_app.logger.exception(
            "Unable to retrieve Kalxa "
            "Ticketing restaurants. URL: %s",
            url,
        )

        return []

    except ValueError:

        current_app.logger.exception(
            "Kalxa Ticketing returned invalid "
            "JSON. URL: %s",
            url,
        )

        return []


# ============================================================
# GET RESTAURANT
# ============================================================

def get_restaurant(
    restaurant_id,
):
    """
    Retrieve one restaurant from Kalxa Ticketing.
    """

    if restaurant_id is None:

        return None

    url = build_api_url(
        (
            f"{RESTAURANTS_ENDPOINT}/"
            f"{restaurant_id}"
        )
    )

    if not url:

        return None

    current_app.logger.info(
        "Requesting Kalxa Ticketing "
        "restaurant %s.",
        restaurant_id,
    )

    try:

        response = requests.get(
            url,
            timeout=DEFAULT_TIMEOUT,
            headers=get_public_headers(),
        )

        if response.status_code == 404:

            current_app.logger.warning(
                "Kalxa Ticketing restaurant "
                "%s was not found.",
                restaurant_id,
            )

            return None

        response.raise_for_status()

        data = response.json()

        if not isinstance(
            data,
            dict,
        ):

            current_app.logger.error(
                "Unexpected restaurant response "
                "for restaurant %s.",
                restaurant_id,
            )

            return None

        return normalize_restaurant(
            data
        )

    except requests.Timeout:

        current_app.logger.exception(
            "Request for Kalxa Ticketing "
            "restaurant %s timed out.",
            restaurant_id,
        )

        return None

    except requests.ConnectionError:

        current_app.logger.exception(
            "Unable to connect to Kalxa "
            "Ticketing for restaurant %s.",
            restaurant_id,
        )

        return None

    except requests.HTTPError:

        current_app.logger.exception(
            "Kalxa Ticketing returned an HTTP "
            "error for restaurant %s.",
            restaurant_id,
        )

        return None

    except requests.RequestException:

        current_app.logger.exception(
            "Unable to retrieve Kalxa "
            "Ticketing restaurant %s.",
            restaurant_id,
        )

        return None

    except ValueError:

        current_app.logger.exception(
            "Kalxa Ticketing returned invalid "
            "JSON for restaurant %s.",
            restaurant_id,
        )

        return None


# ============================================================
# GET MULTIPLE RESTAURANTS
# ============================================================

def get_restaurants_by_ids(
    restaurant_ids,
):
    """
    Retrieve multiple restaurants while preserving
    the supplied restaurant order.
    """

    restaurants = []

    seen = set()

    for restaurant_id in (
        restaurant_ids or []
    ):

        try:

            restaurant_id = int(
                restaurant_id
            )

        except (
            TypeError,
            ValueError,
        ):

            current_app.logger.warning(
                "Ignoring invalid restaurant ID: %s",
                restaurant_id,
            )

            continue

        if restaurant_id in seen:

            continue

        seen.add(
            restaurant_id
        )

        restaurant = get_restaurant(
            restaurant_id
        )

        if restaurant:

            restaurants.append(
                restaurant
            )

    return restaurants


# ============================================================
# NORMALIZE STORY IDS
# ============================================================

def normalize_story_ids(
    story_ids,
):
    """
    Normalize story IDs before sending them to the private
    Ticketing analytics API.

    Invalid IDs are ignored.

    Duplicate IDs are removed while preserving order.

    Maximum:
        100 story IDs per request.
    """

    normalized_ids = []

    seen = set()

    for story_id in (
        story_ids or []
    ):

        try:

            story_id = int(
                story_id
            )

        except (
            TypeError,
            ValueError,
        ):

            continue

        if story_id <= 0:

            continue

        if story_id in seen:

            continue

        seen.add(
            story_id
        )

        normalized_ids.append(
            story_id
        )

        if len(
            normalized_ids
        ) >= 100:

            break

    return normalized_ids


# ============================================================
# NORMALIZE ANALYTICS DATETIME
# ============================================================

def normalize_analytics_datetime(
    value,
):
    """
    Convert a datetime into a UTC ISO-8601 string suitable
    for the Kalxa Ticketing analytics API.

    Naive datetimes are treated as UTC because Kalxa Stories
    stores and compares analytics timestamps in UTC.

    Example:

        2026-10-03T12:30:00+00:00

    Returns None when no datetime was supplied.
    """

    if value is None:

        return None

    if not isinstance(
        value,
        datetime,
    ):

        raise TypeError(
            "Analytics date filters must be datetime objects."
        )

    if value.tzinfo is None:

        value = value.replace(
            tzinfo=timezone.utc
        )

    else:

        value = value.astimezone(
            timezone.utc
        )

    return value.isoformat()


# ============================================================
# EMPTY STORY CONVERSION ANALYTICS
# ============================================================

def empty_story_conversion_analytics(
    story_id,
):
    """
    Return a predictable zero-value analytics structure.

    This allows the dashboard to render normally even when
    Ticketing is temporarily unavailable.
    """

    return {
        "story_id":
            story_id,

        "totals": {
            "restaurant_views":
                0,

            "experience_views":
                0,

            "whatsapp_clicks":
                0,

            "phone_clicks":
                0,

            "directions_clicks":
                0,

            "meaningful_actions":
                0,

            "unique_sessions":
                0,
        },

        "restaurants":
            [],
    }


# ============================================================
# GET STORY CONVERSION ANALYTICS
# ============================================================

def get_story_conversion_analytics(
    story_ids,
    start_at=None,
    end_at=None,
):
    """
    Retrieve aggregated downstream conversion analytics
    from Kalxa Ticketing.

    The optional start_at and end_at values allow the Stories
    dashboard period selector to use the same date window for
    both Stories analytics and Ticketing analytics.

    Example:

        get_story_conversion_analytics(
            [1, 2, 3],
            start_at=datetime(
                2026,
                10,
                1,
                tzinfo=timezone.utc,
            ),
            end_at=datetime.now(
                timezone.utc
            ),
        )

    Ticketing may return:

        restaurant_view
        experience_view
        whatsapp_click
        phone_click
        directions_click

    The private Ticketing endpoint returns aggregates only.

    Raw anonymous session IDs are never returned to Stories.

    Request parameters:

        story_ids=1,2,3

        start_at=2026-10-01T00:00:00+00:00

        end_at=2026-10-03T12:30:00+00:00

    start_at and end_at are omitted for all-time analytics.

    Return format:

        {
            1: {
                "story_id": 1,
                "totals": {...},
                "restaurants": [...]
            },

            2: {
                ...
            }
        }

    The dictionary is keyed by integer story ID so dashboard
    code can efficiently perform:

        analytics.get(article.id)
    """

    normalized_story_ids = (
        normalize_story_ids(
            story_ids
        )
    )

    if not normalized_story_ids:

        return {}


    # ========================================================
    # NORMALIZE DATE FILTERS
    # ========================================================

    try:

        normalized_start_at = (
            normalize_analytics_datetime(
                start_at
            )
        )

        normalized_end_at = (
            normalize_analytics_datetime(
                end_at
            )
        )

    except TypeError:

        current_app.logger.exception(
            "Invalid date filter supplied to "
            "Ticketing conversion analytics."
        )

        normalized_start_at = None
        normalized_end_at = None


    # ========================================================
    # DEFAULT ZERO RESULTS
    # ========================================================

    results = {
        story_id:
            empty_story_conversion_analytics(
                story_id
            )

        for story_id
        in normalized_story_ids
    }


    # ========================================================
    # URL
    # ========================================================

    url = build_api_url(
        INTERNAL_RESTAURANT_ANALYTICS_ENDPOINT
    )

    if not url:

        return results


    # ========================================================
    # INTERNAL HEADERS
    # ========================================================

    headers = get_internal_headers()

    if not headers:

        current_app.logger.error(
            "Unable to request Ticketing conversion "
            "analytics because the internal API key "
            "is unavailable."
        )

        return results


    # ========================================================
    # REQUEST PARAMETERS
    # ========================================================

    params = {
        "story_ids":
            ",".join(
                str(
                    story_id
                )
                for story_id
                in normalized_story_ids
            )
    }


    # --------------------------------------------------------
    # PERIOD FILTER
    # --------------------------------------------------------

    if normalized_start_at:

        params[
            "start_at"
        ] = normalized_start_at

    if normalized_end_at:

        params[
            "end_at"
        ] = normalized_end_at


    current_app.logger.info(
        (
            "Requesting Kalxa Ticketing conversion "
            "analytics for %s story/stories. "
            "start_at=%s end_at=%s"
        ),
        len(
            normalized_story_ids
        ),
        normalized_start_at or "all-time",
        normalized_end_at or "all-time",
    )


    # ========================================================
    # REQUEST
    # ========================================================

    try:

        response = requests.get(
            url,
            params=params,
            timeout=DEFAULT_TIMEOUT,
            headers=headers,
        )

        current_app.logger.info(
            "Kalxa Ticketing internal analytics "
            "API returned status %s.",
            response.status_code,
        )

        response.raise_for_status()

        data = response.json()


        # ====================================================
        # VALIDATE ROOT RESPONSE
        # ====================================================

        if not isinstance(
            data,
            dict,
        ):

            current_app.logger.error(
                "Unexpected Kalxa Ticketing analytics "
                "response type: %s",
                type(data).__name__,
            )

            return results

        if data.get(
            "ok"
        ) is not True:

            current_app.logger.error(
                "Kalxa Ticketing analytics API "
                "returned ok=false."
            )

            return results

        stories = data.get(
            "stories",
            [],
        )

        if not isinstance(
            stories,
            list,
        ):

            current_app.logger.error(
                "Kalxa Ticketing analytics response "
                "'stories' is not a list."
            )

            return results


        # ====================================================
        # NORMALIZE RESPONSE
        # ====================================================

        for story in stories:

            if not isinstance(
                story,
                dict,
            ):

                continue

            try:

                story_id = int(
                    story.get(
                        "story_id"
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                continue

            if (
                story_id
                not in results
            ):

                continue

            totals = story.get(
                "totals",
                {},
            )

            if not isinstance(
                totals,
                dict,
            ):

                totals = {}

            restaurants = story.get(
                "restaurants",
                [],
            )

            if not isinstance(
                restaurants,
                list,
            ):

                restaurants = []


            # ================================================
            # NORMALIZE RESTAURANT ANALYTICS
            # ================================================

            normalized_restaurants = []

            for restaurant in restaurants:

                if not isinstance(
                    restaurant,
                    dict,
                ):

                    continue

                try:

                    restaurant_id = int(
                        restaurant.get(
                            "restaurant_id"
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    continue

                normalized_restaurants.append(
                    {
                        "restaurant_id":
                            restaurant_id,

                        "restaurant_views":
                            safe_int(
                                restaurant.get(
                                    "restaurant_views"
                                )
                            ),

                        "experience_views":
                            safe_int(
                                restaurant.get(
                                    "experience_views"
                                )
                            ),

                        "whatsapp_clicks":
                            safe_int(
                                restaurant.get(
                                    "whatsapp_clicks"
                                )
                            ),

                        "phone_clicks":
                            safe_int(
                                restaurant.get(
                                    "phone_clicks"
                                )
                            ),

                        "directions_clicks":
                            safe_int(
                                restaurant.get(
                                    "directions_clicks"
                                )
                            ),

                        "meaningful_actions":
                            safe_int(
                                restaurant.get(
                                    "meaningful_actions"
                                )
                            ),

                        "unique_sessions":
                            safe_int(
                                restaurant.get(
                                    "unique_sessions"
                                )
                            ),
                    }
                )


            # ================================================
            # STORY TOTALS
            # ================================================

            results[
                story_id
            ] = {
                "story_id":
                    story_id,

                "totals": {
                    "restaurant_views":
                        safe_int(
                            totals.get(
                                "restaurant_views"
                            )
                        ),

                    "experience_views":
                        safe_int(
                            totals.get(
                                "experience_views"
                            )
                        ),

                    "whatsapp_clicks":
                        safe_int(
                            totals.get(
                                "whatsapp_clicks"
                            )
                        ),

                    "phone_clicks":
                        safe_int(
                            totals.get(
                                "phone_clicks"
                            )
                        ),

                    "directions_clicks":
                        safe_int(
                            totals.get(
                                "directions_clicks"
                            )
                        ),

                    "meaningful_actions":
                        safe_int(
                            totals.get(
                                "meaningful_actions"
                            )
                        ),

                    "unique_sessions":
                        safe_int(
                            totals.get(
                                "unique_sessions"
                            )
                        ),
                },

                "restaurants":
                    normalized_restaurants,
            }

        return results


    # ========================================================
    # REQUEST ERRORS
    # ========================================================

    except requests.Timeout:

        current_app.logger.exception(
            "Kalxa Ticketing conversion analytics "
            "request timed out."
        )

        return results

    except requests.ConnectionError:

        current_app.logger.exception(
            "Unable to connect to Kalxa Ticketing "
            "conversion analytics API."
        )

        return results

    except requests.HTTPError:

        current_app.logger.exception(
            "Kalxa Ticketing conversion analytics "
            "API returned an HTTP error."
        )

        return results

    except requests.RequestException:

        current_app.logger.exception(
            "Unable to retrieve Kalxa Ticketing "
            "conversion analytics."
        )

        return results

    except ValueError:

        current_app.logger.exception(
            "Kalxa Ticketing conversion analytics "
            "API returned invalid JSON."
        )

        return results


# ============================================================
# SAFE INTEGER
# ============================================================

def safe_int(
    value,
):
    """
    Convert an analytics value to a non-negative integer.

    Invalid or negative values become zero.
    """

    try:

        value = int(
            value or 0
        )

    except (
        TypeError,
        ValueError,
    ):

        return 0

    return max(
        value,
        0,
    )


# ============================================================
# NORMALIZE RESTAURANT
# ============================================================

def normalize_restaurant(
    data,
):
    """
    Normalize restaurant data returned by Kalxa Ticketing.

    Kalxa Ticketing currently returns profile_path such as:

    /restaurant/1

    Stories converts that into a complete Ticketing URL.
    """

    base_url = get_ticketing_base_url()

    restaurant_id = data.get(
        "id"
    )

    profile_path = (
        data.get(
            "profile_path"
        )
        or
        ""
    ).strip()


    # ========================================================
    # PROFILE URL
    # ========================================================

    if (
        profile_path.startswith(
            "http://"
        )
        or
        profile_path.startswith(
            "https://"
        )
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


    # ========================================================
    # RETURN NORMALIZED RESTAURANT
    # ========================================================

    return {
        **data,

        "id":
            restaurant_id,

        "business_name":
            data.get(
                "business_name"
            )
            or
            "Restaurant",

        "headline":
            data.get(
                "headline"
            )
            or
            "",

        "description":
            data.get(
                "description"
            )
            or
            "",

        "price_text":
            data.get(
                "price_text"
            )
            or
            "",

        "address":
            data.get(
                "address"
            )
            or
            "",

        "area":
            data.get(
                "area"
            )
            or
            "",

        "directions_url":
            data.get(
                "directions_url"
            )
            or
            "",

        "active":
            bool(
                data.get(
                    "active",
                    False,
                )
            ),

        "profile_path":
            profile_path,

        "profile_url":
            profile_url,
    }
