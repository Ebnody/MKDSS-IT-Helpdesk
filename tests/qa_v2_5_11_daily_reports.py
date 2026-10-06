from pathlib import Path
import ast, re, zipfile

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT/'app.py').read_text(encoding='utf-8')
base = (ROOT/'templates/base.html').read_text(encoding='utf-8')
new = (ROOT/'templates/daily_report_new.html').read_text(encoding='utf-8')

checks=[]
def check(name, ok):
    checks.append((name,bool(ok)))

check('Python AST parses', ast.parse(app) is not None)
check('DailyReport stores submitting account in user_id', 'user_id=u.id' in app and 'author_id=u.id' in app)
check('Daily report notification routing is role based', 'reviewer_roles = ("IT_MANAGER",)' in app and 'reviewer_roles = ("IT_TEAM_LEADER",)' in app)
check('Technician reports route to Team Leader', 'elif u.role.name == "IT_TECHNICIAN":\n                    reviewer_roles = ("IT_TEAM_LEADER",)' in app)
check('Team Leader reports route to Manager', 'if u.role.name == "IT_TEAM_LEADER":\n                    reviewer_roles = ("IT_MANAGER",)' in app)
check('System Admin reports route to Manager', 'elif u.role.name == "SYSTEM_ADMINISTRATOR":\n                    reviewer_roles = ("IT_MANAGER",)' in app)
check('Manager reports do not notify another reviewer', 'else:\n                    reviewer_roles = ()' in app)
check('Reviewer notifications are active users only', 'User.is_active.is_(True)' in app)
check('Report ownership view restriction for technician', 'if r.user_id != u.id:' in app)
check('Team Leader report scope is restricted', 'Role.name.in_' in app and 'IT_TEAM_LEADER' in app and 'IT_TECHNICIAN' in app and 'DailyReport.user_id == User.id' in app)
check('Daily report draft key includes account id', "accountId='{{ current_user.id if current_user else 0 }}'" in base and "mkdss-draft:'+accountId" in base)
check('Successful report submission clears drafts', 'draft_cleared=\"1\"' in app and "get('draft_cleared') === '1'" in base)
check('Daily report form fields use draft persistence', 'name="summary"' in new and 'name="tickets_worked_on"' in new)

# Ensure no global page reload was reintroduced.
check('No automatic location.reload', 'location.reload' not in base)

print('V2.5.11 DAILY REPORT QA')
for n,ok in checks: print(('PASS' if ok else 'FAIL')+' - '+n)
print(f'RESULT: {"PASS" if all(ok for _,ok in checks) else "FAIL"}')
