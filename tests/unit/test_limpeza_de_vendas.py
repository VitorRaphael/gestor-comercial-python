"""A limpeza de entrega: sai toda venda de teste, fica todo o cadastro, e a numeração volta ao 1.

Os bancos daqui são criados pelas migrations de verdade, até a última revisão,
como os do preparo da semente: um schema escrito à mão deixaria de acompanhar
o do programa — e uma tabela nova de venda passaria despercebida.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

import gestor_comercial
from gestor_comercial.repository.limpeza_de_vendas import LimpezaRecusada, contar_movimento, limpar_vendas
from gestor_comercial.repository.preparo_da_semente import TABELAS_DE_MOVIMENTO, preparar_semente

RAIZ = Path(gestor_comercial.__file__).resolve().parents[2]
CADASTRO = ("categorias", "subcategorias", "produtos", "combo_itens", "mesas", "funcionarios", "usuarios",
            "loja_config", "impressoras", "preferencias")


@pytest.fixture(scope="module")
def banco_migrado(tmp_path_factory) -> bytes:
    from alembic import command
    from alembic.config import Config

    arquivo = tmp_path_factory.mktemp("molde") / "molde.db"
    config = Config(str(RAIZ / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    command.upgrade(config, "head")
    with closing(sqlite3.connect(arquivo)) as conexao:
        conexao.execute("PRAGMA journal_mode=DELETE")
    return arquivo.read_bytes()


@pytest.fixture
def banco(tmp_path, banco_migrado) -> Path:
    """Um dia de teste na tela: cardápio montado, e um caixa com venda, sangria, consumo e fila de impressão."""
    arquivo = tmp_path / "gestor_comercial.db"
    arquivo.write_bytes(banco_migrado)
    with closing(sqlite3.connect(arquivo)) as conexao:
        conexao.execute("PRAGMA journal_mode=WAL")
        conexao.executescript(
            """
            INSERT INTO categorias (id, nome, ativo) VALUES (1, 'Lanches', 1);
            INSERT INTO produtos (id, nome, preco, custo, ativo, is_combo, categoria_id) VALUES (1, 'X-Tudo', 30, 12, 1, 0, 1);
            INSERT INTO mesas (id, numero, status) VALUES (1, 1, 'OCUPADA'), (2, 2, 'LIVRE');
            INSERT INTO usuarios (id, nome, perfil, ativo) VALUES (7, 'Caixa', 'GERENTE', 1);
            INSERT INTO funcionarios (id, nome, ativo, saldo_devedor) VALUES (3, 'Zé', 1, 18.50), (4, 'Ana', 1, 0);
            INSERT INTO impressoras (id, nome, tipo_conexao, colunas, ativa, padrao) VALUES (1, 'Balcão', 'ARQUIVO', 48, 1, 1);
            INSERT INTO preferencias (chave, valor) VALUES ('tema', 'escuro');
            INSERT INTO caixas (id, status, valor_abertura, aberto_em, aberto_por_id) VALUES (40, 'ABERTO', 100, '2026-09-20 17:00', 7);
            INSERT INTO comandas (id, status, aberta_em, mesa_id, caixa_id, usuario_id) VALUES (90, 'ABERTA', '2026-09-20 18:00', 1, 40, 7);
            INSERT INTO itens_comanda (id, quantidade, preco_unit_congelado, cancelado, comanda_id, produto_id) VALUES (300, 2, 30, 0, 90, 1);
            INSERT INTO pagamentos (id, forma, valor, registrado_em, comanda_id, valor_quitado, funcionario_consumo_id) VALUES (55, 'CONSUMO_INTERNO', 18.50, '2026-09-20 19:00', 90, 18.50, 3);
            INSERT INTO consumo_sessao_assinaturas (id, id_funcionario, id_sessao, data_hora, valor_total_sessao, traco_json, id_pagamento) VALUES (2, 3, 'a1b2', '2026-09-20 19:00', 18.50, '{}', 55);
            INSERT INTO movimentos_caixa (id, tipo, valor, registrado_em, caixa_id, usuario_id) VALUES (12, 'SANGRIA', 50, '2026-09-20 20:00', 40, 7);
            INSERT INTO quitacoes_consumo (id, valor_quitado, quitado_em, funcionario_id, autorizado_por_id) VALUES (5, 10, '2026-09-20 21:00', 3, 7);
            INSERT INTO fila_impressao_pendente (id, impressora_id, documento, descricao, criado_em, tentativas) VALUES (8, 1, 'x', 'Comanda', '2026-09-20 18:01', 1);
            """
        )
    return arquivo


def _linhas(arquivo: Path, tabela: str) -> list[tuple]:
    with closing(sqlite3.connect(arquivo)) as conexao:
        return conexao.execute(f'SELECT * FROM "{tabela}" ORDER BY 1').fetchall()


def test_apaga_toda_tabela_de_venda(banco):
    relatorio = limpar_vendas(banco)

    assert contar_movimento(banco) == {tabela: 0 for tabela in TABELAS_DE_MOVIMENTO}
    assert relatorio.apagadas == {
        "fila_impressao_pendente": 1,
        "quitacoes_consumo": 1,
        "movimentos_caixa": 1,
        "consumo_sessao_assinaturas": 1,
        "pagamentos": 1,
        "itens_comanda": 1,
        "comandas": 1,
        "caixas": 1,
    }


def test_cadastro_sai_exatamente_como_entrou(banco):
    antes = {tabela: _linhas(banco, tabela) for tabela in CADASTRO if tabela not in ("mesas", "funcionarios")}

    limpar_vendas(banco)

    assert {tabela: _linhas(banco, tabela) for tabela in antes} == antes
    assert antes["produtos"] and antes["preferencias"] and antes["impressoras"]


def test_saldo_de_consumo_e_mesa_ocupada_voltam_ao_zero(banco):
    relatorio = limpar_vendas(banco)

    with closing(sqlite3.connect(banco)) as conexao:
        assert conexao.execute("SELECT id, nome, saldo_devedor FROM funcionarios ORDER BY id").fetchall() == [
            (3, "Zé", 0),
            (4, "Ana", 0),
        ]
        assert conexao.execute("SELECT numero, status FROM mesas ORDER BY numero").fetchall() == [
            (1, "LIVRE"),
            (2, "LIVRE"),
        ]
    assert relatorio.funcionarios_com_saldo_zerado == 1
    assert relatorio.mesas_liberadas == 1


def test_primeira_venda_depois_da_limpeza_e_a_numero_1(banco):
    limpar_vendas(banco)

    with closing(sqlite3.connect(banco)) as conexao:
        conexao.execute("INSERT INTO caixas (status, valor_abertura, aberto_em) VALUES ('ABERTO', 0, '2026-09-22 17:00')")
        conexao.execute(
            "INSERT INTO comandas (status, aberta_em, caixa_id, usuario_id) VALUES ('ABERTA', '2026-09-22 18:00', 1, 7)"
        )
        assert conexao.execute("SELECT id FROM caixas").fetchall() == [(1,)]
        assert conexao.execute("SELECT id FROM comandas").fetchall() == [(1,)]


def test_numeracao_volta_ao_1_mesmo_com_autoincrement(tmp_path):
    """Nenhuma tabela usa AUTOINCREMENT hoje; se uma migration ligar, o contador também zera."""
    arquivo = tmp_path / "gestor_comercial.db"
    with closing(sqlite3.connect(arquivo)) as conexao:
        conexao.executescript(
            """
            CREATE TABLE caixas (id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT);
            CREATE TABLE funcionarios (id INTEGER PRIMARY KEY, saldo_devedor NUMERIC);
            CREATE TABLE mesas (id INTEGER PRIMARY KEY, status TEXT);
            INSERT INTO caixas (id, status) VALUES (41, 'FECHADO');
            """
        )

    limpar_vendas(arquivo)

    with closing(sqlite3.connect(arquivo)) as conexao:
        conexao.execute("INSERT INTO caixas (status) VALUES ('ABERTO')")
        assert conexao.execute("SELECT id FROM caixas").fetchall() == [(1,)]


def test_guarda_uma_copia_do_banco_de_antes(banco):
    relatorio = limpar_vendas(banco, agora=datetime(2026, 9, 21, 22, 5, 9))

    assert relatorio.copia_de_seguranca == banco.with_name("gestor_comercial.db.antes-da-limpeza-20260921-220509")
    assert _linhas(relatorio.copia_de_seguranca, "comandas")[0][0] == 90
    assert _linhas(relatorio.copia_de_seguranca, "pagamentos")[0][0] == 55


def test_banco_continua_em_wal_e_integro(banco):
    limpar_vendas(banco)

    with closing(sqlite3.connect(banco)) as conexao:
        assert conexao.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conexao.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_recusa_com_o_programa_aberto_e_nao_apaga_nada(banco):
    programa = sqlite3.connect(banco)
    try:
        programa.execute("SELECT COUNT(*) FROM produtos").fetchone()

        with pytest.raises(LimpezaRecusada, match="programa parece estar aberto"):
            limpar_vendas(banco)
    finally:
        programa.close()

    assert contar_movimento(banco)["comandas"] == 1
    assert not list(banco.parent.glob("*.antes-da-limpeza-*"))


def test_venda_apontada_por_cadastro_desfaz_a_limpeza_inteira(banco):
    """Chave estrangeira ligada: se o cadastro apontar para uma venda, nada sai pela metade."""
    with closing(sqlite3.connect(banco)) as conexao:
        conexao.executescript(
            """
            CREATE TABLE marcador (id INTEGER PRIMARY KEY, comanda_id INTEGER REFERENCES comandas (id));
            INSERT INTO marcador (id, comanda_id) VALUES (1, 90);
            """
        )

    with pytest.raises(sqlite3.IntegrityError):
        limpar_vendas(banco)

    assert contar_movimento(banco) == {tabela: 1 for tabela in TABELAS_DE_MOVIMENTO}


def test_banco_inexistente_e_recusado(tmp_path):
    with pytest.raises(LimpezaRecusada, match="não encontrado"):
        limpar_vendas(tmp_path / "nao_existe.db")
    assert list(tmp_path.iterdir()) == []


def test_banco_limpo_vira_semente_aceita(banco, tmp_path):
    """A outra ponta: o build recusa semente com venda; depois da limpeza, aceita."""
    limpar_vendas(banco)

    relatorio = preparar_semente(banco, tmp_path / "semente")

    assert relatorio.produtos == 1 and relatorio.mesas == 2
