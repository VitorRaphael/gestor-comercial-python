"""A migração `b9d2f5a31c47`: a bobina gravada e a letra grossa da impressora. §9.22.

O banco da máquina do food truck é a **única cópia** dos dados do pai do Vitor, e
esta migração roda no arranque do `.exe`, antes de qualquer tela aparecer.

O que os testes abaixo cobrem:

1. **cada impressora que já existe reabre como abria** — a bobina preenchida
   pela regra do §9.19 (até 40 colunas é 58mm), a letra fina, as colunas intactas;
2. **a regra do SQL é a regra do domain** — as duas cópias não podem divergir;
3. **é atômica** — uma queda no meio do preenchimento não deixa coluna nenhuma
   para trás, e a `alembic_version` continua na revisão anterior;
4. **coluna posta à mão não derruba o boot**, e mesmo assim a bobina é preenchida;
5. **o roteamento de impressão continua de pé**;
6. **a ida e a volta funcionam**, e o banco criado do zero chega ao mesmo schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial
from gestor_comercial.domain.impressora import bobina_mm_das_colunas

REVISAO_ANTERIOR = "c7b4e0f12a86"
REVISAO = "b9d2f5a31c47"

# (id, nome, colunas) — as larguras que um cadastro antigo pode ter: as duas
# de fábrica, o teto do 58mm, o 42 ambíguo do §9.19 e uma larga.
LEGADAS = [(1, "Caixa", 32), (2, "Balcão", 40), (3, "Bar", 42), (4, "Cozinha", 48), (5, "Copa", 64)]


def _config(arquivo: Path, monkeypatch):
    from alembic.config import Config

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    return config


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco na revisão ANTERIOR, com cinco impressoras e uma categoria roteada."""
    from alembic import command

    arquivo = tmp_path / "impressoras.db"
    config = _config(arquivo, monkeypatch)
    command.upgrade(config, REVISAO_ANTERIOR)

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    with engine.begin() as conexao:
        for impressora_id, nome, colunas in LEGADAS:
            conexao.execute(
                sa.text(
                    "INSERT INTO impressoras (id, nome, colunas, ativa, padrao, tipo_conexao) "
                    "VALUES (:id, :nome, :colunas, 1, :padrao, 'ARQUIVO')"
                ),
                {"id": impressora_id, "nome": nome, "colunas": colunas, "padrao": impressora_id == 1},
            )
        conexao.execute(
            sa.text("INSERT INTO categorias (id, nome, ativo, arquivado, impressora_id) VALUES (1, 'Lanches', 1, 0, 4)")
        )
    yield config, engine
    engine.dispose()


def _colunas(engine) -> set[str]:
    return {coluna["name"] for coluna in sa.inspect(engine).get_columns("impressoras")}


def _linhas(engine, sql: str) -> list[tuple]:
    with engine.begin() as conexao:
        return [tuple(linha) for linha in conexao.execute(sa.text(sql))]


def _versao(engine) -> str:
    return _linhas(engine, "SELECT version_num FROM alembic_version")[0][0]


# ----------------------------------------------------------------------
# 1. Cada impressora reabre como abria
# ----------------------------------------------------------------------


def test_a_bobina_das_antigas_sai_das_colunas_e_a_letra_nasce_fina(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT id, colunas, bobina_mm, letra_grossa FROM impressoras ORDER BY id") == [
        (1, 32, 58, 0),
        (2, 40, 58, 0),
        (3, 42, 80, 0),
        (4, 48, 80, 0),
        (5, 64, 80, 0),
    ]
    assert _versao(engine) == REVISAO


def test_as_colunas_novas_sao_not_null_com_default(banco):
    """Impressora inserida por fora do ORM (um script, a semente) nasce 80mm e fina."""
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO impressoras (nome, colunas, ativa, padrao, tipo_conexao) "
                "VALUES ('Nova', 48, 1, 0, 'ARQUIVO')"
            )
        )

    colunas = {c["name"]: c for c in sa.inspect(engine).get_columns("impressoras")}
    assert colunas["bobina_mm"]["nullable"] is False
    assert colunas["letra_grossa"]["nullable"] is False
    assert _linhas(engine, "SELECT bobina_mm, letra_grossa FROM impressoras WHERE nome = 'Nova'") == [(80, 0)]


# ----------------------------------------------------------------------
# 2. A regra do SQL é a regra do domain
# ----------------------------------------------------------------------


def test_o_case_da_migracao_e_a_regra_do_domain(banco):
    """Toda largura que o service aceita (20 a 96): a migração e o domain dão a
    mesma bobina. Divergir faria a impressora reabrir numa bobina e a edição
    seguinte deduzir outra."""
    from alembic import command

    config, engine = banco
    with engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM categorias"))
        conexao.execute(sa.text("DELETE FROM impressoras"))
        for colunas in range(20, 97):
            conexao.execute(
                sa.text(
                    "INSERT INTO impressoras (nome, colunas, ativa, padrao, tipo_conexao) "
                    "VALUES (:nome, :colunas, 1, 0, 'ARQUIVO')"
                ),
                {"nome": f"I{colunas}", "colunas": colunas},
            )
    command.upgrade(config, REVISAO)

    divergentes = [
        (colunas, bobina)
        for colunas, bobina in _linhas(engine, "SELECT colunas, bobina_mm FROM impressoras")
        if bobina != bobina_mm_das_colunas(colunas)
    ]
    assert divergentes == []


# ----------------------------------------------------------------------
# 3. Atômica
# ----------------------------------------------------------------------


def test_queda_no_preenchimento_nao_deixa_coluna_nenhuma(banco):
    """Um gatilho derruba o `UPDATE` do preenchimento DEPOIS de as colunas
    terem sido acrescentadas. Sem o `BEGIN` da migração, as colunas ficariam no
    arquivo com a `alembic_version` na revisão anterior (medido numa sonda)."""
    from alembic import command

    config, engine = banco
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "CREATE TRIGGER queda BEFORE UPDATE ON impressoras "
                "BEGIN SELECT RAISE(ABORT, 'queda de energia simulada'); END"
            )
        )

    with pytest.raises(Exception, match="queda de energia simulada"):
        command.upgrade(config, REVISAO)
    engine.dispose()

    assert {"bobina_mm", "letra_grossa"} & _colunas(engine) == set()
    assert _versao(engine) == REVISAO_ANTERIOR
    assert len(_linhas(engine, "SELECT id FROM impressoras")) == len(LEGADAS)

    # O boot seguinte, sem a queda, faz tudo do zero.
    with engine.begin() as conexao:
        conexao.execute(sa.text("DROP TRIGGER queda"))
    command.upgrade(config, REVISAO)
    assert _linhas(engine, "SELECT bobina_mm FROM impressoras WHERE id = 1") == [(58,)]


# ----------------------------------------------------------------------
# 4. Coluna posta à mão
# ----------------------------------------------------------------------


def test_coluna_posta_a_mao_nao_derruba_e_a_bobina_e_preenchida_assim_mesmo(banco):
    """Quem destrava um boot acrescentando a coluna à mão deixa todas as linhas
    no default. A migração passa por cima da coluna e preenche a bobina mesmo
    assim: a de 32 colunas não pode reabrir como 80mm."""
    from alembic import command

    config, engine = banco
    with engine.begin() as conexao:
        conexao.execute(sa.text("ALTER TABLE impressoras ADD COLUMN bobina_mm INTEGER NOT NULL DEFAULT 80"))

    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT id, bobina_mm FROM impressoras WHERE id IN (1, 4) ORDER BY id") == [(1, 58), (4, 80)]
    assert "letra_grossa" in _colunas(engine)


# ----------------------------------------------------------------------
# 5. O roteamento
# ----------------------------------------------------------------------


def test_o_vinculo_de_impressao_continua_de_pe(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT id, impressora_id FROM categorias") == [(1, 4)]
    assert _linhas(engine, "SELECT nome FROM impressoras WHERE padrao = 1") == [("Caixa",)]


# ----------------------------------------------------------------------
# 6. Ida e volta
# ----------------------------------------------------------------------


def test_ida_volta_e_ida_de_novo(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)
    with engine.begin() as conexao:
        conexao.execute(sa.text("UPDATE impressoras SET letra_grossa = 1 WHERE id = 4"))

    command.downgrade(config, REVISAO_ANTERIOR)
    assert {"bobina_mm", "letra_grossa"} & _colunas(engine) == set()
    assert "colunas" in _colunas(engine)
    assert _linhas(engine, "SELECT id, colunas FROM impressoras ORDER BY id") == [
        (impressora_id, colunas) for impressora_id, _nome, colunas in LEGADAS
    ]

    command.upgrade(config, REVISAO)
    assert _linhas(engine, "SELECT id, bobina_mm, letra_grossa FROM impressoras WHERE id IN (1, 4) ORDER BY id") == [
        (1, 58, 0),
        (4, 80, 0),
    ]


def test_banco_novo_chega_a_head_com_as_colunas(tmp_path, monkeypatch):
    """Do zero até a head num `upgrade` só, que é o primeiro boot: aqui a
    transação já pode vir aberta por uma revisão anterior, e o `BEGIN` da
    migração não pode tentar abrir uma segunda."""
    from alembic import command

    arquivo = tmp_path / "novo.db"
    config = _config(arquivo, monkeypatch)
    command.upgrade(config, "head")

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    try:
        assert {"colunas", "bobina_mm", "letra_grossa"} <= _colunas(engine)
        assert _versao(engine) == REVISAO
    finally:
        engine.dispose()
