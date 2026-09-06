"""índices nas chaves estrangeiras

Revision ID: b4d7e2c91a08
Revises: c8e3f6a2b910
Create Date: 2026-09-06 00:00:00.000000

Cria um índice para cada uma das **20 chaves estrangeiras** do schema
(`PRAGMA foreign_key_list` sobre o banco real — o número 38 que estava em
`REMASTERIZACAO-V1.md` §3.5 era contagem de `grep`, não do schema).

Motivo (§3.5): o SQLite cria índice sozinho para PK e UNIQUE, **nunca para
FK**. Sem isto, toda consulta quente do PDV — `comanda.itens`,
`pagamentos por caixa`, `mesa.comandas`, `itens cancelados do turno` — é
varredura da tabela inteira. Hoje, com o banco pequeno, não dói; depois de
meses de operação cada varredura cresce linearmente, e elas rodam dentro dos
laços do Dashboard Mensal. É a causa raiz do "degrada com o tempo".

Custo do outro lado da balança: cada índice é escrita extra no INSERT. Num
food truck, escrita é evento de balcão (um item lançado, um pagamento) e
leitura é tela inteira; a troca compensa com folga.

Nomes seguem o padrão do SQLAlchemy (`ix_<tabela>_<coluna>`), para o
`index=True` declarado no `domain/` e o banco já existente convergirem para o
mesmo schema — banco novo (via `create_all` nos testes) e banco antigo (via
esta migration) ficam idênticos.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b4d7e2c91a08'
down_revision: Union[str, Sequence[str], None] = 'c8e3f6a2b910'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (tabela, coluna) de cada FK do schema, na ordem das tabelas.
INDICES_DE_FK: tuple[tuple[str, str], ...] = (
    ("caixas", "aberto_por_id"),
    ("caixas", "fechado_por_id"),
    ("categorias", "impressora_id"),
    ("comandas", "mesa_id"),
    ("comandas", "usuario_id"),
    ("comandas", "cancelado_por_id"),
    ("comandas", "atendente_id"),
    ("comandas", "caixa_id"),
    ("combo_itens", "combo_id"),
    ("combo_itens", "produto_id"),
    ("itens_comanda", "comanda_id"),
    ("itens_comanda", "produto_id"),
    ("itens_comanda", "cancelado_por_id"),
    ("movimentos_caixa", "caixa_id"),
    ("movimentos_caixa", "usuario_id"),
    ("pagamentos", "comanda_id"),
    ("pagamentos", "funcionario_consumo_id"),
    ("produtos", "categoria_id"),
    ("quitacoes_consumo", "funcionario_id"),
    ("quitacoes_consumo", "autorizado_por_id"),
)


def upgrade() -> None:
    for tabela, coluna in INDICES_DE_FK:
        op.create_index(f"ix_{tabela}_{coluna}", tabela, [coluna], unique=False)


def downgrade() -> None:
    for tabela, coluna in reversed(INDICES_DE_FK):
        op.drop_index(f"ix_{tabela}_{coluna}", table_name=tabela)
