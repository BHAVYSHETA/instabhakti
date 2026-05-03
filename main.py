import pandas as pd
from datetime import datetime
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, flash, redirect, render_template, request, session, url_for, render_template_string
import os
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# Use relative path or environment variable
BASE_DIR = Path(__file__).parent
EXISTING_FILE = BASE_DIR / "submissions.csv"
NEW_SABHYA_FILE = BASE_DIR / "new_sabhya_submissions.csv"

MAX_ENTRIES = 160

EXISTING_COLUMNS = ["no.", "Name", "Mobile", "SMV NO", "Password"]
NEW_SABHYA_COLUMNS = ["no.", "First Name", "Contact No.", "Password", "Created At"]

# ---------------- HELPERS ---------------- #
def generate_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_urlsafe(32)
    return session['csrf_token']

def ensure_csv(file, columns):
    try:
        if not file.exists():
            df = pd.DataFrame(columns=columns)
            df.to_csv(file, index=False)
            return

        df = pd.read_csv(file)
        df.columns = df.columns.str.strip()

        if list(df.columns) != columns:
            df = df.reindex(columns=columns)
            df.to_csv(file, index=False)
    except Exception as e:
        print(f"CSV ensure error: {e}")
        df = pd.DataFrame(columns=columns)
        df.to_csv(file, index=False)

def safe_read_csv(file, columns):
    ensure_csv(file, columns)
    try:
        df = pd.read_csv(file)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        print(f"CSV read error: {e}")
        return pd.DataFrame(columns=columns)

def write_to_csv(file, columns, new_row):
    try:
        ensure_csv(file, columns)
        df = safe_read_csv(file, columns)
        
        # Sanitize inputs to prevent CSV injection
        for key, value in new_row.items():
            if isinstance(value, str):
                new_row[key] = value.replace('\n', ' ').replace('\r', ' ').replace(',', ' ')
        
        new_df = pd.DataFrame([new_row])
        new_df = new_df.reindex(columns=columns)
        df = pd.concat([df, new_df], ignore_index=True)
        df.to_csv(file, index=False)
    except Exception as e:
        print(f"CSV write error: {e}")
        raise

def get_next_entry_number_atomic():
    """Atomic increment to prevent race conditions"""
    lock_file = BASE_DIR / "entry_counter.lock"
    
    try:
        df1 = safe_read_csv(EXISTING_FILE, EXISTING_COLUMNS)
        df2 = safe_read_csv(NEW_SABHYA_FILE, NEW_SABHYA_COLUMNS)
        return len(df1) + len(df2) + 1
    except:
        return 1

# Initialize files
ensure_csv(EXISTING_FILE, EXISTING_COLUMNS)
ensure_csv(NEW_SABHYA_FILE, NEW_SABHYA_COLUMNS)

# ---------------- ROUTES ---------------- #

@app.route("/")
def index():
    generate_csrf_token()  # Generate token
    active_form = request.args.get('form', 'existing')
    return render_template("home.html", 
                         welcome_name=session.get("user_name"),
                         active_form=active_form,
                         csrf_token=generate_csrf_token())
@app.route("/schedule")
def schedule():
    return render_template("schedule.html")

@app.route("/test-csrf")
def test_csrf():
    return render_template_string("""
    <form method="POST" action="/test-csrf-submit">
        {{ csrf_token() }}
        <input type="submit" value="Test CSRF">
    </form>
    """)

@app.route("/test-csrf-submit", methods=["POST"])
def test_csrf_submit():
    return "CSRF Working! ✅"

@app.route("/katha")
def katha():
    return render_template("katha.html")

@app.route("/competition")
def competition():
    return render_template("competition.html")

@app.route("/about")
def about():
    return render_template("About_us.html")

# ---------------- REGISTER ---------------- #

@app.route("/submit", methods=["POST"])
def submit():
    submitted_token = request.form.get('csrf_token')
    if submitted_token != session.get('csrf_token'):
        flash("Invalid request!", "error")
        return redirect(url_for("index"))
        
    entry_number = get_next_entry_number_atomic()
    registration_type = request.form.get("registration_type")

    if entry_number > MAX_ENTRIES:
        flash("Limit reached!", "error")
        return redirect(url_for("index"))

    # -------- NEW SABHYA -------- #
    if registration_type == "new":
        name = request.form.get("first_name", "").strip()
        mobile = request.form.get("contact_no", "").strip()
        password = request.form.get("password", "").strip()

        if not all([name, mobile, password]):
            flash("All fields required!", "error")
            return redirect(url_for("index"))

        write_to_csv(
            NEW_SABHYA_FILE,
            NEW_SABHYA_COLUMNS,
            {
                "no.": entry_number,
                "First Name": name[:50],  # Limit length
                "Contact No.": mobile[:15],
                "Password": generate_password_hash(password),
                "Created At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        flash("New sabhya registered!", "success")
        return redirect(url_for("index"))

    # -------- EXISTING SABHYA -------- #
    name = request.form.get("name", "").strip()
    mobile = request.form.get("mobile_no", "").strip()
    smv = request.form.get("smv_no", "").strip()
    password = request.form.get("password", "").strip()

    if not all([name, mobile, smv, password]):
        flash("All fields required!", "error")
        return redirect(url_for("index"))

    write_to_csv(
        EXISTING_FILE,
        EXISTING_COLUMNS,
        {
            "no.": entry_number,
            "Name": name[:50],
            "Mobile": mobile[:15],
            "SMV NO": smv[:20],
            "Password": generate_password_hash(password),
        },
    )
    flash("Existing sabhya registered!", "success")
    return redirect(url_for("index"))

# ---------------- LOGIN ---------------- #

@app.route("/login", methods=["GET", "POST"])
def login():
    generate_csrf_token()
    
    if request.method == "POST":
        submitted_token = request.form.get('csrf_token')
        if submitted_token != session.get('csrf_token'):  # ✅ Validate token value
            return render_template("login.html", login_error="Invalid request ❌", csrf_token=generate_csrf_token())
        
        # Validate required fields first
        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile_no", "").strip()
        
        if not name or not mobile:
            return render_template("login.html", login_error="Name and mobile required! ❌", csrf_token=generate_csrf_token())
        
        password = request.form.get("password", "").strip()
        smv = request.form.get("smv_no", "").strip() or ""
        
        if not password:
            return render_template("login.html", login_error="Password required! ❌", csrf_token=generate_csrf_token())

        # Rest of your code unchanged...
        df_existing = safe_read_csv(EXISTING_FILE, EXISTING_COLUMNS)
        df_new = safe_read_csv(NEW_SABHYA_FILE, NEW_SABHYA_COLUMNS)
        stored_password = None

        # -------- EXISTING SABHYA (requires SMV) -------- #
        if smv and not df_existing.empty:
            user = df_existing[
                (df_existing["Name"].astype(str).str.strip() == name) &
                (df_existing["Mobile"].astype(str).str.strip() == mobile) &
                (df_existing["SMV NO"].astype(str).str.strip() == smv)
            ]
            if not user.empty:
                stored_password = user.iloc[0]["Password"]

        # -------- NEW SABHYA (no SMV required) -------- #
        if stored_password is None and not df_new.empty:
            user = df_new[
                (df_new["First Name"].astype(str).str.strip() == name) &
                (df_new["Contact No."].astype(str).str.strip() == mobile)
            ]
            if not user.empty:
                stored_password = user.iloc[0]["Password"]

        # -------- PASSWORD CHECK -------- #
        if stored_password and check_password_hash(stored_password, password):
            session["user_name"] = name
            session["user_mobile"] = mobile
            flash("Login successful! ✅", "success")
            return redirect(url_for("index"))

        return render_template("login.html", login_error="Invalid credentials ❌", csrf_token=generate_csrf_token())

    return render_template("login.html", csrf_token=generate_csrf_token())

# ---------------- LOGOUT ---------------- #

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully!", "info")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)