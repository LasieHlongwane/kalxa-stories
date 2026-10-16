"""
KwaNdebele Kalxa Hub — Newsletter Subscriptions

Single opt-in locality subscriptions.

Users are subscribed immediately after submitting their
email address, selecting an area and providing consent.

NO confirmation email is sent.

Independent from:
- Premium Restaurants
- Paid publishing
- Article tables

Features:
- Immediate subscription activation
- Email validation
- Area selection
- Consent recording
- Duplicate protection
- CSRF protection
- Honeypot protection
- Unsubscribe functionality
- Protected admin subscriber list
"""

import re
import secrets

from datetime import datetime, timezone

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

from itsdangerous import (
    URLSafeTimedSerializer,
    BadSignature,
    SignatureExpired,
)

from sqlalchemy.exc import IntegrityError

from app.extensions import db

from app.newsletter.models import StoryEmailSubscriber


# ============================================================
# BLUEPRINT
# ============================================================

newsletter_bp = Blueprint(
    "story_newsletter",
    __name__,
)


# ============================================================
# SUPPORTED LOCALITIES
# ============================================================

AREAS = (
    "All Areas",
    "KwaMhlanga",
    "Kwaggafontein",
    "Siyabuswa",
    
)


# ============================================================
# EMAIL VALIDATION
# ============================================================

EMAIL_RE = re.compile(
    r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
)


# ============================================================
# SECURITY — TOKEN SERIALIZER
#
# Retained for existing unsubscribe links and previously
# issued confirmation links.
# ============================================================

def serializer():

    return URLSafeTimedSerializer(
        current_app.secret_key,
        salt="kalxa-stories-area-optin-v1",
    )


# ============================================================
# CSRF TOKEN
# ============================================================

def subscription_csrf():

    token = session.get(
        "story_newsletter_csrf"
    )

    if not token:

        token = secrets.token_urlsafe(32)

        session[
            "story_newsletter_csrf"
        ] = token

    return token


# ============================================================
# NEWSLETTER SIGNUP PAGE
# ============================================================

@newsletter_bp.get(
    "/stories/newsletter"
)
def signup_page():

    return render_template(
        "newsletter/signup.html",
        areas=AREAS,
        csrf_token=subscription_csrf(),
    )


# ============================================================
# SUBSCRIBE
#
# SINGLE OPT-IN
#
# NO EMAIL CONFIRMATION REQUIRED
#
# WORKFLOW:
#
# 1. Validate request
# 2. Check CSRF
# 3. Validate email and area
# 4. Verify consent
# 5. Check existing subscription
# 6. Activate subscription immediately
# 7. Save to database
# 8. Display success message
#
# No SMTP connection is made.
# ============================================================

@newsletter_bp.post(
    "/stories/newsletter/subscribe"
)
def subscribe():

    # ========================================================
    # REQUEST SIZE PROTECTION
    # ========================================================

    if (
        request.content_length
        and request.content_length > 10000
    ):

        abort(413)


    # ========================================================
    # HONEYPOT SPAM PROTECTION
    # ========================================================

    if request.form.get(
        "website",
        ""
    ).strip():

        return redirect(
            url_for(
                "story_newsletter.signup_page"
            )
        )


    # ========================================================
    # CSRF PROTECTION
    # ========================================================

    sent_csrf = request.form.get(
        "csrf_token",
        ""
    )

    expected_csrf = session.get(
        "story_newsletter_csrf",
        ""
    )

    if (
        not expected_csrf
        or not secrets.compare_digest(
            sent_csrf,
            expected_csrf,
        )
    ):

        abort(400)


    # ========================================================
    # FORM DATA
    # ========================================================

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    area = request.form.get(
        "area",
        ""
    ).strip()

    consent = (
        request.form.get(
            "consent"
        ) == "yes"
    )


    # ========================================================
    # VALIDATION
    # ========================================================

    if (
        len(email) > 254
        or not EMAIL_RE.fullmatch(email)
        or area not in AREAS
        or not consent
    ):

        flash(
            (
                "Enter a valid email address, "
                "choose your area and agree "
                "to receive email updates."
            ),
            "error",
        )

        return redirect(
            url_for(
                "story_newsletter.signup_page"
            )
        )


    # ========================================================
    # CHECK EXISTING SUBSCRIBER
    # ========================================================

    subscriber = (
        StoryEmailSubscriber.query
        .filter_by(
            email=email
        )
        .first()
    )


    # ========================================================
    # PRIVACY-SAFE SUCCESS MESSAGE
    #
    # Do not disclose whether an email already exists.
    # ========================================================

    success_message = (
        "Thank you for joining KwaNdebele Kalxa Hub! "
        "Stay connected with the latest local news, "
        "culture, lifestyle, businesses, events "
        "and community stories."
    )


    # ========================================================
    # ALREADY ACTIVE
    #
    # Do not create duplicates.
    #
    # Do not reveal whether the email already exists.
    # ========================================================

    if (
        subscriber
        and subscriber.status == "active"
    ):

        flash(
            success_message,
            "success",
        )

        return redirect(
            url_for(
                "story_newsletter.signup_page"
            )
        )


    # ========================================================
    # CURRENT TIME
    # ========================================================

    now = datetime.now(
        timezone.utc
    )


    # ========================================================
    # CREATE NEW SUBSCRIBER
    #
    # Immediately active.
    #
    # No pending status.
    #
    # No confirmation email.
    # ========================================================

    if subscriber is None:

        subscriber = StoryEmailSubscriber(

            email=email,

            area=area,

            status="active",

        )

        subscriber.consent_at = now

        subscriber.confirmed_at = now

        subscriber.unsubscribed_at = None

        db.session.add(
            subscriber
        )


    # ========================================================
    # REACTIVATE EXISTING SUBSCRIBER
    #
    # Includes:
    # - Previously pending subscriptions
    # - Previously unsubscribed subscriptions
    #
    # User must submit the form and provide consent again.
    # ========================================================

    else:

        subscriber.area = area

        subscriber.status = "active"

        subscriber.consent_at = now

        subscriber.confirmed_at = now

        subscriber.unsubscribed_at = None


    # ========================================================
    # SAVE SUBSCRIPTION
    # ========================================================

    try:

        db.session.commit()

    except IntegrityError:

        db.session.rollback()

        current_app.logger.warning(
            "Newsletter concurrent email registration"
        )

        flash(
            success_message,
            "success",
        )

        return redirect(
            url_for(
                "story_newsletter.signup_page"
            )
        )


    # ========================================================
    # SUBSCRIPTION SUCCESS
    #
    # The user is already subscribed.
    #
    # No email confirmation is sent.
    # ========================================================

    flash(
        success_message,
        "success",
    )

    return redirect(
        url_for(
            "story_newsletter.signup_page"
        )
    )


# ============================================================
# LEGACY CONFIRMATION ROUTE
#
# Retained for compatibility with links that may already
# exist in previously delivered confirmation emails.
#
# New subscriptions do not use this route.
#
# This route does not activate pending subscriptions.
# ============================================================

@newsletter_bp.get(
    "/stories/newsletter/confirm/<token>"
)
def confirm(token):

    try:

        payload = serializer().loads(
            token,
            max_age=48 * 3600,
        )

    except (
        BadSignature,
        SignatureExpired,
    ):

        return render_template(
            "newsletter/result.html",
            title="Link expired",
            message=(
                "This confirmation link has expired. "
                "You can subscribe directly using "
                "the newsletter form."
            ),
        ), 400


    subscriber = db.session.get(
        StoryEmailSubscriber,
        payload.get(
            "subscriber_id"
        ),
    )


    if (
        not subscriber
        or subscriber.email != payload.get("email")
        or subscriber.status == "unsubscribed"
    ):

        abort(404)


    # ========================================================
    # NO STATUS CHANGE
    #
    # The legacy link is informational only.
    # ========================================================

    return render_template(
        "newsletter/result.html",
        title="Newsletter subscription",
        message=(
            "Email confirmation is no longer required. "
            "If your subscription is not active, "
            "please submit the newsletter form again."
        ),
    )


# ============================================================
# UNSUBSCRIBE
#
# Existing token format preserved.
#
# Existing newsletter unsubscribe links remain compatible.
# ============================================================

@newsletter_bp.get(
    "/stories/newsletter/unsubscribe/<token>"
)
def unsubscribe(token):

    try:

        payload = serializer().loads(
            token,
            max_age=365 * 24 * 3600,
        )

    except (
        BadSignature,
        SignatureExpired,
    ):

        abort(400)


    subscriber = db.session.get(
        StoryEmailSubscriber,
        payload.get(
            "subscriber_id"
        ),
    )


    if (
        not subscriber
        or subscriber.email != payload.get("email")
    ):

        abort(404)


    # ========================================================
    # DEACTIVATE SUBSCRIPTION
    # ========================================================

    subscriber.status = "unsubscribed"

    subscriber.unsubscribed_at = datetime.now(
        timezone.utc
    )


    # ========================================================
    # SAVE CHANGES
    # ========================================================

    db.session.commit()


    # ========================================================
    # RESULT PAGE
    # ========================================================

    return render_template(
        "newsletter/result.html",
        title="Unsubscribed",
        message=(
            "You will no longer receive "
            "KwaNdebele Kalxa Hub email updates."
        ),
    )


# ============================================================
# PROTECTED ADMIN SUBSCRIBER LIST
#
# Existing admin authentication preserved.
#
# Allows filtering by locality.
# ============================================================

@newsletter_bp.get(
    "/admin/story-subscribers"
)
def admin_subscribers():

    # ========================================================
    # ADMIN AUTHENTICATION
    # ========================================================

    if not session.get(
        "kalxa_stories_admin"
    ):

        return redirect(
            url_for(
                "admin.login",
                next=request.path,
            )
        )


    # ========================================================
    # AREA FILTER
    # ========================================================

    selected_area = request.args.get(
        "area",
        ""
    )


    # ========================================================
    # SUBSCRIBER QUERY
    # ========================================================

    query = (
        StoryEmailSubscriber.query
    )


    if selected_area in AREAS:

        query = query.filter_by(
            area=selected_area
        )


    # ========================================================
    # LOAD SUBSCRIBERS
    # ========================================================

    subscribers = (
        query
        .order_by(
            StoryEmailSubscriber.created_at.desc()
        )
        .limit(500)
        .all()
    )


    # ========================================================
    # ACTIVE SUBSCRIBER COUNTS
    # ========================================================

    counts = {

        area: (
            StoryEmailSubscriber.query
            .filter_by(
                area=area,
                status="active",
            )
            .count()
        )

        for area in AREAS

    }


    # ========================================================
    # RENDER ADMIN PAGE
    # ========================================================

    return render_template(
        "newsletter/admin_list.html",
        subscribers=subscribers,
        counts=counts,
        areas=AREAS,
        selected_area=selected_area,
    )
