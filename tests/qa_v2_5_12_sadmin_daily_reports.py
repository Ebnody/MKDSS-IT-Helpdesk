from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT/'app.py').read_text(encoding='utf-8')
base = (ROOT/'templates/base.html').read_text(encoding='utf-8')
new = (ROOT/'templates/daily_report_new.html').read_text(encoding='utf-8')
detail = (ROOT/'templates/daily_report.html').read_text(encoding='utf-8')
listing = (ROOT/'templates/daily_reports.html').read_text(encoding='utf-8')

checks=[]
def check(name, ok): checks.append((name, bool(ok)))
check('Python AST parses', ast.parse(app) is not None)
check('SAdmin can open daily report list route', '@roles(\n        "IT_MANAGER",\n        "IT_TEAM_LEADER",\n        "IT_TECHNICIAN",\n        "SYSTEM_ADMINISTRATOR"\n    )\n    def daily_reports()' in app)
check('SAdmin list is restricted to own user_id', 'if u.role.name in ("IT_TECHNICIAN", "SYSTEM_ADMINISTRATOR")' in app and 'DailyReport.query.filter_by(\n                user_id=u.id\n            )' in app)
check('SAdmin detail route is allowed', '@roles(\n        "IT_MANAGER",\n        "IT_TEAM_LEADER",\n        "IT_TECHNICIAN",\n        "SYSTEM_ADMINISTRATOR"\n    )\n    def daily_report(report_id)' in app)
check('SAdmin detail is restricted to own report', 'elif u.role.name == "SYSTEM_ADMINISTRATOR":' in app and 'if r.user_id != u.id:\n                abort(403)' in app)
check('SAdmin CSV export remains own-only', 'elif u.role.name == "SYSTEM_ADMINISTRATOR":' in app and 'SAdmin can export only their own report.' in app)
check('SAdmin PDF export remains own-only', 'SAdmin can export only their own report.' in app)
check('SAdmin has Daily Reports navigation', "current_user.role.name in ('IT_MANAGER','IT_TEAM_LEADER','IT_TECHNICIAN','SYSTEM_ADMINISTRATOR')" in base and "url_for('daily_reports')" in base)
check('SAdmin new-report page links to own reports', "current_user.role.name in ('IT_TEAM_LEADER','IT_TECHNICIAN','SYSTEM_ADMINISTRATOR')" in new)
check('SAdmin report detail has return link', 'Back to My Reports' in detail)
check('SAdmin listing has own-report wording', 'My Daily Work Reports' in listing and 'View, open, and export your own submitted daily work reports.' in listing)
check('DailyReport ownership on submit remains authenticated user', 'user_id=u.id' in app and 'author_id=u.id' in app)
check('Role-based reviewer routing remains intact', 'reviewer_roles = ("IT_MANAGER",)' in app and 'reviewer_roles = ("IT_TEAM_LEADER",)' in app)
check('No automatic page reload', 'location.reload' not in base)

print('SADMIN DAILY REPORT REGRESSION QA')
for n,ok in checks: print(('PASS' if ok else 'FAIL')+' - '+n)
print(f'RESULT: {"PASS" if all(ok for _,ok in checks) else "FAIL"}')
raise SystemExit(0 if all(ok for _,ok in checks) else 1)
