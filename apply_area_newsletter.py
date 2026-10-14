"""Safe, additive KALXA Stories newsletter installer. No database operations.
Run from project root after merging app/newsletter and templates/newsletter:
    python apply_area_newsletter.py
"""
from pathlib import Path
import ast
import shutil

ROOT = Path(__file__).resolve().parent
changes = {}

def read(relative):
    file = ROOT / relative
    if not file.exists():
        raise RuntimeError(f'Missing file: {relative}. Run from KALXA Stories repository root.')
    return file.read_text(encoding='utf-8')

# App registration, without modifying existing blueprints.
f = 'app/__init__.py'
s = read(f)
if 'story_newsletter.newsletter_bp' not in s:
    anchor = '    return app'
    if s.count(anchor) != 1:
        raise RuntimeError(f'{f}: expected one return app anchor')
    s = s.replace(anchor, '''    # Area-based email subscribers (independent of restaurant & paid articles)
    from app.newsletter.models import StoryEmailSubscriber  # register model with Alembic
    from app.newsletter.routes import newsletter_bp
    app.register_blueprint(newsletter_bp)

''' + anchor, 1)
changes[f] = s

# Insert CTA before last endblock, leaving existing trending & latest intact.
f = 'templates/home.html'
s = read(f)
if 'kalxa-area-newsletter' not in s:
    section = '''
<!-- KALXA AREA NEWSLETTER: additive section -->
<section id="kalxa-area-newsletter" style="padding:80px 0;background:var(--kalxa-cream);border-top:1px solid var(--kalxa-border)" aria-labelledby="kalxa-newsletter-title">
 <div class="page-container" style="max-width:780px;text-align:center">
   <span class="hero-label">LOCAL STORIES · YOUR INBOX</span>
   <h2 id="kalxa-newsletter-title" style="font:500 clamp(34px,5vw,55px)/1.12 var(--kalxa-serif);margin:12px 0 22px">Stay connected to your community.</h2>
   <p style="color:var(--kalxa-text-soft);line-height:1.75">Subscribe for local Stories updates. Choose your closest area: KwaMhlanga, Kwaggafontein or Siyabuswa.</p>
   <a href="{{ url_for('story_newsletter.signup_page') }}" style="display:inline-block;background:var(--kalxa-black);color:white;padding:16px 28px;margin-top:16px;font-weight:700;font-size:13px">Subscribe to local stories →</a>
 </div>
</section>
'''
    anchor = '{% endblock %}'
    pos = s.rfind(anchor)
    if pos == -1:
        raise RuntimeError(f'{f}: no ending block')
    s = s[:pos] + section + '\n' + s[pos:]
changes[f] = s

# Add admin nav to actual existing nav, after New Story link; avoids URL build errors after registration.
f = 'templates/admin/base.html'
s = read(f)
if 'story_newsletter.admin_subscribers' not in s:
    anchor = '        </nav>'
    if s.count(anchor) != 1:
        raise RuntimeError(f'{f}: expected one nav close anchor')
    nav = '''            <a href="{{ url_for('story_newsletter.admin_subscribers') }}">Email Subscribers</a>

'''
    s = s.replace(anchor, nav + anchor, 1)
changes[f] = s

for name, content in changes.items():
    if name.endswith('.py'):
        ast.parse(content, filename=name)
for name, content in changes.items():
    path = ROOT / name
    if path.read_text(encoding='utf-8') == content:
        print('UNCHANGED', name)
        continue
    backup = path.with_name(path.name + '.area-newsletter.bak')
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(content, encoding='utf-8')
    print('UPDATED', name)
print('No migration or database changes performed. Do not deploy until migration is applied.')
