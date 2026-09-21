import logging
import requests
from datetime import datetime
import pytz
from config import Config
from database import db_session
from models import (
    Customer, Transaction, Subscription, InviteLink,
    ChannelMembership, MembershipHistory, AuditLog
)
from services.upi_service import UPIService
from services.google_sheets_service import GoogleSheetsService

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

class TelegramService:

    @staticmethod
    def get_api_url(method: str) -> str:
        return f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/{method}"

    @staticmethod
    def test_connection() -> dict:
        if not Config.TELEGRAM_BOT_TOKEN:
            return {"status": "error", "message": "TELEGRAM_BOT_TOKEN is not set"}
        try:
            res = requests.get(TelegramService.get_api_url("getMe"), timeout=5)
            if res.status_code == 200 and res.json().get("ok"):
                bot_info = res.json().get("result", {})
                return {"status": "ok", "bot_username": bot_info.get("username"), "first_name": bot_info.get("first_name")}
            return {"status": "error", "message": res.text}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def send_message(chat_id: str, text: str, reply_markup: dict = None, parse_mode: str = "HTML") -> bool:
        if not Config.TELEGRAM_BOT_TOKEN:
            logger.warning("TELEGRAM_BOT_TOKEN missing. Cannot send message.")
            return False

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            res = requests.post(TelegramService.get_api_url("sendMessage"), json=payload, timeout=10)
            return res.status_code == 200 and res.json().get("ok", False)
        except Exception as e:
            logger.error(f"[TelegramService] send_message error: {e}")
            return False

    @staticmethod
    def send_photo(chat_id: str, photo_base64_or_url: str, caption: str, reply_markup: dict = None) -> bool:
        if not Config.TELEGRAM_BOT_TOKEN:
            return False

        payload = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            if photo_base64_or_url.startswith("data:image"):
                # Decode base64 PNG
                header, encoded = photo_base64_or_url.split(",", 1)
                import base64
                img_data = base64.b64decode(encoded)
                files = {"photo": ("qr.png", img_data, "image/png")}
                res = requests.post(TelegramService.get_api_url("sendPhoto"), data=payload, files=files, timeout=10)
            else:
                payload["photo"] = photo_base64_or_url
                res = requests.post(TelegramService.get_api_url("sendPhoto"), json=payload, timeout=10)

            return res.status_code == 200 and res.json().get("ok", False)
        except Exception as e:
            logger.error(f"[TelegramService] send_photo error: {e}")
            return False

    @staticmethod
    def create_single_use_invite(telegram_id: str) -> dict:
        """
        Creates single-use invite link (member_limit=1).
        """
        channel_id = Config.TELEGRAM_CHANNEL_ID
        if not channel_id or not Config.TELEGRAM_BOT_TOKEN:
            logger.warning("Channel ID or Bot Token missing for creating invite link.")
            return {"invite_link": "https://t.me/placeholder_vip_channel"}

        payload = {
            "chat_id": channel_id,
            "member_limit": 1,
            "name": f"VIP Access - {telegram_id}"
        }
        try:
            res = requests.post(TelegramService.get_api_url("createChatInviteLink"), json=payload, timeout=10)
            if res.status_code == 200 and res.json().get("ok"):
                result = res.json().get("result", {})
                return {"invite_link": result.get("invite_link")}
            logger.error(f"[TelegramService] createChatInviteLink error: {res.text}")
            return {"invite_link": "https://t.me/placeholder_vip_channel"}
        except Exception as e:
            logger.error(f"[TelegramService] create_single_use_invite exception: {e}")
            return {"invite_link": "https://t.me/placeholder_vip_channel"}

    @staticmethod
    def kick_member(telegram_id: str) -> bool:
        """
        Kicks/bans and unbans a member from private channel to remove them.
        """
        channel_id = Config.TELEGRAM_CHANNEL_ID
        if not channel_id or not Config.TELEGRAM_BOT_TOKEN:
            return False

        try:
            # Ban member
            ban_res = requests.post(TelegramService.get_api_url("banChatMember"), json={
                "chat_id": channel_id,
                "user_id": int(telegram_id),
                "revoke_messages": False
            }, timeout=10)
            
            # Unban immediately so they can re-join later if they renew
            requests.post(TelegramService.get_api_url("unbanChatMember"), json={
                "chat_id": channel_id,
                "user_id": int(telegram_id),
                "only_if_banned": True
            }, timeout=10)

            return ban_res.status_code == 200 and ban_res.json().get("ok", False)
        except Exception as e:
            logger.error(f"[TelegramService] kick_member exception: {e}")
            return False

    @staticmethod
    def send_approval_notification(telegram_id: str, plan_name: str, duration: str, amount: float, invite_url: str, expiry_date: str):
        text = (
            "✅ <b>Payment Approved!</b>\n\n"
            "Your VIP subscription has been activated.\n\n"
            f"📋 Plan: <b>{plan_name}</b>\n"
            f"⏳ Duration: <b>{duration}</b>\n"
            f"💳 Amount: <b>₹{amount:.2f}</b>\n"
            f"📅 Expiry Date: <b>{expiry_date}</b>\n\n"
            "Your secure, single-use VIP Channel access link is ready below:\n"
            "<i>(Click the button below to join)</i>"
        )
        markup = {
            "inline_keyboard": [
                [{"text": "🔐 JOIN VIP CHANNEL", "url": invite_url}],
                [{"text": "📊 My Subscription", "callback_data": "my_subscription"}]
            ]
        }
        TelegramService.send_message(telegram_id, text, reply_markup=markup)

    @staticmethod
    def send_rejection_notification(telegram_id: str, transaction_id: str, reason: str):
        text = (
            "❌ <b>Payment Could Not Be Verified</b>\n\n"
            f"Transaction ID: <b>{transaction_id}</b>\n"
            f"Reason: <i>{reason}</i>\n\n"
            f"Please contact support if you believe this is an error: {Config.SUPPORT_USERNAME}"
        )
        markup = {
            "inline_keyboard": [
                [{"text": "🔄 Try Again / Renew", "callback_data": "subscribe"}],
                [{"text": "❓ Contact Support", "url": f"https://t.me/{Config.SUPPORT_USERNAME.lstrip('@')}"}]
            ]
        }
        TelegramService.send_message(telegram_id, text, reply_markup=markup)

    @staticmethod
    def process_webhook_update(update: dict):
        """
        Main Webhook Update Processor.
        """
        now = datetime.now(IST)

        # 1. Handle Member Join / Leave Chat Updates
        if "chat_member" in update:
            TelegramService._handle_chat_member_update(update["chat_member"])
            return

        # 2. Handle Message Updates
        message = update.get("message")
        callback_query = update.get("callback_query")

        if callback_query:
            TelegramService._handle_callback_query(callback_query)
            return

        if not message:
            return

        from_user = message.get("from", {})
        telegram_id = str(from_user.get("id"))
        text = message.get("text", "").strip()

        # Get or create customer
        customer = db_session.query(Customer).filter_by(telegram_id=telegram_id).first()
        if not customer:
            customer = Customer(
                telegram_id=telegram_id,
                username=from_user.get("username"),
                first_name=from_user.get("first_name"),
                last_name=from_user.get("last_name"),
                created_at=now,
                last_activity=now
            )
            db_session.add(customer)
            db_session.commit()
            GoogleSheetsService.queue_event("CUSTOMER_CREATED", customer.to_dict())
        else:
            customer.username = from_user.get("username")
            customer.first_name = from_user.get("first_name")
            customer.last_name = from_user.get("last_name")
            customer.last_activity = now
            db_session.commit()

        # Handle /start Command
        if text.startswith("/start"):
            TelegramService._send_main_menu(customer)
            return

        # Handle UTR Text Submission
        pending_txn = db_session.query(Transaction).filter_by(
            customer_id=customer.id,
            payment_status="PENDING_PAYMENT"
        ).order_by(Transaction.created_at.desc()).first()

        if pending_txn and (text.isdigit() or len(text) >= 6):
            from services.payment_service import PaymentService
            PaymentService.submit_utr(pending_txn.id, text)
            
            confirm_msg = (
                "✅ <b>Payment Details Received!</b>\n\n"
                "Your UTR has been submitted successfully.\n\n"
                f"💳 Amount: <b>₹{pending_txn.amount:.2f}</b>\n"
                f"🔢 UTR: <b>{text}</b>\n"
                "📋 Status: <b>🟡 Under Verification</b>\n\n"
                "Our admin will verify your payment and approve your VIP access shortly.\n\n"
                "Once approved, you will automatically receive your VIP Channel access link here.\n\n"
                "⏳ <i>Please wait for approval. Payment submitted ≠ access activated.</i>"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "💳 Check Payment Status", "callback_data": "payment_status"}],
                    [{"text": "❓ Contact Support", "url": f"https://t.me/{Config.SUPPORT_USERNAME.lstrip('@')}"}]
                ]
            }
            TelegramService.send_message(telegram_id, confirm_msg, reply_markup=markup)
            return

        # Fallback response
        TelegramService._send_main_menu(customer)

    @staticmethod
    def _send_main_menu(customer: Customer):
        text = (
            f"👋 Welcome <b>{customer.first_name or 'VIP Member'}</b>!\n\n"
            "⭐ <b>VIP Telegram Subscription Manager</b> ⭐\n\n"
            "Get instant access to our exclusive Premium/VIP Channel.\n"
            "Please select an option below:"
        )
        markup = {
            "inline_keyboard": [
                [{"text": "🟢 Subscribe to VIP", "callback_data": "subscribe"}],
                [{"text": "🔄 Renew Subscription", "callback_data": "renew"}],
                [{"text": "📊 My Subscription", "callback_data": "my_subscription"}],
                [{"text": "💳 Payment Status", "callback_data": "payment_status"}],
                [{"text": "❓ Help / Support", "callback_data": "support"}]
            ]
        }
        TelegramService.send_message(customer.telegram_id, text, reply_markup=markup)

    @staticmethod
    def _handle_callback_query(cb: dict):
        telegram_id = str(cb.get("from", {}).get("id"))
        data = cb.get("callback_data")
        customer = db_session.query(Customer).filter_by(telegram_id=telegram_id).first()
        if not customer:
            return

        from services.payment_service import PaymentService

        if data in ["subscribe", "renew"]:
            # Fetch dynamic customer price
            amount = PaymentService.get_customer_price(customer)
            txn = PaymentService.create_pending_transaction(customer, amount=amount)

            # Generate dynamic QR base64
            qr_base64 = UPIService.generate_qr_base64(amount)

            caption = (
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⭐ <b>VIP ACCESS</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Duration: <b>30 Days</b>\n"
                f"Amount: <b>₹{amount:.2f}</b>\n"
                "Payment Method: <b>UPI</b>\n\n"
                f"UPI ID: <code>{Config.UPI_ID}</code>\n"
                f"Payee Name: <b>{Config.PAYEE_NAME}</b>\n\n"
                "👇 Scan the QR code above or pay to the UPI ID.\n"
                "After payment, click the button below and submit your UTR number."
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "✅ I HAVE PAID", "callback_data": f"paid_{txn.id}"}],
                    [{"text": "🔙 Back to Menu", "callback_data": "menu"}]
                ]
            }
            TelegramService.send_photo(telegram_id, qr_base64, caption, reply_markup=markup)

        elif data.startswith("paid_"):
            txn_id = data.replace("paid_", "")
            msg = (
                "Please enter your 12-digit <b>UTR / Transaction Reference Number</b> below:\n\n"
                "<i>(Example: 123456789012)</i>"
            )
            TelegramService.send_message(telegram_id, msg)

        elif data == "my_subscription":
            sub = db_session.query(Subscription).filter_by(customer_id=customer.id).order_by(Subscription.expiry_date.desc()).first()
            now = datetime.now(IST)
            if sub:
                days_left = (sub.expiry_date.replace(tzinfo=None) - now.replace(tzinfo=None)).days
                status_badge = "🟢 ACTIVE" if days_left > 0 else "🔴 EXPIRED"
                if 0 < days_left <= Config.EXPIRY_WARNING_DAYS:
                    status_badge = "🟡 EXPIRING SOON"

                text = (
                    "⭐ <b>MY VIP SUBSCRIPTION</b> ⭐\n\n"
                    f"Plan: <b>{sub.plan_name}</b>\n"
                    f"Amount Paid: <b>₹{sub.amount:.2f}</b>\n"
                    f"Start Date: <b>{sub.start_date.strftime('%d %b %Y')}</b>\n"
                    f"Expiry Date: <b>{sub.expiry_date.strftime('%d %b %Y')}</b>\n"
                    f"Days Remaining: <b>{max(0, days_left)} Days</b>\n"
                    f"Status: <b>{status_badge}</b>"
                )
                markup = {
                    "inline_keyboard": [
                        [{"text": "🔄 Renew Now", "callback_data": "renew"}],
                        [{"text": "🔙 Back to Menu", "callback_data": "menu"}]
                    ]
                }
            else:
                text = "You currently do not have an active VIP subscription."
                markup = {
                    "inline_keyboard": [
                        [{"text": "🟢 Subscribe Now", "callback_data": "subscribe"}],
                        [{"text": "🔙 Back to Menu", "callback_data": "menu"}]
                    ]
                }
            TelegramService.send_message(telegram_id, text, reply_markup=markup)

        elif data == "payment_status":
            txn = db_session.query(Transaction).filter_by(customer_id=customer.id).order_by(Transaction.created_at.desc()).first()
            if txn:
                if txn.payment_status == "APPROVED":
                    invite = db_session.query(InviteLink).filter_by(customer_id=customer.id, status="CREATED").first()
                    invite_url = invite.invite_url if invite else ""
                    text = (
                        "🟢 <b>Payment Approved!</b>\n\n"
                        f"Transaction: <b>{txn.id}</b>\n"
                        f"Amount: <b>₹{txn.amount:.2f}</b>\n"
                        f"UTR: <b>{txn.utr or 'N/A'}</b>\n\n"
                        "Your VIP Channel access is ready below:"
                    )
                    markup = {
                        "inline_keyboard": [
                            [{"text": "🔐 JOIN VIP CHANNEL", "url": invite_url}] if invite_url else [],
                            [{"text": "🔙 Back to Menu", "callback_data": "menu"}]
                        ]
                    }
                elif txn.payment_status == "REJECTED":
                    text = (
                        "🔴 <b>Payment Rejected</b>\n\n"
                        f"Transaction: <b>{txn.id}</b>\n"
                        f"Reason: <i>{txn.rejection_reason or 'UTR unverified'}</i>\n\n"
                        "Please contact support or re-submit."
                    )
                    markup = {
                        "inline_keyboard": [
                            [{"text": "🟢 Subscribe Again", "callback_data": "subscribe"}],
                            [{"text": "❓ Contact Support", "url": f"https://t.me/{Config.SUPPORT_USERNAME.lstrip('@')}"}]
                        ]
                    }
                else:
                    text = (
                        "🟡 <b>Under Verification</b>\n\n"
                        f"Transaction: <b>{txn.id}</b>\n"
                        f"Amount: <b>₹{txn.amount:.2f}</b>\n"
                        f"UTR: <b>{txn.utr or 'Pending Submission'}</b>\n\n"
                        "Our admin is verifying your payment. Once approved, your VIP link will appear here."
                    )
                    markup = {
                        "inline_keyboard": [
                            [{"text": "🔄 Refresh Status", "callback_data": "payment_status"}],
                            [{"text": "🔙 Back to Menu", "callback_data": "menu"}]
                        ]
                    }
            else:
                text = "No recent payment transactions found."
                markup = {"inline_keyboard": [[{"text": "🟢 Subscribe", "callback_data": "subscribe"}]]}

            TelegramService.send_message(telegram_id, text, reply_markup=markup)

        elif data == "support":
            text = (
                "❓ <b>VIP Support & Assistance</b>\n\n"
                f"For any queries regarding payments, access or renewal, please contact our official support team:\n\n"
                f"👤 Admin Support: <b>{Config.SUPPORT_USERNAME}</b>"
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "💬 Open Support Chat", "url": f"https://t.me/{Config.SUPPORT_USERNAME.lstrip('@')}"}],
                    [{"text": "🔙 Back to Menu", "callback_data": "menu"}]
                ]
            }
            TelegramService.send_message(telegram_id, text, reply_markup=markup)

        elif data == "menu":
            TelegramService._send_main_menu(customer)

    @staticmethod
    def _handle_chat_member_update(chat_member: dict):
        now = datetime.now(IST)
        new_state = chat_member.get("new_chat_member", {})
        status = new_state.get("status")
        user = new_state.get("user", {})
        joined_telegram_id = str(user.get("id"))
        invite_link_obj = chat_member.get("invite_link", {})
        invite_url = invite_link_obj.get("invite_link")

        if status == "member" and invite_url:
            # Check single-use invite in database
            invite = db_session.query(InviteLink).filter_by(invite_url=invite_url).first()
            if invite:
                if invite.telegram_id == joined_telegram_id:
                    # Match! Mark invite used
                    invite.status = "USED"
                    invite.used_at = now
                    invite.joined_telegram_id = joined_telegram_id

                    # Membership
                    cust = db_session.query(Customer).filter_by(id=invite.customer_id).first()
                    m = db_session.query(ChannelMembership).filter_by(customer_id=cust.id).first()
                    if not m:
                        m = ChannelMembership(
                            customer_id=cust.id,
                            telegram_id=cust.telegram_id,
                            channel_id=Config.TELEGRAM_CHANNEL_ID,
                            status="IN_CHANNEL",
                            joined_at=now
                        )
                        db_session.add(m)
                    else:
                        m.status = "IN_CHANNEL"
                        m.joined_at = now

                    mh = MembershipHistory(
                        customer_id=cust.id,
                        telegram_id=cust.telegram_id,
                        channel_id=Config.TELEGRAM_CHANNEL_ID,
                        event_type="JOINED",
                        invite_id=invite.id,
                        event_time=now,
                        details="Successfully joined VIP Channel"
                    )
                    db_session.add(mh)
                    db_session.commit()

                    GoogleSheetsService.queue_event("INVITE_USED", invite.to_dict())
                    GoogleSheetsService.queue_event("MEMBER_JOINED", mh.to_dict())
                else:
                    # Mismatch! Unauthorized invite usage
                    invite.status = "COMPROMISED"
                    db_session.commit()

                    # Kick unauthorized user
                    TelegramService.kick_member(joined_telegram_id)
                    audit = AuditLog(
                        actor="SYSTEM",
                        action="UNAUTHORIZED_INVITE_KICK",
                        details=f"Kicked unauthorized user {joined_telegram_id} who used invite assigned to {invite.telegram_id}"
                    )
                    db_session.add(audit)
                    db_session.commit()

        elif status in ["left", "kicked"]:
            cust = db_session.query(Customer).filter_by(telegram_id=joined_telegram_id).first()
            if cust:
                m = db_session.query(ChannelMembership).filter_by(customer_id=cust.id).first()
                if m:
                    m.status = "NOT_IN_CHANNEL"
                    m.left_at = now
                
                mh = MembershipHistory(
                    customer_id=cust.id,
                    telegram_id=cust.telegram_id,
                    channel_id=Config.TELEGRAM_CHANNEL_ID,
                    event_type="LEFT",
                    event_time=now,
                    details="Member left or was removed from channel"
                )
                db_session.add(mh)
                db_session.commit()

                GoogleSheetsService.queue_event("MEMBER_LEFT", mh.to_dict())
