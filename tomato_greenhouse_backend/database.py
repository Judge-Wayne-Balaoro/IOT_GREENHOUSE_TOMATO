import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()


def normalize_database_url(url: str) -> str:
    """Use psycopg 3 for common managed-Postgres connection-string formats."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


_raw_database_url = os.getenv("DATABASE_URL", "")
if not _raw_database_url:
    raise RuntimeError("DATABASE_URL is not set. Configure it in the environment or .env file.")
DATABASE_URL = normalize_database_url(_raw_database_url)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
