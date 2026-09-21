import json
import logging
import requests
from datetime import datetime
import pytz
from config import Config
from models import SyncEvent, Customer, Transaction, SubscriptionHistory, AuditLog
from database import db_session

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

class GoogleSheetsService:

    @staticmethod
    def queue_event(event_type, payload):
        """
        Stores event in sync_events queue table.
        """
        try:
            event = SyncEvent(
                event_type=event_type,
                payload=json.dumps(payload),
                status='PENDING',
                attempt_count=0
            )
            db_session.add(event)
            db_session.commit()
            
            # Immediately attempt sync in non-blocking way
            GoogleSheetsService.process_pending_events()
            return event.id
        except Exception as e:
            db_session.rollback()
            logger.error(f"[GoogleSheetsService] Queue Error: {e}")
            return None

    @staticmethod
    def process_pending_events():
        """
        Sends PENDING / FAILED events to Google Apps Script URL.
        """
        gas_url = Config.GOOGLE_APPS_SCRIPT_URL
        if not gas_url:
            logger.info("[GoogleSheetsService] GOOGLE_APPS_SCRIPT_URL not configured. Sync skipped.")
            return

        pending_events = db_session.query(SyncEvent).filter(
            SyncEvent.status.in_(['PENDING', 'FAILED']),
            SyncEvent.attempt_count < 5
        ).all()

        for event in pending_events:
            try:
                event.attempt_count += 1
                event.last_attempt = datetime.now(IST)
                
                body = {
                    "secret": Config.GOOGLE_APPS_SCRIPT_SECRET,
                    "event_id": event.id,
                    "event_type": event.event_type,
                    "payload": json.loads(event.payload) if isinstance(event.payload, str) else event.payload
                }

                response = requests.post(gas_url, json=body, timeout=10)
                if response.status_code == 200:
                    res_json = response.json()
                    if res_json.get("status") == "success":
                        event.status = 'SYNCED'
                        event.synced_at = datetime.now(IST)
                        event.error_message = None
                    else:
                        event.status = 'FAILED'
                        event.error_message = res_json.get("message", "GAS returned error status")
                else:
                    event.status = 'FAILED'
                    event.error_message = f"HTTP {response.status_code}: {response.text}"

            except Exception as ex:
                event.status = 'FAILED'
                event.error_message = str(ex)

            db_session.commit()

    @staticmethod
    def rebuild_all_sheets():
        """
        Full rebuild of Google Sheets data from operational PostgreSQL DB.
        """
        gas_url = Config.GOOGLE_APPS_SCRIPT_URL
        if not gas_url:
            raise ValueError("GOOGLE_APPS_SCRIPT_URL is not set.")

        customers = [c.to_dict() for c in db_session.query(Customer).all()]
        transactions = [t.to_dict() for t in db_session.query(Transaction).all()]
        subscriptions = [s.to_dict() for s in db_session.query(SubscriptionHistory).all()]

        payload = {
            "customers": customers,
            "transactions": transactions,
            "subscriptions": subscriptions
        }

        body = {
            "secret": Config.GOOGLE_APPS_SCRIPT_SECRET,
            "event_id": f"REBUILD-{int(datetime.now().timestamp())}",
            "event_type": "FULL_REBUILD",
            "payload": payload
        }

        response = requests.post(gas_url, json=body, timeout=30)
        if response.status_code != 200 or response.json().get("status") != "success":
            raise Exception(f"Rebuild failed: {response.text}")

        # Audit log rebuild action
        audit = AuditLog(actor="ADMIN", action="REBUILD_GOOGLE_SHEETS", details="Triggered full rebuild of Google Sheets")
        db_session.add(audit)
        db_session.commit()

        return True
