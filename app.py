
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify
)
from werkzeug.security import (
    generate_password_hash, check_password_hash
)
from functools import wraps
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY", "local-development-only-change-me"
)

DB_NAME = os.path.join(app.root_path, "medical.db")

# ================= DATABASE =================

def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def add_column(conn, table, column, definition):
    columns = {
        row["name"]
        for row in conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }
    if column not in columns:
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN "
            f"{column} {definition}"
        )

def init_db():
    with get_db() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                phone TEXT DEFAULT '',
                notifications INTEGER DEFAULT 1,
                dark_mode INTEGER DEFAULT 0
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL DEFAULT 0,
                stock INTEGER NOT NULL DEFAULT 0
            )
        """)

        extra_columns = {
            "generic_name": "TEXT DEFAULT ''",
            "company": "TEXT DEFAULT ''",
            "category": "TEXT DEFAULT ''",
            "batch": "TEXT DEFAULT ''",
            "expiry": "TEXT DEFAULT ''",
            "mrp": "REAL DEFAULT 0",
            "purchase_price": "REAL DEFAULT 0",
            "gst": "REAL DEFAULT 0",
            "hsn": "TEXT DEFAULT ''",
            "barcode": "TEXT DEFAULT ''",
            "rack": "TEXT DEFAULT ''",
            "supplier_id": "INTEGER"
        }

        for column, definition in extra_columns.items():
            add_column(
                conn, "medicines", column, definition
            )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                address TEXT DEFAULT '',
                gstin TEXT DEFAULT ''
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                address TEXT DEFAULT ''
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER,
                medicine_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                purchase_price REAL NOT NULL,
                total REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(supplier_id)
                    REFERENCES suppliers(id),
                FOREIGN KEY(medicine_id)
                    REFERENCES medicines(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer TEXT NOT NULL,
                total REAL NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                medicine_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                FOREIGN KEY(sale_id)
                    REFERENCES sales(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS shop_settings (
                id INTEGER PRIMARY KEY,
                shop_name TEXT NOT NULL,
                address TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                gstin TEXT DEFAULT ''
            )
        """)

        conn.execute("""
            INSERT OR IGNORE INTO shop_settings
            (id, shop_name, address, phone)
            VALUES (1, ?, ?, ?)
        """, (
            "SRI HARI MEDICAL",
            "BOALIA, BARAIBARH, PURBA MEDINIPUR",
            "9933153104 / 7501023983"
        ))

# ================= HELPERS =================

def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({
                    "error": "Login required"
                }), 401
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper

def json_data():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}

def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError()
        return result.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid amount")

def positive_int(value, allow_zero=False):
    try:
        if isinstance(value, bool):
            raise ValueError()
        number = int(str(value))
        if str(number) != str(value).strip():
            raise ValueError()
        if number < 0 or (number == 0 and not allow_zero):
            raise ValueError()
        return number
    except (TypeError, ValueError):
        raise ValueError("Invalid quantity")

def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

def medicine_valid(data):
    name = str(data.get("name", "")).strip()
    price = money(data.get("price", 0))
    stock = positive_int(
        data.get("stock", 0), allow_zero=True
    )

    if not name or price <= 0:
        raise ValueError("Invalid medicine name or price")

    expiry = str(data.get("expiry", "")).strip()

    if expiry:
        try:
            date.fromisoformat(expiry)
        except ValueError:
            raise ValueError(
                "Expiry must be YYYY-MM-DD"
            )

    return {
        "name": name,
        "price": float(price),
        "stock": stock,
        "generic_name": str(
            data.get("generic_name", "")
        ).strip(),
        "company": str(
            data.get("company", "")
        ).strip(),
        "category": str(
            data.get("category", "")
        ).strip(),
        "batch": str(
            data.get("batch", "")
        ).strip(),
        "expiry": expiry,
        "mrp": float(money(
            data.get("mrp", 0)
        )),
        "purchase_price": float(money(
            data.get("purchase_price", 0)
        )),
        "gst": float(money(
            data.get("gst", 0)
        )),
        "hsn": str(data.get("hsn", "")).strip(),
        "barcode": str(
            data.get("barcode", "")
        ).strip(),
        "rack": str(data.get("rack", "")).strip()
    }

# ================= HOME =================

@app.route("/")
@login_required
def home():
    return render_template("index.html")

@app.route("/medicine")
@login_required
def medicine_page():
    return render_template("medicine.html")

@app.route("/dashboard")
@login_required
def dashboard():
    with get_db() as conn:
        total_medicines = conn.execute(
            "SELECT COUNT(*) FROM medicines"
        ).fetchone()[0]

        total_stock = conn.execute(
            "SELECT COALESCE(SUM(stock),0) FROM medicines"
        ).fetchone()[0]

        low_stock = conn.execute("""
            SELECT COUNT(*) FROM medicines
            WHERE stock < 10
        """).fetchone()[0]

        expired = conn.execute("""
            SELECT COUNT(*) FROM medicines
            WHERE expiry != ''
            AND expiry < ?
        """, (date.today().isoformat(),)).fetchone()[0]

        today_sales = conn.execute("""
            SELECT COALESCE(SUM(total),0) FROM sales
            WHERE DATE(created_at)=?
        """, (date.today().isoformat(),)).fetchone()[0]

    return jsonify({
        "total_medicines": total_medicines,
        "total_stock": total_stock,
        "low_stock": low_stock,
        "expired": expired,
        "today_sales": today_sales
    })

# ================= REGISTER =================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get(
            "name", ""
        ).strip()

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get(
            "password", ""
        )

        if not name or not email or len(password) < 8:
            return (
                "Enter valid name, email and "
                "password of at least 8 characters.",
                400
            )

        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO users
                    (name, email, password)
                    VALUES (?, ?, ?)
                """, (
                    name,
                    email,
                    generate_password_hash(password)
                ))

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            return "Email already registered", 409

    return render_template(
        "login.html", register=True
    )

# ================= LOGIN =================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get(
            "password", ""
        )

        with get_db() as conn:
            user = conn.execute("""
                SELECT * FROM users
                WHERE email=?
            """, (email,)).fetchone()

        if user and check_password_hash(
            user["password"], password
        ):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("home"))

        return "Invalid email or password", 401

    return render_template(
        "login.html", register=False
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ================= SETTINGS =================

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    user_id = session["user_id"]

    if request.method == "POST":
        name = request.form.get(
            "name", ""
        ).strip()

        email = request.form.get(
            "email", ""
        ).strip().lower()

        phone = request.form.get(
            "phone", ""
        ).strip()

        if not name or not email:
            return "Name and email required", 400

        notifications = int(
            request.form.get("notifications") == "on"
        )

        dark_mode = int(
            request.form.get("dark_mode") == "on"
        )

        try:
            with get_db() as conn:
                conn.execute("""
                    UPDATE users
                    SET name=?, email=?, phone=?,
                        notifications=?, dark_mode=?
                    WHERE id=?
                """, (
                    name, email, phone,
                    notifications, dark_mode, user_id
                ))

            session["user_name"] = name
            return redirect(url_for("settings"))

        except sqlite3.IntegrityError:
            return "Email already in use", 409

    with get_db() as conn:
        user = conn.execute("""
            SELECT * FROM users WHERE id=?
        """, (user_id,)).fetchone()

    return render_template(
        "settings.html", user=user
    )

# ================= MEDICINES =================

@app.route("/api/medicines", methods=["GET"])
@login_required
def get_medicines():
    search = request.args.get(
        "search", ""
    ).strip()

    with get_db() as conn:
        if search:
            rows = conn.execute("""
                SELECT * FROM medicines
                WHERE name LIKE ?
                   OR company LIKE ?
                   OR generic_name LIKE ?
                   OR batch LIKE ?
                ORDER BY name
            """, tuple(
                ["%" + search + "%"] * 4
            )).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM medicines
                ORDER BY name
            """).fetchall()

    return jsonify([dict(row) for row in rows])

@app.route("/api/medicines", methods=["POST"])
@login_required
def add_medicine():
    try:
        item = medicine_valid(json_data())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    columns = list(item.keys())
    placeholders = ",".join(["?"] * len(columns))

    sql = (
        "INSERT INTO medicines ("
        + ",".join(columns)
        + ") VALUES ("
        + placeholders + ")"
    )

    with get_db() as conn:
        cursor = conn.execute(
            sql, tuple(item.values())
        )

    return jsonify({
        "message": "Medicine added",
        "id": cursor.lastrowid
    }), 201

@app.route(
    "/api/medicines/<int:medicine_id>",
    methods=["PUT"]
)
@login_required
def update_medicine(medicine_id):
    try:
        item = medicine_valid(json_data())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Stock changes here are intended for
    # manual inventory corrections.
    assignments = ",".join(
        f"{column}=?" for column in item
    )

    with get_db() as conn:
        result = conn.execute(
            f"UPDATE medicines SET {assignments} "
            "WHERE id=?",
            (*item.values(), medicine_id)
        )

    if result.rowcount == 0:
        return jsonify({
            "error": "Medicine not found"
        }), 404

    return jsonify({
        "message": "Medicine updated"
    })

@app.route(
    "/api/medicines/<int:medicine_id>",
    methods=["DELETE"]
)
@login_required
def delete_medicine(medicine_id):
    try:
        with get_db() as conn:
            result = conn.execute("""
                DELETE FROM medicines WHERE id=?
            """, (medicine_id,))

        if result.rowcount == 0:
            return jsonify({
                "error": "Medicine not found"
            }), 404

        return jsonify({
            "message": "Medicine deleted"
        })

    except sqlite3.IntegrityError:
        return jsonify({
            "error": (
                "Medicine has purchase history "
                "and cannot be deleted"
            )
        }), 409

# ================= STOCK ALERTS =================

@app.route("/api/stock/low")
@login_required
def low_stock():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM medicines
            WHERE stock < 10
            ORDER BY stock
        """).fetchall()

    return jsonify([dict(r) for r in rows])

@app.route("/api/stock/expiry")
@login_required
def expiry_alert():
    today = date.today()
    cutoff = today + timedelta(days=90)

    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM medicines
            WHERE expiry != ''
            AND expiry <= ?
            ORDER BY expiry
        """, (cutoff.isoformat(),)).fetchall()

    return jsonify({
        "today": today.isoformat(),
        "medicines": [dict(r) for r in rows]
    })

# ================= SUPPLIERS =================

@app.route("/api/suppliers", methods=["GET", "POST"])
@login_required
def suppliers():
    if request.method == "GET":
        with get_db() as conn:
            rows = conn.execute("""
                SELECT * FROM suppliers ORDER BY name
            """).fetchall()

        return jsonify([dict(r) for r in rows])

    data = json_data()
    name = str(data.get("name", "")).strip()

    if not name:
        return jsonify({
            "error": "Supplier name required"
        }), 400

    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO suppliers
            (name, phone, address, gstin)
            VALUES (?, ?, ?, ?)
        """, (
            name,
            str(data.get("phone", "")),
            str(data.get("address", "")),
            str(data.get("gstin", ""))
        ))

    return jsonify({
        "message": "Supplier added",
        "id": cursor.lastrowid
    }), 201

# ================= CUSTOMERS =================

@app.route("/api/customers", methods=["GET", "POST"])
@login_required
def customers():
    if request.method == "GET":
        with get_db() as conn:
            rows = conn.execute("""
                SELECT * FROM customers ORDER BY name
            """).fetchall()

        return jsonify([dict(r) for r in rows])

    data = json_data()
    name = str(data.get("name", "")).strip()

    if not name:
        return jsonify({
            "error": "Customer name required"
        }), 400

    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO customers
            (name, phone, address)
            VALUES (?, ?, ?)
        """, (
            name,
            str(data.get("phone", "")),
            str(data.get("address", ""))
        ))

    return jsonify({
        "message": "Customer added",
        "id": cursor.lastrowid
    }), 201

# ================= PURCHASE =================

@app.route("/api/purchases", methods=["GET", "POST"])
@login_required
def purchases():
    if request.method == "GET":
        with get_db() as conn:
            rows = conn.execute("""
                SELECT p.*, m.name AS medicine_name,
                       s.name AS supplier_name
                FROM purchases p
                JOIN medicines m
                    ON p.medicine_id=m.id
                LEFT JOIN suppliers s
                    ON p.supplier_id=s.id
                ORDER BY p.id DESC
            """).fetchall()

        return jsonify([dict(r) for r in rows])

    data = json_data()

    try:
        medicine_id = positive_int(
            data.get("medicine_id")
        )
        quantity = positive_int(
            data.get("quantity")
        )
        purchase_price = money(
            data.get("purchase_price")
        )
        if purchase_price < 0:
            raise ValueError("Invalid purchase price")

        supplier_id = data.get("supplier_id")
        if supplier_id in ("", None):
            supplier_id = None
        else:
            supplier_id = positive_int(supplier_id)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    total = purchase_price * quantity
    conn = get_db()

    try:
        conn.execute("BEGIN IMMEDIATE")

        medicine = conn.execute("""
            SELECT id FROM medicines WHERE id=?
        """, (medicine_id,)).fetchone()

        if not medicine:
            raise ValueError("Medicine not found")

        cursor = conn.execute("""
            INSERT INTO purchases
            (supplier_id, medicine_id, quantity,
             purchase_price, total, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            supplier_id, medicine_id, quantity,
            float(purchase_price),
            float(total), now()
        ))

        conn.execute("""
            UPDATE medicines
            SET stock=stock+?,
                purchase_price=?
            WHERE id=?
        """, (
            quantity,
            float(purchase_price),
            medicine_id
        ))

        conn.commit()

        return jsonify({
            "message": "Purchase saved",
            "purchase_id": cursor.lastrowid,
            "total": float(total)
        }), 201

    except ValueError as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400

    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({
            "error": "Invalid supplier or medicine"
        }), 400

    finally:
        conn.close()

# ================= BILLING =================

@app.route("/api/bill", methods=["POST"])
@login_required
def create_bill():
    data = json_data()

    customer = str(
        data.get("customer", "")
    ).strip() or "Walk-in Customer"

    items = data.get("items", [])

    if not isinstance(items, list) or not items:
        return jsonify({
            "error": "Cart is empty"
        }), 400

    quantities = {}

    try:
        for item in items:
            mid = positive_int(item["id"])
            qty = positive_int(item["quantity"])

            quantities[mid] = (
                quantities.get(mid, 0) + qty
            )

    except (ValueError, TypeError, KeyError):
        return jsonify({
            "error": "Invalid cart"
        }), 400

    conn = get_db()

    try:
        conn.execute("BEGIN IMMEDIATE")

        bill_items = []
        total = Decimal("0.00")
        today = date.today().isoformat()

        for mid, qty in quantities.items():
            medicine = conn.execute("""
                SELECT * FROM medicines WHERE id=?
            """, (mid,)).fetchone()

            if not medicine:
                raise ValueError("Medicine not found")

            if medicine["stock"] < qty:
                raise ValueError(
                    "Insufficient stock: "
                    + medicine["name"]
                )

            expiry = medicine["expiry"]

            if expiry and expiry < today:
                raise ValueError(
                    "Expired medicine: "
                    + medicine["name"]
                )

            price = money(medicine["price"])
            total += price * qty

            bill_items.append({
                "id": mid,
                "name": medicine["name"],
                "price": float(price),
                "quantity": qty
            })

        cursor = conn.execute("""
            INSERT INTO sales
            (customer, total, created_at)
            VALUES (?, ?, ?)
        """, (
            customer,
            float(total),
            now()
        ))

        sale_id = cursor.lastrowid

        for item in bill_items:
            conn.execute("""
                INSERT INTO sale_items
                (sale_id, medicine_id, name,
                 price, quantity)
                VALUES (?, ?, ?, ?, ?)
            """, (
                sale_id,
                item["id"],
                item["name"],
                item["price"],
                item["quantity"]
            ))

            conn.execute("""
                UPDATE medicines
                SET stock=stock-?
                WHERE id=?
            """, (
                item["quantity"],
                item["id"]
            ))

        conn.commit()

        return jsonify({
            "message": "Bill created successfully",
            "bill_id": sale_id,
            "customer": customer,
            "items": bill_items,
            "total": float(total),
            "date": now()
        }), 201

    except ValueError as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400

    except sqlite3.Error:
        conn.rollback()
        return jsonify({
            "error": "Database error"
        }), 500

    finally:
        conn.close()

# ================= SALES HISTORY =================

@app.route("/api/sales")
@login_required
def sales_history():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM sales
            ORDER BY id DESC
        """).fetchall()

    return jsonify([dict(r) for r in rows])

@app.route("/api/sales/<int:sale_id>")
@login_required
def sale_details(sale_id):
    with get_db() as conn:
        sale = conn.execute("""
            SELECT * FROM sales WHERE id=?
        """, (sale_id,)).fetchone()

        if not sale:
            return jsonify({
                "error": "Bill not found"
            }), 404

        items = conn.execute("""
            SELECT * FROM sale_items
            WHERE sale_id=?
        """, (sale_id,)).fetchall()

    return jsonify({
        "sale": dict(sale),
        "items": [dict(r) for r in items]
    })

# ================= REPORTS =================

@app.route("/api/reports/daily")
@login_required
def daily_report():
    report_date = request.args.get(
        "date", date.today().isoformat()
    )

    try:
        date.fromisoformat(report_date)
    except ValueError:
        return jsonify({
            "error": "Invalid date"
        }), 400

    with get_db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS bills,
                   COALESCE(SUM(total),0) AS sales
            FROM sales
            WHERE DATE(created_at)=?
        """, (report_date,)).fetchone()

    return jsonify({
        "date": report_date,
        "bills": row["bills"],
        "sales": row["sales"]
    })

@app.route("/api/reports/monthly")
@login_required
def monthly_report():
    month = request.args.get(
        "month", date.today().strftime("%Y-%m")
    )

    try:
        datetime.strptime(month, "%Y-%m")
        if len(month) != 7:
            raise ValueError()
    except ValueError:
        return jsonify({
            "error": "Invalid month"
        }), 400

    with get_db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS bills,
                   COALESCE(SUM(total),0) AS sales
            FROM sales
            WHERE SUBSTR(created_at,1,7)=?
        """, (month,)).fetchone()

    return jsonify({
        "month": month,
        "bills": row["bills"],
        "sales": row["sales"]
    })

# ================= SHOP SETTINGS =================

@app.route("/api/shop", methods=["GET", "POST"])
@login_required
def shop_settings():
    if request.method == "GET":
        with get_db() as conn:
            row = conn.execute("""
                SELECT * FROM shop_settings
                WHERE id=1
            """).fetchone()

        return jsonify(dict(row))

    data = json_data()
    name = str(
        data.get("shop_name", "")
    ).strip()

    if not name:
        return jsonify({
            "error": "Shop name required"
        }), 400

    with get_db() as conn:
        conn.execute("""
            UPDATE shop_settings
            SET shop_name=?, address=?,
                phone=?, gstin=?
            WHERE id=1
        """, (
            name,
            str(data.get("address", "")),
            str(data.get("phone", "")),
            str(data.get("gstin", ""))
        ))

    return jsonify({
        "message": "Shop settings updated"
    })

# ================= START SERVER =================

if __name__ == "__main__":
    init_db()
    app.run(debug=True)