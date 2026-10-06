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
check('Technician is authorized for daily report list', '"IT_TECHNICIAN"' in app and 'def daily_reports()' in app)
check('Technician list is restricted to authenticated user_id', 'if u.role.name in ("IT_TECHNICIAN", "SYSTEM_ADMINISTRATOR")' in app and 'DailyReport.query.filter_by(\n                user_id=u.id\n            )' in app)
check('Technician detail is authorized', 'def daily_report(report_id)' in app and '"IT_TECHNICIAN"' in app)
check('Technician detail is own-only', 'if u.role.name == "IT_TECHNICIAN":' in app and 'if r.user_id != u.id:\n                abort(403)' in app)
check('Technician CSV export is authorized and own-only', 'def daily_report_csv(report_id)' in app and 'if u.role.name == "IT_TECHNICIAN":' in app and 'filename=daily_report_' in app)
check('Technician PDF export is authorized and own-only', 'def daily_report_pdf(report_id)' in app and 'if u.role.name == "IT_TECHNICIAN":' in app and 'daily_report_{r.id}.pdf' in app)
check('Technician has Daily Reports navigation', "current_user.role.name in ('IT_MANAGER','IT_TEAM_LEADER','IT_TECHNICIAN','SYSTEM_ADMINISTRATOR')" in base and "url_for('daily_reports')" in base)
check('Technician new-report page links to own reports', "current_user.role.name in ('IT_TEAM_LEADER','IT_TECHNICIAN','SYSTEM_ADMINISTRATOR')" in new)
check('Technician listing has own-report wording', "current_user.role.name in ('IT_TECHNICIAN','SYSTEM_ADMINISTRATOR')" in listing and 'View, open, and export your own submitted daily work reports.' in listing)
check('Technician listing exposes View/PDF/CSV actions', "url_for('daily_report',report_id=r.id)" in listing and "url_for('daily_report_pdf',report_id=r.id)" in listing and "url_for('daily_report_csv',report_id=r.id)" in listing)
check('Technician detail exposes PDF/CSV actions', "url_for('daily_report_csv',report_id=report.id)" in detail and "url_for('daily_report_pdf',report_id=report.id)" in detail)
check('DailyReport ownership on submit remains authenticated user', 'user_id=u.id' in app and 'author_id=u.id' in app)
check('Technician reports route to Team Leader', 'elif u.role.name == "IT_TECHNICIAN":\n                    reviewer_roles = ("IT_TEAM_LEADER",)' in app)

print('V2.5.13 TECHNICIAN DAILY REPORT VIEW/PDF/CSV QA')
for n,ok in checks: print(('PASS' if ok else 'FAIL')+' - '+n)
print(f'RESULT: {"PASS" if all(ok for _,ok in checks) else "FAIL"}')
raise SystemExit(0 if all(ok for _,ok in checks) else 1)
