"""unifica cascata de 3 níveis de PIN (Senha de Login, Operacional, Master)

Revision ID: 490c75504570
Revises: f4b2c8e1a7d5
Create Date: 2026-09-05 00:00:00.000000

Unificação de dois sistemas de PIN paralelos que existiam (§3.13, decisão do
Vitor de 2026-09-05): o PIN pessoal por `Usuario` (usado hoje no login) e os
segredos operacionais de `LojaConfig` (Senha Operacional/Gerente, Senha
Master/Dono). A partir desta migração há uma cascata única de 3 níveis, toda
em `LojaConfig`:
- Nível 1 — Senha de Login: desbloqueia o terminal na tela de login (para
  qualquer operador do dropdown), mapa de mesas e abertura de comandas.
  Coluna nova `senha_login_hash`/`senha_login_salt`, padrão "26407200" —
  mesmo valor que já era o PIN de login dos dois turnos de Caixa (ver
  migração `f4b2c8e1a7d5`), então nenhuma instalação existente perde acesso.
- Nível 2 — Senha Operacional (Caixa): já existia, sem mudança de valor.
- Nível 3 — Senha Master (Dono): já existia, sem mudança de valor.

Cascata: quem digita a Senha Master autentica também onde a Operacional ou a
de Login é pedida; quem digita a Operacional autentica também onde a de
Login é pedida (ver `AuthService.validar_pin_nivel`).

O que esta migração faz:
1. Adiciona `loja_config.senha_login_hash`/`senha_login_salt` (backfill com
   o PIN padrão "26407200", hash gerado aqui com salt novo — não reaproveita
   nenhum salt existente).
2. Remove `usuarios.pin_hash`/`usuarios.salt`: PIN pessoal por usuário deixa
   de existir. `Usuario` continua só para identificar QUEM está logando
   (nome, perfil, ativo) — a validação do PIN em si passa a ser sempre
   contra a cascata de `loja_config`, nunca mais contra um hash gravado no
   próprio usuário. Destrutiva e sem downgrade de dado (os hashes antigos
   não têm como voltar — mesma decisão já tomada em migrações anteriores de
   bootstrap/dado, ex.: `f4b2c8e1a7d5`), mas o downgrade recria as colunas
   (nullable, sem valor) para manter o schema reversível.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import base64
import hashlib
import os


revision: str = '490c75504570'
down_revision: Union[str, Sequence[str], None] = 'f4b2c8e1a7d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SENHA_LOGIN_PADRAO = "26407200"


def _gerar_salt() -> str:
    return base64.b64encode(os.urandom(16)).decode()


def _hash_pin(pin: str, salt: str) -> str:
    salt_bytes = base64.b64decode(salt)
    digest = hashlib.sha256(salt_bytes + pin.encode()).digest()
    return base64.b64encode(digest).decode()


def upgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table("loja_config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("senha_login_hash", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("senha_login_salt", sa.String(length=64), nullable=True))

    salt = _gerar_salt()
    pin_hash = _hash_pin(SENHA_LOGIN_PADRAO, salt)
    conn.execute(
        sa.text("UPDATE loja_config SET senha_login_hash = :hash, senha_login_salt = :salt"),
        {"hash": pin_hash, "salt": salt},
    )

    with op.batch_alter_table("loja_config", schema=None) as batch_op:
        batch_op.alter_column("senha_login_hash", existing_type=sa.String(length=128), nullable=False)
        batch_op.alter_column("senha_login_salt", existing_type=sa.String(length=64), nullable=False)

    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_column("pin_hash")
        batch_op.drop_column("salt")


def downgrade() -> None:
    # Sem volta pro PIN pessoal (os hashes antigos não foram guardados em
    # nenhum lugar) — recria as colunas nullable só pra destravar o schema,
    # mesmo padrão já aceito em `d23a4f888a77`/`f4b2c8e1a7d5`.
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.add_column(sa.Column("salt", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("pin_hash", sa.String(length=128), nullable=True))

    with op.batch_alter_table("loja_config", schema=None) as batch_op:
        batch_op.drop_column("senha_login_salt")
        batch_op.drop_column("senha_login_hash")
