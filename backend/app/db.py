from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(
    f"sqlite:///{DATA_DIR / 'vnflow.db'}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
