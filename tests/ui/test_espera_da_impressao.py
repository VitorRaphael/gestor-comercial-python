"""A janela não congela enquanto o cupom sai (`Mitigação de Falhas.md`, Fase 3).

`tests/unit/test_fila_impressao.py` prova o lado do service: a conversa com o
cabo roda em outra thread e o que atravessa não tem vínculo com o banco. Aqui é
a outra ponta — a espera que a UI injeta, e as duas propriedades dela que não
podem se perder numa refatoração:

1. a tela continua sendo repintada (senão o Windows desenha "Não Está
   Respondendo" por cima do PDV, e o operador fecha no X no meio da venda);
2. a reentrância é contida — a entrada do operador fica segurada pela bandeira
   `ExcludeUserInputEvents`, e uma espera aninhada para de bombear eventos
   (senão a pilha cresce sem fim e o cupom sai duas vezes).
"""

from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtWidgets import QApplication

from gestor_comercial.ui.widgets.aviso_impressao import aguardar_repintando


def _thread_que_demora(segundos: float) -> threading.Thread:
    thread = threading.Thread(target=lambda: time.sleep(segundos), daemon=True)
    thread.start()
    return thread


def test_a_tela_continua_sendo_repintada_durante_a_espera(qapp):
    """Sem isto a thread principal para de responder ao gerenciador de janelas."""
    pintadas = []
    from PySide6.QtCore import QTimer

    cronometro = QTimer()
    cronometro.setInterval(10)
    cronometro.timeout.connect(lambda: pintadas.append(1))
    cronometro.start()

    aguardar_repintando(_thread_que_demora(0.3), teto_s=2.0)
    cronometro.stop()

    assert pintadas, (
        "nenhum evento do Qt foi processado durante a espera — a janela ficaria "
        "congelada e o Windows a marcaria como 'Não Está Respondendo'"
    )


def test_a_espera_passa_a_bandeira_que_segura_a_entrada_do_operador(qapp, monkeypatch):
    """`ExcludeUserInputEvents` é o que impede o clique de virar 2ª impressão.

    A verificação aqui é a da bandeira, e não a de um clique simulado, por um
    motivo que vale registrar: um evento injetado com `postEvent` **atravessa**
    essa exclusão (foi medido), porque ele entra direto na fila do Qt em vez de
    vir do gerenciador de janelas. A bandeira vale para a entrada de verdade,
    que é a do operador — e essa não tem como ser fabricada num teste offscreen.

    Quem cobre o caso que o `postEvent` representa (evento postado por código
    disparando outra impressão) é o teste de aninhamento abaixo.
    """
    from PySide6.QtCore import QEventLoop

    bandeiras = []
    monkeypatch.setattr(
        QApplication, "processEvents", staticmethod(lambda flags: bandeiras.append(flags))
    )

    aguardar_repintando(_thread_que_demora(0.15), teto_s=2.0)

    assert bandeiras, "a espera não processou evento nenhum"
    assert all(
        flags == QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents for flags in bandeiras
    )


def test_espera_aninhada_para_de_bombear_eventos(qapp):
    """A trava que impede a pilha de reentrância de crescer sem fim.

    Se um evento postado disparar outra impressão no meio de uma espera, caímos
    em `aguardar_repintando` de novo. Da segunda em diante o bombeamento tem que
    ser desligado: a tela já está sendo repintada pela espera de fora, e o que
    não pode é cada nível empilhar mais um `processEvents`.
    """
    from gestor_comercial.ui.widgets import aviso_impressao

    aviso_impressao._esperando = True
    try:
        comeco = time.monotonic()
        aguardar_repintando(_thread_que_demora(0.1), teto_s=2.0)
        gasto = time.monotonic() - comeco
    finally:
        aviso_impressao._esperando = False

    # Voltou (não ficou preso) e a trava foi devolvida como estava.
    assert gasto < 1.0
    assert aviso_impressao._esperando is False


def test_a_trava_e_devolvida_mesmo_se_algo_estourar(qapp, monkeypatch):
    """Trava presa em `True` deixaria o PDV sem repintura pelo resto do turno."""
    from gestor_comercial.ui.widgets import aviso_impressao

    def processar_que_falha(_flags):
        raise RuntimeError("Qt em pânico")

    monkeypatch.setattr(QApplication, "processEvents", staticmethod(processar_que_falha))

    with pytest.raises(RuntimeError):
        aguardar_repintando(_thread_que_demora(0.5), teto_s=2.0)

    assert aviso_impressao._esperando is False


def test_a_espera_respeita_o_teto(qapp):
    """Driver pendurado não pode segurar a tela para sempre."""
    comeco = time.monotonic()
    aguardar_repintando(_thread_que_demora(5.0), teto_s=0.3)
    gasto = time.monotonic() - comeco

    assert gasto < 2.0


def test_a_espera_volta_assim_que_a_impressao_termina(qapp):
    """Não pode ficar esperando o teto inteiro quando o cupom já saiu."""
    comeco = time.monotonic()
    aguardar_repintando(_thread_que_demora(0.05), teto_s=3.0)
    gasto = time.monotonic() - comeco

    assert gasto < 1.0


# ----------------------------------------------------------------------
# O painel da fila na tela de Impressoras
# ----------------------------------------------------------------------


def test_painel_da_fila_fica_escondido_no_dia_normal(todas_as_telas):
    """Seção permanentemente vazia ensina o operador a ignorar aquela área da
    tela — e é justamente ali que a informação urgente aparece."""
    tela = todas_as_telas["Impressoras"]
    assert tela._painel_fila.isVisibleTo(tela) is False
    assert tela._lista_fila.count() == 0


def test_painel_da_fila_aparece_com_o_cupom_que_nao_saiu(
    qapp, uow, auth, driver_que_falha, gerente, caixa_aberto, cardapio
):
    from gestor_comercial.services.impressao_service import ImpressaoService
    from gestor_comercial.ui.views.impressoras_view import ImpressorasView
    from tests.unit.test_impressao_service import (
        nova_categoria_com_produto,
        nova_comanda,
        nova_impressora,
        novo_item,
    )

    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    impressao.imprimir_comanda(comanda.id)

    tela = ImpressorasView(cardapio, impressao)

    assert tela._painel_fila.isVisibleTo(tela) is True
    assert tela._lista_fila.count() == 1
    # O rótulo diz para onde o cupom ia: sem o destino, o operador não sabe qual
    # impressora precisa resolver antes de clicar em Reimprimir.
    assert "Cozinha" in tela._lista_fila.item(0).text()

    tela.deleteLater()


def test_reimprimir_sem_escolher_o_cupom_avisa_em_vez_de_estourar(
    qapp, uow, auth, driver_que_falha, gerente, caixa_aberto, cardapio
):
    from gestor_comercial.services.impressao_service import ImpressaoService
    from gestor_comercial.ui.views.impressoras_view import ImpressorasView
    from tests.unit.test_impressao_service import nova_comanda, nova_impressora

    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    nova_impressora(uow, "Balcão", padrao=True)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    impressao.imprimir_recibo(comanda.id)

    tela = ImpressorasView(cardapio, impressao)
    tela._lista_fila.setCurrentItem(None)
    tela._reimprimir_da_fila()

    assert "Escolha" in tela._label_erro.text()

    tela.deleteLater()


def test_descartar_tira_o_cupom_da_tela(
    qapp, uow, auth, driver_que_falha, gerente, caixa_aberto, cardapio
):
    from gestor_comercial.services.impressao_service import ImpressaoService
    from gestor_comercial.ui.views.impressoras_view import ImpressorasView
    from tests.unit.test_impressao_service import nova_comanda, nova_impressora

    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    nova_impressora(uow, "Balcão", padrao=True)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    impressao.imprimir_recibo(comanda.id)

    tela = ImpressorasView(cardapio, impressao)
    tela._lista_fila.setCurrentRow(0)
    tela._descartar_da_fila()

    assert tela._lista_fila.count() == 0
    assert tela._painel_fila.isVisibleTo(tela) is False

    tela.deleteLater()
