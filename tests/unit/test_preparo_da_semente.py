"""A semente que o build embute: o cardápio inteiro, só o cardápio, e nada de sobra.

O banco de trabalho roda em WAL, e o defeito que abriu este módulo era
silencioso: medido no banco real do Vitor, uma cópia só do `.db` embutiria 182
produtos em vez de 188, 169 fotos em vez de 177 e 8 itens de combo em vez de
29 — as edições mais recentes moravam no `-wal`. Nenhum erro, nenhum aviso.

Os bancos daqui são criados pelas migrations de verdade, até a última revisão:
um schema escrito à mão no teste deixaria de acompanhar o do programa.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import gestor_comercial
from gestor_comercial.core.banco_semente import Provisionamento, provisionar
from gestor_comercial.repository.preparo_da_semente import SementeRecusada, preparar_semente

RAIZ = Path(gestor_comercial.__file__).resolve().parents[2]


def _config(arquivo: Path):
    from alembic.config import Config

    config = Config(str(RAIZ / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    return config


@pytest.fixture(scope="module")
def banco_migrado(tmp_path_factory) -> bytes:
    """Um banco vazio na última revisão, migrado uma vez para o módulo inteiro."""
    from alembic import command

    arquivo = tmp_path_factory.mktemp("molde") / "molde.db"
    command.upgrade(_config(arquivo), "head")
    with closing(sqlite3.connect(arquivo)) as conexao:
        conexao.execute("PRAGMA journal_mode=DELETE")
    return arquivo.read_bytes()


@pytest.fixture
def trabalho(tmp_path, banco_migrado) -> Path:
    """O banco de trabalho: em WAL, com um produto com foto e uma foto que ninguém usa."""
    banco = tmp_path / "trabalho" / "gestor_comercial.db"
    fotos = banco.parent / "uploads" / "thumbnails"
    fotos.mkdir(parents=True)
    banco.write_bytes(banco_migrado)
    with closing(sqlite3.connect(banco)) as conexao:
        conexao.execute("PRAGMA journal_mode=WAL")
        conexao.execute("INSERT INTO categorias (id, nome, ativo) VALUES (1, 'Lanches', 1)")
        _inserir_produto(conexao, 1, "X-Tudo", "xtudo.jpg")
        conexao.commit()
    (fotos / "xtudo.jpg").write_bytes(b"JPEG DO X-TUDO")
    (fotos / "trocada.jpg").write_bytes(b"FOTO ANTIGA QUE O GERENTE TROCOU")
    return banco


def _inserir_produto(conexao: sqlite3.Connection, produto_id: int, nome: str, foto: str | None) -> None:
    conexao.execute(
        "INSERT INTO produtos (id, nome, preco, custo, ativo, is_combo, categoria_id, imagem_path) "
        "VALUES (?, ?, 30, 12, 1, 0, 1, ?)",
        (produto_id, nome, foto),
    )


def _nomes(banco: Path) -> list[str]:
    with closing(sqlite3.connect(banco)) as conexao:
        return [nome for (nome,) in conexao.execute("SELECT nome FROM produtos ORDER BY id")]


def _hash(caminho: Path) -> str:
    # Ausente conta como vazio: abrir um banco em WAL, mesmo só para leitura, faz
    # o SQLite criar um `-wal` de 0 bytes ao lado. O que não pode mudar é conteúdo.
    return hashlib.sha256(caminho.read_bytes() if caminho.exists() else b"").hexdigest()


def test_semente_leva_o_que_so_esta_no_wal(trabalho, tmp_path):
    escritor = sqlite3.connect(trabalho)
    try:
        escritor.execute("PRAGMA wal_autocheckpoint=0")
        _inserir_produto(escritor, 2, "Podrão da Casa", None)
        escritor.commit()
        assert Path(f"{trabalho}-wal").stat().st_size > 0
        (tmp_path / "copia.db").write_bytes(trabalho.read_bytes())
        assert "Podrão da Casa" not in _nomes(tmp_path / "copia.db"), "o cenário não reproduz o -wal pendente"

        relatorio = preparar_semente(trabalho, tmp_path / "semente")
    finally:
        escritor.close()

    assert _nomes(relatorio.banco) == ["X-Tudo", "Podrão da Casa"]


def test_semente_sai_num_arquivo_so_e_integra(trabalho, tmp_path):
    relatorio = preparar_semente(trabalho, tmp_path / "semente")

    with closing(sqlite3.connect(relatorio.banco)) as conexao:
        assert conexao.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert not Path(f"{relatorio.banco}-wal").exists()
    assert relatorio.produtos == 1 and relatorio.categorias == 1


def test_banco_de_trabalho_sai_do_build_como_entrou(trabalho, tmp_path):
    antes = {s: _hash(Path(f"{trabalho}{s}")) for s in ("", "-wal")}

    preparar_semente(trabalho, tmp_path / "semente", migrar=lambda copia: None)

    assert {s: _hash(Path(f"{trabalho}{s}")) for s in ("", "-wal")} == antes


def test_migracao_roda_na_copia_e_nunca_no_banco_de_trabalho(trabalho, tmp_path):
    migrados = []

    relatorio = preparar_semente(trabalho, tmp_path / "semente", migrar=migrados.append)

    assert migrados == [relatorio.banco]
    assert relatorio.banco != trabalho


def test_so_entram_as_fotos_que_algum_produto_usa(trabalho, tmp_path):
    relatorio = preparar_semente(trabalho, tmp_path / "semente")

    assert sorted(f.name for f in (tmp_path / "semente" / "thumbnails").iterdir()) == ["xtudo.jpg"]
    assert (relatorio.fotos, relatorio.fotos_sem_produto_ignoradas) == (1, 1)


def test_sobra_de_build_anterior_nao_entra_na_semente(trabalho, tmp_path):
    destino = tmp_path / "semente"
    (destino / "thumbnails").mkdir(parents=True)
    (destino / "thumbnails" / "de_outro_build.jpg").write_bytes(b"VELHA")

    preparar_semente(trabalho, destino)

    assert not (destino / "thumbnails" / "de_outro_build.jpg").exists()


def test_venda_gravada_no_banco_de_trabalho_recusa_a_semente(trabalho, tmp_path):
    """Um turno de teste deixado aberto faria o programa do pai nascer com caixa aberto."""
    with closing(sqlite3.connect(trabalho)) as conexao:
        conexao.execute(
            "INSERT INTO caixas (status, valor_abertura, aberto_em) VALUES ('ABERTO', 50, '2026-09-16 08:00:00')"
        )
        conexao.commit()
    destino = tmp_path / "semente"

    with pytest.raises(SementeRecusada, match=r"caixas: 1"):
        preparar_semente(trabalho, destino)

    assert not destino.exists(), "semente pela metade deixada para o próximo build empacotar"
    with closing(sqlite3.connect(trabalho)) as conexao:
        assert conexao.execute("SELECT COUNT(*) FROM caixas").fetchone()[0] == 1, "o build apagou dado de venda"


def test_foto_de_produto_faltando_recusa_a_semente(trabalho, tmp_path):
    (trabalho.parent / "uploads" / "thumbnails" / "xtudo.jpg").unlink()
    destino = tmp_path / "semente"

    with pytest.raises(SementeRecusada, match=r"xtudo\.jpg"):
        preparar_semente(trabalho, destino)

    assert not destino.exists()


def test_banco_de_origem_inexistente_recusa(tmp_path):
    with pytest.raises(SementeRecusada, match="não encontrado"):
        preparar_semente(tmp_path / "nao_existe.db", tmp_path / "semente")


def test_ida_e_volta_do_build_ao_primeiro_boot(trabalho, tmp_path):
    """O leiaute que o build grava é o que o boot lê: produto e foto chegam juntos."""
    preparar_semente(trabalho, tmp_path / "semente")
    producao = tmp_path / "AppData" / "GestorComercial_V2" / "gestor_comercial.db"

    resultado = provisionar(producao, tmp_path / "semente")

    assert resultado.situacao is Provisionamento.CRIADO_DA_SEMENTE
    assert _nomes(producao) == ["X-Tudo"]
    assert (producao.parent / "uploads" / "thumbnails" / "xtudo.jpg").read_bytes() == b"JPEG DO X-TUDO"
