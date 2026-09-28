# backend/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

if not settings.DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to backend/.env (see backend/.env.example)."
    )

_connect_args = {}
if "supabase" in settings.DATABASE_URL:
    _connect_args["sslmode"] = "require"

# A small pre-pinged pool: opening a new SSL connection to Supabase costs
# 2-4 s, so connections are reused. psycopg2 does not use server-side prepared
# statements, which keeps this compatible with the transaction pooler (6543).
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
