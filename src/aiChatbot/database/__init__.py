"""
Database package — PostgreSQL async integration (Milestone 6).
Provides SQLAlchemy engine, session factory, ORM models, and repository layer.
"""

from .connection import (
    DatabaseManager,
    get_db_session,
    init_database,
)
from .models import Base, UserModel, SessionModel, MessageModel
from .repository import ChatRepository

__all__ = [
    "DatabaseManager",
    "get_db_session",
    "init_database",
    "Base",
    "UserModel",
    "SessionModel",
    "MessageModel",
    "ChatRepository",
]
