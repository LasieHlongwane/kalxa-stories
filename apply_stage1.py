"""Apply Stage 1 edits to your EXISTING KALXA Stories repository.

Place this file in repository root alongside config.py, with app/ and templates/.
Run: python apply_stage1.py
The script validates every expected insertion before writing; originals are backed up
as .stage1.bak files. Does NOT run migrations or touch the database.
"""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parent


def once_replace(content, old, new, label):
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}. No files changed.")
    return content.replace(old, new, 1)


def update_sources():
    edits = {}

    path = ROOT / "app/models/article.py"
    content = path.read_text(encoding="utf-8")
    marker = '    # ==========================================\n    # RESTAURANTS\n    # =========================================='
    addition = '''    # ============================================================
    # EDITORIAL CATEGORY (INDEPENDENT OF PREMIUM RESTAURANTS)
    # ============================================================
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("story_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    category = db.relationship("StoryCategory", back_populates="articles")

'''
    if "category_id = db.Column" not in content:
        content = once_replace(content, marker, addition + marker, str(path))
    edits[path] = content

    path = ROOT / "app/models/__init__.py"
    content = path.read_text(encoding="utf-8")
    if 'from app.models.story_category import StoryCategory' not in content:
        content = 'from app.models.story_category import StoryCategory\n' + content
        content = once_replace(content, '__all__ = [', '__all__ = [\n    "StoryCategory",', str(path))
    edits[path] = content

    path = ROOT / "app/public/routes.py"
    content = path.read_text(encoding="utf-8")
    if '    StoryCategory,\n' not in content:
        content = once_replace(content, '    Article,\n    StoryAnalyticsEvent,', '    Article,\n    StoryCategory,\n    StoryAnalyticsEvent,', str(path))
    marker = '# ============================================================\n# SUBMIT ARTICLE COMMENT\n# ============================================================'
    route = '''# ============================================================
# EDITORIAL CATEGORY PAGE (NO RESTAURANT ELIGIBILITY CHANGES)
# ============================================================

@public_bp.route("/stories/category/<string:category_slug>")
def story_category(category_slug):
    category = StoryCategory.query.filter_by(
        slug=category_slug,
        is_active=True,
    ).first_or_404()

    articles = (
        active_published_article_query()
        .filter(Article.category_id == category.id)
        .order_by(Article.published_at.desc(), Article.created_at.desc())
        .all()
    )
    return render_template("category.html", category=category, articles=articles)


'''
    if 'def story_category(' not in content:
        content = once_replace(content, marker, route + marker, str(path))
    edits[path] = content

    path = ROOT / "app/admin/routes.py"
    content = path.read_text(encoding="utf-8")
    if '    StoryCategory,\n' not in content:
        content = once_replace(content, '    ArticleRestaurant,\n    StoryAnalyticsEvent,', '    ArticleRestaurant,\n    StoryCategory,\n    StoryAnalyticsEvent,', str(path))
    # Only query categories for editor pages, not for existing dashboard or login.
    marker = '# ============================================================\n# CREATE ARTICLE\n# ============================================================'
    helper = '''def available_story_categories():
    """Categories for the editor; no relationship to Ticketing permissions."""
    return (
        StoryCategory.query.filter_by(is_active=True)
        .order_by(StoryCategory.display_order.asc(), StoryCategory.name.asc())
        .all()
    )


'''
    if 'def available_story_categories()' not in content:
        content = once_replace(content, marker, helper + marker, str(path))

    # All existing editor renders get their categories, with no change to restaurant_ids.
    needle = '"admin/article_form.html",'
    if 'story_categories=available_story_categories(),' not in content:
        if content.count(needle) != 6:
            raise RuntimeError(f"{path}: expected 6 editor renders; found {content.count(needle)}. No files changed.")
        content = content.replace(needle, needle + '\n                story_categories=available_story_categories(),')

    marker = '    # --------------------------------------------------------\n    # DUPLICATE SLUG\n    # --------------------------------------------------------'
    validation = '''    # --------------------------------------------------------
    # OPTIONAL EDITORIAL CATEGORY — NEVER CHECK RESTAURANT ENTITLEMENTS
    # --------------------------------------------------------
    raw_category_id = request.form.get("category_id", "").strip()
    category_id = None
    if raw_category_id:
        try:
            category_id = int(raw_category_id)
        except ValueError:
            flash("Invalid story category.", "error")
            return False
        category_exists = StoryCategory.query.filter_by(
            id=category_id, is_active=True
        ).first()
        if category_exists is None:
            flash("Selected story category does not exist.", "error")
            return False


'''
    if 'raw_category_id = request.form.get("category_id"' not in content:
        content = once_replace(content, marker, validation + marker, str(path))
    marker = '    article.article_type = (\n        article_type\n    )'
    if '    article.category_id = category_id' not in content:
        content = once_replace(content, marker, marker + '\n\n    article.category_id = category_id', str(path))
    edits[path] = content

    path = ROOT / "templates/admin/article_form.html"
    content = path.read_text(encoding="utf-8")
    marker = '        <!-- =============================================\n             SEO\n        ============================================== -->'
    markup = '''        <!-- =============================================
             EDITORIAL CATEGORY — OPTIONAL AND INDEPENDENT
             OF THE PREMIUM RESTAURANT ASSOCIATION
        ============================================== -->
        <div class="form-section">
            <h2>Story Category</h2>
            <div class="field">
                <label for="story-category">Show this story under</label>
                {% set current_category = request.form.get(
                    'category_id', article.category_id if article and article.category_id else ''
                ) | string %}
                <select id="story-category" name="category_id">
                    <option value="" {% if not current_category %}selected{% endif %}>
                        No category (existing/default publishing)
                    </option>
                    {% for category in story_categories | default([], true) %}
                    <option value="{{ category.id }}" {% if current_category == category.id|string %}selected{% endif %}>
                        {{ category.name }}
                    </option>
                    {% endfor %}
                </select>
                <div class="help">
                    Optional. Categorisation changes where a story is listed, NOT its
                    Kalxa Ticketing restaurant links, Premium benefits, or payment rules.
                </div>
            </div>
        </div>


'''
    if 'id="story-category"' not in content:
        content = once_replace(content, marker, markup + marker, str(path))
    edits[path] = content

    path = ROOT / "templates/home.html"
    content = path.read_text(encoding="utf-8")
    css_marker = '    /* =====================================================\n       FEATURED\n    ====================================================== */'
    css = '''    /* =====================================================
       EDITORIAL CATEGORY NAVIGATION
    ====================================================== */
    .story-categories { padding: 65px 0 10px; }
    .story-categories-heading { margin: 0 0 12px; font-family: var(--kalxa-serif); font-size: clamp(32px, 4vw, 48px); font-weight: 500; }
    .story-categories-intro { color: var(--kalxa-text-soft); font-size: 13px; line-height: 1.7; margin: 0 0 29px; }
    .story-categories-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 15px; }
    .story-category-button { display: flex; align-items: center; justify-content: space-between; gap: 18px; min-height: 135px; padding: 25px 28px; background: var(--kalxa-paper); border: 1px solid var(--kalxa-border); transition: border-color .2s, transform .2s, box-shadow .2s; }
    .story-category-button:hover { border-color: var(--kalxa-gold); transform: translateY(-2px); box-shadow: var(--kalxa-shadow); }
    .story-category-button small { display: block; color: var(--kalxa-gold-dark); font-size: 9px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 11px; }
    .story-category-button strong { display: block; color: var(--kalxa-ink); font-family: var(--kalxa-serif); font-size: clamp(19px, 2.2vw, 27px); font-weight: 500; line-height: 1.2; }
    .story-category-button .category-arrow { color: var(--kalxa-gold-dark); font-size: 26px; flex-shrink: 0; }
    @media (max-width: 650px) { .story-categories { padding: 42px 0 5px; } .story-categories-grid { grid-template-columns: 1fr; } .story-category-button { min-height: 112px; padding: 21px; } }


'''
    if '.story-categories-grid' not in content:
        content = once_replace(content, css_marker, css + css_marker, str(path))
    marker = '{% if featured_article %}'
    markup = '''<!-- =========================================================
     STORY CATEGORIES — NEW NAVIGATION, EXISTING STORIES INTACT
========================================================== -->
<section class="story-categories" aria-labelledby="story-categories-heading">
  <div class="page-container">
    <div class="section-heading"><span>Explore the journal</span></div>
    <h2 class="story-categories-heading" id="story-categories-heading">What would you like to discover?</h2>
    <p class="story-categories-intro">Explore the local people, places, events and experiences shaping our communities.</p>
    <div class="story-categories-grid">
      <a class="story-category-button" href="{{ url_for('public.story_category', category_slug='local') }}"><span><small>Local discoveries</small><strong>What is happening locally?</strong></span><span class="category-arrow" aria-hidden="true">↗</span></a>
      <a class="story-category-button" href="{{ url_for('public.story_category', category_slug='experiences') }}"><span><small>Events &amp; experiences</small><strong>What experiences can people attend?</strong></span><span class="category-arrow" aria-hidden="true">↗</span></a>
      <a class="story-category-button" href="{{ url_for('public.story_category', category_slug='food') }}"><span><small>Food &amp; lifestyle</small><strong>Where can people eat, socialise and explore?</strong></span><span class="category-arrow" aria-hidden="true">↗</span></a>
      <a class="story-category-button" href="{{ url_for('public.story_category', category_slug='creators') }}"><span><small>Creators &amp; culture</small><strong>Who is creating, entertaining and influencing locally?</strong></span><span class="category-arrow" aria-hidden="true">↗</span></a>
    </div>
  </div>
</section>

'''
    if 'id="story-categories-heading"' not in content:
        content = once_replace(content, marker, markup + marker, str(path))
    edits[path] = content

    # Preflight: ensure new files are present and no missing source paths.
    for target in edits:
        if not target.exists():
            raise FileNotFoundError(f"Required source file missing: {target}")

    # Apply once all validations have passed.
    changed = 0
    for target, new_content in edits.items():
        old_content = target.read_text(encoding="utf-8")
        if old_content == new_content:
            print(f"UNCHANGED {target.relative_to(ROOT)}")
            continue
        backup = target.with_name(target.name + ".stage1.bak")
        if not backup.exists():
            shutil.copy2(target, backup)
        target.write_text(new_content, encoding="utf-8")
        print(f"UPDATED   {target.relative_to(ROOT)} (backup: {backup.name})")
        changed += 1

    print(f"Done: {changed} files updated. No migration or database operation performed.")


if __name__ == "__main__":
    update_sources()
