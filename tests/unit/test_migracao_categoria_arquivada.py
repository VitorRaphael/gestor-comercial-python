"""A migração `c7b4e0f12a86`: a categoria passa a poder ser arquivada. §9.14.

O banco da máquina do food truck é a **única cópia** dos dados do pai do Vitor, e
esta migração roda no arranque do `.exe`, antes de qualquer tela aparecer. Um
erro aqui não é um bug de tela: é o app não abrir na hora do almoço.

O que os testes abaixo cobrem:

1. **a coluna entra com o valor certo** — categoria que já existe nunca foi
   arquivada, e um `NULL` aqui sumiria com o cardápio inteiro da tela na
   primeira abertura depois do upgrade;
2. **o vínculo de impressão continua de pé** — a regra de ouro do §9.8, a mesma
   varredura das migrações irmãs;
3. **rodar de novo não quebra** — a coluna posta à mão para destravar um boot
   não pode derrubar o app;
4. **a ida e a volta funcionam** — despromover a versão no balcão tem que ser
   possível sem perder linha.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial

REVISAO_ANTERIOR = "a3e6b91c4d05"
REVISAO = "c7b4e0f12a86"


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco na revisão ANTERIOR, com duas categorias e uma impressora."""
    from alembic import command
    from alembic.config import Config

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    arquivo = tmp_path / "cardapio.db"
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))

    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    command.upgrade(config, REVISAO_ANTERIOR)

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO impressoras (id, nome, colunas, ativa, padrao, tipo_conexao) "
                "VALUES (1, 'Cozinha', 32, 1, 1, 'ARQUIVO')"
            )
        )
        for categoria_id, nome, impressora in [(1, "Lanches", 1), (2, "Bebidas", None)]:
            conexao.execute(
                sa.text(
                    "INSERT INTO categorias (id, nome, ativo, impressora_id) "
                    "VALUES (:id, :nome, 1, :impressora)"
                ),
                {"id": categoria_id, "nome": nome, "impressora": impressora},
            )
        conexao.execute(
            sa.text(
                "INSERT INTO produtos "
                "(id, nome, preco, custo, ativo, arquivado, is_combo, categoria_id) "
                "VALUES (1, 'X Burguer', '13.00', 0, 1, 0, 0, 1)"
            )
        )
    return config, engine


def _colunas(engine) -> set[str]:
    return {coluna["name"] for coluna in sa.inspect(engine).get_columns("categorias")}


def _linhas(engine, sql: str) -> list[tuple]:
    with engine.begin() as conexao:
        return [tuple(linha) for linha in conexao.execute(sa.text(sql))]


def test_a_coluna_entra(banco):
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert "arquivado" in _colunas(engine)


def test_nenhuma_categoria_nasce_arquivada(banco):
    """Arquivado é o que a cascata do §9.14 marca — nunca um estado de partida.

    Um `NULL` aqui faria `listar_do_cardapio` (que exige `= 0`) devolver lista
    vazia: o cardapio inteiro sumiria da tela na primeira abertura.
    """
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT nome, arquivado FROM categorias ORDER BY nome") == [
        ("Bebidas", 0),
        ("Lanches", 0),
    ]


def test_a_impressora_da_categoria_nao_e_tocada(banco):
    """A REGRA DE OURO do §9.8, na altura da migração."""
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert _linhas(
        engine, "SELECT nome, impressora_id FROM categorias ORDER BY nome"
    ) == [("Bebidas", None), ("Lanches", 1)]


def test_o_produto_continua_apontando_para_a_categoria(banco):
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT nome, categoria_id FROM produtos") == [("X Burguer", 1)]


def test_rodar_o_upgrade_com_a_coluna_ja_criada_nao_quebra(banco):
    from alembic import command

    config, engine = banco

    with engine.begin() as conexao:
        conexao.execute(
            sa.text("ALTER TABLE categorias ADD COLUMN arquivado BOOLEAN NOT NULL DEFAULT 0")
        )

    command.upgrade(config, REVISAO)

    assert "arquivado" in _colunas(engine)


def test_ida_e_volta(banco):
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)
    command.downgrade(config, REVISAO_ANTERIOR)

    assert "arquivado" not in _colunas(engine)
    assert _linhas(engine, "SELECT COUNT(*) FROM categorias") == [(2,)]
    assert _linhas(engine, "SELECT COUNT(*) FROM produtos") == [(1,)]
