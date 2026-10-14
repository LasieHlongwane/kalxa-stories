"""Manual, location-targeted story email campaigns.

No Celery, cron, or background worker required. The admin sends up to 20
recipients per explicit batch click. A sending record is never retried
automatically: SMTP acknowledgement ambiguity must be reconciled manually.
"""
import os
import secrets
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, session, url_for)
from sqlalchemy import func
from app.extensions import db
from app.models import Article
from app.newsletter.models import StoryEmailSubscriber
from app.newsletter.routes import AREAS, serializer
from app.notifications.models import StoryNotificationCampaign, StoryNotificationDelivery

notification_bp = Blueprint('story_notifications', __name__, url_prefix='/admin/notifications')
BATCH_SIZE = 20


def now_utc():
    return datetime.now(timezone.utc)


def require_admin():
    if not session.get('kalxa_stories_admin'):
        return redirect(url_for('admin.login', next=request.path))
    return None


def csrf_token():
    if not session.get('story_notify_csrf'):
        session['story_notify_csrf'] = secrets.token_urlsafe(32)
    return session['story_notify_csrf']


def require_csrf():
    given = request.form.get('csrf_token', '')
    expected = session.get('story_notify_csrf', '')
    if not expected or not secrets.compare_digest(given, expected):
        abort(400)


def published_article(article_id):
    article = db.session.get(Article, article_id)
    if not article or article.status != 'published' or article.is_expired:
        abort(400, 'Only active, published stories may be emailed.')
    return article


def smtp_config():
    config = current_app.config
    host = config.get('SMTP_HOST') or os.getenv('SMTP_HOST', '')
    port = int(config.get('SMTP_PORT') or os.getenv('SMTP_PORT', '587'))
    username = config.get('SMTP_USERNAME') or os.getenv('SMTP_USERNAME', '')
    password = config.get('SMTP_PASSWORD') or os.getenv('SMTP_PASSWORD', '')
    sender = config.get('SMTP_FROM_EMAIL') or os.getenv('SMTP_FROM_EMAIL', '')
    use_tls = str(config.get('SMTP_USE_TLS') or os.getenv('SMTP_USE_TLS', 'true')).lower() == 'true'
    if not host or not sender:
        raise RuntimeError('SMTP_HOST and SMTP_FROM_EMAIL are required')
    return host, port, username, password, sender, use_tls


def send_story_email(delivery):
    subscriber = delivery.subscriber
    campaign = delivery.campaign
    host, port, username, password, sender, use_tls = smtp_config()
    story_url = url_for('public.article_detail', slug=campaign.article_slug, _external=True)
    unsubscribe_url = url_for(
        'story_newsletter.unsubscribe',
        token=serializer().dumps({'subscriber_id': subscriber.id, 'email': subscriber.email}),
        _external=True,
    )
    msg = EmailMessage()
    msg['Subject'] = campaign.subject
    msg['From'] = sender
    msg['To'] = subscriber.email
    msg.set_content(
        f'KALXA STORIES\n\n{campaign.message}\n\n'
        f'Read the story: {story_url}\n\n'
        f'You subscribed for updates near {subscriber.area}.\n'
        f'Unsubscribe: {unsubscribe_url}\n'
    )
    with smtplib.SMTP(host, port, timeout=12) as smtp:
        smtp.ehlo()
        if use_tls:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if username:
            smtp.login(username, password)
        smtp.send_message(msg)


def campaign_stats(campaign_id):
    rows = (db.session.query(StoryNotificationDelivery.status, func.count(StoryNotificationDelivery.id))
            .filter_by(campaign_id=campaign_id)
            .group_by(StoryNotificationDelivery.status).all())
    return dict(rows)


@notification_bp.get('/')
def listing():
    guard = require_admin()
    if guard:
        return guard
    campaigns = StoryNotificationCampaign.query.order_by(StoryNotificationCampaign.created_at.desc()).limit(100).all()
    return render_template('notifications/list.html', campaigns=campaigns)


@notification_bp.route('/new', methods=['GET', 'POST'])
def new():
    guard = require_admin()
    if guard:
        return guard
    token = csrf_token()
    selected_id = request.args.get('article_id', type=int)
    articles = (Article.query.filter_by(status='published')
                .order_by(Article.published_at.desc(), Article.id.desc()).limit(300).all())
    eligible = [a for a in articles if not a.is_expired]
    if request.method == 'POST':
        require_csrf()
        article_id = request.form.get('article_id', type=int)
        article = published_article(article_id)
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        submitted_areas = request.form.getlist('areas')
        if 'all' in submitted_areas:
            chosen = list(AREAS)
            target = 'all'
        else:
            if not submitted_areas or any(area not in AREAS for area in submitted_areas):
                flash('Choose at least one valid location.', 'error')
                return redirect(url_for('.new', article_id=article_id))
            chosen = [area for area in AREAS if area in set(submitted_areas)]
            target = ','.join(chosen)
        if not 1 <= len(subject) <= 200 or not 1 <= len(message) <= 2000:
            flash('Subject must be 1–200 and message 1–2000 characters.', 'error')
            return redirect(url_for('.new', article_id=article_id))
        recipients = (StoryEmailSubscriber.query
                      .filter(StoryEmailSubscriber.status == 'active',
                              StoryEmailSubscriber.confirmed_at.isnot(None),
                              StoryEmailSubscriber.area.in_(chosen))
                      .order_by(StoryEmailSubscriber.id.asc()).all())
        # Exactly one row per email (subscriber table enforces email uniqueness).
        campaign = StoryNotificationCampaign(article_id=article.id, article_title=article.title, article_slug=article.slug, subject=subject,
                                              message=message, target_locations=target,
                                              total_recipients=len(recipients))
        db.session.add(campaign)
        db.session.flush()
        for subscriber in recipients:
            db.session.add(StoryNotificationDelivery(campaign_id=campaign.id, subscriber_id=subscriber.id))
        db.session.commit()
        flash(f'Campaign created for {len(recipients)} confirmed subscribers. No emails have been sent yet.', 'success')
        return redirect(url_for('.detail', campaign_id=campaign.id))
    return render_template('notifications/new.html', articles=eligible, areas=AREAS,
                           selected_id=selected_id, csrf_token=token)


@notification_bp.get('/<int:campaign_id>')
def detail(campaign_id):
    guard = require_admin()
    if guard:
        return guard
    campaign = db.get_or_404(StoryNotificationCampaign, campaign_id)
    return render_template('notifications/detail.html', campaign=campaign,
                           stats=campaign_stats(campaign_id), csrf_token=csrf_token(),
                           batch_size=BATCH_SIZE)


@notification_bp.post('/<int:campaign_id>/send-batch')
def send_batch(campaign_id):
    guard = require_admin()
    if guard:
        return guard
    require_csrf()
    campaign = db.get_or_404(StoryNotificationCampaign, campaign_id)
    if campaign.status in ('completed', 'cancelled'):
        abort(400)
    published_article(campaign.article_id)
    try:
        smtp_config()  # Fail before marking any recipients as sending.
    except (ValueError, RuntimeError):
        flash('SMTP configuration is incomplete.', 'error')
        return redirect(url_for('.detail', campaign_id=campaign.id))

    # Claim at most BATCH_SIZE rows under PostgreSQL row locks. This prevents
    # two admins/browser tabs from sending the same queued row simultaneously.
    with db.session.begin_nested():
        claimed = (StoryNotificationDelivery.query
                   .filter_by(campaign_id=campaign.id, status='queued')
                   .order_by(StoryNotificationDelivery.id.asc())
                   .with_for_update(skip_locked=True)
                   .limit(BATCH_SIZE).all())
        ids = []
        for row in claimed:
            row.status = 'sending'
            row.attempt_count += 1
            ids.append(row.id)
    db.session.commit()

    sent = failed = skipped = 0
    for delivery_id in ids:
        row = db.session.get(StoryNotificationDelivery, delivery_id)
        # Unsubscribe after campaign creation must be respected.
        subscriber = db.session.get(StoryEmailSubscriber, row.subscriber_id)
        if not subscriber or subscriber.status != 'active' or not subscriber.confirmed_at:
            row.status = 'skipped'
            skipped += 1
        else:
            try:
                send_story_email(row)
                row.status = 'sent'
                row.sent_at = now_utc()
                sent += 1
            except Exception:
                current_app.logger.exception('Story notification email failure: delivery_id=%s', delivery_id)
                row.status = 'failed'
                row.last_error = 'SMTP send failed; review before retrying.'
                failed += 1
        db.session.commit()
    stats = campaign_stats(campaign.id)
    if stats.get('queued', 0) == 0 and stats.get('sending', 0) == 0:
        campaign.status = 'completed'
        campaign.completed_at = now_utc()
    else:
        campaign.status = 'sending'
    db.session.commit()
    flash(f'Batch: {sent} accepted by SMTP, {failed} failed, {skipped} unsubscribed/skipped.', 'success')
    return redirect(url_for('.detail', campaign_id=campaign.id))


@notification_bp.post('/<int:campaign_id>/cancel')
def cancel(campaign_id):
    guard = require_admin()
    if guard:
        return guard
    require_csrf()
    campaign = db.get_or_404(StoryNotificationCampaign, campaign_id)
    if campaign.status not in ('completed', 'cancelled'):
        (StoryNotificationDelivery.query.filter_by(campaign_id=campaign.id, status='queued')
         .update({'status': 'skipped'}, synchronize_session=False))
        campaign.status = 'cancelled'
        db.session.commit()
    flash('Remaining queued deliveries cancelled.', 'success')
    return redirect(url_for('.detail', campaign_id=campaign.id))
