"""Venda sem mesa tem uma porta só: "+ Pedido Balcão".

Até 2026-09-22 o cabeçalho de Mesas tinha dois botões ("Balcão" e
"+ Nova comanda") ligados ao mesmo `_abrir_balcao`. Dois nomes para uma ação
só fazem o operador parar e pensar qual é o certo — e no balcão não há tempo
para isso.
"""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from gestor_comercial.ui.views.mesas_view import MesasView


def test_cabecalho_tem_so_o_botao_pedido_balcao(qapp, comandas):
    view = MesasView(comandas)
    textos = [b.text() for b in view.findChildren(QPushButton)]

    assert "+  Pedido Balcão" in textos
    assert "Balcão" not in textos
    assert "+  Nova comanda" not in textos
    assert view._botao_pedido_balcao.property("variante") == "primario"


def test_pedido_balcao_abre_comanda_sem_mesa(qapp, comandas, gerente, caixa_aberto):
    view = MesasView(comandas)
    abertas = []
    view.comanda_aberta.connect(abertas.append)

    view._botao_pedido_balcao.click()

    assert len(abertas) == 1
    assert abertas[0].mesa_id is None
