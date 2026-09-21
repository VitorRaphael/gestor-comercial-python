"""O primeiro boot do `.exe`: criar o banco da semente, e nunca mais.

A provisão é a única escrita do programa que acontece ANTES de existir banco, e
é a única que, errada, apagaria vendas: bastaria confundir "primeira abertura"
com "qualquer abertura". Por isso o caso mais importante daqui é o do banco que
já existe e não pode ser tocado, e o segundo é o da queda no meio.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from gestor_comercial.core import banco_semente
from gestor_comercial.core.banco_semente import Provisionamento, provisionar


@pytest.fixture
def semente(tmp_path) -> Path:
    pasta = tmp_path / "semente"
    (pasta / "thumbnails").mkdir(parents=True)
    (pasta / "banco_seed.db").write_bytes(b"CARDAPIO DO VITOR" * 64)
    for nome in ("a1.jpg", "b2.jpg", "c3.jpg"):
        (pasta / "thumbnails" / nome).write_bytes(nome.encode() * 128)
    return pasta


@pytest.fixture
def banco(tmp_path) -> Path:
    return tmp_path / "AppData" / "GestorComercial_V2" / "gestor_comercial.db"


def _fotos(banco: Path) -> dict[str, bytes]:
    pasta = banco.parent / "uploads" / "thumbnails"
    return {f.name: f.read_bytes() for f in pasta.iterdir()} if pasta.is_dir() else {}


def test_primeira_abertura_cria_o_banco_e_as_fotos(semente, banco):
    resultado = provisionar(banco, semente)

    assert resultado.situacao is Provisionamento.CRIADO_DA_SEMENTE
    assert resultado.fotos_copiadas == 3
    assert banco.read_bytes() == (semente / "banco_seed.db").read_bytes()
    assert _fotos(banco) == {f.name: f.read_bytes() for f in (semente / "thumbnails").iterdir()}
    assert list(banco.parent.rglob("*.tmp")) == [], "temporário de cópia deixado para trás"


def test_banco_existente_nunca_e_lido_nem_sobrescrito(semente, banco):
    banco.parent.mkdir(parents=True)
    banco.write_bytes(b"VENDAS DE UM MES INTEIRO")
    assinatura = banco.stat().st_mtime_ns

    resultado = provisionar(banco, semente)

    assert resultado.situacao is Provisionamento.JA_EXISTIA
    assert banco.read_bytes() == b"VENDAS DE UM MES INTEIRO"
    assert banco.stat().st_mtime_ns == assinatura
    assert _fotos(banco) == {}, "fotos da semente despejadas sobre uma instalação em uso"


def test_abertura_do_dia_a_dia_nao_passa_pela_trava(semente, banco):
    """Com banco, a provisão sai num `stat` e não espera uma janela presa no primeiro boot."""
    banco.parent.mkdir(parents=True)
    banco.write_bytes(b"VENDAS")
    resultados = []

    with banco_semente._trava_exclusiva(banco.parent / banco_semente.ARQUIVO_DA_TRAVA):
        abertura = threading.Thread(target=lambda: resultados.append(provisionar(banco, semente)))
        abertura.start()
        abertura.join(timeout=2)
        assert not abertura.is_alive(), "a abertura normal ficou esperando a trava"

    assert resultados[0].situacao is Provisionamento.JA_EXISTIA


def test_sem_semente_nao_cria_nada(tmp_path, banco):
    resultado = provisionar(banco, tmp_path / "nao_existe")

    assert resultado.situacao is Provisionamento.SEM_SEMENTE
    assert not banco.parent.exists(), "sem semente, quem cria o banco é a migration, como sempre foi"


def test_restos_de_um_banco_apagado_saem_antes_de_a_semente_entrar(semente, banco):
    """O SQLite não confere se o `-wal` pertence ao arquivo ao lado: aplicaria as
    páginas do banco velho sobre a semente."""
    banco.parent.mkdir(parents=True)
    for sufixo in ("-wal", "-shm", "-journal"):
        Path(f"{banco}{sufixo}").write_bytes(b"PAGINAS DE OUTRO BANCO")

    provisionar(banco, semente)

    assert banco.exists()
    assert [s for s in ("-wal", "-shm", "-journal") if Path(f"{banco}{s}").exists()] == []


def test_queda_no_meio_nao_publica_banco_e_a_abertura_seguinte_refaz(semente, banco, monkeypatch):
    """O banco é o ponto de confirmação: sem ele, o boot seguinte começa do zero."""
    original = banco_semente._copiar_duravel
    copias = []

    def cai_na_segunda_foto(origem, destino):
        copias.append(origem.name)
        if len(copias) == 2:
            raise OSError("energia caiu")
        original(origem, destino)

    monkeypatch.setattr(banco_semente, "_copiar_duravel", cai_na_segunda_foto)
    with pytest.raises(OSError):
        provisionar(banco, semente)
    assert not banco.exists(), "banco publicado com as fotos pela metade"

    monkeypatch.setattr(banco_semente, "_copiar_duravel", original)
    resultado = provisionar(banco, semente)

    assert resultado.situacao is Provisionamento.CRIADO_DA_SEMENTE
    assert len(_fotos(banco)) == 3


def test_banco_publicado_por_outra_janela_durante_a_espera_nao_e_sobrescrito(semente, banco):
    """Duplo clique: a segunda instância espera a trava e, ao entrar, confere de novo."""
    banco.parent.mkdir(parents=True)
    resultados = []

    with banco_semente._trava_exclusiva(banco.parent / banco_semente.ARQUIVO_DA_TRAVA):
        segunda = threading.Thread(target=lambda: resultados.append(provisionar(banco, semente)))
        segunda.start()
        time.sleep(0.3)
        assert segunda.is_alive(), "a segunda instância não esperou a trava"
        banco.write_bytes(b"PUBLICADO PELA PRIMEIRA")
    segunda.join(timeout=10)

    assert resultados[0].situacao is Provisionamento.JA_EXISTIA
    assert banco.read_bytes() == b"PUBLICADO PELA PRIMEIRA"


@pytest.mark.skipif(sys.platform != "win32", reason="a espera com teto é a do Windows")
def test_trava_presa_vira_erro_com_mensagem_e_nao_espera_para_sempre(tmp_path):
    trava = tmp_path / ".provisionamento.lock"
    erros = []

    def tentar():
        try:
            with banco_semente._trava_exclusiva(trava, espera_maxima=0.2):
                pass
        except TimeoutError as erro:
            erros.append(erro)

    with banco_semente._trava_exclusiva(trava):
        outra = threading.Thread(target=tentar)
        outra.start()
        outra.join(timeout=10)

    assert len(erros) == 1
    assert "preparando o banco" in str(erros[0])
