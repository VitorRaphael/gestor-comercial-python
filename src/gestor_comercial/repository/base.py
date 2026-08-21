import os
from pathlib import Path
from typing import Generic, TypeVar

from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# GESTOR_COMERCIAL_DB permite apontar pra outro arquivo sem tocar no código —
# usado pra testar migration em banco descartável e pra apontar o .exe pra um
# caminho fixo na máquina do food truck.
DB_PATH = Path(os.environ.get("GESTOR_COMERCIAL_DB", Path.home() / ".gestor_comercial" / "gestor_comercial.db"))


class Base(DeclarativeBase):
    pass


def get_engine(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}")


engine = get_engine()
SessionLocal = sessionmaker(bind=engine)


T = TypeVar("T", bound=Base)


class Repository(Generic[T]):
    """CRUD comum a todas as entidades.

    Esta é a única camada que fala SQLAlchemy: os services recebem um
    UnitOfWork e chamam métodos daqui, nunca `session.query()` direto.

    `salvar` faz `flush` e não `commit` de propósito — quem decide o
    momento do commit é o service, para que uma operação que mexe em
    várias entidades (registrar pagamento + fechar comanda + liberar mesa)
    seja tudo-ou-nada.
    """

    modelo: type[T]

    def __init__(self, session: Session) -> None:
        self.session = session

    def salvar(self, entidade: T) -> T:
        self.session.add(entidade)
        self.session.flush()
        return entidade

    def salvar_todos(self, entidades: list[T]) -> list[T]:
        self.session.add_all(entidades)
        self.session.flush()
        return entidades

    def buscar_por_id(self, entidade_id: int) -> T | None:
        return self.session.get(self.modelo, entidade_id)

    def listar_todos(self) -> list[T]:
        return list(self.session.scalars(select(self.modelo).order_by(self.modelo.id)))

    def remover(self, entidade: T) -> None:
        self.session.delete(entidade)
        self.session.flush()
