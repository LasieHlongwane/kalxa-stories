"""Paid Stories prices and Yoco Checkout API operations."""
import os
import base64
import hashlib
import hmac
import time
from urllib.parse import urlparse
import requests
from flask import current_app

# Introductory prices, in cents. Customize only here before launching.
ARTICLE_PRICES = {7: 4900, 14: 8900, 30: 14900, 60: 24900, 90: 34900}
FEATURE_PRICES = {0: 0, 7: 4900, 14: 8900, 30: 14900}
CATEGORIES = {
    'local': "What's happening locally?",
    'experiences': 'What experiences can people attend?',
    'food': 'Where can people eat, socialise and explore?',
    'creators': 'Who is creating, entertaining and influencing locally?',
}

def quote(duration, featured):
    if duration not in ARTICLE_PRICES or featured not in FEATURE_PRICES or featured > duration:
        raise ValueError('Invalid publishing duration or featured placement.')
    return ARTICLE_PRICES[duration] + FEATURE_PRICES[featured]

def checkout_url_is_safe(url):
    u = urlparse(url or '')
    return u.scheme == 'https' and u.hostname in {'c.yoco.com', 'pay.yoco.com', 'checkout.yoco.com'}

def create_checkout(submission, payment, success_url, cancel_url):
    secret = current_app.config.get('YOCO_SECRET_KEY') or os.environ.get('YOCO_SECRET_KEY')
    if not secret:
        raise RuntimeError('YOCO_SECRET_KEY is missing.')
    data = {
        'amount': submission.amount_cents,
        'currency': 'ZAR',
        'successUrl': success_url,
        'cancelUrl': cancel_url,
        'failureUrl': cancel_url,
        'metadata': {'kalxa_story_reference': submission.reference},
        'externalId': submission.reference,
    }
    response = requests.post('https://payments.yoco.com/api/checkouts', json=data, headers={
        'Authorization': f'Bearer {secret}', 'Content-Type': 'application/json',
        'Idempotency-Key': f'kalxa-stories-payment-{payment.id}',
    }, timeout=15)
    response.raise_for_status()
    data = response.json()
    if (not isinstance(data, dict) or not isinstance(data.get('id'), str)
            or data.get('amount') != submission.amount_cents or data.get('currency') != 'ZAR'
            or not checkout_url_is_safe(data.get('redirectUrl'))):
        raise RuntimeError('Yoco returned an invalid checkout response.')
    return data

def verify_signature(headers, body):
    secret = current_app.config.get('YOCO_WEBHOOK_SECRET') or os.environ.get('YOCO_WEBHOOK_SECRET', '')
    event_id = headers.get('webhook-id', '')
    ts = headers.get('webhook-timestamp', '')
    sig = headers.get('webhook-signature', '')
    if not secret.startswith('whsec_') or not event_id or not ts.isdigit() or not sig:
        return False
    if abs(int(time.time()) - int(ts)) > 180:
        return False
    try:
        key = base64.b64decode(secret[6:], validate=True)
        payload = event_id.encode() + b'.' + ts.encode() + b'.' + body
        expected = base64.b64encode(hmac.new(key, payload, hashlib.sha256).digest()).decode()
        return any(hmac.compare_digest(part[3:], expected) for part in sig.split() if part.startswith('v1,'))
    except (ValueError, TypeError):
        return False
