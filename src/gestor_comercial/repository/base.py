from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = Path.home() / ".gestor_comercial" / "gestor_comercial.db"


class Base(DeclarativeBase):
    pass


def get_engine(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}")


engine = get_engine()
SessionLocal = sessionmaker(bind=engine)
