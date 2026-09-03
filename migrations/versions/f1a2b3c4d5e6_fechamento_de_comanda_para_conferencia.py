"""fechamento de comanda para conferência (pré-conta)

Revision ID: f1a2b3c4d5e6
Revises: d23a4f888a77
Create Date: 2026-09-03 00:00:00.000000

Adiciona o estado intermediário `EM_CONFERENCIA` entre `ABERTA` e `FECHADA`
(§ Fechamento/Conferência de Comanda): o garçom fecha o lançamento de itens,
emite a pré-conta, e só depois disso o pagamento pode ser recebido — `fechar()`
(que já existia e sempre significou "paga e mesa liberada") passa a exigir
esse estado em vez de `ABERTA`.

Também soma os dois campos que a pré-conta decide no momento do fechamento e
que precisam ficar congelados na comanda, pelo mesmo motivo de
`preco_unit_congelado` em `ItemComanda`: `taxa_servico_percentual` (opcional)
e `valor_desconto` (default 0). `em_conferencia_em` marca quando a conferência
começou, do mesmo jeito que `fechada_em`/`cancelada_em` já marcam suas
transições.

O `CHECK` do enum `status` é recriado via `batch_alter_table` porque SQLite
não suporta `ALTER TYPE`/`DROP CONSTRAINT` direto — o batch mode do Alembic
recria a tabela inteira com o novo conjunto de valores.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'd23a4f888a77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_COMANDA_OLD = sa.Enum('ABERTA', 'FECHADA', 'CANCELADA', name='statuscomanda')
_STATUS_COMANDA_NEW = sa.Enum(
    'ABERTA', 'EM_CONFERENCIA', 'FECHADA', 'CANCELADA', name='statuscomanda'
)


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("comandas", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_STATUS_COMANDA_OLD,
            type_=_STATUS_COMANDA_NEW,
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("em_conferencia_em", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("taxa_servico_percentual", sa.Numeric(5, 2), nullable=True))
        batch_op.add_column(
            sa.Column(
                "valor_desconto",
                sa.Numeric(10, 2),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Comanda hoje em EM_CONFERENCIA não tem estado antigo equivalente: volta
    # pra ABERTA (perde só a marca de "pré-conta já emitida", os itens
    # continuam intactos) — decisão simétrica à de outras migrações deste
    # projeto que preferem uma perda de metadado documentada a travar o
    # downgrade.
    op.execute(
        "UPDATE comandas SET status = 'ABERTA' WHERE status = 'EM_CONFERENCIA'"
    )
    with op.batch_alter_table("comandas", schema=None) as batch_op:
        batch_op.drop_column("valor_desconto")
        batch_op.drop_column("taxa_servico_percentual")
        batch_op.drop_column("em_conferencia_em")
        batch_op.alter_column(
            "status",
            existing_type=_STATUS_COMANDA_NEW,
            type_=_STATUS_COMANDA_OLD,
            existing_nullable=False,
        )
