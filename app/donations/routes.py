"""
KwaNdebele Kalxa Hub — Donations

Allows visitors to contribute R5, R10 or R20
through Yoco hosted checkout.

Checkout initiation only.

Payment success must be independently verified
through Yoco webhooks before recording a donation
as successfully paid.
"""

import os
import secrets
import uuid

import requests

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)


# ============================================================
# BLUEPRINT
# ============================================================

donations_bp = Blueprint(
    "story_donations",
    __name__,
)


# ============================================================
# DONATION AMOUNTS
#
# Values are in cents.
# ============================================================

DONATION_AMOUNTS = {
    "5": 500,
    "10": 1000,
    "20": 2000,
}


# ============================================================
# YOCO CHECKOUT API
# ============================================================

YOCO_CHECKOUT_URL = (
    "https://payments.yoco.com/api/checkouts"
)


# ============================================================
# CSRF
# ============================================================

def donation_csrf():

    token = session.get(
        "story_donation_csrf"
    )

    if not token:

        token = secrets.token_urlsafe(32)

        session[
            "story_donation_csrf"
        ] = token

    return token


# ============================================================
# DONATION PAGE
# ============================================================

@donations_bp.get("/support-kwandebele")
def donate_page():

    return render_template(
        "donations/donate.html",
        csrf_token=donation_csrf(),
    )


# ============================================================
# CREATE YOCO CHECKOUT
# ============================================================

@donations_bp.post(
    "/support-kwandebele/checkout"
)
def create_checkout():

    # --------------------------------------------------------
    # REQUEST SIZE
    # --------------------------------------------------------

    if (
        request.content_length
        and request.content_length > 10000
    ):
        abort(413)


    # --------------------------------------------------------
    # CSRF VALIDATION
    # --------------------------------------------------------

    sent_token = request.form.get(
        "csrf_token",
        ""
    )

    expected_token = session.get(
        "story_donation_csrf",
        ""
    )

    if (
        not expected_token
        or not secrets.compare_digest(
            sent_token,
            expected_token,
        )
    ):
        abort(400)


    # --------------------------------------------------------
    # AMOUNT VALIDATION
    #
    # Never trust an amount directly from the browser.
    # --------------------------------------------------------

    selected_amount = request.form.get(
        "amount",
        ""
    )

    amount_in_cents = DONATION_AMOUNTS.get(
        selected_amount
    )

    if amount_in_cents is None:

        flash(
            "Please select R5, R10 or R20.",
            "error",
        )

        return redirect(
            url_for(
                "story_donations.donate_page"
            )
        )


    # --------------------------------------------------------
    # YOCO SECRET KEY
    # --------------------------------------------------------

    secret_key = (
        current_app.config.get("YOCO_SECRET_KEY")
        or os.getenv("YOCO_SECRET_KEY")
    )

    if not secret_key:

        current_app.logger.error(
            "YOCO_SECRET_KEY is not configured"
        )

        flash(
            "Payments are temporarily unavailable.",
            "error",
        )

        return redirect(
            url_for(
                "story_donations.donate_page"
            )
        )


    # --------------------------------------------------------
    # UNIQUE REFERENCE
    # --------------------------------------------------------

    reference = (
        "KALXA-DONATION-"
        + uuid.uuid4().hex
    )


    # --------------------------------------------------------
    # CHECKOUT PAYLOAD
    # --------------------------------------------------------

    payload = {

        "amount": amount_in_cents,

        "currency": "ZAR",

        "successUrl": url_for(
            "story_donations.payment_return",
            outcome="returned",
            _external=True,
            _scheme="https",
        ),

        "cancelUrl": url_for(
            "story_donations.payment_return",
            outcome="cancelled",
            _external=True,
            _scheme="https",
        ),

        "failureUrl": url_for(
            "story_donations.payment_return",
            outcome="failed",
            _external=True,
            _scheme="https",
        ),

        "metadata": {

            "kalxa_reference": reference,

            "purpose": "kwandebele_hub_support",

            "amount_rands": selected_amount,

        },

    }


    # --------------------------------------------------------
    # REQUEST HEADERS
    # --------------------------------------------------------

    headers = {

        "Authorization": (
            f"Bearer {secret_key}"
        ),

        "Content-Type": "application/json",

        "Idempotency-Key": reference,

    }


    # --------------------------------------------------------
    # CALL YOCO
    # --------------------------------------------------------

    try:

        response = requests.post(

            YOCO_CHECKOUT_URL,

            json=payload,

            headers=headers,

            timeout=15,

        )

        response.raise_for_status()

        checkout = response.json()

        redirect_url = checkout.get(
            "redirectUrl"
        )

        if (
            not isinstance(redirect_url, str)
            or not redirect_url.startswith(
                "https://"
            )
        ):

            raise ValueError(
                "Invalid checkout redirect URL"
            )

        # Only redirect to a Yoco checkout URL.
        from urllib.parse import urlparse

        parsed = urlparse(redirect_url)

        if parsed.hostname not in (
            "c.yoco.com",
            "pay.yoco.com",
        ):

            raise ValueError(
                "Unexpected checkout host"
            )

        return redirect(
            redirect_url,
            code=303,
        )

    except (
        requests.RequestException,
        ValueError,
    ):

        current_app.logger.exception(
            "Yoco donation checkout failed"
        )

        flash(
            "We could not start your payment. "
            "Please try again.",
            "error",
        )

        return redirect(
            url_for(
                "story_donations.donate_page"
            )
        )


# ============================================================
# PAYMENT RETURN PAGE
#
# IMPORTANT:
# A browser redirect is NOT proof of payment.
#
# A verified Yoco webhook is required before marking
# a donation as paid.
# ============================================================

@donations_bp.get(
    "/support-kwandebele/payment/<outcome>"
)
def payment_return(outcome):

    if outcome == "cancelled":

        message = (
            "Your payment was cancelled. "
            "No contribution has been confirmed."
        )

        title = "Payment Cancelled"

    elif outcome == "failed":

        message = (
            "Your payment was not completed. "
            "You can try again."
        )

        title = "Payment Unsuccessful"

    elif outcome == "returned":

        message = (
            "Thank you for supporting KwaNdebele Hub. "
            "Your payment is being verified."
        )

        title = "Payment Processing"

    else:

        abort(404)

    return render_template(
        "newsletter/result.html",
        title=title,
        message=message,
    )
