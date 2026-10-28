from flask import Flask, request, redirect, url_for, session, render_template_string, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from functools import wraps
from datetime import date

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET_KEY"
DB = "garments.db"


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('owner','employee'))
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            assigned_qty INTEGER NOT NULL,
            rate REAL NOT NULL,
            due_date TEXT,
            completed_qty INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Assigned',
            created_at TEXT NOT NULL,
            FOREIGN KEY(employee_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS advances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            note TEXT,
            paid_date TEXT NOT NULL,
            FOREIGN KEY(employee_id) REFERENCES users(id)
        );
        """)
        owner = con.execute(
            "SELECT id FROM users WHERE username = ?", ("owner",)
        ).fetchone()
        if not owner:
            con.execute(
                "INSERT INTO users (username, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                ("owner", "Garments Owner",
                 generate_password_hash("ChangeMe123!"), "owner")
            )


BASE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} | Garments Work & Salary</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f3f6fa;color:#172033}
header{background:#123047;color:white;padding:18px 5%;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
header a{color:white;text-decoration:none;margin-left:12px}
main{max-width:1100px;margin:28px auto;padding:0 16px}
h1,h2{margin-top:0}.muted{color:#65758b}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}
.card{background:white;border-radius:14px;padding:20px;box-shadow:0 4px 18px #17304712;margin-bottom:18px}
.stat{font-size:28px;font-weight:bold;color:#087f70}
form{display:grid;gap:10px}input,select,button{font:inherit;padding:11px;border:1px solid #cbd5e1;border-radius:8px;width:100%}
button,.btn{background:#087f70;color:white;border:0;cursor:pointer;text-decoration:none;display:inline-block;text-align:center;padding:11px 14px;border-radius:8px}
button:hover,.btn:hover{background:#06675c}table{width:100%;border-collapse:collapse;min-width:620px}
th,td{text-align:left;padding:11px;border-bottom:1px solid #e2e8f0;vertical-align:top}
.table-wrap{overflow-x:auto}.notice{padding:12px;background:#e0f2fe;border-radius:8px;margin-bottom:12px}
.error{background:#fee2e2}.inline-form{display:flex;gap:8px;align-items:center}.inline-form input{min-width:95px}
small{color:#65758b}.login{max-width:430px;margin:50px auto}
@media(max-width:600px){header{padding:16px}main{margin-top:18px}.card{padding:16px}}
</style>
</head>
<body>
<header>
  <div><strong>🧵 Garments Work & Salary</strong></div>
  <nav>
  {% if user %}
    <span>{{ user['full_name'] }} ({{ user['role']|title }})</span>
    <a href="{{ url_for('dashboard') }}">Dashboard</a>
    <a href="{{ url_for('logout') }}">Logout</a>
  {% endif %}
  </nav>
</header>
<main>
{% with messages = get_flashed_messages() %}
  {% for message in messages %}<div class="notice">{{ message }}</div>{% endfor %}
{% endwith %}
{{ content|safe }}
</main>
</body>
</html>
"""


def page(title, content, **kwargs):
    return render_template_string(
        BASE, title=title, content=render_template_string(content, **kwargs),
        user=current_user()
    )


def current_user():
    if "user_id" not in session:
        return None
    with connect() as con:
        return con.execute("SELECT * FROM users WHERE id = ?",
                           (session["user_id"],)).fetchone()


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login"))
            if role and user["role"] != role:
                flash("Indha page-ku permission illa.")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with connect() as con:
            user = con.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Username or password incorrect.")
    content = """
    <section class="card login">
      <h1>Login</h1>
      <p class="muted">Owner or employee account use pannunga.</p>
      <form method="post">
        <label>Username</label><input name="username" required autocomplete="username">
        <label>Password</label><input type="password" name="password" required autocomplete="current-password">
        <button type="submit">Login</button>
      </form>
      <p><small>First owner login: username <b>owner</b>, password <b>ChangeMe123!</b>.
      Login pannadhum owner password-a maathunga.</small></p>
    </section>"""
    return page("Login", content)


@app.route("/dashboard")
@login_required()
def dashboard():
    user = current_user()
    if user["role"] == "owner":
        return redirect(url_for("owner_dashboard"))
    return redirect(url_for("employee_dashboard"))


@app.route("/owner")
@login_required("owner")
def owner_dashboard():
    with connect() as con:
        employees = con.execute(
            "SELECT id, username, full_name FROM users WHERE role='employee' ORDER BY full_name"
        ).fetchall()
        tasks = con.execute("""
            SELECT tasks.*, users.full_name
            FROM tasks JOIN users ON users.id=tasks.employee_id
            ORDER BY tasks.id DESC
        """).fetchall()
        totals = con.execute("""
            SELECT
              COALESCE((SELECT SUM(completed_qty * rate) FROM tasks
                        WHERE status='Approved'),0) AS earned,
              COALESCE((SELECT SUM(amount) FROM advances),0) AS advances,
              (SELECT COUNT(*) FROM users WHERE role='employee') AS staff,
              (SELECT COUNT(*) FROM tasks WHERE status != 'Approved') AS pending
        """).fetchone()

    content = """
    <h1>Owner Dashboard</h1>
    <p class="muted">Employee accounts, daily work, approvals and salary tracking.</p>
    <div class="grid">
      <div class="card"><div class="muted">Employees</div><div class="stat">{{ totals['staff'] }}</div></div>
      <div class="card"><div class="muted">Tasks awaiting approval</div><div class="stat">{{ totals['pending'] }}</div></div>
      <div class="card"><div class="muted">Approved earnings total</div><div class="stat">₹{{ '%.2f'|format(totals['earned']) }}</div></div>
      <div class="card"><div class="muted">Advances paid total</div><div class="stat">₹{{ '%.2f'|format(totals['advances']) }}</div></div>
    </div>

    <div class="grid">
      <section class="card">
        <h2>Create Employee</h2>
        <form method="post" action="{{ url_for('create_employee') }}">
          <label>Employee full name</label><input name="full_name" required>
          <label>Login username</label><input name="username" required>
          <label>Temporary password</label><input name="password" type="password" minlength="8" required>
          <button>Create employee account</button>
        </form>
      </section>
      <section class="card">
        <h2>Assign Work</h2>
        {% if employees %}
        <form method="post" action="{{ url_for('create_task') }}">
          <label>Employee</label><select name="employee_id" required>
          {% for e in employees %}<option value="{{ e['id'] }}">{{ e['full_name'] }} (@{{ e['username'] }})</option>{% endfor %}
          </select>
          <label>Work description</label><input name="title" placeholder="Example: Shirt stitching" required>
          <label>Quantity assigned (pieces)</label><input type="number" name="assigned_qty" min="1" required>
          <label>Rate per piece (₹)</label><input type="number" name="rate" min="0" step="0.01" required>
          <label>Due date (optional)</label><input type="date" name="due_date">
          <button>Assign work</button>
        </form>
        {% else %}<p>Create an employee account first.</p>{% endif %}
      </section>
      <section class="card">
        <h2>Record Salary Advance</h2>
        {% if employees %}
        <form method="post" action="{{ url_for('add_advance') }}">
          <label>Employee</label><select name="employee_id" required>
          {% for e in employees %}<option value="{{ e['id'] }}">{{ e['full_name'] }}</option>{% endfor %}
          </select>
          <label>Advance amount (₹)</label><input type="number" name="amount" min="0.01" step="0.01" required>
          <label>Note (optional)</label><input name="note" placeholder="Cash advance">
          <button>Save advance</button>
        </form>
        {% else %}<p>Create an employee account first.</p>{% endif %}
      </section>
    </div>

    <section class="card">
      <h2>Assigned Work & Approval</h2>
      <div class="table-wrap"><table>
      <tr><th>Employee / Work</th><th>Assigned</th><th>Rate</th><th>Submitted pieces</th><th>Status</th><th>Action</th></tr>
      {% for t in tasks %}
      <tr>
        <td><b>{{ t['full_name'] }}</b><br>{{ t['title'] }}<br><small>Due: {{ t['due_date'] or 'Not set' }}</small></td>
        <td>{{ t['assigned_qty'] }}</td><td>₹{{ '%.2f'|format(t['rate']) }}</td>
        <td>{{ t['completed_qty'] }}</td><td>{{ t['status'] }}</td>
        <td>
        {% if t['status'] == 'Submitted' %}
          <form method="post" action="{{ url_for('approve_task', task_id=t['id']) }}">
            <button>Approve {{ t['completed_qty'] }} pieces</button>
          </form>
        {% elif t['status'] == 'Assigned' %}
          <small>Waiting for employee submission</small>
        {% else %}
          <small>Approved earnings: ₹{{ '%.2f'|format(t['completed_qty'] * t['rate']) }}</small>
        {% endif %}
        </td>
      </tr>
      {% else %}<tr><td colspan="6">No work assigned yet.</td></tr>{% endfor %}
      </table></div>
    </section>
    <section class="card">
      <h2>Employee Salary Summary</h2>
      <div class="table-wrap"><table>
      <tr><th>Employee</th><th>Approved earnings</th><th>Advance</th><th>Balance</th></tr>
      {% for e in employees %}
      <tr><td>{{ e['full_name'] }} (@{{ e['username'] }})</td>
      <td>₹{{ '%.2f'|format(e['earned']) }}</td>
      <td>₹{{ '%.2f'|format(e['advance']) }}</td>
      <td><b>₹{{ '%.2f'|format(e['earned'] - e['advance']) }}</b></td></tr>
      {% else %}<tr><td colspan="4">No employees yet.</td></tr>{% endfor %}
      </table></div>
      <p><small>Balance is a running total: approved piece earnings minus recorded advances. Add payment tracking separately before using this as an official payroll record.</small></p>
    </section>
    """
    # Add each employee's salary figures to the list used by the template.
    employee_data = []
    with connect() as con:
        for e in employees:
            earned = con.execute(
                "SELECT COALESCE(SUM(completed_qty * rate),0) FROM tasks WHERE employee_id=? AND status='Approved'",
                (e["id"],)
            ).fetchone()[0]
            advance = con.execute(
                "SELECT COALESCE(SUM(amount),0) FROM advances WHERE employee_id=?",
                (e["id"],)
            ).fetchone()[0]
            employee_data.append({
                "id": e["id"], "username": e["username"], "full_name": e["full_name"],
                "earned": earned, "advance": advance
            })
    return page("Owner Dashboard", content, employees=employee_data, tasks=tasks, totals=totals)


@app.route("/owner/employee", methods=["POST"])
@login_required("owner")
def create_employee():
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not full_name or not username or len(password) < 8:
        flash("Name, username and password (at least 8 characters) enter pannunga.")
    else:
        try:
            with connect() as con:
                con.execute(
                    "INSERT INTO users (username, full_name, password_hash, role) VALUES (?, ?, ?, 'employee')",
                    (username, full_name, generate_password_hash(password))
                )
            flash("Employee account created.")
        except sqlite3.IntegrityError:
            flash("Indha username already irukku. Vera username use pannunga.")
    return redirect(url_for("owner_dashboard"))


@app.route("/owner/task", methods=["POST"])
@login_required("owner")
def create_task():
    try:
        employee_id = int(request.form.get("employee_id", ""))
        title = request.form.get("title", "").strip()
        qty = int(request.form.get("assigned_qty", "0"))
        rate = float(request.form.get("rate", "-1"))
        due_date = request.form.get("due_date", "").strip() or None
        if not title or qty < 1 or rate < 0:
            raise ValueError
        with connect() as con:
            employee = con.execute(
                "SELECT id FROM users WHERE id=? AND role='employee'", (employee_id,)
            ).fetchone()
            if not employee:
                flash("Valid employee select pannunga.")
                return redirect(url_for("owner_dashboard"))
            con.execute(
                """INSERT INTO tasks
                (employee_id,title,assigned_qty,rate,due_date,created_at)
                VALUES (?,?,?,?,?,?)""",
                (employee_id, title, qty, rate, due_date, date.today().isoformat())
            )
        flash("Work successfully assigned.")
    except (ValueError, TypeError):
        flash("Quantity and rate correct-a enter pannunga.")
    return redirect(url_for("owner_dashboard"))


@app.route("/owner/approve/<int:task_id>", methods=["POST"])
@login_required("owner")
def approve_task(task_id):
    with connect() as con:
        task = con.execute(
            "SELECT * FROM tasks WHERE id=? AND status='Submitted'", (task_id,)
        ).fetchone()
        if task:
            con.execute("UPDATE tasks SET status='Approved' WHERE id=?", (task_id,))
            flash("Work approved. Employee salary updated.")
        else:
            flash("Submitted task not found or already approved.")
    return redirect(url_for("owner_dashboard"))


@app.route("/owner/advance", methods=["POST"])
@login_required("owner")
def add_advance():
    try:
        employee_id = int(request.form.get("employee_id", ""))
        amount = float(request.form.get("amount", "0"))
        note = request.form.get("note", "").strip()
        if amount <= 0:
            raise ValueError
        with connect() as con:
            employee = con.execute(
                "SELECT id FROM users WHERE id=? AND role='employee'", (employee_id,)
            ).fetchone()
            if not employee:
                flash("Valid employee select pannunga.")
                return redirect(url_for("owner_dashboard"))
            con.execute(
                "INSERT INTO advances (employee_id,amount,note,paid_date) VALUES (?,?,?,?)",
                (employee_id, amount, note, date.today().isoformat())
            )
        flash("Advance saved. Balance salary recalculated.")
    except (ValueError, TypeError):
        flash("Valid advance amount enter pannunga.")
    return redirect(url_for("owner_dashboard"))


@app.route("/employee")
@login_required("employee")
def employee_dashboard():
    user = current_user()
    with connect() as con:
        tasks = con.execute(
            "SELECT * FROM tasks WHERE employee_id=? ORDER BY id DESC",
            (user["id"],)
        ).fetchall()
        earned = con.execute(
            "SELECT COALESCE(SUM(completed_qty * rate),0) FROM tasks WHERE employee_id=? AND status='Approved'",
            (user["id"],)
        ).fetchone()[0]
        advances = con.execute(
            "SELECT COALESCE(SUM(amount),0) FROM advances WHERE employee_id=?",
            (user["id"],)
        ).fetchone()[0]
    content = """
    <h1>Vanakkam, {{ user['full_name'] }}!</h1>
    <p class="muted">Ungalukku assign panna work and unga salary mattum inga theriyum.</p>
    <div class="grid">
      <div class="card"><div class="muted">Approved earnings</div><div class="stat">₹{{ '%.2f'|format(earned) }}</div></div>
      <div class="card"><div class="muted">Advance received</div><div class="stat">₹{{ '%.2f'|format(advances) }}</div></div>
      <div class="card"><div class="muted">Current balance</div><div class="stat">₹{{ '%.2f'|format(earned-advances) }}</div></div>
    </div>
    <section class="card">
      <h2>My Assigned Work</h2>
      <div class="table-wrap"><table>
      <tr><th>Work</th><th>Assigned pieces</th><th>Rate / piece</th><th>Submit completed pieces</th><th>Status</th></tr>
      {% for t in tasks %}
      <tr>
        <td>{{ t['title'] }}<br><small>Due: {{ t['due_date'] or 'Not set' }}</small></td>
        <td>{{ t['assigned_qty'] }}</td><td>₹{{ '%.2f'|format(t['rate']) }}</td>
        <td>
        {% if t['status'] == 'Assigned' %}
          <form method="post" action="{{ url_for('submit_task', task_id=t['id']) }}">
            <input type="number" name="completed_qty" min="0" max="{{ t['assigned_qty'] }}" required placeholder="Pieces done">
            <button type="submit">Submit work</button>
          </form>
        {% else %}{{ t['completed_qty'] }} pieces{% endif %}
        </td>
        <td>{{ t['status'] }}</td>
      </tr>
      {% else %}<tr><td colspan="5">Innum work assign pannala. Owner assign pannadhum inga theriyum.</td></tr>{% endfor %}
      </table></div>
      <p><small>Salary-la count aaguradhu owner approve panna completed pieces mattum.</small></p>
    </section>
    """
    return page("Employee Dashboard", content, user=user, tasks=tasks,
                earned=earned, advances=advances)


@app.route("/employee/submit/<int:task_id>", methods=["POST"])
@login_required("employee")
def submit_task(task_id):
    user = current_user()
    try:
        completed = int(request.form.get("completed_qty", "-1"))
        with connect() as con:
            task = con.execute(
                "SELECT * FROM tasks WHERE id=? AND employee_id=? AND status='Assigned'",
                (task_id, user["id"])
            ).fetchone()
            if not task:
                flash("Indha task submit panna mudiyadhu.")
            elif completed < 0 or completed > task["assigned_qty"]:
                flash("Completed pieces assigned quantity-kulla irukkanum.")
            else:
                con.execute(
                    "UPDATE tasks SET completed_qty=?, status='Submitted' WHERE id=?",
                    (completed, task_id)
                )
                flash("Completed quantity owner approval-ku submit aagiduchu.")
    except ValueError:
        flash("Valid completed quantity enter pannunga.")
    return redirect(url_for("employee_dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
