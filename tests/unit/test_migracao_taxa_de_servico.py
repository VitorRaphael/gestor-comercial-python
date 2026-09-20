"""A migração `e4b8c2a6d913`: a chave da taxa na loja e a taxa em reais na comanda. §9.23.

O banco da máquina do food truck é a **única cópia** dos dados do pai do Vitor, e
esta migração roda no arranque do `.exe`, antes de qualquer tela aparecer. Ela
reescreve comanda que já foi paga — e comanda paga é dinheiro que o fechamento
de caixa já conferiu.

O que os testes abaixo cobrem:

1. **a loja que já existe continua cobrando a taxa** — a linha singleton reabre
   com a chave ligada;
2. **cada comanda que já passou pela conferência ganha o valor da taxa**, pela
   mesma conta do app: itens não cancelados, meio centavo para cima — inclusive
   no subtotal em que a conta em ponto flutuante erraria o centavo;
3. **quem não tinha taxa fica no zero** (aberta, sem taxa, taxa zero);
4. **é atômica** — uma queda no preenchimento não deixa coluna nenhuma para trás;
5. **coluna posta à mão não derruba o boot**, e o valor é preenchido assim mesmo;
6. **a ida e a volta funcionam**, e o banco novo chega à head com as duas colunas.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial
from gestor_comercial.services.comanda_service import valor_da_taxa_de_servico
from gestor_comercial.services.dinheiro import dinheiro

REVISAO_ANTERIOR = "b9d2f5a31c47"
REVISAO = "e4b8c2a6d913"

# (id, status, percentual, itens [(preço, quantidade, cancelado)], taxa esperada)
COMANDAS = [
    # A mesa do mockup, com um item cancelado que NÃO pode entrar na conta.
    (1, "EM_CONFERENCIA", "10", [("65.75", 2, 0), ("30.00", 1, 1)], "13.15"),
    # Paga: é a que o fechamento do dia vai somar.
    (2, "FECHADA", "10", [("99.95", 1, 0)], "10.00"),
    # Meio centavo: 0,005 sobe para 0,01.
    (3, "FECHADA", "10", [("0.05", 1, 0)], "0.01"),
    # Fechada sem taxa, e com taxa zero.
    (4, "FECHADA", None, [("50.00", 1, 0)], "0.00"),
    (5, "FECHADA", "0", [("50.00", 1, 0)], "0.00"),
    # Aberta: ainda não tem taxa.
    (6, "ABERTA", None, [("20.00", 3, 0)], "0.00"),
]


def _config(arquivo: Path, monkeypatch):
    from alembic.config import Config

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    return config


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco na revisão ANTERIOR com a loja, um turno e as seis comandas."""
    from alembic import command

    arquivo = tmp_path / "taxa.db"
    config = _config(arquivo, monkeypatch)
    command.upgrade(config, REVISAO_ANTERIOR)

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO loja_config (id, senha_master_hash, senha_master_salt, "
                "senha_operacional_hash, senha_operacional_salt, senha_login_hash, "
                "senha_login_salt, cpf_dono_definido) VALUES (1, 'h', 's', 'h', 's', 'h', 's', 0)"
            )
        )
        conexao.execute(
            sa.text(
                "INSERT INTO caixas (id, status, valor_abertura, aberto_em) "
                "VALUES (1, 'ABERTO', 100, '2026-09-18 17:00:00')"
            )
        )
        conexao.execute(sa.text("INSERT INTO categorias (id, nome, ativo, arquivado) VALUES (1, 'Lanches', 1, 0)"))
        conexao.execute(
            sa.text(
                "INSERT INTO produtos (id, nome, preco, custo, ativo, is_combo, categoria_id, arquivado) "
                "VALUES (1, 'Lanche', 10, 0, 1, 0, 1, 0)"
            )
        )
        for comanda_id, status, percentual, itens, _esperado in COMANDAS:
            conexao.execute(
                sa.text(
                    "INSERT INTO comandas (id, status, aberta_em, caixa_id, usuario_id, "
                    "valor_desconto, taxa_servico_percentual) "
                    "VALUES (:id, :status, '2026-09-18 18:00:00', 1, 1, 0, :percentual)"
                ),
                {"id": comanda_id, "status": status, "percentual": percentual},
            )
            for preco, quantidade, cancelado in itens:
                conexao.execute(
                    sa.text(
                        "INSERT INTO itens_comanda (comanda_id, produto_id, quantidade, "
                        "preco_unit_congelado, cancelado) VALUES (:comanda, 1, :qtd, :preco, :cancelado)"
                    ),
                    {"comanda": comanda_id, "qtd": quantidade, "preco": preco, "cancelado": cancelado},
                )
    yield config, engine
    engine.dispose()


def _colunas(engine, tabela: str) -> set[str]:
    return {coluna["name"] for coluna in sa.inspect(engine).get_columns(tabela)}


def _linhas(engine, sql: str) -> list[tuple]:
    with engine.begin() as conexao:
        return [tuple(linha) for linha in conexao.execute(sa.text(sql))]


def _versao(engine) -> str:
    return _linhas(engine, "SELECT version_num FROM alembic_version")[0][0]


def _taxas(engine) -> dict[int, Decimal]:
    """O valor gravado de cada comanda, lido como o app lê: `str` antes do
    `Decimal` (o SQLite devolve `NUMERIC` como `float`)."""
    return {
        comanda_id: dinheiro(str(valor))
        for comanda_id, valor in _linhas(engine, "SELECT id, valor_taxa_servico FROM comandas ORDER BY id")
    }


ESPERADO = {comanda_id: Decimal(esperado) for comanda_id, *_resto, esperado in COMANDAS}


# ----------------------------------------------------------------------
# 1. A loja continua cobrando
# ----------------------------------------------------------------------


def test_a_loja_que_ja_existe_continua_cobrando_a_taxa(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT aceita_taxa_servico FROM loja_config") == [(1,)]
    assert _versao(engine) == REVISAO


# ----------------------------------------------------------------------
# 2 e 3. O valor de cada comanda
# ----------------------------------------------------------------------


def test_cada_comanda_ganha_a_taxa_que_o_app_cobraria(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    assert _taxas(engine) == ESPERADO


def test_a_conta_da_migracao_e_a_conta_do_app(banco):
    """A regra está COPIADA na migração (uma migração faz amanhã o que fez
    hoje). Esta trava confere que a cópia e o original dão o mesmo centavo em
    cada comanda do cenário."""
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    for comanda_id, _status, percentual, itens, _esperado in COMANDAS:
        subtotal = dinheiro(
            sum((dinheiro(preco) * quantidade for preco, quantidade, cancelado in itens if not cancelado), Decimal(0))
        )
        do_app = valor_da_taxa_de_servico(subtotal, None if percentual is None else Decimal(percentual))
        assert _taxas(engine)[comanda_id] == do_app, f"comanda {comanda_id}"


def test_as_colunas_novas_sao_not_null_com_default(banco):
    """Comanda e loja inseridas por fora do ORM nascem sem taxa e cobrando."""
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO comandas (id, status, aberta_em, caixa_id, usuario_id, valor_desconto) "
                "VALUES (99, 'ABERTA', '2026-09-19 10:00:00', 1, 1, 0)"
            )
        )

    comandas = {c["name"]: c for c in sa.inspect(engine).get_columns("comandas")}
    loja = {c["name"]: c for c in sa.inspect(engine).get_columns("loja_config")}
    assert comandas["valor_taxa_servico"]["nullable"] is False
    assert loja["aceita_taxa_servico"]["nullable"] is False
    assert _taxas(engine)[99] == Decimal("0")


# ----------------------------------------------------------------------
# 4. Atômica
# ----------------------------------------------------------------------


def test_queda_no_preenchimento_nao_deixa_coluna_nenhuma(banco):
    """Um gatilho derruba o `UPDATE` da taxa DEPOIS de as duas colunas terem
    sido acrescentadas. Sem o `BEGIN` da migração, as colunas ficariam no
    arquivo com a `alembic_version` na revisão anterior."""
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

    assert "valor_taxa_servico" not in _colunas(engine, "comandas")
    assert "aceita_taxa_servico" not in _colunas(engine, "loja_config")
    assert _versao(engine) == REVISAO_ANTERIOR

    # O boot seguinte, sem a queda, faz tudo do zero.
    with engine.begin() as conexao:
        conexao.execute(sa.text("DROP TRIGGER queda"))
    command.upgrade(config, REVISAO)
    assert _taxas(engine) == ESPERADO


# ----------------------------------------------------------------------
# 5. Coluna posta à mão
# ----------------------------------------------------------------------


def test_coluna_posta_a_mao_nao_derruba_e_a_taxa_e_preenchida_assim_mesmo(banco):
    """Quem destrava um boot acrescentando a coluna à mão deixa toda comanda no
    zero do default: a migração passa por cima da coluna e preenche mesmo assim,
    senão o fechamento do dia perderia a taxa das contas antigas."""
    from alembic import command

    config, engine = banco
    with engine.begin() as conexao:
        conexao.execute(
            sa.text("ALTER TABLE comandas ADD COLUMN valor_taxa_servico NUMERIC(10, 2) NOT NULL DEFAULT 0")
        )

    command.upgrade(config, REVISAO)

    assert _taxas(engine) == ESPERADO
    assert "aceita_taxa_servico" in _colunas(engine, "loja_config")


# ----------------------------------------------------------------------
# 6. Ida e volta
# ----------------------------------------------------------------------


def test_ida_volta_e_ida_de_novo(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)
    with engine.begin() as conexao:
        conexao.execute(sa.text("UPDATE loja_config SET aceita_taxa_servico = 0"))

    command.downgrade(config, REVISAO_ANTERIOR)
    assert "valor_taxa_servico" not in _colunas(engine, "comandas")
    assert "aceita_taxa_servico" not in _colunas(engine, "loja_config")
    assert _linhas(engine, "SELECT id, taxa_servico_percentual FROM comandas WHERE id = 1") == [(1, 10)]

    command.upgrade(config, REVISAO)
    assert _taxas(engine) == ESPERADO
    # A escolha de desligar não sobrevive à volta — está escrito na migração.
    assert _linhas(engine, "SELECT aceita_taxa_servico FROM loja_config") == [(1,)]


def test_banco_novo_chega_a_head_com_as_duas_colunas(tmp_path, monkeypatch):
    """Do zero até a head num `upgrade` só, que é o primeiro boot: aqui a
    transação já pode vir aberta por uma revisão anterior, e o `BEGIN` da
    migração não pode tentar abrir uma segunda."""
    from alembic import command
    from alembic.script import ScriptDirectory

    arquivo = tmp_path / "novo.db"
    config = _config(arquivo, monkeypatch)
    command.upgrade(config, "head")

    roteiro = ScriptDirectory.from_config(config)
    cabeca = roteiro.get_current_head()
    engine = sa.create_engine(f"sqlite:///{arquivo}")
    try:
        assert "valor_taxa_servico" in _colunas(engine, "comandas")
        assert "aceita_taxa_servico" in _colunas(engine, "loja_config")
        assert _versao(engine) == cabeca
        assert REVISAO in {revisao.revision for revisao in roteiro.walk_revisions("base", cabeca)}
    finally:
        engine.dispose()
