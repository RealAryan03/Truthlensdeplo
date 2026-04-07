from flask import Flask, render_template, request, redirect, session, url_for
import requests
import spacy
import os
import smtplib
import ssl
import re
import secrets
import hashlib
from email.message import EmailMessage
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
from datetime import datetime, timezone, timedelta
from backend.bert_model import get_bert_score
import pickle

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-in-env')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# -------- USER MODEL --------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    sender_email = db.Column(db.String(255), nullable=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    email_sent = db.Column(db.Boolean, nullable=False, default=False)
    email_error = db.Column(db.Text, nullable=True)


class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='password_reset_tokens')


# Create database tables
with app.app_context():
    db.create_all()

    # Backward-compatible schema update for existing SQLite DBs.
    user_columns = [row[1] for row in db.session.execute(text("PRAGMA table_info(user)")).fetchall()]
    if "email" not in user_columns:
        db.session.execute(text("ALTER TABLE user ADD COLUMN email VARCHAR(255)"))
        db.session.commit()



API_KEY = os.getenv("FACT_CHECK_API_KEY")

if not API_KEY:
    pass

CONTACT_RECIPIENT = "zackryder38056@gmail.com"
SMTP_SENDER_EMAIL = (os.getenv("SMTP_SENDER_EMAIL") or "").strip()
SMTP_SENDER_PASSWORD = (os.getenv("SMTP_SENDER_PASSWORD") or "").strip()
SMTP_HOST = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
SMTP_PORT = int((os.getenv("SMTP_PORT") or "465").strip())
SMTP_USE_TLS = (os.getenv("SMTP_USE_TLS") or "false").strip().lower() == "true"

BACKUP_SMTP_SENDER_EMAIL = (os.getenv("BACKUP_SMTP_SENDER_EMAIL") or "").strip()
BACKUP_SMTP_SENDER_PASSWORD = (os.getenv("BACKUP_SMTP_SENDER_PASSWORD") or "").strip()
BACKUP_SMTP_HOST = (os.getenv("BACKUP_SMTP_HOST") or SMTP_HOST).strip()
BACKUP_SMTP_PORT = int((os.getenv("BACKUP_SMTP_PORT") or str(SMTP_PORT)).strip())
BACKUP_SMTP_USE_TLS = (os.getenv("BACKUP_SMTP_USE_TLS") or str(SMTP_USE_TLS).lower()).strip().lower() == "true"
RESET_LINK_BASE_URL = (os.getenv("RESET_LINK_BASE_URL") or "").strip().rstrip("/")

# Load ML model + vectorizer

# model = pickle.load(open("model.pkl", "rb"))
# vectorizer = pickle.load(open("vectorizer.pkl", "rb"))

model = pickle.load(open("model_ml.pkl", "rb"))
vectorizer = pickle.load(open("vectorizer_ml.pkl", "rb"))


# Load spaCy model
nlp = spacy.load("en_core_web_sm")


# ---------------- NLP ----------------
def extract_main_sentences(text, n=3):
    doc = nlp(text)
    sentences = list(doc.sents)

    sentence_scores = {}

    for sent in sentences:
        score = 0
        for token in sent:
            if token.pos_ in ["NOUN", "PROPN", "VERB"]:
                score += 1
        
        sentence_scores[sent.text] = score

    ranked = sorted(sentence_scores, key=sentence_scores.get, reverse=True)
    return ranked[:n]


# ---------------- API ----------------
def check_fact_api(text):
    url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

    params = {
        "query": text[:300],
        "key": API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()

        if "claims" in data:
            claim = data["claims"][0]
            rating = claim["claimReview"][0]["textualRating"]

            if "false" in rating.lower():
                return "False"
            elif "true" in rating.lower():
                return "True"
            else:
                return "Uncertain"

        return "No Data"

    except Exception as e:
        print("API Error:", e)
        return "No Data"


# ---------------- HELPERS ----------------
def final_api_decision(results):
    if "False" in results:
        return "False"
    elif "True" in results:
        return "True"
    else:
        return "No Data"


def adjust_score(ml_score, api_result):
    if api_result == "False":
        return ml_score - 20
    elif api_result == "True":
        return ml_score + 10
    else:
        return ml_score


def generate_explanation(ml_score, bert_score, api_result):
    """
    Generates a textual explanation of the credibility analysis
    using BERT score and API result.
    
    ml_score: percentage (0-100) or None if not used
    bert_score: percentage (0-100)
    api_result: "True", "False", or "No Data"
    """
    explanation = []

    # ML-based explanation (only if ML score is provided)
    if ml_score is not None:
        if ml_score > 70:
            explanation.append("The article uses formal and structured language (ML model analysis).")
        else:
            explanation.append("The article shows patterns often seen in misleading content (ML model analysis).")

    # BERT-based explanation
    if bert_score > 70:
        explanation.append("DistilBERT model predicts the article is likely authentic.")
    elif bert_score < 40:
        explanation.append("DistilBERT model indicates the article might be misleading.")
    else:
        explanation.append("DistilBERT model shows moderate confidence; the article may require further verification.")

    # API-based explanation
    if api_result == "False":
        explanation.append("Fact-checking sources indicate the claim is false.")
    elif api_result == "True":
        explanation.append("Fact-checking sources confirm the claim is true.")
    else:
        explanation.append("No verified fact-check data found.")

    return explanation


def send_contact_email(name, sender_email, message):
    smtp_configs = []
    if SMTP_SENDER_EMAIL and SMTP_SENDER_PASSWORD:
        smtp_configs.append({
            "label": "primary",
            "host": SMTP_HOST,
            "port": SMTP_PORT,
            "use_tls": SMTP_USE_TLS,
            "sender_email": SMTP_SENDER_EMAIL,
            "sender_password": SMTP_SENDER_PASSWORD,
        })

    if BACKUP_SMTP_SENDER_EMAIL and BACKUP_SMTP_SENDER_PASSWORD:
        smtp_configs.append({
            "label": "backup",
            "host": BACKUP_SMTP_HOST,
            "port": BACKUP_SMTP_PORT,
            "use_tls": BACKUP_SMTP_USE_TLS,
            "sender_email": BACKUP_SMTP_SENDER_EMAIL,
            "sender_password": BACKUP_SMTP_SENDER_PASSWORD,
        })

    if not smtp_configs:
        return False, "No SMTP credentials configured. Set primary or backup SMTP credentials in .env"

    last_error = ""

    for cfg in smtp_configs:
        for attempt in range(1, 4):
            try:
                email = EmailMessage()
                email["Subject"] = f"TruthLens Contact Message from {name}"
                email["From"] = cfg["sender_email"]
                email["To"] = CONTACT_RECIPIENT
                if sender_email:
                    email["Reply-To"] = sender_email

                email.set_content(
                    f"New contact form submission\n\n"
                    f"Name: {name}\n"
                    f"Email: {sender_email or 'Not provided'}\n\n"
                    f"Message:\n{message}"
                )

                context = ssl.create_default_context()
                if cfg["use_tls"]:
                    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
                        server.starttls(context=context)
                        server.login(cfg["sender_email"], cfg["sender_password"])
                        server.send_message(email)
                else:
                    with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=15) as server:
                        server.login(cfg["sender_email"], cfg["sender_password"])
                        server.send_message(email)
                return True, ""
            except Exception as e:
                last_error = f"{cfg['label']} SMTP attempt {attempt} failed: {e}"

    return False, f"All SMTP delivery attempts failed. Last error: {last_error}"


def send_password_reset_email(recipient_email, reset_url):
    smtp_configs = []
    if SMTP_SENDER_EMAIL and SMTP_SENDER_PASSWORD:
        smtp_configs.append({
            "label": "primary",
            "host": SMTP_HOST,
            "port": SMTP_PORT,
            "use_tls": SMTP_USE_TLS,
            "sender_email": SMTP_SENDER_EMAIL,
            "sender_password": SMTP_SENDER_PASSWORD,
        })

    if BACKUP_SMTP_SENDER_EMAIL and BACKUP_SMTP_SENDER_PASSWORD:
        smtp_configs.append({
            "label": "backup",
            "host": BACKUP_SMTP_HOST,
            "port": BACKUP_SMTP_PORT,
            "use_tls": BACKUP_SMTP_USE_TLS,
            "sender_email": BACKUP_SMTP_SENDER_EMAIL,
            "sender_password": BACKUP_SMTP_SENDER_PASSWORD,
        })

    if not smtp_configs:
        return False, "No SMTP credentials configured."

    last_error = ""
    for cfg in smtp_configs:
        for attempt in range(1, 4):
            try:
                email = EmailMessage()
                email["Subject"] = "TruthLens Password Reset"
                email["From"] = cfg["sender_email"]
                email["To"] = recipient_email
                email.set_content(
                    "We received a password reset request for your TruthLens account.\n\n"
                    f"Reset link (valid for 30 minutes):\n{reset_url}\n\n"
                    "If you did not request this reset, you can safely ignore this email."
                )

                context = ssl.create_default_context()
                if cfg["use_tls"]:
                    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
                        server.starttls(context=context)
                        server.login(cfg["sender_email"], cfg["sender_password"])
                        server.send_message(email)
                else:
                    with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=15) as server:
                        server.login(cfg["sender_email"], cfg["sender_password"])
                        server.send_message(email)
                return True, ""
            except Exception as e:
                last_error = f"{cfg['label']} SMTP attempt {attempt} failed: {e}"

    return False, f"All SMTP delivery attempts failed. Last error: {last_error}"


def hash_reset_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def utc_now():
    return datetime.now(timezone.utc)


def normalize_utc(dt_value):
    if dt_value is None:
        return None
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=timezone.utc)
    return dt_value.astimezone(timezone.utc)


def build_reset_url(raw_token):
    if RESET_LINK_BASE_URL:
        return f"{RESET_LINK_BASE_URL}/reset-password/{raw_token}"
    return url_for('reset_password', token=raw_token, _external=True)


# ---------------- ROUTES ----------------

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
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            return render_template(
                "login.html",
                status_type="error",
                status_message="Username and password are required."
            )

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('home'))
        else:
            return render_template(
                "login.html",
                status_type="error",
                status_message="Invalid username or password.",
                form_username=username,
                show_forgot=True
            )

    return render_template("login.html")


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()

        if not identifier:
            return render_template(
                "forgot_password.html",
                status_type="error",
                status_message="Please enter your username or email.",
                form_identifier=identifier,
            )

        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()

        # Keep response generic to avoid username/email enumeration.
        generic_msg = "If an account with a verified email exists, a reset link has been sent."

        if not user or not user.email:
            return render_template(
                "forgot_password.html",
                status_type="success",
                status_message=generic_msg,
                form_identifier="",
            )

        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_reset_token(raw_token)
        reset_entry = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=utc_now() + timedelta(minutes=30),
            used=False,
        )
        db.session.add(reset_entry)
        db.session.commit()

        reset_url = build_reset_url(raw_token)
        email_sent, email_error = send_password_reset_email(user.email, reset_url)

        if not email_sent:
            reset_entry.used = True
            db.session.commit()

        return render_template(
            "forgot_password.html",
            status_type="success",
            status_message=generic_msg,
            form_identifier="",
        )

    return render_template("forgot_password.html")


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    token_hash = hash_reset_token(token)
    reset_entry = PasswordResetToken.query.filter_by(token_hash=token_hash, used=False).first()
    now = utc_now()
    expires_at = normalize_utc(reset_entry.expires_at) if reset_entry else None

    if not reset_entry or not expires_at or expires_at < now:
        return render_template(
            "reset_password.html",
            status_type="error",
            status_message="This reset link is invalid or has expired. Please request a new one.",
            token_valid=False,
        )

    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not new_password or not confirm_password:
            return render_template(
                "reset_password.html",
                status_type="error",
                status_message="All fields are required.",
                token_valid=True,
                token=token,
            )

        if len(new_password) < 6:
            return render_template(
                "reset_password.html",
                status_type="error",
                status_message="Password must be at least 6 characters.",
                token_valid=True,
                token=token,
            )

        if new_password != confirm_password:
            return render_template(
                "reset_password.html",
                status_type="error",
                status_message="Passwords do not match.",
                token_valid=True,
                token=token,
            )

        reset_entry.user.set_password(new_password)
        reset_entry.used = True

        # Invalidate any other active reset links for the same account.
        PasswordResetToken.query.filter(
            PasswordResetToken.user_id == reset_entry.user_id,
            PasswordResetToken.used == False,
            PasswordResetToken.id != reset_entry.id,
        ).update({"used": True})

        db.session.commit()

        return render_template(
            "reset_password.html",
            status_type="success",
            status_message="Password reset successful. Redirecting to login...",
            token_valid=False,
            redirect_url=url_for('login')
        )

    return render_template("reset_password.html", token_valid=True, token=token)


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

        email_pattern = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
        if not re.match(email_pattern, email):
            return render_template(
                "register.html",
                status_type="error",
                status_message="Please provide a valid email address.",
                form_username=username,
                form_email=email,
            )

        if len(password) < 6:
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


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        sender_email = request.form.get('email', '').strip()
        message = request.form.get('message', '').strip()

        if not name or not message:
            return render_template(
                "contact.html",
                status_type="error",
                status_message="Please provide your name and message.",
                form_name=name,
                form_email=sender_email,
                form_message=message,
            )

        contact_record = ContactMessage(
            name=name,
            sender_email=sender_email or None,
            message=message,
        )
        db.session.add(contact_record)

        email_sent, email_error = send_contact_email(name, sender_email, message)
        contact_record.email_sent = email_sent
        contact_record.email_error = email_error or None
        db.session.commit()

        if email_sent:
            status_message = "Message sent successfully. We will get back to you soon."
        else:
            # Keep UX stable for users even if SMTP provider is temporarily unavailable.
            status_message = "Message received successfully. Our team has been notified and will get back to you soon."

        return render_template(
            "contact.html",
            status_type="success",
            status_message=status_message,
            form_name="",
            form_email="",
            form_message="",
        )

    return render_template("contact.html")


@app.route('/predict', methods=['POST'])
def predict():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    article = request.form['article']

    # -------- ML Prediction (0.4 weight) --------
    article_vec = vectorizer.transform([article])
    ml_score = model.predict_proba(article_vec)[0][1]  # 0-1
    ml_score_percent = ml_score * 100

    # -------- BERT Prediction (0.5 weight) --------
    bert_score = get_bert_score(article)  # 0-1
    bert_score_percent = bert_score * 100

    # -------- Extract key sentences for API --------
    main_sentences = extract_main_sentences(article)
    api_results = []
    for sent in main_sentences:
        if len(sent) < 300:
            result = check_fact_api(sent)
            api_results.append(result)

    # Final API decision (TRUE / FALSE / NO DATA)
    api_result = final_api_decision(api_results)

    # Convert API result to weight (0.1 weight)
    api_score_map = {"True": 1, "False": 0, "No Data": 0.5}
    api_score = api_score_map.get(api_result, 0.5)  # default 0.5 if unknown

    # -------- Final Combined Credibility Score --------
    final_score = 0.5 * bert_score_percent + 0.4 * ml_score_percent + 0.1 * (api_score * 100)

    # -------- Explanation --------
    explanation = generate_explanation(ml_score_percent, bert_score_percent, api_result)

    return render_template("index.html",
                           ml_score=round(ml_score_percent, 2),
                           bert_score=round(bert_score_percent, 2),
                           api_result=api_result,
                           final_score=round(final_score, 2),
                           explanation=explanation)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)