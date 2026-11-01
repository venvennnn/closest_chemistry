import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AUTH_MODE", "single")
os.environ.setdefault("DATABASE_SSL_REQUIRE", "false")
os.environ.setdefault("LOCAL_STORAGE_DIR", str(ROOT / ".local_storage_test"))

from app.config import get_settings
from app.database import Base, reset_engine, get_engine


@pytest.fixture()
def session():
    get_settings.cache_clear()
    reset_engine()
    engine = get_engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        reset_engine()
        get_settings.cache_clear()
