# Apply R200 permanent publishing rules to installed KALXA Stories. No database operations.
from pathlib import Path
import shutil, ast
ROOT=Path(__file__).resolve().parent
PACKAGE=Path(__file__).resolve().parent/'permanent_r200_files'
files=['app/paid/service.py','app/paid/models.py','app/paid/routes.py','templates/paid/submit.html','templates/paid/admin_detail.html']
changes={}
for f in files:
    if not (ROOT/f).exists():
        raise SystemExit(f'Missing {f}. Install prior paid publishing package first.')
    changes[f]=(PACKAGE/f).read_text(encoding='utf-8')

# Existing Trending integration currently references now-removed ends_at.
p='app/public/routes.py'
s=(ROOT/p).read_text(encoding='utf-8')
s=s.replace('        PaidStoryPublication.ends_at > now,\n','')
s=s.replace('            PaidStoryPublication.ends_at > now,\n','')
changes[p]=s

# Existing article editor must not reintroduce expiry or change permanent URLs.
p='app/admin/routes.py'
s=(ROOT/p).read_text(encoding='utf-8')
if 'PERMANENT PAID STORY GUARD R200' not in s:
    anchor='    # --------------------------------------------------------\n    # ASSIGN\n    # --------------------------------------------------------'
    guard='''    # PERMANENT PAID STORY GUARD R200
    # Existing Premium restaurant editorial flow is unaffected.
    from app.paid.models import PaidStorySubmission
    if article.id is not None:
        paid_record = PaidStorySubmission.query.filter_by(article_id=article.id).first()
        if paid_record is not None:
            if expires_at is not None:
                flash("Permanent paid stories cannot have an expiration date.", "error")
                return False
            if article.status == "published" and slug != article.slug:
                flash("Published paid story URLs are permanent. Keep the original slug.", "error")
                return False
            if status == "published" and paid_record.review_status != "published":
                flash("Publish paid stories from the Paid Submissions screen.", "error")
                return False

'''
    if s.count(anchor)!=1: raise SystemExit('Admin form assignment anchor changed; refusing unsafe update.')
    s=s.replace(anchor,guard+anchor,1)
# Guard quick publish route from bypassing paid payment verification.
anchor='    article.status = (\n        "published"\n    )'
if 'QUICK PUBLISH PAID SAFETY GUARD R200' not in s:
    if s.count(anchor)!=1: raise SystemExit('Quick-publish anchor changed; refusing unsafe update.')
    guard='''    # QUICK PUBLISH PAID SAFETY GUARD R200
    from app.paid.models import PaidStorySubmission
    if PaidStorySubmission.query.filter_by(article_id=article.id).first() is not None:
        flash("Use Paid Submissions to publish this permanent paid article.", "error")
        return redirect(url_for("admin.article_edit", article_id=article.id))

'''
    s=s.replace(anchor,guard+anchor,1)
changes[p]=s

# Home marketing copy: no duration language.
p='templates/home.html'
s=(ROOT/p).read_text(encoding='utf-8')
s=s.replace('choose a publishing duration and request featured placement.','publish a permanent story for a once-off R200 payment, subject to editorial approval.')
changes[p]=s
for f,source in changes.items():
    if f.endswith('.py'): ast.parse(source,filename=f)
for f,source in changes.items():
    path=ROOT/f
    if source==path.read_text(encoding='utf-8'):
        print('UNCHANGED:',f);continue
    backup=path.with_name(path.name+'.before_permanent_r200.bak')
    if not backup.exists():shutil.copy2(path,backup)
    path.write_text(source,encoding='utf-8')
    print('UPDATED:',f)
print('No migrations or database changes were applied. Do not deploy before migration review.')
