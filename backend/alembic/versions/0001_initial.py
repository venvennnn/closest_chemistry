"""initial closest chemistry schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.database import Base
    from app import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.database import Base
    from app import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
