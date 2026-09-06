"""Recarregar uma tabela não pode deixar as células antigas na memória.

Ver `REMASTERIZACAO-V1.md` §3.3. Este vazamento é **mais frequente** que o dos
modais: dispara a cada `atualizar()` de tela, não a cada clique do usuário.

## A armadilha do PySide6

Em Qt/C++, `QTableWidget::setCellWidget` destrói o widget que já estava na
célula. **No PySide6 não destrói.** `setRowCount(0)` também não. Então toda
view que remonta a tabela — comanda reaberta, cardápio após um CRUD, troca de
categoria — deixa a leva anterior de widgets pendurada na tabela.

Como as 10 views vivem o processo inteiro (`main_window.py:138-182`), essas
sobras nunca são recolhidas.

## Sobre os marcadores `xfail`

Mesma mecânica de `test_vazamento_modais.py`: descrevem o comportamento que a
**Fase 4** vai entregar e falham hoje de propósito. `strict=True` faz a suíte
quebrar quando a correção entrar, forçando a remoção do marcador.
"""

from __future__ import annotations

import gc
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QLabel, QTableWidget, QWidget

from gestor_comercial.ui.views.cardapio_view import CardapioView

PENDENTE_FASE_4 = "Fase 4 da Remasterização: células de tabela ainda não são destruídas (§3.3)"

RECARGAS = 20


def _assentar(qapp) -> None:
    gc.collect()
    qapp.processEvents()
    gc.collect()
    qapp.processEvents()


def test_o_comportamento_do_qt_esta_documentado(qapp):
    """Prova, sem passar por nenhuma view, que a armadilha existe mesmo.

    Este teste passa hoje e é o "antes" verificável do §3.3. Se um dia o
    PySide6 mudar esse comportamento, é aqui que a mudança aparece primeiro —
    e aí boa parte da Fase 4 deixa de ser necessária.
    """
    tabela = QTableWidget(1, 1)

    for i in range(50):
        tabela.setCellWidget(0, 0, QLabel(f"célula {i}"))
    _assentar(qapp)

    sobreviventes = tabela.findChildren(QLabel)
    assert len(sobreviventes) == 50, (
        "setCellWidget passou a destruir o widget anterior — reavaliar o §3.3 "
        "antes de fazer a Fase 4."
    )


@pytest.mark.xfail(strict=True, reason=PENDENTE_FASE_4)
def test_setcellwidget_nao_deixa_celula_antiga_viva(qapp):
    """O alvo: substituir o widget de uma célula 50 vezes deve deixar 1 vivo."""
    tabela = QTableWidget(1, 1)

    for i in range(50):
        tabela.setCellWidget(0, 0, QLabel(f"célula {i}"))
    _assentar(qapp)

    assert len(tabela.findChildren(QLabel)) == 1


@pytest.mark.xfail(strict=True, reason=PENDENTE_FASE_4)
def test_limpar_tabela_com_setrowcount_libera_as_celulas(qapp):
    """`setRowCount(0)` é o padrão de limpeza usado pelas views. Ele precisa
    liberar os widgets de célula, não só sumir com as linhas."""
    tabela = QTableWidget(0, 1)

    for ciclo in range(RECARGAS):
        tabela.setRowCount(1)
        tabela.setCellWidget(0, 0, QLabel(f"ciclo {ciclo}"))
        tabela.setRowCount(0)
    _assentar(qapp)

    assert tabela.findChildren(QLabel) == []


@pytest.mark.xfail(strict=True, reason=PENDENTE_FASE_4)
def test_cardapio_nao_cresce_a_cada_atualizar(qapp, cardapio, categoria, gerente):
    """O caminho real: `CardapioView.atualizar()` roda a cada CRUD de produto e
    a cada troca de categoria. Vinte recargas não podem aumentar o número de
    widgets vivos dentro da tabela.

    A asserção é sobre *crescimento*, não sobre um número absoluto: quantos
    widgets uma linha usa é detalhe de layout que pode mudar sem ser bug. O que
    nunca pode acontecer é o total subir a cada recarga.
    """
    for indice in range(5):
        cardapio.criar_produto(
            nome=f"Produto {indice}", preco=Decimal("10.00"), categoria_id=categoria.id
        )

    view = CardapioView(cardapio)
    view.atualizar()
    _assentar(qapp)
    depois_da_primeira = len(view._painel_produtos.tabela.findChildren(QWidget))

    for _ in range(RECARGAS):
        view.atualizar()
    _assentar(qapp)
    depois_de_muitas = len(view._painel_produtos.tabela.findChildren(QWidget))

    assert depois_de_muitas == depois_da_primeira, (
        f"A tabela do Cardápio foi de {depois_da_primeira} para {depois_de_muitas} "
        f"widgets em {RECARGAS} recargas — cada refresh deixa a leva anterior viva."
    )
