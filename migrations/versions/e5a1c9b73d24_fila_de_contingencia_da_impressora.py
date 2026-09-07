"""fila de contingência da impressora

Revision ID: e5a1c9b73d24
Revises: b4d7e2c91a08
Create Date: 2026-09-07 00:00:00.000000

Fase 3 de `Mitigação de Falhas.md`. Cria `fila_impressao_pendente`, onde fica o
cupom que a impressora recusou.

O RNF de §2 (impressora quebrada não derruba a venda) já era cumprido: a falha
virava aviso âmbar e o cliente ia embora pago. O que faltava era a outra metade
— o **cupom** se perdia, e recuperá-lo dependia de o operador achar a comanda e
clicar "2ª via" à mão, no meio do pico.

A tabela guarda o documento já montado (JSON de `BlocoTexto`) e não o id da
comanda: reimprimir tem que sair igual ao que teria saído na hora, e nem todo
cupom vem de comanda (fechamento de caixa, teste de impressora). Ver a docstring
de `domain/fila_impressao.py` para o resto do porquê.

O índice em `criado_em` existe porque toda leitura da fila é por ordem de
chegada (imprimir o mais antigo primeiro) ou por poda do excedente — as duas
varreriam a tabela inteira sem ele, pelo mesmo motivo do §3.5.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'e5a1c9b73d24'
down_revision: Union[str, Sequence[str], None] = 'b4d7e2c91a08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fila_impressao_pendente",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("impressora_id", sa.Integer(), nullable=False),
        sa.Column("documento", sa.Text(), nullable=False),
        sa.Column("descricao", sa.String(length=120), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("tentativas", sa.Integer(), nullable=False),
        sa.Column("ultimo_erro", sa.String(length=400), nullable=True),
        sa.ForeignKeyConstraint(["impressora_id"], ["impressoras.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fila_impressao_pendente_impressora_id",
        "fila_impressao_pendente",
        ["impressora_id"],
    )
    op.create_index(
        "ix_fila_impressao_pendente_criado_em",
        "fila_impressao_pendente",
        ["criado_em"],
    )


def downgrade() -> None:
    op.drop_index("ix_fila_impressao_pendente_criado_em", table_name="fila_impressao_pendente")
    op.drop_index("ix_fila_impressao_pendente_impressora_id", table_name="fila_impressao_pendente")
    op.drop_table("fila_impressao_pendente")
