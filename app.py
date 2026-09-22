from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import re
import calendar
import os
from functools import wraps

from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.secret_key = os.environ.get("WORKLAB_SECRET_KEY", "worklab-dev-change-this-key")


# =========================================================
# DATABASE
# =========================================================

DATABASE = "worklab.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


# =========================================================
# WORKLAB PRICES
# =========================================================

NORMAL_PRICES = {
    "Student": {
        "Half Day": 20,
        "Full Day": 30
    },

    "Normal": {
        "Half Day": 25,
        "Full Day": 40
    }
}


SUBSCRIBER_PRICES = {
    "Student": {
        "Half Day": 10,
        "Full Day": 15
    },

    "Normal": {
        "Half Day": 15,
        "Full Day": 25
    }
}


SUBSCRIPTION_PRICES = {
    "Weekly": 50,
    "Monthly": 200
}


VALID_STATUS = [
    "Student",
    "Normal"
]


VALID_PLANS = [
    "Half Day",
    "Full Day"
]


VALID_SUBSCRIPTIONS = [
    "None",
    "Weekly",
    "Monthly"
]


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def add_one_month(date_value):

    year = date_value.year
    month = date_value.month + 1

    if month == 13:
        month = 1
        year += 1

    day = min(
        date_value.day,
        calendar.monthrange(year, month)[1]
    )

    return date_value.replace(
        year=year,
        month=month,
        day=day
    )


# =========================================================
# PHONE FUNCTIONS
# =========================================================

def clean_phone(phone):

    return re.sub(
        r"\D",
        "",
        phone
    )


def validate_phone(country_code, phone):

    digits = clean_phone(phone)

    # MOROCCO
    if country_code == "+212":

        # Allow:
        # 650618705
        # 0650618705

        if len(digits) == 10 and digits.startswith("0"):
            digits = digits[1:]

        if len(digits) != 9:
            return None

        if digits[0] not in ["5", "6", "7"]:
            return None

        return "+212" + digits

    # OTHER COUNTRIES
    if len(digits) < 6 or len(digits) > 14:
        return None

    return country_code + digits


# =========================================================
# EMAIL VALIDATION
# =========================================================

def validate_email(email):

    if not email:
        return True

    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

    return re.fullmatch(
        pattern,
        email
    ) is not None


# =========================================================
# CLIENT ID VALIDATION
# =========================================================

def validate_client_id(client_id):

    pattern = r"^WL\d{4}$"

    return re.fullmatch(
        pattern,
        client_id
    ) is not None



# =========================================================
# ADDITIONAL SERVICES
# =========================================================

@app.route("/services", methods=["GET", "POST"])
def additional_services():
    error = None
    success_items = None
    client = None
    total = 0

    if request.method == "POST":
        client_id = request.form.get("client_id", "").strip().upper()

        if not validate_client_id(client_id):
            error = "Please enter a valid Client ID, for example WL0001."
            return render_template(
                "additional_services.html",
                error=error,
                client=None,
                success_items=None,
                total=0
            )

        connection = get_db_connection()

        client = connection.execute(
            "SELECT * FROM clients WHERE client_id = ?",
            (client_id,)
        ).fetchone()

        if not client:
            connection.close()
            error = "Client ID not found."
            return render_template(
                "additional_services.html",
                error=error,
                client=None,
                success_items=None,
                total=0
            )

        service_fields = {
            "Drink": "drink_price",
            "Snack": "snack_price",
            "PS5": "ps5_price",
            "Printing": "printing_price"
        }

        selected_services = []

        for service_name, field_name in service_fields.items():
            price_text = request.form.get(field_name, "").strip()

            if not price_text:
                continue

            try:
                price = float(price_text)
            except ValueError:
                connection.close()
                error = f"Invalid price for {service_name}."
                return render_template(
                    "additional_services.html",
                    error=error,
                    client=client,
                    success_items=None,
                    total=0
                )

            if price <= 0:
                connection.close()
                error = f"The price for {service_name} must be greater than 0."
                return render_template(
                    "additional_services.html",
                    error=error,
                    client=client,
                    success_items=None,
                    total=0
                )

            selected_services.append((service_name, price))

        if not selected_services:
            connection.close()
            error = "Please enter a price for at least one additional service."
            return render_template(
                "additional_services.html",
                error=error,
                client=client,
                success_items=None,
                total=0
            )

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            for service_name, price in selected_services:
                payment_cursor = connection.execute(
                    """
                    INSERT INTO payments
                    (client_id, payment_date, payment_type, amount)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        client_id,
                        now_text,
                        "Additional Service",
                        price
                    )
                )

                payment_id = payment_cursor.lastrowid

                connection.execute(
                    """
                    INSERT INTO additional_services
                    (client_id, service_type, price, service_date, payment_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        client_id,
                        service_name,
                        price,
                        now_text,
                        payment_id
                    )
                )

            connection.commit()

        except Exception as error_exception:
            connection.rollback()
            connection.close()
            error = f"Could not save additional services: {error_exception}"
            return render_template(
                "additional_services.html",
                error=error,
                client=client,
                success_items=None,
                total=0
            )

        connection.close()
        success_items = selected_services
        total = sum(price for _, price in selected_services)

    return render_template(
        "additional_services.html",
        error=error,
        client=client,
        success_items=success_items,
        total=total
    )


# =========================================================
# ADMIN / STAFF DATABASE
# =========================================================

DEFAULT_PERMISSIONS = {
    "view_clients",
    "view_visits",
    "view_subscriptions"
}

FINANCE_PERMISSIONS = {
    "view_finance",
    "manage_expenses"
}

ALL_PERMISSIONS = DEFAULT_PERMISSIONS | FINANCE_PERMISSIONS | {
    "manage_users"
}


def initialize_admin_database():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            permission TEXT NOT NULL,
            UNIQUE(user_id, permission),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_date TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expense_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            old_values TEXT,
            new_values TEXT,
            reason TEXT,
            performed_by INTEGER,
            action_date TEXT NOT NULL,
            FOREIGN KEY (performed_by) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS additional_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL,
            service_type TEXT NOT NULL,
            price REAL NOT NULL,
            service_date TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(client_id)
        )
    """)


    # =====================================================
    # ADD PAYMENT LINK TO ADDITIONAL SERVICES
    # =====================================================

    additional_service_columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(additional_services)"
        ).fetchall()
    }

    if "payment_id" not in additional_service_columns:

        connection.execute(
            """
            ALTER TABLE additional_services
            ADD COLUMN payment_id INTEGER
            """
        )


    # =====================================================
    # ADDITIONAL SERVICES AUDIT HISTORY
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            old_values TEXT,
            new_values TEXT,
            reason TEXT NOT NULL,
            performed_by INTEGER,
            action_date TEXT NOT NULL,
            FOREIGN KEY (performed_by) REFERENCES users(id)
        )
    """)


    connection.commit()
    connection.close()


initialize_admin_database()


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    connection = get_db_connection()
    user = connection.execute(
        "SELECT * FROM users WHERE id = ? AND is_active = 1",
        (user_id,)
    ).fetchone()
    connection.close()
    return user


def get_user_permissions(user_id):
    connection = get_db_connection()
    rows = connection.execute(
        "SELECT permission FROM user_permissions WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    connection.close()
    return {row["permission"] for row in rows}


def has_permission(permission):
    user = get_current_user()
    if not user:
        return False
    if user["role"] == "Admin":
        return True
    return permission in get_user_permissions(user["id"])


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


def permission_required(permission):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not get_current_user():
                return redirect(url_for("admin_login"))
            if not has_permission(permission):
                flash("You do not have permission to access this page.", "error")
                return redirect(url_for("admin_dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def resolve_period():
    period = request.args.get("period", "month")
    today = datetime.now().date()

    if period == "today":
        start = today
        end = today
    elif period == "7days":
        start = today - timedelta(days=6)
        end = today
    elif period == "year":
        start = today.replace(month=1, day=1)
        end = today
    elif period == "custom":
        try:
            start = datetime.strptime(request.args.get("start", ""), "%Y-%m-%d").date()
            end = datetime.strptime(request.args.get("end", ""), "%Y-%m-%d").date()
            if start > end:
                start, end = end, start
        except ValueError:
            start = today.replace(day=1)
            end = today
            period = "month"
    else:
        start = today.replace(day=1)
        end = today
        period = "month"

    return period, start, end


def resolve_profit_period():
    """
    Independent profitability period.
    Net Profit is intentionally calculated only for:
    - one complete/current calendar month
    - one complete/current calendar year
    """
    today = datetime.now().date()
    profit_mode = request.args.get("profit_mode", "month").strip().lower()

    if profit_mode == "year":
        try:
            profit_year = int(request.args.get("profit_year", today.year))
        except (TypeError, ValueError):
            profit_year = today.year

        profit_start = datetime(profit_year, 1, 1).date()
        profit_end = datetime(profit_year, 12, 31).date()
        profit_label = str(profit_year)
        profit_month = today.month

    else:
        profit_mode = "month"

        try:
            profit_year = int(request.args.get("profit_year", today.year))
        except (TypeError, ValueError):
            profit_year = today.year

        try:
            profit_month = int(request.args.get("profit_month", today.month))
        except (TypeError, ValueError):
            profit_month = today.month

        if profit_month < 1 or profit_month > 12:
            profit_month = today.month

        last_day = calendar.monthrange(profit_year, profit_month)[1]
        profit_start = datetime(profit_year, profit_month, 1).date()
        profit_end = datetime(profit_year, profit_month, last_day).date()
        profit_label = profit_start.strftime("%B %Y")

    return (
        profit_mode,
        profit_year,
        profit_month,
        profit_start,
        profit_end,
        profit_label
    )


def admin_context():
    user = get_current_user()
    permissions = ALL_PERMISSIONS if user and user["role"] == "Admin" else (
        get_user_permissions(user["id"]) if user else set()
    )
    return {
        "current_user": user,
        "permissions": permissions
    }


# =========================================================
# ADMIN AUTHENTICATION
# =========================================================

@app.route("/admin/setup", methods=["GET", "POST"])
def admin_setup():
    connection = get_db_connection()
    count = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
    connection.close()

    if count > 0:
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        if not full_name or not username or len(password) < 6:
            return render_template(
                "admin_setup.html",
                error="Complete all fields. Password must contain at least 6 characters."
            )

        connection = get_db_connection()
        try:
            connection.execute(
                """
                INSERT INTO users
                (username, password_hash, full_name, role, is_active, created_at)
                VALUES (?, ?, ?, 'Admin', 1, ?)
                """,
                (
                    username,
                    generate_password_hash(password),
                    full_name,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            )
            connection.commit()
        except sqlite3.IntegrityError:
            connection.close()
            return render_template("admin_setup.html", error="This username already exists.")
        connection.close()
        return redirect(url_for("admin_login"))

    return render_template("admin_setup.html", error=None)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    connection = get_db_connection()
    count = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
    connection.close()

    if count == 0:
        return redirect(url_for("admin_setup"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db_connection()
        user = connection.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username,)
        ).fetchone()
        connection.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("admin_dashboard"))

        error = "Invalid username or password."

    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@login_required
def admin_dashboard():
    # Global dashboard period:
    # controls activity, revenue and expenses.
    period, start_date, end_date = resolve_period()
    start_text = start_date.strftime("%Y-%m-%d")
    end_text = end_date.strftime("%Y-%m-%d")

    # Independent profitability period:
    # controls ONLY Net Profit.
    (
        profit_mode,
        profit_year,
        profit_month,
        profit_start,
        profit_end,
        profit_label
    ) = resolve_profit_period()

    profit_start_text = profit_start.strftime("%Y-%m-%d")
    profit_end_text = profit_end.strftime("%Y-%m-%d")

    connection = get_db_connection()

    total_clients = connection.execute(
        """
        SELECT COUNT(*) AS total FROM clients
        WHERE date(registration_date) BETWEEN ? AND ?
        """, (start_text, end_text)
    ).fetchone()["total"]

    visits = connection.execute(
        """
        SELECT COUNT(*) AS total FROM visits
        WHERE date(visit_date) BETWEEN ? AND ?
        """, (start_text, end_text)
    ).fetchone()["total"]

    active_subscriptions = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM subscriptions s
        INNER JOIN (
            SELECT client_id, MAX(id) AS max_id
            FROM subscriptions
            GROUP BY client_id
        ) latest ON latest.max_id = s.id
        WHERE datetime(s.end_date) > datetime('now', 'localtime')
        """
    ).fetchone()["total"]

    subscriptions_started = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM subscriptions
        WHERE date(start_date) BETWEEN ? AND ?
        """, (start_text, end_text)
    ).fetchone()["total"]

    expiring_soon = connection.execute(
        """
        SELECT s.*, c.full_name, c.phone, c.email
        FROM subscriptions s
        INNER JOIN clients c ON c.client_id = s.client_id
        INNER JOIN (
            SELECT client_id, MAX(id) AS max_id
            FROM subscriptions
            GROUP BY client_id
        ) latest ON latest.max_id = s.id
        WHERE datetime(s.end_date) > datetime('now', 'localtime')
          AND datetime(s.end_date) <= datetime('now', 'localtime', '+3 days')
        ORDER BY datetime(s.end_date) ASC
        """
    ).fetchall()

    recent_checkins = connection.execute(
        """
        SELECT v.*, c.full_name
        FROM visits v
        JOIN clients c ON c.client_id = v.client_id
        ORDER BY v.id DESC
        LIMIT 6
        """
    ).fetchall()

    finance_allowed = has_permission("view_finance")

    revenue = expenses = visit_revenue = subscription_revenue = additional_services_revenue = None
    profit_revenue = profit_expenses = net_profit = None

    if finance_allowed:
        # These follow the GLOBAL filter.
        revenue = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM payments
            WHERE date(payment_date) BETWEEN ? AND ?
            """, (start_text, end_text)
        ).fetchone()["total"]

        visit_revenue = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM payments
            WHERE payment_type = 'Visit'
              AND date(payment_date) BETWEEN ? AND ?
            """, (start_text, end_text)
        ).fetchone()["total"]

        subscription_revenue = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM payments
            WHERE payment_type = 'Subscription'
              AND date(payment_date) BETWEEN ? AND ?
            """, (start_text, end_text)
        ).fetchone()["total"]

        additional_services_revenue = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM payments
            WHERE payment_type = 'Additional Service'
              AND date(payment_date) BETWEEN ? AND ?
            """, (start_text, end_text)
        ).fetchone()["total"]

        expenses = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE date(expense_date) BETWEEN ? AND ?
            """, (start_text, end_text)
        ).fetchone()["total"]

        # These follow ONLY the independent Month/Year profitability selector.
        profit_revenue = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM payments
            WHERE date(payment_date) BETWEEN ? AND ?
            """, (profit_start_text, profit_end_text)
        ).fetchone()["total"]

        profit_expenses = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE date(expense_date) BETWEEN ? AND ?
            """, (profit_start_text, profit_end_text)
        ).fetchone()["total"]

        net_profit = profit_revenue - profit_expenses

    # Years offered by the selector.
    year_rows = connection.execute(
        """
        SELECT CAST(strftime('%Y', payment_date) AS INTEGER) AS y FROM payments
        UNION
        SELECT CAST(strftime('%Y', expense_date) AS INTEGER) AS y FROM expenses
        ORDER BY y DESC
        """
    ).fetchall()

    available_years = [row["y"] for row in year_rows if row["y"]]
    current_year = datetime.now().year
    if current_year not in available_years:
        available_years.insert(0, current_year)
    if profit_year not in available_years:
        available_years.append(profit_year)
        available_years = sorted(set(available_years), reverse=True)

    connection.close()

    return render_template(
        "admin_dashboard.html",
        **admin_context(),
        period=period,
        start_date=start_text,
        end_date=end_text,
        total_clients=total_clients,
        visits=visits,
        active_subscriptions=active_subscriptions,
        subscriptions_started=subscriptions_started,
        expiring_soon=expiring_soon,
        recent_checkins=recent_checkins,
        finance_allowed=finance_allowed,
        revenue=revenue,
        expenses=expenses,
        visit_revenue=visit_revenue,
        subscription_revenue=subscription_revenue,
        additional_services_revenue=additional_services_revenue,

        profit_mode=profit_mode,
        profit_year=profit_year,
        profit_month=profit_month,
        profit_start=profit_start_text,
        profit_end=profit_end_text,
        profit_label=profit_label,
        profit_revenue=profit_revenue,
        profit_expenses=profit_expenses,
        net_profit=net_profit,
        available_years=available_years
    )


# =========================================================
# ADMIN VISITS
# =========================================================

@app.route("/admin/visits")
@permission_required("view_visits")
def admin_visits():
    period, start_date, end_date = resolve_period()
    start_text = start_date.strftime("%Y-%m-%d")
    end_text = end_date.strftime("%Y-%m-%d")

    search = request.args.get("search", "").strip()
    plan_filter = request.args.get("plan", "All").strip()

    query = """
        SELECT v.*, c.full_name, c.status, c.phone
        FROM visits v
        JOIN clients c ON c.client_id = v.client_id
        WHERE date(v.visit_date) BETWEEN ? AND ?
    """
    params = [start_text, end_text]

    if search:
        query += """
            AND (
                c.client_id LIKE ?
                OR c.full_name LIKE ?
                OR c.phone LIKE ?
            )
        """
        value = f"%{search}%"
        params.extend([value, value, value])

    if plan_filter in {"Half Day", "Full Day"}:
        query += " AND v.plan = ?"
        params.append(plan_filter)

    query += " ORDER BY datetime(v.visit_date) DESC, v.id DESC"

    connection = get_db_connection()
    rows = connection.execute(query, params).fetchall()

    total_visits = len(rows)
    half_day_count = sum(1 for row in rows if row["plan"] == "Half Day")
    full_day_count = sum(1 for row in rows if row["plan"] == "Full Day")
    total_visit_amount = sum(float(row["price"]) for row in rows)

    connection.close()

    return render_template(
        "admin_visits.html",
        visits=rows,
        period=period,
        start_date=start_text,
        end_date=end_text,
        search=search,
        plan_filter=plan_filter,
        total_visits=total_visits,
        half_day_count=half_day_count,
        full_day_count=full_day_count,
        total_visit_amount=total_visit_amount,
        **admin_context()
    )


# =========================================================
# ADMIN SUBSCRIPTIONS
# =========================================================

@app.route("/admin/subscriptions")
@permission_required("view_subscriptions")
def admin_subscriptions():
    period, start_date, end_date = resolve_period()
    start_text = start_date.strftime("%Y-%m-%d")
    end_text = end_date.strftime("%Y-%m-%d")

    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "All").strip()
    type_filter = request.args.get("type", "All").strip()

    query = """
        SELECT s.*, c.full_name, c.phone,
        CASE
            WHEN datetime(s.end_date) > datetime('now', 'localtime')
             AND datetime(s.end_date) <= datetime('now', 'localtime', '+3 days')
                THEN 'Ending Soon'
            WHEN datetime(s.end_date) > datetime('now', 'localtime')
                THEN 'Active'
            ELSE 'Expired'
        END AS subscription_status
        FROM subscriptions s
        JOIN clients c ON c.client_id = s.client_id
        WHERE date(s.start_date) BETWEEN ? AND ?
    """
    params = [start_text, end_text]

    if search:
        query += """
            AND (
                c.client_id LIKE ?
                OR c.full_name LIKE ?
                OR c.phone LIKE ?
            )
        """
        value = f"%{search}%"
        params.extend([value, value, value])

    if type_filter in {"Weekly", "Monthly"}:
        query += " AND s.subscription_type = ?"
        params.append(type_filter)

    query += " ORDER BY datetime(s.start_date) DESC, s.id DESC"

    connection = get_db_connection()
    rows = connection.execute(query, params).fetchall()

    if status_filter in {"Active", "Ending Soon", "Expired"}:
        rows = [row for row in rows if row["subscription_status"] == status_filter]

    total_subscriptions = len(rows)
    active_count = sum(1 for row in rows if row["subscription_status"] == "Active")
    ending_soon_count = sum(1 for row in rows if row["subscription_status"] == "Ending Soon")
    expired_count = sum(1 for row in rows if row["subscription_status"] == "Expired")

    connection.close()

    return render_template(
        "admin_subscriptions.html",
        subscriptions=rows,
        period=period,
        start_date=start_text,
        end_date=end_text,
        search=search,
        status_filter=status_filter,
        type_filter=type_filter,
        total_subscriptions=total_subscriptions,
        active_count=active_count,
        ending_soon_count=ending_soon_count,
        expired_count=expired_count,
        **admin_context()
    )


# =========================================================
# ADMIN ADDITIONAL SERVICES
# =========================================================

@app.route("/admin/services")
@permission_required("view_finance")
def admin_services():
    period, start_date, end_date = resolve_period()
    start_text = start_date.strftime("%Y-%m-%d")
    end_text = end_date.strftime("%Y-%m-%d")

    search = request.args.get("search", "").strip()
    service_filter = request.args.get("service", "All").strip()

    query = """
        SELECT a.*, c.full_name, c.phone
        FROM additional_services a
        JOIN clients c ON c.client_id = a.client_id
        WHERE date(a.service_date) BETWEEN ? AND ?
    """
    params = [start_text, end_text]

    if search:
        query += """
            AND (
                c.client_id LIKE ?
                OR c.full_name LIKE ?
                OR c.phone LIKE ?
            )
        """
        value = f"%{search}%"
        params.extend([value, value, value])

    if service_filter in {"Drink", "Snack", "PS5", "Printing"}:
        query += " AND a.service_type = ?"
        params.append(service_filter)

    query += " ORDER BY datetime(a.service_date) DESC, a.id DESC"

    connection = get_db_connection()
    rows = connection.execute(query, params).fetchall()
    total_services_revenue = sum(float(row["price"]) for row in rows)
    connection.close()

    return render_template(
        "admin_services.html",
        services=rows,
        period=period,
        start_date=start_text,
        end_date=end_text,
        search=search,
        service_filter=service_filter,
        total_services_revenue=total_services_revenue,
        **admin_context()
    )

# =========================================================
# EDIT ADDITIONAL SERVICE
# =========================================================

@app.route(
    "/admin/services/<int:service_id>/edit",
    methods=["GET", "POST"]
)
@permission_required("view_finance")
def admin_edit_service(service_id):

    user = get_current_user()
    connection = get_db_connection()

    # =====================================================
    # FIND SERVICE
    # =====================================================

    service = connection.execute(
        """
        SELECT
            a.*,
            c.full_name,
            c.phone

        FROM additional_services a

        JOIN clients c
            ON c.client_id = a.client_id

        WHERE a.id = ?
        """,
        (service_id,)
    ).fetchone()


    if not service:

        connection.close()

        flash(
            "Additional service not found.",
            "error"
        )

        return redirect(
            url_for("admin_services")
        )


    # =====================================================
    # SAVE MODIFICATION
    # =====================================================

    if request.method == "POST":

        service_type = request.form.get(
            "service_type",
            ""
        ).strip()

        price_text = request.form.get(
            "price",
            ""
        ).strip()

        reason = request.form.get(
            "reason",
            ""
        ).strip()


        valid_services = {
            "Drink",
            "Snack",
            "PS5",
            "Printing"
        }


        # =================================================
        # VALIDATE PRICE
        # =================================================

        try:

            new_price = float(price_text)
            valid_price = new_price > 0

        except ValueError:

            valid_price = False


        if service_type not in valid_services:

            connection.close()

            flash(
                "Please select a valid service.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_edit_service",
                    service_id=service_id
                )
            )


        if not valid_price:

            connection.close()

            flash(
                "Please enter a valid price.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_edit_service",
                    service_id=service_id
                )
            )


        if not reason:

            connection.close()

            flash(
                "Please enter a reason for the modification.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_edit_service",
                    service_id=service_id
                )
            )


        # =================================================
        # SAVE OLD / NEW VALUES FOR AUDIT
        # =================================================

        old_values = (
            f"Service: {service['service_type']} | "
            f"Price: {float(service['price']):.2f} DH"
        )


        new_values = (
            f"Service: {service_type} | "
            f"Price: {new_price:.2f} DH"
        )


        try:

            # =================================================
            # UPDATE ADDITIONAL SERVICE
            # =================================================

            connection.execute(
                """
                UPDATE additional_services

                SET
                    service_type = ?,
                    price = ?

                WHERE id = ?
                """,
                (
                    service_type,
                    new_price,
                    service_id
                )
            )


            # =================================================
            # UPDATE ITS LINKED PAYMENT
            # =================================================

            if service["payment_id"]:

                connection.execute(
                    """
                    UPDATE payments

                    SET amount = ?

                    WHERE id = ?
                    AND payment_type = 'Additional Service'
                    """,
                    (
                        new_price,
                        service["payment_id"]
                    )
                )


            # =================================================
            # OLD SERVICES CREATED BEFORE payment_id
            # =================================================

            else:

                old_payment = connection.execute(
                    """
                    SELECT id

                    FROM payments

                    WHERE client_id = ?
                    AND payment_type = 'Additional Service'
                    AND payment_date = ?
                    AND amount = ?

                    ORDER BY id DESC

                    LIMIT 1
                    """,
                    (
                        service["client_id"],
                        service["service_date"],
                        service["price"]
                    )
                ).fetchone()


                if old_payment:

                    connection.execute(
                        """
                        UPDATE payments

                        SET amount = ?

                        WHERE id = ?
                        """,
                        (
                            new_price,
                            old_payment["id"]
                        )
                    )


                    connection.execute(
                        """
                        UPDATE additional_services

                        SET payment_id = ?

                        WHERE id = ?
                        """,
                        (
                            old_payment["id"],
                            service_id
                        )
                    )


            # =================================================
            # AUDIT HISTORY
            # =================================================

            connection.execute(
                """
                INSERT INTO service_audit
                (
                    service_id,
                    action_type,
                    old_values,
                    new_values,
                    reason,
                    performed_by,
                    action_date
                )

                VALUES
                (
                    ?,
                    'EDIT',
                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    service_id,
                    old_values,
                    new_values,
                    reason,
                    user["id"],
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            )


            connection.commit()


        except Exception as error:

            connection.rollback()
            connection.close()

            flash(
                f"Could not update service: {error}",
                "error"
            )

            return redirect(
                url_for(
                    "admin_edit_service",
                    service_id=service_id
                )
            )


        connection.close()


        flash(
            "Additional service and revenue updated successfully.",
            "success"
        )


        return redirect(
            url_for("admin_services")
        )


    # =====================================================
    # SHOW EDIT PAGE
    # =====================================================

    connection.close()


    return render_template(
        "admin_edit_service.html",
        service=service,
        **admin_context()
    )
# =========================================================
# ADMIN PAYMENTS
# =========================================================

@app.route("/admin/payments")
@permission_required("view_finance")
def admin_payments():
    period, start_date, end_date = resolve_period()
    start_text = start_date.strftime("%Y-%m-%d")
    end_text = end_date.strftime("%Y-%m-%d")

    search = request.args.get("search", "").strip()
    payment_type = request.args.get("type", "All").strip()

    query = """
        SELECT p.*, c.full_name, c.phone
        FROM payments p
        JOIN clients c ON c.client_id = p.client_id
        WHERE date(p.payment_date) BETWEEN ? AND ?
    """
    params = [start_text, end_text]

    if search:
        query += """
            AND (
                c.client_id LIKE ?
                OR c.full_name LIKE ?
                OR c.phone LIKE ?
            )
        """
        value = f"%{search}%"
        params.extend([value, value, value])

    if payment_type in {"Visit", "Subscription", "Additional Service"}:
        query += " AND p.payment_type = ?"
        params.append(payment_type)

    query += " ORDER BY datetime(p.payment_date) DESC, p.id DESC"

    connection = get_db_connection()
    rows = connection.execute(query, params).fetchall()

    total_payments = sum(float(row["amount"]) for row in rows)
    visit_revenue = sum(float(row["amount"]) for row in rows if row["payment_type"] == "Visit")
    subscription_revenue = sum(float(row["amount"]) for row in rows if row["payment_type"] == "Subscription")
    additional_services_revenue = sum(
        float(row["amount"]) for row in rows
        if row["payment_type"] == "Additional Service"
    )

    connection.close()

    return render_template(
        "admin_payments.html",
        payments=rows,
        period=period,
        start_date=start_text,
        end_date=end_text,
        search=search,
        payment_type=payment_type,
        total_payments=total_payments,
        visit_revenue=visit_revenue,
        subscription_revenue=subscription_revenue,
        additional_services_revenue=additional_services_revenue,
        **admin_context()
    )


# =========================================================
# ADMIN EXPENSES
# =========================================================

@app.route("/admin/expenses", methods=["GET", "POST"])
@permission_required("manage_expenses")
def admin_expenses():
    user = get_current_user()

    if request.method == "POST":
        expense_date = request.form.get("expense_date", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        amount_text = request.form.get("amount", "").strip()

        try:
            amount = float(amount_text)
            valid = amount > 0
        except ValueError:
            valid = False

        if not expense_date or not category or not valid:
            flash("Please enter a valid date, category and amount.", "error")
        else:
            connection = get_db_connection()
            connection.execute(
                """
                INSERT INTO expenses
                (expense_date, category, description, amount, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    expense_date,
                    category,
                    description,
                    amount,
                    user["id"],
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            )
            connection.commit()
            connection.close()
            flash("Expense added successfully.", "success")
            return redirect(url_for("admin_expenses"))

    period, start_date, end_date = resolve_period()
    start_text = start_date.strftime("%Y-%m-%d")
    end_text = end_date.strftime("%Y-%m-%d")
    category_filter = request.args.get("category", "All").strip()

    query = """
        SELECT e.*, u.full_name AS created_by_name
        FROM expenses e
        LEFT JOIN users u ON u.id = e.created_by
        WHERE date(e.expense_date) BETWEEN ? AND ?
    """
    params = [start_text, end_text]

    if category_filter != "All":
        query += " AND e.category = ?"
        params.append(category_filter)

    query += " ORDER BY date(e.expense_date) DESC, e.id DESC"

    connection = get_db_connection()
    rows = connection.execute(query, params).fetchall()
    total_expenses = sum(float(row["amount"]) for row in rows)

    audit_logs = connection.execute(
        """
        SELECT a.*, u.full_name AS performed_by_name
        FROM expense_audit a
        LEFT JOIN users u ON u.id = a.performed_by
        ORDER BY datetime(a.action_date) DESC, a.id DESC
        LIMIT 100
        """
    ).fetchall()

    connection.close()

    return render_template(
        "admin_expenses.html",
        expenses=rows,
        audit_logs=audit_logs,
        today=datetime.now().strftime("%Y-%m-%d"),
        period=period,
        start_date=start_text,
        end_date=end_text,
        category_filter=category_filter,
        total_expenses=total_expenses,
        **admin_context()
    )


# =========================================================
# EDIT / DELETE EXPENSES + AUDIT HISTORY
# =========================================================

EXPENSE_CATEGORIES = {
    "Rent",
    "Electricity",
    "Water",
    "Internet",
    "Drinks & Snacks",
    "Cleaning",
    "Equipment",
    "Maintenance",
    "Supplies",
    "Salaries",
    "Marketing",
    "Taxes & Fees",
    "Other"
}


def expense_snapshot(expense):
    return (
        f"Date: {expense['expense_date']} | "
        f"Category: {expense['category']} | "
        f"Description: {expense['description'] or '—'} | "
        f"Amount: {float(expense['amount']):.2f} DH"
    )


@app.route("/admin/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
@permission_required("manage_expenses")
def admin_edit_expense(expense_id):
    user = get_current_user()
    connection = get_db_connection()

    expense = connection.execute(
        "SELECT * FROM expenses WHERE id = ?",
        (expense_id,)
    ).fetchone()

    if not expense:
        connection.close()
        flash("Expense not found.", "error")
        return redirect(url_for("admin_expenses"))

    if request.method == "POST":
        expense_date = request.form.get("expense_date", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        amount_text = request.form.get("amount", "").strip()
        reason = request.form.get("reason", "").strip()

        try:
            datetime.strptime(expense_date, "%Y-%m-%d")
            valid_date = True
        except ValueError:
            valid_date = False

        try:
            amount = float(amount_text)
            valid_amount = amount > 0
        except ValueError:
            valid_amount = False

        if not valid_date or category not in EXPENSE_CATEGORIES or not valid_amount or not reason:
            connection.close()
            flash("Enter a valid date, category, amount and correction reason.", "error")
            return redirect(url_for("admin_edit_expense", expense_id=expense_id))

        old_values = expense_snapshot(expense)
        new_values = (
            f"Date: {expense_date} | "
            f"Category: {category} | "
            f"Description: {description or '—'} | "
            f"Amount: {amount:.2f} DH"
        )

        try:
            connection.execute(
                """
                UPDATE expenses
                SET expense_date = ?, category = ?, description = ?, amount = ?
                WHERE id = ?
                """,
                (expense_date, category, description, amount, expense_id)
            )

            connection.execute(
                """
                INSERT INTO expense_audit
                (expense_id, action_type, old_values, new_values, reason, performed_by, action_date)
                VALUES (?, 'EDIT', ?, ?, ?, ?, ?)
                """,
                (
                    expense_id,
                    old_values,
                    new_values,
                    reason,
                    user["id"],
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            )

            connection.commit()
            flash("Expense updated successfully.", "success")
        except Exception as error:
            connection.rollback()
            connection.close()
            flash(f"Could not update expense: {error}", "error")
            return redirect(url_for("admin_edit_expense", expense_id=expense_id))

        connection.close()
        return redirect(url_for("admin_expenses"))

    connection.close()
    return render_template(
        "admin_edit_expense.html",
        expense=expense,
        **admin_context()
    )


@app.route("/admin/expenses/<int:expense_id>/delete", methods=["POST"])
@permission_required("manage_expenses")
def admin_delete_expense(expense_id):
    user = get_current_user()
    reason = request.form.get("reason", "").strip()

    if not reason:
        flash("A reason is required before deleting an expense.", "error")
        return redirect(url_for("admin_expenses"))

    connection = get_db_connection()
    expense = connection.execute(
        "SELECT * FROM expenses WHERE id = ?",
        (expense_id,)
    ).fetchone()

    if not expense:
        connection.close()
        flash("Expense not found.", "error")
        return redirect(url_for("admin_expenses"))

    old_values = expense_snapshot(expense)

    try:
        # Keep the audit record even though the expense itself is removed.
        connection.execute(
            """
            INSERT INTO expense_audit
            (expense_id, action_type, old_values, new_values, reason, performed_by, action_date)
            VALUES (?, 'DELETE', ?, NULL, ?, ?, ?)
            """,
            (
                expense_id,
                old_values,
                reason,
                user["id"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )

        connection.execute(
            "DELETE FROM expenses WHERE id = ?",
            (expense_id,)
        )

        connection.commit()
        flash("Expense deleted. The deletion was saved in the audit history.", "success")
    except Exception as error:
        connection.rollback()
        flash(f"Could not delete expense: {error}", "error")

    connection.close()
    return redirect(url_for("admin_expenses"))


# =========================================================
# USERS & ACCESS - ADMIN ONLY
# =========================================================

@app.route("/admin/users", methods=["GET", "POST"])
@login_required
def admin_users():
    current = get_current_user()
    if current["role"] != "Admin":
        flash("Only an Admin can manage users.", "error")
        return redirect(url_for("admin_dashboard"))

    connection = get_db_connection()

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "Staff")
        selected_permissions = set(request.form.getlist("permissions")) & ALL_PERMISSIONS

        if not full_name or not username or len(password) < 6:
            connection.close()
            flash("Complete all user fields. Password must contain at least 6 characters.", "error")
            return redirect(url_for("admin_users"))

        if role not in {"Staff", "Manager"}:
            role = "Staff"

        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO users
                (username, password_hash, full_name, role, is_active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (
                    username,
                    generate_password_hash(password),
                    full_name,
                    role,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            )
            new_user_id = cursor.lastrowid

            for permission in selected_permissions:
                cursor.execute(
                    "INSERT INTO user_permissions (user_id, permission) VALUES (?, ?)",
                    (new_user_id, permission)
                )

            connection.commit()
            flash("User created successfully.", "success")
        except sqlite3.IntegrityError:
            connection.rollback()
            flash("This username already exists.", "error")

        connection.close()
        return redirect(url_for("admin_users"))

    users = connection.execute(
        "SELECT * FROM users ORDER BY id DESC"
    ).fetchall()

    permissions_by_user = {}
    for user in users:
        permissions_by_user[user["id"]] = {
            row["permission"] for row in connection.execute(
                "SELECT permission FROM user_permissions WHERE user_id = ?",
                (user["id"],)
            ).fetchall()
        }

    connection.close()

    return render_template(
        "admin_users.html",
        users=users,
        permissions_by_user=permissions_by_user,
        all_permissions=sorted(ALL_PERMISSIONS),
        **admin_context()
    )


@app.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@login_required
def admin_toggle_user(user_id):
    current = get_current_user()
    if current["role"] != "Admin" or current["id"] == user_id:
        return redirect(url_for("admin_users"))

    connection = get_db_connection()
    user = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        connection.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (0 if user["is_active"] else 1, user_id)
        )
        connection.commit()
    connection.close()
    return redirect(url_for("admin_users"))


# =========================================================
# STAFF ENTRY FROM PUBLIC HOME
# =========================================================

@app.route("/staff-access")
def staff_access():
    # The public-home staff entry always starts a fresh login.
    session.clear()
    return redirect(url_for("admin_login"))


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# NEW CLIENT REGISTRATION
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "GET":

        return render_template(
            "register.html",
            error=None,
            form_data={}
        )

    # =====================================================
    # GET FORM DATA
    # =====================================================

    full_name = request.form.get(
        "full_name",
        ""
    ).strip()

    country_code = request.form.get(
        "country_code",
        "+212"
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip()

    status = request.form.get(
        "status",
        ""
    ).strip()

    plan = request.form.get(
        "plan",
        ""
    ).strip()

    subscription = request.form.get(
        "subscription",
        ""
    ).strip()


    # =====================================================
    # KEEP FORM DATA IF ERROR
    # =====================================================

    form_data = {
        "full_name": full_name,
        "country_code": country_code,
        "phone": phone,
        "email": email,
        "status": status,
        "plan": plan,
        "subscription": subscription
    }


    # =====================================================
    # REQUIRED FIELDS
    # =====================================================

    if not full_name:

        return render_template(
            "register.html",
            error="Full Name is required.",
            form_data=form_data
        )


    if not phone:

        return render_template(
            "register.html",
            error="Phone number is required.",
            form_data=form_data
        )


    if status not in VALID_STATUS:

        return render_template(
            "register.html",
            error="Please select a valid client status.",
            form_data=form_data
        )


    if plan not in VALID_PLANS:

        return render_template(
            "register.html",
            error="Please select Half Day or Full Day.",
            form_data=form_data
        )


    if subscription not in VALID_SUBSCRIPTIONS:

        return render_template(
            "register.html",
            error="Please select a subscription option.",
            form_data=form_data
        )


    # =====================================================
    # EMAIL
    # =====================================================

    if not validate_email(email):

        return render_template(
            "register.html",
            error="Please enter a valid email address.",
            form_data=form_data
        )


    # =====================================================
    # PHONE
    # =====================================================

    formatted_phone = validate_phone(
        country_code,
        phone
    )


    if formatted_phone is None:

        if country_code == "+212":

            error_message = (
                "Invalid Moroccan phone number. "
                "Enter 9 digits, for example 650618705."
            )

        else:

            error_message = (
                "Invalid phone number."
            )


        return render_template(
            "register.html",
            error=error_message,
            form_data=form_data
        )


    # =====================================================
    # CALCULATE PRICES
    # =====================================================

    normal_visit_price = (
        NORMAL_PRICES[status][plan]
    )

    subscriber_visit_price = (
        SUBSCRIBER_PRICES[status][plan]
    )


    subscription_fee = 0


    if subscription == "None":

        visit_price = normal_visit_price

    else:

        visit_price = subscriber_visit_price

        subscription_fee = (
            SUBSCRIPTION_PRICES[
                subscription
            ]
        )


    total = (
        visit_price
        +
        subscription_fee
    )


    # =====================================================
    # CURRENT DATE
    # =====================================================

    now = datetime.now()

    registration_date = now.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


    connection = get_db_connection()

    cursor = connection.cursor()


    try:

        # =================================================
        # CREATE CLIENT
        # =================================================

        cursor.execute(
            """
            INSERT INTO clients
            (
                client_id,
                full_name,
                phone,
                email,
                status,
                registration_date
            )
            VALUES
            (
                NULL,
                ?,
                ?,
                ?,
                ?,
                ?
            )
            """,
            (
                full_name,
                formatted_phone,
                email,
                status,
                registration_date
            )
        )


        database_id = cursor.lastrowid


        client_id = (
            f"WL{database_id:04d}"
        )


        # =================================================
        # SAVE CLIENT ID
        # =================================================

        cursor.execute(
            """
            UPDATE clients
            SET client_id = ?
            WHERE id = ?
            """,
            (
                client_id,
                database_id
            )
        )


        # =================================================
        # SAVE VISIT
        # =================================================

        cursor.execute(
            """
            INSERT INTO visits
            (
                client_id,
                visit_date,
                plan,
                price
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?
            )
            """,
            (
                client_id,
                registration_date,
                plan,
                visit_price
            )
        )


        # =================================================
        # SAVE VISIT PAYMENT
        # =================================================

        cursor.execute(
            """
            INSERT INTO payments
            (
                client_id,
                payment_date,
                payment_type,
                amount
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?
            )
            """,
            (
                client_id,
                registration_date,
                "Visit",
                visit_price
            )
        )


        # =================================================
        # CREATE SUBSCRIPTION
        # =================================================

        if subscription != "None":

            subscription_start = now


            if subscription == "Weekly":

                subscription_end = (
                    subscription_start
                    +
                    timedelta(days=7)
                )

            else:

                subscription_end = (
                    add_one_month(
                        subscription_start
                    )
                )


            start_date = (
                subscription_start.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )


            end_date = (
                subscription_end.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )


            # SAVE SUBSCRIPTION

            cursor.execute(
                """
                INSERT INTO subscriptions
                (
                    client_id,
                    subscription_type,
                    start_date,
                    end_date,
                    price
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    client_id,
                    subscription,
                    start_date,
                    end_date,
                    subscription_fee
                )
            )


            # SAVE SUBSCRIPTION PAYMENT

            cursor.execute(
                """
                INSERT INTO payments
                (
                    client_id,
                    payment_date,
                    payment_type,
                    amount
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    client_id,
                    registration_date,
                    "Subscription",
                    subscription_fee
                )
            )


        # =================================================
        # SAVE EVERYTHING
        # =================================================

        connection.commit()


    except Exception as error:

        connection.rollback()

        connection.close()

        return (
            "An error occurred while registering "
            f"the client: {error}"
        )


    connection.close()


    # =====================================================
    # NEW PROFESSIONAL SUCCESS PAGE
    # =====================================================

    return render_template(
        "registration_success.html",
        client_id=client_id,
        full_name=full_name,
        status=status,
        plan=plan,
        subscription=subscription,
        total=total
    )


# =========================================================
# EXISTING CLIENT SEARCH
# =========================================================

@app.route(
    "/checkin",
    methods=["GET", "POST"]
)
def checkin():

    if request.method == "GET":

        return render_template(
            "checkin.html",
            error=None
        )


    client_id = request.form.get(
        "client_id",
        ""
    ).strip().upper()


    # =====================================================
    # CLIENT ID VALIDATION
    # =====================================================

    if not client_id:

        return render_template(
            "checkin.html",
            error="Please enter a Client ID."
        )


    if not validate_client_id(
        client_id
    ):

        return render_template(
            "checkin.html",
            error=(
                "Invalid Client ID. "
                "Please use the format WL0001."
            )
        )


    connection = get_db_connection()


    # =====================================================
    # FIND CLIENT
    # =====================================================

    client = connection.execute(
        """
        SELECT *
        FROM clients
        WHERE client_id = ?
        """,
        (
            client_id,
        )
    ).fetchone()


    if client is None:

        connection.close()

        return render_template(
            "checkin.html",
            error=(
                "Client not found. "
                "Please check the Client ID."
            )
        )


    # =====================================================
    # GET LATEST SUBSCRIPTION
    # =====================================================

    subscription = connection.execute(
        """
        SELECT *
        FROM subscriptions
        WHERE client_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            client_id,
        )
    ).fetchone()


    connection.close()


    # =====================================================
    # CHECK SUBSCRIPTION STATUS
    # =====================================================

    subscription_status = "none"


    if subscription:

        try:

            end_date = datetime.strptime(
                subscription["end_date"],
                "%Y-%m-%d %H:%M:%S"
            )


            if datetime.now() < end_date:

                subscription_status = (
                    "active"
                )

            else:

                subscription_status = (
                    "expired"
                )


        except ValueError:

            subscription_status = (
                "expired"
            )


    # =====================================================
    # PRICES
    # =====================================================

    client_status = client["status"]


    normal_half = (
        NORMAL_PRICES[
            client_status
        ]["Half Day"]
    )


    normal_full = (
        NORMAL_PRICES[
            client_status
        ]["Full Day"]
    )


    subscriber_half = (
        SUBSCRIBER_PRICES[
            client_status
        ]["Half Day"]
    )


    subscriber_full = (
        SUBSCRIBER_PRICES[
            client_status
        ]["Full Day"]
    )


    return render_template(
        "client_checkin.html",

        client=client,

        subscription=subscription,

        subscription_status=(
            subscription_status
        ),

        normal_half=normal_half,

        normal_full=normal_full,

        subscriber_half=(
            subscriber_half
        ),

        subscriber_full=(
            subscriber_full
        )
    )


# =========================================================
# PROCESS EXISTING CLIENT CHECK-IN
# =========================================================

@app.route(
    "/process-checkin",
    methods=["POST"]
)
def process_checkin():

    client_id = request.form.get(
        "client_id",
        ""
    ).strip().upper()


    plan = request.form.get(
        "plan",
        ""
    ).strip()


    subscription_choice = request.form.get(
        "subscription_choice",
        ""
    ).strip()


    # =====================================================
    # VALIDATE CLIENT ID
    # =====================================================

    if not validate_client_id(
        client_id
    ):

        return (
            "Invalid Client ID."
        )


    # =====================================================
    # VALIDATE PLAN
    # =====================================================

    if plan not in VALID_PLANS:

        return (
            "Invalid visit plan."
        )


    connection = get_db_connection()


    # =====================================================
    # FIND CLIENT
    # =====================================================

    client = connection.execute(
        """
        SELECT *
        FROM clients
        WHERE client_id = ?
        """,
        (
            client_id,
        )
    ).fetchone()


    if client is None:

        connection.close()

        return (
            "Client not found."
        )


    # =====================================================
    # GET LATEST SUBSCRIPTION
    # =====================================================

    latest_subscription = (
        connection.execute(
            """
            SELECT *
            FROM subscriptions
            WHERE client_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                client_id,
            )
        ).fetchone()
    )


    active_subscription = False


    if latest_subscription:

        try:

            end_date = datetime.strptime(
                latest_subscription[
                    "end_date"
                ],
                "%Y-%m-%d %H:%M:%S"
            )


            if datetime.now() < end_date:

                active_subscription = True


        except ValueError:

            active_subscription = False


    client_status = client["status"]


    now = datetime.now()


    visit_date = now.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


    new_subscription = None

    subscription_fee = 0


    # =====================================================
    # ACTIVE SUBSCRIPTION
    # =====================================================

    if active_subscription:

        visit_price = (
            SUBSCRIBER_PRICES[
                client_status
            ][plan]
        )


    # =====================================================
    # NO ACTIVE SUBSCRIPTION
    # =====================================================

    else:

        if subscription_choice == "None":

            visit_price = (
                NORMAL_PRICES[
                    client_status
                ][plan]
            )


        elif subscription_choice in [
            "Weekly",
            "Monthly"
        ]:

            new_subscription = (
                subscription_choice
            )


            subscription_fee = (
                SUBSCRIPTION_PRICES[
                    new_subscription
                ]
            )


            visit_price = (
                SUBSCRIBER_PRICES[
                    client_status
                ][plan]
            )


        else:

            connection.close()

            return (
                "Please choose a valid "
                "subscription option."
            )


    total = (
        visit_price
        +
        subscription_fee
    )


    cursor = connection.cursor()


    try:

        # =================================================
        # SAVE VISIT
        # =================================================

        cursor.execute(
            """
            INSERT INTO visits
            (
                client_id,
                visit_date,
                plan,
                price
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?
            )
            """,
            (
                client_id,
                visit_date,
                plan,
                visit_price
            )
        )


        # =================================================
        # SAVE VISIT PAYMENT
        # =================================================

        cursor.execute(
            """
            INSERT INTO payments
            (
                client_id,
                payment_date,
                payment_type,
                amount
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?
            )
            """,
            (
                client_id,
                visit_date,
                "Visit",
                visit_price
            )
        )


        # =================================================
        # NEW / RENEWED SUBSCRIPTION
        # =================================================

        if new_subscription:

            subscription_start = now


            if new_subscription == "Weekly":

                subscription_end = (
                    subscription_start
                    +
                    timedelta(days=7)
                )


            else:

                subscription_end = (
                    add_one_month(
                        subscription_start
                    )
                )


            start_date = (
                subscription_start.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )


            end_date = (
                subscription_end.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )


            cursor.execute(
                """
                INSERT INTO subscriptions
                (
                    client_id,
                    subscription_type,
                    start_date,
                    end_date,
                    price
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    client_id,
                    new_subscription,
                    start_date,
                    end_date,
                    subscription_fee
                )
            )


            # SUBSCRIPTION PAYMENT

            cursor.execute(
                """
                INSERT INTO payments
                (
                    client_id,
                    payment_date,
                    payment_type,
                    amount
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    client_id,
                    visit_date,
                    "Subscription",
                    subscription_fee
                )
            )


        connection.commit()


    except Exception as error:

        connection.rollback()

        connection.close()

        return (
            "An error occurred during "
            f"check-in: {error}"
        )


    connection.close()

    # =====================================================
    # CHECK-IN SUCCESS PAGE
    # =====================================================

    if new_subscription:
        subscription_display = new_subscription
    elif active_subscription:
        subscription_display = latest_subscription["subscription_type"]
    else:
        subscription_display = "None"

    return render_template(
        "checkin_success.html",
        client_id=client_id,
        full_name=client["full_name"],
        plan=plan,
        subscription_display=subscription_display,
        visit_price=visit_price,
        subscription_fee=subscription_fee,
        total=total
    )


# =========================================================
# CLIENTS MANAGEMENT
# =========================================================

@app.route("/clients")
@permission_required("view_clients")
def clients():

    search = request.args.get(
        "search",
        ""
    ).strip()


    connection = get_db_connection()


    # =====================================================
    # SEARCH CLIENTS
    # =====================================================

    if search:

        search_value = (
            f"%{search}%"
        )


        clients_list = (
            connection.execute(
                """
                SELECT *
                FROM clients

                WHERE client_id LIKE ?

                OR full_name LIKE ?

                OR phone LIKE ?

                ORDER BY id DESC
                """,
                (
                    search_value,
                    search_value,
                    search_value
                )
            ).fetchall()
        )


    else:

        clients_list = (
            connection.execute(
                """
                SELECT *
                FROM clients
                ORDER BY id DESC
                """
            ).fetchall()
        )


    # =====================================================
    # PREPARE CLIENT DATA
    # =====================================================

    clients_data = []


    for client in clients_list:

        latest_subscription = (
            connection.execute(
                """
                SELECT *
                FROM subscriptions

                WHERE client_id = ?

                ORDER BY id DESC

                LIMIT 1
                """,
                (
                    client["client_id"],
                )
            ).fetchone()
        )


        subscription_status = "None"

        subscription_type = "-"


        if latest_subscription:

            subscription_type = (
                latest_subscription[
                    "subscription_type"
                ]
            )


            try:

                end_date = datetime.strptime(
                    latest_subscription[
                        "end_date"
                    ],
                    "%Y-%m-%d %H:%M:%S"
                )


                if datetime.now() < end_date:

                    subscription_status = (
                        "Active"
                    )

                else:

                    subscription_status = (
                        "Expired"
                    )


            except ValueError:

                subscription_status = (
                    "Expired"
                )


        clients_data.append(
            {
                "client": client,

                "subscription_status":
                    subscription_status,

                "subscription_type":
                    subscription_type
            }
        )


    connection.close()


    return render_template(
        "clients.html",
        clients=clients_data,
        search=search,
        **admin_context()
    )

# =========================================================
# EDIT CLIENT
# =========================================================

@app.route(
    "/clients/<client_id>/edit",
    methods=["GET", "POST"]
)
@permission_required("view_clients")
def admin_edit_client(client_id):

    client_id = client_id.strip().upper()

    connection = get_db_connection()

    client = connection.execute(
        """
        SELECT *
        FROM clients
        WHERE client_id = ?
        """,
        (client_id,)
    ).fetchone()


    if not client:

        connection.close()

        flash(
            "Client not found.",
            "error"
        )

        return redirect(
            url_for("clients")
        )


    # =====================================================
    # SAVE MODIFICATIONS
    # =====================================================

    if request.method == "POST":

        full_name = request.form.get(
            "full_name",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        status = request.form.get(
            "status",
            ""
        ).strip()

        reason = request.form.get(
            "reason",
            ""
        ).strip()


        # =================================================
        # VALIDATION
        # =================================================

        if not full_name:

            connection.close()

            flash(
                "Full name is required.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_edit_client",
                    client_id=client_id
                )
            )


        if not phone:

            connection.close()

            flash(
                "Phone number is required.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_edit_client",
                    client_id=client_id
                )
            )


        if email and not validate_email(email):

            connection.close()

            flash(
                "Please enter a valid email address.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_edit_client",
                    client_id=client_id
                )
            )


        if status not in VALID_STATUS:

            connection.close()

            flash(
                "Invalid client status.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_edit_client",
                    client_id=client_id
                )
            )


        if not reason:

            connection.close()

            flash(
                "Please enter a reason for the modification.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_edit_client",
                    client_id=client_id
                )
            )


        # =================================================
        # UPDATE CLIENT
        # =================================================

        try:

            connection.execute(
                """
                UPDATE clients

                SET
                    full_name = ?,
                    phone = ?,
                    email = ?,
                    status = ?

                WHERE client_id = ?
                """,
                (
                    full_name,
                    phone,
                    email,
                    status,
                    client_id
                )
            )


            connection.commit()


        except Exception as error:

            connection.rollback()

            connection.close()

            flash(
                f"Could not update client: {error}",
                "error"
            )

            return redirect(
                url_for(
                    "admin_edit_client",
                    client_id=client_id
                )
            )


        connection.close()


        flash(
            "Client information updated successfully.",
            "success"
        )


        return redirect(
            url_for(
                "clients",
                search=client_id
            )
        )


    # =====================================================
    # OPEN EDIT PAGE
    # =====================================================

    connection.close()


    return render_template(
        "admin_edit_client.html",
        client=client,
        **admin_context()
    )
# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )