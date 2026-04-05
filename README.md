# TruthLens - Credibility Analyzer

TruthLens is a Flask web app that analyzes article credibility using:
- A trained ML model (Logistic Regression + TF-IDF)
- Google Fact Check API lookups
- A Contact Us form with database-backed message storage

## Important Contact Us Behavior

Contact form submissions are now resilient:
- User messages are always saved to the database first.
- If SMTP/email delivery fails, users still receive a success message.
- Email failure details are stored internally for diagnostics.

This means fresh clones can use Contact Us even without SMTP configured.

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

For password reset emails on other devices/networks, set:
- `RESET_LINK_BASE_URL` to your reachable app URL (example: `https://your-domain.com` or your tunnel URL)

## 6) Run the App

```bash
python app.py
```

Open:
- http://127.0.0.1:5000

## 7) Verify Contact Us in a Fresh Clone

1. Open Contact page.
2. Submit Name + Message (Email optional).
3. Confirm success message appears.
4. Confirm message is stored in SQLite database at `instance/users.db` table `contact_message`.

## SMTP Notes (Optional)

If SMTP is configured correctly in `.env`:
- Contact message is saved AND email is sent.

## Password Reset Link Notes

- Password reset uses secure one-time email links.
- If links open as localhost/LAN and fail on another device, set `RESET_LINK_BASE_URL` in `.env`.
- Example for tunnel testing: `RESET_LINK_BASE_URL=https://<your-ngrok-subdomain>.ngrok-free.app`

If SMTP is missing or fails:
- Contact message is still saved.
- User still sees success response.
- Failure reason is captured in `email_error` in the database.

## Security Note

Do not commit real credentials in `.env`.
Use `.env.example` as the template and keep secrets local only.
