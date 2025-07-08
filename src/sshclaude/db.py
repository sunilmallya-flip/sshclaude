from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from sqlalchemy import (Boolean, Column, DateTime, Integer, String,
                        create_engine)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sshclaude.db")
engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
    ),
)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


class Provision(Base):
    __tablename__ = "provisions"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False)
    subdomain = Column(String, unique=True, nullable=False)
    tunnel_id = Column(String, nullable=False)
    dns_record_id = Column(String, nullable=False)
    access_app_id = Column(String, nullable=False)


class LoginEvent(Base):
    __tablename__ = "login_events"

    id = Column(Integer, primary_key=True, index=True)
    subdomain = Column(String, index=True, nullable=False)
    user = Column(String, nullable=False)
    ip = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id = Column(String, primary_key=True, index=True)
    token = Column(String, nullable=False)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Generator:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
