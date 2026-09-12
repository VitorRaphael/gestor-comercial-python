"""subcategoria ativa e produto arquivado

Revision ID: a3e6b91c4d05
Revises: b6e2d80a3f14
Create Date: 2026-09-12 00:00:00.000001

Pedido do Vitor (§9.13): os três botões do rodapé do Cardápio passaram a agir
sobre o que está selecionado — categoria, subcategoria ou produto —, e duas
dessas ações não tinham onde ser gravadas.

**`subcategorias.ativo`** — desativar uma subdivisão passou a ser uma REGRA DE
VENDA, como já era a da categoria: os produtos dela somem do balcão sem sair do
cadastro. Isso reverte, de propósito e a pedido, a decisão do §9.9 de a
subcategoria não ter estado. `NOT NULL DEFAULT 1` e um `UPDATE` explícito nas
linhas que já existem: banco em uso tem subdivisão gravada, e uma coluna nova
com `NULL` faria a consulta de lançamento (`subcategorias.ativo = 1`) sumir com
produto do balcão na primeira abertura depois do upgrade — a pior forma
possível de descobrir uma migração, com o food truck aberto.

**`produtos.arquivado`** — a exclusão em cascata da subcategoria (liberada pela
Senha Master) apaga de verdade quem nunca foi vendido e MARCA quem já tem venda
registrada. Sem a marca, só haveria dois caminhos para um produto com
histórico: apagar a linha (e arrancar junto o item da comanda, o relatório e o
cupom que já saíram) ou deixá-lo no cardápio depois de o gerente ter mandado
excluir. `NOT NULL DEFAULT 0`: produto que já existe nunca foi arquivado.

**O que esta migração NÃO faz**, e é a mesma regra de ouro da `e2c7b4f9a613` e
da `f8d1a6c40b27`: não toca em `categorias`, não toca em `impressoras` e não
mexe em vínculo de impressão nenhum. O roteamento continua saindo de
`produto.categoria.impressora` (`impressao_service._destino_do_item`), e
nenhuma impressora precisa ser reconfigurada depois deste upgrade.

Os dois passos são idempotentes pelo motivo de sempre: a máquina do food truck
é a única cópia do banco, e se alguém tiver acrescentado a coluna à mão para
destravar um boot, a migração tem que passar por cima em silêncio em vez de
derrubar o app no arranque. A checagem é feita com o inspetor, à mão, porque o
SQLite não aceita `ADD COLUMN IF NOT EXISTS` (o `ALTER TABLE` dele é mínimo de
propósito) e o Alembic repassaria a cláusula crua.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3e6b91c4d05'
down_revision: Union[str, Sequence[str], None] = 'b6e2d80a3f14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUNA_SUBCATEGORIA = "ativo"
COLUNA_PRODUTO = "arquivado"


def _tem_coluna(tabela: str, coluna: str) -> bool:
    inspetor = sa.inspect(op.get_bind())
    return coluna in {c["name"] for c in inspetor.get_columns(tabela)}


def upgrade() -> None:
    """Upgrade schema."""
    if not _tem_coluna("subcategorias", COLUNA_SUBCATEGORIA):
        # `server_default` na hora de criar a coluna, e não só o `default` do
        # SQLAlchemy: o default do ORM só vale para linha inserida pelo ORM, e
        # o `ALTER TABLE ADD COLUMN NOT NULL` do SQLite exige um default para
        # poder preencher as linhas que já estão lá.
        op.add_column(
            "subcategorias",
            sa.Column(
                COLUNA_SUBCATEGORIA,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )
        # Cinto: se a coluna tiver nascido de outro caminho (um banco tocado à
        # mão), as linhas antigas podem estar com NULL. Uma subdivisão sem
        # estado é uma subdivisão que não vende.
        op.execute("UPDATE subcategorias SET ativo = 1 WHERE ativo IS NULL")

    if not _tem_coluna("produtos", COLUNA_PRODUTO):
        op.add_column(
            "produtos",
            sa.Column(
                COLUNA_PRODUTO,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
        op.execute("UPDATE produtos SET arquivado = 0 WHERE arquivado IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    # `ALTER TABLE ... DROP COLUMN` nativo (SQLite 3.35+, e o app embarca a
    # 3.50) em vez de `batch_alter_table`: o batch RECRIA a tabela, e o
    # `DROP TABLE produtos` do meio do caminho esbarra nas linhas de
    # `combo_itens`/`itens_comanda` que apontam para ela — com o
    # `PRAGMA foreign_keys=ON` do §3.5 ligado, a volta morria com "FOREIGN KEY
    # constraint failed". Ver o cabeçalho da `f8d1a6c40b27`.
    #
    # Voltar perde as duas informações e não há para onde movê-las: um produto
    # arquivado reaparece no cardápio (é o estado anterior a esta revisão, e o
    # menos ruim dos dois — melhor um item de volta na tela que um item some do
    # relatório), e toda subdivisão volta a vender.
    if _tem_coluna("produtos", COLUNA_PRODUTO):
        op.execute(f"ALTER TABLE produtos DROP COLUMN {COLUNA_PRODUTO}")
    if _tem_coluna("subcategorias", COLUNA_SUBCATEGORIA):
        op.execute(f"ALTER TABLE subcategorias DROP COLUMN {COLUNA_SUBCATEGORIA}")
