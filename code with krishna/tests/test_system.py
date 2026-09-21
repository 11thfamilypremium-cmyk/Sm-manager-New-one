import unittest
import os
from datetime import datetime, timedelta
import pytz

# Set test environment
os.environ["DATABASE_URL"] = "sqlite:///data/test_sm_manager.db"
os.environ["TELEGRAM_BOT_TOKEN"] = ""

from database import init_db, db_session, Base, engine
from models import Customer, Transaction, Subscription, InviteLink, ChannelMembership
from services.payment_service import PaymentService
from services.scheduler_service import SchedulerService

IST = pytz.timezone('Asia/Kolkata')

class TestSubscriptionSystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def tearDown(self):
        db_session.remove()

    def test_customer_creation_and_price_override(self):
        # Create customer
        c1 = Customer(telegram_id="1001", first_name="Rahul", username="rahul_vip")
        db_session.add(c1)
        db_session.commit()

        # Check default global price
        self.assertEqual(PaymentService.get_customer_price(c1), 299.0)

        # Set customer-specific custom price override
        c1.custom_price = 249.0
        db_session.commit()

        self.assertEqual(PaymentService.get_customer_price(c1), 249.0)

    def test_payment_submission_and_manual_approval(self):
        c1 = Customer(telegram_id="1002", first_name="Aman")
        db_session.add(c1)
        db_session.commit()

        # 1. Create transaction
        txn = PaymentService.create_pending_transaction(c1, amount=299.0)
        self.assertEqual(txn.payment_status, "PENDING_PAYMENT")

        # 2. Submit UTR
        PaymentService.submit_utr(txn.id, "123456789012")
        self.assertEqual(txn.payment_status, "UTR_SUBMITTED")
        self.assertEqual(txn.utr, "123456789012")

        # 3. Manual Approval
        approved_txn, sub, invite = PaymentService.approve_payment(txn.id, admin_user="ADMIN")
        self.assertEqual(approved_txn.payment_status, "APPROVED")
        self.assertIsNotNone(sub)
        self.assertEqual(sub.status, "ACTIVE")
        self.assertIsNotNone(invite)
        self.assertEqual(invite.status, "CREATED")

        # 4. Idempotency test: approve again should not create duplicate subscription
        approved_txn2, sub2, invite2 = PaymentService.approve_payment(txn.id, admin_user="ADMIN")
        sub_count = db_session.query(Subscription).filter_by(customer_id=c1.id).count()
        self.assertEqual(sub_count, 1)

    def test_active_renewal_extends_expiry(self):
        c1 = Customer(telegram_id="1003", first_name="Rohit")
        db_session.add(c1)
        db_session.commit()

        # Approval 1: 30 days
        txn1 = PaymentService.create_pending_transaction(c1, amount=299.0)
        PaymentService.submit_utr(txn1.id, "UTR111111")
        _, sub1, _ = PaymentService.approve_payment(txn1.id)

        initial_expiry = sub1.expiry_date

        # Renewal approval before expiry
        txn2 = PaymentService.create_pending_transaction(c1, amount=299.0)
        PaymentService.submit_utr(txn2.id, "UTR222222")
        _, sub2, _ = PaymentService.approve_payment(txn2.id)

        # Renewal should extend from existing expiry date
        self.assertEqual(sub2.start_date, initial_expiry)
        expected_expiry = initial_expiry + timedelta(days=30)
        self.assertEqual(sub2.expiry_date, expected_expiry)

    def test_expiry_scheduler(self):
        c1 = Customer(telegram_id="1004", first_name="Vikram")
        db_session.add(c1)
        db_session.commit()

        # Create expired subscription
        now = datetime.now(IST)
        expired_date = now - timedelta(days=1)
        sub = Subscription(
            customer_id=c1.id,
            plan_name="VIP — 30 Days",
            amount=299.0,
            start_date=now - timedelta(days=31),
            expiry_date=expired_date,
            status="ACTIVE"
        )
        db_session.add(sub)
        db_session.commit()

        # Run scheduler
        res = SchedulerService.process_expiries()
        self.assertEqual(res["processed_subscriptions"], 1)

        db_session.refresh(sub)
        self.assertEqual(sub.status, "EXPIRED")

if __name__ == '__main__':
    unittest.main()
