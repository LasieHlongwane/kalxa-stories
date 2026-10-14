"""Run ONLY after the category database migration has been applied.

Usage (from the repository root): python seed_story_categories.py
"""
from app import create_app
from app.extensions import db
from app.models.story_category import StoryCategory

CATEGORIES = (
    ("local", "What's happening locally?", "Local businesses, community stories and opportunities.", 1),
    ("experiences", "What experiences can people attend?", "Events, entertainment and real-world experiences.", 2),
    ("food", "Where can people eat, socialise and explore?", "Restaurants, food culture and local places.", 3),
    ("creators", "Who is creating, entertaining and influencing locally?", "Artists, creators and local voices.", 4),
)

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        for slug, name, description, order in CATEGORIES:
            category = StoryCategory.query.filter_by(slug=slug).first()
            if category is None:
                category = StoryCategory(slug=slug)
                db.session.add(category)
            category.name = name
            category.description = description
            category.display_order = order
            category.is_active = True
        db.session.commit()
        print("Four KALXA Stories categories are ready.")
