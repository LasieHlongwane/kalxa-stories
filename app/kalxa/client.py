import requests

from flask import current_app


# ============================================================
# DEFAULTS
# ============================================================

DEFAULT_TIMEOUT = 10

RESTAURANTS_ENDPOINT = (
    "/api/public/restaurants"
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
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "Kalxa-Stories/1.0"
                ),
            },
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
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "Kalxa-Stories/1.0"
                ),
            },
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
# NORMALIZE RESTAURANT
# ============================================================

def normalize_restaurant(
    data,
):
    """
    Normalize restaurant data returned by Kalxa Ticketing.

    Kalxa Ticketing currently returns profile_path such as:

    /restaurant/1

    Stories converts that into:

    https://tickets.kalxa.co.za/restaurant/1
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

    # --------------------------------------------------------
    # PROFILE URL
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # RETURN NORMALIZED RESTAURANT
    # --------------------------------------------------------

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
