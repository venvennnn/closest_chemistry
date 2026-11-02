import os
import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["ENVIRONMENT"] = "test"
os.environ["AUTH_MODE"] = "single"
os.environ["DATABASE_SSL_REQUIRE"] = "false"
os.environ["LOCAL_STORAGE_DIR"] = str(ROOT / ".local_storage_test")
os.environ["RUN_WORKER"] = "0"
for _youcam_key in (
    "YOU_CAM_API_KEY",
    "YOUCAM_API_KEY",
    "YOU_CAM_ENABLED_CATEGORIES",
    "YOUCAM_ENABLED_CATEGORIES",
    "YOU_CAM_UNIT_COST",
    "YOUCAM_UNIT_COST",
    "YOU_CAM_BASE_URL",
    "YOUCAM_BASE_URL",
):
    os.environ.pop(_youcam_key, None)

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
