"""snapshot do mix de vendas no fechamento do caixa

Revision ID: 625114038889
Revises: c3f9a7d21b6e
Create Date: 2026-08-27 00:00:00.000000

`resumo_produtos_json` guarda, congelado no momento de `CaixaService.fechar`,
o mix de vendas do turno (produto, quantidade, valor unitário, subtotal) —
o Dashboard Mensal agrega o ranking de produtos lendo só essa coluna nos
fechamentos do mês, sem re-consultar `item_comanda`.

Nullable e sem backfill: caixa fechado antes desta migração não tem como
recuperar retroativamente o mix vendido naquele turno específico (a soma dos
itens de hoje não corresponde ao que foi vendido então), então esses
fechamentos simplesmente ficam fora do ranking mensal quando o mês consultado
inclui turnos antigos.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '625114038889'
down_revision: Union[str, Sequence[str], None] = 'c3f9a7d21b6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resumo_produtos_json", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.drop_column("resumo_produtos_json")
