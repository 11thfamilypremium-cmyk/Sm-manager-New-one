import os
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from config import Config

class DBService:
    def __init__(self):
        self.use_google_sheets = False
        self.sheet = None
        self.init_db()

    def init_db(self):
        """Initializes Google Sheets or sets up local JSON database fallback."""
        Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not Config.LOCAL_DB_FILE.exists():
            with open(Config.LOCAL_DB_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)

        # Attempt to connect to Google Sheets
        try:
            import gspread
            from oauth2client.service_account import ServiceAccountCredentials

            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]

            creds = None
            if Config.GOOGLE_SHEETS_CREDENTIALS_JSON:
                # Loaded from Environment variable (Render cloud deployment)
                creds_dict = json.loads(Config.GOOGLE_SHEETS_CREDENTIALS_JSON)
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            elif os.path.exists(Config.GOOGLE_CREDENTIALS_FILE):
                # Loaded from local credentials.json file
                creds = ServiceAccountCredentials.from_json_keyfile_name(Config.GOOGLE_CREDENTIALS_FILE, scope)

            if creds:
                client = gspread.authorize(creds)
                try:
                    self.sheet = client.open(Config.GOOGLE_SHEET_NAME).sheet1
                except Exception:
                    # Create the sheet if it doesn't exist
                    spreadsheet = client.create(Config.GOOGLE_SHEET_NAME)
                    self.sheet = spreadsheet.sheet1
                    # Add headers
                    self.sheet.append_row([
                        "Order ID", "Telegram Username", "Telegram User ID", "Amount (INR)",
                        "UTR / Txn ID", "Status", "Duration (Days)", "Created At",
                        "Approved At", "Expiry Date", "Invite Link", "Notes"
                    ])
                self.use_google_sheets = True
                print(">>> [DBService] Connected to Google Sheets successfully!")
                return
        except Exception as e:
            print(f">>> [DBService] Google Sheets not configured or failed to connect ({e}). Using local JSON fallback.")

        self.use_google_sheets = False

    def _read_local_db(self) -> list:
        if not Config.LOCAL_DB_FILE.exists():
            return []
        try:
            with open(Config.LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_local_db(self, records: list):
        with open(Config.LOCAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, default=str)

    def _sync_record_to_sheet(self, record: dict):
        """Appends or updates a record in Google Sheets if active."""
        if not self.use_google_sheets or not self.sheet:
            return
        try:
            row_data = [
                record.get("order_id", ""),
                record.get("telegram_username", ""),
                record.get("telegram_user_id", ""),
                record.get("amount", 0),
                record.get("utr_number", ""),
                record.get("status", ""),
                record.get("duration_days", 30),
                record.get("created_at", ""),
                record.get("approved_at", ""),
                record.get("expiry_date", ""),
                record.get("invite_link", ""),
                record.get("notes", "")
            ]
            
            # Find row with same order_id
            cell = self.sheet.find(record.get("order_id"))
            if cell:
                # Update existing row
                row_idx = cell.row
                for col_idx, val in enumerate(row_data, start=1):
                    self.sheet.update_cell(row_idx, col_idx, str(val))
            else:
                self.sheet.append_row(row_data)
        except Exception as e:
            print(f">>> [DBService] Failed to sync to Google Sheets: {e}")

    def create_order(self, telegram_username: str, amount: float, duration_days: int = 30, notes: str = "") -> dict:
        username = telegram_username.strip()
        if not username.startswith("@"):
            username = f"@{username}"

        order_id = "ORD-" + uuid.uuid4().hex[:10].upper()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        record = {
            "order_id": order_id,
            "telegram_username": username,
            "telegram_user_id": "",
            "amount": float(amount),
            "utr_number": "",
            "status": "pending_payment",  # pending_payment, pending_approval, active, expired, rejected
            "duration_days": int(duration_days),
            "created_at": now_str,
            "approved_at": "",
            "expiry_date": "",
            "invite_link": "",
            "notes": notes
        }

        records = self._read_local_db()
        records.insert(0, record)
        self._write_local_db(records)
        self._sync_record_to_sheet(record)
        return record

    def get_order(self, order_id: str) -> dict:
        records = self._read_local_db()
        for r in records:
            if r.get("order_id") == order_id:
                return r
        return None

    def get_all_orders(self) -> list:
        records = self._read_local_db()
        now = datetime.now()
        
        # Calculate dynamic days remaining for active members
        for r in records:
            if r.get("status") == "active" and r.get("expiry_date"):
                try:
                    exp_dt = datetime.strptime(r["expiry_date"], "%Y-%m-%d %H:%M:%S")
                    diff = exp_dt - now
                    r["days_remaining"] = max(0, diff.days)
                    r["is_expiring_soon"] = 0 <= diff.days <= 3
                except Exception:
                    r["days_remaining"] = 0
                    r["is_expiring_soon"] = False
            else:
                r["days_remaining"] = 0
                r["is_expiring_soon"] = False

        return records

    def submit_utr(self, order_id: str, utr_number: str, telegram_user_id: str = "") -> dict:
        records = self._read_local_db()
        updated_record = None
        for r in records:
            if r.get("order_id") == order_id:
                r["utr_number"] = utr_number.strip()
                if telegram_user_id:
                    r["telegram_user_id"] = str(telegram_user_id).strip()
                r["status"] = "pending_approval"
                r["submitted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                updated_record = r
                break

        if updated_record:
            self._write_local_db(records)
            self._sync_record_to_sheet(updated_record)
        return updated_record

    def approve_order(self, order_id: str, invite_link: str = "", telegram_user_id: str = "") -> dict:
        records = self._read_local_db()
        updated_record = None
        now = datetime.now()

        for r in records:
            if r.get("order_id") == order_id:
                duration = r.get("duration_days", 30)
                expiry_dt = now + timedelta(days=duration)
                
                r["status"] = "active"
                r["approved_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
                r["expiry_date"] = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")
                if invite_link:
                    r["invite_link"] = invite_link
                if telegram_user_id:
                    r["telegram_user_id"] = str(telegram_user_id)
                updated_record = r
                break

        if updated_record:
            self._write_local_db(records)
            self._sync_record_to_sheet(updated_record)
        return updated_record

    def reject_order(self, order_id: str, reason: str = "Invalid Payment / UTR") -> dict:
        records = self._read_local_db()
        updated_record = None
        for r in records:
            if r.get("order_id") == order_id:
                r["status"] = "rejected"
                r["notes"] = f"Rejected: {reason}"
                updated_record = r
                break

        if updated_record:
            self._write_local_db(records)
            self._sync_record_to_sheet(updated_record)
        return updated_record

    def expire_or_kick_member(self, order_id: str, reason: str = "30-Day Expiry Completed") -> dict:
        records = self._read_local_db()
        updated_record = None
        for r in records:
            if r.get("order_id") == order_id:
                r["status"] = "expired"
                r["notes"] = reason
                updated_record = r
                break

        if updated_record:
            self._write_local_db(records)
            self._sync_record_to_sheet(updated_record)
        return updated_record

    def extend_membership(self, order_id: str, extra_days: int = 30) -> dict:
        records = self._read_local_db()
        updated_record = None
        now = datetime.now()

        for r in records:
            if r.get("order_id") == order_id:
                # If currently expired or active, calculate from max(now, current_expiry)
                try:
                    current_exp = datetime.strptime(r["expiry_date"], "%Y-%m-%d %H:%M:%S")
                    base_date = max(now, current_exp)
                except Exception:
                    base_date = now

                new_expiry = base_date + timedelta(days=extra_days)
                r["expiry_date"] = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
                r["status"] = "active"
                r["notes"] = f"Extended by {extra_days} days on {now.strftime('%Y-%m-%d')}"
                updated_record = r
                break

        if updated_record:
            self._write_local_db(records)
            self._sync_record_to_sheet(updated_record)
        return updated_record

    def get_expired_due_members(self) -> list:
        """Returns active members whose expiry_date is in the past."""
        records = self._read_local_db()
        now = datetime.now()
        due_members = []

        for r in records:
            if r.get("status") == "active" and r.get("expiry_date"):
                try:
                    exp_dt = datetime.strptime(r["expiry_date"], "%Y-%m-%d %H:%M:%S")
                    if exp_dt <= now:
                        due_members.append(r)
                except Exception:
                    pass
        return due_members

    def get_metrics(self) -> dict:
        records = self.get_all_orders()
        total_revenue = sum(r.get("amount", 0) for r in records if r.get("status") in ["active", "expired"])
        active_count = sum(1 for r in records if r.get("status") == "active")
        pending_count = sum(1 for r in records if r.get("status") == "pending_approval")
        expiring_soon_count = sum(1 for r in records if r.get("is_expiring_soon", False))
        expired_count = sum(1 for r in records if r.get("status") == "expired")

        return {
            "total_revenue": total_revenue,
            "active_members": active_count,
            "pending_approvals": pending_count,
            "expiring_soon": expiring_soon_count,
            "expired_members": expired_count,
            "is_using_google_sheets": self.use_google_sheets
        }
