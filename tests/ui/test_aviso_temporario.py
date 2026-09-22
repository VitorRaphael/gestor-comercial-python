"""Regra global: todo aviso da interface expira em exatamente 3 segundos."""

from __future__ import annotations

import time

from PySide6.QtCore import QCoreApplication

from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao
from gestor_comercial.ui.widgets.aviso_temporario import TEMPO_DE_VIDA_MS, AvisoTemporario


def _esperar(ms: int) -> None:
    limite = time.monotonic() + ms / 1000
    while time.monotonic() < limite:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def test_tempo_de_vida_e_3_segundos():
    assert TEMPO_DE_VIDA_MS == 3000


def test_aviso_some_sozinho_depois_do_tempo_de_vida(qapp):
    aviso = AvisoTemporario()
    aviso._timer.setInterval(60)  # mesma mecânica, sem o teste levar 3 s

    aviso.setText("Pedido enviado para a produção com sucesso!")
    assert aviso.text()
    _esperar(120)

    assert aviso.text() == ""
    assert aviso.property("tom") == ""


def test_aviso_novo_reinicia_a_contagem(qapp):
    aviso = AvisoTemporario()
    aviso._timer.setInterval(100)

    aviso.setText("primeiro")
    _esperar(70)
    aviso.setText("segundo")
    _esperar(70)  # 140 ms desde o primeiro: sem o reset já teria sumido

    assert aviso.text() == "segundo"
    _esperar(60)
    assert aviso.text() == ""


def test_limpar_desarma_o_timer(qapp):
    aviso = AvisoTemporario()
    aviso.setText("algo")
    aviso.setText("")
    assert not aviso._timer.isActive()


def test_aviso_de_impressao_herda_a_regra(qapp):
    aviso = AvisoDeImpressao()
    aviso.mostrar_falha("Recibo não impresso: sem papel")
    assert aviso._timer.isActive()
    assert aviso._timer.interval() == TEMPO_DE_VIDA_MS
