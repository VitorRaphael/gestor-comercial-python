"""campos de auditoria: troco, valor_quitado, cancelamento e timestamps de caixa

Revision ID: a6108ce87d55
Revises: 1eb3a1232a49
Create Date: 2026-08-20 20:23:10.679565

As duas colunas NOT NULL (caixas.aberto_em e pagamentos.valor_quitado) entram
em três passos — cria nullable, preenche as linhas antigas, aperta pra NOT NULL.
Adicionar NOT NULL direto quebraria em qualquer banco que já tenha vendas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6108ce87d55'
down_revision: Union[str, Sequence[str], None] = '1eb3a1232a49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_COMANDAS_CANCELADO_POR = "fk_comandas_cancelado_por_id_funcionarios"
FK_ITENS_CANCELADO_POR = "fk_itens_comanda_cancelado_por_id_funcionarios"


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("aberto_em", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("fechado_em", sa.DateTime(), nullable=True))

    op.execute("UPDATE caixas SET aberto_em = CURRENT_TIMESTAMP WHERE aberto_em IS NULL")

    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.alter_column("aberto_em", existing_type=sa.DateTime(), nullable=False)

    with op.batch_alter_table("comandas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cancelada_em", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("motivo_cancelamento", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("cancelado_por_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            FK_COMANDAS_CANCELADO_POR, "funcionarios", ["cancelado_por_id"], ["id"]
        )

    with op.batch_alter_table("itens_comanda", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cancelado_em", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("cancelado_por_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            FK_ITENS_CANCELADO_POR, "funcionarios", ["cancelado_por_id"], ["id"]
        )

    with op.batch_alter_table("pagamentos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("troco", sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(
            sa.Column("valor_quitado", sa.Numeric(precision=10, scale=2), nullable=True)
        )

    op.execute("UPDATE pagamentos SET valor_quitado = 0 WHERE valor_quitado IS NULL")

    with op.batch_alter_table("pagamentos", schema=None) as batch_op:
        batch_op.alter_column(
            "valor_quitado", existing_type=sa.Numeric(precision=10, scale=2), nullable=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("pagamentos", schema=None) as batch_op:
        batch_op.drop_column("valor_quitado")
        batch_op.drop_column("troco")

    with op.batch_alter_table("itens_comanda", schema=None) as batch_op:
        batch_op.drop_constraint(FK_ITENS_CANCELADO_POR, type_="foreignkey")
        batch_op.drop_column("cancelado_por_id")
        batch_op.drop_column("cancelado_em")

    with op.batch_alter_table("comandas", schema=None) as batch_op:
        batch_op.drop_constraint(FK_COMANDAS_CANCELADO_POR, type_="foreignkey")
        batch_op.drop_column("cancelado_por_id")
        batch_op.drop_column("motivo_cancelamento")
        batch_op.drop_column("cancelada_em")

    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.drop_column("fechado_em")
        batch_op.drop_column("aberto_em")
