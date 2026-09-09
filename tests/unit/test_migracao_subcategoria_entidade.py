"""A migração `f8d1a6c40b27` converte a etiqueta de texto em entidade. §9.9.

A revisão anterior (`e2c7b4f9a613`) guardou a subcategoria como TEXTO no
produto. Funcionava para etiquetar, e não para o que o Vitor pediu em seguida:
uma tela de cadastro. Esta migração cria `subcategorias`, converte o dado que
existir e derruba a coluna antiga.

O banco da máquina do food truck é a **única cópia** dos dados, e esta migração
roda no arranque do `.exe`. O que os testes abaixo cobrem:

1. **a conversão não perde nem embaralha** — cada par (categoria, texto) vira
   UMA linha, e cada produto passa a apontar para a linha da categoria DELE. Um
   "Podrão" de Lanches não pode acabar apontando para o "Podrão" de Porções;
2. **o vínculo de impressão continua de pé** — a regra de ouro do §9.8;
3. **a ida e a volta preservam o dado** — é o que permite despromover a versão
   na máquina do balcão se algo der errado.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial

REVISAO_ANTERIOR = "e2c7b4f9a613"
REVISAO = "f8d1a6c40b27"


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco na revisão ANTERIOR, com a etiqueta de texto já preenchida.

    Duas categorias usam o MESMO texto ("Podrão"), que é o caso capaz de
    embaralhar produto entre grupos se a conversão casar só pelo nome.
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
        for categoria_id, nome in [(1, "Lanches"), (2, "Porções")]:
            conexao.execute(
                sa.text(
                    "INSERT INTO categorias (id, nome, ativo, impressora_id) "
                    "VALUES (:id, :nome, 1, 1)"
                ),
                {"id": categoria_id, "nome": nome},
            )
        produtos = [
            (1, "X Burguer", 1, "Podrão"),
            (2, "X Tudo", 1, "Podrão"),
            (3, "X Artesanal", 1, "Artesanal"),
            (4, "Batata", 2, "Podrão"),
            (5, "Água", 2, None),
        ]
        for produto_id, nome, categoria_id, sub in produtos:
            conexao.execute(
                sa.text(
                    "INSERT INTO produtos (id, nome, preco, custo, ativo, is_combo, "
                    "categoria_id, subcategoria) "
                    "VALUES (:id, :nome, 10, 0, 1, 0, :cat, :sub)"
                ),
                {"id": produto_id, "nome": nome, "cat": categoria_id, "sub": sub},
            )
    return config, engine


def _colunas(engine, tabela: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(tabela)}


def _subcategorias(engine) -> list[tuple[str, int]]:
    with engine.connect() as conexao:
        return [
            (linha[0], linha[1])
            for linha in conexao.execute(
                sa.text("SELECT nome, categoria_id FROM subcategorias ORDER BY categoria_id, nome")
            )
        ]


def _vinculos(engine) -> list[tuple[str, str | None]]:
    """Produto → nome da subcategoria apontada (ou None)."""
    with engine.connect() as conexao:
        return [
            (linha[0], linha[1])
            for linha in conexao.execute(
                sa.text(
                    "SELECT p.nome, s.nome FROM produtos p "
                    "LEFT JOIN subcategorias s ON s.id = p.subcategoria_id "
                    "ORDER BY p.id"
                )
            )
        ]


def test_cada_par_categoria_texto_vira_uma_linha(banco):
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    # "Podrão" aparece DUAS vezes: uma por categoria. São duas subdivisões
    # independentes, e juntá-las numa só faria a Batata de Porções aparecer
    # dentro de Lanches.
    assert _subcategorias(engine) == [
        ("Artesanal", 1),
        ("Podrão", 1),
        ("Podrão", 2),
    ]


def test_cada_produto_aponta_para_a_subcategoria_da_categoria_dele(banco):
    """O caso que uma junção só pelo nome embaralharia."""
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert _vinculos(engine) == [
        ("X Burguer", "Podrão"),
        ("X Tudo", "Podrão"),
        ("X Artesanal", "Artesanal"),
        ("Batata", "Podrão"),
        ("Água", None),
    ]
    with engine.connect() as conexao:
        categorias = conexao.execute(
            sa.text(
                "SELECT p.nome, s.categoria_id FROM produtos p "
                "JOIN subcategorias s ON s.id = p.subcategoria_id ORDER BY p.id"
            )
        ).all()
    assert [linha[1] for linha in categorias] == [1, 1, 1, 2]


def test_a_coluna_de_texto_e_o_indice_antigo_saem(banco):
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    assert "subcategoria" not in _colunas(engine, "produtos")
    assert "subcategoria_id" in _colunas(engine, "produtos")
    indices = {i["name"] for i in sa.inspect(engine).get_indexes("produtos")}
    assert "idx_produtos_categoria_sub" not in indices
    assert "ix_produtos_subcategoria_id" in indices


def test_o_par_categoria_nome_e_unico_no_banco(banco):
    """A checagem do service compara ignorando acento e caixa, o que é mais
    rígido que isto — mas quem gravar sem passar por ele (uma migração, um
    script) também não pode conseguir criar o par exato duas vezes."""
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conexao:
            conexao.execute(
                sa.text("INSERT INTO subcategorias (nome, categoria_id) VALUES ('Podrão', 1)")
            )


def test_o_vinculo_de_impressao_nao_e_tocado(banco):
    """A REGRA DE OURO, no nível do schema."""
    from alembic import command

    config, engine = banco

    command.upgrade(config, REVISAO)

    with engine.connect() as conexao:
        vinculos = conexao.execute(
            sa.text("SELECT id, impressora_id FROM categorias ORDER BY id")
        ).all()
    assert [tuple(linha) for linha in vinculos] == [(1, 1), (2, 1)]


def test_upgrade_e_downgrade_ida_e_volta_preserva_o_dado(banco):
    """Voltar devolve a coluna de texto preenchida — e é isso que permite
    despromover a versão no balcão sem perder a organização do cardápio."""
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    command.downgrade(config, REVISAO_ANTERIOR)

    assert "subcategoria_id" not in _colunas(engine, "produtos")
    assert "subcategorias" not in sa.inspect(engine).get_table_names()
    with engine.connect() as conexao:
        textos = conexao.execute(
            sa.text("SELECT nome, subcategoria FROM produtos ORDER BY id")
        ).all()
    assert [tuple(linha) for linha in textos] == [
        ("X Burguer", "Podrão"),
        ("X Tudo", "Podrão"),
        ("X Artesanal", "Artesanal"),
        ("Batata", "Podrão"),
        ("Água", None),
    ]

    command.upgrade(config, REVISAO)
    assert _vinculos(engine)[0] == ("X Burguer", "Podrão")


def test_banco_sem_etiqueta_nenhuma_sobe_igual(tmp_path, monkeypatch):
    """O caso da máquina do food truck: a revisão anterior entrou hoje e o
    `seed.py` nunca classificou produto nenhum, então não há o que converter."""
    from alembic import command
    from alembic.config import Config

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    arquivo = tmp_path / "vazio.db"
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")

    command.upgrade(config, REVISAO)

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    assert _subcategorias(engine) == []
    assert "subcategoria_id" in _colunas(engine, "produtos")


# ---------------------------------------------------------------------------
# O banco de VERDADE: populado, e no meio de uma tentativa que falhou
# ---------------------------------------------------------------------------
#
# Esta seção existe por causa de um defeito que a suíte deixou passar e que
# derrubou o app do Vitor no arranque, com o cardápio semeado:
#
#     sqlite3.IntegrityError: FOREIGN KEY constraint failed
#     [SQL: DROP TABLE produtos]
#
# A migração usava `batch_alter_table` para tirar a coluna de texto, e o batch
# funciona RECRIANDO a tabela — com o `PRAGMA foreign_keys=ON` do §3.5 ligado, o
# `DROP TABLE produtos` do meio do caminho esbarra nas linhas de `combo_itens` e
# `itens_comanda` que apontam para ela.
#
# O que os testes acima não tinham: linha nenhuma REFERENCIANDO `produtos`. Num
# banco assim o batch passa liso, e foi por isso que tudo estava verde.


@pytest.fixture
def banco_povoado(tmp_path, monkeypatch):
    """A revisão anterior com o que o `seed.py` deixa: produtos COM referências.

    `combo_itens` e `itens_comanda` são as duas tabelas que apontam para
    `produtos` — e o seed do primeiro boot já cria 8 componentes de combo, então
    este é o estado da máquina do food truck, não um caso de laboratório.
    """
    from alembic import command
    from alembic.config import Config

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    arquivo = tmp_path / "povoado.db"
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    command.upgrade(config, REVISAO_ANTERIOR)

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    with engine.begin() as conexao:
        conexao.execute(
            sa.text("INSERT INTO categorias (id, nome, ativo) VALUES (1, 'Lanches', 1)")
        )
        for produto_id, nome, sub in [
            (1, "X Burguer", "Podrão"),
            (2, "X Tudo", "Podrão"),
            (3, "Combo Casal", None),
        ]:
            conexao.execute(
                sa.text(
                    "INSERT INTO produtos (id, nome, preco, custo, ativo, is_combo, "
                    "categoria_id, subcategoria) VALUES (:id, :n, 10, 0, 1, 0, 1, :s)"
                ),
                {"id": produto_id, "n": nome, "s": sub},
            )
        conexao.execute(
            sa.text(
                "INSERT INTO combo_itens (id, combo_id, produto_id, quantidade) "
                "VALUES (1, 3, 1, 1)"
            )
        )
    return config, engine


def test_a_migracao_sobe_com_produtos_referenciados(banco_povoado):
    """O defeito que derrubou o app do Vitor, agora trancado.

    Se alguém trocar o `DROP COLUMN` nativo por `batch_alter_table` de novo,
    este teste morre em "FOREIGN KEY constraint failed" antes de chegar às
    asserções.
    """
    from alembic import command

    config, engine = banco_povoado

    command.upgrade(config, REVISAO)

    assert "subcategoria" not in _colunas(engine, "produtos")
    assert _vinculos(engine) == [
        ("X Burguer", "Podrão"),
        ("X Tudo", "Podrão"),
        ("Combo Casal", None),
    ]
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT COUNT(*) FROM combo_itens")).scalar_one() == 1


def _modulo_da_migracao():
    """Carrega o arquivo da migração como módulo, para chamar `_dropar_coluna`.

    A alternativa seria conferir o `PRAGMA` depois do `command.upgrade`, e ela
    NÃO serve: o Alembic fecha a conexão dele no fim, e qualquer conexão nova
    nasce com as FKs ligadas pelo listener do `repository/base.py` (§3.5). Ou
    seja, um `finally` que esquecesse de religar passaria despercebido — a
    asserção estaria olhando para a conexão errada.
    """
    import importlib.util

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    caminho = raiz / "migrations" / "versions" / f"{REVISAO}_subcategoria_vira_entidade.py"
    spec = importlib.util.spec_from_file_location("migracao_subcategoria", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_o_caminho_de_compatibilidade_religa_as_chaves_estrangeiras(banco_povoado, monkeypatch):
    """Na MESMA conexão em que a migração as desligou.

    Um banco que seguisse com as FKs desligadas aceitaria item órfão em
    silêncio, que é exatamente o que o §3.5 existe para impedir — e, dentro de
    um `alembic upgrade` que roda várias revisões, a conexão é reaproveitada
    pelas migrações seguintes.
    """
    import sqlite3

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    _, engine = banco_povoado
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.30.0")
    modulo = _modulo_da_migracao()

    with engine.connect() as conexao:
        assert conexao.execute(sa.text("PRAGMA foreign_keys")).scalar_one() == 1, (
            "premissa: o listener do §3.5 liga as FKs em toda conexão"
        )
        contexto = MigrationContext.configure(conexao)
        with Operations.context(contexto):
            # Na ordem da migração: o índice usa a coluna, e o SQLite recusa
            # `DROP COLUMN` enquanto ele existir.
            conexao.execute(sa.text("DROP INDEX IF EXISTS idx_produtos_categoria_sub"))
            modulo._dropar_coluna("produtos", "subcategoria")

        assert conexao.execute(sa.text("PRAGMA foreign_keys")).scalar_one() == 1, (
            "a migração deixou as chaves estrangeiras DESLIGADAS na conexão"
        )
    assert "subcategoria" not in _colunas(engine, "produtos")


def test_o_caminho_nativo_nao_encosta_nas_chaves_estrangeiras(banco_povoado):
    """O caminho que roda na máquina do food truck não desliga nada: o
    `DROP COLUMN` nativo não recria a tabela, então não há o que proteger."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    _, engine = banco_povoado
    modulo = _modulo_da_migracao()
    assert modulo._tem_drop_column_nativo(), "o SQLite embarcado deixou de ter DROP COLUMN"

    with engine.connect() as conexao:
        contexto = MigrationContext.configure(conexao)
        with Operations.context(contexto):
            conexao.execute(sa.text("DROP INDEX IF EXISTS idx_produtos_categoria_sub"))
            modulo._dropar_coluna("produtos", "subcategoria")

        assert conexao.execute(sa.text("PRAGMA foreign_keys")).scalar_one() == 1
    assert "subcategoria" not in _colunas(engine, "produtos")


def test_o_caminho_de_compatibilidade_tambem_sobe(banco_povoado, monkeypatch):
    """O `batch_alter_table` com as FKs desligadas, para SQLite < 3.35.

    O app embarca a sua própria 3.50, então este caminho não roda na máquina do
    food truck — e é justamente por isso que ele precisa de teste: um caminho
    que nunca roda é um caminho que ninguém percebe quebrado.

    `sqlite3.sqlite_version` é lido DENTRO da migração, e o módulo `sqlite3` é o
    mesmo que o Alembic carrega — por isso o `monkeypatch` chega lá.
    """
    import sqlite3

    from alembic import command

    config, engine = banco_povoado
    monkeypatch.setattr(sqlite3, "sqlite_version", "3.30.0")

    command.upgrade(config, REVISAO)

    assert "subcategoria" not in _colunas(engine, "produtos")
    assert _vinculos(engine)[0] == ("X Burguer", "Podrão")
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT COUNT(*) FROM combo_itens")).scalar_one() == 1
        assert conexao.execute(sa.text("PRAGMA foreign_keys")).scalar_one() == 1


def test_a_migracao_retoma_de_uma_tentativa_que_morreu_no_meio(banco_povoado):
    """O estado em que o banco do Vitor ficou depois do primeiro erro.

    O Alembic assume DDL **não-transacional** no SQLite: a tabela criada pela
    tentativa que falhou continuou lá e a `alembic_version` ficou na revisão
    anterior. Sem os `if_not_exists`, a segunda tentativa bate em "table
    subcategorias already exists" — e o app não abre nunca mais, porque a
    migração roda no arranque.
    """
    from alembic import command

    config, engine = banco_povoado
    # Reproduz o que a primeira tentativa alcançou antes de morrer no
    # `DROP TABLE produtos`: tabela, índices e a coluna nova já existem.
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "CREATE TABLE subcategorias (id INTEGER NOT NULL, nome VARCHAR(80) NOT NULL, "
                "categoria_id INTEGER NOT NULL, PRIMARY KEY (id), "
                "FOREIGN KEY(categoria_id) REFERENCES categorias (id), "
                "CONSTRAINT uq_subcategoria_por_categoria UNIQUE (categoria_id, nome))"
            )
        )
        conexao.execute(
            sa.text("CREATE INDEX ix_subcategorias_categoria_id ON subcategorias (categoria_id)")
        )
        conexao.execute(
            sa.text(
                "CREATE INDEX idx_subcategorias_categoria_nome "
                "ON subcategorias (categoria_id, nome)"
            )
        )
        conexao.execute(sa.text("ALTER TABLE produtos ADD COLUMN subcategoria_id INTEGER"))
        conexao.execute(
            sa.text("CREATE INDEX ix_produtos_subcategoria_id ON produtos (subcategoria_id)")
        )

    command.upgrade(config, REVISAO)

    with engine.connect() as conexao:
        assert (
            conexao.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
            == REVISAO
        )
    # E a conversão do dado acontece na retomada, e não fica pela metade.
    assert _vinculos(engine) == [
        ("X Burguer", "Podrão"),
        ("X Tudo", "Podrão"),
        ("Combo Casal", None),
    ]
    assert "subcategoria" not in _colunas(engine, "produtos")


def test_a_volta_tambem_sobe_com_produtos_referenciados(banco_povoado):
    """O `downgrade` tinha o mesmo `batch_alter_table`, e o mesmo problema."""
    from alembic import command

    config, engine = banco_povoado
    command.upgrade(config, REVISAO)

    command.downgrade(config, REVISAO_ANTERIOR)

    with engine.connect() as conexao:
        textos = conexao.execute(
            sa.text("SELECT nome, subcategoria FROM produtos ORDER BY id")
        ).all()
        assert conexao.execute(sa.text("SELECT COUNT(*) FROM combo_itens")).scalar_one() == 1
    assert [tuple(linha) for linha in textos] == [
        ("X Burguer", "Podrão"),
        ("X Tudo", "Podrão"),
        ("Combo Casal", None),
    ]
