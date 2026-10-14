"""Add email campaign blueprint, model discovery, and admin navigation.
No database operations. Run from project root after merging the package.
"""
import ast
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
updates = {}
f = root / 'app/__init__.py'
s = f.read_text(encoding='utf-8')
if 'story_notifications.notification_bp' not in s:
    anchor = '    return app'
    if s.count(anchor) != 1:
        raise RuntimeError('Missing unique return app in app/__init__.py')
    s = s.replace(anchor, '''    # Independent, location-based admin story email notifications
    from app.notifications.models import StoryNotificationCampaign, StoryNotificationDelivery
    from app.notifications.routes import notification_bp
    app.register_blueprint(notification_bp)

''' + anchor, 1)
updates[f] = s
f = root / 'templates/admin/base.html'
s = f.read_text(encoding='utf-8')
if "story_notifications.listing" not in s:
    anchor = '        </nav>'
    if s.count(anchor) != 1:
        raise RuntimeError('Missing unique admin nav closing tag')
    s = s.replace(anchor, '''            <a href="{{ url_for('story_notifications.listing') }}">Story Notifications</a>

''' + anchor, 1)
updates[f] = s
for path, new in updates.items():
    if path.suffix == '.py':
        ast.parse(new, filename=str(path))
for path, new in updates.items():
    if path.read_text(encoding='utf-8') == new:
        print('UNCHANGED:', path)
        continue
    backup = path.with_suffix(path.suffix + '.notifications.bak')
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(new, encoding='utf-8')
    print('UPDATED:', path)
print('No migrations generated/applied. Do not deploy until migrations are reviewed and applied.')
