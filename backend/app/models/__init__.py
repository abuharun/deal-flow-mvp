"""Declarative base for all models.

Every model module must be imported here so Base.metadata is complete for
Alembic autogenerate (alembic/env.py targets Base.metadata).
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.models.analysis_job import AnalysisJob  # noqa: E402
from app.models.audit import AuditActorType, AuditLog  # noqa: E402
from app.models.auth_session import AuthSession  # noqa: E402
from app.models.consent import Consent  # noqa: E402
from app.models.email_token import EmailToken, EmailTokenPurpose  # noqa: E402
from app.models.invite import Invite  # noqa: E402
from app.models.payment import Payment  # noqa: E402
from app.models.pitch_deck import PitchDeck  # noqa: E402
from app.models.startup import Startup, StartupStatus, Submission  # noqa: E402
from app.models.user import UiLocale, User, UserRole  # noqa: E402

__all__ = [
    "AnalysisJob",
    "AuditActorType",
    "AuditLog",
    "AuthSession",
    "Base",
    "Consent",
    "EmailToken",
    "EmailTokenPurpose",
    "Invite",
    "Payment",
    "PitchDeck",
    "Startup",
    "StartupStatus",
    "Submission",
    "UiLocale",
    "User",
    "UserRole",
]
