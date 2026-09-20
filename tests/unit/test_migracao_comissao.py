"""A migração `f6a1d3b78c42`: o controle do repasse de comissão. §9.25.

O que os testes abaixo cobrem:

1. **o passado entra como acertado** — toda conta FECHADA que já existe nasce
   com a comissão marcada como paga, senão o programa abriria uma lista de
   pendências de todas as vendas antigas (dívida que ninguém tem);
2. **o que ainda não fechou fica pendente** — aberta, em conferência e
   cancelada ficam no zero do default;
3. **a data fica nula** — não sabemos quando o repasse foi feito, e `agora`
   registraria como de hoje o que foi feito semanas atrás;
4. **é atômica** — uma queda no meio não deixa coluna nenhuma para trás;
5. **a ida e a volta funcionam**, e o banco novo chega à head com as colunas.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial

REVISAO_ANTERIOR = "e4b8c2a6d913"
REVISAO = "f6a1d3b78c42"

# (id, status) — uma de cada situação que a coluna precisa distinguir.
COMANDAS = [(1, "FECHADA"), (2, "FECHADA"), (3, "EM_CONFERENCIA"), (4, "ABERTA"), (5, "CANCELADA")]
PAGAS = {1, 2}


def _config(arquivo: Path, monkeypatch):
    from alembic.config import Config

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    return config


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco na revisão ANTERIOR, com um turno e cinco comandas."""
    from alembic import command

    arquivo = tmp_path / "comissao.db"
    config = _config(arquivo, monkeypatch)
    command.upgrade(config, REVISAO_ANTERIOR)

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO caixas (id, status, valor_abertura, aberto_em) "
                "VALUES (1, 'ABERTO', 100, '2026-09-19 17:00:00')"
            )
        )
        for comanda_id, status in COMANDAS:
            conexao.execute(
                sa.text(
                    "INSERT INTO comandas (id, status, aberta_em, caixa_id, usuario_id, "
                    "valor_desconto, valor_taxa_servico, taxa_servico_percentual) "
                    "VALUES (:id, :status, '2026-09-19 18:00:00', 1, 1, 0, 13.15, 10)"
                ),
                {"id": comanda_id, "status": status},
            )
    yield config, engine
    engine.dispose()


def _colunas(engine) -> set[str]:
    return {coluna["name"] for coluna in sa.inspect(engine).get_columns("comandas")}


def _linhas(engine, sql: str) -> list[tuple]:
    with engine.begin() as conexao:
        return [tuple(linha) for linha in conexao.execute(sa.text(sql))]


def _versao(engine) -> str:
    return _linhas(engine, "SELECT version_num FROM alembic_version")[0][0]


# ----------------------------------------------------------------------
# 1, 2 e 3. O que cada conta antiga vira
# ----------------------------------------------------------------------


def test_o_passado_entra_como_acertado(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    marcas = dict(_linhas(engine, "SELECT id, comissao_paga FROM comandas ORDER BY id"))
    assert marcas == {comanda_id: int(comanda_id in PAGAS) for comanda_id, _status in COMANDAS}
    assert _versao(engine) == REVISAO


def test_a_data_do_repasse_antigo_fica_nula(banco):
    """Não sabemos quando foi: inventar `agora` registraria como repasse de hoje
    o que foi feito semanas atrás."""
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT COUNT(*) FROM comandas WHERE comissao_paga_em IS NOT NULL") == [(0,)]


def test_a_coluna_e_not_null_com_default(banco):
    """Comanda inserida por fora do ORM nasce com a comissão pendente."""
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO comandas (id, status, aberta_em, caixa_id, usuario_id, valor_desconto) "
                "VALUES (99, 'ABERTA', '2026-09-20 10:00:00', 1, 1, 0)"
            )
        )

    colunas = {c["name"]: c for c in sa.inspect(engine).get_columns("comandas")}
    assert colunas["comissao_paga"]["nullable"] is False
    assert colunas["comissao_paga_em"]["nullable"] is True
    assert _linhas(engine, "SELECT comissao_paga FROM comandas WHERE id = 99") == [(0,)]


# ----------------------------------------------------------------------
# 4. Atômica
# ----------------------------------------------------------------------


def test_queda_na_marcacao_nao_deixa_coluna_nenhuma(banco):
    from alembic import command

    config, engine = banco
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "CREATE TRIGGER queda BEFORE UPDATE ON comandas "
                "BEGIN SELECT RAISE(ABORT, 'queda de energia simulada'); END"
            )
        )

    with pytest.raises(Exception, match="queda de energia simulada"):
        command.upgrade(config, REVISAO)
    engine.dispose()

    assert {"comissao_paga", "comissao_paga_em"} & _colunas(engine) == set()
    assert _versao(engine) == REVISAO_ANTERIOR

    with engine.begin() as conexao:
        conexao.execute(sa.text("DROP TRIGGER queda"))
    command.upgrade(config, REVISAO)
    assert _linhas(engine, "SELECT comissao_paga FROM comandas WHERE id = 1") == [(1,)]


# ----------------------------------------------------------------------
# 5. Ida e volta
# ----------------------------------------------------------------------


def test_ida_volta_e_ida_de_novo(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)
    with engine.begin() as conexao:
        conexao.execute(sa.text("UPDATE comandas SET comissao_paga = 0 WHERE id = 1"))

    command.downgrade(config, REVISAO_ANTERIOR)
    assert {"comissao_paga", "comissao_paga_em"} & _colunas(engine) == set()
    # O valor da comissão continua lá: ele é a taxa de serviço da conta.
    assert _linhas(engine, "SELECT valor_taxa_servico FROM comandas WHERE id = 1") == [(13.15,)]

    command.upgrade(config, REVISAO)
    assert _linhas(engine, "SELECT comissao_paga FROM comandas WHERE id = 1") == [(1,)]


def test_banco_novo_chega_a_head_com_as_colunas(tmp_path, monkeypatch):
    from alembic import command
    from alembic.script import ScriptDirectory

    arquivo = tmp_path / "novo.db"
    config = _config(arquivo, monkeypatch)
    command.upgrade(config, "head")

    roteiro = ScriptDirectory.from_config(config)
    cabeca = roteiro.get_current_head()
    engine = sa.create_engine(f"sqlite:///{arquivo}")
    try:
        assert {"comissao_paga", "comissao_paga_em"} <= _colunas(engine)
        assert _versao(engine) == cabeca
        assert REVISAO in {revisao.revision for revisao in roteiro.walk_revisions("base", cabeca)}
    finally:
        engine.dispose()
