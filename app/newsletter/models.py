from datetime import datetime, timezone
from app.extensions import db


class StoryEmailSubscriber(db.Model):
    __tablename__ = 'story_email_subscribers'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False, unique=True, index=True)
    area = db.Column(db.String(40), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    consent_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    confirmed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    unsubscribed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Purpose-limited data: no GPS coordinates, addresses, or passwords.
