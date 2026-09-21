"""remove a taxa de serviço e a comissão que saía dela

Revision ID: c5d9e17a24b8
Revises: f6a1d3b78c42
Create Date: 2026-09-21 00:00:00.000000

Pedido do Vitor (§9.26): a taxa de serviço de 10% deixa de existir no sistema
inteiro — regra, banco e tela. O total da conta volta a ser, e só, a soma dos
itens lançados.

A comissão do garçom (§9.25, de ontem) **sai junto, e não por escolha de
escopo**: ela nunca teve valor próprio. `ComissaoDaConta.valor` era o
`valor_taxa_servico` da conta, por decisão explícita daquele item ("uma segunda
cópia do mesmo número acabaria divergindo"). Sem taxa, toda comissão do sistema
valeria R$ 0,00 — o card não apareceria, o KPI de Funcionários ficaria zerado e
o repasse não teria o que repassar. Manter as colunas seria guardar o controle
de um pagamento que não existe mais.

## As cinco colunas que saem

* `comandas.taxa_servico_percentual` (`f1a2b3c4d5e6`)
* `comandas.valor_taxa_servico` (`e4b8c2a6d913`)
* `comandas.comissao_paga` e `comandas.comissao_paga_em` (`f6a1d3b78c42`)
* `loja_config.aceita_taxa_servico` (`e4b8c2a6d913`)

`DROP COLUMN` nativo (SQLite 3.35+, e o app embarca a 3.50) e não
`batch_alter_table`, pelo motivo da `a3e6b91c4d05`: o batch RECRIA a tabela, e
`comandas` tem `itens_comanda` e `pagamentos` apontando para ela com o
`PRAGMA foreign_keys=ON` do §3.5 ligado.

**O que o faturamento perde: nada.** O dinheiro recebido mora em `pagamentos`,
e nenhuma linha de lá é tocada aqui. Uma conta fechada com taxa continua com o
valor que o cliente pagou. O que some é a decomposição "quanto daquilo foi
taxa" — o relatório do turno deixa de ter a linha, porque a loja deixa de ter a
cobrança.

## Os movimentos de caixa do tipo `COMISSAO` viram `DESPESA`

`movimentos_caixa.tipo` é `VARCHAR` sem `CHECK`, então o schema nunca guardou a
lista de tipos — quem guarda é o enum `TipoMovimento`, e ler "COMISSAO" com o
valor fora do enum estoura na hora de montar o objeto. Apagar as linhas também
não serve: aquele dinheiro **saiu da gaveta de verdade**, e apagá-lo faria o
turno correspondente parecer que sobrou dinheiro no fechamento.

Então o repasse vira `DESPESA`, que é o tipo que já significa "saiu da gaveta e
não é venda", com a descrição preservada (ela começa com "Comissão de ...", e é
o que explica a linha para quem conferir o turno depois). A conta do saldo
esperado dá exatamente o mesmo número antes e depois: os dois tipos estão em
`TIPOS_QUE_SAEM_DA_GAVETA`.

Na máquina do pai do Vitor isto não deve encontrar nada: o `.exe` que roda lá é
anterior ao §9.23, e a taxa nunca chegou a ser cobrada em produção. O
tratamento existe porque o banco de desenvolvimento tem esses dados e porque
uma migração que só funciona no banco vazio não é uma migração.

## Atômica de verdade

O mesmo `BEGIN` explícito das três irmãs anteriores (`b9d2f5a31c47`,
`e4b8c2a6d913`, `f6a1d3b78c42`): o Alembic trata o DDL do SQLite como
não-transacional, e o primeiro `ALTER TABLE` rodaria em autocommit. Com ele, a
reescrita dos movimentos, os cinco `DROP COLUMN` e a troca da
`alembic_version` são um commit só.

## A volta

O `downgrade` recria as cinco colunas com o mesmo tipo e o mesmo default de
origem, e **não recupera dado nenhum**: a taxa cobrada em cada conta antiga e a
marca de repasse foram apagadas na ida. Voltar devolve o schema, com toda
comanda em `valor_taxa_servico = 0` e a loja com a taxa ligada — o estado de
quem acabou de instalar a `e4b8c2a6d913`. As linhas de `DESPESA` que já foram
`COMISSAO` **ficam como estão**: o texto da descrição é o único vínculo, e
reclassificar por ele reescreveria uma despesa de verdade que alguém tenha
descrito com a palavra "Comissão".
"""
from typing import Sequence, Union
import sqlite3

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5d9e17a24b8'
down_revision: Union[str, Sequence[str], None] = 'f6a1d3b78c42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabela, coluna, tipo, nulável, default do SQL) — na ordem em que o
# `downgrade` as recria. O `upgrade` derruba na ordem inversa.
COLUNAS_REMOVIDAS = (
    ("loja_config", "aceita_taxa_servico", sa.Boolean(), False, "1"),
    ("comandas", "taxa_servico_percentual", sa.Numeric(5, 2), True, None),
    ("comandas", "valor_taxa_servico", sa.Numeric(10, 2), False, "0"),
    ("comandas", "comissao_paga", sa.Boolean(), False, "0"),
    ("comandas", "comissao_paga_em", sa.DateTime(), True, None),
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


def upgrade() -> None:
    """Upgrade schema."""
    _abrir_transacao()
    # ANTES dos `DROP COLUMN`: se a migração parar no meio, um movimento com
    # tipo fora do enum é o que impede o programa de abrir a tela de Caixa.
    op.execute("UPDATE movimentos_caixa SET tipo = 'DESPESA' WHERE tipo = 'COMISSAO'")
    for tabela, coluna, _tipo, _nulavel, _padrao in reversed(COLUNAS_REMOVIDAS):
        if coluna in _colunas_existentes(tabela):
            op.execute(f"ALTER TABLE {tabela} DROP COLUMN {coluna}")


def downgrade() -> None:
    """Downgrade schema."""
    _abrir_transacao()
    for tabela, coluna, tipo, nulavel, padrao in COLUNAS_REMOVIDAS:
        if coluna in _colunas_existentes(tabela):
            continue
        # `server_default` no que é `NOT NULL`: o `ADD COLUMN` do SQLite exige
        # um default para preencher as linhas que já estão lá.
        op.add_column(
            tabela,
            sa.Column(
                coluna,
                tipo,
                nullable=nulavel,
                server_default=None if padrao is None else sa.text(padrao),
            ),
        )
