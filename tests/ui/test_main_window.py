"""A janela do app monta, e toda navegação leva a uma tela que existe. Ver §3.11.

A `MainWindow` não era montada por nenhum teste. É a peça que compõe todas as
outras — instancia as telas, empilha no `QStackedWidget` e mapeia rótulo →
página —, e um erro aqui não aparece em teste de tela nenhuma: aparece no boot,
na frente do pai do Vitor.

A Fase 5 tirou a `EstoqueView` daqui (§3.11: tela instanciada no boot, empilhada
e registrada na navegação, mas sem nenhum caminho de usuário até ela, porque a
Central de Loja nunca renderizou um card "Estoque"). Uma remoção assim mexe em
quatro lugares do mesmo arquivo; esquecer um deles deixa um `AttributeError`
esperando o clique. Daí estes testes.

`test_todo_destino_da_central_de_loja_tem_card` é o que fecha o §3.11 de vez:
ele compara a lista de destinos com os cards de fato desenhados, e reprova tanto
a tela fantasma (destino sem card) quanto o card quebrado (card sem destino).
"""

from __future__ import annotations

import pytest

from gestor_comercial.ui.main_window import _MODULOS_HUB, MainWindow
from gestor_comercial.ui.views.loja_hub_view import _SECAO_CATALOGO, _SECAO_EQUIPE


@pytest.fixture
def janela(qapp, auth, comandas, cardapio, caixas_service, pagamentos, impressao, funcionarios):
    return MainWindow(
        auth, comandas, cardapio, caixas_service, pagamentos, impressao, funcionarios
    )


def test_a_janela_monta(janela):
    assert janela._paginas.count() > 0


def test_todo_destino_da_navegacao_aponta_para_uma_pagina_empilhada(janela):
    """O mapa `rótulo -> (página, recarregar)` e o `QStackedWidget` têm que
    contar a mesma história. Página fora da pilha nunca aparece; o clique
    simplesmente não faz nada."""
    orfaos = [
        rotulo
        for rotulo, fabrica in janela._destinos_nav.items()
        if janela._paginas.indexOf(fabrica()[0]) < 0
    ]

    assert not orfaos, f"destinos que apontam para fora do QStackedWidget: {orfaos}"


def test_toda_pagina_empilhada_e_alcancavel(janela):
    """O outro lado — o defeito do §3.11. Tela montada no boot, carregada na
    memória e no `.exe`, sem nenhum caminho de usuário até ela.

    A Comanda é a exceção legítima: chega-se nela por um cartão de mesa, não
    por um item de navegação.
    """
    alcancaveis = {id(fabrica()[0]) for fabrica in janela._destinos_nav.values()}
    alcancaveis.add(id(janela._comanda_view))

    fantasmas = [
        janela._paginas.widget(indice).__class__.__name__
        for indice in range(janela._paginas.count())
        if id(janela._paginas.widget(indice)) not in alcancaveis
    ]

    assert not fantasmas, f"telas montadas no boot sem caminho até elas: {fantasmas}"


def test_todo_modulo_do_hub_tem_card_na_central_de_loja():
    """`_MODULOS_HUB` decide quem mostra a barra "← Central de Loja"; os cards
    decidem no que dá para clicar. Um item só num dos dois é o §3.11 de volta."""
    cards = {rotulo for rotulo, _sub, _glifo in _SECAO_CATALOGO + _SECAO_EQUIPE}

    assert cards == _MODULOS_HUB, (
        f"sem card: {sorted(_MODULOS_HUB - cards)} | "
        f"card sem módulo: {sorted(cards - _MODULOS_HUB)}"
    )


def test_todo_card_da_central_de_loja_navega_para_algum_lugar(janela):
    """Fecha o triângulo: card -> destino -> página empilhada."""
    cards = {rotulo for rotulo, _sub, _glifo in _SECAO_CATALOGO + _SECAO_EQUIPE}

    sem_destino = sorted(cards - set(janela._destinos_nav))

    assert not sem_destino, f"cards da Central de Loja que não levam a lugar nenhum: {sem_destino}"
