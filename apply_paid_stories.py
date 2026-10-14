"""Safely install Paid Stories additions into existing KALXA Stories repo."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
FEATURE_HELPER = (Path(__file__).resolve().parent / 'featured_helper.py.txt').read_text(encoding='utf-8')

def patch(relative, needle, replacement):
    path = ROOT / relative
    if not path.exists():
        raise SystemExit(f'Missing required file: {relative}')
    content = path.read_text(encoding='utf-8')
    if replacement in content:
        print('Already patched:', relative)
        return
    count = content.count(needle)
    if count != 1:
        raise SystemExit(f'Expected one anchor in {relative}; found {count}. No changes to this file.')
    shutil.copy2(path, str(path) + '.paid.bak')
    path.write_text(content.replace(needle, replacement, 1), encoding='utf-8')
    print('Updated:', relative)

patch('app/__init__.py',
    '    # ========================================================\n    # PUBLIC BLUEPRINT',
    '    # ========================================================\n    # PAID STORIES (INDEPENDENT OF PREMIUM RESTAURANTS)\n    # ========================================================\n    from app.paid import models as paid_models  # noqa: F401\n    from app.paid.routes import paid_bp\n    app.register_blueprint(paid_bp)\n\n    # ========================================================\n    # PUBLIC BLUEPRINT')

patch('templates/admin/base.html',
    '        </nav>',
    '''            <a href="{{ url_for('paid_stories.admin_submissions') }}">Paid Submissions</a>\n        </nav>''')

patch('templates/home.html',
    '{% endblock %}', # first block closes title - must instead target LAST endblock
    '{% endblock %}') if False else None
path = ROOT / 'templates/home.html'
if not path.exists():
    raise SystemExit('Missing templates/home.html')
content = path.read_text(encoding='utf-8')
marker = '<!-- KALXA PAID STORIES CALL TO ACTION -->'
if marker not in content:
    closing = '{% endblock %}'
    i = content.rfind(closing)
    if i == -1:
        raise SystemExit('Homepage has no endblock; aborting.')
    shutil.copy2(path, str(path) + '.paid.bak')
    content = content[:i] + '''\n<!-- KALXA PAID STORIES CALL TO ACTION -->
<section style="background:var(--kalxa-black);color:#f5efe3;padding:85px 0;text-align:center">
    <div class="page-container" style="max-width:760px">
        <span style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#d0ab70">Publish with KALXA</span>
        <h2 style="font-family:var(--kalxa-serif);font-size:clamp(37px,5vw,65px);font-weight:500">Have a story worth sharing?</h2>
        <p style="line-height:1.8;color:#c6bdb0;margin:20px auto 35px">Businesses, event organisers and creators can submit a story, choose a publishing duration and request featured placement.</p>
        <a href="{{ url_for('paid_stories.submit_story') }}" style="display:inline-block;background:#e6d4b7;color:#181511;padding:16px 28px;font-weight:700">Submit your story →</a>
    </div>
</section>
''' + content[i:]
    path.write_text(content, encoding='utf-8')
    print('Updated: templates/home.html')
else:
    print('Already patched: templates/home.html')

# Prioritize paid featured stories only during purchased placement window.
public_path = ROOT / 'app/public/routes.py'
public_text = public_path.read_text(encoding='utf-8')
if 'def order_by_active_paid_featured(articles):' not in public_text:
    featured_anchor = '    featured_article = ('
    if public_text.count(featured_anchor) != 1:
        raise SystemExit('Could not locate homepage featured article anchor')
    public_text = public_text.replace(featured_anchor,
        '    articles = order_by_active_paid_featured(articles)\n\n' + featured_anchor, 1)
    public_text += FEATURE_HELPER
    if 'def story_category(category_slug):' in public_text:
        start = public_text.index('def story_category(category_slug):')
        end = public_text.find('    return render_template(', start)
        if end != -1 and 'articles = order_by_active_paid_featured(articles)' not in public_text[start:end]:
            public_text = public_text[:end] + '    articles = order_by_active_paid_featured(articles)\n\n' + public_text[end:]
    shutil.copy2(public_path, str(public_path) + '.paid.bak')
    public_path.write_text(public_text, encoding='utf-8')
    print('Updated: app/public/routes.py (featured placement ordering)')

# Existing admin editor is allowed to edit paid article drafts, but must NOT bypass payment lifecycle.
admin = 'app/admin/routes.py'
path = ROOT / admin
content = path.read_text(encoding='utf-8')
anchor = '''    # --------------------------------------------------------
    # ASSIGN
    # --------------------------------------------------------'''
guard = '''    # --------------------------------------------------------
    # PAID ARTICLE LIFECYCLE GUARD
    # --------------------------------------------------------
    # Paid articles must be published through the independent
    # Paid Submissions admin review action, not this editor.
    from app.paid.models import PaidStorySubmission
    if article.id is not None:
        paid_submission = PaidStorySubmission.query.filter_by(article_id=article.id).first()
        if paid_submission is not None and status == "published" and paid_submission.review_status != "published":
            flash("Publish paid stories from the Paid Submissions screen after payment verification.", "error")
            return False

'''
if guard not in content:
    if content.count(anchor) != 1:
        raise SystemExit(f'Could not safely locate admin form assignment anchor. Found {content.count(anchor)}')
    shutil.copy2(path, str(path) + '.paid.bak')
    content = content.replace(anchor, guard + anchor, 1)
    path.write_text(content, encoding='utf-8')
    print('Updated: app/admin/routes.py (paid-only publishing guard)')

# Import paid model metadata during Flask-Migrate autogeneration via app factory above.
print('Paid publishing code installed. DATABASE MIGRATION STILL REQUIRED; do not deploy yet.')
