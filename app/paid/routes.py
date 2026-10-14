"""Independent paid editorial application; does not touch restaurant subscription rules."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4
from urllib.parse import urlparse
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import Article
from app.paid.models import (PaidStorySubmission, PaidStoryPayment,
                             PaidStoryWebhookEvent, PaidStoryPublication)
from app.paid.service import (ARTICLE_PRICES, FEATURE_PRICES, CATEGORIES, quote,
                              create_checkout, verify_signature)

paid_bp = Blueprint('paid_stories', __name__)

def authenticated():
    return bool(__import__('flask').session.get('kalxa_stories_admin'))

def require_admin():
    if not authenticated():
        abort(403)

def token_hash(token):
    return sha256(token.encode()).hexdigest()

def access_allowed(submission):
    from hmac import compare_digest
    return compare_digest(submission.access_token_hash, token_hash(request.args.get('token', '')))

@paid_bp.route('/stories/submit', methods=['GET', 'POST'])
def submit_story():
    if request.method == 'GET':
        return render_template('paid/submit.html', article_prices=ARTICLE_PRICES,
                               feature_prices=FEATURE_PRICES, categories=CATEGORIES)
    if request.content_length and request.content_length > 30_000:
        abort(413)
    fields = {name: request.form.get(name, '').strip() for name in (
        'applicant_type', 'applicant_name', 'contact_name', 'email', 'whatsapp',
        'location', 'category_slug', 'title', 'description', 'website')}
    try:
        duration = int(request.form.get('duration_days', ''))
        featured = int(request.form.get('featured_days', ''))
        price = quote(duration, featured)
    except (ValueError, TypeError):
        flash('Choose a valid duration and featured option.', 'error')
        return redirect(url_for('paid_stories.submit_story'))
    if (fields['applicant_type'] not in ('business', 'creator', 'organiser')
            or fields['category_slug'] not in CATEGORIES
            or not all(fields[k] for k in ('applicant_name', 'contact_name', 'email', 'whatsapp', 'location', 'title', 'description'))
            or '@' not in fields['email']
            or len(fields['description']) < 30
            or any(len(fields[k]) > limit for k, limit in {
                'applicant_name': 150, 'contact_name': 150, 'email': 254,
                'whatsapp': 35, 'location': 180, 'title': 250, 'description': 6000,
                'website': 500}.items())
            or (fields['website'] and (urlparse(fields['website']).scheme not in ('http', 'https')
                                        or not urlparse(fields['website']).hostname))):
        flash('Please check your details and story (minimum 30 characters).', 'error')
        return redirect(url_for('paid_stories.submit_story'))
    token = token_urlsafe(32)
    sub = PaidStorySubmission(reference='KS-' + uuid4().hex[:18].upper(),
        access_token_hash=token_hash(token), duration_days=duration, featured_days=featured,
        amount_cents=price, **fields)
    db.session.add(sub)
    db.session.commit()
    return redirect(url_for('paid_stories.start_checkout', reference=sub.reference, token=token))

@paid_bp.post('/stories/submissions/<reference>/checkout')
def retry_checkout(reference):
    sub = PaidStorySubmission.query.filter_by(reference=reference).first_or_404()
    if not access_allowed(sub):
        abort(403)
    return redirect(url_for('paid_stories.start_checkout', reference=reference, token=request.args.get('token')))

@paid_bp.get('/stories/submissions/<reference>/checkout')
def start_checkout(reference):
    sub = PaidStorySubmission.query.filter_by(reference=reference).first_or_404()
    if not access_allowed(sub):
        abort(403)
    if sub.payment_status == 'paid':
        return redirect(url_for('paid_stories.submission_status', reference=reference, token=request.args['token']))
    old = PaidStoryPayment.query.filter_by(submission_id=sub.id).order_by(PaidStoryPayment.id.desc()).first()
    if old and old.status == 'created' and old.checkout_url:
        return redirect(old.checkout_url)
    payment = PaidStoryPayment(submission_id=sub.id, amount_cents=sub.amount_cents)
    db.session.add(payment)
    db.session.commit()
    try:
        return_url = url_for('paid_stories.submission_status', reference=reference, token=request.args['token'], _external=True)
        checkout = create_checkout(sub, payment, return_url, return_url)
        payment.checkout_id = checkout['id']
        payment.checkout_url = checkout['redirectUrl']
        payment.status = 'created'
        db.session.commit()
        return redirect(payment.checkout_url)
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Unable to initialise story checkout for %s', reference)
        flash('Checkout is unavailable. Please try again later. No article has been activated.', 'error')
        return redirect(url_for('paid_stories.submission_status', reference=reference, token=request.args['token']))

@paid_bp.get('/stories/submissions/<reference>/status')
def submission_status(reference):
    sub = PaidStorySubmission.query.filter_by(reference=reference).first_or_404()
    if not access_allowed(sub):
        abort(403)
    return render_template('paid/status.html', sub=sub, token=request.args['token'])

@paid_bp.post('/webhooks/yoco/stories')
def yoco_webhook():
    raw = request.get_data(cache=False)
    if len(raw) > 100_000 or not verify_signature(request.headers, raw):
        abort(403)
    obj = __import__('json').loads(raw)
    event_id = request.headers.get('webhook-id')
    if not isinstance(obj, dict) or not isinstance(obj.get('payload'), dict):
        abort(400)
    if PaidStoryWebhookEvent.query.filter_by(event_id=event_id).first():
        return {'ok': True}, 200
    event_type = obj.get('type')
    p = obj['payload']
    if event_type not in ('payment.succeeded', 'payment.failed'):
        db.session.add(PaidStoryWebhookEvent(event_id=event_id))
        db.session.commit()
        return {'ok': True}, 200
    metadata = p.get('metadata') if isinstance(p.get('metadata'), dict) else {}
    checkout_id = metadata.get('checkoutId')
    payment = PaidStoryPayment.query.filter_by(checkout_id=checkout_id).first() if isinstance(checkout_id, str) else None
    if payment is None:
        current_app.logger.warning('Unknown Yoco checkout in paid Stories event %s', event_id)
        abort(409)  # Request retry while checkout record is being persisted.
    sub = db.session.get(PaidStorySubmission, payment.submission_id)
    expected_mode = current_app.config.get('YOCO_EXPECTED_MODE', __import__('os').environ.get('YOCO_EXPECTED_MODE', 'test'))
    if p.get('mode') != expected_mode:
        abort(403)
    if (p.get('amount') != payment.amount_cents or p.get('currency') != 'ZAR'
            or payment.amount_cents != sub.amount_cents):
        current_app.logger.error('Payment mismatch for submission %s', sub.reference)
        abort(409)
    if event_type == 'payment.succeeded':
        if p.get('status') != 'succeeded' or not isinstance(p.get('id'), str):
            abort(409)
        if payment.payment_id and payment.payment_id != p['id']:
            abort(409)
        payment.payment_id = p['id']
        payment.status = 'paid'
        sub.payment_status = 'paid'
        sub.review_status = 'pending_review' if sub.review_status == 'awaiting_payment' else sub.review_status
        if sub.paid_at is None:
            sub.paid_at = datetime.now(timezone.utc)
    elif sub.payment_status != 'paid':
        payment.status = 'failed'
    db.session.add(PaidStoryWebhookEvent(event_id=event_id))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {'ok': True}, 200
    return {'ok': True}, 200

@paid_bp.get('/admin/paid-stories')
def admin_submissions():
    require_admin()
    subs = PaidStorySubmission.query.order_by(PaidStorySubmission.created_at.desc()).limit(200).all()
    return render_template('paid/admin_list.html', submissions=subs)

@paid_bp.get('/admin/paid-stories/<int:submission_id>')
def admin_submission(submission_id):
    require_admin()
    sub = db.session.get(PaidStorySubmission, submission_id)
    if not sub:
        abort(404)
    pub = PaidStoryPublication.query.filter_by(submission_id=sub.id).first()
    return render_template('paid/admin_detail.html', sub=sub, publication=pub)

@paid_bp.post('/admin/paid-stories/<int:submission_id>/reject')
def admin_reject(submission_id):
    require_admin()
    sub = db.session.get(PaidStorySubmission, submission_id)
    if not sub or sub.article_id:
        abort(409)
    sub.review_status = 'rejected'
    sub.admin_notes = request.form.get('notes', '')[:2000]
    db.session.commit()
    flash('Submission rejected. Handle any refund separately according to your policy.', 'success')
    return redirect(url_for('paid_stories.admin_submission', submission_id=sub.id))

@paid_bp.post('/admin/paid-stories/<int:submission_id>/prepare')
def admin_prepare(submission_id):
    require_admin()
    sub = db.session.get(PaidStorySubmission, submission_id)
    if not sub or sub.payment_status != 'paid' or sub.review_status not in ('pending_review', 'approved') or sub.article_id:
        abort(409)
    slug = 'paid-' + sub.reference.lower()
    article = Article(title=sub.title, slug=slug, excerpt=sub.description[:260],
                      body='<p>' + __import__('markupsafe').escape(sub.description).replace('\n', '</p><p>') + '</p>',
                      article_type='sponsored', is_sponsored=True, status='draft')
    if hasattr(Article, 'category_id'):
        from app.models.story_category import StoryCategory
        category = StoryCategory.query.filter_by(slug=sub.category_slug).first()
        if category:
            article.category_id = category.id
    db.session.add(article)
    db.session.flush()
    sub.article_id = article.id
    sub.review_status = 'approved'
    db.session.commit()
    flash('Draft created. Edit article and return here to publish after approval.', 'success')
    return redirect(url_for('paid_stories.admin_submission', submission_id=sub.id))

@paid_bp.post('/admin/paid-stories/<int:submission_id>/publish')
def admin_publish(submission_id):
    require_admin()
    sub = db.session.get(PaidStorySubmission, submission_id)
    if not sub or sub.payment_status != 'paid' or sub.review_status != 'approved' or not sub.article_id:
        abort(409)
    article = db.session.get(Article, sub.article_id)
    if not article or PaidStoryPublication.query.filter_by(submission_id=sub.id).first():
        abort(409)
    now = datetime.now(timezone.utc)
    article.status = 'published'
    article.is_sponsored = True
    article.published_at = now
    # Paid-only publication lifecycle, independent from Premium restaurant expiry.
    end = now + timedelta(days=sub.duration_days)
    article.expires_at = end
    pub = PaidStoryPublication(submission_id=sub.id, article_id=article.id,
           starts_at=now, ends_at=end,
           featured_until=now + timedelta(days=sub.featured_days) if sub.featured_days else None)
    db.session.add(pub)
    sub.review_status = 'published'
    db.session.commit()
    flash('Paid article published. Duration starts now.', 'success')
    return redirect(url_for('paid_stories.admin_submission', submission_id=sub.id))
