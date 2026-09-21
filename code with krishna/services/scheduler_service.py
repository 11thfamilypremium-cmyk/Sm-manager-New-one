import logging
from datetime import datetime, timedelta
import pytz
from config import Config
from database import db_session
from models import (
    Customer, Subscription, SubscriptionHistory, InviteLink,
    ChannelMembership, MembershipHistory, AuditLog
)
from services.telegram_service import TelegramService
from services.google_sheets_service import GoogleSheetsService

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

class SchedulerService:

    @staticmethod
    def process_expiries() -> dict:
        """
        Idempotent expiry processor job.
        """
        now = datetime.now(IST)
        expired_subs = db_session.query(Subscription).filter(
            Subscription.status.in_(["ACTIVE", "EXPIRING_SOON"]),
            Subscription.expiry_date <= now
        ).all()

        processed_count = 0
        kicked_count = 0

        for sub in expired_subs:
            try:
                sub.status = "EXPIRED"

                customer = db_session.query(Customer).filter_by(id=sub.customer_id).first()
                if customer:
                    # 1. Kick member from Telegram VIP Channel
                    kicked = TelegramService.kick_member(customer.telegram_id)
                    if kicked:
                        kicked_count += 1

                    # 2. Update Channel Membership
                    m = db_session.query(ChannelMembership).filter_by(customer_id=customer.id).first()
                    if m:
                        m.status = "REMOVED"
                        m.removed_at = now

                    mh = MembershipHistory(
                        customer_id=customer.id,
                        telegram_id=customer.telegram_id,
                        channel_id=Config.TELEGRAM_CHANNEL_ID,
                        event_type="EXPIRED_REMOVAL",
                        event_time=now,
                        details="Removed automatically due to subscription expiry"
                    )
                    db_session.add(mh)

                    # 3. Revoke unused invite links
                    invites = db_session.query(InviteLink).filter_by(customer_id=customer.id, status="CREATED").all()
                    for inv in invites:
                        inv.status = "REVOKED"

                    # 4. Immutable History & Audit Log
                    sh = SubscriptionHistory(
                        customer_id=customer.id,
                        transaction_id=sub.transaction_id,
                        plan_name=sub.plan_name,
                        amount=sub.amount,
                        start_date=sub.start_date,
                        expiry_date=sub.expiry_date,
                        event_type="EXPIRY",
                        created_at=now
                    )
                    db_session.add(sh)

                    audit = AuditLog(
                        actor="SYSTEM",
                        action="SUBSCRIPTION_EXPIRED",
                        entity_type="Customer",
                        entity_id=customer.id,
                        details=f"Subscription expired. Member kicked: {kicked}"
                    )
                    db_session.add(audit)

                    # 5. Telegram Notification
                    msg = (
                        "🔴 <b>Your VIP Subscription Has Expired</b>\n\n"
                        "Your VIP Channel access has ended and membership has been removed.\n\n"
                        "To regain instant access, please renew your subscription below:"
                    )
                    markup = {
                        "inline_keyboard": [
                            [{"text": "🔄 Renew VIP Subscription", "callback_data": "renew"}]
                        ]
                    }
                    TelegramService.send_message(customer.telegram_id, msg, reply_markup=markup)

                    # 6. Google Sheets Sync
                    GoogleSheetsService.queue_event("SUBSCRIPTION_EXPIRED", sub.to_dict())
                    GoogleSheetsService.queue_event("MEMBER_REMOVED", {"customer_id": customer.id, "telegram_id": customer.telegram_id})

                processed_count += 1
            except Exception as e:
                logger.error(f"[SchedulerService] Expiry processing error for sub {sub.id}: {e}")

        db_session.commit()
        return {"processed_subscriptions": processed_count, "members_kicked": kicked_count}

    @staticmethod
    def send_expiry_reminders() -> dict:
        """
        Sends expiry warning messages to active members (7 days, 3 days, 1 day before expiry).
        """
        now = datetime.now(IST)
        active_subs = db_session.query(Subscription).filter(
            Subscription.status.in_(["ACTIVE", "EXPIRING_SOON"]),
            Subscription.expiry_date > now
        ).all()

        reminders_sent = 0

        for sub in active_subs:
            customer = db_session.query(Customer).filter_by(id=sub.customer_id).first()
            if not customer:
                continue

            days_left = (sub.expiry_date.replace(tzinfo=None) - now.replace(tzinfo=None)).days
            
            # Update status badge
            if 0 < days_left <= Config.EXPIRY_WARNING_DAYS:
                sub.status = "EXPIRING_SOON"

            msg = None
            if days_left == 7:
                msg = f"⏳ <b>Reminder:</b> Your VIP subscription expires in <b>7 days</b> ({sub.expiry_date.strftime('%d %b %Y')}). Renew early to avoid interruption!"
            elif days_left == 3:
                msg = f"⏳ <b>Reminder:</b> Your VIP subscription expires in <b>3 days</b> ({sub.expiry_date.strftime('%d %b %Y')}). Click below to renew!"
            elif days_left == 1:
                msg = f"⚠️ <b>Urgent:</b> Your VIP subscription expires <b>tomorrow</b>! Renew now to retain access."

            if msg:
                markup = {
                    "inline_keyboard": [
                        [{"text": "🔄 Renew Subscription Now", "callback_data": "renew"}]
                    ]
                }
                if TelegramService.send_message(customer.telegram_id, msg, reply_markup=markup):
                    reminders_sent += 1

        db_session.commit()
        return {"reminders_sent": reminders_sent}
