from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import os
import smtplib
import ssl
import secrets
import bcrypt
from email.message import EmailMessage
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text, or_, func
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
import sys
import re

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def get_database_uri():
    # On Vercel: prefer external DB when DATABASE_URL is provided,
    # otherwise fall back to /tmp sqlite.
    is_vercel = bool((os.getenv("VERCEL") or "").strip())
    force_sqlite_on_vercel = (os.getenv("FORCE_SQLITE_ON_VERCEL") or "false").strip().lower() == "true"
    database_url = (os.getenv("DATABASE_URL") or "").strip()

    if is_vercel and (force_sqlite_on_vercel or not database_url):
        return "sqlite:////tmp/users.db"

    if not database_url:
        # Vercel serverless runtime allows writes only in /tmp.
        return "sqlite:////tmp/users.db"
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    if database_url.startswith("postgresql://") and "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"
    return database_url

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.config['SECRET_KEY'] = (os.getenv('SECRET_KEY') or secrets.token_hex(32)).strip()
app.config['SQLALCHEMY_DATABASE_URI'] = get_database_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgresql"):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "pool_pre_ping": True,
        "pool_recycle": 180,
        "connect_args": {"connect_timeout": 10},
    }
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = (os.getenv('SESSION_COOKIE_SECURE') or 'false').strip().lower() == 'true'

raw_origins = (os.getenv("FRONTEND_ORIGIN") or "*").strip()
allowed_origins = "*" if raw_origins == "*" else [o.strip() for o in raw_origins.split(",") if o.strip()]
API_BASE_URL = (os.getenv("API_BASE_URL") or "").strip().rstrip("/")
CORS(
    app,
    resources={
        r"/contact": {"origins": allowed_origins},
        r"/forgot-password": {"origins": allowed_origins},
        r"/reset-password": {"origins": allowed_origins},
    },
    methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

db = SQLAlchemy(app)


# -------- USER MODEL --------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)
    password = db.Column(db.String(255), nullable=False)
    otp = db.Column(db.String(6), nullable=True)

    def set_password(self, password):
        self.password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        stored = self.password or ""
        if stored.startswith("$2a$") or stored.startswith("$2b$") or stored.startswith("$2y$"):
            try:
                return bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8'))
            except ValueError:
                return False
        return check_password_hash(stored, password)


class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=True)
    message = db.Column(db.Text, nullable=False)


def initialize_database_safely():
    try:
        with app.app_context():
            db.create_all()
            try:
                # SQLite-only migration path; PostgreSQL will skip this block.
                user_columns = [row[1] for row in db.session.execute(text("PRAGMA table_info(user)")).fetchall()]
                if "email" not in user_columns:
                    db.session.execute(text("ALTER TABLE user ADD COLUMN email VARCHAR(255)"))
                if "password" not in user_columns:
                    db.session.execute(text("ALTER TABLE user ADD COLUMN password VARCHAR(255)"))
                if "otp" not in user_columns:
                    db.session.execute(text("ALTER TABLE user ADD COLUMN otp VARCHAR(6)"))
                if "password_hash" in user_columns:
                    db.session.execute(text("UPDATE user SET password = password_hash WHERE password IS NULL"))
                db.session.commit()
            except Exception:
                pass
    except Exception as e:
        app.logger.exception("Database initialization skipped due to startup error: %s", e)


initialize_database_safely()
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CONTACT_RECIPIENT = (os.getenv("CONTACT_RECIPIENT") or "").strip()
SMTP_EMAIL = (os.getenv("EMAIL") or "").strip()
SMTP_APP_PASSWORD = (os.getenv("APP_PASSWORD") or "").strip()
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL") or CONTACT_RECIPIENT or SMTP_EMAIL).strip()


def is_valid_email(value):
    if not value:
        return False
    return bool(EMAIL_PATTERN.match(value.strip().lower()))


def is_valid_password(value, min_length=6):
    if not value:
        return False
    return len(value.strip()) >= min_length


def validate_contact_payload(name, email, message):
    if not email or not message:
        return False, "Email and message are required."
    if not is_valid_email(email):
        return False, "Please enter a valid email address."
    if len(name) > 120:
        return False, "Name is too long."
    if len(message) < 5 or len(message) > 5000:
        return False, "Message must be between 5 and 5000 characters."
    return True, ""


def send_email(to_email, subject, body_text, reply_to=None):
    if not SMTP_EMAIL or not SMTP_APP_PASSWORD:
        return False, "Missing EMAIL or APP_PASSWORD in environment."
    try:
        email = EmailMessage()
        email["Subject"] = subject
        email["From"] = SMTP_EMAIL
        email["To"] = to_email
        if reply_to:
            email["Reply-To"] = reply_to
        email.set_content(body_text)
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=20) as server:
            server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
            server.send_message(email)
        return True, ""
    except Exception as e:
        return False, f"Gmail SMTP send failed: {e}"


def send_contact_email(name, sender_email, message):
    if not ADMIN_EMAIL:
        return False, "Missing admin destination email."
    email_subject = f"TruthLens Contact Message from {name}"
    email_body = f"New contact form submission\n\nName: {name}\nEmail: {sender_email or 'Not provided'}\n\nMessage:\n{message}"
    return send_email(ADMIN_EMAIL, email_subject, email_body, reply_to=sender_email or None)


def send_password_reset_email(recipient_email, otp_code):
    email_subject = "TruthLens Password Reset OTP"
    email_body = f"We received a password reset request for your TruthLens account.\n\nYour OTP code (valid for 10 minutes): {otp_code}\n\nIf you did not request this reset, you can safely ignore this email."
    return send_email(recipient_email, email_subject, email_body)


def wants_json_response():
    accept_header = (request.headers.get("Accept") or "").lower()
    return request.is_json or "application/json" in accept_header


def contact_response(success, message, status_code=200, form_data=None):
    if wants_json_response():
        payload = {"success": success, "message": message}
        return jsonify(payload), status_code
    form_data = form_data or {}
    return render_template(
        "contact.html",
        status_type="success" if success else "error",
        status_message=message,
        form_name=form_data.get("name", ""),
        form_email=form_data.get("email", ""),
        form_message=form_data.get("message", ""),
    ), status_code


def auth_response(template_name, success, message, status_code=200, form_data=None, extra_context=None):
    if wants_json_response():
        payload = {"success": success, "message": message}
        return jsonify(payload), status_code
    form_data = form_data or {}
    context = {
        "status_type": "success" if success else "error",
        "status_message": message,
        "form_identifier": form_data.get("identifier", ""),
        "form_otp": form_data.get("otp", ""),
    }
    if extra_context:
        context.update(extra_context)
    return render_template(template_name, **context), status_code


@app.context_processor
def inject_frontend_config():
    return {"api_base_url": API_BASE_URL}


# -------- ROUTES --------

@app.route('/healthz')
def healthz():
    return jsonify({"ok": True}), 200

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template("home.html")


@app.route('/analyze')
def analyze():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template("index.html")


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not identifier or not password:
            return render_template(
                "login.html",
                status_type="error",
                status_message="Username and password are required."
            )
        identifier_lc = identifier.lower()
        user = None
        try:
            user = User.query.filter(
                or_(func.lower(User.username) == identifier_lc, func.lower(User.email) == identifier_lc)
            ).first()
        except SQLAlchemyError as e:
            app.logger.warning("Primary DB login query failed, trying local fallback: %s", e)

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('home'))

        return render_template(
            "login.html",
            status_type="error",
            status_message="Invalid username or password.",
            form_username=identifier,
            show_forgot=True
        )
    return render_template("login.html")


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = (request.form.get('email') or request.form.get('identifier') or '').strip().lower()
        otp_action = (request.form.get('otp_action') or 'send').strip().lower()
        otp_code = (request.form.get('otp') or '').strip()
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            email = (payload.get('email') or '').strip().lower()
            otp_action = (payload.get('otp_action') or otp_action).strip().lower()
            otp_code = (payload.get('otp') or otp_code).strip()

        form_data = {"identifier": email, "otp": otp_code}
        if not email:
            return auth_response("forgot_password.html", False, "Please enter your email address.", 400, form_data)
        if not is_valid_email(email):
            return auth_response("forgot_password.html", False, "Please enter a valid email address.", 400, form_data)
        user = User.query.filter(func.lower(User.email) == email).first()
        generic_msg = "If an account with a verified email exists, an OTP has been sent."

        if otp_action == 'verify':
            if not otp_code:
                return auth_response(
                    "forgot_password.html",
                    False,
                    "Enter the OTP you received.",
                    400,
                    {"identifier": email, "otp": ""},
                    extra_context={"otp_step": True},
                )
            if not user or not user.email or not user.otp or user.otp != otp_code:
                return auth_response(
                    "forgot_password.html",
                    False,
                    "Invalid OTP. Please request a new one.",
                    400,
                    {"identifier": email, "otp": otp_code},
                    extra_context={"otp_step": True},
                )
            return redirect(url_for('reset_password', email=email, otp=otp_code))

        if not user or not user.email:
            return auth_response(
                "forgot_password.html",
                True,
                generic_msg,
                200,
                {"identifier": email, "otp": ""},
                extra_context={"otp_step": False},
            )

        otp_code = f"{secrets.randbelow(1000000):06d}"
        user.otp = otp_code
        db.session.commit()
        email_sent, email_error = send_password_reset_email(user.email, otp_code)
        if not email_sent:
            user.otp = None
            app.logger.warning("Password reset email failed for user_id=%s: %s", user.id, email_error)
            db.session.commit()
            return auth_response(
                "forgot_password.html",
                False,
                "We could not send the OTP email. Please try again.",
                500,
                {"identifier": email, "otp": ""},
                extra_context={"otp_step": False},
            )
        return auth_response(
            "forgot_password.html",
            True,
            "OTP sent. Enter the OTP below on this page to continue.",
            200,
            {"identifier": email, "otp": ""},
            extra_context={"otp_step": True},
        )
    return render_template("forgot_password.html", otp_step=False)


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = (request.form.get('email') or request.form.get('identifier') or '').strip().lower()
        otp_code = request.form.get('otp', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            email = (payload.get('email') or '').strip().lower()
            otp_code = (payload.get('otp') or '').strip()
            new_password = (payload.get('new_password') or '').strip()
            confirm_password = (payload.get('confirm_password') or '').strip()
        form_data = {"identifier": email, "otp": otp_code}
        if not email or not otp_code or not new_password or not confirm_password:
            return auth_response("reset_password.html", False, "All fields are required.", 400, form_data)
        if not is_valid_email(email):
            return auth_response("reset_password.html", False, "Please enter a valid email address.", 400, form_data)
        if not otp_code.isdigit() or len(otp_code) != 6:
            return auth_response("reset_password.html", False, "OTP must be a 6-digit code.", 400, form_data)
        if not is_valid_password(new_password):
            return auth_response("reset_password.html", False, "Password must be at least 6 characters.", 400, form_data)
        if new_password != confirm_password:
            return auth_response("reset_password.html", False, "Passwords do not match.", 400, form_data)
        user = User.query.filter(func.lower(User.email) == email).first()
        if not user:
            return auth_response("reset_password.html", False, "Invalid reset details. Please request a new OTP.", 400, form_data)
        if not user.otp or user.otp != otp_code:
            return auth_response("reset_password.html", False, "Invalid OTP. Please request a new one.", 400, form_data)
        user.set_password(new_password)
        user.otp = None
        db.session.commit()
        return auth_response(
            "reset_password.html",
            True,
            "Password reset successful. Redirecting to login...",
            200,
            form_data={"identifier": "", "otp": ""},
            extra_context={"redirect_url": url_for('login')},
        )
    email = (request.args.get('email') or '').strip().lower()
    otp_code = (request.args.get('otp') or '').strip()
    return render_template("reset_password.html", form_identifier=email, form_otp=otp_code)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not username or not email or not password or not confirm_password:
            return render_template(
                "register.html",
                status_type="error",
                status_message="All fields are required.",
                form_username=username,
                form_email=email,
            )
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
            return render_template(
                "register.html",
                status_type="error",
                status_message="Please provide a valid email address.",
                form_username=username,
                form_email=email,
            )
        if not is_valid_password(password):
            return render_template(
                "register.html",
                status_type="error",
                status_message="Password must be at least 6 characters.",
                form_username=username,
                form_email=email,
            )
        if password != confirm_password:
            return render_template(
                "register.html",
                status_type="error",
                status_message="Passwords do not match.",
                form_username=username,
                form_email=email,
            )

        try:
            if User.query.filter_by(username=username).first():
                return render_template(
                    "register.html",
                    status_type="error",
                    status_message="Username already exists.",
                    form_username=username,
                    form_email=email,
                )
            if User.query.filter_by(email=email).first():
                return render_template(
                    "register.html",
                    status_type="error",
                    status_message="Email already registered.",
                    form_username=username,
                    form_email=email,
                )

            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            app.logger.exception("Registration database error: %s", e)
            return render_template(
                "register.html",
                status_type="error",
                status_message="Registration failed due to a database issue. Please try again.",
                form_username=username,
                form_email=email,
            ), 503
        except Exception as e:
            db.session.rollback()
            app.logger.exception("Registration unexpected error: %s", e)
            return render_template(
                "register.html",
                status_type="error",
                status_message="Something went wrong while creating your account. Please try again.",
                form_username=username,
                form_email=email,
            ), 500

        return render_template(
            "register.html",
            status_type="success",
            status_message="Registration successful! Redirecting to login...",
            form_username="",
            form_email="",
            redirect_url=url_for('login')
        )
    return render_template("register.html")


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/about')
def about():
    return render_template("about.html")


@app.route('/contact', methods=['GET', 'POST', 'OPTIONS'])
def contact():
    if request.method == 'OPTIONS':
        return '', 204
    if request.method == 'GET':
        return render_template("contact.html")
    if request.method == 'POST':
        payload = request.get_json(silent=True) if request.is_json else None
        name = ((payload or {}).get('name') or request.form.get('name') or 'Website User').strip()
        sender_email = ((payload or {}).get('email') or request.form.get('email') or '').strip().lower()
        message = ((payload or {}).get('message') or request.form.get('message') or '').strip()
        form_data = {"name": name, "email": sender_email, "message": message}
        is_valid_contact, contact_error = validate_contact_payload(name, sender_email, message)
        if not is_valid_contact:
            return contact_response(False, contact_error, status_code=400, form_data=form_data)
        email_sent = False
        try:
            contact_record = Contact(email=sender_email, message=message)
            db.session.add(contact_record)
            db.session.flush()
            email_sent, email_error = send_contact_email(name, sender_email, message)
            if not email_sent:
                app.logger.warning("Contact email delivery failed for message_id=%s: %s", contact_record.id, email_error)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.exception("Contact DB save failed, trying email-only fallback: %s", e)
            email_sent, email_error = send_contact_email(name, sender_email, message)
            if not email_sent:
                app.logger.warning("Contact fallback email delivery also failed: %s", email_error)
                return contact_response(
                    False,
                    "Failed to process your message. Please try again.",
                    status_code=500,
                    form_data=form_data,
                )
        if email_sent:
            status_message = "Message sent successfully. We will get back to you soon."
        else:
            status_message = "Message received successfully. We will get back to you soon."
        return contact_response(True, status_message, status_code=200, form_data={})
    return contact_response(False, "Method not allowed.", status_code=405)


@app.route('/predict', methods=['POST'])
def predict():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template(
        "index.html",
        status_type="error",
        status_message="Prediction is disabled on Vercel free serverless due to size limits. Deploy backend on Render/Railway to enable full ML analysis.",
    )
