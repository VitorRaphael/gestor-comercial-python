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


def limpar_tabela(tabela: QTableWidget, *, linhas: int = 0) -> None:
    """Esvazia a tabela destruindo os widgets de célula e deixa `linhas` linhas.

    Substitui o par `setRowCount(0)` / `setRowCount(len(dados))` que as views
    usam antes de repopular:

        limpar_tabela(self._tabela, linhas=len(movimentos))
        for linha, movimento in enumerate(movimentos):
            ...

    O `setRowCount(0)` intermediário não é decoração: é ele que descarta os
    `QTableWidgetItem` (esses o Qt destrói sozinho) antes de a tabela voltar ao
    tamanho pedido.
    """
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
