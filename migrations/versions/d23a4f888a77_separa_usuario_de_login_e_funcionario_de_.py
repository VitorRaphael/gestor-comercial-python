"""separa Usuario (login) de Funcionario (atendimento, sem login)

Revision ID: d23a4f888a77
Revises: 625114038889
Create Date: 2026-08-28 00:00:00.000000

Até aqui `funcionarios` misturava quem loga no sistema (PIN, perfil,
`exigir_gerente`) com quem atende a mesa/comanda. Isso fazia qualquer
ATENDENTE aparecer na tela de login, quando login deveria ser só de quem de
fato opera caixa/sistema (§3.1 vs §3.11 revisados).

O que esta migração faz:
1. Cria `usuarios` (login) e copia todo mundo de `funcionarios` pra lá,
   mapeando o perfil antigo ATENDENTE -> OPERADOR_CAIXA (continuam logando
   como estavam) e GERENTE -> GERENTE. Os ids são preservados na cópia.
2. Repõe `comandas.funcionario_id`/`movimentos_caixa.funcionario_id` como
   `usuario_id` (NOT NULL, é sempre quem estava logado) e adiciona
   `comandas.atendente_id` (nullable, novo — vínculo manual de "quem atendeu"
   com a nova `Funcionario`, escolhido na tela, ver `ComandaService.
   definir_atendente`).
3. Repõe as FKs nomeadas de ação administrativa (`comandas.cancelado_por_id`,
   `itens_comanda.cancelado_por_id`, `caixas.aberto_por_id`,
   `caixas.fechado_por_id`) para apontar pra `usuarios` em vez de
   `funcionarios` — são sempre gerente logado.
4. Esvazia `funcionarios` (todo mundo virou `usuario`) e recria a tabela sem
   `pin_hash`/`salt`/`perfil`, com `cargo`/`telefone` novos. `saldo_devedor`
   é mantido, mas como não há mais nenhum `Funcionario` cadastrado depois do
   esvaziamento, a dívida de consumo interno antiga (`pagamentos.
   funcionario_consumo_id`, `quitacoes_consumo`) perde o dono: pagamentos
   viram NULL (campo já era nullable) e quitações antigas são apagadas (só
   faziam sentido presas a um devedor que não existe mais). Essa perda é uma
   decisão de produto aceita (Vitor, 2026-08-28): ninguém tinha consumo
   interno em aberto que precisasse sobreviver à reestruturação — o modelo
   de "quem deve" muda de dono a partir daqui.

`quitacoes_consumo.autorizado_por_id` continua com FK anônima apontando
"funcionarios" no metadata do SQLite (nunca foi nomeada na migração
original), mas os valores nela são válidos (ids preservados na cópia pra
`usuarios`) e o app nunca liga `PRAGMA foreign_keys` — não há enforcement
para corrigir, e recriar essa FK exigiria reconstruir a tabela inteira só
por cosmética de metadado. Documentado aqui em vez de "corrigido".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd23a4f888a77'
down_revision: Union[str, Sequence[str], None] = '625114038889'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_COMANDAS_CANCELADO_POR_OLD = "fk_comandas_cancelado_por_id_funcionarios"
FK_COMANDAS_CANCELADO_POR_NEW = "fk_comandas_cancelado_por_id_usuarios"
FK_ITENS_CANCELADO_POR_OLD = "fk_itens_comanda_cancelado_por_id_funcionarios"
FK_ITENS_CANCELADO_POR_NEW = "fk_itens_comanda_cancelado_por_id_usuarios"
FK_CAIXAS_ABERTO_POR_OLD = "fk_caixas_aberto_por_id_funcionarios"
FK_CAIXAS_ABERTO_POR_NEW = "fk_caixas_aberto_por_id_usuarios"
FK_CAIXAS_FECHADO_POR_OLD = "fk_caixas_fechado_por_id_funcionarios"
FK_CAIXAS_FECHADO_POR_NEW = "fk_caixas_fechado_por_id_usuarios"
FK_COMANDAS_USUARIO = "fk_comandas_usuario_id_usuarios"
FK_COMANDAS_ATENDENTE = "fk_comandas_atendente_id_funcionarios"
FK_MOVIMENTOS_USUARIO = "fk_movimentos_caixa_usuario_id_usuarios"

_PERFIL_USUARIO_ENUM = sa.Enum(
    "ADMIN", "GERENTE", "OPERADOR_CAIXA", name="perfilusuario"
)


def upgrade() -> None:
    """Upgrade schema."""
    # ------------------------------------------------------------------
    # 1) usuarios: cria e copia de funcionarios (ATENDENTE -> OPERADOR_CAIXA)
    # ------------------------------------------------------------------
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("pin_hash", sa.String(length=128), nullable=False),
        sa.Column("salt", sa.String(length=64), nullable=False),
        sa.Column("perfil", _PERFIL_USUARIO_ENUM, nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        INSERT INTO usuarios (id, nome, pin_hash, salt, perfil, ativo)
        SELECT
            id,
            nome,
            pin_hash,
            salt,
            CASE perfil WHEN 'ATENDENTE' THEN 'OPERADOR_CAIXA' ELSE perfil END,
            ativo
        FROM funcionarios
        """
    )

    # ------------------------------------------------------------------
    # 2) comandas / movimentos_caixa: funcionario_id -> usuario_id
    #    (+ comandas.atendente_id novo, opcional, para a nova Funcionario)
    # ------------------------------------------------------------------
    with op.batch_alter_table("comandas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("usuario_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("atendente_id", sa.Integer(), nullable=True))

    op.execute("UPDATE comandas SET usuario_id = funcionario_id")

    with op.batch_alter_table("comandas", schema=None) as batch_op:
        batch_op.alter_column("usuario_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(FK_COMANDAS_USUARIO, "usuarios", ["usuario_id"], ["id"])
        batch_op.create_foreign_key(
            FK_COMANDAS_ATENDENTE, "funcionarios", ["atendente_id"], ["id"]
        )
        batch_op.drop_constraint(FK_COMANDAS_CANCELADO_POR_OLD, type_="foreignkey")
        batch_op.create_foreign_key(
            FK_COMANDAS_CANCELADO_POR_NEW, "usuarios", ["cancelado_por_id"], ["id"]
        )
        batch_op.drop_column("funcionario_id")

    with op.batch_alter_table("movimentos_caixa", schema=None) as batch_op:
        batch_op.add_column(sa.Column("usuario_id", sa.Integer(), nullable=True))

    op.execute("UPDATE movimentos_caixa SET usuario_id = funcionario_id")

    with op.batch_alter_table("movimentos_caixa", schema=None) as batch_op:
        batch_op.alter_column("usuario_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(FK_MOVIMENTOS_USUARIO, "usuarios", ["usuario_id"], ["id"])
        batch_op.drop_column("funcionario_id")

    # ------------------------------------------------------------------
    # 3) itens_comanda.cancelado_por_id / caixas.aberto_por_id/fechado_por_id
    #    repontam pra usuarios (ação administrativa, sempre gerente logado)
    # ------------------------------------------------------------------
    with op.batch_alter_table("itens_comanda", schema=None) as batch_op:
        batch_op.drop_constraint(FK_ITENS_CANCELADO_POR_OLD, type_="foreignkey")
        batch_op.create_foreign_key(
            FK_ITENS_CANCELADO_POR_NEW, "usuarios", ["cancelado_por_id"], ["id"]
        )

    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.drop_constraint(FK_CAIXAS_ABERTO_POR_OLD, type_="foreignkey")
        batch_op.drop_constraint(FK_CAIXAS_FECHADO_POR_OLD, type_="foreignkey")
        batch_op.create_foreign_key(
            FK_CAIXAS_ABERTO_POR_NEW, "usuarios", ["aberto_por_id"], ["id"]
        )
        batch_op.create_foreign_key(
            FK_CAIXAS_FECHADO_POR_NEW, "usuarios", ["fechado_por_id"], ["id"]
        )

    # ------------------------------------------------------------------
    # 4) funcionarios: esvazia (todo mundo virou usuario) e recria sem
    #    pin_hash/salt/perfil, com cargo/telefone
    # ------------------------------------------------------------------
    op.execute("UPDATE pagamentos SET funcionario_consumo_id = NULL WHERE funcionario_consumo_id IS NOT NULL")
    op.execute("DELETE FROM quitacoes_consumo")
    op.execute("DELETE FROM funcionarios")

    with op.batch_alter_table("funcionarios", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cargo", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("telefone", sa.String(length=30), nullable=True))
        batch_op.drop_column("perfil")
        batch_op.drop_column("pin_hash")
        batch_op.drop_column("salt")


def downgrade() -> None:
    """Downgrade schema."""
    # A dívida de consumo interno apagada no passo 4 do upgrade não volta —
    # perda aceita (ver docstring). Os cadastros de usuários (login) voltam
    # pra funcionarios, remapeando OPERADOR_CAIXA -> ATENDENTE e ADMIN ->
    # GERENTE (perfil ADMIN não existia antes; rebaixar a GERENTE é o mais
    # próximo do que a versão antiga suportava).
    op.execute("DELETE FROM funcionarios")

    with op.batch_alter_table("funcionarios", schema=None) as batch_op:
        batch_op.add_column(sa.Column("salt", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("pin_hash", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column(
                "perfil",
                sa.Enum("ATENDENTE", "GERENTE", name="perfilfuncionario"),
                nullable=True,
            )
        )
        batch_op.drop_column("telefone")
        batch_op.drop_column("cargo")

    op.execute(
        """
        INSERT INTO funcionarios (id, nome, pin_hash, salt, perfil, ativo, saldo_devedor)
        SELECT
            id,
            nome,
            pin_hash,
            salt,
            CASE perfil WHEN 'OPERADOR_CAIXA' THEN 'ATENDENTE' ELSE 'GERENTE' END,
            ativo,
            0
        FROM usuarios
        """
    )

    with op.batch_alter_table("caixas", schema=None) as batch_op:
        batch_op.drop_constraint(FK_CAIXAS_FECHADO_POR_NEW, type_="foreignkey")
        batch_op.drop_constraint(FK_CAIXAS_ABERTO_POR_NEW, type_="foreignkey")
        batch_op.create_foreign_key(
            FK_CAIXAS_ABERTO_POR_OLD, "funcionarios", ["aberto_por_id"], ["id"]
        )
        batch_op.create_foreign_key(
            FK_CAIXAS_FECHADO_POR_OLD, "funcionarios", ["fechado_por_id"], ["id"]
        )

    with op.batch_alter_table("itens_comanda", schema=None) as batch_op:
        batch_op.drop_constraint(FK_ITENS_CANCELADO_POR_NEW, type_="foreignkey")
        batch_op.create_foreign_key(
            FK_ITENS_CANCELADO_POR_OLD, "funcionarios", ["cancelado_por_id"], ["id"]
        )

    with op.batch_alter_table("movimentos_caixa", schema=None) as batch_op:
        batch_op.add_column(sa.Column("funcionario_id", sa.Integer(), nullable=True))
    op.execute("UPDATE movimentos_caixa SET funcionario_id = usuario_id")
    with op.batch_alter_table("movimentos_caixa", schema=None) as batch_op:
        batch_op.alter_column("funcionario_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint(FK_MOVIMENTOS_USUARIO, type_="foreignkey")
        batch_op.drop_column("usuario_id")

    with op.batch_alter_table("comandas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("funcionario_id", sa.Integer(), nullable=True))
    op.execute("UPDATE comandas SET funcionario_id = usuario_id")
    with op.batch_alter_table("comandas", schema=None) as batch_op:
        batch_op.alter_column("funcionario_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint(FK_COMANDAS_CANCELADO_POR_NEW, type_="foreignkey")
        batch_op.create_foreign_key(
            FK_COMANDAS_CANCELADO_POR_OLD, "funcionarios", ["cancelado_por_id"], ["id"]
        )
        batch_op.drop_constraint(FK_COMANDAS_ATENDENTE, type_="foreignkey")
        batch_op.drop_constraint(FK_COMANDAS_USUARIO, type_="foreignkey")
        batch_op.drop_column("atendente_id")
        batch_op.drop_column("usuario_id")

    op.drop_table("usuarios")
