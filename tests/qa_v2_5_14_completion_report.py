from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "app.py").read_text(encoding="utf-8")
tpl = (ROOT / "templates/completion_report.html").read_text(encoding="utf-8")
css = (ROOT / "static/app.css").read_text(encoding="utf-8")
checks = []
def check(name, ok):
    checks.append((name, bool(ok)))
    print(("PASS" if ok else "FAIL") + " - " + name)

try:
    ast.parse(app)
    check("Python AST parses", True)
except Exception:
    check("Python AST parses", False)

check("Completion metadata uses separate label/value elements", all(x in tpl for x in ["completion-meta-label", "completion-meta-value"]))
check("Status has separate value element", 'Status</span><div class="completion-meta-value">' in tpl)
check("Priority has separate value element", 'Priority</span><div class="completion-meta-value">' in tpl)
check("Requester has separate value element", 'Requester</span><div class="completion-meta-value">' in tpl)
check("Assignee has separate value element", 'Assignee</span><div class="completion-meta-value">' in tpl)
check("Completion value CSS enforces block layout", ".completion-meta-item strong,.completion-meta-value{display:block!important" in css)
check("Completion values have spacing gap", ".completion-meta-item{display:flex;flex-direction:column;align-items:flex-start;gap:7px" in css)
check("Completion values wrap long text", "word-break:break-word" in css and "overflow-wrap:anywhere" in css)
check("Completion report route remains present", "completion_report" in app)
print("RESULT: " + ("PASS" if all(ok for _, ok in checks) else "FAIL"))
