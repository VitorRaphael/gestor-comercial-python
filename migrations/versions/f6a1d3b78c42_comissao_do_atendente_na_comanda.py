"""comissão do atendente: se o repasse da taxa já foi feito

Revision ID: f6a1d3b78c42
Revises: e4b8c2a6d913
Create Date: 2026-09-20 00:00:00.000000

Pedido do Vitor (§9.25): a tela de pagamento ganhou o card "Comissão de
[garçom]", com os botões "Comissão paga" e "Comissão não paga", e as pendentes
viram uma lista para o gerente acertar no fim do turno.

**`comandas.comissao_paga`** (`NOT NULL DEFAULT 0`) e **`comissao_paga_em`**
(nula). O VALOR da comissão não ganha coluna: ele é o `valor_taxa_servico` do
§9.23 — a comissão É a taxa de serviço daquela conta —, e uma segunda cópia do
mesmo número seria uma divergência esperando acontecer. O que se grava é só o
que o sistema não consegue deduzir: se o dinheiro já foi para a mão do garçom.

## O passado entra como ACERTADO

Toda comanda FECHADA que já existe recebe `comissao_paga = 1`. Antes desta
coluna o repasse acontecia fora do sistema (no fim do turno, na mão), e nascer
com `0` faria o programa abrir uma lista de comissões "pendentes" de todas as
vendas antigas — dívida que ninguém tem. A data fica nula de propósito: não
sabemos quando foi, e inventar `agora` seria registrar como repasse de hoje o
que foi feito semanas atrás.

Comanda ABERTA, EM_CONFERENCIA ou CANCELADA fica no `0` do default: a primeira
ainda vai ser paga e as outras duas não geram repasse.

## Atômica de verdade

O mesmo `BEGIN` explícito das duas irmãs anteriores (`b9d2f5a31c47`,
`e4b8c2a6d913`), pelo mesmo motivo: o Alembic trata o DDL do SQLite como
não-transacional, e o `ALTER TABLE` que chega primeiro rodaria em autocommit.
Com o `BEGIN`, as colunas, a marcação do passado e a troca da
`alembic_version` são um commit só.

**O que esta migração NÃO faz:** não toca em `valor_taxa_servico`, em
`atendente_id` nem em movimento de caixa nenhum. O repasse que sai da gaveta
(`TipoMovimento.COMISSAO`) passa a existir daqui para a frente, e o tipo novo
não pede migração porque a coluna `movimentos_caixa.tipo` é `VARCHAR` sem
`CHECK`.
"""
from typing import Sequence, Union
import sqlite3

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a1d3b78c42'
down_revision: Union[str, Sequence[str], None] = 'e4b8c2a6d913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELA = "comandas"
# (coluna, tipo, nulável, default do SQL)
COLUNAS_NOVAS = (
    ("comissao_paga", sa.Boolean(), False, "0"),
    ("comissao_paga_em", sa.DateTime(), True, None),
)


def _colunas_existentes() -> set[str]:
    inspetor = sa.inspect(op.get_bind())
    return {coluna["name"] for coluna in inspetor.get_columns(TABELA)}


def _abrir_transacao() -> None:
    """`BEGIN` explícito, para o `ALTER TABLE` entrar na transação. Ver o cabeçalho."""
    if context.is_offline_mode():  # pragma: no cover - o app só migra conectado
        return
    conexao = op.get_bind()
    dbapi = conexao.connection.dbapi_connection
    if isinstance(dbapi, sqlite3.Connection) and not dbapi.in_transaction:
        conexao.exec_driver_sql("BEGIN")


def upgrade() -> None:
    """Upgrade schema."""
    _abrir_transacao()
    existentes = _colunas_existentes()
    for coluna, tipo, nulavel, padrao in COLUNAS_NOVAS:
        if coluna in existentes:
            continue
        # `server_default` no que é `NOT NULL`: o `ADD COLUMN` do SQLite exige
        # um default para preencher as linhas que já estão lá.
        op.add_column(
            TABELA,
            sa.Column(
                coluna,
                tipo,
                nullable=nulavel,
                server_default=None if padrao is None else sa.text(padrao),
            ),
        )
    # O passado entra como acertado — ver o cabeçalho. Roda sempre (e não só
    # quando a coluna nasce agora) pelo motivo da `b9d2f5a31c47`: numa coluna
    # posta à mão, toda comanda estaria no zero do default.
    op.execute(f"UPDATE {TABELA} SET comissao_paga = 1 WHERE status = 'FECHADA'")
    op.execute(f"UPDATE {TABELA} SET comissao_paga = 0 WHERE comissao_paga IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    # `DROP COLUMN` nativo (SQLite 3.35+), pelo motivo da `a3e6b91c4d05`: o
    # `batch_alter_table` recriaria `comandas` inteira com `itens_comanda` e
    # `pagamentos` apontando para ela e o `foreign_keys=ON` ligado.
    #
    # Voltar perde só o controle do repasse: o valor da comissão continua no
    # `valor_taxa_servico` de cada conta.
    existentes = _colunas_existentes()
    for coluna, _tipo, _nulavel, _padrao in reversed(COLUNAS_NOVAS):
        if coluna in existentes:
            op.execute(f"ALTER TABLE {TABELA} DROP COLUMN {coluna}")
