"""impressora com parametros de conexao e item_comanda.impresso_em

Revision ID: 06b890e91ef1
Revises: a6108ce87d55
Create Date: 2026-08-21 14:07:32.874096

Fase 4 (§3.12): a impressora deixa de ser só um nome e passa a guardar como
falar com o hardware, e o item da comanda passa a lembrar se já foi pra
cozinha.

As quatro colunas NOT NULL de `impressoras` (tipo_conexao, colunas, ativa,
padrao) entram em três passos — cria nullable, preenche as linhas antigas,
aperta pra NOT NULL. Adicionar NOT NULL direto quebraria em qualquer banco
que já tenha impressora cadastrada.

`impressoras.nome` também vira UNIQUE aqui (o Java já era; o Python tinha
deixado passar).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06b890e91ef1'
down_revision: Union[str, Sequence[str], None] = 'a6108ce87d55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UQ_IMPRESSORAS_NOME = "uq_impressoras_nome"

TIPO_CONEXAO = sa.Enum(
    "USB", "SERIAL", "REDE", "WINDOWS", "ARQUIVO", name="tipoconexaoimpressora"
)

# 48 colunas = bobina de 80mm, o tamanho que o food truck comprou.
COLUNAS_PADRAO = 48


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("impressoras", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tipo_conexao", TIPO_CONEXAO, nullable=True))
        batch_op.add_column(sa.Column("vendor_id", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("product_id", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("porta_serial", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("baudrate", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("host", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("porta_rede", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("nome_fila", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("caminho_arquivo", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("colunas", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("ativa", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("padrao", sa.Boolean(), nullable=True))

    # Impressora que já existia foi cadastrada só com nome: ela vira ARQUIVO,
    # o modo que grava o cupom num .txt e não depende de hardware nenhum.
    op.execute("UPDATE impressoras SET tipo_conexao = 'ARQUIVO' WHERE tipo_conexao IS NULL")
    op.execute(f"UPDATE impressoras SET colunas = {COLUNAS_PADRAO} WHERE colunas IS NULL")
    op.execute("UPDATE impressoras SET ativa = 1 WHERE ativa IS NULL")
    op.execute("UPDATE impressoras SET padrao = 0 WHERE padrao IS NULL")
    # Elege a mais antiga como padrão. `criar_impressora` só faz isso quando uma
    # impressora NOVA é cadastrada — quem já rodava a Fase 3 com a 'Cozinha'
    # cadastrada sairia daqui com zero padrão, e aí o recibo do cliente e o
    # fechamento de caixa parariam de sair em silêncio, além de todo item de
    # categoria sem impressora virar aviso órfão. Em banco vazio o WHERE é no-op.
    op.execute("UPDATE impressoras SET padrao = 1 WHERE id = (SELECT MIN(id) FROM impressoras)")

    # Sem a UNIQUE o banco pode ter dois nomes iguais, e aí a migration morreria
    # no meio deixando o app sem subir. Renomear a duplicata (a mais nova) é
    # feio, mas mantém o food truck aberto — o gerente arruma o nome na tela.
    op.execute(
        "UPDATE impressoras SET nome = nome || ' (' || id || ')' "
        "WHERE id NOT IN (SELECT MIN(id) FROM impressoras GROUP BY nome)"
    )

    with op.batch_alter_table("impressoras", schema=None) as batch_op:
        batch_op.alter_column("tipo_conexao", existing_type=TIPO_CONEXAO, nullable=False)
        batch_op.alter_column("colunas", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("ativa", existing_type=sa.Boolean(), nullable=False)
        batch_op.alter_column("padrao", existing_type=sa.Boolean(), nullable=False)
        batch_op.create_unique_constraint(UQ_IMPRESSORAS_NOME, ["nome"])

    with op.batch_alter_table("itens_comanda", schema=None) as batch_op:
        # Nasce NULL em todo item antigo, e NULL é justamente o que a via de
        # acréscimo considera "ainda não foi pra cozinha". Ou seja: uma comanda
        # que atravessar a atualização ABERTA vai imprimir tudo de novo no
        # próximo clique. É aceitável e até correto — antes da Fase 4 nenhum
        # item havia sido impresso de verdade (o Java só logava). Comanda já
        # fechada não imprime mais nada, então não há efeito nas vendas antigas.
        batch_op.add_column(sa.Column("impresso_em", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("itens_comanda", schema=None) as batch_op:
        batch_op.drop_column("impresso_em")

    with op.batch_alter_table("impressoras", schema=None) as batch_op:
        batch_op.drop_constraint(UQ_IMPRESSORAS_NOME, type_="unique")
        batch_op.drop_column("padrao")
        batch_op.drop_column("ativa")
        batch_op.drop_column("colunas")
        batch_op.drop_column("caminho_arquivo")
        batch_op.drop_column("nome_fila")
        batch_op.drop_column("porta_rede")
        batch_op.drop_column("host")
        batch_op.drop_column("baudrate")
        batch_op.drop_column("porta_serial")
        batch_op.drop_column("product_id")
        batch_op.drop_column("vendor_id")
        batch_op.drop_column("tipo_conexao")
