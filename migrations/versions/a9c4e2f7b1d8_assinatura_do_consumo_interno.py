"""assinatura manuscrita do consumo interno

Revision ID: a9c4e2f7b1d8
Revises: d2a8f5c3e917
Create Date: 2026-09-22

Cria `consumo_sessao_assinaturas`: uma linha por pagamento CONSUMO_INTERNO,
com o traço da assinatura do colaborador em JSON. A assinatura substitui o PIN
do gerente na hora de lançar o consumo no caixa.

Consumos lançados antes desta migração ficam sem linha aqui — foram
autorizados por PIN — e a tela de detalhes diz isso em vez de um quadro vazio.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9c4e2f7b1d8"
down_revision: Union[str, Sequence[str], None] = "d2a8f5c3e917"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELA = "consumo_sessao_assinaturas"


def upgrade() -> None:
    """Upgrade schema."""
    if TABELA in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABELA,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("id_funcionario", sa.Integer(), sa.ForeignKey("funcionarios.id"), nullable=False),
        sa.Column("id_sessao", sa.String(36), nullable=False, unique=True),
        sa.Column("data_hora", sa.DateTime(), nullable=False),
        sa.Column("valor_total_sessao", sa.Numeric(10, 2), nullable=False),
        sa.Column("traco_json", sa.Text(), nullable=False),
        sa.Column("id_pagamento", sa.Integer(), sa.ForeignKey("pagamentos.id"), nullable=False, unique=True),
    )
    op.create_index(
        "ix_consumo_sessao_assinaturas_id_funcionario", TABELA, ["id_funcionario"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_consumo_sessao_assinaturas_id_funcionario", table_name=TABELA)
    op.drop_table(TABELA)
