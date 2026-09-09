"""A migração `e2c7b4f9a613` acrescenta o sub-modelo sem tocar em nada. §9.8.

O banco da máquina do food truck é a **única cópia** dos dados do pai do Vitor,
e esta migração roda no arranque do `.exe`, antes de qualquer tela aparecer. Um
erro aqui não é um bug de tela: é o app não abrir na hora do almoço.

O que os testes abaixo cobrem:

1. **o produto que já existe sobrevive** — nome, preço e categoria intactos, e
   `subcategoria` em `NULL`, que é o mesmo estado de um produto novo cadastrado
   sem preencher o campo. Não há dado a chutar (a diferença para a
   `c1d5b8e37a42`, que precisava adivinhar tamanho de senha);
2. **o vínculo de impressão continua de pé** — a regra de ouro do §9.8. A
   coluna nova está em `produtos`, e `categorias.impressora_id`, que é quem
   decide a bobina, não é tocado;
3. **rodar de novo não quebra** — se alguém tiver adicionado a coluna à mão
   para destravar um boot, o upgrade tem que passar por cima em silêncio;
4. **a ida e a volta funcionam** — é o que permite despromover a versão na
   máquina do balcão se algo der errado.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial

# A revisão imediatamente anterior à que está sendo testada.
REVISAO_ANTERIOR = "d9b4c7e21f30"
REVISAO = "e2c7b4f9a613"

INDICE = "idx_produtos_categoria_sub"


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco na revisão ANTERIOR, com um cardápio pequeno já cadastrado.

    "Lanches" sai na impressora "Cozinha" e tem dois produtos; é esse vínculo
    que a regra de ouro proíbe a migração de mexer.
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
        for produto_id, nome, preco in [(1, "X Burguer", "13.00"), (2, "X Tudo", "16.00")]:
            conexao.execute(
                sa.text(
                    "INSERT INTO produtos (id, nome, preco, custo, ativo, is_combo, categoria_id) "
                    "VALUES (:id, :nome, :preco, 0, 1, 0, 1)"
                ),
                {"id": produto_id, "nome": nome, "preco": preco},
            )
    return config, engine


def _colunas(engine) -> set[str]:
    return {coluna["name"] for coluna in sa.inspect(engine).get_columns("produtos")}


def _indices(engine) -> dict[str, list[str]]:
    return {i["name"]: list(i["column_names"]) for i in sa.inspect(engine).get_indexes("produtos")}


def test_a_coluna_e_o_indice_entram(banco):
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert "subcategoria" in _colunas(engine)
    assert _indices(engine)[INDICE] == ["categoria_id", "subcategoria"]


def test_o_indice_antigo_da_categoria_continua_de_pe(banco):
    """O composto ACRESCENTA; ele não substitui o `ix_produtos_categoria_id`.

    Quem consulta produto por categoria (a tela do Cardápio, o `existe_com_
    categoria` que barra a exclusão) usa o índice de uma coluna só, e perdê-lo
    seria trocar uma consulta rápida por uma varredura em toda tela de cadastro.
    """
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert _indices(engine)["ix_produtos_categoria_id"] == ["categoria_id"]


def test_o_produto_que_ja_existia_sobrevive_com_submodelo_nulo(banco):
    """Nada a migrar e nada a chutar: produto antigo é produto sem sub-modelo."""
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    with engine.connect() as conexao:
        linhas = conexao.execute(
            sa.text("SELECT nome, preco, categoria_id, subcategoria FROM produtos ORDER BY id")
        ).mappings().all()

    assert [linha["nome"] for linha in linhas] == ["X Burguer", "X Tudo"]
    assert [linha["categoria_id"] for linha in linhas] == [1, 1]
    assert all(linha["subcategoria"] is None for linha in linhas)


def test_o_vinculo_de_impressao_nao_e_tocado(banco):
    """A REGRA DE OURO, no nível do schema.

    Depois do upgrade, "Lanches" continua apontando para a impressora 1. Se a
    migração um dia começar a mexer em `categorias`, o pai do Vitor descobriria
    isso no primeiro pedido que não saísse na cozinha — aqui ela reprova antes.
    """
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    with engine.connect() as conexao:
        vinculo = conexao.execute(
            sa.text("SELECT impressora_id FROM categorias WHERE id = 1")
        ).scalar_one()

    assert vinculo == 1


def test_upgrade_passa_por_cima_de_uma_coluna_criada_a_mao(banco):
    """Idempotência, e o motivo dela: a máquina do balcão é a única cópia.

    Se alguém tiver adicionado a coluna manualmente para destravar um boot, o
    upgrade não pode derrubar o app no arranque com "duplicate column name".
    """
    from alembic import command

    config, engine = banco
    with engine.begin() as conexao:
        conexao.execute(sa.text("ALTER TABLE produtos ADD COLUMN subcategoria VARCHAR(80)"))
        conexao.execute(
            sa.text(f"CREATE INDEX {INDICE} ON produtos (categoria_id, subcategoria)")
        )

    command.upgrade(config, REVISAO)

    assert "subcategoria" in _colunas(engine)
    assert _indices(engine)[INDICE] == ["categoria_id", "subcategoria"]


def test_upgrade_e_downgrade_ida_e_volta(banco):
    """Voltar apaga os sub-modelos digitados — é o preço, e é conhecido. O que
    não pode é a volta deixar o banco num estado que a versão anterior recusa."""
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)
    with engine.begin() as conexao:
        conexao.execute(sa.text("UPDATE produtos SET subcategoria = 'Podrão' WHERE id = 1"))

    command.downgrade(config, REVISAO_ANTERIOR)

    assert "subcategoria" not in _colunas(engine)
    assert INDICE not in _indices(engine)
    # O produto continua lá, com categoria e impressora — só a etiqueta se foi.
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT COUNT(*) FROM produtos")).scalar_one() == 2
        assert conexao.execute(
            sa.text("SELECT impressora_id FROM categorias WHERE id = 1")
        ).scalar_one() == 1

    command.upgrade(config, REVISAO)
    assert "subcategoria" in _colunas(engine)
