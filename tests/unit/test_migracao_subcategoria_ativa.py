"""A migração `a3e6b91c4d05`: subcategoria com estado, produto arquivável. §9.13.

O banco da máquina do food truck é a **única cópia** dos dados do pai do Vitor,
e esta migração roda no arranque do `.exe`, antes de qualquer tela aparecer. Um
erro aqui não é um bug de tela: é o app não abrir na hora do almoço — ou, pior
neste caso, é o app abrir com o cardápio pela metade.

O que os testes abaixo cobrem:

1. **as duas colunas entram, e com o valor certo** — toda subdivisão que já
   existe nasce VENDENDO (`ativo = 1`) e todo produto nasce NÃO arquivado. Um
   `NULL` em `subcategorias.ativo` faria a consulta de lançamento
   (`subcategorias.ativo = 1`) sumir com produto do balcão na primeira abertura
   depois do upgrade, que é a pior forma possível de descobrir uma migração;
2. **o vínculo de impressão continua de pé** — a regra de ouro do §9.8, a mesma
   varredura da `e2c7b4f9a613`: `categorias.impressora_id` não é tocado, e
   nenhuma impressora precisa ser reconfigurada;
3. **rodar de novo não quebra** — se alguém tiver adicionado a coluna à mão para
   destravar um boot, o upgrade tem que passar por cima em silêncio;
4. **a ida e a volta funcionam** — é o que permite despromover a versão na
   máquina do balcão se algo der errado.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial

# A revisão imediatamente anterior à que está sendo testada.
REVISAO_ANTERIOR = "b6e2d80a3f14"
REVISAO = "a3e6b91c4d05"


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco na revisão ANTERIOR, com categoria, subdivisões e produtos.

    "Lanches" sai na impressora "Cozinha", tem duas subdivisões e três produtos
    (dois classificados, um solto). É o estado real de uma categoria em
    organização — e é o vínculo com a impressora que a regra de ouro proíbe a
    migração de tocar.
    """
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
        conexao.execute(
            sa.text(
                "INSERT INTO categorias (id, nome, ativo, impressora_id) "
                "VALUES (1, 'Lanches', 1, 1)"
            )
        )
        for sub_id, nome in [(1, "Podrão"), (2, "Artesanal")]:
            conexao.execute(
                sa.text(
                    "INSERT INTO subcategorias (id, nome, categoria_id) "
                    "VALUES (:id, :nome, 1)"
                ),
                {"id": sub_id, "nome": nome},
            )
        for produto_id, nome, sub in [(1, "X Burguer", 1), (2, "X Missão", 2), (3, "X Egg", None)]:
            conexao.execute(
                sa.text(
                    "INSERT INTO produtos "
                    "(id, nome, preco, custo, ativo, is_combo, categoria_id, subcategoria_id) "
                    "VALUES (:id, :nome, '13.00', 0, 1, 0, 1, :sub)"
                ),
                {"id": produto_id, "nome": nome, "sub": sub},
            )
    return config, engine


def _colunas(engine, tabela: str) -> set[str]:
    return {coluna["name"] for coluna in sa.inspect(engine).get_columns(tabela)}


def _linhas(engine, sql: str) -> list[tuple]:
    with engine.begin() as conexao:
        return [tuple(linha) for linha in conexao.execute(sa.text(sql))]


def test_as_duas_colunas_entram(banco):
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert "ativo" in _colunas(engine, "subcategorias")
    assert "arquivado" in _colunas(engine, "produtos")


def test_toda_subdivisao_que_ja_existia_continua_vendendo(banco):
    """O ponto da migração: `NOT NULL DEFAULT 1` preenche o que já está lá.

    Sem isto, a primeira abertura depois do upgrade teria o cardápio inteiro
    fora do balcão — as duas subdivisões com `ativo` nulo, e a consulta de
    lançamento exigindo `= 1`.
    """
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT nome, ativo FROM subcategorias ORDER BY nome") == [
        ("Artesanal", 1),
        ("Podrão", 1),
    ]


def test_nenhum_produto_nasce_arquivado(banco):
    """Arquivado é o que a cascata do §9.13 marca — nunca um estado de partida."""
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT nome, arquivado FROM produtos ORDER BY nome") == [
        ("X Burguer", 0),
        ("X Egg", 0),
        ("X Missão", 0),
    ]


def test_o_produto_e_a_classificacao_dele_sobrevivem(banco):
    """A migração acrescenta; ela não reclassifica nem desclassifica nada."""
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert _linhas(
        engine, "SELECT nome, categoria_id, subcategoria_id FROM produtos ORDER BY nome"
    ) == [
        ("X Burguer", 1, 1),
        ("X Egg", 1, None),
        ("X Missão", 1, 2),
    ]


def test_a_impressora_da_categoria_nao_e_tocada(banco):
    """A REGRA DE OURO do §9.8, na altura da migração.

    O estado novo mora em `subcategorias` e em `produtos`; `categorias.
    impressora_id`, que é quem decide a bobina, sai igual — e por isso nenhuma
    impressora do food truck precisa ser reconfigurada depois deste upgrade.
    """
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT nome, impressora_id FROM categorias") == [("Lanches", 1)]


def test_rodar_o_upgrade_com_a_coluna_ja_criada_nao_quebra(banco):
    """Idempotência: a coluna posta à mão para destravar um boot não derruba o app."""
    from alembic import command

    config, engine = banco

    with engine.begin() as conexao:
        conexao.execute(
            sa.text("ALTER TABLE subcategorias ADD COLUMN ativo BOOLEAN NOT NULL DEFAULT 1")
        )

    command.upgrade(config, REVISAO)

    assert "ativo" in _colunas(engine, "subcategorias")
    assert "arquivado" in _colunas(engine, "produtos")


def test_ida_e_volta(banco):
    """Despromover a versão no balcão tem que ser possível sem perder linha."""
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)
    command.downgrade(config, REVISAO_ANTERIOR)

    assert "ativo" not in _colunas(engine, "subcategorias")
    assert "arquivado" not in _colunas(engine, "produtos")
    assert _linhas(engine, "SELECT COUNT(*) FROM produtos") == [(3,)]
    assert _linhas(engine, "SELECT COUNT(*) FROM subcategorias") == [(2,)]
