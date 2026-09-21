"""Onde o programa lê e grava — e a garantia de que o `.exe` não conhece o banco antigo.

A máquina do food truck já rodou um `.exe` de testes que gravou em
`~/.gestor_comercial/`. Estes testes trancam as duas metades da promessa do
`core/caminhos.py`: em desenvolvimento nada mudou, e empacotado o programa só
conhece `%APPDATA%\\GestorComercial_V2` — nem a pasta velha, nem a variável de
ambiente que poderia apontar para ela.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import gestor_comercial
from gestor_comercial.core import caminhos, resilience

RAIZ_DO_REPO = Path(gestor_comercial.__file__).resolve().parents[2]


@pytest.fixture
def desenvolvimento(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delenv(caminhos.VARIAVEL_DO_BANCO, raising=False)


@pytest.fixture
def empacotado(tmp_path, monkeypatch):
    """Simula o processo de dentro do `.exe`, com uma variável esquecida apontando para o banco velho."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_MEI123"), raising=False)
    (tmp_path / "Downloads").mkdir()
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Downloads" / "GestorComercial.exe"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv(caminhos.VARIAVEL_DO_BANCO, str(Path.home() / ".gestor_comercial" / "gestor_comercial.db"))
    return tmp_path


def test_desenvolvimento_continua_na_pasta_de_trabalho(desenvolvimento):
    assert caminhos.empacotado() is False
    assert caminhos.pasta_de_dados() == Path.home() / ".gestor_comercial"
    assert caminhos.caminho_do_banco() == Path.home() / ".gestor_comercial" / "gestor_comercial.db"
    assert caminhos.raiz_de_recursos() == RAIZ_DO_REPO
    assert caminhos.recurso("alembic.ini").is_file()


def test_desenvolvimento_respeita_a_variavel_do_banco(desenvolvimento, tmp_path, monkeypatch):
    descartavel = tmp_path / "teste" / "loja.db"
    monkeypatch.setenv(caminhos.VARIAVEL_DO_BANCO, str(descartavel))

    assert caminhos.caminho_do_banco() == descartavel
    assert caminhos.pasta_de_dados() == descartavel.parent


def test_empacotado_usa_so_a_pasta_propria_da_versao(empacotado):
    pasta = empacotado / "AppData" / "Roaming" / "GestorComercial_V2"

    assert caminhos.empacotado() is True
    assert caminhos.pasta_de_dados() == pasta
    assert caminhos.caminho_do_banco() == pasta / "gestor_comercial.db"
    assert resilience.caminho_do_log() == pasta / "logs" / "gestor.log"


def test_empacotado_ignora_a_variavel_que_apontaria_para_o_banco_antigo(empacotado):
    """A variável foi sugerida no DEPLOYMENT.md antigo para fixar o banco na máquina do
    pai. Esquecida no Windows dele, levaria o programa novo direto para o banco velho."""
    assert ".gestor_comercial" not in str(caminhos.caminho_do_banco())
    assert ".gestor_comercial" not in str(caminhos.pasta_de_dados())


def test_empacotado_sem_appdata_cai_no_roaming_do_usuario(empacotado, monkeypatch):
    monkeypatch.delenv("APPDATA")

    assert caminhos.pasta_de_dados() == Path.home() / "AppData" / "Roaming" / "GestorComercial_V2"


@pytest.fixture
def pendrive(empacotado, monkeypatch):
    """A pasta `App_Pendrive`: o `.exe` com o banco ao lado."""
    pasta = empacotado / "E" / "App_Pendrive"
    pasta.mkdir(parents=True)
    (pasta / "gestor_comercial.db").write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(pasta / "GestorComercial.exe"))
    return pasta


def test_exe_sem_banco_ao_lado_nao_e_portatil(empacotado):
    assert caminhos.portatil() is False
    assert caminhos.pasta_de_dados() == empacotado / "AppData" / "Roaming" / "GestorComercial_V2"


def test_exe_com_o_banco_ao_lado_grava_tudo_na_propria_pasta(pendrive):
    assert caminhos.portatil() is True
    assert caminhos.pasta_de_dados() == pendrive
    assert caminhos.caminho_do_banco() == pendrive / "gestor_comercial.db"
    assert resilience.caminho_do_log() == pendrive / "logs" / "gestor.log"


def test_portatil_segue_o_exe_e_nao_a_pasta_atual(pendrive, tmp_path, monkeypatch):
    """Um atalho com "Iniciar em" apontando para outro lugar não troca o banco."""
    outra = tmp_path / "Desktop"
    outra.mkdir()
    (outra / "gestor_comercial.db").write_bytes(b"")
    monkeypatch.chdir(outra)

    assert caminhos.caminho_do_banco() == pendrive / "gestor_comercial.db"


def test_portatil_acompanha_a_pasta_quando_ela_e_copiada(pendrive, tmp_path, monkeypatch):
    """Do pendrive (E:) para o C:: o caminho é lido do `.exe` em execução, nunca gravado."""
    copia = tmp_path / "C" / "GestorComercial"
    copia.mkdir(parents=True)
    (copia / "gestor_comercial.db").write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(copia / "GestorComercial.exe"))

    assert caminhos.caminho_do_banco() == copia / "gestor_comercial.db"


def test_portatil_so_vale_no_exe(pendrive, monkeypatch):
    """Rodando do código-fonte, um banco esquecido ao lado do `python.exe` não muda nada."""
    monkeypatch.delattr(sys, "frozen")
    monkeypatch.delenv(caminhos.VARIAVEL_DO_BANCO)

    assert caminhos.portatil() is False
    assert caminhos.caminho_do_banco() == Path.home() / ".gestor_comercial" / "gestor_comercial.db"


def test_pasta_com_algo_chamado_gestor_comercial_db_que_nao_e_arquivo_nao_e_portatil(empacotado, monkeypatch):
    pasta = empacotado / "Estranha"
    (pasta / "gestor_comercial.db").mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(pasta / "GestorComercial.exe"))

    assert caminhos.portatil() is False


def test_empacotado_le_recursos_da_pasta_de_extracao(empacotado):
    assert caminhos.raiz_de_recursos() == empacotado / "_MEI123"
    assert caminhos.recurso("semente") == empacotado / "_MEI123" / "semente"


def test_nenhum_modulo_monta_a_pasta_de_dados_por_conta_propria():
    """Varredura: quem precisar da pasta de dados pede a `core/caminhos.py`.

    Foram quatro cópias da mesma regra (banco, log, fotos, cupons) antes de ela
    ter lugar próprio; a dos cupons ignorava a variável de ambiente e, no `.exe`,
    teria continuado gravando na pasta do programa anterior.
    """
    fonte = RAIZ_DO_REPO / "src" / "gestor_comercial"
    permitido = fonte / "core" / "caminhos.py"
    reincidentes = [
        str(arquivo.relative_to(fonte))
        for arquivo in fonte.rglob("*.py")
        if arquivo != permitido
        and any(
            trecho in linha
            for linha in arquivo.read_text(encoding="utf-8").splitlines()
            if not linha.lstrip().startswith("#")
            for trecho in ('".gestor_comercial"', "Path.home()", "GESTOR_COMERCIAL_DB\"")
        )
    ]
    assert reincidentes == []
