import logging
from datetime import datetime, timedelta
import pytz
from config import Config
from database import db_session
from models import (
    Customer, Transaction, Subscription, SubscriptionHistory,
    InviteLink, AuditLog
)
from services.google_sheets_service import GoogleSheetsService
from services.telegram_service import TelegramService

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

class PaymentService:

    @staticmethod
    def get_customer_price(customer: Customer) -> float:
        """
        Returns customer-specific price if configured, otherwise default global price.
        """
        if customer.custom_price is not None and customer.custom_price > 0:
            return float(customer.custom_price)
        return float(Config.DEFAULT_PRICE)

    @staticmethod
    def create_pending_transaction(customer: Customer, amount: float = None, plan_name: str = "VIP — 30 Days", duration_days: int = 30) -> Transaction:
        if amount is None:
            amount = PaymentService.get_customer_price(customer)

        now = datetime.now(IST)
        txn_count = db_session.query(Transaction).count() + 1
        txn_id = f"TXN-{now.strftime('%Y%m%d')}-{txn_count:04d}"

        txn = Transaction(
            id=txn_id,
            customer_id=customer.id,
            telegram_id=customer.telegram_id,
            amount=amount,
            currency="INR",
            payment_status="PENDING_PAYMENT",
            plan_name=plan_name,
            duration_days=duration_days,
            created_at=now
        )
        db_session.add(txn)
        db_session.commit()

        # Audit log & Google Sync
        audit = AuditLog(actor="CUSTOMER", action="TRANSACTION_CREATED", entity_type="Transaction", entity_id=txn.id, details=f"Amount: ₹{amount}")
        db_session.add(audit)
        db_session.commit()

        GoogleSheetsService.queue_event("TRANSACTION_CREATED", txn.to_dict())
        return txn

    @staticmethod
    def submit_utr(transaction_id: str, utr: str, screenshot_url: str = None) -> Transaction:
        txn = db_session.query(Transaction).filter_by(id=transaction_id).first()
        if not txn:
            raise ValueError("Transaction not found")

        now = datetime.now(IST)
        txn.utr = utr.strip()
        txn.payment_status = "UTR_SUBMITTED"
        txn.submitted_at = now
        if screenshot_url:
            txn.screenshot_url = screenshot_url

        db_session.commit()

        # Audit log & Google Sync
        audit = AuditLog(actor="CUSTOMER", action="UTR_SUBMITTED", entity_type="Transaction", entity_id=txn.id, details=f"UTR: {utr}")
        db_session.add(audit)
        db_session.commit()

        GoogleSheetsService.queue_event("PAYMENT_SUBMITTED", txn.to_dict())
        return txn

    @staticmethod
    def approve_payment(transaction_id: str, admin_user: str = "ADMIN") -> tuple:
        """
        Idempotent Payment Approval.
        """
        txn = db_session.query(Transaction).filter_by(id=transaction_id).first()
        if not txn:
            raise ValueError("Transaction not found")

        # Idempotency check: if already approved, do not create duplicate subscription
        if txn.payment_status == "APPROVED":
            existing_sub = db_session.query(Subscription).filter_by(transaction_id=txn.id).first()
            existing_invite = db_session.query(InviteLink).filter_by(customer_id=txn.customer_id, status="CREATED").first()
            return txn, existing_sub, existing_invite

        now = datetime.now(IST)
        txn.payment_status = "APPROVED"
        txn.approved_at = now
        txn.verified_by = admin_user

        customer = db_session.query(Customer).filter_by(id=txn.customer_id).first()

        # Renewal Date Logic:
        # Check active subscription where expiry_date > now
        active_sub = db_session.query(Subscription).filter(
            Subscription.customer_id == customer.id,
            Subscription.status.in_(["ACTIVE", "EXPIRING_SOON"]),
            Subscription.expiry_date > now
        ).order_by(Subscription.expiry_date.desc()).first()

        duration = txn.duration_days or 30
        if active_sub:
            # Active customer: extend from existing expiry date
            start_date = active_sub.expiry_date
            new_expiry = active_sub.expiry_date + timedelta(days=duration)
            event_type = "RENEWAL"
        else:
            # Expired or new customer: start from current date
            start_date = now
            new_expiry = now + timedelta(days=duration)
            event_type = "NEW_SUBSCRIPTION"

        subscription = Subscription(
            customer_id=customer.id,
            transaction_id=txn.id,
            plan_name=txn.plan_name,
            amount=txn.amount,
            start_date=start_date,
            expiry_date=new_expiry,
            status="ACTIVE",
            created_at=now
        )
        db_session.add(subscription)

        # Historical Record (Immutable)
        history = SubscriptionHistory(
            customer_id=customer.id,
            transaction_id=txn.id,
            plan_name=txn.plan_name,
            amount=txn.amount,
            start_date=start_date,
            expiry_date=new_expiry,
            event_type=event_type,
            created_at=now
        )
        db_session.add(history)
        db_session.commit()

        # Generate Telegram Single-Use Invite Link (member_limit=1)
        invite_data = TelegramService.create_single_use_invite(customer.telegram_id)
        invite_url = invite_data.get("invite_link", "")

        invite = InviteLink(
            customer_id=customer.id,
            telegram_id=customer.telegram_id,
            invite_url=invite_url,
            created_at=now,
            expires_at=now + timedelta(days=2), # Link expires in 48h
            status="CREATED"
        )
        db_session.add(invite)
        db_session.commit()

        # Notify Customer on Telegram
        TelegramService.send_approval_notification(
            telegram_id=customer.telegram_id,
            plan_name=txn.plan_name,
            duration=f"{duration} Days",
            amount=txn.amount,
            invite_url=invite_url,
            expiry_date=new_expiry.strftime('%d %b %Y')
        )

        # Audit log & Google Sync
        audit = AuditLog(
            actor=admin_user,
            action="PAYMENT_APPROVED",
            entity_type="Transaction",
            entity_id=txn.id,
            details=f"Approved ₹{txn.amount}. Expiry: {new_expiry.strftime('%Y-%m-%d')}"
        )
        db_session.add(audit)
        db_session.commit()

        GoogleSheetsService.queue_event("PAYMENT_APPROVED", txn.to_dict())
        GoogleSheetsService.queue_event("SUBSCRIPTION_CREATED", history.to_dict())
        GoogleSheetsService.queue_event("INVITE_CREATED", invite.to_dict())

        return txn, subscription, invite

    @staticmethod
    def reject_payment(transaction_id: str, admin_user: str = "ADMIN", reason: str = "UTR could not be verified.") -> Transaction:
        txn = db_session.query(Transaction).filter_by(id=transaction_id).first()
        if not txn:
            raise ValueError("Transaction not found")

        now = datetime.now(IST)
        txn.payment_status = "REJECTED"
        txn.rejected_at = now
        txn.verified_by = admin_user
        txn.rejection_reason = reason
        db_session.commit()

        customer = db_session.query(Customer).filter_by(id=txn.customer_id).first()

        # Notify Customer on Telegram
        TelegramService.send_rejection_notification(
            telegram_id=customer.telegram_id,
            transaction_id=txn.id,
            reason=reason
        )

        # Audit log & Google Sync
        audit = AuditLog(actor=admin_user, action="PAYMENT_REJECTED", entity_type="Transaction", entity_id=txn.id, details=f"Reason: {reason}")
        db_session.add(audit)
        db_session.commit()

        GoogleSheetsService.queue_event("PAYMENT_REJECTED", txn.to_dict())
        return txn
