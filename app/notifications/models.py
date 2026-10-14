from datetime import datetime, timezone
from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class StoryNotificationCampaign(db.Model):
    __tablename__ = 'story_notification_campaigns'
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, nullable=False, index=True)  # external reference; never block existing article deletes
    article_title = db.Column(db.String(250), nullable=False)
    article_slug = db.Column(db.String(300), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    # CSV of distinct selected area names, or 'all'; immutable once created.
    target_locations = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='queued', index=True)
    total_recipients = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    deliveries = db.relationship('StoryNotificationDelivery', back_populates='campaign', lazy='select')


class StoryNotificationDelivery(db.Model):
    __tablename__ = 'story_notification_deliveries'
    __table_args__ = (db.UniqueConstraint('campaign_id', 'subscriber_id', name='uq_story_notification_campaign_subscriber'),)
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('story_notification_campaigns.id', ondelete='CASCADE'), nullable=False, index=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('story_email_subscribers.id', ondelete='RESTRICT'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='queued', index=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.String(240), nullable=True)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    campaign = db.relationship('StoryNotificationCampaign', back_populates='deliveries')
    subscriber = db.relationship('StoryEmailSubscriber')
