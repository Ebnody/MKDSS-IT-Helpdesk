from pathlib import Path
import ast,re,zipfile,sys
from jinja2 import Environment, FileSystemLoader
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'app.py'; T=ROOT/'templates'; CSS=ROOT/'static/pro_ui.css'; BASE=T/'base.html'; DASH=T/'dashboard.html'; NOTIF=T/'notifications.html'
errors=[]; checks=[]
def check(name, cond, detail=''):
    checks.append((name,bool(cond)))
    if not cond: errors.append(f'{name}: {detail}')

src=APP.read_text(encoding='utf-8'); css=CSS.read_text(encoding='utf-8'); base=BASE.read_text(encoding='utf-8'); dash=DASH.read_text(encoding='utf-8'); notif=NOTIF.read_text(encoding='utf-8')
# Python parse
try: ast.parse(src); py_ok=True
except Exception as e: py_ok=False; errors.append(f'Python parse: {e}')
check('Python AST parse',py_ok)
# Jinja parse
jinja_ok=True
env=Environment(loader=FileSystemLoader(str(T)))
for p in sorted(T.glob('*.html')):
    try: env.parse(p.read_text(encoding='utf-8'))
    except Exception as e: jinja_ok=False; errors.append(f'Jinja {p.name}: {e}')
check('All Jinja templates parse',jinja_ok)
# JS syntax for inline scripts
import subprocess,tempfile
js_ok=True
for p in sorted(T.glob('*.html')):
    s=p.read_text(encoding='utf-8')
    for i,block in enumerate(re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',s,re.S|re.I)):
        if not block.strip(): continue
        f=Path(tempfile.mkstemp(suffix='.js')[1]); f.write_text(block,encoding='utf-8')
        r=subprocess.run(['node','--check',str(f)],capture_output=True,text=True)
        f.unlink(missing_ok=True)
        if r.returncode: js_ok=False; errors.append(f'JS {p.name} block {i}: {r.stderr.strip()}')
check('Inline JavaScript syntax',js_ok)
# Role dashboards
for role,phrase in [('EMPLOYEE','My Requests'),('IT_TECHNICIAN','My Work Queue'),('IT_TEAM_LEADER','IT Support Queue'),('IT_MANAGER','Management Overview'),('SYSTEM_ADMINISTRATOR','System Administration Work')]:
    check(f'Role dashboard {role}', f"dashboard_role == '{role}'" in dash)
    check(f'Role content {role}', phrase in dash)
check('Dashboard scope title is role-derived','dashboard_scope_title=dashboard_scope[0]' in src)
# Theme fixes
for needle,label in [
 ('--pro-search:#0b2038','dark search background'),('--pro-search-text:#dce8f5','dark search text'),('--pro-search:#f4f7fb','light search background'),('--pro-search-text:#172438','light search text'),
 ('html[data-theme="light"] .pro-main','light main contrast'),('html[data-theme="dark"] .data-table td','dark table contrast'),('html[data-theme="dark"] .pro-search input','dark search contrast')]: check(label,needle in css)
# Date range
check('Dashboard has From date input','name="from"' in dash and 'type="date"' in dash)
check('Dashboard has To date input','name="to"' in dash and 'type="date"' in dash)
check('Dashboard parses From date','from_text = request.args.get("from", "").strip()' in src)
check('Dashboard parses To date','to_text = request.args.get("to", "").strip()' in src)
check('Dashboard filters selected period','q = q.filter(Ticket.created_at >= period_start, Ticket.created_at < period_end)' in src)
check('Dashboard chart honors selected period','chart_days = min((period_to - period_from).days + 1, 31)' in src)
check('Date picker dark icon styling','::-webkit-calendar-picker-indicator' in css and 'color-scheme:dark' in css)
# Notification behavior
check('Mark-read route exists','@app.post("/notifications/<int:notification_id>/read")' in src)
check('Mark-read remains user-authorized','if not n or n.user_id != u.id:' in src)
read_block=src[src.index('def notification_read'):src.index('@app.post("/notifications/read-all")')]
check('Mark-read does not redirect to ticket','redirect(url_for("ticket", ticket_id=t.id))' not in read_block)
check('Mark-read redirects to notifications','return redirect(url_for("notifications"))' in read_block)
check('Open remains separate','def notification_open(notification_id):' in src)
check('Open still redirects to ticket when authorized','return redirect(url_for("ticket", ticket_id=t.id))' in src[src.index('def notification_open'):src.index('@app.post("/tickets/<int:ticket_id>/submit-completion")')])
check('Mark-as-read button is distinct','class="action-btn mark-read"' in notif)
check('Mark-as-read button posts read route','url_for(\'notification_read\', notification_id=n.id)' in notif)
check('Open button remains separate','url_for(\'notification_open\', notification_id=n.id)' in notif)
check('Mark-read button label clear','Mark as read' in notif)
# CSS balance
check('CSS brace balance',css.count('{')==css.count('}'))
# no stale version refs in shell/templates
check('Base assets use v2.5.14',"v='2.5.14'" in base)
check('Sidebar version v2.5.14','v2.5.14' in base)
# Package hygiene
check('No production SQLite DB',not any(p.suffix.lower() in {'.db','.sqlite','.sqlite3'} for p in ROOT.rglob('*') if p.is_file()))
check('No pycache',not any('__pycache__' in p.parts or p.suffix=='.pyc' for p in ROOT.rglob('*')))
print(f'QA checks: {len(checks)}')
for n,p in checks: print(('PASS ' if p else 'FAIL ')+n)
if errors:
    print('\nFAILURES:'); print('\n'.join(errors)); sys.exit(1)
print('RESULT: PASS')
