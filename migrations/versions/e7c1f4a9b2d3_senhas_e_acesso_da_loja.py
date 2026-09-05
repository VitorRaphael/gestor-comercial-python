"""cria loja_config (Senha Master, Senha Operacional, CPF do Dono)

Revision ID: e7c1f4a9b2d3
Revises: b7c9e2f14a03
Create Date: 2026-09-05 00:00:00.000000

Módulo "Senhas e Acesso" (§3.13): tabela singleton (sempre id=1) com os três
segredos operacionais da loja, cada um só com hash+salt — nunca texto puro.
O seed dos valores padrão (Senha Master "050727", Senha Operacional
"26407200") não é feito aqui: fica a cargo de `LojaConfigService.
obter_ou_criar()`, chamado sob demanda na primeira vez que qualquer tela
tocar no módulo, mesmo padrão do primeiro gerente em `repository/seed.py`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7c1f4a9b2d3'
down_revision: Union[str, Sequence[str], None] = 'b7c9e2f14a03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "loja_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("senha_master_hash", sa.String(length=128), nullable=False),
        sa.Column("senha_master_salt", sa.String(length=64), nullable=False),
        sa.Column("senha_operacional_hash", sa.String(length=128), nullable=False),
        sa.Column("senha_operacional_salt", sa.String(length=64), nullable=False),
        sa.Column("cpf_dono_hash", sa.String(length=128), nullable=True),
        sa.Column("cpf_dono_salt", sa.String(length=64), nullable=True),
        sa.Column("cpf_dono_definido", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table("loja_config")
