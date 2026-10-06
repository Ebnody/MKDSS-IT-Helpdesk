import os
import tempfile
import unittest
from datetime import timedelta

# The application reads DATABASE_URL while creating the module-level Flask app.
DB_FD, DB_PATH = tempfile.mkstemp(suffix=".sqlite3")
os.close(DB_FD)
os.environ["DATABASE_URL"] = "sqlite:///" + DB_PATH
os.environ["SECRET_KEY"] = "test-only-secret"
os.environ["TESTING"] = "1"

import app as helpdesk


class HelpdeskCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = helpdesk.app
        cls.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(DB_PATH)
        except OSError:
            pass

    def test_overdue_rules(self):
        with self.app.app_context():
            role = helpdesk.Role.query.filter_by(name="EMPLOYEE").first()
            user = helpdesk.User(
                username="test_employee",
                email="test_employee@local.invalid",
                employee_id="TEST-001",
                full_name="Test Employee",
                password_hash="unused",
                role=role,
            )
            helpdesk.db.session.add(user)
            helpdesk.db.session.flush()

            old = helpdesk.now() - timedelta(hours=2)
            t = helpdesk.Ticket(
                ticket_no="TEST-OVERDUE-1",
                subject="Overdue",
                description="test",
                request_type="IT_SUPPORT",
                requester_id=user.id,
                priority="MEDIUM",
                status="NEW",
                created_at=old,
                updated_at=old,
            )
            helpdesk.db.session.add(t)
            helpdesk.db.session.flush()
            self.assertTrue(helpdesk.is_ticket_overdue(t))

            t.status = "CLOSED"
            self.assertFalse(helpdesk.is_ticket_overdue(t))

    def test_authorization_helpers(self):
        with self.app.app_context():
            emp_role = helpdesk.Role.query.filter_by(name="EMPLOYEE").first()
            tech_role = helpdesk.Role.query.filter_by(name="IT_TECHNICIAN").first()
            emp = helpdesk.User(
                username="emp2", email="emp2@local.invalid", employee_id="TEST-002",
                full_name="Employee Two", password_hash="unused", role=emp_role
            )
            tech = helpdesk.User(
                username="tech2", email="tech2@local.invalid", employee_id="TEST-003",
                full_name="Technician Two", password_hash="unused", role=tech_role
            )
            helpdesk.db.session.add_all([emp, tech])
            helpdesk.db.session.flush()
            t = helpdesk.Ticket(
                ticket_no="TEST-AUTH-1", subject="Auth", description="test",
                request_type="IT_SUPPORT", requester_id=emp.id,
                priority="HIGH", status="ASSIGNED", assigned_to_id=tech.id
            )
            helpdesk.db.session.add(t)
            helpdesk.db.session.commit()
            self.assertTrue(helpdesk.can_view_ticket(emp, t))
            self.assertTrue(helpdesk.can_update_ticket(tech, t))
            self.assertFalse(helpdesk.can_update_ticket(emp, t))


if __name__ == "__main__":
    unittest.main()
