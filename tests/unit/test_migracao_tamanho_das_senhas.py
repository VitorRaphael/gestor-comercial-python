"""A migração `c1d5b8e37a42` só afirma o tamanho da senha quando tem certeza.

O teclado de PIN desenha a fileira de marcadores do tamanho da senha antes de o
operador digitar, e o hash não devolve isso — SHA-256 é via de mão única. Daí as
três colunas `senha_*_tamanho` em `loja_config`.

O problema é o banco que já existe. Chutar "6 para a Master, 8 para as outras",
que é a senha de fábrica, acertaria em toda instalação nova e **mentiria** em
qualquer banco onde o dono já tivesse trocado a senha — uma bolinha a mais na
tela, que é exatamente o defeito que a coluna existe para corrigir.

Como o salt está no banco e o algoritmo é conhecido, dá para saber com certeza
se a senha ainda é a de fábrica: refaz o hash do padrão com o salt gravado e
compara. Estes testes provam os dois lados dessa decisão num banco só — Master
intocada (tamanho preenchido) ao lado de Operacional trocada (fica `NULL`).
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial

# A revisão imediatamente anterior à que está sendo testada.
REVISAO_ANTERIOR = "a7f3c2e5d918"
REVISAO = "c1d5b8e37a42"

SENHA_MASTER_DE_FABRICA = "050727"
SENHA_LOGIN_DE_FABRICA = "26407200"
SENHA_OPERACIONAL_TROCADA = "9137"


def _hash(pin: str, salt: str) -> str:
    digest = hashlib.sha256(base64.b64decode(salt) + pin.encode()).digest()
    return base64.b64encode(digest).decode()


def _salt() -> str:
    return base64.b64encode(os.urandom(16)).decode()


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco na revisão ANTERIOR à migração, com a linha singleton da loja.

    Master e Login continuam na senha de fábrica; a Operacional foi trocada por
    uma de quatro dígitos — o cenário que o chute erraria.
    """
    from alembic import command
    from alembic.config import Config

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    arquivo = tmp_path / "loja.db"
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))

    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    command.upgrade(config, REVISAO_ANTERIOR)

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    salts = {nivel: _salt() for nivel in ("master", "operacional", "login")}
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO loja_config (id, senha_master_hash, senha_master_salt, "
                "senha_operacional_hash, senha_operacional_salt, senha_login_hash, "
                "senha_login_salt, cpf_dono_definido) VALUES (1, :mh, :ms, :oh, :os, "
                ":lh, :ls, 0)"
            ),
            {
                "mh": _hash(SENHA_MASTER_DE_FABRICA, salts["master"]),
                "ms": salts["master"],
                "oh": _hash(SENHA_OPERACIONAL_TROCADA, salts["operacional"]),
                "os": salts["operacional"],
                "lh": _hash(SENHA_LOGIN_DE_FABRICA, salts["login"]),
                "ls": salts["login"],
            },
        )
    return config, engine


def _tamanhos(engine) -> dict[str, int | None]:
    with engine.connect() as conexao:
        linha = conexao.execute(
            sa.text(
                "SELECT senha_master_tamanho, senha_operacional_tamanho, "
                "senha_login_tamanho FROM loja_config WHERE id = 1"
            )
        ).mappings().one()
    return {
        "master": linha["senha_master_tamanho"],
        "operacional": linha["senha_operacional_tamanho"],
        "login": linha["senha_login_tamanho"],
    }


def test_a_senha_de_fabrica_tem_o_tamanho_preenchido(banco):
    """O caso comum, e o que conserta a tela: instalação que nunca trocou a
    senha passa a saber que a Operacional de fábrica tem oito dígitos."""
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    tamanhos = _tamanhos(engine)
    assert tamanhos["master"] == len(SENHA_MASTER_DE_FABRICA) == 6
    assert tamanhos["login"] == len(SENHA_LOGIN_DE_FABRICA) == 8


def test_a_senha_ja_trocada_fica_desconhecida_em_vez_de_chutada(banco):
    """O caso que o chute estragaria.

    A Operacional deste banco tem quatro dígitos, não os oito de fábrica, e a
    migração não tem como descobrir isso — só como descobrir que **não é** a de
    fábrica. `NULL` é a resposta honesta: a tela cai no piso padrão até a
    próxima troca, e nunca mostra um número inventado.
    """
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert _tamanhos(engine)["operacional"] is None, (
        "a migração afirmou um tamanho para uma senha que ela não consegue conferir"
    )


def test_o_tamanho_certo_entra_sozinho_na_proxima_troca(banco, uow):
    """A outra metade da resposta honesta: `NULL` não é permanente."""
    from alembic import command

    from gestor_comercial.services.loja_config_service import LojaConfigService

    config, engine = banco
    command.upgrade(config, REVISAO)

    servico = LojaConfigService(uow)
    servico.obter_ou_criar()  # banco em memória do `uow`, independente do arquivo
    servico.alterar_senha_operacional(SENHA_MASTER_DE_FABRICA, "1234567")

    assert servico.tamanho_da_senha(2) == 7


def test_upgrade_e_downgrade_ida_e_volta(banco):
    """As três colunas guardam número derivado da senha, então dropá-las não
    perde nada — mas o caminho de volta tem que funcionar de verdade, e é o que
    permite despromover a versão se algo der errado na máquina do balcão."""
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)
    command.downgrade(config, REVISAO_ANTERIOR)

    with engine.connect() as conexao:
        colunas = {c["name"] for c in sa.inspect(conexao.engine).get_columns("loja_config")}
    assert "senha_master_tamanho" not in colunas

    command.upgrade(config, REVISAO)
    assert _tamanhos(engine)["master"] == 6
