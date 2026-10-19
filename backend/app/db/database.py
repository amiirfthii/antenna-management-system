#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

database_url = settings.get_database_url()
print(f"Using database: {database_url}")

engine_kwargs = {
    "pool_pre_ping": True,
    "echo": settings.DEBUG,
}

if database_url.startswith("sqlite"):
    engine_kwargs.update({
        "connect_args": {"check_same_thread": False},
        "pool_pre_ping": False,
    })
elif database_url.startswith("mysql"):
    engine_kwargs.update({
        "pool_recycle": 3600,
        "pool_size": 20,
        "max_overflow": 40,
        "connect_args": {
            "charset": "utf8mb4",
            "connect_timeout": 10,
        },
    })

engine = create_engine(database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency برای گرفتن سشن دیتابیس در FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
