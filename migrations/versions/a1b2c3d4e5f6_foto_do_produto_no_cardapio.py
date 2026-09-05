"""foto do produto no cardápio

Revision ID: a1b2c3d4e5f6
Revises: 490c75504570
Create Date: 2026-09-05 00:00:00.000000

Adiciona `produtos.imagem_path`: guarda só o NOME do arquivo da miniatura já
processada (JPEG, máx 120x120, ~15-25KB), salva em
`<dir_dados>/uploads/thumbnails/`. Nunca guarda o caminho absoluto (a pasta é
resolvida em runtime por `imagem_service`) nem o arquivo original pesado.
Nullable — produto sem foto continua normal, UI usa placeholder.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '490c75504570'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("produtos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("imagem_path", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("produtos", schema=None) as batch_op:
        batch_op.drop_column("imagem_path")
