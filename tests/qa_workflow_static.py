from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app.py'
DASH = ROOT / 'templates' / 'dashboard.html'
TICKET = ROOT / 'templates' / 'ticket.html'
BASE = ROOT / 'templates' / 'base.html'
src = APP.read_text(encoding='utf-8')

assert 'def notify_new_request_workflow(ticket):' in src
assert 'Role.name.in_(["IT_TEAM_LEADER", "IT_MANAGER"])' in src
assert '["SYSTEM_ADMINISTRATOR", "IT_MANAGER"]' in src
assert 'notification_count = notify_new_request_workflow(t)' in src
assert 'queue_notifications={notification_count}' in src
assert '@app.post("/tickets/<int:ticket_id>/submit-completion")' in src
assert 't.status = "RESOLVED"' in src
assert 'COMPLETION_SUBMITTED' in src
assert '@app.post("/tickets/<int:ticket_id>/approve-completion")' in src
assert '@app.post("/tickets/<int:ticket_id>/confirm-completion")' in src
assert 't.status = "CLOSED"' in src
assert '"ASSIGNED": {"IN_PROGRESS", "PENDING"}' in src
assert '"IN_PROGRESS": {"PENDING"}' in src
assert '"PENDING": {"IN_PROGRESS"}' in src
assert 'and t.status in ("ASSIGNED", "IN_PROGRESS", "PENDING")' in src
for role in ['EMPLOYEE','IT_TECHNICIAN','IT_TEAM_LEADER','IT_MANAGER','SYSTEM_ADMINISTRATOR']:
    assert f"dashboard_role == '{role}'" in DASH.read_text(encoding='utf-8') or role in DASH.read_text(encoding='utf-8')
assert 'dashboard_scope_title=dashboard_scope[0]' in src
assert 'id="notificationButton"' in BASE.read_text(encoding='utf-8')
assert 'setInterval' in BASE.read_text(encoding='utf-8')
assert 'submit_completion' in TICKET.read_text(encoding='utf-8')
print('STATIC WORKFLOW QA: PASS')
