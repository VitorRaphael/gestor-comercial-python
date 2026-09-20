"""taxa de serviço: a chave da loja e o valor isolado na comanda

Revision ID: e4b8c2a6d913
Revises: b9d2f5a31c47
Create Date: 2026-09-19 00:00:00.000000

Pedido do Vitor (§9.23), em duas partes que viajam juntas.

**`loja_config.aceita_taxa_servico`** (`NOT NULL DEFAULT 1`). O interruptor
"Cobrar taxa de serviço (10%)" da Central de Loja. Ligado, porque é o que a loja
sempre fez: antes desta coluna o "Fechar conta" já oferecia os 10% a toda mesa,
e a linha singleton que já existe reabre oferecendo — só deixa de oferecer se o
dono desligar. Mora em `loja_config`, e não em `preferencias`, porque é regra de
negócio: o `ComandaService` recusa a taxa com ela desligada.

**`comandas.valor_taxa_servico`** (`NOT NULL DEFAULT 0`). A taxa em reais,
gravada à parte no mesmo commit que põe a comanda em conferência, para o
fechamento do dia somar "quanto da venda foi taxa de serviço" sem refazer a
conta de cada comanda a partir dos itens.

As comandas que JÁ passaram pela conferência com taxa ganham o valor aqui,
calculado do jeito que o app calculava: soma dos itens não cancelados pelo preço
congelado, e `subtotal × percentual ÷ 100` arredondado meio-pra-cima nos
centavos. A conta é em `Decimal`, no Python, e não em SQL: o `ROUND` do SQLite
opera sobre `REAL`, e `131.50 * 10 / 100` em ponto flutuante é
`13.149999999999999`, a um fio de virar R$ 13,14. A regra é COPIADA do
`comanda_service`, e não importada: uma migração tem que fazer amanhã o que fez
hoje, mesmo que a regra do app mude.

Comanda aberta, cancelada ou sem taxa fica no zero do default — e é o valor
certo para as três.

## Atômica de verdade

O mesmo `BEGIN` explícito da `b9d2f5a31c47`, pelo mesmo motivo: o Alembic trata
o DDL do SQLite como não-transacional, e o `ALTER TABLE` que chega primeiro
rodaria em autocommit. Com o `BEGIN`, as duas colunas, o preenchimento e a
troca da `alembic_version` são um commit só — uma queda no meio não deixa
coluna no arquivo com a versão na revisão anterior.

Os `if` das colunas são o cinto para o banco que as ganhou à mão, e o
preenchimento roda sempre: é seguro porque o app não grava nada antes de a
migração terminar, e necessário porque numa coluna posta à mão toda comanda
estaria no zero do default.

**O que esta migração NÃO faz:** não toca em `taxa_servico_percentual` nem em
item nenhum. A conta que já foi emitida continua como foi emitida.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence, Union
import sqlite3

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4b8c2a6d913'
down_revision: Union[str, Sequence[str], None] = 'b9d2f5a31c47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabela, coluna, tipo, default do SQL)
COLUNAS_NOVAS = (
    ("loja_config", "aceita_taxa_servico", sa.Boolean(), "1"),
    ("comandas", "valor_taxa_servico", sa.Numeric(10, 2), "0"),
)

CENTAVOS = Decimal("0.01")


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


def _dinheiro(valor: object) -> Decimal:
    """O `dinheiro()` do app, na medida do que esta migração lê do banco.

    `str()` antes do `Decimal` porque o SQLite devolve `NUMERIC` como `float`, e
    `Decimal(13.15)` guarda a dízima binária inteira.
    """
    return Decimal(str(valor)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _preencher_valor_da_taxa() -> None:
    conexao = op.get_bind()
    com_taxa = conexao.execute(
        sa.text(
            "SELECT id, taxa_servico_percentual FROM comandas "
            "WHERE taxa_servico_percentual IS NOT NULL AND taxa_servico_percentual <> 0"
        )
    ).all()
    for comanda_id, percentual in com_taxa:
        itens = conexao.execute(
            sa.text(
                "SELECT preco_unit_congelado, quantidade FROM itens_comanda "
                "WHERE comanda_id = :comanda AND cancelado = 0"
            ),
            {"comanda": comanda_id},
        ).all()
        subtotal = _dinheiro(sum((_dinheiro(preco) * quantidade for preco, quantidade in itens), Decimal(0)))
        valor = _dinheiro(subtotal * _dinheiro(percentual) / Decimal("100"))
        conexao.execute(
            sa.text("UPDATE comandas SET valor_taxa_servico = :valor WHERE id = :comanda"),
            {"valor": str(valor), "comanda": comanda_id},
        )


def upgrade() -> None:
    """Upgrade schema."""
    _abrir_transacao()
    for tabela, coluna, tipo, padrao in COLUNAS_NOVAS:
        if coluna not in _colunas_existentes(tabela):
            # `server_default`, e não só o `default` do ORM: o
            # `ADD COLUMN NOT NULL` do SQLite exige um default para preencher as
            # linhas que já estão lá.
            op.add_column(
                tabela,
                sa.Column(coluna, tipo, nullable=False, server_default=sa.text(padrao)),
            )
    # Cinto, como na `b9d2f5a31c47`: coluna nascida de outro caminho pode ter
    # NULL, e `bool(None)` desligaria a taxa da loja em silêncio.
    op.execute("UPDATE loja_config SET aceita_taxa_servico = 1 WHERE aceita_taxa_servico IS NULL")
    _preencher_valor_da_taxa()


def downgrade() -> None:
    """Downgrade schema."""
    # `DROP COLUMN` nativo (SQLite 3.35+), pelo motivo da `a3e6b91c4d05`: o
    # `batch_alter_table` recriaria `comandas` inteira com `itens_comanda` e
    # `pagamentos` apontando para ela e o `foreign_keys=ON` ligado.
    #
    # Voltar perde as duas coisas: o código anterior oferece a taxa a toda
    # mesa, e refaz o valor da taxa a partir do percentual quando precisa dele.
    for tabela, coluna, _tipo, _padrao in reversed(COLUNAS_NOVAS):
        if coluna in _colunas_existentes(tabela):
            op.execute(f"ALTER TABLE {tabela} DROP COLUMN {coluna}")
