"""Opt-in locality subscriptions, email confirmation and protected admin list.

Independent from Premium Restaurants, paid publishing, and article tables.
"""
import os
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, session, url_for)
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.newsletter.models import StoryEmailSubscriber

newsletter_bp = Blueprint('story_newsletter', __name__)
AREAS = ('KwaMhlanga', 'Kwaggafontein', 'Siyabuswa')
EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='kalxa-stories-area-optin-v1')


def subscription_csrf():
    token = session.get('story_newsletter_csrf')
    if not token:
        token = secrets.token_urlsafe(32)
        session['story_newsletter_csrf'] = token
    return token


def send_confirmation(subscriber):
    """Return False if SMTP not configured or email delivery failed."""
    host = current_app.config.get('SMTP_HOST') or os.getenv('SMTP_HOST', '')
    username = current_app.config.get('SMTP_USERNAME') or os.getenv('SMTP_USERNAME', '')
    password = current_app.config.get('SMTP_PASSWORD') or os.getenv('SMTP_PASSWORD', '')
    from_email = current_app.config.get('SMTP_FROM_EMAIL') or os.getenv('SMTP_FROM_EMAIL', '')
    if not host or not from_email:
        current_app.logger.warning('Stories newsletter: SMTP_HOST or SMTP_FROM_EMAIL missing')
        return False
    port = int(current_app.config.get('SMTP_PORT') or os.getenv('SMTP_PORT', '587'))
    use_tls = str(current_app.config.get('SMTP_USE_TLS') or os.getenv('SMTP_USE_TLS', 'true')).lower() == 'true'
    link = url_for('story_newsletter.confirm',
                   token=serializer().dumps({'subscriber_id': subscriber.id, 'email': subscriber.email}),
                   _external=True)
    message = EmailMessage()
    message['Subject'] = 'Confirm your KALXA Stories subscription'
    message['From'] = from_email
    message['To'] = subscriber.email
    message.set_content(f'Confirm your subscription for {subscriber.area} stories:\n\n{link}\n\n'
                        'This link expires in 48 hours. If you did not request this, ignore this email.')
    try:
        with smtplib.SMTP(host, port, timeout=12) as smtp:
            smtp.ehlo()
            if use_tls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException, ValueError):
        current_app.logger.exception('Stories newsletter confirmation email failed')
        return False


@newsletter_bp.get('/stories/newsletter')
def signup_page():
    return render_template('newsletter/signup.html', areas=AREAS,
                           csrf_token=subscription_csrf())


@newsletter_bp.post('/stories/newsletter/subscribe')
def subscribe():
    if request.content_length and request.content_length > 10000:
        abort(413)
    if request.form.get('website', '').strip():  # honeypot, return without data insertion
        return redirect(url_for('story_newsletter.signup_page'))
    sent_csrf = request.form.get('csrf_token', '')
    expected_csrf = session.get('story_newsletter_csrf', '')
    if not expected_csrf or not secrets.compare_digest(sent_csrf, expected_csrf):
        abort(400)
    email = request.form.get('email', '').strip().lower()
    area = request.form.get('area', '').strip()
    consent = request.form.get('consent') == 'yes'
    if len(email) > 254 or not EMAIL_RE.fullmatch(email) or area not in AREAS or not consent:
        flash('Enter a valid email, choose an area and agree to receive email updates.', 'error')
        return redirect(url_for('story_newsletter.signup_page'))
    subscriber = StoryEmailSubscriber.query.filter_by(email=email).first()
    if subscriber and subscriber.status == 'active':
        # Do not disclose existing subscribers' email addresses.
        flash('If your address is eligible, you will receive an email with the next steps.', 'success')
        return redirect(url_for('story_newsletter.signup_page'))
    if subscriber is None:
        subscriber = StoryEmailSubscriber(email=email, area=area, status='pending')
        db.session.add(subscriber)
    else:
        subscriber.area = area
        subscriber.status = 'pending'
        subscriber.consent_at = datetime.now(timezone.utc)
        subscriber.confirmed_at = None
        subscriber.unsubscribed_at = None
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.warning('Newsletter concurrent email registration')
        flash('If your address is eligible, you will receive an email with the next steps.', 'success')
        return redirect(url_for('story_newsletter.signup_page'))
    if send_confirmation(subscriber):
        flash('Check your inbox and confirm your email to subscribe.', 'success')
    else:
        flash('Your request was saved, but the confirmation email could not be sent. Please try again later.', 'error')
    return redirect(url_for('story_newsletter.signup_page'))


@newsletter_bp.get('/stories/newsletter/confirm/<token>')
def confirm(token):
    try:
        payload = serializer().loads(token, max_age=48 * 3600)
    except (BadSignature, SignatureExpired):
        return render_template('newsletter/result.html', title='Link expired',
                               message='Please sign up again to get a new confirmation email.'), 400
    subscriber = db.session.get(StoryEmailSubscriber, payload.get('subscriber_id'))
    if not subscriber or subscriber.email != payload.get('email') or subscriber.status == 'unsubscribed':
        abort(404)
    subscriber.status = 'active'
    subscriber.confirmed_at = datetime.now(timezone.utc)
    db.session.commit()
    return render_template('newsletter/result.html', title='Subscription confirmed',
                           message=f'You will receive KALXA Stories updates for {subscriber.area}.')


@newsletter_bp.get('/stories/newsletter/unsubscribe/<token>')
def unsubscribe(token):
    try:
        payload = serializer().loads(token, max_age=365 * 24 * 3600)
    except (BadSignature, SignatureExpired):
        abort(400)
    subscriber = db.session.get(StoryEmailSubscriber, payload.get('subscriber_id'))
    if not subscriber or subscriber.email != payload.get('email'):
        abort(404)
    subscriber.status = 'unsubscribed'
    subscriber.unsubscribed_at = datetime.now(timezone.utc)
    db.session.commit()
    return render_template('newsletter/result.html', title='Unsubscribed',
                           message='You will no longer receive KALXA Stories updates.')


@newsletter_bp.get('/admin/story-subscribers')
def admin_subscribers():
    if not session.get('kalxa_stories_admin'):
        return redirect(url_for('admin.login', next=request.path))
    selected_area = request.args.get('area', '')
    query = StoryEmailSubscriber.query
    if selected_area in AREAS:
        query = query.filter_by(area=selected_area)
    subscribers = query.order_by(StoryEmailSubscriber.created_at.desc()).limit(500).all()
    counts = {area: StoryEmailSubscriber.query.filter_by(area=area, status='active').count()
              for area in AREAS}
    return render_template('newsletter/admin_list.html', subscribers=subscribers,
                           counts=counts, areas=AREAS, selected_area=selected_area)
