import os
import io
import csv
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from functools import wraps

from flask import (
    Flask, abort, flash, redirect, render_template, request,
    session, url_for, send_file, make_response, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE = os.path.abspath(os.path.dirname(__file__))
try:
    # Windows does not ship the IANA timezone database. Prefer the real
    # Africa/Addis_Ababa zone when tzdata is installed. Ethiopia remains
    # permanently UTC+03:00, so the fixed-offset fallback is equivalent
    # for this application if the timezone database is unavailable.
    LOCAL_TZ = ZoneInfo("Africa/Addis_Ababa")
except ZoneInfoNotFoundError:
    LOCAL_TZ = timezone(timedelta(hours=3), name="Africa/Addis_Ababa")

db = SQLAlchemy()


ROLES = {
    "SYSTEM_ADMINISTRATOR": (
        "System Administrator",
        "System configuration and account administration."
    ),
    "IT_MANAGER": (
        "IT Manager",
        "Department-wide monitoring, activity oversight and reporting."
    ),
    "IT_TEAM_LEADER": (
        "IT Team Leader",
        "Queue management, first-come-first-served assignment and supervision."
    ),
    "IT_TECHNICIAN": (
        "IT Technician",
        "Assigned support work, activity updates and resolution."
    ),
    "EMPLOYEE": (
        "Employee",
        "Submit and track personal IT support requests."
    ),
}


STATUSES = [
    "NEW",
    "ASSIGNED",
    "IN_PROGRESS",
    "PENDING",
    "RESOLVED",
    "CLOSED",
]

PRIORITIES = [
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
]

REQUEST_TYPES = [
    "IT_SUPPORT",
    "SYSTEM_ADMIN_SUPPORT",
]

REQUEST_TYPE_LABELS = {
    "IT_SUPPORT": "IT Support",
    "SYSTEM_ADMIN_SUPPORT": "System Administration Support",
}


ASSIGNABLE_ROLES_BY_ROLE = {
    "IT_TEAM_LEADER": {
        "IT_TECHNICIAN",
        "IT_TEAM_LEADER",
    },
    "IT_MANAGER": {
        "IT_TECHNICIAN",
        "IT_TEAM_LEADER",
        "SYSTEM_ADMINISTRATOR",
    },
    "SYSTEM_ADMINISTRATOR": {
        "SYSTEM_ADMINISTRATOR",
    },
}


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255))

    users = db.relationship("User", back_populates="role")


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    users = db.relationship("User", back_populates="department")
    tickets = db.relationship("Ticket", back_populates="department")


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    request_type = db.Column(db.String(30), nullable=False, default="IT_SUPPORT", index=True)

    tickets = db.relationship("Ticket", back_populates="category")


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
        index=True
    )
    email = db.Column(
        db.String(160),
        unique=True,
        nullable=False,
        index=True
    )
    employee_id = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
        index=True
    )
    full_name = db.Column(db.String(160), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    role_id = db.Column(
        db.Integer,
        db.ForeignKey("roles.id"),
        nullable=False,
        index=True
    )

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id"),
        index=True
    )

    is_active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    must_change_password = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )

    failed_login_count = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )

    last_login_at = db.Column(
        db.DateTime(timezone=True)
    )

    role = db.relationship(
        "Role",
        back_populates="users"
    )

    department = db.relationship(
        "Department",
        back_populates="users"
    )

    created_tickets = db.relationship(
        "Ticket",
        foreign_keys="Ticket.requester_id",
        back_populates="requester"
    )

    assigned_tickets = db.relationship(
        "Ticket",
        foreign_keys="Ticket.assigned_to_id",
        back_populates="technician"
    )

    activities = db.relationship(
        "TicketActivity",
        foreign_keys="TicketActivity.user_id",
        back_populates="user"
    )

    uploaded_attachments = db.relationship(
        "Attachment",
        foreign_keys="Attachment.uploaded_by_id",
        back_populates="uploaded_by"
    )

    audit_logs = db.relationship(
        "AuditLog",
        foreign_keys="AuditLog.user_id",
        back_populates="user"
    )

    daily_reports = db.relationship(
        "DailyReport",
        foreign_keys="DailyReport.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    ticket_no = db.Column(
        db.String(30),
        unique=True,
        index=True
    )

    subject = db.Column(
        db.String(200),
        nullable=False
    )

    description = db.Column(
        db.Text,
        nullable=False
    )

    request_type = db.Column(
        db.String(30),
        default="IT_SUPPORT",
        nullable=False,
        index=True
    )

    requester_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id"),
        index=True
    )

    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id"),
        index=True
    )

    priority = db.Column(
        db.String(20),
        default="MEDIUM",
        nullable=False,
        index=True
    )

    status = db.Column(
        db.String(20),
        default="NEW",
        nullable=False,
        index=True
    )

    assigned_to_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        index=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(LOCAL_TZ),
        nullable=False,
        index=True
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(LOCAL_TZ),
        onupdate=lambda: datetime.now(LOCAL_TZ),
        nullable=False
    )

    resolved_at = db.Column(
        db.DateTime(timezone=True)
    )

    closed_at = db.Column(
        db.DateTime(timezone=True)
    )

    completion_approved_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), index=True
    )

    completion_approved_at = db.Column(
        db.DateTime(timezone=True)
    )

    completion_approval_note = db.Column(
        db.Text
    )

    requester_confirmed_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), index=True
    )

    requester_confirmed_at = db.Column(
        db.DateTime(timezone=True)
    )

    requester_confirmation_note = db.Column(
        db.Text
    )

    requester = db.relationship(
        "User",
        foreign_keys=[requester_id],
        back_populates="created_tickets"
    )

    technician = db.relationship(
        "User",
        foreign_keys=[assigned_to_id],
        back_populates="assigned_tickets"
    )

    completion_approved_by = db.relationship(
        "User", foreign_keys=[completion_approved_by_id]
    )

    requester_confirmed_by = db.relationship(
        "User", foreign_keys=[requester_confirmed_by_id]
    )

    department = db.relationship(
        "Department",
        back_populates="tickets"
    )

    category = db.relationship(
        "Category",
        back_populates="tickets"
    )

    activities = db.relationship(
        "TicketActivity",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketActivity.created_at"
    )

    attachments = db.relationship(
        "Attachment",
        back_populates="ticket",
        cascade="all, delete-orphan"
    )


class TicketActivity(db.Model):
    __tablename__ = "ticket_activities"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    ticket_id = db.Column(
        db.Integer,
        db.ForeignKey("tickets.id"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    activity_type = db.Column(
        db.String(40),
        nullable=False
    )

    note = db.Column(
        db.Text,
        nullable=False
    )

    old_status = db.Column(
        db.String(20)
    )

    new_status = db.Column(
        db.String(20)
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(LOCAL_TZ),
        nullable=False,
        index=True
    )

    ticket = db.relationship(
        "Ticket",
        back_populates="activities"
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="activities"
    )


class Attachment(db.Model):
    __tablename__ = "attachments"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    ticket_id = db.Column(
        db.Integer,
        db.ForeignKey("tickets.id"),
        nullable=False,
        index=True
    )

    original_name = db.Column(
        db.String(255),
        nullable=False
    )

    stored_name = db.Column(
        db.String(255),
        nullable=False,
        unique=True
    )

    content_type = db.Column(
        db.String(120)
    )

    uploaded_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(LOCAL_TZ),
        nullable=False
    )

    ticket = db.relationship(
        "Ticket",
        back_populates="attachments"
    )

    uploaded_by = db.relationship(
        "User",
        foreign_keys=[uploaded_by_id],
        back_populates="uploaded_attachments"
    )


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=True, index=True)
    title = db.Column(db.String(180), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    kind = db.Column(db.String(50), nullable=False, default="INFO", index=True)
    url = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    dedupe_key = db.Column(db.String(255), unique=True, nullable=True, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(LOCAL_TZ),
        nullable=False,
        index=True
    )

    user = db.relationship("User", backref=db.backref("notifications", lazy=True))
    ticket = db.relationship("Ticket", backref=db.backref("notifications", lazy=True))

class DailyReport(db.Model):
    __tablename__ = "daily_reports"

    id = db.Column(db.Integer, primary_key=True)
    report_date = db.Column(db.Date, nullable=False, index=True)
    author_id = db.Column(db.Integer, nullable=False, default=0, index=True)
    activity = db.Column(db.Text, nullable=False, default="")
    achievements = db.Column(db.Text)
    issues = db.Column(db.Text)
    next_actions = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    tickets_worked_on = db.Column(db.Text)
    summary = db.Column(db.Text, nullable=False, default="")
    challenges = db.Column(db.Text)
    actions = db.Column(db.Text)
    pending_work = db.Column(db.Text)
    next_day_plan = db.Column(db.Text)
    remarks = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(LOCAL_TZ),
        nullable=False,
        index=True
    )

    user = db.relationship("User", foreign_keys=[user_id], back_populates="daily_reports")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        index=True
    )

    action = db.Column(
        db.String(80),
        nullable=False,
        index=True
    )

    entity_type = db.Column(
        db.String(80),
        nullable=False
    )

    entity_id = db.Column(
        db.String(80)
    )

    details = db.Column(
        db.Text
    )

    ip_address = db.Column(
        db.String(64)
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(LOCAL_TZ),
        nullable=False,
        index=True
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="audit_logs"
    )


def now():
    return datetime.now(LOCAL_TZ)


def current_user():
    if not session.get("user_id"):
        return None
    return db.session.get(User, session.get("user_id"))


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def require_csrf():
    if request.method == "POST":
        if request.form.get("_csrf") != session.get("csrf"):
            abort(400)


def log(action, entity_type, entity_id=None, details=""):
    u = current_user()

    db.session.add(
        AuditLog(
            user_id=u.id if u else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            details=details,
            ip_address=request.remote_addr
        )
    )

    db.session.commit()


def login_required(fn):
    @wraps(fn)
    def w(*a, **k):
        u = current_user()

        if not u:
            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )

        if (
            u.must_change_password
            and request.endpoint not in (
                "change_password",
                "logout",
                "static"
            )
        ):
            return redirect(url_for("change_password"))

        return fn(*a, **k)

    return w


def roles(*names):
    def dec(fn):
        @wraps(fn)
        def w(*a, **k):
            u = current_user()

            if not u:
                return redirect(url_for("login"))

            if not u.role or u.role.name not in names:
                abort(403)

            return fn(*a, **k)

        return w

    return dec


def ensure_schema_compatibility():
    """Apply only additive, data-preserving SQLite migrations."""
    if db.engine.url.get_backend_name() != "sqlite":
        return

    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    def add_column(table, column, definition):
        if table not in tables:
            return
        cols = {c["name"] for c in inspect(db.engine).get_columns(table)}
        if column not in cols:
            with db.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))

    add_column("tickets", "request_type", "VARCHAR(30) NOT NULL DEFAULT 'IT_SUPPORT'")
    add_column("categories", "request_type", "VARCHAR(30) NOT NULL DEFAULT 'IT_SUPPORT'")
    add_column("daily_reports", "tickets_worked_on", "TEXT")
    add_column("daily_reports", "pending_work", "TEXT")
    add_column("daily_reports", "remarks", "TEXT")
    add_column("tickets", "completion_approved_by_id", "INTEGER")
    add_column("tickets", "completion_approved_at", "DATETIME")
    add_column("tickets", "completion_approval_note", "TEXT")
    add_column("tickets", "requester_confirmed_by_id", "INTEGER")
    add_column("tickets", "requester_confirmed_at", "DATETIME")
    add_column("tickets", "requester_confirmation_note", "TEXT")

    if "tickets" in tables:
        with db.engine.begin() as conn:
            conn.execute(text("UPDATE tickets SET priority='CRITICAL' WHERE priority='URGENT'"))

    # The model for Notification is created by db.create_all() on first startup.


def user_by_role(role_name):
    return (
        User.query
        .join(Role)
        .filter(
            Role.name == role_name,
            User.is_active.is_(True)
        )
        .order_by(User.id)
        .first()
    )


def accessible_ticket_query(u):
    """Return a SQLAlchemy query containing only tickets visible to the user."""
    if u.role.name == "EMPLOYEE":
        return Ticket.query.filter(Ticket.requester_id == u.id)
    if u.role.name == "IT_TECHNICIAN":
        return Ticket.query.filter(Ticket.assigned_to_id == u.id)
    if u.role.name == "IT_MANAGER":
        return Ticket.query
    if u.role.name == "SYSTEM_ADMINISTRATOR":
        return Ticket.query.filter(
            Ticket.request_type == "SYSTEM_ADMIN_SUPPORT",
            Ticket.assigned_to_id == u.id
        )
    if u.role.name == "IT_TEAM_LEADER":
        return Ticket.query.filter(Ticket.request_type == "IT_SUPPORT")
    return Ticket.query.filter(Ticket.requester_id == u.id)


def assignment_targets(u, ticket=None):
    if not u:
        return []
    if u.role.name == "IT_TEAM_LEADER":
        roles_allowed = {"IT_TEAM_LEADER", "IT_TECHNICIAN"} if not ticket or ticket.request_type == "IT_SUPPORT" else set()
    elif u.role.name == "IT_MANAGER":
        if ticket and ticket.requester_id != u.id:
            return []
        roles_allowed = {"IT_TEAM_LEADER", "IT_TECHNICIAN"} if ticket and ticket.request_type == "IT_SUPPORT" else {"SYSTEM_ADMINISTRATOR"}
    else:
        roles_allowed = set()
    if not roles_allowed:
        return []
    return (User.query.join(Role)
            .filter(Role.name.in_(roles_allowed), User.is_active.is_(True))
            .order_by(User.full_name).all())


def can_view_ticket(u, t):
    if not u or not t:
        return False
    return accessible_ticket_query(u).filter(Ticket.id == t.id).first() is not None


def can_update_ticket(u, t):
    """Only the assigned user may update operational ticket fields."""
    return bool(u and t and t.assigned_to_id == u.id and u.role.name != "EMPLOYEE" and t.status in ("ASSIGNED", "IN_PROGRESS", "PENDING"))


def can_assign_ticket(u, t):
    if not u or not t:
        return False
    if u.role.name == "IT_TEAM_LEADER":
        return t.request_type == "IT_SUPPORT"
    if u.role.name == "IT_MANAGER":
        return t.requester_id == u.id
    return False


def can_approve_completion(u, t):
    if not u or not t or t.status != "RESOLVED":
        return False
    if u.role.name == "IT_TEAM_LEADER":
        return t.request_type == "IT_SUPPORT"
    if u.role.name == "IT_MANAGER":
        return True
    return False


def can_confirm_completion(u, t):
    return bool(
        u and t and t.requester_id == u.id
        and t.status == "RESOLVED"
        and t.completion_approved_at is not None
        and t.requester_confirmed_at is None
    )


def is_completed_request(t):
    return bool(
        t and t.status == "CLOSED"
        and t.completion_approved_at is not None
        and t.requester_confirmed_at is not None
    )


def is_ticket_overdue(ticket, reference_time=None):
    """Authoritative overdue calculation used by dashboards, lists and notifications."""
    if not ticket or ticket.status == "CLOSED" or not ticket.created_at:
        return False
    current = reference_time or now()
    created = ticket.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=LOCAL_TZ)
    else:
        created = created.astimezone(LOCAL_TZ)
    age_seconds = (current - created).total_seconds()
    if ticket.status == "NEW" and ticket.assigned_to_id is None:
        return age_seconds > 3600
    return age_seconds > 86400


def overdue_ticket_query(base_query=None):
    rows = (base_query or Ticket.query).all()
    return [t for t in rows if is_ticket_overdue(t)]


def create_notification(user, title, message, kind="INFO", ticket=None, url=None, dedupe_key=None):
    if not user or not user.is_active:
        return None
    if dedupe_key and Notification.query.filter_by(dedupe_key=dedupe_key).first():
        return None
    n = Notification(
        user_id=user.id,
        ticket_id=ticket.id if ticket else None,
        title=title[:180],
        message=message[:500],
        kind=kind,
        url=url,
        is_read=False,
        dedupe_key=dedupe_key
    )
    db.session.add(n)
    return n


def notification_recipients(ticket):
    users = []
    seen = set()
    for candidate in (
        ticket.requester,
        ticket.technician,
    ):
        if candidate and candidate.is_active and candidate.id not in seen:
            users.append(candidate); seen.add(candidate.id)
    if ticket.request_type == "IT_SUPPORT":
        for r in ("IT_TEAM_LEADER", "IT_MANAGER"):
            for u in User.query.join(Role).filter(Role.name == r, User.is_active.is_(True)).all():
                if u.id not in seen:
                    users.append(u); seen.add(u.id)
    elif ticket.request_type == "SYSTEM_ADMIN_SUPPORT":
        for u in User.query.join(Role).filter(Role.name == "SYSTEM_ADMINISTRATOR", User.is_active.is_(True)).all():
            if u.id not in seen:
                users.append(u); seen.add(u.id)
        for u in User.query.join(Role).filter(Role.name == "IT_MANAGER", User.is_active.is_(True)).all():
            if u.id not in seen:
                users.append(u); seen.add(u.id)
    return users


def notify_ticket_event(ticket, title, message, kind="TICKET", exclude_user_id=None):
    for user in notification_recipients(ticket):
        if exclude_user_id and user.id == exclude_user_id:
            continue
        create_notification(
            user, title, message, kind=kind, ticket=ticket,
            url=url_for("ticket", ticket_id=ticket.id),
            dedupe_key=None
        )


def notify_new_request_workflow(ticket):
    """Create persistent queue notifications for a newly submitted request.

    This is deliberately separate from generic ticket-event notifications so a new
    requester submission always reaches the operational queue even when the ticket
    has not been assigned yet. Returns the number of notifications created.
    """
    if not ticket or not ticket.id:
        return 0
    if ticket.request_type == "IT_SUPPORT":
        role_names = ["IT_TEAM_LEADER", "IT_MANAGER"]
    elif ticket.request_type == "SYSTEM_ADMIN_SUPPORT":
        role_names = ["SYSTEM_ADMINISTRATOR", "IT_MANAGER"]
    else:
        return 0
    recipients = (
        User.query.join(Role)
        .filter(Role.name.in_(role_names), User.is_active.is_(True))
        .all()
    )
    created = 0
    for user in recipients:
        n = create_notification(
            user,
            "New support request",
            f"{ticket.ticket_no} has been submitted and requires your attention.",
            kind="CREATED",
            ticket=ticket,
            url=url_for("ticket", ticket_id=ticket.id),
            dedupe_key=f"NEW_REQUEST:{ticket.id}:{user.id}"
        )
        if n is not None:
            created += 1
    return created


def refresh_overdue_notifications():
    """Create at most one overdue notification per ticket/user."""
    for ticket in Ticket.query.filter(Ticket.status != "CLOSED").all():
        if not is_ticket_overdue(ticket):
            continue
        for user in notification_recipients(ticket):
            create_notification(
                user,
                "Overdue support request",
                f"{ticket.ticket_no} requires attention because it is overdue.",
                kind="OVERDUE",
                ticket=ticket,
                url=url_for("ticket", ticket_id=ticket.id),
                dedupe_key=f"OVERDUE:{ticket.id}:{user.id}"
            )
    db.session.commit()


def localtime(value, fmt="%Y-%m-%d %H:%M"):
    """
    Convert stored datetimes to Africa/Addis_Ababa time.

    Supports:
        {{ value|localtime }}

    and:

        {{ value|localtime("%Y-%m-%d %H:%M:%S") }}
    """

    if value is None:
        return ""

    if not isinstance(value, datetime):
        return str(value)

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=LOCAL_TZ
        )
    else:
        value = value.astimezone(
            LOCAL_TZ
        )

    return value.strftime(fmt)


def configured_secret_key(instance_path):
    value = os.environ.get("SECRET_KEY")
    if value and value != "CHANGE_THIS_IN_PRODUCTION":
        return value
    key_file = os.path.join(instance_path, "secret_key.txt")
    try:
        if os.path.isfile(key_file):
            value = open(key_file, "r", encoding="utf-8").read().strip()
            if value:
                return value
        value = secrets.token_urlsafe(48)
        with open(key_file, "w", encoding="utf-8") as fh:
            fh.write(value)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return value
    except OSError:
        return secrets.token_urlsafe(48)


def create_app():
    app = Flask(
        __name__,
        instance_relative_config=True
    )

    os.makedirs(
        app.instance_path,
        exist_ok=True
    )

    app.config.update(
        SECRET_KEY=configured_secret_key(app.instance_path),

        SQLALCHEMY_DATABASE_URI=(
            os.environ.get("DATABASE_URL")
            or (
                "sqlite:///"
                + os.environ.get(
                    "DATABASE_PATH",
                    os.path.join(app.instance_path, "mkdss_helpdesk.sqlite3")
                )
            )
        ),

        SQLALCHEMY_TRACK_MODIFICATIONS=False,

        MAX_CONTENT_LENGTH=int(os.environ.get("MAX_UPLOAD_SIZE", str(50 * 1024 * 1024))),

        UPLOAD_FOLDER=os.path.join(
            app.instance_path,
            "attachments"
        ),

        SESSION_COOKIE_HTTPONLY=True,

        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    )

    os.makedirs(
        app.config["UPLOAD_FOLDER"],
        exist_ok=True
    )

    db.init_app(app)

    with app.app_context():

        db.create_all()

        ensure_schema_compatibility()

        if db.engine.url.get_backend_name() == "sqlite":

            with db.engine.connect() as c:

                c.execute(
                    text("PRAGMA foreign_keys=ON")
                )

                c.execute(
                    text("PRAGMA journal_mode=WAL")
                )

                c.execute(
                    text("PRAGMA busy_timeout=5000")
                )

                c.commit()

        for key, (display, desc) in ROLES.items():

            if not Role.query.filter_by(
                name=key
            ).first():

                db.session.add(
                    Role(
                        name=key,
                        display_name=display,
                        description=desc
                    )
                )

        db.session.commit()

    app.jinja_env.filters["localtime"] = localtime

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["now"] = now
    app.jinja_env.globals["is_ticket_overdue"] = is_ticket_overdue
    app.jinja_env.globals["can_approve_completion"] = can_approve_completion
    app.jinja_env.globals["can_confirm_completion"] = can_confirm_completion
    app.jinja_env.globals["is_completed_request"] = is_completed_request

    app.jinja_env.globals["STATUSES"] = STATUSES

    app.jinja_env.globals["PRIORITIES"] = PRIORITIES

    app.jinja_env.globals["REQUEST_TYPES"] = REQUEST_TYPES

    app.jinja_env.globals[
        "REQUEST_TYPE_LABELS"
    ] = REQUEST_TYPE_LABELS

    app.jinja_env.globals[
        "request_type_labels"
    ] = REQUEST_TYPE_LABELS

    register(app)

    return app


def register(app):

    @app.before_request
    def before():
        require_csrf()


    @app.context_processor
    def globals_():

        u = current_user()

        return {
            "current_user": u,
            "role_names": ROLES,
            "request_type_labels": REQUEST_TYPE_LABELS,
            "STATUSES": STATUSES,
            "PRIORITIES": PRIORITIES,
            "REQUEST_TYPES": REQUEST_TYPES,
            "assignment_targets": (
                assignment_targets(u)
                if u
                else []
            ),
            "unread_notification_count": (
                Notification.query.filter_by(user_id=u.id, is_read=False).count()
                if u else 0
            ),
            "recent_notifications": (
                Notification.query.filter_by(user_id=u.id)
                .order_by(Notification.created_at.desc())
                .limit(5).all()
                if u else []
            ),
        }


    @app.route(
        "/setup",
        methods=["GET", "POST"]
    )
    def setup():

        if User.query.count():
            abort(404)

        if request.method == "POST":

            f = request.form

            vals = [
                f.get(x, "").strip()
                for x in (
                    "full_name",
                    "username",
                    "email",
                    "employee_id"
                )
            ]

            pw = f.get("password", "")

            if (
                not all(vals)
                or len(pw) < 12
                or pw != f.get("confirmation", "")
            ):

                flash(
                    "Enter all fields and use matching passwords of at least 12 characters.",
                    "error"
                )

            elif "@" not in vals[2]:

                flash(
                    "Enter a valid work email.",
                    "error"
                )

            else:

                role = Role.query.filter_by(
                    name="SYSTEM_ADMINISTRATOR"
                ).first()

                u = User(
                    full_name=vals[0],
                    username=vals[1].lower(),
                    email=vals[2].lower(),
                    employee_id=vals[3],
                    password_hash=generate_password_hash(pw),
                    role=role,
                    is_active=True
                )

                db.session.add(u)
                db.session.commit()

                log(
                    "INITIAL_ADMIN_CREATED",
                    "User",
                    u.id
                )

                flash(
                    "System Administrator created. Sign in to continue.",
                    "success"
                )

                return redirect(
                    url_for("login")
                )

        return render_template("setup.html")


    @app.route(
        "/login",
        methods=["GET", "POST"]
    )
    def login():

        if current_user():
            return redirect(
                url_for("dashboard")
            )

        if request.method == "POST":

            username = (
                request.form
                .get("username", "")
                .strip()
                .lower()
            )

            pw = request.form.get(
                "password",
                ""
            )

            u = User.query.filter_by(
                username=username
            ).first()

            if (
                not u
                or not check_password_hash(
                    u.password_hash,
                    pw
                )
                or not u.is_active
            ):
                if u and u.is_active:
                    u.failed_login_count = (u.failed_login_count or 0) + 1
                    db.session.commit()
                flash(
                    "Invalid credentials or inactive account.",
                    "error"
                )

            else:

                session.clear()

                session["user_id"] = u.id

                session["csrf"] = (
                    secrets.token_urlsafe(32)
                )

                u.last_login_at = now()

                u.failed_login_count = 0

                db.session.commit()

                log(
                    "LOGIN",
                    "User",
                    u.id
                )

                next_url = request.args.get("next", "")
                if not next_url.startswith("/"):
                    next_url = url_for("dashboard")
                return redirect(next_url)

        return render_template("login.html")


    @app.post("/logout")
    @login_required
    def logout():

        u = current_user()

        log(
            "LOGOUT",
            "User",
            u.id
        )

        session.clear()

        return redirect(
            url_for("login")
        )


    @app.get("/")
    def root():

        if current_user():
            return redirect(
                url_for("dashboard")
            )

        if User.query.count() == 0:
            return redirect(
                url_for("setup")
            )

        return redirect(
            url_for("login")
        )


    @app.get("/dashboard")
    @login_required
    def dashboard():

        u = current_user()

        refresh_overdue_notifications()
        q = accessible_ticket_query(u)

        # Dashboard reporting window is user-selectable. Dates are interpreted in
        # Africa/Addis_Ababa and applied to ticket creation time. Invalid or reversed
        # values safely fall back to the current 7-day window.
        today_local = now().date()
        default_from = today_local - timedelta(days=6)
        from_text = request.args.get("from", "").strip()
        to_text = request.args.get("to", "").strip()
        try:
            period_from = datetime.strptime(from_text, "%Y-%m-%d").date() if from_text else default_from
        except ValueError:
            period_from = default_from
        try:
            period_to = datetime.strptime(to_text, "%Y-%m-%d").date() if to_text else today_local
        except ValueError:
            period_to = today_local
        if period_from > period_to:
            period_from, period_to = default_from, today_local

        period_start = datetime(period_from.year, period_from.month, period_from.day, tzinfo=LOCAL_TZ)
        period_end = datetime(period_to.year, period_to.month, period_to.day, tzinfo=LOCAL_TZ) + timedelta(days=1)
        q = q.filter(Ticket.created_at >= period_start, Ticket.created_at < period_end)

        visible_rows_for_overdue = q.all()
        overdue_count = sum(1 for x in visible_rows_for_overdue if is_ticket_overdue(x))

        # Dashboard analytics are derived only from the authorized ticket set.
        # Nothing here is demo/sample data.
        category_counts = {}
        for cat in Category.query.order_by(Category.name).all():
            n = q.filter(Ticket.category_id == cat.id).count()
            if n:
                category_counts[cat.name] = n

        response_durations = []
        resolution_durations = []
        for ticket_row in visible_rows_for_overdue:
            created = ticket_row.created_at
            if created:
                first_response = next(
                    (a.created_at for a in sorted(ticket_row.activities, key=lambda a: a.created_at)
                     if a.activity_type != "CREATED" and a.created_at and a.created_at >= created),
                    None,
                )
                if first_response:
                    seconds = (first_response - created).total_seconds()
                    if seconds >= 0:
                        response_durations.append(seconds)
            finished = ticket_row.resolved_at or ticket_row.closed_at
            if created and finished:
                seconds = (finished - created).total_seconds()
                if seconds >= 0:
                    resolution_durations.append(seconds)

        avg_response_seconds = (sum(response_durations) / len(response_durations)) if response_durations else None
        avg_resolution_seconds = (sum(resolution_durations) / len(resolution_durations)) if resolution_durations else None
        closed_completion_rate = ((sum(1 for x in visible_rows_for_overdue if x.status == "CLOSED") / len(visible_rows_for_overdue)) * 100) if visible_rows_for_overdue else 0
        response_buckets = {"UNDER_5": 0, "5_15": 0, "15_30": 0, "OVER_30": 0}
        for seconds in response_durations:
            minutes = seconds / 60
            if minutes < 5:
                response_buckets["UNDER_5"] += 1
            elif minutes < 15:
                response_buckets["5_15"] += 1
            elif minutes < 30:
                response_buckets["15_30"] += 1
            else:
                response_buckets["OVER_30"] += 1

        visible_ticket_ids = [t.id for t in visible_rows_for_overdue]
        activity_feed = []
        if visible_ticket_ids:
            today_start = datetime(now().year, now().month, now().day, tzinfo=LOCAL_TZ)
            tomorrow_start = today_start + timedelta(days=1)
            activity_feed = (
                TicketActivity.query
                .filter(
                    TicketActivity.ticket_id.in_(visible_ticket_ids),
                    TicketActivity.created_at >= today_start,
                    TicketActivity.created_at < tomorrow_start,
                )
                .order_by(TicketActivity.created_at.desc())
                .limit(8)
                .all()
            )

        dashboard_scope = {
            "EMPLOYEE": ("My Requests", "Requests you submitted and actions requiring your attention."),
            "IT_TECHNICIAN": ("My Assigned Work", "Tickets currently assigned to you for technical action."),
            "IT_TEAM_LEADER": ("IT Support Queue", "IT Support requests requiring assignment, monitoring, or completion approval."),
            "IT_MANAGER": ("Management Overview", "All authorized requests and completion approvals across the helpdesk."),
            "SYSTEM_ADMINISTRATOR": ("System Administration Queue", "System Administration requests assigned to your account."),
        }.get(u.role.name, ("Helpdesk", "Authorized helpdesk information."))

        role_metrics = {
            "needs_assignment": q.filter(Ticket.status == "NEW", Ticket.assigned_to_id.is_(None)).count(),
            "assigned": q.filter(Ticket.status == "ASSIGNED").count(),
            "in_progress": q.filter(Ticket.status == "IN_PROGRESS").count(),
            "pending": q.filter(Ticket.status == "PENDING").count(),
            "resolved_waiting": q.filter(Ticket.status == "RESOLVED", Ticket.completion_approved_at.is_(None)).count(),
            "awaiting_requester": q.filter(Ticket.status == "RESOLVED", Ticket.completion_approved_at.isnot(None), Ticket.requester_confirmed_at.is_(None)).count(),
            "closed": q.filter(Ticket.status == "CLOSED").count(),
            "overdue": overdue_count,
        }
        if u.role.name == "EMPLOYEE":
            role_metrics["my_open"] = q.filter(Ticket.status != "CLOSED").count()
            role_metrics["my_completed"] = q.filter(Ticket.status == "CLOSED", Ticket.requester_confirmed_at.isnot(None)).count()
        elif u.role.name == "IT_TECHNICIAN":
            role_metrics["my_assigned"] = q.filter(Ticket.assigned_to_id == u.id, Ticket.status != "CLOSED").count()
        elif u.role.name == "IT_TEAM_LEADER":
            role_metrics["queue_new"] = q.filter(Ticket.status == "NEW", Ticket.assigned_to_id.is_(None)).count()
        elif u.role.name == "IT_MANAGER":
            role_metrics["approval_queue"] = q.filter(Ticket.status == "RESOLVED", Ticket.completion_approved_at.is_(None)).count()
        elif u.role.name == "SYSTEM_ADMINISTRATOR":
            role_metrics["my_system_requests"] = q.count()

        if u.role.name == "SYSTEM_ADMINISTRATOR":

            tickets = (
                q.order_by(
                    Ticket.created_at.desc()
                )
                .limit(10)
                .all()
            )

            counts = {
                s: q.filter(
                    Ticket.status == s
                ).count()
                for s in STATUSES
            }

            activity_count = (
                AuditLog.query.count()
            )

            total_count = q.count()
            priority_counts = {p: q.filter(Ticket.priority == p).count() for p in PRIORITIES}
            request_type_counts = {rt: q.filter(Ticket.request_type == rt).count() for rt in REQUEST_TYPES}
            department_counts = {}
            for dep in Department.query.filter_by(is_active=True).order_by(Department.name).all():
                n = q.filter(Ticket.department_id == dep.id).count()
                if n:
                    department_counts[dep.name] = n
            chart_days = min((period_to - period_from).days + 1, 31)
            chart_start_date = period_to - timedelta(days=chart_days - 1)
            tickets_by_day = []
            for offset in range(chart_days - 1, -1, -1):
                day = period_to - timedelta(days=offset)
                start = datetime(day.year, day.month, day.day, tzinfo=LOCAL_TZ)
                end = start + timedelta(days=1)
                n = q.filter(Ticket.created_at >= start, Ticket.created_at < end).count()
                tickets_by_day.append({"label": day.strftime("%a"), "date": day.strftime("%d %b"), "count": n})

            return render_template(
                "dashboard.html",
                tickets=tickets,
                counts=counts,
                activity_count=activity_count,
                overdue_count=overdue_count,
                total_count=total_count,
                priority_counts=priority_counts,
                request_type_counts=request_type_counts,
                department_counts=department_counts,
                tickets_by_day=tickets_by_day,
                assignment_targets=assignment_targets(u),
                request_type_labels=REQUEST_TYPE_LABELS,
                category_counts=category_counts,
                avg_response_seconds=avg_response_seconds,
                avg_resolution_seconds=avg_resolution_seconds,
                closed_completion_rate=closed_completion_rate,
                response_buckets=response_buckets,
                activity_feed=activity_feed,
                dashboard_role=u.role.name,
                role_metrics=role_metrics,
                dashboard_scope_title=dashboard_scope[0],
                dashboard_scope_description=dashboard_scope[1],
                dashboard_period_start=tickets_by_day[0]["date"],
                dashboard_period_end=tickets_by_day[-1]["date"],
                dashboard_period_from=period_from.isoformat(),
                dashboard_period_to=period_to.isoformat(),
            )

        tickets = (
            q.order_by(
                Ticket.created_at.asc()
                if u.role.name == "IT_TEAM_LEADER"
                else Ticket.created_at.desc()
            )
            .limit(12)
            .all()
        )

        counts = {
            s: q.filter(
                Ticket.status == s
            ).count()
            for s in STATUSES
        }

        # Dashboard analytics are derived exclusively from the same authorized
        # ticket query used by the rest of the application. No demo data or
        # hardcoded business metrics are used.
        total_count = q.count()
        priority_counts = {
            p: q.filter(Ticket.priority == p).count()
            for p in PRIORITIES
        }
        request_type_counts = {
            rt: q.filter(Ticket.request_type == rt).count()
            for rt in REQUEST_TYPES
        }

        department_counts = {}
        for dep in Department.query.filter_by(is_active=True).order_by(Department.name).all():
            n = q.filter(Ticket.department_id == dep.id).count()
            if n:
                department_counts[dep.name] = n

        # Respect the user-selected reporting window for every dashboard role.
        # Limit the visual series to 31 days so a very large date range remains
        # readable while the KPI/count queries still use the full selected range.
        chart_days = min((period_to - period_from).days + 1, 31)
        chart_start_date = period_to - timedelta(days=chart_days - 1)
        tickets_by_day = []
        for offset in range(chart_days - 1, -1, -1):
            day = period_to - timedelta(days=offset)
            start = datetime(day.year, day.month, day.day, tzinfo=LOCAL_TZ)
            end = start + timedelta(days=1)
            n = q.filter(Ticket.created_at >= start, Ticket.created_at < end).count()
            tickets_by_day.append({
                "label": day.strftime("%a"),
                "date": day.strftime("%d %b"),
                "count": n,
            })

        return render_template(
            "dashboard.html",
            tickets=tickets,
            counts=counts,
            activity_count=None,
            overdue_count=overdue_count,
            total_count=total_count,
            priority_counts=priority_counts,
            request_type_counts=request_type_counts,
            department_counts=department_counts,
            tickets_by_day=tickets_by_day,
            assignment_targets=assignment_targets(u),
            request_type_labels=REQUEST_TYPE_LABELS,
            category_counts=category_counts,
            avg_response_seconds=avg_response_seconds,
            avg_resolution_seconds=avg_resolution_seconds,
            closed_completion_rate=closed_completion_rate,
            response_buckets=response_buckets,
            activity_feed=activity_feed,
            dashboard_role=u.role.name,
            role_metrics=role_metrics,
            dashboard_scope_title=dashboard_scope[0],
            dashboard_scope_description=dashboard_scope[1],
            dashboard_period_start=tickets_by_day[0]["date"],
            dashboard_period_end=tickets_by_day[-1]["date"],
            dashboard_period_from=period_from.isoformat(),
            dashboard_period_to=period_to.isoformat(),
        )


    @app.route(
        "/tickets/new",
        methods=["GET", "POST"]
    )
    @roles(
        "EMPLOYEE",
        "IT_TECHNICIAN",
        "IT_TEAM_LEADER",
        "IT_MANAGER"
    )
    def new_ticket():

        u = current_user()

        if u.role.name == "EMPLOYEE":

            allowed_types = [
                "IT_SUPPORT"
            ]

        elif u.role.name == "IT_MANAGER":

            allowed_types = [
                "IT_SUPPORT",
                "SYSTEM_ADMIN_SUPPORT"
            ]

        else:

            allowed_types = [
                "SYSTEM_ADMIN_SUPPORT"
            ]

        if request.method == "POST":

            f = request.form

            subject = (
                f.get("subject", "")
                .strip()
            )

            desc = (
                f.get("description", "")
                .strip()
            )

            request_type = f.get(
                "request_type",
                "IT_SUPPORT"
            )

            if request_type not in allowed_types:
                abort(403)

            dep = (
                int(f["department_id"])
                if f.get("department_id")
                else u.department_id
            )

            cat = (
                int(f["category_id"])
                if f.get("category_id")
                else None
            )

            category = db.session.get(Category, cat) if cat else None
            if category and (not category.is_active or category.request_type != request_type):
                flash("The selected category is not valid for this request type.", "error")
                category = None
                cat = None

            if not subject or not desc or not dep:

                flash(
                    "Subject, description and department are required.",
                    "error"
                )

            else:

                initial_priority = f.get(
                    "priority",
                    "MEDIUM"
                )

                if initial_priority not in PRIORITIES:
                    initial_priority = "MEDIUM"

                t = Ticket(
                    subject=subject,
                    description=desc,
                    request_type=request_type,
                    requester_id=u.id,
                    department_id=dep,
                    category_id=cat,
                    priority=initial_priority,
                    status="NEW"
                )

                db.session.add(t)

                db.session.flush()

                t.ticket_no = (
                    f"MKDSS-{t.id:06d}"
                )

                db.session.add(
                    TicketActivity(
                        ticket=t,
                        user_id=u.id,
                        activity_type="CREATED",
                        note=(
                            f"{REQUEST_TYPE_LABELS[request_type]} "
                            "request created."
                        )
                    )
                )

                if request_type == "SYSTEM_ADMIN_SUPPORT":

                    admin = user_by_role(
                        "SYSTEM_ADMINISTRATOR"
                    )

                    if admin:

                        t.assigned_to_id = admin.id

                        t.status = "ASSIGNED"

                        db.session.add(
                            TicketActivity(
                                ticket=t,
                                user_id=u.id,
                                activity_type="ASSIGNMENT",
                                note=(
                                    "System administration request "
                                    f"routed to {admin.full_name}."
                                )
                            )
                        )

                        flash(
                            f"Request {t.ticket_no} created and sent to {admin.full_name}.",
                            "success"
                        )

                    else:

                        flash(
                            f"Request {t.ticket_no} was created, but no active System Administrator is available. It is waiting for SAdmin.",
                            "error"
                        )

                else:

                    flash(
                        f"Request {t.ticket_no} created.",
                        "success"
                    )

                db.session.commit()

                notification_count = notify_new_request_workflow(t)
                log(
                    "TICKET_CREATED",
                    "Ticket",
                    t.id,
                    f"{t.ticket_no}; type={request_type}; queue_notifications={notification_count}"
                )
                # Also notify the directly assigned SAdmin for system-admin requests.
                if t.assigned_to_id and t.request_type == "SYSTEM_ADMIN_SUPPORT":
                    create_notification(
                        t.technician,
                        "System administration request assigned",
                        f"{t.ticket_no} has been assigned to you and requires action.",
                        kind="ASSIGNMENT",
                        ticket=t,
                        url=url_for("ticket", ticket_id=t.id),
                        dedupe_key=f"ASSIGNMENT:{t.id}:{t.assigned_to_id}:created"
                    )
                db.session.commit()

                return redirect(
                    url_for(
                        "ticket",
                        ticket_id=t.id
                    )
                )

        return render_template(
            "ticket_new.html",
            departments=(
                Department.query
                .filter_by(is_active=True)
                .order_by(Department.name)
                .all()
            ),
            categories=(
                Category.query
                .filter(
                    Category.is_active.is_(True),
                    Category.request_type.in_(allowed_types)
                )
                .order_by(Category.name)
                .all()
            ),
            allowed_types=allowed_types,
            request_type_labels=REQUEST_TYPE_LABELS
        )


    @app.get("/tickets")
    @login_required
    def tickets():

        u = current_user()

        if u.role.name == "SYSTEM_ADMINISTRATOR":
            return redirect(
                url_for("dashboard")
            )

        q = accessible_ticket_query(u)

        status = request.args.get("status")
        request_type = request.args.get("request_type", "").strip().upper()
        priority = request.args.get("priority", "").strip().upper()
        assigned = request.args.get("assigned_to", "").strip()
        overdue_only = request.args.get("overdue") == "1"
        search = request.args.get("q", "").strip()

        if status in STATUSES:
            q = q.filter(Ticket.status == status)
        if request_type in REQUEST_TYPES:
            q = q.filter(Ticket.request_type == request_type)
        if priority in PRIORITIES:
            q = q.filter(Ticket.priority == priority)
        if assigned.isdigit():
            q = q.filter(Ticket.assigned_to_id == int(assigned))
        if search:
            q = q.filter(
                (Ticket.ticket_no.ilike(f"%{search}%")) |
                (Ticket.subject.ilike(f"%{search}%")) |
                (Ticket.description.ilike(f"%{search}%"))
            )

        rows = q.order_by(
            Ticket.created_at.asc() if u.role.name == "IT_TEAM_LEADER"
            else Ticket.created_at.desc()
        ).all()

        if overdue_only:
            rows = [t for t in rows if is_ticket_overdue(t)]

        return render_template(
            "tickets.html",
            tickets=rows,
            assignment_targets=assignment_targets(u),
            request_type_labels=REQUEST_TYPE_LABELS
        )


    @app.get("/tickets/<int:ticket_id>")
    @login_required
    def ticket(ticket_id):

        t = db.session.get(
            Ticket,
            ticket_id
        )

        if not t:
            abort(404)

        u = current_user()

        if not can_view_ticket(u, t):
            abort(403)

        targets = assignment_targets(u, t)

        return render_template(
            "ticket.html",
            t=t,
            technicians=targets,
            can_edit=can_update_ticket(u, t),
            overdue=is_ticket_overdue(t)
        )


    @app.post("/tickets/<int:ticket_id>/update")
    @login_required
    def update_ticket(ticket_id):

        t = db.session.get(
            Ticket,
            ticket_id
        )

        u = current_user()

        if not t:
            abort(404)

        if not can_update_ticket(u, t):
            abort(403)

        f = request.form

        old = t.status

        new = f.get(
            "status",
            old
        )

        allowed_transitions = {
            "NEW": {"ASSIGNED"},
            "ASSIGNED": {"IN_PROGRESS", "PENDING"},
            "IN_PROGRESS": {"PENDING"},
            "PENDING": {"IN_PROGRESS"},
            "RESOLVED": {"IN_PROGRESS"},
            "CLOSED": set(),
        }
        if new not in STATUSES or (new != old and new not in allowed_transitions.get(old, set())):
            flash(f"Invalid status transition from {old.replace('_',' ').title()} to {new.replace('_',' ').title()}.", "error")
            return redirect(url_for("ticket", ticket_id=t.id))

        if (
            u.role.name == "SYSTEM_ADMINISTRATOR"
            and t.request_type != "SYSTEM_ADMIN_SUPPORT"
        ):
            abort(403)

        if new == "CLOSED":
            flash("The requester must confirm and accept the completed work before the ticket can be closed.", "error")
            return redirect(url_for("ticket", ticket_id=t.id))

        note = (
            f.get("note", "")
            .strip()
        )

        if (
            new in ("RESOLVED", "CLOSED")
            and u.role.name in (
                "IT_TECHNICIAN",
                "IT_TEAM_LEADER",
                "IT_MANAGER",
                "SYSTEM_ADMINISTRATOR"
            )
            and not note
        ):

            flash(
                "Please enter the work performed or resolution description before marking the request as resolved or closed.",
                "error"
            )

            return redirect(
                url_for(
                    "ticket",
                    ticket_id=t.id
                )
            )

        # Priority is immutable after creation.

        if new != old:

            t.status = new

            if new == "RESOLVED":
                t.resolved_at = now()
                t.completion_approved_by_id = None
                t.completion_approved_at = None
                t.completion_approval_note = None
                t.requester_confirmed_by_id = None
                t.requester_confirmed_at = None
                t.requester_confirmation_note = None

            if new == "IN_PROGRESS":
                t.completion_approved_by_id = None
                t.completion_approved_at = None
                t.completion_approval_note = None
                t.requester_confirmed_by_id = None
                t.requester_confirmed_at = None
                t.requester_confirmation_note = None

            if new == "CLOSED":
                t.closed_at = now()

        if note:

            db.session.add(
                TicketActivity(
                    ticket=t,
                    user_id=u.id,
                    activity_type="UPDATE",
                    note=note,
                    old_status=old,
                    new_status=(
                        new
                        if new != old
                        else None
                    )
                )
            )

        elif new != old:

            db.session.add(
                TicketActivity(
                    ticket=t,
                    user_id=u.id,
                    activity_type="STATUS_CHANGE",
                    note=(
                        f"Status changed from "
                        f"{old} to {new}."
                    ),
                    old_status=old,
                    new_status=new
                )
            )

        db.session.commit()

        log(
            "TICKET_UPDATED",
            "Ticket",
            t.id,
            f"status={t.status}"
        )
        if new != old:
            notify_ticket_event(
                t,
                "Request status updated",
                f"{t.ticket_no} status changed to {t.status.replace('_',' ').title()}.",
                kind="STATUS",
                exclude_user_id=u.id
            )
            db.session.commit()

        flash(
            "Request updated.",
            "success"
        )

        return redirect(
            url_for(
                "ticket",
                ticket_id=t.id
            )
        )


    @app.post("/tickets/<int:ticket_id>/assign")
    @roles(
        "IT_TEAM_LEADER",
        "IT_MANAGER"
    )
    def assign(ticket_id):

        t = db.session.get(
            Ticket,
            ticket_id
        )

        u = current_user()

        if not t:
            abort(404)

        if u.role.name == "IT_TEAM_LEADER":

            if t.request_type != "IT_SUPPORT":
                abort(403)

        elif u.role.name == "IT_MANAGER":

            if t.requester_id != u.id:
                abort(403)

        else:

            abort(403)

        raw_assignee = request.form.get(
            "assignee_id"
        )

        if raw_assignee is None:

            raw_assignee = request.form.get(
                "technician_id"
            )

        try:

            assignee_id = int(
                raw_assignee or "0"
            )

        except (
            TypeError,
            ValueError
        ):

            flash(
                "Please select a valid person to assign the request to.",
                "error"
            )

            return redirect(
                url_for(
                    "ticket",
                    ticket_id=t.id
                )
            )

        target = (
            User.query
            .join(Role)
            .filter(
                User.id == assignee_id,
                User.is_active.is_(True)
            )
            .first()
        )

        if not target:

            flash(
                "The selected user does not exist or is inactive.",
                "error"
            )

            return redirect(
                url_for(
                    "ticket",
                    ticket_id=t.id
                )
            )

        if t.request_type == "IT_SUPPORT":

            allowed_roles = {
                "IT_TEAM_LEADER",
                "IT_TECHNICIAN"
            }

        elif t.request_type == "SYSTEM_ADMIN_SUPPORT":

            allowed_roles = {
                "SYSTEM_ADMINISTRATOR"
            }

        else:

            flash(
                "This request has an invalid request type and cannot be assigned.",
                "error"
            )

            return redirect(
                url_for(
                    "ticket",
                    ticket_id=t.id
                )
            )

        if target.role.name not in allowed_roles:

            if t.request_type == "IT_SUPPORT":

                flash(
                    "IT Support requests can only be assigned to an IT Technician or IT Team Leader.",
                    "error"
                )

            else:

                flash(
                    "System Administration Support requests can only be assigned to the System Administrator.",
                    "error"
                )

            return redirect(
                url_for(
                    "ticket",
                    ticket_id=t.id
                )
            )

        if (
            u.role.name == "IT_TEAM_LEADER"
            and target.role.name not in (
                "IT_TECHNICIAN",
                "IT_TEAM_LEADER"
            )
        ):
            abort(403)

        old_id = t.assigned_to_id

        t.assigned_to_id = target.id

        if t.status == "NEW":
            t.status = "ASSIGNED"

        db.session.add(
            TicketActivity(
                ticket=t,
                user_id=u.id,
                activity_type="ASSIGNMENT",
                note=(
                    f"Assigned to "
                    f"{target.full_name} "
                    f"({target.role.display_name})."
                )
            )
        )

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            app.logger.exception(
                "TICKET ASSIGNMENT FAILED: "
                "ticket=%s user=%s target=%s",
                t.id,
                u.id,
                assignee_id
            )

            flash(
                "The request could not be assigned. No changes were saved.",
                "error"
            )

            return redirect(
                url_for(
                    "ticket",
                    ticket_id=t.id
                )
            )

        log(
            "TICKET_ASSIGNED",
            "Ticket",
            t.id,
            (
                f"previous_assignee={old_id}; "
                f"assignee={target.employee_id}; "
                f"role={target.role.name}"
            )
        )

        notify_ticket_event(
            t,
            "Request assigned",
            f"{t.ticket_no} has been assigned to {target.full_name}.",
            kind="ASSIGNMENT",
            exclude_user_id=u.id
        )
        db.session.commit()

        flash(
            f"Request assigned to {target.full_name}.",
            "success"
        )

        return redirect(
            url_for(
                "ticket",
                ticket_id=t.id
            )
        )


    @app.post("/tickets/<int:ticket_id>/comment")
    @login_required
    def comment(ticket_id):

        t = db.session.get(
            Ticket,
            ticket_id
        )

        u = current_user()

        if not t:
            abort(404)

        if not can_update_ticket(u, t):
            abort(403)

        note = (
            request.form
            .get("note", "")
            .strip()
        )

        if not note:

            flash(
                "Activity note is required.",
                "error"
            )

        else:

            db.session.add(
                TicketActivity(
                    ticket=t,
                    user_id=u.id,
                    activity_type="COMMENT",
                    note=note
                )
            )

            db.session.commit()

            log(
                "TICKET_ACTIVITY_ADDED",
                "Ticket",
                t.id
            )
            notify_ticket_event(
                t,
                "New ticket activity",
                f"New work activity was added to {t.ticket_no}.",
                kind="ACTIVITY",
                exclude_user_id=u.id
            )
            db.session.commit()

            flash(
                "Activity recorded.",
                "success"
            )

        return redirect(
            url_for(
                "ticket",
                ticket_id=t.id
            )
        )


    @app.post("/tickets/<int:ticket_id>/upload")
    @login_required
    def upload(ticket_id):

        t = db.session.get(
            Ticket,
            ticket_id
        )

        u = current_user()

        if not t:
            abort(404)

        if not can_update_ticket(u, t):
            abort(403)

        f = request.files.get("file")

        if not f or not f.filename:

            flash(
                "Select a file.",
                "error"
            )

        else:

            safe = secure_filename(
                f.filename
            )

            stored = (
                secrets.token_hex(16)
                + "_"
                + safe
            )

            f.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    stored
                )
            )

            db.session.add(
                Attachment(
                    ticket_id=t.id,
                    original_name=f.filename,
                    stored_name=stored,
                    content_type=f.content_type,
                    uploaded_by_id=u.id
                )
            )

            db.session.add(
                TicketActivity(
                    ticket_id=t.id,
                    user_id=u.id,
                    activity_type="ATTACHMENT",
                    note=(
                        f"Attachment uploaded: "
                        f"{f.filename}"
                    )
                )
            )

            db.session.commit()

            log(
                "ATTACHMENT_UPLOADED",
                "Ticket",
                t.id,
                f.filename
            )
            notify_ticket_event(
                t,
                "Ticket attachment added",
                f"A new attachment was added to {t.ticket_no}.",
                kind="ATTACHMENT",
                exclude_user_id=u.id
            )
            db.session.commit()

            flash(
                "Attachment uploaded.",
                "success"
            )

        return redirect(
            url_for(
                "ticket",
                ticket_id=t.id
            )
        )


    @app.get("/attachments/<int:attachment_id>")
    @login_required
    def attachment(attachment_id):

        a = db.session.get(
            Attachment,
            attachment_id
        )

        if not a:
            abort(404)

        t = a.ticket

        u = current_user()

        if not can_view_ticket(u, t):
            abort(403)

        path = os.path.join(app.config["UPLOAD_FOLDER"], a.stored_name)
        if not os.path.isfile(path):
            abort(404)
        return send_file(
            path,
            download_name=a.original_name,
            as_attachment=False
        )


    # ============================================================
    # NOTIFICATIONS
    # ============================================================

    @app.get("/notifications/unread-count")
    @login_required
    def notifications_unread_count():
        """Return only the current user's unread notification count for polling.

        This endpoint intentionally does not reload or replace the current page,
        so users can keep typing work notes without losing their draft.
        """
        u = current_user()
        count = Notification.query.filter_by(user_id=u.id, is_read=False).count()
        return jsonify({"unread": count})

    @app.get("/notifications")
    @login_required
    def notifications():
        refresh_overdue_notifications()
        u = current_user()
        rows = (Notification.query
                .filter_by(user_id=u.id)
                .order_by(Notification.created_at.desc())
                .limit(250).all())
        return render_template("notifications.html", notifications=rows)

    @app.post("/notifications/<int:notification_id>/read")
    @login_required
    def notification_read(notification_id):
        n = db.session.get(Notification, notification_id)
        u = current_user()
        if not n or n.user_id != u.id:
            abort(403)
        n.is_read = True
        db.session.commit()
        log("NOTIFICATION_READ", "Notification", n.id)
        # Mark-read is deliberately a state-only action. It must NOT open the
        # related ticket; opening a notification is a separate action.
        return redirect(url_for("notifications"))

    @app.post("/notifications/read-all")
    @login_required
    def notifications_read_all():
        u = current_user()
        Notification.query.filter_by(user_id=u.id, is_read=False).update(
            {Notification.is_read: True}, synchronize_session=False
        )
        db.session.commit()
        log("NOTIFICATIONS_READ_ALL", "Notification")
        return redirect(url_for("notifications"))

    @app.get("/notifications/open/<int:notification_id>")
    @login_required
    def notification_open(notification_id):
        n = db.session.get(Notification, notification_id)
        u = current_user()
        if not n or n.user_id != u.id:
            abort(403)
        n.is_read = True
        db.session.commit()
        log("NOTIFICATION_OPENED", "Notification", n.id)
        if n.ticket_id:
            t = db.session.get(Ticket, n.ticket_id)
            if t and can_view_ticket(u, t):
                return redirect(url_for("ticket", ticket_id=t.id))
        return redirect(url_for("notifications"))

    @app.post("/tickets/<int:ticket_id>/submit-completion")
    @login_required
    def submit_completion(ticket_id):
        """Explicit completion action for the assigned technician/SAdmin/team leader."""
        t = db.session.get(Ticket, ticket_id)
        u = current_user()
        if not t:
            abort(404)
        if not can_update_ticket(u, t):
            abort(403)
        if t.status not in ("ASSIGNED", "IN_PROGRESS", "PENDING"):
            flash("This request cannot be submitted for completion from its current status.", "error")
            return redirect(url_for("ticket", ticket_id=t.id))
        note = request.form.get("completion_note", "").strip()
        if not note:
            flash("Enter the work performed and resolution before submitting completion.", "error")
            return redirect(url_for("ticket", ticket_id=t.id))
        old = t.status
        t.status = "RESOLVED"
        t.resolved_at = now()
        t.completion_approved_by_id = None
        t.completion_approved_at = None
        t.completion_approval_note = None
        t.requester_confirmed_by_id = None
        t.requester_confirmed_at = None
        t.requester_confirmation_note = None
        db.session.add(TicketActivity(
            ticket=t, user_id=u.id, activity_type="COMPLETION_SUBMITTED",
            note=f"Completion submitted by {u.full_name}. {note}",
            old_status=old, new_status="RESOLVED"
        ))
        db.session.commit()
        # Explicitly notify the authorized approver(s).
        if t.request_type == "IT_SUPPORT":
            approvers = User.query.join(Role).filter(
                Role.name.in_(["IT_TEAM_LEADER", "IT_MANAGER"]), User.is_active.is_(True)
            ).all()
        else:
            approvers = User.query.join(Role).filter(
                Role.name == "IT_MANAGER", User.is_active.is_(True)
            ).all()
        for approver in approvers:
            if approver.id != u.id:
                create_notification(
                    approver, "Completion approval required",
                    f"{t.ticket_no} was marked completed by {u.full_name}. Please review and approve or return it.",
                    kind="COMPLETION_PENDING", ticket=t,
                    url=url_for("ticket", ticket_id=t.id),
                    dedupe_key=f"COMPLETION_PENDING:{t.id}:{approver.id}:{t.resolved_at.timestamp()}"
                )
        db.session.commit()
        flash("Completion submitted for Team Leader/Manager approval.", "success")
        return redirect(url_for("ticket", ticket_id=t.id))


    @app.post("/tickets/<int:ticket_id>/approve-completion")
    @roles("IT_MANAGER", "IT_TEAM_LEADER")
    def approve_completion(ticket_id):
        t = db.session.get(Ticket, ticket_id)
        u = current_user()
        if not t:
            abort(404)
        if not can_approve_completion(u, t) or not can_view_ticket(u, t):
            abort(403)
        note = request.form.get("approval_note", "").strip()
        if not note:
            flash("Approval note is required before approving completion.", "error")
            return redirect(url_for("ticket", ticket_id=t.id))
        t.completion_approved_by_id = u.id
        t.completion_approved_at = now()
        t.completion_approval_note = note
        db.session.add(TicketActivity(ticket=t, user_id=u.id, activity_type="COMPLETION_APPROVAL", note=f"Completion approved by {u.full_name}. {note}"))
        db.session.commit()
        create_notification(
            t.requester,
            "Completed work ready for your confirmation",
            f"{t.ticket_no} was completed by {t.technician.full_name if t.technician else 'support staff'} and approved by {u.full_name}. Please review and confirm acceptance.",
            kind="COMPLETION_APPROVAL", ticket=t, url=url_for("ticket", ticket_id=t.id),
            dedupe_key=f"COMPLETION_APPROVAL:{t.id}:{u.id}:{int(t.completion_approved_at.timestamp())}"
        )
        db.session.commit()
        flash("Completion approved. The requester has been notified to review and accept the work.", "success")
        return redirect(url_for("ticket", ticket_id=t.id))


    @app.post("/tickets/<int:ticket_id>/reject-completion")
    @roles("IT_MANAGER", "IT_TEAM_LEADER")
    def reject_completion(ticket_id):
        t = db.session.get(Ticket, ticket_id)
        u = current_user()
        if not t:
            abort(404)
        if not can_approve_completion(u, t) or not can_view_ticket(u, t):
            abort(403)
        note = request.form.get("rejection_note", "").strip()
        if not note:
            flash("A reason is required when sending a completed request back for work.", "error")
            return redirect(url_for("ticket", ticket_id=t.id))
        t.status = "IN_PROGRESS"
        t.completion_approved_by_id = None
        t.completion_approved_at = None
        t.completion_approval_note = None
        t.requester_confirmed_by_id = None
        t.requester_confirmed_at = None
        t.requester_confirmation_note = None
        db.session.add(TicketActivity(ticket=t, user_id=u.id, activity_type="COMPLETION_REJECTED", note=f"Completion sent back by {u.full_name}. {note}", old_status="RESOLVED", new_status="IN_PROGRESS"))
        db.session.commit()
        notify_ticket_event(t, "Completion needs more work", f"{t.ticket_no} was sent back for additional work by {u.full_name}: {note}", kind="COMPLETION_REJECTED", exclude_user_id=u.id)
        db.session.commit()
        flash("The request was returned for additional work.", "success")
        return redirect(url_for("ticket", ticket_id=t.id))


    @app.get("/tickets/<int:ticket_id>/completion-report")
    @login_required
    def completion_report(ticket_id):
        t = db.session.get(Ticket, ticket_id)
        u = current_user()
        if not t:
            abort(404)
        if not is_completed_request(t):
            abort(404)
        if not can_view_ticket(u, t):
            abort(403)
        return render_template("completion_report.html", t=t)


    @app.get("/tickets/<int:ticket_id>/completion-report/pdf")
    @login_required
    def completion_report_pdf(ticket_id):
        t = db.session.get(Ticket, ticket_id)
        u = current_user()
        if not t:
            abort(404)
        if not is_completed_request(t) or not can_view_ticket(u, t):
            abort(403)
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            abort(500)
        buf=io.BytesIO(); c=canvas.Canvas(buf,pagesize=A4); width,height=A4; y=height-45
        c.setFont("Helvetica-Bold",16); c.drawString(40,y,"MKDSS IT Helpdesk - Completion Report"); y-=24
        c.setFont("Helvetica",10)
        for label,value in [
            ("Ticket",t.ticket_no),("Subject",t.subject),("Requester",t.requester.full_name if t.requester else "Deleted User"),
            ("Assignee",t.technician.full_name if t.technician else "—"),("Priority",t.priority),("Status",t.status),
            ("Approved By",t.completion_approved_by.full_name if t.completion_approved_by else "—"),
            ("Approved At",localtime(t.completion_approved_at)),
            ("Accepted By",t.requester_confirmed_by.full_name if t.requester_confirmed_by else "—"),
            ("Accepted At",localtime(t.requester_confirmed_at)),
            ("Closed At",localtime(t.closed_at))]:
            c.drawString(40,y,f"{label}: {value}"); y-=15
        y-=8; c.setFont("Helvetica-Bold",11); c.drawString(40,y,"Management Approval"); y-=16; c.setFont("Helvetica",9)
        for line in (t.completion_approval_note or "").splitlines() or [""]:
            c.drawString(40,y,line[:115]); y-=13
        y-=8; c.setFont("Helvetica-Bold",11); c.drawString(40,y,"Requester Acceptance"); y-=16; c.setFont("Helvetica",9)
        for line in (t.requester_confirmation_note or "").splitlines() or [""]:
            c.drawString(40,y,line[:115]); y-=13
        y-=10; c.setFont("Helvetica-Bold",11); c.drawString(40,y,"Work / Activity History"); y-=16; c.setFont("Helvetica",8)
        for a in t.activities:
            if a.activity_type not in ("UPDATE","STATUS_CHANGE","COMPLETION_REJECTED","COMPLETION_APPROVAL","REQUESTER_ACCEPTED","ASSIGNMENT"): continue
            line=f"{localtime(a.created_at)} | {a.user.full_name if a.user else 'Deleted User'} | {a.note}"
            for chunk in [line[i:i+115] for i in range(0,len(line),115)]:
                if y<45: c.showPage(); y=height-45; c.setFont("Helvetica",8)
                c.drawString(40,y,chunk); y-=11
        c.save(); buf.seek(0)
        return send_file(buf,as_attachment=True,download_name=f"{t.ticket_no}_completion_report.pdf",mimetype="application/pdf")


    @app.post("/tickets/<int:ticket_id>/confirm-completion")
    @login_required
    def confirm_completion(ticket_id):
        t = db.session.get(Ticket, ticket_id)
        u = current_user()
        if not t:
            abort(404)
        if not can_confirm_completion(u, t):
            abort(403)
        note = request.form.get("confirmation_note", "").strip()
        if not note:
            flash("Please confirm what was completed and accepted.", "error")
            return redirect(url_for("ticket", ticket_id=t.id))
        t.requester_confirmed_by_id = u.id
        t.requester_confirmed_at = now()
        t.requester_confirmation_note = note
        t.status = "CLOSED"
        t.closed_at = now()
        db.session.add(TicketActivity(ticket=t, user_id=u.id, activity_type="REQUESTER_ACCEPTED", note=f"Requester confirmed and accepted the completed work. {note}", old_status="RESOLVED", new_status="CLOSED"))
        db.session.commit()
        notify_ticket_event(t, "Request completed and accepted", f"{t.ticket_no} was confirmed and accepted by the requester.", kind="COMPLETION_ACCEPTED", exclude_user_id=u.id)
        db.session.commit()
        flash("Thank you. The completed work has been accepted and the request is now closed.", "success")
        return redirect(url_for("ticket", ticket_id=t.id))


    @app.get("/reports/completed")
    @roles("IT_MANAGER", "IT_TEAM_LEADER", "IT_TECHNICIAN", "SYSTEM_ADMINISTRATOR")
    def completed_reports():
        u = current_user()
        q = accessible_ticket_query(u).filter(
            Ticket.status == "CLOSED",
            Ticket.completion_approved_at.isnot(None),
            Ticket.requester_confirmed_at.isnot(None)
        )
        start = request.args.get("from", "").strip()
        end = request.args.get("to", "").strip()
        qtext = request.args.get("q", "").strip()
        if start:
            try: q = q.filter(Ticket.closed_at >= datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ))
            except ValueError: start = ""
        if end:
            try: q = q.filter(Ticket.closed_at < datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ) + timedelta(days=1))
            except ValueError: end = ""
        if qtext:
            q = q.filter(Ticket.ticket_no.ilike(f"%{qtext}%") | Ticket.subject.ilike(f"%{qtext}%"))
        rows = q.order_by(Ticket.closed_at.desc()).all()
        return render_template("completed_reports.html", rows=rows, start=start, end=end, search=qtext, total=len(rows))


    @app.get("/reports/completed/csv")
    @roles("IT_MANAGER", "IT_TEAM_LEADER", "IT_TECHNICIAN", "SYSTEM_ADMINISTRATOR")
    def completed_report_csv():
        u = current_user()
        q = accessible_ticket_query(u).filter(Ticket.status == "CLOSED", Ticket.completion_approved_at.isnot(None), Ticket.requester_confirmed_at.isnot(None))
        start=request.args.get("from", "").strip(); end=request.args.get("to", "").strip(); qtext=request.args.get("q", "").strip()
        if start:
            try: q=q.filter(Ticket.closed_at >= datetime.strptime(start,"%Y-%m-%d").replace(tzinfo=LOCAL_TZ))
            except ValueError: pass
        if end:
            try: q=q.filter(Ticket.closed_at < datetime.strptime(end,"%Y-%m-%d").replace(tzinfo=LOCAL_TZ)+timedelta(days=1))
            except ValueError: pass
        if qtext: q=q.filter(Ticket.ticket_no.ilike(f"%{qtext}%") | Ticket.subject.ilike(f"%{qtext}%"))
        out=io.StringIO(); w=csv.writer(out)
        w.writerow(["Ticket","Requester","Department","Assignee","Priority","Resolution","Approved By","Approved At","Requester Acceptance","Accepted At","Closed At"])
        for t in q.order_by(Ticket.closed_at.desc()).all():
            w.writerow([t.ticket_no, t.requester.full_name if t.requester else "Deleted User", t.department.name if t.department else "", t.technician.full_name if t.technician else "", t.priority, next((a.note for a in reversed(t.activities) if a.activity_type in ("UPDATE","COMPLETION_APPROVAL") and a.note), ""), t.completion_approved_by.full_name if t.completion_approved_by else "", localtime(t.completion_approved_at), t.requester_confirmation_note or "", localtime(t.requester_confirmed_at), localtime(t.closed_at)])
        resp=make_response(out.getvalue()); resp.headers["Content-Type"]="text/csv; charset=utf-8"; resp.headers["Content-Disposition"]="attachment; filename=mkdss_completed_requests.csv"; return resp


    @app.get("/reports")
    @roles(
        "IT_MANAGER",
        "IT_TEAM_LEADER",
        "IT_TECHNICIAN",
        "SYSTEM_ADMINISTRATOR"
    )
    def reports():

        u = current_user()

        status = (
            request.args
            .get("status", "")
            .strip()
            .upper()
        )

        search = (
            request.args
            .get("q", "")
            .strip()
        )

        if u.role.name == "SYSTEM_ADMINISTRATOR":

            q = Ticket.query.filter(
                Ticket.request_type == "SYSTEM_ADMIN_SUPPORT",
                Ticket.assigned_to_id == u.id
            )

        elif u.role.name == "IT_TECHNICIAN":

            q = Ticket.query.filter(
                Ticket.assigned_to_id == u.id
            )

        elif u.role.name == "IT_TEAM_LEADER":

            assigned_by = (
                db.session.query(
                    TicketActivity.ticket_id
                )
                .filter(
                    TicketActivity.user_id == u.id,
                    TicketActivity.activity_type
                    == "ASSIGNMENT"
                )
            )

            q = Ticket.query.filter(
                (Ticket.assigned_to_id == u.id)
                |
                Ticket.id.in_(assigned_by)
            )

        else:

            q = Ticket.query

        if status in STATUSES:

            q = q.filter(
                Ticket.status == status
            )

        if search:

            q = q.filter(
                (Ticket.ticket_no.ilike(
                    f"%{search}%"
                ))
                |
                (Ticket.subject.ilike(
                    f"%{search}%"
                ))
            )

        rows = (
            q.order_by(
                Ticket.created_at.desc()
            )
            .all()
        )

        counts = {
            st: q.filter(
                Ticket.status == st
            ).count()
            for st in STATUSES
        }

        return render_template(
            "reports.html",
            rows=rows,
            report_user=u,
            counts=counts,
            selected_status=(
                status
                if status in STATUSES
                else ""
            ),
            search=search,
            request_type_labels=REQUEST_TYPE_LABELS,
            statuses=STATUSES
        )


    @app.get("/reports/csv")
    @roles(
        "IT_MANAGER",
        "IT_TEAM_LEADER",
        "IT_TECHNICIAN",
        "SYSTEM_ADMINISTRATOR"
    )
    def report_csv():

        u = current_user()

        status = (
            request.args
            .get("status", "")
            .strip()
            .upper()
        )

        search = (
            request.args
            .get("q", "")
            .strip()
        )

        if u.role.name == "SYSTEM_ADMINISTRATOR":

            q = Ticket.query.filter(
                Ticket.request_type == "SYSTEM_ADMIN_SUPPORT",
                Ticket.assigned_to_id == u.id
            )

        elif u.role.name == "IT_TECHNICIAN":

            q = Ticket.query.filter(
                Ticket.assigned_to_id == u.id
            )

        elif u.role.name == "IT_TEAM_LEADER":

            assigned_by = (
                db.session.query(
                    TicketActivity.ticket_id
                )
                .filter(
                    TicketActivity.user_id == u.id,
                    TicketActivity.activity_type
                    == "ASSIGNMENT"
                )
            )

            q = Ticket.query.filter(
                (Ticket.assigned_to_id == u.id)
                |
                Ticket.id.in_(assigned_by)
            )

        else:

            q = Ticket.query

        if status in STATUSES:

            q = q.filter(
                Ticket.status == status
            )

        if search:

            q = q.filter(
                (Ticket.ticket_no.ilike(
                    f"%{search}%"
                ))
                |
                (Ticket.subject.ilike(
                    f"%{search}%"
                ))
            )

        rows = (
            q.order_by(
                Ticket.created_at.desc()
            )
            .all()
        )

        out = io.StringIO()

        w = csv.writer(out)

        w.writerow([
            "Ticket",
            "Type",
            "Subject",
            "Requester",
            "Department",
            "Assignee",
            "Priority",
            "Status",
            "Created",
            "Resolved",
            "Closed"
        ])

        for t in rows:

            w.writerow([
                t.ticket_no,
                REQUEST_TYPE_LABELS.get(
                    t.request_type,
                    t.request_type
                ),
                t.subject,
                (
                    t.requester.full_name
                    if t.requester
                    else "Deleted user"
                ),
                (
                    t.department.name
                    if t.department
                    else ""
                ),
                (
                    t.technician.full_name
                    if t.technician
                    else "Unassigned"
                ),
                t.priority,
                t.status,
                (
                    t.created_at.isoformat()
                    if t.created_at
                    else ""
                ),
                (
                    t.resolved_at.isoformat()
                    if t.resolved_at
                    else ""
                ),
                (
                    t.closed_at.isoformat()
                    if t.closed_at
                    else ""
                )
            ])

        resp = make_response(
            out.getvalue()
        )

        resp.headers[
            "Content-Type"
        ] = "text/csv; charset=utf-8"

        resp.headers[
            "Content-Disposition"
        ] = (
            "attachment; "
            "filename=mkdss_it_report.csv"
        )

        return resp


    @app.get("/reports/pdf")
    @roles("IT_MANAGER", "IT_TEAM_LEADER", "IT_TECHNICIAN", "SYSTEM_ADMINISTRATOR")
    def report_pdf():
        u = current_user()
        status = request.args.get("status", "").strip().upper()
        search = request.args.get("q", "").strip()
        q = accessible_ticket_query(u)
        if status in STATUSES:
            q = q.filter(Ticket.status == status)
        if search:
            q = q.filter(
                Ticket.ticket_no.ilike(f"%{search}%") |
                Ticket.subject.ilike(f"%{search}%")
            )
        rows = q.order_by(Ticket.created_at.desc()).all()
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            abort(500)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        y = height - 45
        c.setFont("Helvetica-Bold", 15)
        c.drawString(40, y, "MKDSS IT Helpdesk Report")
        y -= 18
        c.setFont("Helvetica", 9)
        c.drawString(40, y, f"Generated: {localtime(now(), '%Y-%m-%d %H:%M')}")
        y -= 24
        for t in rows:
            line = f"{t.ticket_no} | {t.status} | {t.priority} | {t.subject[:70]}"
            c.drawString(40, y, line)
            y -= 14
            if y < 45:
                c.showPage()
                y = height - 45
        c.save()
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name="mkdss_it_helpdesk_report.pdf", mimetype="application/pdf")

    # ============================================================
    # DAILY WORK REPORTS
    # ============================================================

    @app.route("/daily-reports/new", methods=["GET", "POST"])
    @roles("IT_MANAGER", "IT_TEAM_LEADER", "IT_TECHNICIAN", "SYSTEM_ADMINISTRATOR")
    def new_daily_report():
        u = current_user()
        if request.method == "POST":
            f = request.form
            raw_date = f.get("report_date", "").strip()
            summary = f.get("summary", "").strip()
            tickets_worked_on = f.get("tickets_worked_on", "").strip()
            challenges = f.get("challenges", "").strip()
            actions = f.get("actions", "").strip()
            pending_work = f.get("pending_work", "").strip()
            next_day_plan = f.get("next_day_plan", "").strip()
            remarks = f.get("remarks", "").strip()
            try:
                report_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                report_date = None
            if not report_date or not summary:
                flash("Report date and work summary are required.", "error")
            else:
                r = DailyReport(
                    report_date=report_date,
                    author_id=u.id,
                    activity=summary,
                    user_id=u.id,
                    tickets_worked_on=tickets_worked_on or None,
                    summary=summary,
                    challenges=challenges or None,
                    actions=actions or None,
                    pending_work=pending_work or None,
                    next_day_plan=next_day_plan or None,
                    remarks=remarks or None
                )
                db.session.add(r)
                db.session.commit()
                log("DAILY_REPORT_CREATED", "DailyReport", r.id)
                # Route the report to the correct reviewer based on the
                # submitter's role, while keeping the report permanently
                # owned by the submitting account via DailyReport.user_id.
                if u.role.name == "IT_TEAM_LEADER":
                    reviewer_roles = ("IT_MANAGER",)
                elif u.role.name == "IT_TECHNICIAN":
                    reviewer_roles = ("IT_TEAM_LEADER",)
                elif u.role.name == "SYSTEM_ADMINISTRATOR":
                    reviewer_roles = ("IT_MANAGER",)
                else:
                    reviewer_roles = ()

                for reviewer in User.query.join(Role).filter(
                    Role.name.in_(reviewer_roles), User.is_active.is_(True)
                ).all():
                    create_notification(
                        reviewer, "Daily work report submitted",
                        f"{u.full_name} submitted a daily work report for {report_date.isoformat()}.",
                        kind="DAILY_REPORT",
                        url=url_for("daily_report", report_id=r.id),
                        dedupe_key=f"DAILY_REPORT:{r.id}:{reviewer.id}"
                    )
                db.session.commit()
                flash("Daily work report submitted to the appropriate reviewer.", "success")
                if u.role.name == "SYSTEM_ADMINISTRATOR":
                    return redirect(url_for("dashboard"))
                return redirect(url_for("daily_reports", draft_cleared="1"))
        return render_template("daily_report_new.html", report_date=now().date())

    @app.get("/daily-reports")
    @roles(
        "IT_MANAGER",
        "IT_TEAM_LEADER",
        "IT_TECHNICIAN",
        "SYSTEM_ADMINISTRATOR"
    )
    def daily_reports():

        u = current_user()

        if u.role.name in ("IT_TECHNICIAN", "SYSTEM_ADMINISTRATOR"):

            # Technicians and System Administrators can review/export only
            # reports that belong to their own authenticated account.
            q = DailyReport.query.filter_by(
                user_id=u.id
            )

        elif u.role.name == "IT_TEAM_LEADER":

            q = (
                DailyReport.query
                .join(
                    User,
                    DailyReport.user_id == User.id
                )
                .join(
                    Role,
                    User.role_id == Role.id
                )
                .filter(
                    Role.name.in_(
                        (
                            "IT_TEAM_LEADER",
                            "IT_TECHNICIAN"
                        )
                    )
                )
            )

        else:

            # IT Manager can review all IT personnel reports,
            # including System Administrator reports.
            q = (
                DailyReport.query
                .join(
                    User,
                    DailyReport.user_id == User.id
                )
                .join(
                    Role,
                    User.role_id == Role.id
                )
                .filter(
                    Role.name.in_(
                        (
                            "IT_MANAGER",
                            "IT_TEAM_LEADER",
                            "IT_TECHNICIAN",
                            "SYSTEM_ADMINISTRATOR"
                        )
                    )
                )
            )

        rows = (
            q.order_by(
                DailyReport.report_date.desc(),
                DailyReport.created_at.desc()
            )
            .all()
        )

        return render_template(
            "daily_reports.html",
            reports=rows
        )


    @app.get("/daily-reports/<int:report_id>")
    @roles(
        "IT_MANAGER",
        "IT_TEAM_LEADER",
        "IT_TECHNICIAN",
        "SYSTEM_ADMINISTRATOR"
    )
    def daily_report(report_id):

        r = db.session.get(
            DailyReport,
            report_id
        )

        if not r:
            abort(404)

        u = current_user()

        if u.role.name == "IT_TECHNICIAN":

            if r.user_id != u.id:
                abort(403)

        elif u.role.name == "IT_TEAM_LEADER":

            report_owner = r.user

            if (
                not report_owner
                or report_owner.role.name
                not in (
                    "IT_TEAM_LEADER",
                    "IT_TECHNICIAN"
                )
            ):
                abort(403)

        elif u.role.name == "SYSTEM_ADMINISTRATOR":

            # System Administrator can view only their own submitted reports.
            if r.user_id != u.id:
                abort(403)

        # IT Manager can view all daily reports,
        # including SAdmin reports.

        return render_template(
            "daily_report.html",
            report=r
        )


    @app.get(
        "/daily-reports/<int:report_id>/csv"
    )
    @roles(
        "IT_MANAGER",
        "IT_TEAM_LEADER",
        "IT_TECHNICIAN",
        "SYSTEM_ADMINISTRATOR"
    )
    def daily_report_csv(report_id):

        r = db.session.get(
            DailyReport,
            report_id
        )

        if not r:
            abort(404)

        u = current_user()

        if u.role.name == "IT_TECHNICIAN":

            if r.user_id != u.id:
                abort(403)

        elif u.role.name == "IT_TEAM_LEADER":

            report_owner = r.user

            if (
                not report_owner
                or report_owner.role.name
                not in (
                    "IT_TEAM_LEADER",
                    "IT_TECHNICIAN"
                )
            ):
                abort(403)

        elif u.role.name == "SYSTEM_ADMINISTRATOR":

            # SAdmin can export only their own report.
            if r.user_id != u.id:
                abort(403)

        out = io.StringIO()

        w = csv.writer(out)

        w.writerow([
            "Report Date", "Prepared By", "Tickets Worked On", "Summary",
            "Challenges", "Actions", "Pending Work", "Next Day Plan", "Remarks"
        ])
        w.writerow([
            r.report_date.isoformat(),
            r.user.full_name if r.user else "Deleted User",
            r.tickets_worked_on or "",
            r.summary,
            r.challenges or "",
            r.actions or "",
            r.pending_work or "",
            r.next_day_plan or "",
            r.remarks or ""
        ])

        resp = make_response(
            out.getvalue()
        )

        resp.headers[
            "Content-Type"
        ] = "text/csv; charset=utf-8"

        resp.headers[
            "Content-Disposition"
        ] = (
            f"attachment; "
            f"filename=daily_report_{r.id}.csv"
        )

        return resp


    @app.get(
        "/daily-reports/<int:report_id>/pdf"
    )
    @roles(
        "IT_MANAGER",
        "IT_TEAM_LEADER",
        "IT_TECHNICIAN",
        "SYSTEM_ADMINISTRATOR"
    )
    def daily_report_pdf(report_id):

        r = db.session.get(
            DailyReport,
            report_id
        )

        if not r:
            abort(404)

        u = current_user()

        if u.role.name == "IT_TECHNICIAN":

            if r.user_id != u.id:
                abort(403)

        elif u.role.name == "IT_TEAM_LEADER":

            report_owner = r.user

            if (
                not report_owner
                or report_owner.role.name
                not in (
                    "IT_TEAM_LEADER",
                    "IT_TECHNICIAN"
                )
            ):
                abort(403)

        elif u.role.name == "SYSTEM_ADMINISTRATOR":

            # SAdmin can export only their own report.
            if r.user_id != u.id:
                abort(403)

        try:

            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas

        except ImportError:

            flash(
                "PDF export requires the reportlab package.",
                "error"
            )

            if u.role.name == "SYSTEM_ADMINISTRATOR":

                return redirect(
                    url_for("dashboard")
                )

            return redirect(
                url_for(
                    "daily_report",
                    report_id=r.id
                )
            )

        buf = io.BytesIO()

        c = canvas.Canvas(
            buf,
            pagesize=A4
        )

        width, height = A4

        y = height - 50

        c.setFont(
            "Helvetica-Bold",
            16
        )

        c.drawString(
            50,
            y,
            "MKDSS IT Daily Work Report"
        )

        y -= 30

        def write_field(label, value):

            nonlocal y

            c.setFont(
                "Helvetica-Bold",
                10
            )

            c.drawString(
                50,
                y,
                label
            )

            y -= 15

            c.setFont(
                "Helvetica",
                10
            )

            for line in (
                value or ""
            ).splitlines() or [""]:

                c.drawString(
                    60,
                    y,
                    line[:110]
                )

                y -= 14

                if y < 55:

                    c.showPage()

                    y = height - 50

        write_field(
            "Report Date",
            r.report_date.isoformat()
        )

        write_field(
            "Prepared By",
            (
                r.user.full_name
                if r.user
                else "Deleted User"
            )
        )

        write_field("Tickets Worked On", r.tickets_worked_on or "")
        write_field("Summary", r.summary)
        write_field("Challenges",
            r.challenges or ""
        )

        write_field(
            "Actions",
            r.actions or ""
        )

        write_field("Next Day Plan", r.next_day_plan or "")
        write_field("Pending Work", r.pending_work or "")
        write_field("Remarks", r.remarks or "")

        c.save()

        buf.seek(0)

        return send_file(
            buf,
            as_attachment=True,
            download_name=(
                f"daily_report_{r.id}.pdf"
            ),
            mimetype="application/pdf"
        )


    # ============================================================
    # SYSTEM ADMINISTRATION
    # ============================================================

    @app.get("/admin/users")
    @roles("SYSTEM_ADMINISTRATOR")
    def users():

        visible_users = (
            User.query
            .filter(
                User.username
                != "__deleted_user__"
            )
            .order_by(User.full_name)
            .all()
        )

        return render_template(
            "users.html",
            users=visible_users,
            roles=(
                Role.query
                .order_by(Role.display_name)
                .all()
            ),
            departments=(
                Department.query
                .filter_by(is_active=True)
                .order_by(Department.name)
                .all()
            )
        )


    @app.post("/admin/users")
    @roles("SYSTEM_ADMINISTRATOR")
    def create_user():

        f = request.form

        username = (
            f.get("username", "")
            .strip()
            .lower()
        )

        email = (
            f.get("email", "")
            .strip()
            .lower()
        )

        eid = (
            f.get("employee_id", "")
            .strip()
        )

        role = Role.query.filter_by(
            name=f.get("role")
        ).first()

        if not all([
            f.get("full_name", "").strip(),
            username,
            email,
            eid,
            f.get("password", ""),
            role
        ]):

            flash(
                "Complete all required fields.",
                "error"
            )

        elif len(f["password"]) < 12:

            flash(
                "Password must contain at least 12 characters.",
                "error"
            )

        elif User.query.filter(
            (User.username == username)
            |
            (User.email == email)
            |
            (User.employee_id == eid)
        ).first():

            flash(
                "Username, email, or employee ID already exists.",
                "error"
            )

        else:

            u = User(
                full_name=f["full_name"].strip(),
                username=username,
                email=email,
                employee_id=eid,
                password_hash=generate_password_hash(
                    f["password"]
                ),
                role=role,
                department_id=(
                    int(f["department_id"])
                    if f.get("department_id")
                    else None
                ),
                must_change_password=True,
                is_active=True
            )

            db.session.add(u)

            db.session.commit()

            log(
                "USER_CREATED",
                "User",
                u.id,
                f"role={role.name}"
            )

            flash(
                "Account created.",
                "success"
            )

        return redirect(
            url_for("users")
        )


    @app.route(
        "/admin/users/<int:user_id>/edit",
        methods=["GET", "POST"]
    )
    @roles("SYSTEM_ADMINISTRATOR")
    def edit_user(user_id):

        u = db.session.get(
            User,
            user_id
        )

        if (
            not u
            or u.username == "__deleted_user__"
        ):
            abort(404)

        if request.method == "POST":

            f = request.form

            username = (
                f.get("username", "")
                .strip()
                .lower()
            )

            email = (
                f.get("email", "")
                .strip()
                .lower()
            )

            eid = (
                f.get("employee_id", "")
                .strip()
            )

            role = Role.query.filter_by(
                name=f.get("role")
            ).first()

            duplicate = (
                User.query
                .filter(User.id != u.id)
                .filter(
                    (User.username == username)
                    |
                    (User.email == email)
                    |
                    (User.employee_id == eid)
                )
                .first()
            )

            if not all([
                f.get("full_name", "").strip(),
                username,
                email,
                eid,
                role
            ]):

                flash(
                    "Complete all required fields.",
                    "error"
                )

            elif duplicate:

                flash(
                    "Username, email, or employee ID already exists.",
                    "error"
                )

            else:

                u.full_name = (
                    f["full_name"].strip()
                )

                u.username = username

                u.email = email

                u.employee_id = eid

                u.role = role

                u.department_id = (
                    int(f["department_id"])
                    if f.get("department_id")
                    else None
                )

                new_password = f.get(
                    "password",
                    ""
                )

                if new_password:

                    if len(new_password) < 12:

                        flash(
                            "New password must contain at least 12 characters.",
                            "error"
                        )

                        return redirect(
                            url_for(
                                "edit_user",
                                user_id=u.id
                            )
                        )

                    u.password_hash = (
                        generate_password_hash(
                            new_password
                        )
                    )

                    u.must_change_password = True

                db.session.commit()

                log(
                    "USER_UPDATED",
                    "User",
                    u.id,
                    f"role={role.name}"
                )

                flash(
                    "Account updated.",
                    "success"
                )

                return redirect(
                    url_for("users")
                )

        return render_template(
            "user_edit.html",
            user=u,
            roles=(
                Role.query
                .order_by(Role.display_name)
                .all()
            ),
            departments=(
                Department.query
                .filter_by(is_active=True)
                .order_by(Department.name)
                .all()
            )
        )


    @app.post(
        "/admin/users/<int:user_id>/toggle"
    )
    @roles("SYSTEM_ADMINISTRATOR")
    def toggle_user(user_id):

        u = db.session.get(
            User,
            user_id
        )

        if (
            not u
            or u.id == current_user().id
            or u.username == "__deleted_user__"
        ):
            abort(400)

        u.is_active = not u.is_active

        db.session.commit()

        log(
            "USER_STATUS_CHANGED",
            "User",
            u.id,
            str(u.is_active)
        )

        flash(
            "Account status updated.",
            "success"
        )

        return redirect(
            url_for("users")
        )


    def get_or_create_deleted_user():

        deleted = User.query.filter_by(
            username="__deleted_user__"
        ).first()

        if deleted:
            return deleted

        role = Role.query.filter_by(
            name="SYSTEM_ADMINISTRATOR"
        ).first()

        deleted = User(
            full_name="Deleted User",
            username="__deleted_user__",
            email="deleted-user@local.invalid",
            employee_id="__DELETED__",
            password_hash=generate_password_hash(
                secrets.token_hex(32)
            ),
            role=role,
            is_active=False,
            must_change_password=False
        )

        db.session.add(deleted)

        db.session.flush()

        return deleted


    @app.post(
        "/admin/users/<int:user_id>/delete"
    )
    @roles("SYSTEM_ADMINISTRATOR")
    def delete_user(user_id):

        u = db.session.get(
            User,
            user_id
        )

        if (
            not u
            or u.id == current_user().id
            or u.username == "__deleted_user__"
        ):
            abort(400)

        deleted = get_or_create_deleted_user()

        Ticket.query.filter_by(
            requester_id=u.id
        ).update(
            {
                Ticket.requester_id:
                deleted.id
            },
            synchronize_session=False
        )

        Ticket.query.filter_by(
            assigned_to_id=u.id
        ).update(
            {
                Ticket.assigned_to_id:
                deleted.id
            },
            synchronize_session=False
        )

        TicketActivity.query.filter_by(
            user_id=u.id
        ).update(
            {
                TicketActivity.user_id:
                deleted.id
            },
            synchronize_session=False
        )

        Attachment.query.filter_by(
            uploaded_by_id=u.id
        ).update(
            {
                Attachment.uploaded_by_id:
                deleted.id
            },
            synchronize_session=False
        )

        AuditLog.query.filter_by(
            user_id=u.id
        ).update(
            {
                AuditLog.user_id:
                deleted.id
            },
            synchronize_session=False
        )

        DailyReport.query.filter_by(user_id=u.id).update(
            {DailyReport.user_id: deleted.id, DailyReport.author_id: deleted.id},
            synchronize_session=False
        )
        Notification.query.filter_by(user_id=u.id).delete(synchronize_session=False)

        uid = u.id

        db.session.delete(u)

        db.session.commit()

        log(
            "USER_DELETED",
            "User",
            uid,
            "Account permanently removed; historical records retained as Deleted User."
        )

        flash(
            "User account deleted. Historical records were retained as Deleted User.",
            "success"
        )

        return redirect(
            url_for("users")
        )


    @app.route(
        "/admin/departments",
        methods=["GET", "POST"]
    )
    @roles("SYSTEM_ADMINISTRATOR")
    def departments():

        if request.method == "POST":

            name = (
                request.form
                .get("name", "")
                .strip()
            )

            if (
                name
                and not Department.query
                .filter_by(name=name)
                .first()
            ):

                d = Department(
                    name=name,
                    description=(
                        request.form
                        .get("description", "")
                        .strip()
                        or None
                    )
                )

                db.session.add(d)

                db.session.commit()

                log(
                    "DEPARTMENT_CREATED",
                    "Department",
                    d.id
                )

                flash(
                    "Department created.",
                    "success"
                )

            else:

                flash(
                    "Department name is required and must be unique.",
                    "error"
                )

        return render_template(
            "departments.html",
            departments=(
                Department.query
                .order_by(Department.name)
                .all()
            )
        )


    @app.route("/admin/departments/<int:department_id>/edit", methods=["GET", "POST"])
    @roles("SYSTEM_ADMINISTRATOR")
    def edit_department(department_id):
        d = db.session.get(Department, department_id)
        if not d:
            abort(404)
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip() or None
            if not name:
                flash("Department name is required.", "error")
            elif Department.query.filter(Department.id != d.id, Department.name == name).first():
                flash("Department name must be unique.", "error")
            else:
                d.name = name
                d.description = description
                db.session.commit()
                log("DEPARTMENT_UPDATED", "Department", d.id)
                flash("Department updated.", "success")
                return redirect(url_for("departments"))
        return render_template("department_edit.html", department=d)

    @app.post("/admin/departments/<int:department_id>/toggle")
    @roles("SYSTEM_ADMINISTRATOR")
    def toggle_department(department_id):
        d = db.session.get(Department, department_id)
        if not d:
            abort(404)
        d.is_active = not d.is_active
        db.session.commit()
        log("DEPARTMENT_STATUS_CHANGED", "Department", d.id, str(d.is_active))
        flash("Department status updated.", "success")
        return redirect(url_for("departments"))

    @app.route("/admin/categories", methods=["GET", "POST"])
    @roles("SYSTEM_ADMINISTRATOR")
    def categories():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            request_type = request.form.get("request_type", "IT_SUPPORT")
            if request_type not in REQUEST_TYPES:
                abort(400)
            if not name:
                flash("Category name is required.", "error")
            elif Category.query.filter_by(name=name).first():
                flash("Category name must be unique.", "error")
            else:
                c = Category(name=name, request_type=request_type, is_active=True)
                db.session.add(c)
                db.session.commit()
                log("CATEGORY_CREATED", "Category", c.id, f"type={request_type}")
                flash("Category created.", "success")
        return render_template(
            "categories.html",
            categories=Category.query.order_by(Category.request_type, Category.name).all()
        )

    @app.route("/admin/categories/<int:category_id>/edit", methods=["GET", "POST"])
    @roles("SYSTEM_ADMINISTRATOR")
    def edit_category(category_id):
        c = db.session.get(Category, category_id)
        if not c:
            abort(404)
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            request_type = request.form.get("request_type", "").strip()
            if not name or request_type not in REQUEST_TYPES:
                flash("Category name and request type are required.", "error")
            elif Category.query.filter(Category.id != c.id, Category.name == name).first():
                flash("Category name must be unique.", "error")
            else:
                c.name = name
                c.request_type = request_type
                db.session.commit()
                log("CATEGORY_UPDATED", "Category", c.id, f"type={request_type}")
                flash("Category updated.", "success")
                return redirect(url_for("categories"))
        return render_template("category_edit.html", category=c, request_type_labels=REQUEST_TYPE_LABELS)

    @app.post("/admin/categories/<int:category_id>/toggle")
    @roles("SYSTEM_ADMINISTRATOR")
    def toggle_category(category_id):
        c = db.session.get(Category, category_id)
        if not c:
            abort(404)
        c.is_active = not c.is_active
        db.session.commit()
        log("CATEGORY_STATUS_CHANGED", "Category", c.id, str(c.is_active))
        flash("Category status updated.", "success")
        return redirect(url_for("categories"))

    @app.post("/admin/categories/<int:category_id>/delete")
    @roles("SYSTEM_ADMINISTRATOR")
    def delete_category(category_id):
        c = db.session.get(Category, category_id)
        if not c:
            abort(404)
        if Ticket.query.filter_by(category_id=c.id).first():
            flash("This category is used by historical requests. Deactivate it instead of deleting it.", "error")
        else:
            db.session.delete(c)
            db.session.commit()
            log("CATEGORY_DELETED", "Category", category_id)
            flash("Category deleted.", "success")
        return redirect(url_for("categories"))

    @app.get("/audit")
    @roles(
        "SYSTEM_ADMINISTRATOR",
        "IT_MANAGER"
    )
    def audit():

        u = current_user()

        if u.role.name == "SYSTEM_ADMINISTRATOR":

            logs = (
                AuditLog.query
                .order_by(
                    AuditLog.created_at.desc()
                )
                .limit(1000)
                .all()
            )

            audit_scope = (
                "All system activity by all users"
            )

        else:

            it_roles = (
                "IT_MANAGER",
                "IT_TEAM_LEADER",
                "IT_TECHNICIAN"
            )

            logs = (
                AuditLog.query
                .join(
                    User,
                    AuditLog.user_id == User.id
                )
                .join(
                    Role,
                    User.role_id == Role.id
                )
                .filter(
                    Role.name.in_(it_roles)
                )
                .order_by(
                    AuditLog.created_at.desc()
                )
                .limit(1000)
                .all()
            )

            audit_scope = (
                "IT team activity only"
            )

        return render_template(
            "audit.html",
            logs=logs,
            audit_scope=audit_scope
        )


    @app.route(
        "/profile/password",
        methods=["GET", "POST"]
    )
    @login_required
    def change_password():

        u = current_user()

        if request.method == "POST":

            old = request.form.get(
                "current_password",
                ""
            )

            new = request.form.get(
                "new_password",
                ""
            )

            if not check_password_hash(
                u.password_hash,
                old
            ):

                flash(
                    "Current password is incorrect.",
                    "error"
                )

            elif len(new) < 12:

                flash(
                    "New password must contain at least 12 characters.",
                    "error"
                )

            elif new != request.form.get(
                "confirm_password",
                ""
            ):

                flash(
                    "Passwords do not match.",
                    "error"
                )

            else:

                u.password_hash = (
                    generate_password_hash(new)
                )

                u.must_change_password = False

                db.session.commit()

                log(
                    "PASSWORD_CHANGED",
                    "User",
                    u.id
                )

                flash(
                    "Password changed.",
                    "success"
                )

                return redirect(
                    url_for("dashboard")
                )

        return render_template(
            "password.html"
        )


    @app.errorhandler(403)
    def e403(e):

        return (
            render_template(
                "error.html",
                code=403,
                title="Access denied",
                message=(
                    "Your account is not authorized "
                    "for this action."
                )
            ),
            403
        )


    @app.errorhandler(500)
    def e500(e):
        db.session.rollback()
        app.logger.exception("Unhandled application error")
        return (
            render_template(
                "error.html",
                code=500,
                title="Server error",
                message="The request could not be completed. The error has been logged."
            ),
            500
        )

    @app.errorhandler(404)
    def e404(e):

        return (
            render_template(
                "error.html",
                code=404,
                title="Not found",
                message=(
                    "The requested resource was not found."
                )
            ),
            404
        )


app = create_app()


if __name__ == "__main__":

    import argparse

    p = argparse.ArgumentParser()

    p.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5001")))

    a = p.parse_args()

    app.run(
        host=a.host,
        port=a.port,
        debug=False
    )