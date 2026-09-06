import os
import sqlite3
from pathlib import Path
from typing import Generic, TypeVar

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# GESTOR_COMERCIAL_DB permite apontar pra outro arquivo sem tocar no código —
# usado pra testar migration em banco descartável e pra apontar o .exe pra um
# caminho fixo na máquina do food truck.
DB_PATH = Path(os.environ.get("GESTOR_COMERCIAL_DB", Path.home() / ".gestor_comercial" / "gestor_comercial.db"))


@event.listens_for(Engine, "connect")
def _configurar_conexao_sqlite(conexao_dbapi, _registro) -> None:
    """Aplica os PRAGMAs do projeto em toda conexão SQLite.

    **`foreign_keys=ON`** — o SQLite nasce com a checagem **desligada** e a
    configuração vale por conexão, não fica gravada no arquivo, então não
    adianta ligar uma vez. Sem isto, as 20 `ForeignKey` declaradas no `domain/`
    são decorativas: o banco aceita item apontando para produto inexistente,
    pagamento de comanda apagada, e o problema só aparece semanas depois como
    relatório que não fecha. Ver `REMASTERIZACAO-V1.md` §3.5.

    **`journal_mode=WAL`** — leitura e escrita deixam de se bloquear (§8,
    decisão do Vitor de 2026-09-06). Hoje isso já paga 3x em cada lançamento de
    item no balcão; o motivo principal, porém, é o App Mobile do Atendente do
    backlog: com o journal `delete`, um segundo cliente lendo o banco trava a
    gravação da venda. Diferente do `foreign_keys`, este PRAGMA fica **gravado
    no arquivo** e valeria mesmo se fosse ligado uma vez só — está aqui para o
    banco recém-criado (primeiro boot, e cada banco novo da suíte) já nascer em
    WAL.

    **O que NÃO é configurado aqui, de propósito: `synchronous`.** Todo guia de
    WAL sugere baixar para `NORMAL`, e é uma armadilha para este projeto:
    `NORMAL` protege contra o app morrer, mas **não** contra a energia cair no
    meio do commit — exatamente o cenário do food truck, e exatamente o que
    `tests/integration/test_resiliencia_queda_energia.py` prova hoje. Fica no
    `FULL` padrão do SQLite: a venda commitada está no disco antes de a tela
    dizer que está.

    O listener é registrado na classe `Engine` (e não numa instância) de
    propósito: assim vale também para os engines que a suíte de testes cria por
    conta própria, e o teste passa a rodar sob as mesmas regras da produção.
    """
    if not isinstance(conexao_dbapi, sqlite3.Connection):
        return
    cursor = conexao_dbapi.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        # Banco em memória (a suíte usa `sqlite:///:memory:`) não tem arquivo
        # onde manter um WAL; o SQLite recusa a troca e devolve "memory". Pedir
        # assim mesmo é inofensivo, mas o `if` deixa a intenção explícita.
        if conexao_dbapi.execute("PRAGMA database_list").fetchone()[2]:
            cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


class Base(DeclarativeBase):
    pass


def get_engine(db_path: Path = DB_PATH) -> Engine:
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

    def buscar_por_id(self, entidade_id: int) -> T | None:
        return self.session.get(self.modelo, entidade_id)

    def listar_todos(self) -> list[T]:
        return list(self.session.scalars(select(self.modelo).order_by(self.modelo.id)))

    def remover(self, entidade: T) -> None:
        self.session.delete(entidade)
        self.session.flush()
