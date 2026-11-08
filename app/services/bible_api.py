import json
import os

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from app.extensions import db

from app.models import (
StoryCategory,
ScriptureContent,
)

============================================================

API SETTINGS

============================================================

BIBLE_API_BASE_URL = (
"https://bible.helloao.org/api"
)

DEFAULT_TRANSLATION = "ENGWEBP"

============================================================

KALXA STORIES CHRISTIAN COMMUNITY CATEGORIES

============================================================

These categories are created automatically when

Scripture synchronisation runs.

Existing category records are reused.

Existing category IDs are never replaced.

============================================================

CHRISTIAN_CATEGORIES = [

{
    "name": "Prayers",
    "slug": "prayers",
    "description": (
        "Prayer reflections, encouragement and "
        "Scripture to help us grow closer to God."
    ),
    "display_order": 1,
},

{
    "name": "Let's Talk the Word",
    "slug": "lets-talk-the-word",
    "description": (
        "Conversations, reflections and discussions "
        "about God's Word."
    ),
    "display_order": 2,
},

{
    "name": "How God Changed My Life",
    "slug": "how-god-changed-my-life",
    "description": (
        "Personal testimonies and stories about "
        "how God has changed people's lives."
    ),
    "display_order": 3,
},

{
    "name": "Community Announcements",
    "slug": "community-announcements",
    "description": (
        "Announcements, updates and information "
        "for the Christian community."
    ),
    "display_order": 4,
},

{
    "name": "Growing in Faith",
    "slug": "growing-in-faith",
    "description": (
        "Scripture, reflections and resources "
        "that encourage spiritual growth."
    ),
    "display_order": 5,
},

{
    "name": "Words of Encouragement",
    "slug": "words-of-encouragement",
    "description": (
        "Biblical encouragement and reminders "
        "of God's promises."
    ),
    "display_order": 6,
},

{
    "name": "Quotes",
    "slug": "quotes",
    "description": (
        "Meaningful Bible verses and Christian "
        "quotes for everyday encouragement."
    ),
    "display_order": 7,
},

]

============================================================

SCRIPTURE CONTENT PLAN

============================================================

These passages are automatically retrieved from

the Free Use Bible API.

Scripture is currently assigned to:

prayers

words-of-encouragement

quotes

The remaining Christian categories can contain

administrator-published articles.

============================================================

SCRIPTURE_PLAN = {

"prayers": [

    {
        "title": "A Prayer for a Clean Heart",
        "book": "PSA",
        "chapter": 51,
        "verse": 10,
        "reference": "Psalm 51:10",
    },

    {
        "title": "Seeking God's Guidance",
        "book": "PRO",
        "chapter": 3,
        "verse": 5,
        "reference": "Proverbs 3:5",
    },

    {
        "title": "Finding Strength Through Prayer",
        "book": "PSA",
        "chapter": 46,
        "verse": 1,
        "reference": "Psalm 46:1",
    },

],

"words-of-encouragement": [

    {
        "title": "Do Not Be Afraid",
        "book": "ISA",
        "chapter": 41,
        "verse": 10,
        "reference": "Isaiah 41:10",
    },

    {
        "title": "Strength for Today",
        "book": "PHP",
        "chapter": 4,
        "verse": 13,
        "reference": "Philippians 4:13",
    },

    {
        "title": "God Is Our Refuge",
        "book": "PSA",
        "chapter": 46,
        "verse": 1,
        "reference": "Psalm 46:1",
    },

    {
        "title": "Cast Your Worries on Him",
        "book": "1PE",
        "chapter": 5,
        "verse": 7,
        "reference": "1 Peter 5:7",
    },

],

"quotes": [

    {
        "title": "Love Never Fails",
        "book": "1CO",
        "chapter": 13,
        "verse": 8,
        "reference": "1 Corinthians 13:8",
    },

    {
        "title": "The Lord Is My Shepherd",
        "book": "PSA",
        "chapter": 23,
        "verse": 1,
        "reference": "Psalm 23:1",
    },

    {
        "title": "A New Beginning",
        "book": "2CO",
        "chapter": 5,
        "verse": 17,
        "reference": "2 Corinthians 5:17",
    },

],

}

============================================================

ENSURE CHRISTIAN CATEGORIES EXIST

============================================================

def ensure_christian_categories():

created_count = 0
activated_count = 0

categories = {}

for category_data in CHRISTIAN_CATEGORIES:

    category = (
        StoryCategory.query
        .filter_by(
            slug=category_data["slug"],
        )
        .first()
    )

    if category is None:

        category = StoryCategory(
            name=category_data["name"],
            slug=category_data["slug"],
            description=category_data["description"],
            display_order=category_data["display_order"],
            is_active=True,
        )

        db.session.add(category)

        created_count += 1

    else:

        if not category.is_active:

            category.is_active = True

            activated_count += 1

    categories[category_data["slug"]] = category

# Make newly created category IDs available
# before Scripture records are assigned to them.

db.session.flush()

return {
    "categories": categories,
    "created": created_count,
    "activated": activated_count,
}

============================================================

FETCH JSON

============================================================

def fetch_json(url):

request = Request(
    url,
    headers={
        "User-Agent": "Kalxa-Stories/1.0",
        "Accept": "application/json",
    },
)

try:

    with urlopen(
        request,
        timeout=20,
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )

except HTTPError as error:

    current_app.logger.error(
        "Bible API HTTP error: %s",
        error.code,
    )

    raise

except URLError:

    current_app.logger.exception(
        "Unable to connect to Bible API."
    )

    raise

except Exception:

    current_app.logger.exception(
        "Unable to process Bible API response."
    )

    raise

============================================================

GET A BIBLE CHAPTER

============================================================

def get_bible_chapter(
translation,
book,
chapter,
):

url = (
    f"{BIBLE_API_BASE_URL}/"
    f"{translation}/"
    f"{book}/"
    f"{chapter}.json"
)

return fetch_json(url)

============================================================

EXTRACT VERSE TEXT

============================================================

def extract_verse_text(
chapter_data,
verse_number,
):

if not isinstance(chapter_data, dict):

    return None

chapter = chapter_data.get(
    "chapter",
    {},
)

if not isinstance(chapter, dict):

    return None

content = chapter.get(
    "content",
    [],
)

if not isinstance(content, list):

    return None

for item in content:

    if not isinstance(item, dict):

        continue

    if item.get("type") != "verse":

        continue

    if item.get("number") != verse_number:

        continue

    text = item.get(
        "content",
        item.get("text", ""),
    )

    if isinstance(text, list):

        text = " ".join(
            str(part)
            for part in text
            if isinstance(part, str)
        )

    if isinstance(text, str):

        cleaned_text = text.strip()

        if cleaned_text:

            return cleaned_text

return None

============================================================

SYNCHRONISE SCRIPTURE

============================================================

def sync_scripture_content():

translation = (
    current_app.config.get(
        "BIBLE_API_TRANSLATION"
    )
    or os.environ.get(
        "BIBLE_API_TRANSLATION"
    )
    or DEFAULT_TRANSLATION
)

translation = str(
    translation
).strip()

if not translation:

    raise ValueError(
        "Bible API translation is not configured."
    )

# ========================================================
# CREATE / ACTIVATE CHRISTIAN CATEGORIES
# ========================================================

category_result = ensure_christian_categories()

categories = category_result["categories"]

categories_created = category_result["created"]

categories_activated = category_result["activated"]

# ========================================================
# CACHE CHAPTERS DURING SYNCHRONISATION
# ========================================================
#
# Multiple verses from the same chapter only require
# one external API request.
#
# ========================================================

chapter_cache = {}

created_count = 0
updated_count = 0
skipped_count = 0

# ========================================================
# PROCESS SCRIPTURE PLAN
# ========================================================

for category_slug, passages in SCRIPTURE_PLAN.items():

    category = categories.get(
        category_slug
    )

    if category is None:

        current_app.logger.warning(
            "Scripture category is missing: %s",
            category_slug,
        )

        skipped_count += len(passages)

        continue

    for position, passage in enumerate(
        passages,
        start=1,
    ):

        book = passage["book"]

        chapter_number = passage["chapter"]

        verse_number = passage["verse"]

        # =================================================
        # CHAPTER CACHE
        # =================================================

        cache_key = (
            translation,
            book,
            chapter_number,
        )

        if cache_key not in chapter_cache:

            chapter_cache[cache_key] = (
                get_bible_chapter(
                    translation=translation,
                    book=book,
                    chapter=chapter_number,
                )
            )

        chapter_data = chapter_cache[
            cache_key
        ]

        # =================================================
        # EXTRACT VERSE
        # =================================================

        verse_text = extract_verse_text(
            chapter_data,
            verse_number,
        )

        if not verse_text:

            current_app.logger.warning(
                "Bible verse not found: %s",
                passage["reference"],
            )

            skipped_count += 1

            continue

        # =================================================
        # SOURCE URL
        # =================================================

        source_url = (
            f"{BIBLE_API_BASE_URL}/"
            f"{translation}/"
            f"{book}/"
            f"{chapter_number}.json"
        )

        # =================================================
        # CHECK FOR EXISTING SCRIPTURE
        # =================================================

        existing = (
            ScriptureContent.query
            .filter_by(
                category_id=category.id,
                verse_reference=passage["reference"],
                translation=translation,
            )
            .first()
        )

        if existing:

            existing.title = passage["title"]

            existing.content = verse_text

            existing.book = book

            existing.chapter = chapter_number

            existing.verse = verse_number

            existing.source_url = source_url

            existing.source = "Free Use Bible API"

            existing.display_order = position

            existing.is_active = True

            updated_count += 1

        else:

            scripture = ScriptureContent(

                category_id=category.id,

                title=passage["title"],

                content=verse_text,

                book=book,

                chapter=chapter_number,

                verse=verse_number,

                verse_reference=passage["reference"],

                translation=translation,

                source="Free Use Bible API",

                source_url=source_url,

                display_order=position,

                is_active=True,

            )

            db.session.add(
                scripture
            )

            created_count += 1

# ========================================================
# COMMIT DATABASE CHANGES
# ========================================================

try:

    db.session.commit()

except Exception:

    db.session.rollback()

    current_app.logger.exception(
        "Unable to save Scripture content."
    )

    raise

# ========================================================
# SYNCHRONISATION SUMMARY
# ========================================================

current_app.logger.info(
    (
        "Scripture synchronisation completed. "
        "Categories created: %s. "
        "Categories activated: %s. "
        "Scripture created: %s. "
        "Scripture updated: %s. "
        "Scripture skipped: %s."
    ),
    categories_created,
    categories_activated,
    created_count,
    updated_count,
    skipped_count,
)

return {

    "categories_created": categories_created,

    "categories_activated": categories_activated,

    "created": created_count,

    "updated": updated_count,

    "skipped": skipped_count,

    "translation": translation,

}
