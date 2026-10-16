#from datetime import datetime, timezone
from datetime import datetime, timezone

from app.extensions import db

def utcnow():
    return datetime.now(timezone.utc)

class PaidStorySubmission(db.Model):
    __tablename__ = 'paid_story_submissions'
    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(40), unique=True, nullable=False, index=True)
    access_token_hash = db.Column(db.String(64), nullable=False)
    applicant_type = db.Column(db.String(20), nullable=False)
    applicant_name = db.Column(db.String(150), nullable=False)
    contact_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    whatsapp = db.Column(db.String(35), nullable=False)
    location = db.Column(db.String(180), nullable=False)
    category_slug = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(250), nullable=False)
    description = db.Column(db.Text, nullable=False)
    website = db.Column(db.String(500))
    amount_cents = db.Column(db.Integer, nullable=False)
    payment_status = db.Column(db.String(25), nullable=False, default='pending', index=True)
    review_status = db.Column(db.String(25), nullable=False, default='awaiting_payment', index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    paid_at = db.Column(db.DateTime(timezone=True))
    article_id = db.Column(db.Integer, db.ForeignKey('articles.id', ondelete='SET NULL'), unique=True, nullable=True)
    article = db.relationship('Article', foreign_keys=[article_id])
    admin_notes = db.Column(db.Text)

class PaidStoryPayment(db.Model):
    __tablename__ = 'paid_story_payments'
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('paid_story_submissions.id'), nullable=False, index=True)
    submission = db.relationship('PaidStorySubmission', backref='payments')
    checkout_id = db.Column(db.String(160), unique=True, nullable=True)
    checkout_url = db.Column(db.Text)
    payment_id = db.Column(db.String(160), unique=True, nullable=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(25), nullable=False, default='initiated')
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

class PaidStoryWebhookEvent(db.Model):
    __tablename__ = 'paid_story_webhook_events'
    event_id = db.Column(db.String(200), primary_key=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

class PaidStoryPublication(db.Model):
    __tablename__ = 'paid_story_publications'
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('paid_story_submissions.id'), nullable=False, unique=True)
    article_id = db.Column(db.Integer, db.ForeignKey('articles.id'), nullable=False, unique=True)
    starts_at = db.Column(db.DateTime(timezone=True), nullable=False)
    featured_until = db.Column(db.DateTime(timezone=True))
    submission = db.relationship('PaidStorySubmission')
    article = db.relationship('Article')
