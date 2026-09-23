# backend/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://postgres.exzfeyytdtijtsjvfixl:%40Gikundiro5@aws-0-eu-west-2.pooler.supabase.com:6543/postgres"

# Added poolclass=NullPool to prevent transaction pooler errors on port 6543
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    poolclass=NullPool,
    connect_args={"sslmode": "require"}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()