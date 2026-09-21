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
