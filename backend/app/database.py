from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.require_database()
        connect_args = {}
        engine_kwargs: dict = {"pool_pre_ping": True, "connect_args": connect_args}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            engine_kwargs["poolclass"] = StaticPool
        elif settings.database_ssl_require and "sslmode=" not in url and "sqlite" not in url:
            if "ssl" not in url:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}sslmode=require" if "localhost" not in url and "127.0.0.1" not in url else url
        _engine = create_engine(url, **engine_kwargs)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
