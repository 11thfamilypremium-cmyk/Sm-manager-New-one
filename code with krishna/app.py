import os
import functools
from datetime import datetime, timedelta
import pytz
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config
from database import init_db, db_session
from models import (
    Customer, Transaction, Subscription, SubscriptionHistory,
    InviteLink, ChannelMembership, AuditLog, SyncEvent, SystemSetting, ManualAdjustment
)
from services.telegram_service import TelegramService
from services.payment_service import PaymentService
from services.scheduler_service import SchedulerService
from services.google_sheets_service import GoogleSheetsService

IST = pytz.timezone('Asia/Kolkata')

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY

# Initialize database
init_db()

# Initialize APScheduler for background jobs
scheduler = BackgroundScheduler(daemon=True)

def scheduled_job():
    with app.app_context():
        try:
            SchedulerService.process_expiries()
            SchedulerService.send_expiry_reminders()
            GoogleSheetsService.process_pending_events()
        except Exception as e:
            app.logger.error(f"[Scheduler Error] {e}")

if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    try:
        scheduler.add_job(scheduled_job, 'interval', minutes=60)
        scheduler.start()
    except Exception as e:
        print(f">>> [Scheduler Start Warning] {e}")

# Admin Auth Decorator
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ----------------- PUBLIC & SYSTEM ENDPOINTS -----------------

@app.route('/health', methods=['GET'])
def health_check():
    """Render health check endpoint"""
    try:
        db_session.execute("SELECT 1")
        bot_status = TelegramService.test_connection()
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "telegram_bot": bot_status.get("status"),
            "timestamp": datetime.now(IST).isoformat()
        }), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """Telegram Webhook Endpoint"""
    secret_token = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    # Can validate secret token if configured
    try:
        data = request.get_json(force=True)
        if data:
            TelegramService.process_webhook_update(data)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        app.logger.error(f"Webhook processing error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 200

@app.route('/jobs/process-expiries', methods=['POST'])
def cron_process_expiries():
    """Protected Scheduled Job Endpoint for Expiry Processing"""
    auth_secret = request.headers.get('X-Cron-Secret') or request.args.get('secret')
    if auth_secret != Config.CRON_SECRET:
        return jsonify({"error": "Unauthorized cron trigger"}), 401

    try:
        expiry_result = SchedulerService.process_expiries()
        reminder_result = SchedulerService.send_expiry_reminders()
        GoogleSheetsService.process_pending_events()
        return jsonify({
            "status": "success",
            "expiry_results": expiry_result,
            "reminder_results": reminder_result,
            "timestamp": datetime.now(IST).isoformat()
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ----------------- ADMIN DASHBOARD ROUTES -----------------

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            session['admin_user'] = username
            audit = AuditLog(actor="ADMIN", action="ADMIN_LOGIN", details="Admin logged in successfully")
            db_session.add(audit)
            db_session.commit()
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('login.html', error="Invalid username or password")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/')
@app.route('/admin')
@login_required
def admin_dashboard():
    return render_template('admin.html', bot_token_set=bool(Config.TELEGRAM_BOT_TOKEN))

# ----------------- ADMIN REST APIs -----------------

@app.route('/api/admin/metrics', methods=['GET'])
@login_required
def api_metrics():
    now = datetime.now(IST)
    total_customers = db_session.query(Customer).count()
    active_members = db_session.query(Subscription).filter(Subscription.status == 'ACTIVE', Subscription.expiry_date > now).count()
    
    expiring_soon = db_session.query(Subscription).filter(
        Subscription.status.in_(['ACTIVE', 'EXPIRING_SOON']),
        Subscription.expiry_date > now,
        Subscription.expiry_date <= now + timedelta(days=Config.EXPIRY_WARNING_DAYS)
    ).count()

    expired_members = db_session.query(Subscription).filter(
        (Subscription.status == 'EXPIRED') | (Subscription.expiry_date <= now)
    ).count()

    pending_payments = db_session.query(Transaction).filter(Transaction.payment_status.in_(['UTR_SUBMITTED', 'PENDING_PAYMENT'])).count()
    approved_payments = db_session.query(Transaction).filter_by(payment_status='APPROVED').count()
    rejected_payments = db_session.query(Transaction).filter_by(payment_status='REJECTED').count()

    # Revenue
    approved_txns = db_session.query(Transaction).filter_by(payment_status='APPROVED').all()
    total_revenue = sum(t.amount for t in approved_txns)

    # Sync Status
    pending_syncs = db_session.query(SyncEvent).filter_by(status='PENDING').count()
    failed_syncs = db_session.query(SyncEvent).filter_by(status='FAILED').count()
    last_sync = db_session.query(SyncEvent).filter_by(status='SYNCED').order_by(SyncEvent.synced_at.desc()).first()

    return jsonify({
        "total_customers": total_customers,
        "active_members": active_members,
        "expiring_soon": expiring_soon,
        "expired_members": expired_members,
        "pending_payments": pending_payments,
        "approved_payments": approved_payments,
        "rejected_payments": rejected_payments,
        "total_revenue": total_revenue,
        "sync_status": {
            "pending": pending_syncs,
            "failed": failed_syncs,
            "last_synced": last_sync.synced_at.isoformat() if last_sync and last_sync.synced_at else None
        }
    })

@app.route('/api/admin/pending-payments', methods=['GET'])
@login_required
def api_pending_payments():
    pending = db_session.query(Transaction).filter(
        Transaction.payment_status.in_(['UTR_SUBMITTED', 'PENDING_PAYMENT'])
    ).order_by(Transaction.created_at.desc()).all()

    results = []
    for t in pending:
        c = db_session.query(Customer).filter_by(id=t.customer_id).first()
        item = t.to_dict()
        item['customer_name'] = f"{c.first_name or ''} {c.last_name or ''}".strip() if c else "Unknown"
        item['telegram_username'] = c.username if c else ""
        results.append(item)

    return jsonify({"pending_payments": results})

@app.route('/api/admin/approve-payment', methods=['POST'])
@login_required
def api_approve_payment():
    data = request.get_json() or {}
    transaction_id = data.get('transaction_id')
    if not transaction_id:
        return jsonify({"error": "transaction_id required"}), 400

    try:
        admin_user = session.get('admin_user', 'ADMIN')
        txn, sub, invite = PaymentService.approve_payment(transaction_id, admin_user=admin_user)
        return jsonify({
            "message": "Payment approved successfully",
            "transaction": txn.to_dict(),
            "subscription": sub.to_dict(),
            "invite": invite.to_dict() if invite else None
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/reject-payment', methods=['POST'])
@login_required
def api_reject_payment():
    data = request.get_json() or {}
    transaction_id = data.get('transaction_id')
    reason = data.get('reason', 'UTR could not be verified.')

    if not transaction_id:
        return jsonify({"error": "transaction_id required"}), 400

    try:
        admin_user = session.get('admin_user', 'ADMIN')
        txn = PaymentService.reject_payment(transaction_id, admin_user=admin_user, reason=reason)
        return jsonify({"message": "Payment rejected", "transaction": txn.to_dict()}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/customers', methods=['GET'])
@login_required
def api_customers():
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('filter', '').strip()

    query = db_session.query(Customer)

    if search:
        query = query.filter(
            (Customer.first_name.ilike(f"%{search}%")) |
            (Customer.username.ilike(f"%{search}%")) |
            (Customer.telegram_id.ilike(f"%{search}%"))
        )

    customers = query.all()
    now = datetime.now(IST)
    results = []

    for c in customers:
        sub = db_session.query(Subscription).filter_by(customer_id=c.id).order_by(Subscription.expiry_date.desc()).first()
        mem = db_session.query(ChannelMembership).filter_by(customer_id=c.id).first()
        txns = db_session.query(Transaction).filter_by(customer_id=c.id, payment_status='APPROVED').all()

        days_left = 0
        sub_status = "NO_SUBSCRIPTION"
        if sub:
            days_left = (sub.expiry_date.replace(tzinfo=None) - now.replace(tzinfo=None)).days
            if days_left > Config.EXPIRY_WARNING_DAYS:
                sub_status = "ACTIVE"
            elif 0 < days_left <= Config.EXPIRY_WARNING_DAYS:
                sub_status = "EXPIRING_SOON"
            else:
                sub_status = "EXPIRED"

        if status_filter and status_filter != 'ALL':
            if status_filter == 'ACTIVE' and sub_status not in ['ACTIVE', 'EXPIRING_SOON']:
                continue
            elif status_filter == 'EXPIRING' and sub_status != 'EXPIRING_SOON':
                continue
            elif status_filter == 'EXPIRED' and sub_status != 'EXPIRED':
                continue

        item = c.to_dict()
        item['custom_price'] = c.custom_price
        item['effective_price'] = PaymentService.get_customer_price(c)
        item['subscription'] = sub.to_dict() if sub else None
        item['days_remaining'] = max(0, days_left) if sub else 0
        item['subscription_status'] = sub_status
        item['membership_status'] = mem.status if mem else "NOT_IN_CHANNEL"
        item['total_paid'] = sum(t.amount for t in txns)
        results.append(item)

    return jsonify({"customers": results})

@app.route('/api/admin/customer/<customer_id>', methods=['GET'])
@login_required
def api_customer_detail(customer_id):
    c = db_session.query(Customer).filter_by(id=customer_id).first()
    if not c:
        return jsonify({"error": "Customer not found"}), 404

    txns = [t.to_dict() for t in db_session.query(Transaction).filter_by(customer_id=c.id).order_by(Transaction.created_at.desc()).all()]
    subs = [s.to_dict() for s in db_session.query(Subscription).filter_by(customer_id=c.id).order_by(Subscription.expiry_date.desc()).all()]
    sub_hist = [sh.to_dict() for sh in db_session.query(SubscriptionHistory).filter_by(customer_id=c.id).order_by(SubscriptionHistory.created_at.desc()).all()]
    invites = [i.to_dict() for i in db_session.query(InviteLink).filter_by(customer_id=c.id).order_by(InviteLink.created_at.desc()).all()]
    adjustments = [a.to_dict() for a in db_session.query(ManualAdjustment).filter_by(customer_id=c.id).order_by(ManualAdjustment.created_at.desc()).all()]

    data = c.to_dict()
    data['effective_price'] = PaymentService.get_customer_price(c)
    data['transactions'] = txns
    data['subscriptions'] = subs
    data['subscription_history'] = sub_hist
    data['invites'] = invites
    data['manual_adjustments'] = adjustments
    return jsonify(data)

@app.route('/api/admin/customer/<customer_id>/custom-price', methods=['POST'])
@login_required
def api_set_custom_price(customer_id):
    c = db_session.query(Customer).filter_by(id=customer_id).first()
    if not c:
        return jsonify({"error": "Customer not found"}), 404

    data = request.get_json() or {}
    price = data.get('price')
    if price is not None:
        c.custom_price = float(price) if float(price) > 0 else None
        db_session.commit()
        audit = AuditLog(actor="ADMIN", action="CUSTOM_PRICE_SET", entity_type="Customer", entity_id=c.id, details=f"Custom price set to ₹{c.custom_price}")
        db_session.add(audit)
        db_session.commit()
        GoogleSheetsService.queue_event("CUSTOMER_UPDATED", c.to_dict())

    return jsonify({"message": "Custom price updated", "customer": c.to_dict()})

@app.route('/api/admin/customer/<customer_id>/adjust-expiry', methods=['POST'])
@login_required
def api_adjust_expiry(customer_id):
    c = db_session.query(Customer).filter_by(id=customer_id).first()
    if not c:
        return jsonify({"error": "Customer not found"}), 404

    data = request.get_json() or {}
    days = int(data.get('days', 0))
    reason = data.get('reason', 'Manual admin extension')

    sub = db_session.query(Subscription).filter_by(customer_id=c.id).order_by(Subscription.expiry_date.desc()).first()
    now = datetime.now(IST)

    if sub:
        base_date = sub.expiry_date if sub.expiry_date > now else now
        sub.expiry_date = base_date + timedelta(days=days)
        sub.status = "ACTIVE"
    else:
        sub = Subscription(
            customer_id=c.id,
            plan_name="VIP — 30 Days (Manual)",
            amount=0.0,
            start_date=now,
            expiry_date=now + timedelta(days=days),
            status="ACTIVE",
            created_at=now
        )
        db_session.add(sub)

    adj = ManualAdjustment(
        customer_id=c.id,
        subscription_id=sub.id,
        adjustment_type="ADD_DAYS" if days >= 0 else "SUBTRACT_DAYS",
        days_adjusted=days,
        reason=reason,
        adjusted_by=session.get('admin_user', 'ADMIN')
    )
    db_session.add(adj)

    sh = SubscriptionHistory(
        customer_id=c.id,
        plan_name=sub.plan_name,
        amount=0.0,
        start_date=sub.start_date,
        expiry_date=sub.expiry_date,
        event_type="MANUAL_EXTENSION",
        created_at=now
    )
    db_session.add(sh)
    db_session.commit()

    GoogleSheetsService.queue_event("SUBSCRIPTION_EXTENDED", sh.to_dict())
    return jsonify({"message": f"Expiry adjusted by {days} days", "subscription": sub.to_dict()})

@app.route('/api/admin/customer/<customer_id>/generate-invite', methods=['POST'])
@login_required
def api_generate_invite(customer_id):
    c = db_session.query(Customer).filter_by(id=customer_id).first()
    if not c:
        return jsonify({"error": "Customer not found"}), 404

    now = datetime.now(IST)
    invite_data = TelegramService.create_single_use_invite(c.telegram_id)
    invite_url = invite_data.get("invite_link", "")

    invite = InviteLink(
        customer_id=c.id,
        telegram_id=c.telegram_id,
        invite_url=invite_url,
        created_at=now,
        expires_at=now + timedelta(days=2),
        status="CREATED"
    )
    db_session.add(invite)
    db_session.commit()

    # Send invite link to customer via bot
    TelegramService.send_message(c.telegram_id, f"🔐 Here is your replacement VIP Channel access link:\n\n{invite_url}")

    return jsonify({"message": "New invite link generated and sent", "invite": invite.to_dict()})

@app.route('/api/admin/customer/<customer_id>/remove-member', methods=['POST'])
@login_required
def api_remove_member(customer_id):
    c = db_session.query(Customer).filter_by(id=customer_id).first()
    if not c:
        return jsonify({"error": "Customer not found"}), 404

    kicked = TelegramService.kick_member(c.telegram_id)
    now = datetime.now(IST)
    
    mem = db_session.query(ChannelMembership).filter_by(customer_id=c.id).first()
    if mem:
        mem.status = "REMOVED"
        mem.removed_at = now

    audit = AuditLog(actor=session.get('admin_user', 'ADMIN'), action="MANUAL_MEMBER_REMOVE", entity_type="Customer", entity_id=c.id, details="Manually kicked from VIP channel")
    db_session.add(audit)
    db_session.commit()

    return jsonify({"message": "Member removed from Telegram channel", "kicked": kicked})

@app.route('/api/admin/rebuild-sheets', methods=['POST'])
@login_required
def api_rebuild_sheets():
    try:
        GoogleSheetsService.rebuild_all_sheets()
        return jsonify({"message": "Google Sheets rebuild triggered successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/audit-logs', methods=['GET'])
@login_required
def api_audit_logs():
    logs = db_session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100).all()
    return jsonify({"audit_logs": [l.to_dict() for l in logs]})

# Teardown database session
@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
