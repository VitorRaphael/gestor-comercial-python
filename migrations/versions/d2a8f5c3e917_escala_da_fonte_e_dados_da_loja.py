"""escala da fonte da impressora e dados da loja no recibo (§9.30)

Revision ID: d2a8f5c3e917
Revises: c5d9e17a24b8
Create Date: 2026-09-22

## O que muda

**`impressoras.escala_fonte`** (`NOT NULL DEFAULT 2`) entra no lugar de
**`impressoras.letra_grossa`**, que sai. A espessura (ênfase no cupom inteiro)
deu lugar ao tamanho: a escala multiplica, pelo `GS !` do ESC/POS, as linhas de
destaque do cupom (título, mesa e TOTAL). Toda impressora que já existe nasce em
2x, que é o tamanho que o número da mesa já tinha — o cupom de produção sai
igual ao de ontem.

**`loja_config.nome_loja`, `telefone`, `cidade`, `uf`** (todas anuláveis): o
cabeçalho do recibo. Anuláveis porque a loja ainda não os informou, e a
migração não tem de onde tirá-los.

## Atomicidade

`BEGIN` explícito, como na `c5d9e17a24b8`: o `pysqlite` não abre transação
antes de DDL, e sem ele o primeiro `ALTER TABLE` rodaria em autocommit. Com ele,
as cinco colunas novas, o `DROP COLUMN` e a troca da `alembic_version` são um
commit só — queda de energia no meio devolve o banco como estava.

## A volta

O `downgrade` recria `letra_grossa` com 0 (letra fina) e derruba as colunas
novas. A escala escolhida e os dados da loja se perdem.
"""
from typing import Sequence, Union
import sqlite3

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2a8f5c3e917'
down_revision: Union[str, Sequence[str], None] = 'c5d9e17a24b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabela, coluna, tipo, nulável, default do SQL)
COLUNAS_NOVAS = (
    ("impressoras", "escala_fonte", sa.Integer(), False, "2"),
    ("loja_config", "nome_loja", sa.String(60), True, None),
    ("loja_config", "telefone", sa.String(20), True, None),
    ("loja_config", "cidade", sa.String(60), True, None),
    ("loja_config", "uf", sa.String(2), True, None),
)


def _colunas_existentes(tabela: str) -> set[str]:
    inspetor = sa.inspect(op.get_bind())
    return {coluna["name"] for coluna in inspetor.get_columns(tabela)}


def _abrir_transacao() -> None:
    """`BEGIN` explícito, para o `ALTER TABLE` entrar na transação. Ver o cabeçalho."""
    if context.is_offline_mode():  # pragma: no cover - o app só migra conectado
        return
    conexao = op.get_bind()
    dbapi = conexao.connection.dbapi_connection
    if isinstance(dbapi, sqlite3.Connection) and not dbapi.in_transaction:
        conexao.exec_driver_sql("BEGIN")


def _adicionar(tabela: str, coluna: str, tipo, nulavel: bool, padrao: str | None) -> None:
    if coluna in _colunas_existentes(tabela):
        return
    # `server_default` no que é `NOT NULL`: o `ADD COLUMN` do SQLite exige um
    # default para preencher as linhas que já estão lá.
    op.add_column(
        tabela,
        sa.Column(
            coluna,
            tipo,
            nullable=nulavel,
            server_default=None if padrao is None else sa.text(padrao),
        ),
    )


def upgrade() -> None:
    """Upgrade schema."""
    _abrir_transacao()
    for coluna in COLUNAS_NOVAS:
        _adicionar(*coluna)
    # `DROP COLUMN` nativo (SQLite 3.35+), pelo motivo da `a3e6b91c4d05`: o
    # `batch_alter_table` recriaria `impressoras` com `categorias` apontando
    # para ela e o `foreign_keys=ON` ligado.
    if "letra_grossa" in _colunas_existentes("impressoras"):
        op.execute("ALTER TABLE impressoras DROP COLUMN letra_grossa")


def downgrade() -> None:
    """Downgrade schema."""
    _abrir_transacao()
    _adicionar("impressoras", "letra_grossa", sa.Boolean(), False, "0")
    for tabela, coluna, *_ in reversed(COLUNAS_NOVAS):
        if coluna in _colunas_existentes(tabela):
            op.execute(f"ALTER TABLE {tabela} DROP COLUMN {coluna}")
