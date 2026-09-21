import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "sm-manager-super-secret-key-2026")
    
    # Telegram Configuration
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
    
    # UPI Payment Configuration
    UPI_ID = os.environ.get("UPI_ID", "myupi@upi")
    PAYEE_NAME = os.environ.get("PAYEE_NAME", "VIP Membership")
    
    # Defaults
    DEFAULT_PRICE = float(os.environ.get("DEFAULT_PRICE", 299.0))
    DEFAULT_DURATION_DAYS = int(os.environ.get("DEFAULT_DURATION_DAYS", 30))
    EXPIRY_WARNING_DAYS = int(os.environ.get("EXPIRY_WARNING_DAYS", 7))
    
    # Google Apps Script Integration
    GOOGLE_APPS_SCRIPT_URL = os.environ.get("GOOGLE_APPS_SCRIPT_URL", "")
    GOOGLE_APPS_SCRIPT_SECRET = os.environ.get("GOOGLE_APPS_SCRIPT_SECRET", "gas-sync-secret")
    
    # Protected Job Endpoint Secret
    CRON_SECRET = os.environ.get("CRON_SECRET", "cron-execution-secret-2026")
    
    # App URLs & Timezone
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000").rstrip("/")
    TIMEZONE = os.environ.get("TIMEZONE", "Asia/Kolkata")
    SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "@VIPSupport")
    
    # Admin Credentials
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    # Default password is "admin123"
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
