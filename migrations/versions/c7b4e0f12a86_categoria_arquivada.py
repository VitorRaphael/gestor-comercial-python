"""categoria arquivada

Revision ID: c7b4e0f12a86
Revises: a3e6b91c4d05
Create Date: 2026-09-12 00:00:00.000002

Pedido do Vitor (§9.14): excluir uma categoria inteira, **mesmo com itens e
subcategorias dentro**, mediante a Senha Master. O §9.13 já tinha feito isso
para a subcategoria; a categoria esbarra numa coisa que a subcategoria não
tinha.

**`produtos.categoria_id` é NOT NULL.** Um produto que já foi vendido não pode
sair do banco (arrancaria o item da comanda, o total do turno e o cupom que já
saiu na bobina), e também não pode ficar apontando para uma categoria que
deixou de existir. Por isso a categoria que ainda segura produto arquivado
**não é apagada: é marcada**, e some de todas as telas pela mesma porta que o
produto arquivado do §9.13.

Quando nenhum produto da categoria tem histórico, nada disso acontece: a linha
é apagada de verdade, como sempre foi.

`NOT NULL DEFAULT 0` — categoria que já existe nunca foi arquivada. Não há dado
a migrar nem a chutar, que é a diferença para a `c1d5b8e37a42`.

**O que esta migração NÃO faz**, a mesma regra de ouro da `e2c7b4f9a613`, da
`f8d1a6c40b27` e da `a3e6b91c4d05`: não toca em `impressoras` nem em
`categorias.impressora_id`. O roteamento continua saindo de
`produto.categoria.impressora` (`impressao_service._destino_do_item`) e nenhuma
impressora precisa ser reconfigurada depois deste upgrade.

**O que ela também não faz, e é uma decisão:** não mexe na `UNIQUE` de
`categorias.nome`. A categoria arquivada continua ocupando o nome, e quem
libera o nome é o service, renomeando a linha para `Lanches [excluída #3]` na
hora de arquivar — assim o gerente recria "Lanches" no minuto seguinte. Tirar a
`UNIQUE` exigiria recriar a tabela `categorias` inteira, com `produtos` e
`subcategorias` apontando para ela e o `PRAGMA foreign_keys=ON` ligado (ver o
cabeçalho da `f8d1a6c40b27`): risco grande para resolver no banco o que uma
linha de service resolve.

O passo é idempotente pelo motivo de sempre: a máquina do food truck é a única
cópia do banco, e se alguém tiver acrescentado a coluna à mão para destravar um
boot, a migração tem que passar por cima em silêncio em vez de derrubar o app
no arranque. A checagem é feita com o inspetor, à mão, porque o SQLite não
aceita `ADD COLUMN IF NOT EXISTS`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7b4e0f12a86'
down_revision: Union[str, Sequence[str], None] = 'a3e6b91c4d05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUNA = "arquivado"


def _tem_coluna() -> bool:
    inspetor = sa.inspect(op.get_bind())
    return COLUNA in {c["name"] for c in inspetor.get_columns("categorias")}


def upgrade() -> None:
    """Upgrade schema."""
    if not _tem_coluna():
        op.add_column(
            "categorias",
            sa.Column(COLUNA, sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
        # Cinto, como na `a3e6b91c4d05`: se a coluna tiver nascido de outro
        # caminho, as linhas antigas podem estar com NULL — e categoria sem
        # estado é categoria que some do cardápio.
        op.execute("UPDATE categorias SET arquivado = 0 WHERE arquivado IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    # Voltar faz as categorias arquivadas REAPARECEREM no Cardápio, junto com
    # os produtos arquivados delas. É o estado anterior a esta revisão, e o
    # menos ruim dos dois: melhor um grupo de volta na tela do que um produto
    # sumindo do relatório.
    if _tem_coluna():
        op.execute(f"ALTER TABLE categorias DROP COLUMN {COLUNA}")
