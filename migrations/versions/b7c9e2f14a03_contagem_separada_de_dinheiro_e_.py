"""contagem separada de dinheiro e maquininha no fechamento

Revision ID: b7c9e2f14a03
Revises: f1a2b3c4d5e6
Create Date: 2026-09-03 00:00:00.000000

`Caixa.valor_contado` virava um único número contado na conferência, mas a
gaveta (dinheiro) e o extrato da maquininha (cartão/PIX) são duas contagens
físicas independentes, cada uma com sua própria diferença esperado x
contado. Vira `valor_contado_dinheiro` + `valor_contado_maquininha`.

Sem backfill: não há como saber retroativamente, a partir de um único
`valor_contado` histórico, quanto daquele total era dinheiro e quanto era
maquininha — a divisão nunca foi registrada. Projeto ainda em
desenvolvimento, sem dado de produção real a preservar, então a coluna
antiga é dropada direto em vez de migrada; fechamentos antigos ficam com as
duas contagens novas em branco (mesmo efeito de "não conferido" que já
existia pra um caixa recém-aberto).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c9e2f14a03'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.drop_column("valor_contado")
        batch_op.add_column(sa.Column("valor_contado_dinheiro", sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column("valor_contado_maquininha", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Simétrico ao upgrade: não há como recompor o `valor_contado` único a
    # partir das duas contagens separadas (não é soma — cada uma tem sua
    # própria diferença vs. um esperado diferente), então volta em branco.
    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.drop_column("valor_contado_maquininha")
        batch_op.drop_column("valor_contado_dinheiro")
        batch_op.add_column(sa.Column("valor_contado", sa.Numeric(10, 2), nullable=True))
