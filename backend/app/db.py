from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(db_path: Path):
    # check_same_thread=False is required because FastAPI may service a request
    # on a different thread than the one that opened the connection; SQLAlchemy's
    # pooling still serializes access per session.
    return create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
