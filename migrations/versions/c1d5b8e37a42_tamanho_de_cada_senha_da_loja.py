"""tamanho de cada senha da loja

Revision ID: c1d5b8e37a42
Revises: a7f3c2e5d918
Create Date: 2026-09-08 00:00:00.000000

O teclado de PIN (`ui/widgets/pin_pad_dialog.py`) precisa desenhar a fileira de
marcadores do tamanho da senha ANTES de o operador digitar o primeiro dígito, e
o hash não devolve isso: SHA-256 é via de mão única, e do hash não sai nem o
valor nem o comprimento. Sem o campo, a tela mostrava um piso fixo de seis
bolinhas — errado para a Senha Operacional, que de fábrica tem oito.

Três colunas novas em `loja_config`, uma por nível da cascata (§3.13). Guardam
o COMPRIMENTO, nunca o valor.

## Por que o backfill confere o hash em vez de chutar

Chutar o tamanho da senha de fábrica (6 para a Master, 8 para as outras duas)
acertaria em toda instalação nova e mentiria em qualquer banco onde a senha já
tivesse sido trocada — e uma bolinha a mais na tela é exatamente o defeito que
esta migração existe para corrigir.

Como o salt está no banco e o algoritmo é conhecido, dá para saber com certeza
se cada senha AINDA é a de fábrica: basta refazer o hash do padrão com o salt
gravado e comparar. Bateu, o tamanho é o do padrão; não bateu, a senha foi
trocada em algum momento, o comprimento é desconhecido e a coluna fica `NULL` —
a tela cai no piso padrão até a próxima troca, que grava o valor certo.

O hash é reimplementado aqui em três linhas, em vez de importar
`AuthService.hash_pin`: migração aplicada meses depois não pode depender de o
código do app ainda ter aquela função com aquele comportamento.
"""
import base64
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1d5b8e37a42'
down_revision: Union[str, Sequence[str], None] = 'a7f3c2e5d918'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cópia congelada de `loja_config_service`, deliberada: o padrão de fábrica de
# hoje é o que este banco pode ter, e mudar a constante lá não pode reescrever
# o passado daqui.
PADRAO_POR_NIVEL = {
    "master": "050727",
    "operacional": "26407200",
    "login": "26407200",
}


def _hash(pin: str, salt: str) -> str:
    """SHA-256(salt + pin) em Base64 — mesmo esquema de `AuthService.hash_pin`."""
    digest = hashlib.sha256(base64.b64decode(salt) + pin.encode()).digest()
    return base64.b64encode(digest).decode()


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("loja_config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("senha_master_tamanho", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("senha_operacional_tamanho", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("senha_login_tamanho", sa.Integer(), nullable=True))

    conexao = op.get_bind()
    linhas = conexao.execute(
        sa.text(
            "SELECT id, senha_master_salt, senha_master_hash, "
            "senha_operacional_salt, senha_operacional_hash, "
            "senha_login_salt, senha_login_hash FROM loja_config"
        )
    ).mappings().all()

    for linha in linhas:
        tamanhos = {}
        for nivel, padrao in PADRAO_POR_NIVEL.items():
            salt = linha[f"senha_{nivel}_salt"]
            guardado = linha[f"senha_{nivel}_hash"]
            try:
                ainda_de_fabrica = salt and _hash(padrao, salt) == guardado
            except Exception:
                # Salt corrompido: não dá para afirmar nada sobre esta senha.
                ainda_de_fabrica = False
            tamanhos[nivel] = len(padrao) if ainda_de_fabrica else None

        conexao.execute(
            sa.text(
                "UPDATE loja_config SET senha_master_tamanho = :master, "
                "senha_operacional_tamanho = :operacional, "
                "senha_login_tamanho = :login WHERE id = :id"
            ),
            {"id": linha["id"], **tamanhos},
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Simétrico: as três colunas só guardam um número derivado da senha, então
    # dropá-las não perde nada que não possa ser reconstruído na próxima troca.
    with op.batch_alter_table("loja_config", schema=None) as batch_op:
        batch_op.drop_column("senha_login_tamanho")
        batch_op.drop_column("senha_operacional_tamanho")
        batch_op.drop_column("senha_master_tamanho")
