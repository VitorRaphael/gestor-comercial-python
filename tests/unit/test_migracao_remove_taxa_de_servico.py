"""A migração `c5d9e17a24b8`: a taxa de serviço e a comissão saem do banco. §9.26.

O banco da máquina do food truck é a **única cópia** dos dados do pai do Vitor, e
esta migração roda no arranque do `.exe`, antes de qualquer tela aparecer. Aqui
ela não acrescenta colunas: ela **derruba cinco**, e é a única do projeto que
apaga dado de venda — a taxa cobrada em cada conta e a marca do repasse.

O que os testes abaixo cobrem:

1. **as cinco colunas somem** — duas de valor e duas de repasse em `comandas`, e
   o interruptor em `loja_config`;
2. **o dinheiro recebido não é tocado** — `pagamentos` é o que sustenta o
   faturamento, e nenhuma linha de lá muda: uma conta fechada com taxa continua
   com o valor que o cliente pagou;
3. **o movimento `COMISSAO` vira `DESPESA`** — o tipo saiu do enum, e uma linha
   com o texto antigo estouraria ao ser lida; apagá-la seria pior, porque
   aquele dinheiro saiu da gaveta de verdade e o turno passaria a sobrar;
4. **rodar de novo não quebra** — banco que já perdeu as colunas (ou que nunca
   as teve) não pode derrubar o app no boot seguinte;
5. **a ida e a volta funcionam** — o `downgrade` devolve o schema, ainda que
   não devolva o dado, e o `upgrade` seguinte passa de novo;
6. **o banco novo chega à head sem as colunas.**
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial

REVISAO_ANTERIOR = "f6a1d3b78c42"
REVISAO = "c5d9e17a24b8"

COLUNAS_DA_COMANDA = {
    "taxa_servico_percentual",
    "valor_taxa_servico",
    "comissao_paga",
    "comissao_paga_em",
}
# (id, status, valor da taxa) — o turno tem conta paga, conta em conferência e
# conta de balcão sem taxa nenhuma.
COMANDAS = [(1, "FECHADA", "13.15"), (2, "FECHADA", "4.80"), (3, "EM_CONFERENCIA", "0")]


def _config(arquivo: Path, monkeypatch):
    from alembic.config import Config

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    return config


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco na revisão ANTERIOR, com um turno que cobrou taxa e repassou."""
    from alembic import command

    arquivo = tmp_path / "taxa.db"
    config = _config(arquivo, monkeypatch)
    command.upgrade(config, REVISAO_ANTERIOR)

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO caixas (id, status, valor_abertura, aberto_em) "
                "VALUES (1, 'ABERTO', 100, '2026-09-20 17:00:00')"
            )
        )
        for comanda_id, status, taxa in COMANDAS:
            conexao.execute(
                sa.text(
                    "INSERT INTO comandas (id, status, aberta_em, caixa_id, usuario_id, "
                    "valor_desconto, valor_taxa_servico, taxa_servico_percentual, comissao_paga) "
                    "VALUES (:id, :status, '2026-09-20 18:00:00', 1, 1, 0, :taxa, 10, 0)"
                ),
                {"id": comanda_id, "status": status, "taxa": taxa},
            )
        # O que o cliente pagou, com a taxa dentro: é esta linha que sustenta o
        # faturamento do turno, e ela não pode mudar.
        conexao.execute(
            sa.text(
                "INSERT INTO pagamentos (id, forma, valor, valor_quitado, registrado_em, comanda_id) "
                "VALUES (1, 'DINHEIRO', 144.65, 0, '2026-09-20 19:00:00', 1)"
            )
        )
        for movimento_id, tipo, valor, descricao in [
            (1, "COMISSAO", "13.15", "Comissão de Lucas Prado · Mesa 12 · comanda 1"),
            (2, "SANGRIA", "50.00", "Sangria do turno"),
        ]:
            conexao.execute(
                sa.text(
                    "INSERT INTO movimentos_caixa (id, tipo, valor, descricao, registrado_em, "
                    "caixa_id, usuario_id) "
                    "VALUES (:id, :tipo, :valor, :descricao, '2026-09-20 19:05:00', 1, 1)"
                ),
                {"id": movimento_id, "tipo": tipo, "valor": valor, "descricao": descricao},
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


# ----------------------------------------------------------------------
# 1. As cinco colunas somem
# ----------------------------------------------------------------------


def test_as_colunas_da_taxa_e_da_comissao_somem(banco):
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    assert COLUNAS_DA_COMANDA & _colunas(engine, "comandas") == set()
    assert "aceita_taxa_servico" not in _colunas(engine, "loja_config")
    assert _versao(engine) == REVISAO


def test_as_comandas_continuam_todas_la(banco):
    """Derrubar coluna não pode derrubar linha: o histórico de vendas fica."""
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT COUNT(*) FROM comandas") == [(len(COMANDAS),)]
    assert _linhas(engine, "SELECT id, status FROM comandas ORDER BY id") == [
        (comanda_id, status) for comanda_id, status, _taxa in COMANDAS
    ]


# ----------------------------------------------------------------------
# 2. O faturamento não muda
# ----------------------------------------------------------------------


def test_o_dinheiro_recebido_nao_e_tocado(banco):
    """O total faturado sai de `pagamentos`, não da comanda.

    A conta 1 entrou com R$ 144,65 (R$ 131,50 de consumo + os 10% que a loja
    cobrava). Depois desta migração o sistema não sabe mais quanto daquilo foi
    taxa — mas o que entrou na gaveta continua sendo R$ 144,65, e é isso que o
    fechamento daquele turno já apurou.
    """
    from alembic import command

    config, engine = banco
    antes = _linhas(engine, "SELECT id, forma, valor FROM pagamentos ORDER BY id")

    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT id, forma, valor FROM pagamentos ORDER BY id") == antes


# ----------------------------------------------------------------------
# 3. O repasse vira despesa
# ----------------------------------------------------------------------


def test_o_movimento_de_comissao_vira_despesa_com_a_descricao_intacta(banco):
    """`TipoMovimento` não tem mais `COMISSAO`, e ler a linha antiga estouraria.

    `DESPESA` é o tipo que já significa "saiu da gaveta e não é venda", e está
    na mesma `TIPOS_QUE_SAEM_DA_GAVETA` — o saldo esperado do turno dá o mesmo
    número antes e depois. A descrição fica porque é ela que explica a linha
    para quem for conferir aquele turno depois.
    """
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    assert _linhas(engine, "SELECT id, tipo, valor, descricao FROM movimentos_caixa ORDER BY id") == [
        (1, "DESPESA", 13.15, "Comissão de Lucas Prado · Mesa 12 · comanda 1"),
        (2, "SANGRIA", 50.0, "Sangria do turno"),
    ]
    assert _linhas(engine, "SELECT COUNT(*) FROM movimentos_caixa WHERE tipo = 'COMISSAO'") == [(0,)]


def test_nenhum_tipo_fora_do_enum_sobra_no_banco(banco):
    """A varredura que impede o app de abrir com um movimento ilegível."""
    from alembic import command

    from gestor_comercial.domain.enums import TipoMovimento

    config, engine = banco
    command.upgrade(config, REVISAO)

    tipos = {linha[0] for linha in _linhas(engine, "SELECT DISTINCT tipo FROM movimentos_caixa")}
    assert tipos <= {membro.value for membro in TipoMovimento}


# ----------------------------------------------------------------------
# 4. Rodar de novo
# ----------------------------------------------------------------------


def test_upgrade_em_banco_que_ja_perdeu_as_colunas_nao_quebra(banco):
    """A coluna derrubada à mão para destravar um boot não pode derrubar o app."""
    from alembic import command

    config, engine = banco
    with engine.begin() as conexao:
        conexao.execute(sa.text("ALTER TABLE comandas DROP COLUMN comissao_paga_em"))

    command.upgrade(config, REVISAO)

    assert COLUNAS_DA_COMANDA & _colunas(engine, "comandas") == set()
    assert _versao(engine) == REVISAO


# ----------------------------------------------------------------------
# 5. Ida e volta
# ----------------------------------------------------------------------


def test_ida_volta_e_ida_de_novo(banco):
    """A volta devolve o SCHEMA, não o dado — e é isso que o cabeçalho promete.

    Quem despromove a versão no balcão reencontra as colunas com o default de
    origem: toda conta sem taxa e a loja com a cobrança ligada.
    """
    from alembic import command

    config, engine = banco
    command.upgrade(config, REVISAO)

    command.downgrade(config, REVISAO_ANTERIOR)
    assert COLUNAS_DA_COMANDA <= _colunas(engine, "comandas")
    assert "aceita_taxa_servico" in _colunas(engine, "loja_config")
    assert _linhas(engine, "SELECT valor_taxa_servico, comissao_paga FROM comandas ORDER BY id") == [
        (0, 0) for _ in COMANDAS
    ]
    assert _linhas(engine, "SELECT COUNT(*) FROM pagamentos") == [(1,)]

    command.upgrade(config, REVISAO)
    assert COLUNAS_DA_COMANDA & _colunas(engine, "comandas") == set()


# ----------------------------------------------------------------------
# 6. Banco novo
# ----------------------------------------------------------------------


def test_banco_novo_chega_a_head_sem_as_colunas(tmp_path, monkeypatch):
    from alembic import command
    from alembic.script import ScriptDirectory

    arquivo = tmp_path / "novo.db"
    config = _config(arquivo, monkeypatch)
    command.upgrade(config, "head")

    roteiro = ScriptDirectory.from_config(config)
    cabeca = roteiro.get_current_head()
    engine = sa.create_engine(f"sqlite:///{arquivo}")
    try:
        assert COLUNAS_DA_COMANDA & _colunas(engine, "comandas") == set()
        assert "aceita_taxa_servico" not in _colunas(engine, "loja_config")
        assert _versao(engine) == cabeca
        assert REVISAO in {revisao.revision for revisao in roteiro.walk_revisions("base", cabeca)}
    finally:
        engine.dispose()


def test_o_schema_da_migracao_bate_com_o_do_create_all(tmp_path, monkeypatch):
    """O banco da suíte (`create_all`) e o do `.exe` (migrações) têm que ter o
    MESMO desenho de `comandas` — a armadilha que o `server_default` das colunas
    removidas existia para evitar, agora do lado da ausência delas."""
    from alembic import command

    from gestor_comercial.repository.base import Base

    arquivo = tmp_path / "migrado.db"
    config = _config(arquivo, monkeypatch)
    command.upgrade(config, "head")

    engine = sa.create_engine(f"sqlite:///{arquivo}")
    try:
        migrado = _colunas(engine, "comandas")
    finally:
        engine.dispose()

    do_orm = {coluna.name for coluna in Base.metadata.tables["comandas"].columns}
    assert migrado == do_orm
