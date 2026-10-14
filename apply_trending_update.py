"""KALXA Stories: add KwaNdebele news + curated Trending Stories.
Run from repository root after copying this script there: python apply_trending_update.py
Does NOT connect to a database or run migrations. Re-runnable.
"""
from pathlib import Path
import shutil
import ast

ROOT = Path(__file__).resolve().parent
changes = {}

def load(relative):
    p = ROOT / relative
    if not p.exists():
        raise RuntimeError(f"Missing {relative}. Copy this installer to the KALXA Stories repository root.")
    return p.read_text(encoding='utf-8')

def replace_once(s, original, new, file):
    count = s.count(original)
    if count != 1:
        raise RuntimeError(f"{file}: expected exactly one insertion anchor; found {count}. No files written.")
    return s.replace(original, new, 1)

# 1: five categories in the EXISTING seeder (not a schema change).
f = 'seed_story_categories.py'
s = load(f)
if '"news-kwandebele"' not in s:
    original = '    ("creators", "Who is creating, entertaining and influencing locally?", "Artists, creators and local voices.", 4),'
    s = replace_once(s, original, original + '\n    ("news-kwandebele", "Latest news in KwaNdebele", "News, updates, developments and community announcements across KwaNdebele.", 5),', f)
    s = s.replace('Four KALXA Stories categories are ready.', 'Five KALXA Stories categories are ready.')
changes[f] = s

# 2: enable news in the paid submission form dropdown / server-side validation.
f = 'app/paid/service.py'
s = load(f)
if "'news-kwandebele':" not in s:
    original = "    'creators': 'Who is creating, entertaining and influencing locally?',"
    s = replace_once(s, original, original + "\n    'news-kwandebele': 'Latest news in KwaNdebele',", f)
changes[f] = s

# 3: homepage: fifth category + trending section just after categories.
f = 'templates/home.html'
s = load(f)
if "category_slug='news-kwandebele'" not in s:
    needle = '''      <a class="story-category-button" href="{{ url_for('public.story_category', category_slug='creators') }}"><span><small>Creators &amp; culture</small><strong>Who is creating, entertaining and influencing locally?</strong></span><span class="category-arrow" aria-hidden="true">↗</span></a>'''
    addition = '''\n      <a class="story-category-button" href="{{ url_for('public.story_category', category_slug='news-kwandebele') }}"><span><small>KwaNdebele news</small><strong>Latest news in KwaNdebele</strong></span><span class="category-arrow" aria-hidden="true">↗</span></a>'''
    s = replace_once(s, needle, needle + addition, f)
if 'id="trending-stories-heading"' not in s:
    anchor = '{% if featured_article %}'
    section = '''<!-- =========================================================
     TRENDING STORIES — CURATED: RESTAURANT-LINKED + PAID FEATURED
     This does not modify any restaurant eligibility or payment rule.
========================================================== -->
{% if trending_articles %}
<section class="latest-section trending-section" aria-labelledby="trending-stories-heading">
  <div class="page-container">
    <div class="latest-header">
      <div class="latest-header-copy">
        <span>From our community</span>
        <h2 class="latest-heading-title" id="trending-stories-heading">Trending stories</h2>
      </div>
      <a href="{{ url_for('public.stories') }}">Explore all stories →</a>
    </div>
    <div class="story-grid">
      {% for article in trending_articles %}
      <article class="story-card">
        <a class="story-image-link" href="{{ url_for('public.article_detail', slug=article.slug) }}" aria-label="Read {{ article.title }}">
          <div class="story-image">
            {% if article.display_cover_image_url %}
            <img src="{{ article.display_cover_image_url }}" alt="{{ article.title }}" loading="lazy">
            {% else %}
            <div class="image-placeholder small"><span>K</span></div>
            {% endif %}
          </div>
        </a>
        <div class="story-card-content">
          <div class="story-meta">
            {% if article.is_sponsored %}<span class="sponsored-label">Sponsored</span>{% endif %}
            <span>{{ article.category.name if article.category else article.article_type.replace('_', ' ').title() }}</span>
          </div>
          <h3><a href="{{ url_for('public.article_detail', slug=article.slug) }}">{{ article.title }}</a></h3>
          {% if article.excerpt %}<p>{{ article.excerpt }}</p>{% endif %}
          <a class="read-link" href="{{ url_for('public.article_detail', slug=article.slug) }}">Read story <span>→</span></a>
        </div>
      </article>
      {% endfor %}
    </div>
  </div>
</section>
{% endif %}

'''
    s = replace_once(s, anchor, section + anchor, f)
changes[f] = s

# 4: public homepage: select restaurant-linked stories and active paid featured articles.
# 'Trending' is curated placement (not an engagement ranking). Preserve normal feeds.
f = 'app/public/routes.py'
s = load(f)
if 'def kalxa_trending_articles(' not in s:
    marker = '# ============================================================\n# HOME\n# ============================================================'
    helper = '''# ============================================================
# CURATED TRENDING STORIES (DISPLAY ONLY)
# ============================================================

def kalxa_trending_articles(limit=6):
    """Return active restaurant-linked stories and actively paid featured stories.

    Restaurant association is not proof of a current Premium subscription;
    eligibility remains exclusively in the existing Ticketing integration.
    No changes to ArticleRestaurant or Premium subscription policies.
    """
    from app.models import ArticleRestaurant
    from app.paid.models import PaidStoryPublication

    now = datetime.now(timezone.utc)
    active_featured = (
        db.session.query(PaidStoryPublication.article_id)
        .filter(
            PaidStoryPublication.starts_at <= now,
            PaidStoryPublication.ends_at > now,
            PaidStoryPublication.featured_until > now,
        )
        .subquery()
    )
    linked_restaurants = (
        db.session.query(ArticleRestaurant.article_id)
        .distinct()
        .subquery()
    )

    candidates = (
        active_published_article_query()
        .filter(or_(
            Article.id.in_(db.session.query(active_featured.c.article_id)),
            Article.id.in_(db.session.query(linked_restaurants.c.article_id)),
        ))
        .order_by(Article.published_at.desc(), Article.created_at.desc())
        .limit(100)
        .all()
    )

    featured_ids = set(
        row[0] for row in db.session.query(active_featured.c.article_id).all()
    )
    # Paid featured placements first; remaining restaurant stories newest first.
    candidates.sort(key=lambda article: article.id not in featured_ids)
    return candidates[:limit]


'''
    s = replace_once(s, marker, helper + marker, f)
if 'trending_articles=kalxa_trending_articles(),' not in s:
    home_pos = s.index('def home():')
    after = s.index('def stories():')
    chunk = s[home_pos:after]
    chunk = replace_once(chunk, '        featured_article=featured_article,', '        featured_article=featured_article,\n        trending_articles=kalxa_trending_articles(),', f + ' home')
    s = s[:home_pos] + chunk + s[after:]
changes[f] = s

# Preflight Python source syntax and verify semantic invariants.
for name, content in changes.items():
    if name.endswith('.py'):
        ast.parse(content, filename=name)
assert 'ArticleRestaurant' in changes['app/public/routes.py']
assert "category_slug='news-kwandebele'" in changes['templates/home.html']
for name, content in changes.items():
    p = ROOT / name
    old = p.read_text(encoding='utf-8')
    if content == old:
        print('UNCHANGED', name)
        continue
    backup = p.with_name(p.name + '.trending.bak')
    if not backup.exists():
        shutil.copy2(p, backup)
    p.write_text(content, encoding='utf-8')
    print('UPDATED', name, '(backup:', backup.name + ')')
print('Completed. NO migrations, seeding, or database operations performed.')
