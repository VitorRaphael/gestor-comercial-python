"""observação da abertura do caixa

Revision ID: d9b4c7e21f30
Revises: c1d5b8e37a42
Create Date: 2026-09-09 00:00:00.000000

Pedido do Vitor junto com os modais novos de abrir/fechar caixa (§9.7): a tela
de abertura passou a ter um campo "OBSERVAÇÃO (opcional)", com o exemplo "fundo
recebido do cofre".

O fechamento já tinha o dele (`observacao_fechamento`, que sai no relatório
impresso do turno); a abertura, não — e um campo que o operador preenche e o
sistema descarta é pior que campo nenhum. Numa tela que declara dinheiro, é o
tipo de coisa que só se descobre quando alguém procura a anotação e ela nunca
existiu.

`String(500)` e nullable, igual ao par de fechamento: turno já aberto antes
desta coluna existir simplesmente não tem anotação, que é o mesmo estado de um
turno aberto sem o operador escrever nada.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9b4c7e21f30'
down_revision: Union[str, Sequence[str], None] = 'c1d5b8e37a42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("observacao_abertura", sa.String(500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Simétrico: a anotação some junto com a coluna. Não há para onde movê-la —
    # `observacao_fechamento` é de outro momento do turno e juntar as duas
    # produziria um texto que ninguém escreveu.
    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.drop_column("observacao_abertura")
