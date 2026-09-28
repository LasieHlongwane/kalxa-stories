import requests

from flask import current_app


# ============================================================
# BASE URL
# ============================================================

def get_ticketing_base_url():

    return (
        current_app.config[
            "KALXA_TICKETING_URL"
        ]
        .rstrip("/")
    )


# ============================================================
# SEARCH RESTAURANTS
# ============================================================

def search_restaurants(
    search="",
):

    base_url = (
        get_ticketing_base_url()
    )

    url = (
        f"{base_url}"
        "/api/public/restaurants"
    )

    try:

        response = requests.get(
            url,
            params={
                "q": search,
            },
            timeout=5,
        )

        response.raise_for_status()

        data = response.json()

        restaurants = data.get(
            "restaurants",
            [],
        )

        return [
            normalize_restaurant(
                restaurant
            )
            for restaurant
            in restaurants
        ]

    except (
        requests.RequestException,
        ValueError,
    ):

        current_app.logger.exception(
            "Unable to retrieve "
            "Kalxa Ticketing restaurants."
        )

        return []


# ============================================================
# GET RESTAURANT
# ============================================================

def get_restaurant(
    restaurant_id,
):

    base_url = (
        get_ticketing_base_url()
    )

    url = (
        f"{base_url}"
        f"/api/public/restaurants/"
        f"{restaurant_id}"
    )

    try:

        response = requests.get(
            url,
            timeout=5,
        )

        if response.status_code == 404:

            return None

        response.raise_for_status()

        return normalize_restaurant(
            response.json()
        )

    except (
        requests.RequestException,
        ValueError,
    ):

        current_app.logger.exception(
            "Unable to retrieve restaurant %s.",
            restaurant_id,
        )

        return None


# ============================================================
# GET MULTIPLE RESTAURANTS
# ============================================================

def get_restaurants_by_ids(
    restaurant_ids,
):

    restaurants = []

    seen = set()

    for restaurant_id in restaurant_ids:

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
# NORMALIZE
# ============================================================

def normalize_restaurant(
    data
):

    base_url = (
        get_ticketing_base_url()
    )

    profile_path = (
        data.get(
            "profile_path"
        )
        or
        ""
    )

    if profile_path.startswith(
        "http://"
    ) or profile_path.startswith(
        "https://"
    ):

        profile_url = (
            profile_path
        )

    elif profile_path:

        profile_url = (
            f"{base_url}"
            f"/{profile_path.lstrip('/')}"
        )

    else:

        restaurant_id = (
            data.get("id")
        )

        profile_url = (
            f"{base_url}"
            f"/restaurant/"
            f"{restaurant_id}"
        )

    return {

        **data,

        "profile_url":
            profile_url,

    }