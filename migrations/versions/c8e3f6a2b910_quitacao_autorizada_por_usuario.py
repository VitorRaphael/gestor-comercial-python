"""quitacao_consumo.autorizado_por_id aponta para usuarios, não para funcionarios

Revision ID: c8e3f6a2b910
Revises: a1b2c3d4e5f6
Create Date: 2026-09-06 00:00:00.000000

Conserta o último desvio de schema entre o banco MIGRADO (o do food truck) e o
que o `domain/` declara. `QuitacaoConsumo.autorizado_por_id` é declarado como
`ForeignKey("usuarios.id")` e o service grava ali o `id` do **gerente logado**
(`pagamento_service.quitar_consumo`), que é um `Usuario`. No banco migrado, a
FK anônima herdada do schema inicial continuava apontando para `funcionarios`.

A migration `d23a4f888a77` conhecia essa anomalia e a deixou registrada como
aceitável, com uma justificativa explícita:

> "os valores nela são válidos (...) e o app nunca liga `PRAGMA foreign_keys`
> — não há enforcement para corrigir, e recriar essa FK exigiria reconstruir a
> tabela inteira só por cosmética de metadado."

**Essa premissa deixou de valer na Fase 1 desta remasterização** (2026-09-06),
que passou a ligar `PRAGMA foreign_keys=ON` em toda conexão (§3.5). Deixou de
ser cosmética e virou defeito de produção, com duas caras — as duas
reproduzidas num banco migrado antes desta migration existir:

- **Quebra.** Gerente com `usuarios.id` maior que o maior `funcionarios.id`
  (o caso comum: a loja tem mais logins de turno do que garçons cadastrados)
  → dar baixa em consumo interno estoura
  `IntegrityError: FOREIGN KEY constraint failed`.
- **Corrompe em silêncio.** Quando o id existe dos dois lados por
  coincidência, a linha grava apontando para o funcionário errado: o código
  quis dizer o `Usuario` 2, o banco lê o `Funcionario` 2.

E nada disso aparecia na suíte: os testes montam o schema com
`Base.metadata.create_all`, que segue o `domain/` e já criava a FK certa. Só o
banco que veio pelas migrations — exatamente o da máquina do food truck —
tinha a FK errada.

O SQLite não altera constraint no lugar, então a tabela é reconstruída
(`batch_alter_table` com `copy_from`), o que também é a oportunidade de **dar
nome às duas FKs** — as anônimas do schema inicial eram justamente o que
impedia consertar isso sem reconstruir. Os dados são copiados como estão: são
válidos contra `usuarios` desde `d23a4f888a77`, que esvaziou a tabela.

Ver `REMASTERIZACAO-V1.md` §3.5 e §8.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8e3f6a2b910'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_FUNCIONARIO = "fk_quitacoes_consumo_funcionario_id_funcionarios"
FK_AUTORIZADO_USUARIOS = "fk_quitacoes_consumo_autorizado_por_id_usuarios"
FK_AUTORIZADO_FUNCIONARIOS = "fk_quitacoes_consumo_autorizado_por_id_funcionarios"


def _tabela(destino_autorizado_por: str, nome_fk_autorizado: str) -> sa.Table:
    """A tabela como ela deve ficar — `copy_from` do batch, que no SQLite é o
    que descreve a estrutura a reconstruir (o `upgrade` aponta
    `autorizado_por_id` para `usuarios`; o `downgrade`, de volta para
    `funcionarios`)."""
    return sa.Table(
        "quitacoes_consumo",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("valor_quitado", sa.Numeric(10, 2), nullable=False),
        sa.Column("quitado_em", sa.DateTime(), nullable=False),
        sa.Column("funcionario_id", sa.Integer(), nullable=False),
        sa.Column("autorizado_por_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["funcionario_id"], ["funcionarios.id"], name=FK_FUNCIONARIO),
        sa.ForeignKeyConstraint(
            ["autorizado_por_id"], [f"{destino_autorizado_por}.id"], name=nome_fk_autorizado
        ),
    )


def _reconstruir(destino: str, nome_fk: str) -> None:
    # `PRAGMA foreign_keys` desligado durante a reconstrução: o SQLite renomeia
    # a tabela nova por cima da antiga, e com a checagem ligada esse passo
    # intermediário pode ser recusado. Religado ao fim para o resto da sessão
    # do Alembic seguir sob a mesma regra da produção.
    op.execute("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table(
        "quitacoes_consumo",
        schema=None,
        recreate="always",
        copy_from=_tabela(destino, nome_fk),
    ):
        pass
    op.execute("PRAGMA foreign_keys=ON")


def upgrade() -> None:
    _reconstruir("usuarios", FK_AUTORIZADO_USUARIOS)


def downgrade() -> None:
    _reconstruir("funcionarios", FK_AUTORIZADO_FUNCIONARIOS)
