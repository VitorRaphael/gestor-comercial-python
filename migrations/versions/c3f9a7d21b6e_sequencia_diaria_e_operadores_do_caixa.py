"""sequência diária e operadores de abertura/fechamento do caixa

Revision ID: c3f9a7d21b6e
Revises: 06b890e91ef1
Create Date: 2026-08-26 00:00:00.000000

Histórico de Fechamentos (Controle de Turnos): `numero_sequencial_dia` guarda
a ordem do fechamento no dia de `fechado_em`, calculada e gravada uma única
vez por `CaixaService.fechar` — nunca recalculada depois. `aberto_por_id` e
`fechado_por_id` guardam quem operou cada ponta do turno, para o relatório
"Xº Fechamento do dia" mostrar os dois operadores.

Todas nullable de propósito, sem backfill: caixa antigo não tem como saber
retroativamente quem abriu/fechou nem em que ordem, e não há RN que exija
essas colunas para caixa já encerrado antes desta migração.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f9a7d21b6e'
down_revision: Union[str, Sequence[str], None] = '06b890e91ef1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_CAIXAS_ABERTO_POR = "fk_caixas_aberto_por_id_funcionarios"
FK_CAIXAS_FECHADO_POR = "fk_caixas_fechado_por_id_funcionarios"


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("numero_sequencial_dia", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("aberto_por_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("fechado_por_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            FK_CAIXAS_ABERTO_POR, "funcionarios", ["aberto_por_id"], ["id"]
        )
        batch_op.create_foreign_key(
            FK_CAIXAS_FECHADO_POR, "funcionarios", ["fechado_por_id"], ["id"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.drop_constraint(FK_CAIXAS_FECHADO_POR, type_="foreignkey")
        batch_op.drop_constraint(FK_CAIXAS_ABERTO_POR, type_="foreignkey")
        batch_op.drop_column("fechado_por_id")
        batch_op.drop_column("aberto_por_id")
        batch_op.drop_column("numero_sequencial_dia")
