"""Layout que quebra linha sozinho quando os itens não cabem na largura
disponível -- usado pelas grades de cards (ver `LojaHubView`) para que a
Central de Loja continue legível com a janela redimensionada, sem depender
de um número fixo de colunas por `QGridLayout`.

Adaptado do recipe oficial de FlowLayout do Qt (mesmo algoritmo do exemplo
`layouts/flowlayout` da documentação do PySide6), sem dependências extras.
"""

from __future__ import annotations

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget

from gestor_comercial.core.resilience import nao_deixa_escapar


class FlowLayout(QLayout):
    def __init__(self, parent: QWidget | None = None, margin: int = 0, spacing: int = 12) -> None:
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(QMargins(margin, margin, margin, margin))
        self.setSpacing(spacing)
        self._items: list[QLayoutItem] = []

    def __del__(self) -> None:
        while self.count():
            self.takeAt(0)

    @nao_deixa_escapar()
    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 (override Qt)
        self._items.append(item)

    @nao_deixa_escapar(retorno=0)
    def count(self) -> int:  # noqa: N802 (override Qt)
        return len(self._items)

    @nao_deixa_escapar()
    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 (override Qt)
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    @nao_deixa_escapar()
    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 (override Qt)
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    @nao_deixa_escapar(retorno=Qt.Orientation(0))
    def expandingDirections(self) -> Qt.Orientations:  # noqa: N802 (override Qt)
        return Qt.Orientation(0)

    @nao_deixa_escapar(retorno=True)
    def hasHeightForWidth(self) -> bool:  # noqa: N802 (override Qt)
        return True

    @nao_deixa_escapar(retorno=0)
    def heightForWidth(self, width: int) -> int:  # noqa: N802 (override Qt)
        return self._organizar(QRect(0, 0, width, 0), medir_apenas=True)

    @nao_deixa_escapar()
    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 (override Qt)
        super().setGeometry(rect)
        self._organizar(rect, medir_apenas=False)

    @nao_deixa_escapar(retorno=QSize(0, 0))
    def sizeHint(self) -> QSize:  # noqa: N802 (override Qt)
        return self.minimumSize()

    @nao_deixa_escapar(retorno=QSize(0, 0))
    def minimumSize(self) -> QSize:  # noqa: N802 (override Qt)
        tamanho = QSize()
        for item in self._items:
            tamanho = tamanho.expandedTo(item.minimumSize())
        margens = self.contentsMargins()
        tamanho += QSize(margens.left() + margens.right(), margens.top() + margens.bottom())
        return tamanho

    def _organizar(self, rect: QRect, medir_apenas: bool) -> int:
        x = rect.x()
        y = rect.y()
        altura_linha = 0
        espacamento = self.spacing()

        for item in self._items:
            widget = item.widget()
            espaco_x = espacamento
            espaco_y = espacamento
            largura_proxima = x + item.sizeHint().width() + espaco_x
            if largura_proxima - espaco_x > rect.right() and altura_linha > 0:
                x = rect.x()
                y = y + altura_linha + espaco_y
                altura_linha = 0
                largura_proxima = x + item.sizeHint().width() + espaco_x

            if not medir_apenas:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = largura_proxima
            altura_linha = max(altura_linha, item.sizeHint().height())

        return y + altura_linha - rect.y()
