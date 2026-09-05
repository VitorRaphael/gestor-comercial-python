"""garante PIN de login ativo para todo Funcionario com cargo Caixa

Revision ID: f4b2c8e1a7d5
Revises: d3f8a1c4e6b9
Create Date: 2026-09-12 00:00:00.000000

Bug relatado pelo Vitor: "Caixa Turno - Manhã" não conseguia logar com a
Senha Operacional padrão (26407200). Causa: a migração anterior
(d3f8a1c4e6b9) já criava o `Usuario` "Caixa Turno - Manhã" com um PIN
bootstrap diferente (081600), e uma instalação que rodou só até ali (ou que
teve o Funcionario "Caixa Turno - Manhã" cadastrado manualmente pela tela,
sem o `Usuario` de login correspondente) nunca ficou com 26407200 de fato.

O que esta migração faz, para toda instalação (nova ou antiga):
1. Garante que "Caixa Turno - Manhã" e "Caixa Turno - Noite" têm `Usuario`
   de login com PIN 26407200 (cria se não existir, redefine se existir com
   outro PIN) — mesmo valor de `LojaConfigService.SENHA_OPERACIONAL_PADRAO`,
   por decisão do Vitor (2026-09-12) de que os dois turnos compartilham essa
   senha em vez de PIN individual.
2. Generaliza pra qualquer outro `Funcionario` com `cargo = 'Caixa'` e
   `ativo = 1` que ainda não tenha um `Usuario` de login com o mesmo nome:
   cria um com PIN 26407200 e perfil GERENTE (mesmo perfil dos dois turnos
   — abrir/fechar caixa exige perfil gerencial em `AuthService.
   exigir_gerente`, decisão já tomada em d3f8a1c4e6b9de não mudar o modelo
   de permissão nesta rodada).

Não mexe em quem JÁ tem PIN funcionando: só cria o que falta e realinha o
PIN dos dois operadores nomeados que o bug afetou.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import base64
import hashlib
import os


revision: str = 'f4b2c8e1a7d5'
down_revision: Union[str, Sequence[str], None] = 'd3f8a1c4e6b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOME_CAIXA_MANHA = "Caixa Turno - Manhã"
NOME_CAIXA_NOITE = "Caixa Turno - Noite"
PIN_CAIXA_PADRAO = "26407200"


def _gerar_salt() -> str:
    return base64.b64encode(os.urandom(16)).decode()


def _hash_pin(pin: str, salt: str) -> str:
    salt_bytes = base64.b64decode(salt)
    digest = hashlib.sha256(salt_bytes + pin.encode()).digest()
    return base64.b64encode(digest).decode()


def _upsert_usuario(conn, nome: str) -> None:
    existente = conn.execute(
        sa.text("SELECT id FROM usuarios WHERE nome = :nome"), {"nome": nome}
    ).first()
    salt = _gerar_salt()
    pin_hash = _hash_pin(PIN_CAIXA_PADRAO, salt)
    if existente is None:
        conn.execute(
            sa.text(
                """
                INSERT INTO usuarios (nome, pin_hash, salt, perfil, ativo)
                VALUES (:nome, :pin_hash, :salt, 'GERENTE', 1)
                """
            ),
            {"nome": nome, "pin_hash": pin_hash, "salt": salt},
        )
    else:
        conn.execute(
            sa.text(
                "UPDATE usuarios SET pin_hash = :pin_hash, salt = :salt, ativo = 1 WHERE id = :id"
            ),
            {"pin_hash": pin_hash, "salt": salt, "id": existente.id},
        )


def upgrade() -> None:
    conn = op.get_bind()

    _upsert_usuario(conn, NOME_CAIXA_MANHA)
    _upsert_usuario(conn, NOME_CAIXA_NOITE)

    outros_caixas = conn.execute(
        sa.text(
            "SELECT nome FROM funcionarios WHERE cargo = 'Caixa' AND ativo = 1 "
            "AND nome NOT IN (:manha, :noite)"
        ),
        {"manha": NOME_CAIXA_MANHA, "noite": NOME_CAIXA_NOITE},
    ).all()
    for linha in outros_caixas:
        existente = conn.execute(
            sa.text("SELECT id FROM usuarios WHERE nome = :nome"), {"nome": linha.nome}
        ).first()
        if existente is None:
            _upsert_usuario(conn, linha.nome)


def downgrade() -> None:
    # Não há como "desfazer" com segurança: reverter apagaria PINs que podem
    # já ter sido trocados manualmente pelo Vitor depois desta migração.
    # Aceito como migração de dados sem downgrade real (mesmo padrão de
    # `LojaConfigService.obter_ou_criar`, sem migração reversível de bootstrap).
    pass
