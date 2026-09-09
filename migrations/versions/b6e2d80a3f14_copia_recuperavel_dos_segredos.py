"""copia recuperavel dos segredos, para o botao de olho

Revision ID: b6e2d80a3f14
Revises: a4c9f1d70b52
Create Date: 2026-09-09 00:00:00.000004

A cascata de 3 níveis (§3.13) guardava só hash+salt, e a regra escrita era que
"ver o valor" não existe como operação. O Vitor pediu o contrário: um olho ao
lado de cada linha de "Senhas e Acesso" que, mediante o CPF do Dono, mostra o
valor real. Hash é via de mão única, então uma segunda cópia precisa existir.

Quatro colunas novas em `loja_config`, uma por segredo, guardando o valor
embaralhado por `services/segredo_reversivel.py` — que documenta o que essa
cópia protege (leitura casual do `.db`) e o que **não** protege (quem tem o
arquivo e o programa). A chave fica em `preferencias.chave_de_exibicao`, criada
aqui, porque o backup do projeto é uma cópia do `.db` e uma chave guardada fora
dele tornaria todo backup restaurado ilegível.

**Nada aqui participa de autenticação.** `senha_*_hash` continua sendo a única
coisa contra a qual um PIN digitado é conferido; estas colunas só alimentam a
tela.

## Por que o backfill confere o hash em vez de chutar

Mesma técnica de `c1d5b8e37a42` (que preencheu `senha_*_tamanho`): o salt está
no banco e o algoritmo é conhecido, então dá para saber com CERTEZA se uma
senha ainda é a de fábrica — refaz o hash do padrão com o salt gravado e
compara. Bateu, o valor é conhecido e vira cópia recuperável; não bateu, a
senha foi trocada em algum momento, ninguém sabe qual é, e a coluna fica
`NULL`. A tela então diz "altere-a uma vez para poder visualizá-la", e a
próxima troca grava a cópia sozinha.

Chutar seria pior que não preencher: o olho mostraria "26407200" com ar de
verdade para um dono que trocou a senha meses atrás.

O CPF do Dono não tem padrão de fábrica — não há o que recuperar, e ele fica
`NULL` até o próximo cadastro/alteração.

O hash e a cifra são reimplementados aqui, em vez de importados do app: uma
migração aplicada meses depois não pode depender de aquelas funções ainda
existirem com aquele comportamento.
"""
import base64
import hashlib
import hmac
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b6e2d80a3f14'
down_revision: Union[str, Sequence[str], None] = 'a4c9f1d70b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHAVE_DE_EXIBICAO = "chave_de_exibicao"

# Cópia congelada de `loja_config_service`: o padrão de fábrica de HOJE é o que
# este banco pode ter, e mudar a constante lá não pode reescrever o passado.
PADRAO_POR_NIVEL = {
    "master": "050727",
    "operacional": "26407200",
    "login": "26407200",
}

# Cópia congelada de `services/segredo_reversivel.py` — mesmos rótulos e
# tamanhos, para o que sai daqui ser legível por lá.
_ROTULO_FLUXO = b"fluxo"
_ROTULO_SELO = b"selo"
_NONCE = 16
_SELO = 16


def _hash(pin: str, salt: str) -> str:
    """SHA-256(salt + pin) em Base64 — mesmo esquema de `AuthService.hash_pin`."""
    digest = hashlib.sha256(base64.b64decode(salt) + pin.encode()).digest()
    return base64.b64encode(digest).decode()


def _cifrar(valor: str, chave_b64: str) -> str:
    chave = base64.b64decode(chave_b64)
    nonce = os.urandom(_NONCE)
    claro = valor.encode("utf-8")

    fluxo = bytearray()
    contador = 0
    while len(fluxo) < len(claro):
        fluxo.extend(
            hmac.new(
                chave,
                _ROTULO_FLUXO + nonce + contador.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
        )
        contador += 1

    cifrado = bytes(a ^ b for a, b in zip(claro, bytes(fluxo[: len(claro)])))
    selo = hmac.new(chave, _ROTULO_SELO + nonce + cifrado, hashlib.sha256).digest()[:_SELO]
    return base64.b64encode(nonce + selo + cifrado).decode()


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("loja_config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("senha_master_cifrada", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("senha_operacional_cifrada", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("senha_login_cifrada", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("cpf_dono_cifrado", sa.String(length=255), nullable=True))

    conexao = op.get_bind()
    linhas = conexao.execute(
        sa.text(
            "SELECT id, senha_master_salt, senha_master_hash, "
            "senha_operacional_salt, senha_operacional_hash, "
            "senha_login_salt, senha_login_hash FROM loja_config"
        )
    ).mappings().all()
    if not linhas:
        # Banco sem a linha singleton ainda (ela nasce no primeiro toque em
        # "Senhas e Acesso"): não há o que preencher, e o bootstrap do service
        # já cria as cópias das três senhas de fábrica.
        return

    chave = conexao.execute(
        sa.text("SELECT valor FROM preferencias WHERE chave = :chave"),
        {"chave": CHAVE_DE_EXIBICAO},
    ).scalar()
    if not chave:
        chave = base64.b64encode(os.urandom(32)).decode()
        conexao.execute(
            sa.text("INSERT INTO preferencias (chave, valor) VALUES (:chave, :valor)"),
            {"chave": CHAVE_DE_EXIBICAO, "valor": chave},
        )

    for linha in linhas:
        copias = {}
        for nivel, padrao in PADRAO_POR_NIVEL.items():
            salt = linha[f"senha_{nivel}_salt"]
            guardado = linha[f"senha_{nivel}_hash"]
            try:
                ainda_de_fabrica = bool(salt) and _hash(padrao, salt) == guardado
            except Exception:
                # Salt corrompido: não dá para afirmar nada sobre esta senha.
                ainda_de_fabrica = False
            copias[nivel] = _cifrar(padrao, chave) if ainda_de_fabrica else None

        conexao.execute(
            sa.text(
                "UPDATE loja_config SET senha_master_cifrada = :master, "
                "senha_operacional_cifrada = :operacional, "
                "senha_login_cifrada = :login WHERE id = :id"
            ),
            {"id": linha["id"], **copias},
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Simétrico e sem perda de autenticação: o que sai daqui é a cópia de
    # exibição, nunca o hash. Depois de descer, o olho deixa de existir e o
    # login continua funcionando igual.
    with op.batch_alter_table("loja_config", schema=None) as batch_op:
        batch_op.drop_column("cpf_dono_cifrado")
        batch_op.drop_column("senha_login_cifrada")
        batch_op.drop_column("senha_operacional_cifrada")
        batch_op.drop_column("senha_master_cifrada")
    op.execute(
        sa.text("DELETE FROM preferencias WHERE chave = 'chave_de_exibicao'")
    )
