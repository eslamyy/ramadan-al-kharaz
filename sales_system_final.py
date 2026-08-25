
from flask import Flask, request, redirect, url_for, render_template_string, session, flash, send_file
import sqlite3
import os
import shutil
import tempfile
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DATABASE = "sales_full.db"


# =========================================================
# قاعدة البيانات
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin'
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        barcode TEXT UNIQUE,
        purchase_price REAL NOT NULL DEFAULT 0,
        sale_price REAL NOT NULL DEFAULT 0,
        quantity INTEGER NOT NULL DEFAULT 0,
        low_stock INTEGER NOT NULL DEFAULT 5,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        address TEXT,
        notes TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        address TEXT,
        notes TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        subtotal REAL NOT NULL,
        discount REAL NOT NULL DEFAULT 0,
        total REAL NOT NULL,
        paid REAL NOT NULL DEFAULT 0,
        balance REAL NOT NULL DEFAULT 0,
        payment_method TEXT NOT NULL DEFAULT 'نقدي',
        notes TEXT,
        sale_date TEXT NOT NULL,
        FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        product_id INTEGER,
        product_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        cost_price REAL NOT NULL DEFAULT 0,
        total REAL NOT NULL,
        FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
        FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id INTEGER,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_cost REAL NOT NULL,
        total REAL NOT NULL,
        purchase_date TEXT NOT NULL,
        notes TEXT,
        FOREIGN KEY(supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL,
        FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        amount REAL NOT NULL,
        expense_date TEXT NOT NULL,
        notes TEXT
    );

    CREATE TABLE IF NOT EXISTS returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        total REAL NOT NULL,
        return_date TEXT NOT NULL,
        notes TEXT,
        FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS return_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        return_id INTEGER NOT NULL,
        invoice_item_id INTEGER NOT NULL,
        product_id INTEGER,
        product_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        total REAL NOT NULL,
        FOREIGN KEY(return_id) REFERENCES returns(id) ON DELETE CASCADE,
        FOREIGN KEY(invoice_item_id) REFERENCES invoice_items(id) ON DELETE RESTRICT,
        FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS customer_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        payment_date TEXT NOT NULL,
        notes TEXT,
        received_by TEXT,
        FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS supplier_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        payment_date TEXT NOT NULL,
        notes TEXT,
        paid_by TEXT,
        FOREIGN KEY(supplier_id) REFERENCES suppliers(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        store_name TEXT NOT NULL DEFAULT 'اسم المحل',
        store_phone TEXT,
        store_address TEXT,
        tax_number TEXT,
        currency TEXT NOT NULL DEFAULT 'د.ل',
        receipt_size TEXT NOT NULL DEFAULT '80mm'
    );
    """)

    user = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if not user:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            ("admin", generate_password_hash("1234"), "المدير", "admin")
        )

    # ترقية قاعدة البيانات القديمة إلى V4 بدون حذف البيانات
    invoice_columns = [r[1] for r in conn.execute("PRAGMA table_info(invoices)").fetchall()]
    if "created_by" not in invoice_columns:
        conn.execute("ALTER TABLE invoices ADD COLUMN created_by TEXT")

    settings = conn.execute("SELECT id FROM settings WHERE id=1").fetchone()
    if not settings:
        conn.execute("""
            INSERT INTO settings
            (id, store_name, store_phone, store_address, tax_number, currency, receipt_size)
            VALUES (1, 'اسم المحل', '', '', '', 'د.ل', '80mm')
        """)

    conn.commit()
    conn.close()


# =========================================================
# أدوات عامة
# =========================================================

def get_settings():
    conn = get_db()
    row = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
    conn.close()
    return row


def money(value):
    try:
        value = float(value)
    except Exception:
        value = 0.0
    settings = get_settings()
    return f"{value:.2f} {settings['currency']}"


STYLE = """
<style>
*{box-sizing:border-box}
body{margin:0;font-family:Arial,Tahoma,sans-serif;background:#f3f4f6;color:#111827}
a{text-decoration:none}
.topbar{background:#111827;color:#fff;padding:14px 16px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:5}
.topbar .title{font-size:20px;font-weight:bold}
.topbar a{color:#fff}
.nav{display:flex;gap:8px;overflow-x:auto;background:#1f2937;padding:8px}
.nav a{white-space:nowrap;background:#374151;color:#fff;padding:9px 12px;border-radius:8px;font-size:14px}
.container{max-width:1150px;margin:auto;padding:16px}
.card{background:#fff;border-radius:14px;padding:16px;margin-bottom:16px;box-shadow:0 2px 10px rgba(0,0,0,.06)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.stat{background:#fff;border-radius:14px;padding:18px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,.06)}
.stat .n{font-size:26px;font-weight:bold;margin-top:8px}
input,select,textarea{width:100%;padding:11px;border:1px solid #d1d5db;border-radius:8px;margin:6px 0 12px;font-size:16px;background:#fff}
textarea{min-height:80px}
button,.btn{display:inline-block;border:0;border-radius:8px;padding:10px 14px;font-size:15px;cursor:pointer}
.btn-main,button{background:#111827;color:#fff}
.btn-green{background:#16a34a;color:#fff}
.btn-blue{background:#2563eb;color:#fff}
.btn-red{background:#dc2626;color:#fff}
.btn-gray{background:#6b7280;color:#fff}
.btn-orange{background:#ea580c;color:#fff}
.full{width:100%}
.actions{display:flex;gap:6px;flex-wrap:wrap}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:720px}
th{background:#111827;color:#fff;padding:10px}
td{border-bottom:1px solid #e5e7eb;padding:10px;text-align:center}
tr:hover td{background:#f9fafb}
.alert{padding:12px;border-radius:8px;margin-bottom:12px}
.alert-success{background:#dcfce7;color:#166534}
.alert-error{background:#fee2e2;color:#991b1b}
.alert-info{background:#dbeafe;color:#1e40af}
.badge{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px}
.badge-red{background:#fee2e2;color:#991b1b}
.badge-green{background:#dcfce7;color:#166534}
.total-box{font-size:22px;font-weight:bold;padding:12px;background:#f9fafb;border-radius:10px;margin:10px 0}
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.login-card{width:100%;max-width:420px;background:#fff;padding:24px;border-radius:16px;box-shadow:0 4px 18px rgba(0,0,0,.1)}
.small{font-size:13px;color:#6b7280}
.barcode-box{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:end}
h1,h2,h3{margin-top:0}
@media print{
  .no-print,.nav,.topbar .right{display:none!important}
  body{background:#fff}
  .container{max-width:none;padding:0}
  .card{box-shadow:none;border:0}
}
</style>
"""

NAV = """
<div class="topbar no-print">
  <div class="title">{{ store_name }}</div>
  <div class="right"><a href="/logout">تسجيل الخروج</a></div>
</div>
<div class="nav no-print">
  <a href="/">الرئيسية</a>
  <a href="/sales">المبيعات</a>
  <a href="/customers">العملاء</a>
  <a href="/customer-accounts">حسابات العملاء</a>
  <a href="/invoices">الفواتير</a>
  <a href="/returns">المرتجعات</a>
  {% if current_role == 'admin' %}
    <a href="/products">المنتجات</a>
    <a href="/stock">المخزون</a>
    <a href="/suppliers">الموردون</a>
    <a href="/supplier-accounts">حسابات الموردين</a>
    <a href="/purchases">المشتريات</a>
    <a href="/expenses">المصروفات</a>
    <a href="/reports">التقارير</a>
    <a href="/users">المستخدمون</a>
    <a href="/backup">النسخ الاحتياطي</a>
    <a href="/settings">الإعدادات</a>
  {% endif %}
</div>
"""


def page(title, body, **context):
    settings = get_settings()
    template = f"""
    <!doctype html>
    <html lang="ar" dir="rtl">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>{title}</title>
      {STYLE}
    </head>
    <body>
      {NAV}
      <div class="container">
        {{% with messages = get_flashed_messages(with_categories=true) %}}
          {{% for category, message in messages %}}
            <div class="alert {{% if category == 'success' %}}alert-success{{% elif category == 'error' %}}alert-error{{% else %}}alert-info{{% endif %}}">
              {{{{ message }}}}
            </div>
          {{% endfor %}}
        {{% endwith %}}
        {body}
      </div>
    </body>
    </html>
    """
    context["store_name"] = settings["store_name"]
    context["currency"] = settings["currency"]
    context["current_role"] = session.get("role", "")
    context["current_user"] = session.get("full_name", "")
    return render_template_string(template, **context)


def login_required():
    return "user_id" in session


@app.before_request
def protect_routes():
    allowed = {"login", "static"}

    if request.endpoint and request.endpoint not in allowed and not login_required():
        return redirect(url_for("login"))

    admin_only = {
        "products", "edit_product", "delete_product", "stock",
        "suppliers", "purchases", "expenses", "delete_expense",
        "reports", "settings", "users", "add_user",
        "delete_user", "reset_user_password",
        "backup_page", "download_backup", "restore_backup",
        "supplier_accounts", "supplier_statement", "supplier_payment"
    }

    if (
        request.endpoint in admin_only
        and session.get("role") != "admin"
    ):
        flash("هذه الصفحة متاحة للمدير فقط.", "error")
        return redirect(url_for("home"))


# =========================================================
# تسجيل الدخول
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            return redirect(url_for("home"))

        error = "اسم المستخدم أو كلمة المرور غير صحيحة."

    template = f"""
    <!doctype html>
    <html lang="ar" dir="rtl">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>تسجيل الدخول</title>
      {STYLE}
    </head>
    <body>
      <div class="login-wrap">
        <div class="login-card">
          <h2>تسجيل الدخول</h2>
          {{% if error %}}<div class="alert alert-error">{{{{ error }}}}</div>{{% endif %}}
          <form method="post">
            <label>اسم المستخدم</label>
            <input name="username" required>
            <label>كلمة المرور</label>
            <input type="password" name="password" required>
            <button class="full">دخول</button>
          </form>
          <p class="small">الافتراضي: admin / 1234</p>
        </div>
      </div>
    </body>
    </html>
    """
    return render_template_string(template, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))




# =========================================================
# النسخ الاحتياطي والاستعادة
# =========================================================

def validate_backup_database(path):
    """فحص أساسي للتأكد أن الملف قاعدة بيانات صالحة للمنظومة."""
    conn = None
    try:
        conn = sqlite3.connect(path)
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        required = {
            "users", "products", "customers", "suppliers",
            "invoices", "invoice_items", "purchases",
            "expenses", "settings"
        }

        return required.issubset(tables)
    except sqlite3.DatabaseError:
        return False
    finally:
        if conn is not None:
            conn.close()


@app.route("/backup")
def backup_page():
    body = """
    <div class="card">
      <h2>النسخ الاحتياطي والاستعادة</h2>

      <div class="alert alert-info">
        أنشئ نسخة احتياطية بشكل دوري واحفظها في مكان آمن خارج مجلد البرنامج.
      </div>

      <h3>1. إنشاء نسخة احتياطية</h3>
      <p>
        هذا الزر ينشئ نسخة آمنة من قاعدة البيانات الحالية ثم يرسلها إلى الهاتف للحفظ.
      </p>
      <a class="btn btn-green" href="/backup/download">
        تنزيل نسخة احتياطية
      </a>
    </div>

    <div class="card">
      <h3>2. استعادة نسخة سابقة</h3>

      <div class="alert alert-error">
        الاستعادة تستبدل قاعدة البيانات الحالية بالكامل.
        قبل الاستعادة سيتم إنشاء نسخة أمان تلقائية من البيانات الحالية.
      </div>

      <form method="post"
            action="/backup/restore"
            enctype="multipart/form-data"
            onsubmit="return confirm('هل أنت متأكد من استعادة النسخة؟ سيتم استبدال البيانات الحالية.');">

        <label>اختر ملف النسخة الاحتياطية</label>
        <input type="file" name="backup_file" accept=".db,.sqlite,.sqlite3" required>

        <button class="btn-orange">
          استعادة النسخة
        </button>
      </form>
    </div>
    """

    return page("النسخ الاحتياطي", body)


@app.route("/backup/download")
def download_backup():
    conn = None
    backup_conn = None

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_path = os.path.join(
            tempfile.gettempdir(),
            f"sales_backup_{timestamp}.db"
        )

        if os.path.exists(temp_path):
            os.remove(temp_path)

        # SQLite Backup API أفضل من نسخ الملف أثناء تشغيل المنظومة.
        conn = get_db()
        backup_conn = sqlite3.connect(temp_path)
        conn.backup(backup_conn)

        backup_conn.close()
        backup_conn = None
        conn.close()
        conn = None

        return send_file(
            temp_path,
            as_attachment=True,
            download_name=f"sales_backup_{timestamp}.db",
            mimetype="application/octet-stream"
        )

    except Exception as e:
        if backup_conn is not None:
            backup_conn.close()
        if conn is not None:
            conn.close()

        flash(f"تعذر إنشاء النسخة الاحتياطية: {e}", "error")
        return redirect(url_for("backup_page"))


@app.route("/backup/restore", methods=["POST"])
def restore_backup():
    uploaded = request.files.get("backup_file")

    if not uploaded or not uploaded.filename:
        flash("اختر ملف النسخة الاحتياطية أولًا.", "error")
        return redirect(url_for("backup_page"))

    temp_dir = tempfile.gettempdir()
    temp_uploaded = os.path.join(
        temp_dir,
        "sales_restore_candidate.db"
    )

    safety_copy = os.path.join(
        temp_dir,
        "sales_before_restore_" +
        datetime.now().strftime("%Y%m%d_%H%M%S") +
        ".db"
    )

    try:
        uploaded.save(temp_uploaded)

        if not validate_backup_database(temp_uploaded):
            raise Exception(
                "الملف المختار ليس نسخة احتياطية صالحة لهذه المنظومة."
            )

        # إنشاء نسخة أمان من البيانات الحالية قبل الاستعادة.
        current_conn = get_db()
        safety_conn = sqlite3.connect(safety_copy)
        current_conn.backup(safety_conn)
        safety_conn.close()
        current_conn.close()

        # استعادة البيانات باستخدام SQLite Backup API.
        source_conn = sqlite3.connect(temp_uploaded)
        destination_conn = sqlite3.connect(DATABASE)

        source_conn.backup(destination_conn)

        destination_conn.close()
        source_conn.close()

        # تشغيل أي ترقيات لازمة إذا كانت النسخة أقدم.
        init_db()

        # الجلسة الحالية قد تشير لمستخدم لم يعد موجودًا بعد الاستعادة.
        session.clear()

        flash(
            "تمت استعادة النسخة الاحتياطية بنجاح. سجل الدخول من جديد.",
            "success"
        )
        return redirect(url_for("login"))

    except Exception as e:
        flash(f"فشلت الاستعادة: {e}", "error")
        return redirect(url_for("backup_page"))

    finally:
        try:
            if os.path.exists(temp_uploaded):
                os.remove(temp_uploaded)
        except Exception:
            pass



# =========================================================
# حسابات العملاء والديون والتحصيلات
# =========================================================

@app.route("/customer-accounts")
def customer_accounts():
    conn = get_db()
    rows = conn.execute("""
        SELECT c.*,
               COALESCE((SELECT SUM(i.balance) FROM invoices i WHERE i.customer_id=c.id),0)
               AS invoice_debt,
               COALESCE((SELECT SUM(cp.amount) FROM customer_payments cp WHERE cp.customer_id=c.id),0)
               AS payments
        FROM customers c
        ORDER BY c.name
    """).fetchall()
    conn.close()

    body = """
    <div class="card">
      <h2>حسابات العملاء</h2>
      <div class="table-wrap">
        <table>
          <tr><th>العميل</th><th>الهاتف</th><th>الرصيد قبل التحصيلات</th><th>التحصيلات</th><th>الرصيد الحالي</th><th>كشف الحساب</th></tr>
          {% for c in rows %}
          {% set balance = [c.invoice_debt - c.payments, 0]|max %}
          <tr>
            <td>{{ c.name }}</td>
            <td>{{ c.phone or "" }}</td>
            <td>{{ "%.2f"|format(c.invoice_debt) }} {{ currency }}</td>
            <td>{{ "%.2f"|format(c.payments) }} {{ currency }}</td>
            <td><strong>{{ "%.2f"|format(balance) }} {{ currency }}</strong></td>
            <td><a class="btn btn-blue" href="/customer-statement/{{ c.id }}">فتح</a></td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>
    """
    return page("حسابات العملاء", body, rows=rows)


@app.route("/customer-statement/<int:customer_id>")
def customer_statement(customer_id):
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not customer:
        conn.close()
        return "العميل غير موجود", 404

    invoices_list = conn.execute("""
        SELECT * FROM invoices WHERE customer_id=? ORDER BY sale_date DESC
    """, (customer_id,)).fetchall()

    payments = conn.execute("""
        SELECT * FROM customer_payments WHERE customer_id=? ORDER BY payment_date DESC, id DESC
    """, (customer_id,)).fetchall()

    debt = sum(float(i["balance"]) for i in invoices_list)
    paid_later = sum(float(p["amount"]) for p in payments)
    balance = max(debt - paid_later, 0)
    conn.close()

    body = """
    <div class="card">
      <div class="actions no-print">
        <button onclick="window.print()" class="btn-green">طباعة كشف الحساب</button>
        <a href="/customer-accounts" class="btn btn-gray">رجوع</a>
      </div>
      <h2>كشف حساب: {{ customer.name }}</h2>
      <p>الهاتف: {{ customer.phone or "-" }}</p>
      <div class="grid">
        <div class="stat">إجمالي المتبقي بالفواتير<div class="n">{{ "%.2f"|format(debt) }} {{ currency }}</div></div>
        <div class="stat">التحصيلات اللاحقة<div class="n">{{ "%.2f"|format(paid_later) }} {{ currency }}</div></div>
        <div class="stat">الرصيد الحالي<div class="n">{{ "%.2f"|format(balance) }} {{ currency }}</div></div>
      </div>
    </div>

    <div class="card no-print">
      <h3>تسجيل تحصيل</h3>
      <form method="post" action="/customer-payment/{{ customer.id }}">
        <label>المبلغ</label>
        <input type="number" min="0.01" step="0.01" name="amount" required>
        <label>ملاحظات</label>
        <input name="notes" placeholder="مثال: دفعة نقدية">
        <button class="btn-green">تسجيل التحصيل</button>
      </form>
    </div>

    <div class="card">
      <h3>الفواتير الآجلة / المتبقية</h3>
      <div class="table-wrap"><table>
        <tr><th>الفاتورة</th><th>التاريخ</th><th>الإجمالي</th><th>المدفوع</th><th>المتبقي</th></tr>
        {% for i in invoices_list %}
        <tr>
          <td><a href="/invoice/{{ i.id }}">#{{ i.id }}</a></td>
          <td>{{ i.sale_date }}</td>
          <td>{{ "%.2f"|format(i.total) }} {{ currency }}</td>
          <td>{{ "%.2f"|format(i.paid) }} {{ currency }}</td>
          <td>{{ "%.2f"|format(i.balance) }} {{ currency }}</td>
        </tr>
        {% endfor %}
      </table></div>
    </div>

    <div class="card">
      <h3>سجل التحصيلات</h3>
      <div class="table-wrap"><table>
        <tr><th>التاريخ</th><th>المبلغ</th><th>الموظف</th><th>ملاحظات</th></tr>
        {% for p in payments %}
        <tr><td>{{ p.payment_date }}</td><td>{{ "%.2f"|format(p.amount) }} {{ currency }}</td><td>{{ p.received_by or "-" }}</td><td>{{ p.notes or "" }}</td></tr>
        {% endfor %}
      </table></div>
    </div>
    """
    return page("كشف حساب العميل", body, customer=customer, invoices_list=invoices_list,
                payments=payments, debt=debt, paid_later=paid_later, balance=balance)


@app.route("/customer-payment/<int:customer_id>", methods=["POST"])
def customer_payment(customer_id):
    conn = get_db()
    try:
        amount = float(request.form.get("amount", 0))
        if amount <= 0:
            raise ValueError
        debt = conn.execute("""
            SELECT COALESCE(SUM(balance),0) d FROM invoices WHERE customer_id=?
        """, (customer_id,)).fetchone()["d"]
        previous = conn.execute("""
            SELECT COALESCE(SUM(amount),0) p FROM customer_payments WHERE customer_id=?
        """, (customer_id,)).fetchone()["p"]
        outstanding = max(float(debt) - float(previous), 0)
        if amount > outstanding + 0.0001:
            raise Exception("المبلغ أكبر من الرصيد المستحق على العميل.")

        conn.execute("""
            INSERT INTO customer_payments(customer_id,amount,payment_date,notes,received_by)
            VALUES(?,?,?,?,?)
        """, (customer_id, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              request.form.get("notes","").strip(), session.get("full_name","")))
        conn.commit()
        flash("تم تسجيل التحصيل بنجاح.", "success")
    except Exception as e:
        conn.rollback()
        flash(str(e) if str(e) else "تعذر تسجيل التحصيل.", "error")
    finally:
        conn.close()
    return redirect(url_for("customer_statement", customer_id=customer_id))


# =========================================================
# حسابات الموردين والمدفوعات
# =========================================================

@app.route("/supplier-accounts")
def supplier_accounts():
    conn = get_db()
    rows = conn.execute("""
        SELECT s.*,
               COALESCE((SELECT SUM(p.total) FROM purchases p WHERE p.supplier_id=s.id),0) purchases_total,
               COALESCE((SELECT SUM(sp.amount) FROM supplier_payments sp WHERE sp.supplier_id=s.id),0) payments
        FROM suppliers s ORDER BY s.name
    """).fetchall()
    conn.close()
    body = """
    <div class="card"><h2>حسابات الموردين</h2>
      <div class="alert alert-info">تُعامل المشتريات المسجلة كمبالغ مستحقة للمورد، وتُخصم منها المدفوعات المسجلة.</div>
      <div class="table-wrap"><table>
      <tr><th>المورد</th><th>المشتريات</th><th>المدفوعات</th><th>المتبقي</th><th>كشف</th></tr>
      {% for s in rows %}
      <tr>
        <td>{{ s.name }}</td>
        <td>{{ "%.2f"|format(s.purchases_total) }} {{ currency }}</td>
        <td>{{ "%.2f"|format(s.payments) }} {{ currency }}</td>
        <td><strong>{{ "%.2f"|format([s.purchases_total-s.payments,0]|max) }} {{ currency }}</strong></td>
        <td><a class="btn btn-blue" href="/supplier-statement/{{ s.id }}">فتح</a></td>
      </tr>{% endfor %}
      </table></div>
    </div>
    """
    return page("حسابات الموردين", body, rows=rows)


@app.route("/supplier-statement/<int:supplier_id>")
def supplier_statement(supplier_id):
    conn = get_db()
    supplier = conn.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
    if not supplier:
        conn.close()
        return "المورد غير موجود", 404
    purchases_list = conn.execute("""
        SELECT p.*, pr.name product_name FROM purchases p
        JOIN products pr ON pr.id=p.product_id
        WHERE p.supplier_id=? ORDER BY p.purchase_date DESC
    """, (supplier_id,)).fetchall()
    payments = conn.execute("""
        SELECT * FROM supplier_payments WHERE supplier_id=? ORDER BY payment_date DESC,id DESC
    """, (supplier_id,)).fetchall()
    total_purchases = sum(float(x["total"]) for x in purchases_list)
    total_payments = sum(float(x["amount"]) for x in payments)
    balance = max(total_purchases-total_payments,0)
    conn.close()

    body = """
    <div class="card">
      <div class="actions no-print"><button onclick="window.print()" class="btn-green">طباعة كشف الحساب</button><a href="/supplier-accounts" class="btn btn-gray">رجوع</a></div>
      <h2>كشف حساب المورد: {{ supplier.name }}</h2>
      <div class="grid">
        <div class="stat">المشتريات<div class="n">{{ "%.2f"|format(total_purchases) }} {{ currency }}</div></div>
        <div class="stat">المدفوعات<div class="n">{{ "%.2f"|format(total_payments) }} {{ currency }}</div></div>
        <div class="stat">المتبقي<div class="n">{{ "%.2f"|format(balance) }} {{ currency }}</div></div>
      </div>
    </div>
    <div class="card no-print"><h3>تسجيل دفعة للمورد</h3>
      <form method="post" action="/supplier-payment/{{ supplier.id }}">
        <input type="number" min="0.01" step="0.01" name="amount" placeholder="المبلغ" required>
        <input name="notes" placeholder="ملاحظات">
        <button class="btn-green">تسجيل الدفعة</button>
      </form>
    </div>
    <div class="card"><h3>المشتريات</h3><div class="table-wrap"><table>
      <tr><th>التاريخ</th><th>المنتج</th><th>الكمية</th><th>الإجمالي</th></tr>
      {% for p in purchases_list %}<tr><td>{{ p.purchase_date }}</td><td>{{ p.product_name }}</td><td>{{ p.quantity }}</td><td>{{ "%.2f"|format(p.total) }} {{ currency }}</td></tr>{% endfor %}
    </table></div></div>
    <div class="card"><h3>المدفوعات</h3><div class="table-wrap"><table>
      <tr><th>التاريخ</th><th>المبلغ</th><th>الموظف</th><th>ملاحظات</th></tr>
      {% for p in payments %}<tr><td>{{ p.payment_date }}</td><td>{{ "%.2f"|format(p.amount) }} {{ currency }}</td><td>{{ p.paid_by or "-" }}</td><td>{{ p.notes or "" }}</td></tr>{% endfor %}
    </table></div></div>
    """
    return page("كشف حساب المورد", body, supplier=supplier, purchases_list=purchases_list,
                payments=payments,total_purchases=total_purchases,total_payments=total_payments,balance=balance)


@app.route("/supplier-payment/<int:supplier_id>", methods=["POST"])
def supplier_payment(supplier_id):
    conn = get_db()
    try:
        amount = float(request.form.get("amount",0))
        if amount <= 0: raise ValueError
        purchases_total = conn.execute("SELECT COALESCE(SUM(total),0) v FROM purchases WHERE supplier_id=?", (supplier_id,)).fetchone()["v"]
        payments_total = conn.execute("SELECT COALESCE(SUM(amount),0) v FROM supplier_payments WHERE supplier_id=?", (supplier_id,)).fetchone()["v"]
        outstanding = max(float(purchases_total)-float(payments_total),0)
        if amount > outstanding + 0.0001:
            raise Exception("المبلغ أكبر من الرصيد المستحق للمورد.")
        conn.execute("""
          INSERT INTO supplier_payments(supplier_id,amount,payment_date,notes,paid_by)
          VALUES(?,?,?,?,?)
        """,(supplier_id,amount,datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             request.form.get("notes","").strip(),session.get("full_name","")))
        conn.commit()
        flash("تم تسجيل دفعة المورد.", "success")
    except Exception as e:
        conn.rollback()
        flash(str(e) if str(e) else "تعذر تسجيل الدفعة.", "error")
    finally:
        conn.close()
    return redirect(url_for("supplier_statement", supplier_id=supplier_id))


# =========================================================
# المستخدمون والصلاحيات
# =========================================================

@app.route("/users")
def users():
    conn = get_db()
    items = conn.execute("""
        SELECT id, username, full_name, role
        FROM users
        ORDER BY id
    """).fetchall()
    conn.close()

    body = """
    <div class="card">
      <h2>إضافة مستخدم</h2>
      <form method="post" action="/users/add">
        <label>اسم الموظف</label>
        <input name="full_name" required>

        <label>اسم المستخدم</label>
        <input name="username" required>

        <label>كلمة المرور</label>
        <input type="password" name="password" minlength="4" required>

        <label>الصلاحية</label>
        <select name="role" required>
          <option value="cashier">كاشير</option>
          <option value="admin">مدير</option>
        </select>

        <button>إضافة المستخدم</button>
      </form>
    </div>

    <div class="card">
      <h2>المستخدمون</h2>
      <div class="table-wrap">
        <table>
          <tr>
            <th>#</th>
            <th>الاسم</th>
            <th>اسم المستخدم</th>
            <th>الصلاحية</th>
            <th>الإجراءات</th>
          </tr>

          {% for u in items %}
          <tr>
            <td>{{ u.id }}</td>
            <td>{{ u.full_name }}</td>
            <td>{{ u.username }}</td>
            <td>
              {% if u.role == 'admin' %}مدير{% else %}كاشير{% endif %}
            </td>
            <td class="actions">
              <form method="post" action="/users/password/{{ u.id }}" style="display:flex;gap:5px">
                <input type="password" name="password" placeholder="كلمة مرور جديدة" minlength="4" required style="margin:0">
                <button class="btn-blue">تغيير</button>
              </form>

              {% if u.id != session_user_id %}
              <form method="post" action="/users/delete/{{ u.id }}" onsubmit="return confirm('حذف المستخدم؟')">
                <button class="btn-red">حذف</button>
              </form>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>
    """

    return page(
        "المستخدمون",
        body,
        items=items,
        session_user_id=session.get("user_id")
    )


@app.route("/users/add", methods=["POST"])
def add_user():
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "cashier")

    if role not in {"admin", "cashier"}:
        role = "cashier"

    if not full_name or not username or len(password) < 4:
        flash("تحقق من بيانات المستخدم. كلمة المرور 4 أحرف/أرقام على الأقل.", "error")
        return redirect(url_for("users"))

    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO users
            (username, password_hash, full_name, role)
            VALUES (?, ?, ?, ?)
        """, (
            username,
            generate_password_hash(password),
            full_name,
            role
        ))
        conn.commit()
        flash("تمت إضافة المستخدم.", "success")
    except sqlite3.IntegrityError:
        flash("اسم المستخدم مستخدم بالفعل.", "error")
    finally:
        conn.close()

    return redirect(url_for("users"))


@app.route("/users/password/<int:user_id>", methods=["POST"])
def reset_user_password(user_id):
    password = request.form.get("password", "")

    if len(password) < 4:
        flash("كلمة المرور يجب أن تكون 4 أحرف/أرقام على الأقل.", "error")
        return redirect(url_for("users"))

    conn = get_db()
    conn.execute(
        "UPDATE users SET password_hash=? WHERE id=?",
        (generate_password_hash(password), user_id)
    )
    conn.commit()
    conn.close()

    flash("تم تغيير كلمة المرور.", "success")
    return redirect(url_for("users"))


@app.route("/users/delete/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("لا يمكنك حذف الحساب الذي تستخدمه الآن.", "error")
        return redirect(url_for("users"))

    conn = get_db()
    target = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not target:
        conn.close()
        flash("المستخدم غير موجود.", "error")
        return redirect(url_for("users"))

    if target["role"] == "admin":
        admins = conn.execute(
            "SELECT COUNT(*) c FROM users WHERE role='admin'"
        ).fetchone()["c"]

        if admins <= 1:
            conn.close()
            flash("لا يمكن حذف آخر حساب مدير.", "error")
            return redirect(url_for("users"))

    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    flash("تم حذف المستخدم.", "success")
    return redirect(url_for("users"))


# =========================================================
# الإعدادات وبيانات المحل
# =========================================================

@app.route("/settings", methods=["GET", "POST"])
def settings():
    conn = get_db()

    if request.method == "POST":
        store_name = request.form.get("store_name", "").strip() or "اسم المحل"
        store_phone = request.form.get("store_phone", "").strip()
        store_address = request.form.get("store_address", "").strip()
        tax_number = request.form.get("tax_number", "").strip()
        currency = request.form.get("currency", "").strip() or "د.ل"
        receipt_size = request.form.get("receipt_size", "80mm")

        conn.execute("""
            UPDATE settings
            SET store_name=?, store_phone=?, store_address=?,
                tax_number=?, currency=?, receipt_size=?
            WHERE id=1
        """, (
            store_name, store_phone, store_address,
            tax_number, currency, receipt_size
        ))
        conn.commit()
        conn.close()
        flash("تم حفظ بيانات المحل.", "success")
        return redirect(url_for("settings"))

    s = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
    conn.close()

    body = """
    <div class="card">
      <h2>بيانات المحل والفاتورة</h2>
      <form method="post">
        <label>اسم المحل</label>
        <input name="store_name" value="{{ s.store_name }}" required>

        <label>رقم الهاتف</label>
        <input name="store_phone" value="{{ s.store_phone or '' }}">

        <label>العنوان</label>
        <input name="store_address" value="{{ s.store_address or '' }}">

        <label>الرقم الضريبي / السجل</label>
        <input name="tax_number" value="{{ s.tax_number or '' }}">

        <label>العملة</label>
        <input name="currency" value="{{ s.currency or 'د.ل' }}">

        <label>مقاس ورق الفاتورة</label>
        <select name="receipt_size">
          <option value="80mm" {% if s.receipt_size == '80mm' %}selected{% endif %}>80 مم</option>
          <option value="58mm" {% if s.receipt_size == '58mm' %}selected{% endif %}>58 مم</option>
          <option value="A4" {% if s.receipt_size == 'A4' %}selected{% endif %}>A4</option>
        </select>

        <button>حفظ الإعدادات</button>
      </form>
    </div>
    """
    return page("الإعدادات", body, s=s)


# =========================================================
# الرئيسية
# =========================================================

@app.route("/")
def home():
    conn = get_db()

    product_count = conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
    customer_count = conn.execute("SELECT COUNT(*) c FROM customers").fetchone()["c"]
    today = datetime.now().strftime("%Y-%m-%d")

    today_sales = conn.execute(
        "SELECT COALESCE(SUM(total),0) s FROM invoices WHERE date(sale_date)=?",
        (today,)
    ).fetchone()["s"]

    low_stock = conn.execute(
        "SELECT COUNT(*) c FROM products WHERE quantity <= low_stock"
    ).fetchone()["c"]

    conn.close()

    body = """
    <h2>لوحة التحكم</h2>
    <p>مرحبًا {{ current_user }}</p>

    {% if current_role == 'admin' %}
    <div class="grid">
      <div class="stat">المنتجات<div class="n">{{ product_count }}</div></div>
      <div class="stat">العملاء<div class="n">{{ customer_count }}</div></div>
      <div class="stat">مبيعات اليوم<div class="n">{{ "%.2f"|format(today_sales) }} {{ currency }}</div></div>
      <div class="stat">مخزون منخفض<div class="n">{{ low_stock }}</div></div>
    </div>
    {% endif %}

    <div class="card" style="margin-top:16px">
      <h3>اختصارات</h3>
      <div class="grid">
        <a class="btn btn-green" href="/sales">فاتورة بيع جديدة</a>
        <a class="btn btn-blue" href="/invoices">الفواتير</a>
        <a class="btn btn-orange" href="/returns">المرتجعات</a>
        <a class="btn btn-gray" href="/customers">العملاء</a>
        {% if current_role == 'admin' %}
          <a class="btn btn-blue" href="/products">إدارة المنتجات</a>
          <a class="btn btn-gray" href="/reports">التقارير</a>
        {% endif %}
      </div>
    </div>
    """

    return page(
        "الرئيسية",
        body,
        product_count=product_count,
        customer_count=customer_count,
        today_sales=today_sales,
        low_stock=low_stock
    )


# =========================================================
# المنتجات + البحث
# =========================================================

@app.route("/products", methods=["GET", "POST"])
def products():
    conn = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        barcode = request.form.get("barcode", "").strip() or None

        try:
            purchase_price = float(request.form.get("purchase_price", 0) or 0)
            sale_price = float(request.form.get("sale_price", 0) or 0)
            quantity = int(request.form.get("quantity", 0) or 0)
            low_stock = int(request.form.get("low_stock", 5) or 5)
        except ValueError:
            conn.close()
            flash("تأكد من إدخال الأسعار والكميات بشكل صحيح.", "error")
            return redirect(url_for("products"))

        try:
            conn.execute("""
                INSERT INTO products
                (name, barcode, purchase_price, sale_price, quantity, low_stock, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                name, barcode, purchase_price, sale_price,
                quantity, low_stock, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            flash("تمت إضافة المنتج.", "success")
        except sqlite3.IntegrityError:
            flash("الباركود مستخدم لمنتج آخر.", "error")

        conn.close()
        return redirect(url_for("products"))

    q = request.args.get("q", "").strip()
    if q:
        like = f"%{q}%"
        items = conn.execute("""
            SELECT * FROM products
            WHERE name LIKE ? OR barcode LIKE ?
            ORDER BY id DESC
        """, (like, like)).fetchall()
    else:
        items = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()

    conn.close()

    body = """
    <div class="card">
      <h2>إضافة منتج</h2>
      <form method="post">
        <div class="grid">
          <div><label>اسم المنتج</label><input name="name" required></div>
          <div><label>الباركود</label><input name="barcode"></div>
          <div><label>سعر الشراء</label><input type="number" step="0.01" name="purchase_price" value="0"></div>
          <div><label>سعر البيع</label><input type="number" step="0.01" name="sale_price" value="0" required></div>
          <div><label>الكمية</label><input type="number" name="quantity" value="0"></div>
          <div><label>حد تنبيه المخزون</label><input type="number" name="low_stock" value="5"></div>
        </div>
        <button>حفظ المنتج</button>
      </form>
    </div>

    <div class="card">
      <h2>بحث المنتجات</h2>
      <form method="get">
        <div class="barcode-box">
          <div>
            <label>الاسم أو الباركود</label>
            <input name="q" value="{{ q }}" placeholder="اكتب الاسم أو امسح الباركود">
          </div>
          <button class="btn-blue">بحث</button>
        </div>
      </form>
    </div>

    <div class="card">
      <h2>المنتجات</h2>
      <div class="table-wrap">
        <table>
          <tr>
            <th>#</th><th>المنتج</th><th>الباركود</th><th>شراء</th><th>بيع</th><th>الكمية</th><th>إجراءات</th>
          </tr>
          {% for p in items %}
          <tr>
            <td>{{ p.id }}</td>
            <td>{{ p.name }}</td>
            <td>{{ p.barcode or "" }}</td>
            <td>{{ "%.2f"|format(p.purchase_price) }} {{ currency }}</td>
            <td>{{ "%.2f"|format(p.sale_price) }} {{ currency }}</td>
            <td>
              {{ p.quantity }}
              {% if p.quantity <= p.low_stock %}
                <span class="badge badge-red">منخفض</span>
              {% endif %}
            </td>
            <td class="actions">
              <a class="btn btn-blue" href="/products/edit/{{ p.id }}">تعديل</a>
              <a class="btn btn-red" href="/products/delete/{{ p.id }}" onclick="return confirm('حذف المنتج؟')">حذف</a>
            </td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>
    """
    return page("المنتجات", body, items=items, q=q)


@app.route("/products/edit/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()

    if not product:
        conn.close()
        return "المنتج غير موجود", 404

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            barcode = request.form.get("barcode", "").strip() or None
            purchase_price = float(request.form.get("purchase_price", 0) or 0)
            sale_price = float(request.form.get("sale_price", 0) or 0)
            quantity = int(request.form.get("quantity", 0) or 0)
            low_stock = int(request.form.get("low_stock", 5) or 5)

            conn.execute("""
                UPDATE products SET
                name=?, barcode=?, purchase_price=?, sale_price=?, quantity=?, low_stock=?
                WHERE id=?
            """, (
                name, barcode, purchase_price, sale_price,
                quantity, low_stock, product_id
            ))
            conn.commit()
            conn.close()
            flash("تم تعديل المنتج.", "success")
            return redirect(url_for("products"))

        except sqlite3.IntegrityError:
            flash("الباركود مستخدم لمنتج آخر.", "error")
        except ValueError:
            flash("بيانات رقمية غير صحيحة.", "error")

    conn.close()

    body = """
    <div class="card">
      <h2>تعديل المنتج</h2>
      <form method="post">
        <label>اسم المنتج</label>
        <input name="name" value="{{ product.name }}" required>

        <label>الباركود</label>
        <input name="barcode" value="{{ product.barcode or '' }}">

        <label>سعر الشراء</label>
        <input type="number" step="0.01" name="purchase_price" value="{{ product.purchase_price }}">

        <label>سعر البيع</label>
        <input type="number" step="0.01" name="sale_price" value="{{ product.sale_price }}">

        <label>الكمية</label>
        <input type="number" name="quantity" value="{{ product.quantity }}">

        <label>حد تنبيه المخزون</label>
        <input type="number" name="low_stock" value="{{ product.low_stock }}">

        <button>حفظ التعديلات</button>
        <a class="btn btn-gray" href="/products">إلغاء</a>
      </form>
    </div>
    """
    return page("تعديل المنتج", body, product=product)


@app.route("/products/delete/<int:product_id>")
def delete_product(product_id):
    conn = get_db()

    used = conn.execute(
        "SELECT 1 FROM invoice_items WHERE product_id=? LIMIT 1",
        (product_id,)
    ).fetchone()

    purchased = conn.execute(
        "SELECT 1 FROM purchases WHERE product_id=? LIMIT 1",
        (product_id,)
    ).fetchone()

    if used or purchased:
        flash("لا يمكن حذف منتج له حركات بيع أو شراء.", "error")
    else:
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.commit()
        flash("تم حذف المنتج.", "success")

    conn.close()
    return redirect(url_for("products"))


# =========================================================
# المخزون
# =========================================================

@app.route("/stock")
def stock():
    conn = get_db()
    items = conn.execute("SELECT * FROM products ORDER BY quantity ASC, name ASC").fetchall()
    total_value = conn.execute(
        "SELECT COALESCE(SUM(quantity * purchase_price),0) v FROM products"
    ).fetchone()["v"]
    conn.close()

    body = """
    <div class="card">
      <h2>المخزون</h2>
      <p><strong>قيمة المخزون بسعر الشراء:</strong> {{ "%.2f"|format(total_value) }} {{ currency }}</p>
      <div class="table-wrap">
        <table>
          <tr><th>المنتج</th><th>الكمية</th><th>حد التنبيه</th><th>الحالة</th><th>قيمة المخزون</th></tr>
          {% for p in items %}
          <tr>
            <td>{{ p.name }}</td>
            <td>{{ p.quantity }}</td>
            <td>{{ p.low_stock }}</td>
            <td>
              {% if p.quantity <= p.low_stock %}
                <span class="badge badge-red">منخفض</span>
              {% else %}
                <span class="badge badge-green">جيد</span>
              {% endif %}
            </td>
            <td>{{ "%.2f"|format(p.quantity * p.purchase_price) }} {{ currency }}</td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>
    """
    return page("المخزون", body, items=items, total_value=total_value)


# =========================================================
# العملاء
# =========================================================

@app.route("/customers", methods=["GET", "POST"])
def customers():
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            INSERT INTO customers (name, phone, address, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            request.form.get("name", "").strip(),
            request.form.get("phone", "").strip(),
            request.form.get("address", "").strip(),
            request.form.get("notes", "").strip(),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()
        flash("تمت إضافة العميل.", "success")
        return redirect(url_for("customers"))

    items = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()

    rows = conn.execute("""
        SELECT customer_id, COALESCE(SUM(balance),0) b
        FROM invoices
        WHERE customer_id IS NOT NULL
        GROUP BY customer_id
    """).fetchall()

    conn.close()
    balances = {r["customer_id"]: r["b"] for r in rows}

    body = """
    <div class="card">
      <h2>إضافة عميل</h2>
      <form method="post">
        <label>اسم العميل</label><input name="name" required>
        <label>الهاتف</label><input name="phone">
        <label>العنوان</label><input name="address">
        <label>ملاحظات</label><textarea name="notes"></textarea>
        <button>حفظ العميل</button>
      </form>
    </div>

    <div class="card">
      <h2>العملاء</h2>
      <div class="table-wrap">
        <table>
          <tr><th>#</th><th>الاسم</th><th>الهاتف</th><th>العنوان</th><th>الرصيد المستحق</th></tr>
          {% for c in items %}
          <tr>
            <td>{{ c.id }}</td>
            <td>{{ c.name }}</td>
            <td>{{ c.phone or "" }}</td>
            <td>{{ c.address or "" }}</td>
            <td>{{ "%.2f"|format(balances.get(c.id,0)) }} {{ currency }}</td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>
    """

    return page("العملاء", body, items=items, balances=balances)


# =========================================================
# الموردون
# =========================================================

@app.route("/suppliers", methods=["GET", "POST"])
def suppliers():
    conn = get_db()

    if request.method == "POST":
        conn.execute("""
            INSERT INTO suppliers (name, phone, address, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            request.form.get("name", "").strip(),
            request.form.get("phone", "").strip(),
            request.form.get("address", "").strip(),
            request.form.get("notes", "").strip(),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()
        flash("تمت إضافة المورد.", "success")
        return redirect(url_for("suppliers"))

    items = conn.execute("SELECT * FROM suppliers ORDER BY id DESC").fetchall()
    conn.close()

    body = """
    <div class="card">
      <h2>إضافة مورد</h2>
      <form method="post">
        <label>اسم المورد</label><input name="name" required>
        <label>الهاتف</label><input name="phone">
        <label>العنوان</label><input name="address">
        <label>ملاحظات</label><textarea name="notes"></textarea>
        <button>حفظ المورد</button>
      </form>
    </div>

    <div class="card">
      <h2>الموردون</h2>
      <div class="table-wrap">
        <table>
          <tr><th>#</th><th>الاسم</th><th>الهاتف</th><th>العنوان</th><th>ملاحظات</th></tr>
          {% for s in items %}
          <tr>
            <td>{{ s.id }}</td>
            <td>{{ s.name }}</td>
            <td>{{ s.phone or "" }}</td>
            <td>{{ s.address or "" }}</td>
            <td>{{ s.notes or "" }}</td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>
    """
    return page("الموردون", body, items=items)


# =========================================================
# المشتريات
# =========================================================

@app.route("/purchases", methods=["GET", "POST"])
def purchases():
    conn = get_db()

    if request.method == "POST":
        try:
            supplier_id = request.form.get("supplier_id") or None
            product_id = int(request.form.get("product_id"))
            quantity = int(request.form.get("quantity"))
            unit_cost = float(request.form.get("unit_cost"))
            notes = request.form.get("notes", "").strip()

            if quantity <= 0 or unit_cost < 0:
                raise ValueError

            total = quantity * unit_cost
            purchase_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            conn.execute("BEGIN")
            conn.execute("""
                INSERT INTO purchases
                (supplier_id, product_id, quantity, unit_cost, total, purchase_date, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                supplier_id, product_id, quantity,
                unit_cost, total, purchase_date, notes
            ))

            conn.execute("""
                UPDATE products
                SET quantity = quantity + ?, purchase_price = ?
                WHERE id = ?
            """, (quantity, unit_cost, product_id))

            conn.commit()
            flash("تم تسجيل المشتريات وزيادة المخزون.", "success")

        except Exception:
            conn.rollback()
            flash("تعذر تسجيل المشتريات. تحقق من البيانات.", "error")

        conn.close()
        return redirect(url_for("purchases"))

    products_list = conn.execute("SELECT * FROM products ORDER BY name").fetchall()
    suppliers_list = conn.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    items = conn.execute("""
        SELECT p.*, pr.name product_name, s.name supplier_name
        FROM purchases p
        JOIN products pr ON pr.id=p.product_id
        LEFT JOIN suppliers s ON s.id=p.supplier_id
        ORDER BY p.id DESC
        LIMIT 100
    """).fetchall()
    conn.close()

    body = """
    <div class="card">
      <h2>تسجيل مشتريات</h2>
      <form method="post">
        <label>المورد</label>
        <select name="supplier_id">
          <option value="">بدون مورد محدد</option>
          {% for s in suppliers_list %}
            <option value="{{ s.id }}">{{ s.name }}</option>
          {% endfor %}
        </select>

        <label>المنتج</label>
        <select name="product_id" required>
          <option value="">اختر المنتج</option>
          {% for p in products_list %}
            <option value="{{ p.id }}">{{ p.name }}</option>
          {% endfor %}
        </select>

        <label>الكمية</label>
        <input type="number" min="1" name="quantity" required>

        <label>تكلفة الوحدة</label>
        <input type="number" step="0.01" min="0" name="unit_cost" required>

        <label>ملاحظات</label>
        <textarea name="notes"></textarea>

        <button>حفظ المشتريات</button>
      </form>
    </div>

    <div class="card">
      <h2>آخر المشتريات</h2>
      <div class="table-wrap">
        <table>
          <tr><th>#</th><th>المورد</th><th>المنتج</th><th>الكمية</th><th>التكلفة</th><th>الإجمالي</th><th>التاريخ</th></tr>
          {% for r in items %}
          <tr>
            <td>{{ r.id }}</td>
            <td>{{ r.supplier_name or "-" }}</td>
            <td>{{ r.product_name }}</td>
            <td>{{ r.quantity }}</td>
            <td>{{ "%.2f"|format(r.unit_cost) }} {{ currency }}</td>
            <td>{{ "%.2f"|format(r.total) }} {{ currency }}</td>
            <td>{{ r.purchase_date }}</td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>
    """
    return page(
        "المشتريات",
        body,
        products_list=products_list,
        suppliers_list=suppliers_list,
        items=items
    )


# =========================================================
# المصروفات
# =========================================================

@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    conn = get_db()

    if request.method == "POST":
        try:
            title = request.form.get("title", "").strip()
            amount = float(request.form.get("amount", 0))
            expense_date = request.form.get("expense_date") or datetime.now().strftime("%Y-%m-%d")
            notes = request.form.get("notes", "").strip()

            conn.execute("""
                INSERT INTO expenses (title, amount, expense_date, notes)
                VALUES (?, ?, ?, ?)
            """, (title, amount, expense_date, notes))

            conn.commit()
            flash("تم تسجيل المصروف.", "success")
        except Exception:
            flash("تعذر تسجيل المصروف.", "error")

        conn.close()
        return redirect(url_for("expenses"))

    items = conn.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 200").fetchall()
    conn.close()

    body = """
    <div class="card">
      <h2>إضافة مصروف</h2>
      <form method="post">
        <label>البيان</label><input name="title" required>
        <label>المبلغ</label><input type="number" step="0.01" name="amount" required>
        <label>التاريخ</label><input type="date" name="expense_date" value="{{ today }}">
        <label>ملاحظات</label><textarea name="notes"></textarea>
        <button>حفظ المصروف</button>
      </form>
    </div>

    <div class="card">
      <h2>المصروفات</h2>
      <div class="table-wrap">
        <table>
          <tr><th>#</th><th>البيان</th><th>المبلغ</th><th>التاريخ</th><th>حذف</th></tr>
          {% for e in items %}
          <tr>
            <td>{{ e.id }}</td>
            <td>{{ e.title }}</td>
            <td>{{ "%.2f"|format(e.amount) }} {{ currency }}</td>
            <td>{{ e.expense_date }}</td>
            <td><a class="btn btn-red" href="/expenses/delete/{{ e.id }}" onclick="return confirm('حذف المصروف؟')">حذف</a></td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>
    """
    return page("المصروفات", body, items=items, today=datetime.now().strftime("%Y-%m-%d"))


@app.route("/expenses/delete/<int:expense_id>")
def delete_expense(expense_id):
    conn = get_db()
    conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
    conn.commit()
    conn.close()
    flash("تم حذف المصروف.", "success")
    return redirect(url_for("expenses"))


# =========================================================
# المبيعات والباركود
# =========================================================

@app.route("/sales")
def sales():
    conn = get_db()
    product_q = request.args.get("product_q", "").strip()

    if product_q:
        like = f"%{product_q}%"
        products_list = conn.execute("""
            SELECT * FROM products
            WHERE quantity > 0
              AND (name LIKE ? OR barcode LIKE ?)
            ORDER BY name
            LIMIT 100
        """, (like, like)).fetchall()
    else:
        products_list = conn.execute(
            "SELECT * FROM products WHERE quantity>0 ORDER BY name LIMIT 200"
        ).fetchall()

    customers_list = conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
    conn.close()

    cart = session.get("cart", [])
    subtotal = round(sum(float(i["total"]) for i in cart), 2)

    body = """
    <div class="card">
      <h2>فاتورة مبيعات جديدة</h2>

      <form method="post" action="/sales/barcode">
        <label>إدخال / مسح باركود</label>
        <div class="barcode-box">
          <input name="barcode" autofocus placeholder="امسح الباركود ثم اضغط إضافة">
          <button class="btn-green">إضافة</button>
        </div>
      </form>

      <hr>

      <form method="get" action="/sales">
        <label>بحث سريع عن صنف</label>
        <div class="barcode-box">
          <input name="product_q" value="{{ product_q }}" placeholder="اسم المنتج أو الباركود">
          <button class="btn-blue">بحث</button>
        </div>
      </form>

      <form method="post" action="/sales/add">
        <div class="grid">
          <div>
            <label>اختيار المنتج يدويًا</label>
            <select name="product_id" required>
              <option value="">اختر المنتج</option>
              {% for p in products_list %}
                <option value="{{ p.id }}">
                  {{ p.name }} — {{ "%.2f"|format(p.sale_price) }} {{ currency }} — المتوفر {{ p.quantity }}
                </option>
              {% endfor %}
            </select>
          </div>

          <div>
            <label>الكمية</label>
            <input type="number" min="1" name="quantity" value="1" required>
          </div>
        </div>

        <button class="btn-blue">إضافة إلى السلة</button>
      </form>
    </div>

    <div class="card">
      <h3>سلة الفاتورة</h3>
      <div class="table-wrap">
        <table>
          <tr><th>المنتج</th><th>الكمية</th><th>السعر</th><th>الإجمالي</th><th>حذف</th></tr>
          {% for item in cart %}
          <tr>
            <td>{{ item.name }}</td>
            <td>
              <div class="actions" style="justify-content:center;align-items:center">
                <a class="btn btn-gray" href="/sales/qty/{{ loop.index0 }}/minus">−</a>
                <strong style="min-width:28px">{{ item.quantity }}</strong>
                <a class="btn btn-blue" href="/sales/qty/{{ loop.index0 }}/plus">+</a>
              </div>
            </td>
            <td>{{ "%.2f"|format(item.price) }} {{ currency }}</td>
            <td>{{ "%.2f"|format(item.total) }} {{ currency }}</td>
            <td><a class="btn btn-red" href="/sales/remove/{{ loop.index0 }}">حذف</a></td>
          </tr>
          {% endfor %}
        </table>
      </div>

      <div class="total-box">المجموع قبل الخصم: {{ "%.2f"|format(subtotal) }} {{ currency }}</div>

      {% if cart %}
      <form method="post" action="/sales/checkout">
        <label>العميل</label>
        <select name="customer_id">
          <option value="">عميل نقدي / غير محدد</option>
          {% for c in customers_list %}
            <option value="{{ c.id }}">{{ c.name }}</option>
          {% endfor %}
        </select>

        <div class="grid">
          <div>
            <label>الخصم</label>
            <input id="discountInput" type="number" step="0.01" min="0" name="discount" value="0" oninput="updateChange()">
          </div>

          <div>
            <label>المبلغ المدفوع</label>
            <input id="paidInput" type="number" step="0.01" min="0" name="paid" value="{{ subtotal }}" oninput="updateChange()">
          </div>

          <div>
            <label>طريقة الدفع</label>
            <select name="payment_method">
              <option>نقدي</option>
              <option>آجل</option>
              <option>تحويل</option>
              <option>بطاقة</option>
            </select>
          </div>
        </div>

        <div class="grid">
          <div class="total-box">
            المطلوب: <span id="dueValue">{{ "%.2f"|format(subtotal) }}</span> {{ currency }}
          </div>
          <div class="total-box">
            الباقي للعميل: <span id="changeValue">0.00</span> {{ currency }}
          </div>
        </div>

        <label>ملاحظات</label>
        <textarea name="notes"></textarea>

        <button class="btn-green full">إتمام البيع وحفظ الفاتورة</button>

        <script>
        function updateChange(){
          const subtotal = Number({{ subtotal|tojson }});
          const discount = Math.max(0, Number(document.getElementById('discountInput').value || 0));
          const paid = Math.max(0, Number(document.getElementById('paidInput').value || 0));
          const due = Math.max(0, subtotal - discount);
          const change = Math.max(0, paid - due);

          document.getElementById('dueValue').textContent = due.toFixed(2);
          document.getElementById('changeValue').textContent = change.toFixed(2);
        }
        updateChange();
        </script>
      </form>

      <a class="btn btn-red" href="/sales/clear">إلغاء السلة</a>
      {% endif %}
    </div>
    """

    return page(
        "المبيعات",
        body,
        products_list=products_list,
        customers_list=customers_list,
        cart=cart,
        subtotal=subtotal,
        product_q=product_q
    )


def cart_add_product(product, quantity):
    if quantity <= 0:
        return False, "الكمية يجب أن تكون أكبر من صفر."

    cart = session.get("cart", [])
    already = sum(i["quantity"] for i in cart if i["product_id"] == product["id"])

    if already + quantity > product["quantity"]:
        return False, "الكمية المطلوبة أكبر من المخزون."

    found = False
    for item in cart:
        if item["product_id"] == product["id"]:
            item["quantity"] += quantity
            item["total"] = round(item["quantity"] * item["price"], 2)
            found = True
            break

    if not found:
        cart.append({
            "product_id": product["id"],
            "name": product["name"],
            "quantity": quantity,
            "price": float(product["sale_price"]),
            "cost_price": float(product["purchase_price"]),
            "total": round(quantity * float(product["sale_price"]), 2)
        })

    session["cart"] = cart
    return True, ""


@app.route("/sales/barcode", methods=["POST"])
def sales_barcode():
    barcode = request.form.get("barcode", "").strip()

    if not barcode:
        flash("أدخل الباركود.", "error")
        return redirect(url_for("sales"))

    conn = get_db()
    product = conn.execute(
        "SELECT * FROM products WHERE barcode=?",
        (barcode,)
    ).fetchone()
    conn.close()

    if not product:
        flash("لم يتم العثور على منتج بهذا الباركود.", "error")
        return redirect(url_for("sales"))

    ok, msg = cart_add_product(product, 1)
    if not ok:
        flash(msg, "error")

    return redirect(url_for("sales"))


@app.route("/sales/add", methods=["POST"])
def add_to_cart():
    try:
        product_id = int(request.form.get("product_id"))
        quantity = int(request.form.get("quantity"))
    except (TypeError, ValueError):
        flash("بيانات غير صحيحة.", "error")
        return redirect(url_for("sales"))

    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    conn.close()

    if not product:
        flash("المنتج غير موجود.", "error")
        return redirect(url_for("sales"))

    ok, msg = cart_add_product(product, quantity)
    if not ok:
        flash(msg, "error")

    return redirect(url_for("sales"))



@app.route("/sales/qty/<int:index>/<action>")
def change_cart_quantity(index, action):
    cart = session.get("cart", [])

    if not (0 <= index < len(cart)):
        flash("الصنف غير موجود في السلة.", "error")
        return redirect(url_for("sales"))

    item = cart[index]

    if action == "minus":
        if item["quantity"] <= 1:
            cart.pop(index)
        else:
            item["quantity"] -= 1
            item["total"] = round(item["quantity"] * item["price"], 2)

    elif action == "plus":
        conn = get_db()
        product = conn.execute(
            "SELECT quantity FROM products WHERE id=?",
            (item["product_id"],)
        ).fetchone()
        conn.close()

        if not product:
            flash("المنتج لم يعد موجودًا.", "error")
            return redirect(url_for("sales"))

        if item["quantity"] >= product["quantity"]:
            flash("لا توجد كمية إضافية متاحة في المخزون.", "error")
            return redirect(url_for("sales"))

        item["quantity"] += 1
        item["total"] = round(item["quantity"] * item["price"], 2)

    else:
        flash("عملية غير صحيحة.", "error")

    session["cart"] = cart
    return redirect(url_for("sales"))


@app.route("/sales/remove/<int:index>")
def remove_from_cart(index):
    cart = session.get("cart", [])
    if 0 <= index < len(cart):
        cart.pop(index)
    session["cart"] = cart
    return redirect(url_for("sales"))


@app.route("/sales/clear")
def clear_cart():
    session["cart"] = []
    return redirect(url_for("sales"))


@app.route("/sales/checkout", methods=["POST"])
def checkout():
    cart = session.get("cart", [])

    if not cart:
        flash("السلة فارغة.", "error")
        return redirect(url_for("sales"))

    conn = None

    try:
        customer_id = request.form.get("customer_id") or None
        discount = float(request.form.get("discount", 0) or 0)
        paid = float(request.form.get("paid", 0) or 0)
        payment_method = request.form.get("payment_method", "نقدي")
        notes = request.form.get("notes", "").strip()

        subtotal = round(sum(float(i["total"]) for i in cart), 2)

        if discount < 0 or discount > subtotal:
            raise Exception("قيمة الخصم غير صحيحة.")

        total = round(subtotal - discount, 2)
        paid_for_invoice = round(min(paid, total), 2)
        balance = round(max(total - paid_for_invoice, 0), 2)

        conn = get_db()
        conn.execute("BEGIN")

        for item in cart:
            product = conn.execute(
                "SELECT * FROM products WHERE id=?",
                (item["product_id"],)
            ).fetchone()

            if not product or item["quantity"] > product["quantity"]:
                raise Exception(f"المخزون غير كافٍ للمنتج: {item['name']}")

        sale_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur = conn.execute("""
            INSERT INTO invoices
            (customer_id, subtotal, discount, total, paid, balance, payment_method, notes, sale_date, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            customer_id, subtotal, discount, total,
            paid_for_invoice, balance, payment_method, notes, sale_date,
            session.get("full_name", "")
        ))

        invoice_id = cur.lastrowid

        for item in cart:
            conn.execute("""
                INSERT INTO invoice_items
                (invoice_id, product_id, product_name, quantity, unit_price, cost_price, total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                invoice_id,
                item["product_id"],
                item["name"],
                item["quantity"],
                item["price"],
                item["cost_price"],
                item["total"]
            ))

            conn.execute("""
                UPDATE products SET quantity = quantity - ? WHERE id=?
            """, (item["quantity"], item["product_id"]))

        conn.commit()
        conn.close()

        session["cart"] = []
        flash(f"تم حفظ الفاتورة رقم {invoice_id}.", "success")
        return redirect(url_for("invoice_detail", invoice_id=invoice_id))

    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass

        flash(str(e) if str(e) else "تعذر حفظ الفاتورة.", "error")
        return redirect(url_for("sales"))


# =========================================================
# الفواتير والطباعة الحرارية
# =========================================================

@app.route("/invoices")
def invoices():
    conn = get_db()
    q = request.args.get("q", "").strip()

    if q:
        like = f"%{q}%"
        items = conn.execute("""
            SELECT i.*, c.name customer_name
            FROM invoices i
            LEFT JOIN customers c ON c.id=i.customer_id
            WHERE CAST(i.id AS TEXT) LIKE ?
               OR c.name LIKE ?
               OR c.phone LIKE ?
               OR i.created_by LIKE ?
            ORDER BY i.id DESC
            LIMIT 300
        """, (like, like, like, like)).fetchall()
    else:
        items = conn.execute("""
            SELECT i.*, c.name customer_name
            FROM invoices i
            LEFT JOIN customers c ON c.id=i.customer_id
            ORDER BY i.id DESC
            LIMIT 300
        """).fetchall()

    conn.close()

    body = """
    <div class="card">
      <h2>بحث الفواتير</h2>
      <form method="get">
        <div class="barcode-box">
          <input name="q" value="{{ q }}" placeholder="رقم الفاتورة أو اسم/هاتف العميل أو الموظف">
          <button class="btn-blue">بحث</button>
        </div>
      </form>
    </div>

    <div class="card">
      <h2>الفواتير</h2>
      <div class="table-wrap">
        <table>
          <tr><th>رقم</th><th>التاريخ</th><th>العميل</th><th>الموظف</th><th>الإجمالي</th><th>المدفوع</th><th>الباقي</th><th>الدفع</th><th>عرض</th></tr>
          {% for i in items %}
          <tr>
            <td>{{ i.id }}</td>
            <td>{{ i.sale_date }}</td>
            <td>{{ i.customer_name or "غير محدد" }}</td>
            <td>{{ i.created_by or "-" }}</td>
            <td>{{ "%.2f"|format(i.total) }} {{ currency }}</td>
            <td>{{ "%.2f"|format(i.paid) }} {{ currency }}</td>
            <td>{{ "%.2f"|format(i.balance) }} {{ currency }}</td>
            <td>{{ i.payment_method }}</td>
            <td><a class="btn btn-blue" href="/invoice/{{ i.id }}">عرض</a></td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>
    """
    return page("الفواتير", body, items=items, q=q)


@app.route("/invoice/<int:invoice_id>")
def invoice_detail(invoice_id):
    conn = get_db()

    invoice = conn.execute("""
        SELECT i.*, c.name customer_name, c.phone customer_phone
        FROM invoices i
        LEFT JOIN customers c ON c.id=i.customer_id
        WHERE i.id=?
    """, (invoice_id,)).fetchone()

    if not invoice:
        conn.close()
        return "الفاتورة غير موجودة", 404

    items = conn.execute(
        "SELECT * FROM invoice_items WHERE invoice_id=?",
        (invoice_id,)
    ).fetchall()

    conn.close()

    s = get_settings()
    width = s["receipt_size"]

    if width == "58mm":
        receipt_width = "58mm"
    elif width == "A4":
        receipt_width = "190mm"
    else:
        receipt_width = "80mm"

    template = f"""
    <!doctype html>
    <html lang="ar" dir="rtl">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>فاتورة رقم {{{{ invoice.id }}}}</title>
      <style>
      body{{font-family:Arial,Tahoma,sans-serif;margin:0;background:#f3f4f6}}
      .actions{{max-width:700px;margin:12px auto;display:flex;gap:8px;padding:0 10px}}
      .actions button,.actions a{{border:0;border-radius:8px;padding:10px 14px;text-decoration:none;color:#fff;background:#111827}}
      .receipt{{width:{receipt_width};max-width:100%;margin:12px auto;background:#fff;padding:10px;box-sizing:border-box}}
      .center{{text-align:center}}
      .small{{font-size:12px}}
      .line{{border-top:1px dashed #222;margin:8px 0}}
      table{{width:100%;border-collapse:collapse;font-size:12px}}
      th,td{{padding:5px 2px;text-align:center;border-bottom:1px dotted #ccc}}
      .totals p{{margin:5px 0}}
      .grand{{font-size:18px;font-weight:bold}}
      @media print{{
        @page{{size:{receipt_width} auto;margin:2mm}}
        body{{background:#fff}}
        .actions{{display:none}}
        .receipt{{margin:0;width:{receipt_width};box-shadow:none}}
      }}
      </style>
    </head>
    <body>

      <div class="actions">
        <button onclick="window.print()">طباعة</button>
        <a href="/invoices">رجوع</a>
      </div>

      <div class="receipt">
        <div class="center">
          <h2 style="margin:4px 0">{{{{ settings.store_name }}}}</h2>
          {{% if settings.store_address %}}<div class="small">{{{{ settings.store_address }}}}</div>{{% endif %}}
          {{% if settings.store_phone %}}<div class="small">هاتف: {{{{ settings.store_phone }}}}</div>{{% endif %}}
          {{% if settings.tax_number %}}<div class="small">رقم: {{{{ settings.tax_number }}}}</div>{{% endif %}}
        </div>

        <div class="line"></div>

        <div class="small">
          <div><strong>فاتورة رقم:</strong> {{{{ invoice.id }}}}</div>
          <div><strong>التاريخ:</strong> {{{{ invoice.sale_date }}}}</div>
          <div><strong>العميل:</strong> {{{{ invoice.customer_name or "نقدي" }}}}</div>
          <div><strong>الموظف:</strong> {{{{ invoice.created_by or "-" }}}}</div>
        </div>

        <div class="line"></div>

        <table>
          <tr><th>الصنف</th><th>ك</th><th>السعر</th><th>الإجمالي</th></tr>
          {{% for item in items %}}
          <tr>
            <td>{{{{ item.product_name }}}}</td>
            <td>{{{{ item.quantity }}}}</td>
            <td>{{{{ "%.2f"|format(item.unit_price) }}}}</td>
            <td>{{{{ "%.2f"|format(item.total) }}}}</td>
          </tr>
          {{% endfor %}}
        </table>

        <div class="line"></div>

        <div class="totals">
          <p>المجموع: {{{{ "%.2f"|format(invoice.subtotal) }}}} {{{{ settings.currency }}}}</p>
          <p>الخصم: {{{{ "%.2f"|format(invoice.discount) }}}} {{{{ settings.currency }}}}</p>
          <p class="grand">الإجمالي: {{{{ "%.2f"|format(invoice.total) }}}} {{{{ settings.currency }}}}</p>
          <p>المدفوع: {{{{ "%.2f"|format(invoice.paid) }}}} {{{{ settings.currency }}}}</p>
          <p>الباقي: {{{{ "%.2f"|format(invoice.balance) }}}} {{{{ settings.currency }}}}</p>
          <p>طريقة الدفع: {{{{ invoice.payment_method }}}}</p>
        </div>

        {{% if invoice.notes %}}
        <div class="line"></div>
        <div class="small">ملاحظات: {{{{ invoice.notes }}}}</div>
        {{% endif %}}

        <div class="line"></div>
        <div class="center small">شكرًا لتعاملكم معنا</div>
      </div>

    </body>
    </html>
    """

    return render_template_string(
        template,
        invoice=invoice,
        items=items,
        settings=s
    )



# =========================================================
# المرتجعات
# =========================================================

@app.route("/returns")
def returns_list():
    conn = get_db()

    items = conn.execute("""
        SELECT r.*, i.sale_date, c.name customer_name
        FROM returns r
        JOIN invoices i ON i.id = r.invoice_id
        LEFT JOIN customers c ON c.id = i.customer_id
        ORDER BY r.id DESC
        LIMIT 300
    """).fetchall()

    conn.close()

    body = """
    <div class="card">
      <h2>المرتجعات</h2>

      <form method="get" action="/returns/new">
        <label>رقم الفاتورة المراد إرجاع صنف منها</label>
        <input type="number" min="1" name="invoice_id" placeholder="مثال: 15" required>
        <button class="btn-orange">فتح الفاتورة</button>
      </form>
    </div>

    <div class="card">
      <h3>سجل المرتجعات</h3>

      <div class="table-wrap">
        <table>
          <tr>
            <th>رقم المرتجع</th>
            <th>رقم الفاتورة</th>
            <th>العميل</th>
            <th>قيمة المرتجع</th>
            <th>تاريخ المرتجع</th>
            <th>عرض</th>
          </tr>

          {% for r in items %}
          <tr>
            <td>{{ r.id }}</td>
            <td>{{ r.invoice_id }}</td>
            <td>{{ r.customer_name or "غير محدد" }}</td>
            <td>{{ "%.2f"|format(r.total) }} {{ currency }}</td>
            <td>{{ r.return_date }}</td>
            <td>
              <a class="btn btn-blue" href="/return/{{ r.id }}">عرض</a>
            </td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>
    """

    return page("المرتجعات", body, items=items)


@app.route("/returns/new")
def new_return():
    invoice_id = request.args.get("invoice_id", "").strip()

    try:
        invoice_id = int(invoice_id)
    except ValueError:
        flash("رقم الفاتورة غير صحيح.", "error")
        return redirect(url_for("returns_list"))

    conn = get_db()

    invoice = conn.execute("""
        SELECT i.*, c.name customer_name
        FROM invoices i
        LEFT JOIN customers c ON c.id = i.customer_id
        WHERE i.id = ?
    """, (invoice_id,)).fetchone()

    if not invoice:
        conn.close()
        flash("الفاتورة غير موجودة.", "error")
        return redirect(url_for("returns_list"))

    items = conn.execute("""
        SELECT
            ii.*,
            COALESCE((
                SELECT SUM(ri.quantity)
                FROM return_items ri
                WHERE ri.invoice_item_id = ii.id
            ), 0) AS returned_quantity
        FROM invoice_items ii
        WHERE ii.invoice_id = ?
        ORDER BY ii.id
    """, (invoice_id,)).fetchall()

    conn.close()

    body = """
    <div class="card">
      <h2>إرجاع من الفاتورة رقم {{ invoice.id }}</h2>

      <p><strong>العميل:</strong> {{ invoice.customer_name or "غير محدد" }}</p>
      <p><strong>تاريخ الفاتورة:</strong> {{ invoice.sale_date }}</p>

      <div class="table-wrap">
        <table>
          <tr>
            <th>الصنف</th>
            <th>المباع</th>
            <th>سبق إرجاعه</th>
            <th>المتبقي للإرجاع</th>
            <th>السعر</th>
            <th>إرجاع</th>
          </tr>

          {% for item in items %}
          {% set remaining = item.quantity - item.returned_quantity %}
          <tr>
            <td>{{ item.product_name }}</td>
            <td>{{ item.quantity }}</td>
            <td>{{ item.returned_quantity }}</td>
            <td>{{ remaining }}</td>
            <td>{{ "%.2f"|format(item.unit_price) }} {{ currency }}</td>
            <td>
              {% if remaining > 0 %}
              <form method="post" action="/returns/process">
                <input type="hidden" name="invoice_id" value="{{ invoice.id }}">
                <input type="hidden" name="invoice_item_id" value="{{ item.id }}">
                <input type="number" min="1" max="{{ remaining }}" name="quantity" value="1" required>
                <input name="notes" placeholder="ملاحظة اختيارية">
                <button class="btn-orange">تنفيذ الإرجاع</button>
              </form>
              {% else %}
                <span class="badge badge-green">تم إرجاع الكمية بالكامل</span>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </table>
      </div>

      <a class="btn btn-gray" href="/returns">الرجوع إلى المرتجعات</a>
    </div>
    """

    return page(
        "إرجاع فاتورة",
        body,
        invoice=invoice,
        items=items
    )


@app.route("/returns/process", methods=["POST"])
def process_return():
    conn = None

    try:
        invoice_id = int(request.form.get("invoice_id", "0"))
        invoice_item_id = int(request.form.get("invoice_item_id", "0"))
        quantity = int(request.form.get("quantity", "0"))
        notes = request.form.get("notes", "").strip()

        if quantity <= 0:
            raise Exception("كمية الإرجاع يجب أن تكون أكبر من صفر.")

        conn = get_db()
        conn.execute("BEGIN")

        item = conn.execute("""
            SELECT *
            FROM invoice_items
            WHERE id = ? AND invoice_id = ?
        """, (invoice_item_id, invoice_id)).fetchone()

        if not item:
            raise Exception("الصنف غير موجود في هذه الفاتورة.")

        already_returned = conn.execute("""
            SELECT COALESCE(SUM(quantity), 0) q
            FROM return_items
            WHERE invoice_item_id = ?
        """, (invoice_item_id,)).fetchone()["q"]

        remaining = item["quantity"] - already_returned

        if quantity > remaining:
            raise Exception("كمية الإرجاع أكبر من الكمية المتبقية القابلة للإرجاع.")

        total = round(quantity * float(item["unit_price"]), 2)
        return_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur = conn.execute("""
            INSERT INTO returns
            (invoice_id, total, return_date, notes)
            VALUES (?, ?, ?, ?)
        """, (invoice_id, total, return_date, notes))

        return_id = cur.lastrowid

        conn.execute("""
            INSERT INTO return_items
            (
                return_id,
                invoice_item_id,
                product_id,
                product_name,
                quantity,
                unit_price,
                total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            return_id,
            invoice_item_id,
            item["product_id"],
            item["product_name"],
            quantity,
            item["unit_price"],
            total
        ))

        if item["product_id"] is not None:
            conn.execute("""
                UPDATE products
                SET quantity = quantity + ?
                WHERE id = ?
            """, (quantity, item["product_id"]))

        conn.execute("""
            UPDATE invoices
            SET
                total = CASE WHEN total - ? < 0 THEN 0 ELSE total - ? END,
                paid = CASE
                    WHEN paid > (CASE WHEN total - ? < 0 THEN 0 ELSE total - ? END)
                    THEN (CASE WHEN total - ? < 0 THEN 0 ELSE total - ? END)
                    ELSE paid
                END,
                balance = CASE
                    WHEN (CASE WHEN total - ? < 0 THEN 0 ELSE total - ? END) - paid < 0
                    THEN 0
                    ELSE (CASE WHEN total - ? < 0 THEN 0 ELSE total - ? END) - paid
                END
            WHERE id = ?
        """, (
            total, total,
            total, total,
            total, total,
            total, total,
            total, total,
            invoice_id
        ))

        conn.commit()
        conn.close()

        flash(
            f"تم تسجيل المرتجع رقم {return_id} وإعادة الكمية إلى المخزون.",
            "success"
        )

        return redirect(url_for("return_detail", return_id=return_id))

    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass

        flash(str(e) if str(e) else "تعذر تنفيذ المرتجع.", "error")
        return redirect(url_for("returns_list"))


@app.route("/return/<int:return_id>")
def return_detail(return_id):
    conn = get_db()

    ret = conn.execute("""
        SELECT r.*, i.sale_date, c.name customer_name
        FROM returns r
        JOIN invoices i ON i.id = r.invoice_id
        LEFT JOIN customers c ON c.id = i.customer_id
        WHERE r.id = ?
    """, (return_id,)).fetchone()

    if not ret:
        conn.close()
        return "المرتجع غير موجود", 404

    items = conn.execute("""
        SELECT *
        FROM return_items
        WHERE return_id = ?
        ORDER BY id
    """, (return_id,)).fetchall()

    conn.close()

    body = """
    <div class="card">
      <div class="actions no-print">
        <button onclick="window.print()" class="btn-green">طباعة</button>
        <a class="btn btn-gray" href="/returns">رجوع</a>
      </div>

      <h2 style="text-align:center">إشعار مرتجع رقم {{ ret.id }}</h2>

      <p><strong>الفاتورة الأصلية:</strong> {{ ret.invoice_id }}</p>
      <p><strong>العميل:</strong> {{ ret.customer_name or "غير محدد" }}</p>
      <p><strong>تاريخ المرتجع:</strong> {{ ret.return_date }}</p>

      <div class="table-wrap">
        <table>
          <tr>
            <th>الصنف</th>
            <th>الكمية المرتجعة</th>
            <th>سعر الوحدة</th>
            <th>الإجمالي</th>
          </tr>

          {% for item in items %}
          <tr>
            <td>{{ item.product_name }}</td>
            <td>{{ item.quantity }}</td>
            <td>{{ "%.2f"|format(item.unit_price) }} {{ currency }}</td>
            <td>{{ "%.2f"|format(item.total) }} {{ currency }}</td>
          </tr>
          {% endfor %}
        </table>
      </div>

      <div class="total-box">
        قيمة المرتجع: {{ "%.2f"|format(ret.total) }} {{ currency }}
      </div>

      {% if ret.notes %}
      <p><strong>ملاحظات:</strong> {{ ret.notes }}</p>
      {% endif %}
    </div>
    """

    return page(
        "تفاصيل المرتجع",
        body,
        ret=ret,
        items=items
    )


# =========================================================
# التقارير
# =========================================================

@app.route("/reports")
def reports():
    today = datetime.now().strftime("%Y-%m-%d")
    month_start = datetime.now().strftime("%Y-%m-01")
    start = request.args.get("start", today)
    end = request.args.get("end", today)

    conn = get_db()

    invoice_sales_total = conn.execute("""
        SELECT COALESCE(SUM(total),0) v
        FROM invoices
        WHERE date(sale_date) BETWEEN ? AND ?
    """, (start, end)).fetchone()["v"]

    returns_total = conn.execute("""
        SELECT COALESCE(SUM(total),0) v
        FROM returns
        WHERE date(return_date) BETWEEN ? AND ?
    """, (start, end)).fetchone()["v"]

    sales_total = invoice_sales_total

    discounts = conn.execute("""
        SELECT COALESCE(SUM(discount),0) v
        FROM invoices
        WHERE date(sale_date) BETWEEN ? AND ?
    """, (start, end)).fetchone()["v"]

    gross_profit = conn.execute("""
        SELECT COALESCE(SUM((unit_price - cost_price) * quantity),0) v
        FROM invoice_items ii
        JOIN invoices i ON i.id=ii.invoice_id
        WHERE date(i.sale_date) BETWEEN ? AND ?
    """, (start, end)).fetchone()["v"]

    returned_profit = conn.execute("""
        SELECT COALESCE(SUM((ri.unit_price - ii.cost_price) * ri.quantity),0) v
        FROM return_items ri
        JOIN returns r ON r.id = ri.return_id
        JOIN invoice_items ii ON ii.id = ri.invoice_item_id
        WHERE date(r.return_date) BETWEEN ? AND ?
    """, (start, end)).fetchone()["v"]

    gross_profit = gross_profit - returned_profit

    expenses_total = conn.execute("""
        SELECT COALESCE(SUM(amount),0) v
        FROM expenses
        WHERE date(expense_date) BETWEEN ? AND ?
    """, (start, end)).fetchone()["v"]

    customer_debt = conn.execute("""
        SELECT COALESCE(SUM(balance),0) -
               COALESCE((SELECT SUM(amount) FROM customer_payments),0) v
        FROM invoices
    """).fetchone()["v"]
    customer_debt = max(float(customer_debt or 0), 0)

    supplier_debt = conn.execute("""
        SELECT COALESCE(SUM(total),0) -
               COALESCE((SELECT SUM(amount) FROM supplier_payments),0) v
        FROM purchases
    """).fetchone()["v"]
    supplier_debt = max(float(supplier_debt or 0), 0)

    invoice_count = conn.execute("""
        SELECT COUNT(*) c
        FROM invoices
        WHERE date(sale_date) BETWEEN ? AND ?
    """, (start, end)).fetchone()["c"]

    top_products = conn.execute("""
        SELECT ii.product_name, SUM(ii.quantity) qty, SUM(ii.total) total
        FROM invoice_items ii
        JOIN invoices i ON i.id=ii.invoice_id
        WHERE date(i.sale_date) BETWEEN ? AND ?
        GROUP BY ii.product_name
        ORDER BY qty DESC
        LIMIT 10
    """, (start, end)).fetchall()

    conn.close()

    net_profit = gross_profit - expenses_total - discounts

    body = """
    <div class="card">
      <h2>التقارير</h2>

      <div class="actions" style="margin-bottom:12px">
        <a class="btn btn-blue" href="/reports?start={{ today }}&end={{ today }}">اليوم</a>
        <a class="btn btn-gray" href="/reports?start={{ month_start }}&end={{ today }}">هذا الشهر</a>
      </div>

      <form method="get">
        <div class="grid">
          <div><label>من</label><input type="date" name="start" value="{{ start }}"></div>
          <div><label>إلى</label><input type="date" name="end" value="{{ end }}"></div>
        </div>
        <button>عرض التقرير</button>
      </form>
    </div>

    <div class="grid">
      <div class="stat">المبيعات<div class="n">{{ "%.2f"|format(sales_total) }} {{ currency }}</div></div>
      <div class="stat">عدد الفواتير<div class="n">{{ invoice_count }}</div></div>
      <div class="stat">الخصومات<div class="n">{{ "%.2f"|format(discounts) }} {{ currency }}</div></div>
      <div class="stat">المرتجعات<div class="n">{{ "%.2f"|format(returns_total) }} {{ currency }}</div></div>
      <div class="stat">الربح الإجمالي التقريبي<div class="n">{{ "%.2f"|format(gross_profit) }} {{ currency }}</div></div>
      <div class="stat">المصروفات<div class="n">{{ "%.2f"|format(expenses_total) }} {{ currency }}</div></div>
      <div class="stat">صافي الربح التقريبي<div class="n">{{ "%.2f"|format(net_profit) }} {{ currency }}</div></div>
      <div class="stat">ديون العملاء<div class="n">{{ "%.2f"|format(customer_debt) }} {{ currency }}</div></div>
      <div class="stat">مستحقات الموردين<div class="n">{{ "%.2f"|format(supplier_debt) }} {{ currency }}</div></div>
    </div>

    <div class="card" style="margin-top:16px">
      <h3>أكثر المنتجات مبيعًا</h3>
      <div class="table-wrap">
        <table>
          <tr><th>المنتج</th><th>الكمية المباعة</th><th>قيمة المبيعات</th></tr>
          {% for r in top_products %}
          <tr>
            <td>{{ r.product_name }}</td>
            <td>{{ r.qty }}</td>
            <td>{{ "%.2f"|format(r.total) }} {{ currency }}</td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>
    """

    return page(
        "التقارير",
        body,
        start=start,
        end=end,
        sales_total=sales_total,
        discounts=discounts,
        returns_total=returns_total,
        gross_profit=gross_profit,
        expenses_total=expenses_total,
        net_profit=net_profit,
        invoice_count=invoice_count,
        top_products=top_products,
        today=today,
        month_start=month_start,
        customer_debt=customer_debt,
        supplier_debt=supplier_debt
    )


# =========================================================
# تشغيل
# =========================================================

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
