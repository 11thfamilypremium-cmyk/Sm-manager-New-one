import uuid
from datetime import datetime
import pytz
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from database import Base

IST = pytz.timezone('Asia/Kolkata')

def current_ist_time():
    return datetime.now(IST)

def generate_uuid():
    return str(uuid.uuid4())

class Customer(Base):
    __tablename__ = 'customers'

    id = Column(String(36), primary_key=True, default=generate_uuid)
    telegram_id = Column(String(64), unique=True, nullable=False, index=True)
    username = Column(String(128), index=True, nullable=True)
    first_name = Column(String(128), nullable=True)
    last_name = Column(String(128), nullable=True)
    custom_price = Column(Float, nullable=True)  # Overrides global default price if set
    status = Column(String(32), default='ACTIVE', index=True) # ACTIVE, SUSPENDED
    created_at = Column(DateTime(timezone=True), default=current_ist_time)
    last_activity = Column(DateTime(timezone=True), default=current_ist_time, onupdate=current_ist_time)

    transactions = relationship("Transaction", back_populates="customer", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="customer", cascade="all, delete-orphan")
    invite_links = relationship("InviteLink", back_populates="customer", cascade="all, delete-orphan")
    channel_memberships = relationship("ChannelMembership", back_populates="customer", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "telegram_id": self.telegram_id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "custom_price": self.custom_price,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None
        }

class Plan(Base):
    __tablename__ = 'plans'

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(128), nullable=False)
    duration_days = Column(Integer, default=30)
    default_price = Column(Float, nullable=False, default=299.0)
    is_active = Column(Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "duration_days": self.duration_days,
            "default_price": self.default_price,
            "is_active": self.is_active
        }

class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(String(64), primary_key=True)  # e.g., TXN-20260921-0001
    customer_id = Column(String(36), ForeignKey('customers.id'), nullable=False, index=True)
    telegram_id = Column(String(64), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), default='INR')
    utr = Column(String(64), nullable=True, index=True)
    payment_status = Column(String(32), default='PENDING_PAYMENT', index=True) 
    # Statuses: PENDING_PAYMENT, UTR_SUBMITTED, APPROVED, REJECTED, EXPIRED
    plan_name = Column(String(128), default='VIP — 30 Days')
    duration_days = Column(Integer, default=30)
    screenshot_url = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), default=current_ist_time)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(String(128), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    customer = relationship("Customer", back_populates="transactions")

    def to_dict(self):
        return {
            "transaction_id": self.id,
            "customer_id": self.customer_id,
            "telegram_id": self.telegram_id,
            "amount": self.amount,
            "currency": self.currency,
            "utr": self.utr,
            "payment_status": self.payment_status,
            "plan_name": self.plan_name,
            "duration_days": self.duration_days,
            "screenshot_url": self.screenshot_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "verified_by": self.verified_by,
            "rejection_reason": self.rejection_reason
        }

class Subscription(Base):
    __tablename__ = 'subscriptions'

    id = Column(String(36), primary_key=True, default=generate_uuid)
    customer_id = Column(String(36), ForeignKey('customers.id'), nullable=False, index=True)
    transaction_id = Column(String(64), ForeignKey('transactions.id'), nullable=True)
    plan_name = Column(String(128), default='VIP — 30 Days')
    amount = Column(Float, nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    expiry_date = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(32), default='ACTIVE', index=True)  # ACTIVE, EXPIRING_SOON, EXPIRED
    created_at = Column(DateTime(timezone=True), default=current_ist_time)

    customer = relationship("Customer", back_populates="subscriptions")

    def to_dict(self):
        return {
            "subscription_id": self.id,
            "customer_id": self.customer_id,
            "transaction_id": self.transaction_id,
            "plan_name": self.plan_name,
            "amount": self.amount,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class SubscriptionHistory(Base):
    __tablename__ = 'subscription_history'

    id = Column(String(36), primary_key=True, default=generate_uuid)
    customer_id = Column(String(36), nullable=False, index=True)
    transaction_id = Column(String(64), nullable=True)
    plan_name = Column(String(128), nullable=False)
    amount = Column(Float, nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    expiry_date = Column(DateTime(timezone=True), nullable=False)
    event_type = Column(String(64), nullable=False)  # NEW_SUBSCRIPTION, RENEWAL, MANUAL_EXTENSION, MANUAL_ADJUSTMENT, EXPIRY
    created_at = Column(DateTime(timezone=True), default=current_ist_time)

    def to_dict(self):
        return {
            "history_id": self.id,
            "customer_id": self.customer_id,
            "transaction_id": self.transaction_id,
            "plan_name": self.plan_name,
            "amount": self.amount,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "event_type": self.event_type,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class InviteLink(Base):
    __tablename__ = 'invite_links'

    id = Column(String(36), primary_key=True, default=generate_uuid)
    customer_id = Column(String(36), ForeignKey('customers.id'), nullable=False, index=True)
    telegram_id = Column(String(64), nullable=False)
    invite_url = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=current_ist_time)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    joined_telegram_id = Column(String(64), nullable=True)
    status = Column(String(32), default='CREATED', index=True)  # CREATED, USED, EXPIRED, REVOKED, COMPROMISED

    customer = relationship("Customer", back_populates="invite_links")

    def to_dict(self):
        return {
            "invite_id": self.id,
            "customer_id": self.customer_id,
            "telegram_id": self.telegram_id,
            "invite_url": self.invite_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "used_at": self.used_at.isoformat() if self.used_at else None,
            "joined_telegram_id": self.joined_telegram_id,
            "status": self.status
        }

class ChannelMembership(Base):
    __tablename__ = 'channel_memberships'

    id = Column(String(36), primary_key=True, default=generate_uuid)
    customer_id = Column(String(36), ForeignKey('customers.id'), nullable=False, index=True)
    telegram_id = Column(String(64), nullable=False, index=True)
    channel_id = Column(String(64), nullable=False)
    status = Column(String(32), default='IN_CHANNEL', index=True) # IN_CHANNEL, NOT_IN_CHANNEL, REMOVED
    joined_at = Column(DateTime(timezone=True), default=current_ist_time)
    left_at = Column(DateTime(timezone=True), nullable=True)
    removed_at = Column(DateTime(timezone=True), nullable=True)

    customer = relationship("Customer", back_populates="channel_memberships")

    def to_dict(self):
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "telegram_id": self.telegram_id,
            "channel_id": self.channel_id,
            "status": self.status,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "left_at": self.left_at.isoformat() if self.left_at else None,
            "removed_at": self.removed_at.isoformat() if self.removed_at else None
        }

class MembershipHistory(Base):
    __tablename__ = 'membership_history'

    id = Column(String(36), primary_key=True, default=generate_uuid)
    customer_id = Column(String(36), nullable=False, index=True)
    telegram_id = Column(String(64), nullable=False)
    channel_id = Column(String(64), nullable=False)
    event_type = Column(String(64), nullable=False) # JOINED, LEFT, REMOVED, EXPIRED_REMOVAL
    invite_id = Column(String(36), nullable=True)
    event_time = Column(DateTime(timezone=True), default=current_ist_time)
    details = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "event_id": self.id,
            "customer_id": self.customer_id,
            "telegram_id": self.telegram_id,
            "channel_id": self.channel_id,
            "event_type": self.event_type,
            "invite_id": self.invite_id,
            "event_time": self.event_time.isoformat() if self.event_time else None,
            "details": self.details
        }

class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id = Column(String(36), primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime(timezone=True), default=current_ist_time, index=True)
    actor = Column(String(128), default='SYSTEM') # ADMIN, SYSTEM, CUSTOMER
    action = Column(String(128), nullable=False, index=True)
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(String(64), nullable=True)
    details = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "actor": self.actor,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "details": self.details
        }

class SyncEvent(Base):
    __tablename__ = 'sync_events'

    id = Column(String(64), primary_key=True, default=generate_uuid) # Unique event_id
    event_type = Column(String(64), nullable=False, index=True)
    payload = Column(Text, nullable=False) # JSON payload string
    status = Column(String(32), default='PENDING', index=True) # PENDING, SYNCED, FAILED
    attempt_count = Column(Integer, default=0)
    last_attempt = Column(DateTime(timezone=True), nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "sync_event_id": self.id,
            "event_type": self.event_type,
            "status": self.status,
            "attempt_count": self.attempt_count,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
            "error_message": self.error_message
        }

class SystemSetting(Base):
    __tablename__ = 'system_settings'

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)

class ManualAdjustment(Base):
    __tablename__ = 'manual_adjustments'

    id = Column(String(36), primary_key=True, default=generate_uuid)
    customer_id = Column(String(36), nullable=False, index=True)
    subscription_id = Column(String(36), nullable=True)
    adjustment_type = Column(String(64), nullable=False) # ADD_DAYS, SUBTRACT_DAYS, SET_EXPIRY
    days_adjusted = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    adjusted_by = Column(String(128), default='ADMIN')
    created_at = Column(DateTime(timezone=True), default=current_ist_time)

    def to_dict(self):
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "subscription_id": self.subscription_id,
            "adjustment_type": self.adjustment_type,
            "days_adjusted": self.days_adjusted,
            "reason": self.reason,
            "adjusted_by": self.adjusted_by,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
