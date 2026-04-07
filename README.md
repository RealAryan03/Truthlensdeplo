# TruthLens - Credibility Analyzer

TruthLens is a Flask web app that analyzes article credibility using:
- A trained ML model (Logistic Regression + TF-IDF)
- Google Fact Check API lookups
- A Contact Us form with database-backed message storage
- Password reset links with one-time tokens

## Important Contact Us Behavior

Contact and password reset are resilient:
- User messages are always saved to the database first.
- Email delivery uses Gmail SMTP via environment variables.
- If delivery fails, users still receive a stable success response.
- Email failure details are stored internally for diagnostics.

This means deployments can run on local SQLite or managed cloud databases.

## 1) Prerequisites

- Python 3.10+ (recommended)
- pip
- Internet access (for optional API checks and optional SMTP mail delivery)

## 2) Clone and Open

1. Clone this repository.
2. Open the project folder in VS Code.

## 3) Create and Activate Virtual Environment

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 4) Install Dependencies

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## 5) Configure Environment Variables

Copy the example file and edit values:

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### macOS/Linux

```bash
cp .env.example .env
```

Required and optional values are documented in `.env.example`.

For Contact Us + Forgot Password to be fully functional in production, set:
- `SECRET_KEY` (required)
- `DATABASE_URL` (required for shared cloud database; if omitted uses local SQLite)
- `EMAIL` (your Gmail address used to send emails)
- `APP_PASSWORD` (Gmail App Password)
- `ADMIN_EMAIL` or `CONTACT_RECIPIENT` (where contact messages are delivered)

Optional but recommended:
- `FACT_CHECK_API_KEY` for Google Fact Check integration

Forgot Password now sends a 6-digit OTP to the user's registered email.

## 6) Run the App

```bash
python app.py
```

Open:
- http://127.0.0.1:5000

## Deployment: Render + Vercel

### Backend (Render)

- Start command: `gunicorn app:app`
- Procfile is included with: `web: gunicorn app:app`
- Set environment variables in Render:
	- `EMAIL`
	- `APP_PASSWORD`
	- `ADMIN_EMAIL`
	- `CONTACT_RECIPIENT`
	- `FRONTEND_ORIGIN` (your Vercel domain, e.g. `https://your-app.vercel.app`)

### Frontend (Vercel)

- Set `API_BASE_URL` to your deployed backend URL (for example `https://truthlens.onrender.com`).
- Forms for contact/forgot/reset/predict automatically route to this base URL when set.
- If your frontend uses fetch/axios, point all API calls to `${API_BASE_URL}/contact`, `${API_BASE_URL}/forgot-password`, and `${API_BASE_URL}/reset-password`.

## 7) Verify Contact Us in a Fresh Clone

1. Open Contact page.
2. Submit Name + Message (Email optional).
3. Confirm success message appears.
4. Confirm message is stored in SQLite database at `instance/users.db` table `contact_message`.

## Gmail SMTP Notes

If Gmail SMTP is configured correctly in `.env`:
- Contact message is saved AND email is sent.

Gmail setup:
- Enable 2-Step Verification
- Generate an App Password
- Put Gmail in `EMAIL` and App Password in `APP_PASSWORD`

## Cloud Database Notes

- For Render/Railway/Fly.io/Globe-like platforms, use a managed Postgres URL in `DATABASE_URL`.
- The app auto-detects `postgres://` and converts it to `postgresql://`.
- Local development still works with SQLite when `DATABASE_URL` is unset.

## Password Reset OTP Notes

- Password reset uses secure one-time OTPs valid for 10 minutes.
- OTPs are hashed before storage and invalidated after use.

If SMTP is missing or fails:
- Contact message is still saved.
- User still sees success response.
- Failure reason is captured in `email_error` in the database.

## Security Note

Do not commit real credentials in `.env`.
Use `.env.example` as the template and keep secrets local only.
