"""Limpar um `QTableWidget` destruindo as células na hora, e não depois.

Ver `REMASTERIZACAO-V1.md` §3.3 — **e a correção do §3.3 registrada na Fase 3**.

O §3.3 dizia que `setCellWidget` vaza no PySide6. Medido de novo aqui, com
PySide6 6.11.2 e um laço de eventos rodando de verdade (`app.exec()`), não
vaza: o Qt agenda a destruição do ocupante anterior e recolhe tudo no ciclo
seguinte. A medição original foi feita sem laço de eventos — e sem laço, um
`deleteLater()` legítimo fica pendente para sempre e parece vazamento.

    setCellWidget 50x na mesma célula, com o laço rodando:  1 QLabel vivo
    setRowCount(0) por 20 ciclos, com o laço rodando:       0 QLabel vivos
    CardapioView.atualizar() 21 vezes:            78 -> 78 widgets

Então o que este módulo entrega **não** é a correção de um vazamento: é
**determinismo**. Com `definir_celula`, o widget antigo sai da árvore no ato,
antes do próximo repaint, em vez de continuar filho do viewport na geometria
velha até o Qt passar recolhendo. É a mesma garantia que `layout_utils` dá aos
layouts, e é a que já custou dois bugs visuais de sobreposição neste projeto
(§3.7).
"""

from __future__ import annotations

from PySide6.QtWidgets import QTableWidget, QWidget


def limpar_tabela(
    tabela: QTableWidget, *, linhas: int = 0, preservar_selecao: bool = False
) -> None:
    """Esvazia a tabela destruindo os widgets de célula e deixa `linhas` linhas.

    Substitui o par `setRowCount(0)` / `setRowCount(len(dados))` que as views
    usam antes de repopular:

        limpar_tabela(self._tabela, linhas=len(movimentos))
        for linha, movimento in enumerate(movimentos):
            ...

    O `setRowCount(0)` intermediário não é decoração: é ele que descarta os
    `QTableWidgetItem` (esses o Qt destrói sozinho) antes de a tabela voltar ao
    tamanho pedido.

    `preservar_selecao` devolve a linha corrente ao lugar depois de repopular.
    Não é enfeite: as views chamavam `setRowCount(len(dados))` **sem** zerar
    antes, e nesse caminho o Qt mantém a linha corrente quando a contagem não
    encolhe. Passar pelo zero a perderia — e `cardapio_view`/`impressoras_view`
    leem `currentRow()` logo depois de repopular para decidir quais botões
    ficam habilitados e qual impressora aparece no painel lateral. Sem esta
    opção, editar um produto apagaria a seleção dele.
    """
    if not preservar_selecao:
        _esvaziar(tabela, linhas)
        return

    linha_selecionada = tabela.currentRow()
    coluna_selecionada = max(tabela.currentColumn(), 0)

    # A ida ao zero e a volta emitiriam `itemSelectionChanged`/
    # `currentCellChanged` no meio do refresh, e os assinantes reagiriam a uma
    # seleção vazia que nunca existiu para o usuário — `cardapio_view` chegaria
    # a emitir `produto_selecionado(None)` e a desabilitar os botões do rodapé
    # antes de repovoar. Bloquear a tabela pelo trecho inteiro deixa o
    # observável idêntico ao `setRowCount(len(dados))` que havia antes: nenhum
    # sinal, porque do lado de fora nada mudou. O bloqueio é dos sinais da
    # tabela; as conexões internas view↔modelo do Qt não passam por ele.
    bloqueado = tabela.blockSignals(True)
    try:
        _esvaziar(tabela, linhas)
        if linha_selecionada >= 0 and linhas:
            # Encolheu abaixo da linha selecionada: o `setRowCount(n)` sozinho
            # grudava na última linha existente em vez de largar a seleção.
            tabela.setCurrentCell(min(linha_selecionada, linhas - 1), coluna_selecionada)
    finally:
        tabela.blockSignals(bloqueado)


def _esvaziar(tabela: QTableWidget, linhas: int) -> None:
    for linha in range(tabela.rowCount()):
        for coluna in range(tabela.columnCount()):
            _descartar_celula(tabela, linha, coluna)
    tabela.setRowCount(0)
    if linhas:
        tabela.setRowCount(linhas)


def definir_celula(tabela: QTableWidget, linha: int, coluna: int, widget: QWidget) -> None:
    """`setCellWidget` que destrói o ocupante anterior da célula.

    Use no lugar de `tabela.setCellWidget(...)` sempre que a célula puder já
    estar ocupada — que é o caso de toda tabela repovoada sem passar por
    `limpar_tabela` antes.
    """
    _descartar_celula(tabela, linha, coluna)
    tabela.setCellWidget(linha, coluna, widget)


def _descartar_celula(tabela: QTableWidget, linha: int, coluna: int) -> None:
    anterior = tabela.cellWidget(linha, coluna)
    if anterior is None:
        return
    # `removeCellWidget` desfaz o vínculo célula→widget mas, no PySide6, deixa o
    # widget vivo e ainda filho da tabela. O `setParent(None)` tira da árvore na
    # hora e o `deleteLater()` marca para destruição no próximo ciclo de
    # eventos — o mesmo par usado em `layout_utils.limpar_layout`.
    tabela.removeCellWidget(linha, coluna)
    anterior.setParent(None)
    anterior.deleteLater()
