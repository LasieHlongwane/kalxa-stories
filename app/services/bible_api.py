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

SCRIPTURE CONTENT PLAN

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

chapter = chapter_data.get(
    "chapter",
    {},
)

content = chapter.get(
    "content",
    [],
)

for item in content:

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

        return text.strip()

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

translation = translation.strip()

if not translation:

    raise ValueError(
        "Bible API translation is not configured."
    )

# Cache chapters during this sync operation.
# Multiple verses from the same chapter only
# require one external API request.

chapter_cache = {}

created_count = 0
updated_count = 0
skipped_count = 0

for category_slug, passages in SCRIPTURE_PLAN.items():

    category = (
        StoryCategory.query
        .filter_by(
            slug=category_slug,
            is_active=True,
        )
        .first()
    )

    if category is None:

        current_app.logger.warning(
            "Scripture category is missing or inactive: %s",
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

        source_url = (
            f"{BIBLE_API_BASE_URL}/"
            f"{translation}/"
            f"{book}/"
            f"{chapter_number}.json"
        )

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

try:

    db.session.commit()

except Exception:

    db.session.rollback()

    current_app.logger.exception(
        "Unable to save Scripture content."
    )

    raise

return {
    "created": created_count,
    "updated": updated_count,
    "skipped": skipped_count,
    "translation": translation,
}
