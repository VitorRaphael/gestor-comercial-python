"""renomeia "Gerente" para os operadores reais de turno do caixa

Revision ID: d3f8a1c4e6b9
Revises: e7c1f4a9b2d3
Create Date: 2026-09-05 00:00:00.000001

Até aqui o primeiro boot criava um único `Usuario` genérico chamado
"Gerente" (`repository/seed.py`), usado no dia a dia como quem de fato abre/
fecha o caixa do food truck. Isso fazia relatórios, o card "Fechamento da
Gaveta" e o histórico de comandas mostrarem "Gerente" em vez do operador real
do turno (§ pedido do Vitor, 2026-09-05).

O que esta migração faz, só em instalações que já tinham esse bootstrap
antigo (uma instalação nova nunca chega a ter "Gerente" — o `seed.py` já
sai criando os dois operadores de turno direto):

1. Adiciona `funcionarios.turno_horario` (nullable) — exibição do
   turno/horário na tela Funcionários, sem equivalente em `Usuario`.
2. Renomeia o `Usuario` "Gerente" para "Caixa Turno - Noite", mantendo o
   mesmo id/PIN/perfil GERENTE. Como `caixas.aberto_por_id/fechado_por_id`,
   `comandas.usuario_id/cancelado_por_id` e `movimentos_caixa.usuario_id`
   são todos FK para `usuarios.id` (nunca guardam o nome como texto), o
   histórico inteiro passa a exibir "Caixa Turno - Noite" automaticamente
   via join, sem precisar tocar em nenhuma dessas tabelas.
3. Cria o `Usuario` "Caixa Turno - Manhã" (perfil GERENTE, PIN bootstrap
   "081600" — igual ao que `seed.py` usaria numa instalação nova), pra quem
   abre o turno da manhã também logar com identidade própria a partir de
   agora.

O cadastro dos dois `Funcionario` correspondentes (exibidos na tela
Funcionários) não é feito aqui: fica a cargo de `seed.seed_funcionarios_
turno()`, chamado no boot logo após as migrações, que é idempotente por
nome e cobre tanto o caso "acabou de migrar" quanto instalação nova.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import base64
import hashlib
import os


revision: str = 'd3f8a1c4e6b9'
down_revision: Union[str, Sequence[str], None] = 'e7c1f4a9b2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOME_GERENTE_ANTIGO = "Gerente"
NOME_CAIXA_MANHA = "Caixa Turno - Manhã"
NOME_CAIXA_NOITE = "Caixa Turno - Noite"
PIN_CAIXA_MANHA_PADRAO = "081600"


def _gerar_salt() -> str:
    return base64.b64encode(os.urandom(16)).decode()


def _hash_pin(pin: str, salt: str) -> str:
    salt_bytes = base64.b64decode(salt)
    digest = hashlib.sha256(salt_bytes + pin.encode()).digest()
    return base64.b64encode(digest).decode()


def upgrade() -> None:
    with op.batch_alter_table("funcionarios", schema=None) as batch_op:
        batch_op.add_column(sa.Column("turno_horario", sa.String(length=60), nullable=True))

    conn = op.get_bind()
    gerente = conn.execute(
        sa.text("SELECT id FROM usuarios WHERE nome = :nome"),
        {"nome": NOME_GERENTE_ANTIGO},
    ).first()
    if gerente is None:
        # Instalação nova: nunca teve o "Gerente" genérico, seed.py já
        # cria os dois operadores de turno do zero.
        return

    conn.execute(
        sa.text("UPDATE usuarios SET nome = :novo_nome WHERE id = :id"),
        {"novo_nome": NOME_CAIXA_NOITE, "id": gerente.id},
    )

    salt = _gerar_salt()
    conn.execute(
        sa.text(
            """
            INSERT INTO usuarios (nome, pin_hash, salt, perfil, ativo)
            VALUES (:nome, :pin_hash, :salt, 'GERENTE', 1)
            """
        ),
        {
            "nome": NOME_CAIXA_MANHA,
            "pin_hash": _hash_pin(PIN_CAIXA_MANHA_PADRAO, salt),
            "salt": salt,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM usuarios WHERE nome = :nome"),
        {"nome": NOME_CAIXA_MANHA},
    )
    conn.execute(
        sa.text("UPDATE usuarios SET nome = :antigo WHERE nome = :novo"),
        {"antigo": NOME_GERENTE_ANTIGO, "novo": NOME_CAIXA_NOITE},
    )

    with op.batch_alter_table("funcionarios", schema=None) as batch_op:
        batch_op.drop_column("turno_horario")
