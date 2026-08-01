"""User accounts (founders + the CLI-created VC owner).

Mirrors Alembic revision 0002_users; keep the two in sync.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, Text, func, text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class UserRole(enum.Enum):
    FOUNDER = "founder"
    VC = "vc"


class UiLocale(enum.Enum):
    UZ = "uz"
    RU = "ru"


def pg_enum(py_enum: type[enum.Enum], name: str) -> Enum:
    # Store the lowercase values (not member NAMES); types are created by the
    # migration, never implicitly by metadata.create_all.
    return Enum(
        py_enum,
        name=name,
        values_callable=lambda e: [member.value for member in e],
        create_type=False,
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Retention sweeps only ever scan rows queued for purge.
        Index("ix_users_purge", "purge_after", postgresql_where=text("purge_after IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text(), nullable=False)
    full_name: Mapped[str] = mapped_column(Text(), nullable=False)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False)
    locale: Mapped[UiLocale] = mapped_column(
        pg_enum(UiLocale, "ui_locale"), nullable=False, server_default=text("'uz'")
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
