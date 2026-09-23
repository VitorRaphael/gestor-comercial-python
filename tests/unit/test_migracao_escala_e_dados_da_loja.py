"""A migração `d2a8f5c3e917`: escala da fonte e dados da loja. §9.30.

Roda no arranque do `.exe`, sobre a única cópia dos dados do food truck. O que
estes testes cobrem:

1. **cada impressora reabre em 2x** — o tamanho que a mesa já tinha — e a
   `letra_grossa` sai do banco;
2. **os dados da loja nascem vazios** (`NULL`), e o singleton de senhas intacto;
3. **é atômica** — uma falha no `DROP COLUMN` desfaz também as cinco colunas
   já acrescentadas, e a `alembic_version` fica na revisão anterior;
4. **o roteamento de impressão continua de pé**;
5. **a ida e a volta funcionam**.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial

REVISAO_ANTERIOR = "c5d9e17a24b8"
REVISAO = "d2a8f5c3e917"
COLUNAS_DA_LOJA = {"nome_loja", "telefone", "cidade", "uf"}


def _config(arquivo: Path, monkeypatch):
    from alembic.config import Config

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    return config


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Na revisão anterior: uma impressora grossa, uma fina e uma categoria roteada."""
    from alembic import command

    arquivo = tmp_path / "escala.db"
    config = _config(arquivo, monkeypatch)
    command.upgrade(config, REVISAO_ANTERIOR)

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO impressoras (id, nome, colunas, bobina_mm, letra_grossa, ativa, padrao, tipo_conexao) "
                "VALUES (1, 'Caixa', 48, 80, 1, 1, 1, 'ARQUIVO'), (2, 'Cozinha', 32, 58, 0, 1, 0, 'ARQUIVO')"
            )
        )
        conexao.execute(
            sa.text("INSERT INTO categorias (id, nome, ativo, arquivado, impressora_id) VALUES (1, 'Lanches', 1, 0, 2)")
        )
    yield config, engine
    engine.dispose()


def _colunas(engine, tabela: str) -> dict[str, dict]:
    return {coluna["name"]: coluna for coluna in sa.inspect(engine).get_columns(tabela)}


def _linhas(engine, sql: str) -> list[tuple]:
    with engine.begin() as conexao:
        return [tuple(linha) for linha in conexao.execute(sa.text(sql))]


def _versao(engine) -> str:
    return _linhas(engine, "SELECT version_num FROM alembic_version")[0][0]


def test_toda_impressora_nasce_em_2x_e_a_letra_grossa_sai(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    colunas = _colunas(engine, "impressoras")
    assert "letra_grossa" not in colunas
    assert colunas["escala_fonte"]["nullable"] is False
    assert _linhas(engine, "SELECT id, colunas, bobina_mm, escala_fonte FROM impressoras ORDER BY id") == [
        (1, 48, 80, 2),
        (2, 32, 58, 2),
    ]
    assert _versao(engine) == REVISAO


def test_impressora_inserida_por_fora_do_orm_nasce_em_2x(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO impressoras (nome, colunas, bobina_mm, ativa, padrao, tipo_conexao) "
                "VALUES ('Nova', 48, 80, 1, 0, 'ARQUIVO')"
            )
        )

    assert _linhas(engine, "SELECT escala_fonte FROM impressoras WHERE nome = 'Nova'") == [(2,)]


def test_os_dados_da_loja_nascem_anulaveis(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    colunas = _colunas(engine, "loja_config")
    assert COLUNAS_DA_LOJA <= set(colunas)
    assert all(colunas[nome]["nullable"] for nome in COLUNAS_DA_LOJA)


def test_falha_no_meio_nao_deixa_coluna_nenhuma(banco):
    """Um índice sobre `letra_grossa` faz o `DROP COLUMN` recusar DEPOIS de as
    cinco colunas terem sido acrescentadas. Sem o `BEGIN` da migração, elas
    ficariam no arquivo com a `alembic_version` na revisão anterior."""
    from alembic import command

    config, engine = banco
    with engine.begin() as conexao:
        conexao.execute(sa.text("CREATE INDEX idx_trava ON impressoras (letra_grossa)"))

    with pytest.raises(Exception):
        command.upgrade(config, REVISAO)
    engine.dispose()

    assert "escala_fonte" not in _colunas(engine, "impressoras")
    assert COLUNAS_DA_LOJA & set(_colunas(engine, "loja_config")) == set()
    assert "letra_grossa" in _colunas(engine, "impressoras")
    assert _versao(engine) == REVISAO_ANTERIOR

    # O boot seguinte, sem a trava, faz tudo do zero.
    with engine.begin() as conexao:
        conexao.execute(sa.text("DROP INDEX idx_trava"))
    command.upgrade(config, REVISAO)
    assert _versao(engine) == REVISAO


def test_o_vinculo_de_impressao_continua_de_pe(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT id, impressora_id FROM categorias") == [(1, 2)]
    assert _linhas(engine, "PRAGMA foreign_key_check") == []


def test_banco_novo_chega_a_head_com_as_colunas(tmp_path, monkeypatch):
    """Do zero até a head num `upgrade` só (o primeiro boot): a transação já
    vem aberta por uma revisão anterior, e o `BEGIN` daqui não abre outra."""
    from alembic import command

    arquivo = tmp_path / "novo.db"
    config = _config(arquivo, monkeypatch)
    command.upgrade(config, "head")
    engine = sa.create_engine(f"sqlite:///{arquivo}")
    try:
        assert "escala_fonte" in _colunas(engine, "impressoras")
        assert COLUNAS_DA_LOJA <= set(_colunas(engine, "loja_config"))
    finally:
        engine.dispose()


def test_ida_volta_e_ida_de_novo(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)
    command.downgrade(config, REVISAO_ANTERIOR)

    assert "escala_fonte" not in _colunas(engine, "impressoras")
    assert _linhas(engine, "SELECT letra_grossa FROM impressoras ORDER BY id") == [(0,), (0,)]
    assert COLUNAS_DA_LOJA & set(_colunas(engine, "loja_config")) == set()

    command.upgrade(config, REVISAO)
    assert _versao(engine) == REVISAO
    assert _linhas(engine, "SELECT escala_fonte FROM impressoras ORDER BY id") == [(2,), (2,)]
