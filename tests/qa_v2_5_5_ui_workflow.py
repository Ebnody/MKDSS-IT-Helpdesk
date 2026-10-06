from pathlib import Path
import ast, re, sys
from jinja2 import Environment, FileSystemLoader, meta

ROOT=Path(__file__).resolve().parents[1]
T=ROOT/'templates'; C=ROOT/'static/pro_ui.css'; A=ROOT/'app.py'
errors=[]; checks=[]
def ok(name, condition, detail=''):
    checks.append((name, bool(condition)))
    if not condition: errors.append(f'{name}: {detail}')

env=Environment(loader=FileSystemLoader(str(T)))
for p in sorted(T.glob('*.html')):
    try: env.parse(p.read_text(encoding='utf-8'))
    except Exception as e: errors.append(f'Jinja parse {p.name}: {e}')
checks.append(('Jinja templates parse', not any(x.startswith('Jinja parse') for x in errors)))

base=(T/'base.html').read_text(encoding='utf-8')
css=C.read_text(encoding='utf-8')
app=A.read_text(encoding='utf-8')

templates=[p for p in T.glob('*.html') if p.name not in {'base.html','_ticket_table.html'}]
for p in templates:
    s=p.read_text(encoding='utf-8')
    ok(f'{p.name} extends base', '{% extends "base.html" %}' in s or p.name in {'login.html','setup.html'}, 'page must inherit system shell')

for cls in ['.panel','.page-head','.head','.form','.tablewrap','.notification-item','.filters','.pro-sidebar','.pro-topbar','.pro-theme-toggle']:
    ok(f'UI selector {cls}', cls in css)

# Role dashboard requirements
for role, phrase in {
 'EMPLOYEE':'MY OPEN REQUESTS','IT_TECHNICIAN':'ASSIGNED TO ME','IT_TEAM_LEADER':'NEW UNASSIGNED',
 'IT_MANAGER':'AWAITING APPROVAL','SYSTEM_ADMINISTRATOR':'MY SYSTEM REQUESTS'}.items():
    ok(f'Dashboard branch {role}', f"dashboard_role == '{role}'" in (T/'dashboard.html').read_text(encoding='utf-8') or f' dashboard_role == "{role}"' in (T/'dashboard.html').read_text(encoding='utf-8') in (T/'dashboard.html').read_text(encoding='utf-8'))
    ok(f'Dashboard metric {role}', phrase in (T/'dashboard.html').read_text(encoding='utf-8'))

# Workflow source checks
for needle, label in [
 ('def notify_new_request_workflow(ticket):','new-request notification helper'),
 ('/tickets/<int:ticket_id>/submit-completion','completion submission route'),
 ('completion_note','completion note required'),
 ('COMPLETION_SUBMITTED','completion activity audit'),
 ('confirm_completion','requester acceptance endpoint'),
 ('approve_completion','approval endpoint'),
 ('reject_completion','return-for-more-work endpoint'),
]: ok(label, needle in app)

# Explicit routing checks
ok('IT Support notification targets Team Leaders', 'IT_TEAM_LEADER' in app and 'IT_MANAGER' in app and 'notify_new_request_workflow' in app)
ok('System Admin notification targets SAdmin', 'SYSTEM_ADMINISTRATOR' in app and 'SYSTEM_ADMIN_SUPPORT' in app and 'notify_new_request_workflow' in app)
ok('Direct CLOSED transition blocked', '"CLOSED": set()' in app and 'confirm_completion' in app)

# Version/shell consistency
ok('Base asset version is 2.5.14', "v='2.5.14'" in base)
ok('Sidebar version is 2.5.14', 'v2.5.14' in base)
ok('System-wide CSS version marker', 'v2.5.14' in css)

print(f'QA checks: {len(checks)}')
for n,passed in checks:
    print(('PASS ' if passed else 'FAIL ')+n)
if errors:
    print('\nFAILURES:')
    print('\n'.join(errors))
    sys.exit(1)
print('RESULT: PASS')
