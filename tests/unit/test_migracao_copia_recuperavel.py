"""A migração `b6e2d80a3f14` só cria cópia recuperável do que ela CONHECE.

O botão de olho mostra o valor real de um segredo, e hash é via de mão única —
então a cópia precisa ser gravada quando o valor passa pelo app. Num banco que
já existe, os valores nunca passaram: o que a migração tem em mãos é hash+salt.

Ela resolve isso do mesmo jeito que `c1d5b8e37a42` resolveu o comprimento das
senhas: refaz o hash do padrão de fábrica com o salt gravado e compara. Bateu, o
valor é conhecido e vira cópia; não bateu, a senha foi trocada em algum momento,
ninguém sabe qual é, e a coluna fica `NULL`.

Chutar seria pior que não preencher — o olho mostraria "26407200" com ar de
verdade para um dono que trocou a senha meses atrás. Estes testes provam os dois
lados num banco só: Master intocada (cópia criada) ao lado de Operacional
trocada (fica `NULL`).
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial
from gestor_comercial.services.segredo_reversivel import decifrar

REVISAO_ANTERIOR = "a4c9f1d70b52"
REVISAO = "b6e2d80a3f14"

SENHA_MASTER_DE_FABRICA = "050727"
SENHA_LOGIN_DE_FABRICA = "26407200"
SENHA_OPERACIONAL_TROCADA = "9137"


def _hash(pin: str, salt: str) -> str:
    digest = hashlib.sha256(base64.b64decode(salt) + pin.encode()).digest()
    return base64.b64encode(digest).decode()


def _salt() -> str:
    return base64.b64encode(os.urandom(16)).decode()


def _config(arquivo: Path):
    from alembic.config import Config

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    return config


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco na revisão ANTERIOR, com a linha singleton da loja.

    Master e Login continuam na senha de fábrica; a Operacional foi trocada —
    o cenário que um chute erraria.
    """
    from alembic import command

    arquivo = tmp_path / "loja.db"
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))
    command.upgrade(_config(arquivo), REVISAO_ANTERIOR)

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    salts = {nivel: _salt() for nivel in ("master", "operacional", "login")}
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO loja_config ("
                " id, senha_master_hash, senha_master_salt,"
                " senha_operacional_hash, senha_operacional_salt,"
                " senha_login_hash, senha_login_salt, cpf_dono_definido"
                ") VALUES (1, :mh, :ms, :oh, :os, :lh, :ls, 0)"
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
    return arquivo


def _subir(arquivo: Path) -> None:
    from alembic import command

    command.upgrade(_config(arquivo), REVISAO)


def _linha(arquivo: Path):
    engine = sa.create_engine(f"sqlite:///{arquivo}")
    with engine.connect() as conexao:
        config = conexao.execute(
            sa.text(
                "SELECT senha_master_cifrada, senha_operacional_cifrada, "
                "senha_login_cifrada, cpf_dono_cifrado FROM loja_config WHERE id = 1"
            )
        ).mappings().one()
        chave = conexao.execute(
            sa.text("SELECT valor FROM preferencias WHERE chave = 'chave_de_exibicao'")
        ).scalar()
    return config, chave


def test_a_senha_intocada_vira_copia_recuperavel(banco):
    _subir(banco)
    config, chave = _linha(banco)

    assert chave, "sem a chave de exibição não há como decifrar nada"
    assert decifrar(config["senha_master_cifrada"], chave) == SENHA_MASTER_DE_FABRICA
    assert decifrar(config["senha_login_cifrada"], chave) == SENHA_LOGIN_DE_FABRICA


def test_a_senha_ja_trocada_fica_sem_copia(banco):
    """O lado que importa: a migração não sabe qual é, e não inventa.

    A tela então diz "altere-a uma vez para poder visualizá-la", e a próxima
    troca grava a cópia sozinha.
    """
    _subir(banco)
    config, _ = _linha(banco)

    assert config["senha_operacional_cifrada"] is None


def test_o_cpf_do_dono_nunca_e_chutado(banco):
    """CPF não tem padrão de fábrica: não há o que recuperar."""
    _subir(banco)
    config, _ = _linha(banco)

    assert config["cpf_dono_cifrado"] is None


def test_o_texto_guardado_nao_contem_a_senha(banco):
    _subir(banco)
    config, _ = _linha(banco)

    assert SENHA_MASTER_DE_FABRICA not in config["senha_master_cifrada"]


def test_a_migracao_nao_toca_no_hash(banco):
    """A cópia recuperável é um acréscimo; a autenticação continua saindo do
    hash, e ele tem que atravessar a migração intacto."""
    engine = sa.create_engine(f"sqlite:///{banco}")
    with engine.connect() as conexao:
        antes = conexao.execute(
            sa.text(
                "SELECT senha_master_hash, senha_master_salt, senha_operacional_hash, "
                "senha_login_hash FROM loja_config WHERE id = 1"
            )
        ).one()

    _subir(banco)

    with engine.connect() as conexao:
        depois = conexao.execute(
            sa.text(
                "SELECT senha_master_hash, senha_master_salt, senha_operacional_hash, "
                "senha_login_hash FROM loja_config WHERE id = 1"
            )
        ).one()
    assert antes == depois


def test_banco_sem_a_linha_singleton_nao_quebra(tmp_path, monkeypatch):
    """A linha da loja só nasce no primeiro toque em "Senhas e Acesso": uma
    instalação que nunca abriu aquela tela chega aqui com `loja_config` vazia,
    e a migração tem que passar reto."""
    from alembic import command

    arquivo = tmp_path / "vazio.db"
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))
    command.upgrade(_config(arquivo), REVISAO_ANTERIOR)

    _subir(arquivo)

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT COUNT(*) FROM loja_config")).scalar() == 0


def test_a_ida_e_volta_derruba_as_colunas_e_a_chave(banco):
    from alembic import command

    _subir(banco)
    command.downgrade(_config(banco), REVISAO_ANTERIOR)

    engine = sa.create_engine(f"sqlite:///{banco}")
    with engine.connect() as conexao:
        colunas = {
            linha[1] for linha in conexao.execute(sa.text("PRAGMA table_info(loja_config)"))
        }
        chave = conexao.execute(
            sa.text("SELECT valor FROM preferencias WHERE chave = 'chave_de_exibicao'")
        ).scalar()

    assert "senha_master_cifrada" not in colunas
    assert "cpf_dono_cifrado" not in colunas
    assert chave is None
    # E o que importa de verdade na volta: o login continua funcionando.
    with engine.connect() as conexao:
        assert conexao.execute(
            sa.text("SELECT senha_master_hash FROM loja_config WHERE id = 1")
        ).scalar()
