"""sub-modelo do produto no cardápio

Revision ID: e2c7b4f9a613
Revises: d9b4c7e21f30
Create Date: 2026-09-09 00:00:00.000001

Pedido do Vitor (§9.8): o cardápio real tem 15 categorias e 113 produtos, e
dentro de "Lanches" convivem coisas que não se parecem — artesanal, podrão,
combo. O sub-modelo é a subdivisão DENTRO da categoria, e é só isso: uma
etiqueta de organização de catálogo.

**A regra de ouro está no que esta migração NÃO faz.** Ela não toca em
`categorias`, não toca em `impressoras` e não cria vínculo de impressão
nenhum. O roteamento do cupom continua saindo de
`produto.categoria.impressora` (ver `impressao_service._destino_do_item`), e
por isso nenhuma impressora precisa ser reconfigurada depois deste upgrade: um
produto que ganha sub-modelo continua saindo exatamente na mesma bobina.

`TEXT NULL`, sem default: produto que já existe simplesmente não tem
sub-modelo, que é o mesmo estado de um produto novo cadastrado sem preencher o
campo. Nada a migrar, nada a chutar — é a diferença para a `a7f3c2e5d918`, que
precisou reescrever dado gravado.

O índice é composto (`categoria_id`, `subcategoria`) porque toda leitura do
sub-modelo é feita dentro de uma categoria: "quais sub-modelos existem em
Lanches" é a consulta que monta as sugestões do cadastro e as pílulas de filtro
do Cardápio. Com ele o SQLite responde varrendo o índice, sem abrir linha de
produto nenhuma.

Os dois passos são idempotentes — não porque o Alembic possa rodar a revisão
duas vezes (a `alembic_version` já impede isso), mas porque a máquina do food
truck é a única cópia do banco: se alguém tiver adicionado a coluna à mão para
destravar um boot, a migração precisa passar por cima em silêncio em vez de
derrubar o app no arranque.

O índice usa o `if_not_exists=True` do Alembic, que vira o `CREATE INDEX IF NOT
EXISTS` que o SQLite entende. A **coluna não pode** usar o mesmo atalho: o
SQLite não aceita `ADD COLUMN IF NOT EXISTS` (o `ALTER TABLE` dele é mínimo de
propósito), e o Alembic repassa a cláusula crua — o upgrade morreria com
`syntax error near "EXISTS"`. Por isso a checagem aqui é feita à mão, com o
inspetor.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2c7b4f9a613'
down_revision: Union[str, Sequence[str], None] = 'd9b4c7e21f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDICE = "idx_produtos_categoria_sub"
COLUNA = "subcategoria"


def _ja_tem_a_coluna() -> bool:
    inspetor = sa.inspect(op.get_bind())
    return COLUNA in {coluna["name"] for coluna in inspetor.get_columns("produtos")}


def upgrade() -> None:
    """Upgrade schema."""
    if not _ja_tem_a_coluna():
        # `add_column` direto, e não `batch_alter_table`: acrescentar coluna é a
        # única alteração que o SQLite faz nativamente, sem recriar a tabela. O
        # `batch` das outras migrações existe para DROP/ALTER, que ele não tem —
        # usá-lo aqui recriaria `produtos` inteira (e os índices dela) à toa.
        op.add_column("produtos", sa.Column(COLUNA, sa.String(80), nullable=True))
    op.create_index(
        INDICE,
        "produtos",
        ["categoria_id", COLUNA],
        if_not_exists=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Simétrico, e na ordem inversa: o índice depende da coluna. Voltar apaga
    # os sub-modelos digitados, e não há para onde movê-los — a categoria
    # continua sendo a categoria, e escrever o sub-modelo dentro do nome do
    # produto ("X Burguer (Podrão)") sujaria a busca e o cupom para sempre.
    op.drop_index(INDICE, table_name="produtos", if_exists=True)
    if _ja_tem_a_coluna():
        with op.batch_alter_table("produtos", schema=None) as batch_op:
            batch_op.drop_column(COLUNA)
