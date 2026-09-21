# VIP Telegram Subscription Management System (Sm-manager)

A production-ready VIP Telegram Subscription Management System combining a Telegram customer bot, private channel management, modern SaaS Admin Dashboard, PostgreSQL database, dynamic UPI QR payment generator, single-use invite verification, automated expiry kicking, and idempotent Google Sheets synchronization.

---

## 🌟 Key Features

* **Telegram Customer Bot Engine**: Interactive inline keyboard menu for `/start`, `Subscribe`, `Renew`, `My Subscription`, `Payment Status`, and UTR text submission.
* **Dynamic UPI QR Code Generator**: Generates dynamic QR codes matching the customer's exact price (supports customer-specific price overrides).
* **Strict Manual Payment Approval**: Payments are held as `UTR_SUBMITTED` until manually verified by the admin in the dashboard. Submitting UTR never auto-activates access.
* **Idempotent Approval Logic**:
  * Active customer renewal extends from existing `expiry_date`.
  * Expired or new customer subscription starts from current business date (`Asia/Kolkata`).
* **Single-Use Invite Link Security**: Generates Telegram invite links with `member_limit=1`. Validates joining user ID against assigned Telegram ID; kicks unauthorized users automatically.
* **Automated Expiry & Member Kick Engine**: Protected `/jobs/process-expiries` endpoint (and background scheduler) automatically bans/kicks expired members, revokes invites, logs audit history, and notifies users.
* **SaaS Admin Dashboard**:
  * Real-time KPI Overview (Active members, Expiring soon, Expired, Revenue, Pending payments).
  * Pending Payments review table with instant `Approve` and `Reject` actions.
  * Customer management with search and status filters.
  * Per-customer custom pricing overrides and manual expiry extensions (+Days).
  * **Rebuild Google Sheets** button for 1-click full database export to Google Sheets.
  * System & Admin Audit Logs.
* **Google Sheets Persistent Archive**: Event-driven webhook sync to Google Apps Script (`Code.gs`) with `event_id` idempotency protection across 7 spreadsheet tabs.

---

## 🚀 Setup & Installation

### 1. Local Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Run app locally
python app.py
```
Open `http://localhost:5000/admin` (Default credentials: `admin` / `admin123`).

### 2. Google Apps Script Setup
1. Create a Google Sheet.
2. Go to **Extensions -> Apps Script**.
3. Copy contents of `google-apps-script/Code.gs` into the editor.
4. Click **Deploy -> New deployment -> Web app**.
   * Execute as: **Me**
   * Who has access: **Anyone**
5. Copy the Web App URL and set as `GOOGLE_APPS_SCRIPT_URL`.

### 3. Telegram Webhook Setup
Set your webhook URL using Telegram API:
```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://<YOUR_RENDER_URL>/telegram/webhook"
```

### 4. Render Deployment
The repository includes `render.yaml` and `Procfile` configured for root deployment:
* **Build Command**: `pip install -r requirements.txt`
* **Start Command**: `gunicorn app:app --workers=2 --threads=4 --timeout=120`
* **Health Check Endpoint**: `/health`
* **Cron Trigger Endpoint**: `POST /jobs/process-expiries?secret=<CRON_SECRET>`
