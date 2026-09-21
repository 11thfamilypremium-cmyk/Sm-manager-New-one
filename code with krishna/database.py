import os
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base

Base = declarative_base()

def get_database_url():
    url = os.environ.get("DATABASE_URL", "sqlite:///data/sm_manager.db")
    # Fix Render PostgreSQL URL format if needed (postgres:// -> postgresql://)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url

db_url = get_database_url()

# Create directory for sqlite db if needed
if db_url.startswith("sqlite:///"):
    db_path = db_url.replace("sqlite:///", "")
    dir_name = os.path.dirname(db_path)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)

engine = create_engine(
    db_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {}
)

db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

def init_db():
    import models  # import models to register with Base
    Base.metadata.create_all(bind=engine)
