"""Recarregar uma tela não pode aumentar o número de widgets vivos nela.

Ver `REMASTERIZACAO-V1.md` §3.3 — **e a derrubada do §3.3 na Fase 3**.

## O que mudou nestes testes, e por quê

Este arquivo se chamava `test_vazamento_tabelas.py` e trazia três
`xfail(strict=True)` baseados no §3.3, que afirmava:

> "Em Qt/C++, `QTableWidget::setCellWidget` destrói o widget que já estava na
> célula. No PySide6 não destrói. `setRowCount(0)` também não."

**A segunda metade é falsa.** Medido de novo na Fase 3 com um laço de eventos
rodando de verdade, em `offscreen` e em `windows`, PySide6 6.11.2:

    setCellWidget 50x na mesma célula:      1 widget vivo (o da célula)
    setRowCount(0) por 20 ciclos:           0 widgets vivos
    CardapioView.atualizar() 21 vezes:     78 -> 78 widgets

A medição original rodou **sem laço de eventos** — e sem laço um
`deleteLater()` legítimo fica pendente para sempre, indistinguível de
vazamento. Dois dos `xfail` exercitavam `QTableWidget` cru, sem passar por view
nenhuma: nenhuma correção feita no app poderia deixá-los verdes.

## O que este arquivo mede agora

Não a API do Qt — **as telas do app**. A pergunta que interessa ao food truck
não é "o `setCellWidget` vaza?", é "a tela do Cardápio cresce quando o pai do
Vitor cadastra o décimo produto do dia?". As dez telas são montadas no boot e
vivem o processo inteiro (`main_window.py:138-182`), então tudo o que sobra de
um `atualizar()` sobra até o app fechar.

A asserção é sempre sobre **crescimento**, nunca sobre um número absoluto:
quantos widgets uma linha usa é detalhe de layout que pode mudar sem ser bug. O
que nunca pode acontecer é o total subir a cada recarga.

O contrato dos utilitários de tabela é testado em `test_tabelas.py`, e o
comportamento do Qt cru fica travado lá, em
`test_a_celula_antiga_so_some_sozinha_no_proximo_ciclo`.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QWidget

from gestor_comercial.ui.views.cardapio_view import CardapioView

RECARGAS = 20


def test_cardapio_nao_cresce_a_cada_atualizar(qapp, assentar, cardapio, categoria, gerente):
    """A tela mais castigada por recarga: `CardapioView.atualizar()` roda a cada
    CRUD de produto e a cada troca de categoria."""
    for indice in range(5):
        cardapio.criar_produto(
            nome=f"Produto {indice}", preco=Decimal("10.00"), categoria_id=categoria.id
        )

    view = CardapioView(cardapio)
    view.atualizar()
    assentar()
    # Era a `tabela`; desde o §9.11 é a lista pintada. Ela nem tem widget por
    # linha para sobrar — e é exatamente por isso que a conta tem que continuar
    # sendo feita: o dia em que alguém pendurar um widget numa linha, é aqui
    # que aparece.
    depois_da_primeira = len(view._painel_produtos.lista.findChildren(QWidget))

    for _ in range(RECARGAS):
        view.atualizar()
    assentar()
    depois_de_muitas = len(view._painel_produtos.lista.findChildren(QWidget))

    assert depois_de_muitas == depois_da_primeira, (
        f"A lista do Cardápio foi de {depois_da_primeira} para {depois_de_muitas} "
        f"widgets em {RECARGAS} recargas — cada refresh deixa a leva anterior viva."
    )


def test_nenhuma_tela_cresce_a_cada_atualizar(
    qapp, assentar, gerente, mesa, produto, caixa_aberto, todas_as_telas
):
    """A rede larga, sobre as mesmas treze telas que o smoke monta.

    Com caixa aberto, mesa e produto no banco — sem dado nenhum toda tabela
    ficaria vazia e o teste passaria sem provar coisa alguma. As fixtures de
    dado vêm antes de `todas_as_telas` na assinatura de propósito: as telas
    precisam ser montadas com o banco já povoado.

    É este teste que sustenta o RNF "semanas ligado num Celeron sem degradar":
    a `MainWindow` chama `atualizar()` a cada navegação, então o operador
    dispara isto dezenas de vezes por turno. Tela nova entra na fixture do
    `conftest` e passa a ser coberta aqui automaticamente.
    """
    recarregaveis = {
        nome: tela
        for nome, tela in todas_as_telas.items()
        if getattr(tela, "atualizar", None) is not None
    }
    assert recarregaveis, "nenhuma tela recarregável — a fixture mudou de forma"

    for tela in recarregaveis.values():
        tela.atualizar()
    assentar()
    linha_de_base = {nome: len(tela.findChildren(QWidget)) for nome, tela in recarregaveis.items()}

    for _ in range(RECARGAS):
        for tela in recarregaveis.values():
            tela.atualizar()
    assentar()

    cresceram = {
        nome: (linha_de_base[nome], depois)
        for nome, tela in recarregaveis.items()
        if (depois := len(tela.findChildren(QWidget))) != linha_de_base[nome]
    }
    assert not cresceram, "\n".join(
        f"{nome}: {antes} -> {depois} widgets em {RECARGAS} recargas"
        for nome, (antes, depois) in cresceram.items()
    )
