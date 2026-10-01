# GlassLedger 1.0

**Inventory with a memory.**

GlassLedger is a personal, mobile-first inventory, accountability, reporting and inventory-intelligence application built with **Python, Flask, Jinja, SQLite, HTMX-ready server rendering, and the CryoGlass design system**.

## What is implemented

- Secure owner login, inactivity timeout and failed-login throttling
- Short first-run wizard with editable defaults
- Products, categories, units and aliases
- Product-specific multi-unit packaging (Carton → Bag → Pack → Piece, etc.)
- Opening balance, receive, issue, return, damage, expiry, adjustment and physical-count flows
- Batch and expiry tracking with FEFO guidance
- Append-only stock movement history and owner-only audit trail
- Inventory intelligence: consumption trend, days-of-stock forecast, reorder recommendation, safety buffer, expiry-waste risk and anomaly flags
- Intelligent requisitions with editable requested units/quantities
- In-app low-stock, stockout, forecast, expiry, anomaly, backup and hosting reminders
- Daily, tracking, movement, adjustment and monthly-summary reports
- Finalized immutable report snapshots, PDF generation and HTML fallback
- Expiring/revocable external manager links with optional download permission
- SQLite integrity checks, automatic daily local backups, import/download/restore and emergency pre-restore backup
- Optional automatic Google Drive off-site backup
- Responsive CryoGlass desktop sidebar, animated mobile liquid dock and quick transaction menu
- Reduced-motion and lighter mobile behavior
- Railway-ready production files

## Windows quick start

```powershell
cd GlassLedger
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
flask --app run.py init-db
flask --app run.py create-owner
python run.py
```

Open **http://127.0.0.1:5000** and sign in. The onboarding wizard will guide the initial setup.

## Run the verification tests

```powershell
pip install -r requirements-dev.txt
pytest -q
```

The tests cover multi-unit stock math, insufficient-stock protection, reorder intelligence, SQLite backup integrity, login and the inventory page.

## Important inventory rule

GlassLedger does not directly overwrite a product's current quantity. Stock is derived from append-only movements:

`Opening + Received + Returns In + Adjustments In - Issued - Returns Out - Damage - Expiry - Adjustments Out = Current Stock`

Corrections therefore leave an evidence trail instead of silently changing history.

## Google Drive backup

1. Create a Google Cloud service account and enable the Google Drive API.
2. Create a folder in your Google Drive.
3. Share that folder with the service-account email.
4. Store the service-account JSON **outside Git**.
5. Configure `.env`:

```text
GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
GOOGLE_DRIVE_FOLDER_ID=<folder-id>
AUTO_DRIVE_BACKUP=1
```

Manual Drive upload is available in **Settings → Backup & Recovery**. When credentials are configured, GlassLedger also attempts an off-site copy of the daily automatic backup.

## Railway deployment

Mount a persistent Railway volume, for example at `/data`, and configure:

```text
SECRET_KEY=<long-random-secret>
COOKIE_SECURE=1
DATABASE_URL=sqlite:////data/inventory.db
BACKUP_DIR=/data/backups
REPORT_DIR=/data/reports
```

If using Drive backup, also make the service-account credentials available securely and set the Drive environment variables. `railway.json` and `Procfile` are included.

### Resource strategy

GlassLedger is intentionally quiet on the server: no Redis, Celery, WebSockets or constant polling. Intelligence is calculated from SQLite when useful, charts/animations live in the browser, PDFs are generated only on demand, and the daily backup check runs lazily on normal app use.

## Never commit

- `.env`
- `instance/*.db`
- `instance/backups/`
- generated reports
- Google credentials

## Project status

This package is **GlassLedger 1.0**, the complete agreed V1. Offline/PWA sync, multi-branch support, barcode scanning, WhatsApp/email notifications and ML forecasting remain deliberately outside V1.
