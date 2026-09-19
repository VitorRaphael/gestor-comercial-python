"""Layouts que quebram linha sozinhos quando os itens não cabem na largura
disponível -- usados pelas grades de cards (ver `LojaHubView`) para que a
Central de Loja continue legível com a janela redimensionada, sem depender
de um número fixo de colunas por `QGridLayout`.

`FlowLayout` foi adaptado do recipe oficial do Qt (mesmo algoritmo do exemplo
`layouts/flowlayout` da documentação do PySide6), sem dependências extras.
`GradeFluida` é a variante de células iguais, feita para a grade de mesas.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.ui.widgets.layout_utils import limpar_layout


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


class GradeFluida(FlowLayout):
    """Grade de células IGUAIS cujo número de colunas sai da largura.

    Os itens correm e quebram linha como no `FlowLayout`, mas aqui toda célula
    tem a mesma largura e a fileira é esticada até a borda: a última coluna
    termina exatamente na margem direita, sem sobra irregular e sem passar
    dela. Foi feita para a grade de mesas (§9.24), que usava `QGridLayout` com
    8 colunas fixas — a 1366px a última coluna e meia ficava atrás de uma
    barra de rolagem horizontal.

    O número de colunas é o maior que cabe sem espremer nenhuma célula abaixo
    do mínimo: `(largura + espaço) // (mínimo + espaço)`. O mínimo e a altura
    da célula vêm dos próprios itens (o maior de cada), e não de um número
    passado aqui: quem sabe quanto um cartão precisa é o cartão. Como a célula
    não depende de quantos itens há, filtrar a grade para duas mesas não
    transforma as duas em cartões gigantes.

    Custo: a medida da célula fica guardada até o Qt invalidar o layout (item
    entrando ou saindo, filho mudando de tamanho). Com isso o `heightForWidth`,
    que a `QScrollArea` chama em laço a cada redimensionamento para decidir a
    barra vertical, é aritmética pura, sem percorrer os itens. E redimensionar
    só reposiciona: nenhum widget é criado nem recriado. Para trocar o
    conteúdo inteiro, `repovoar` faz tudo com um relayout só.

    Diferente do `FlowLayout`, que ignora as margens ao posicionar (nenhum
    uso dele tem margem), esta respeita as margens: é o que separa o cartão da
    última coluna da barra de rolagem vertical.
    """

    def __init__(self, parent: QWidget | None = None, margin: int = 0, spacing: int = 12) -> None:
        super().__init__(parent, margin, spacing)
        self._celula: QSize | None = None

    @nao_deixa_escapar()
    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 (override Qt)
        super().addItem(item)
        # O `QGridLayout` e o `QBoxLayout` fazem o mesmo: item novo marca o
        # layout como sujo, e o Qt refaz a geometria no próximo ciclo.
        self.invalidate()

    @nao_deixa_escapar()
    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 (override Qt)
        # Só a medida guardada, e não `invalidate()`: o `__del__` do
        # `FlowLayout` passa por aqui, quando o lado C++ já pode ter sido
        # destruído. Quem tira o widget da tela invalida o layout pelo Qt.
        self._celula = None
        return super().takeAt(index)

    @nao_deixa_escapar()
    def invalidate(self) -> None:
        self._celula = None
        super().invalidate()

    def repovoar(self, widgets: Iterable[QWidget]) -> None:
        """Destrói o que a grade tem e põe `widgets` no lugar, com UM relayout.

        Adicionar um widget a um pai visível agenda um `show()` para o
        próximo ciclo, e cada um desses `show()` refaz na hora o layout do pai
        (é o Qt garantindo que o filho apareça já no lugar). Com sessenta
        mesas eram 61 relayouts completos por recarga, um por cartão: O(n²)
        posicionamentos, 10ms a mais a cada volta para a tela de Mesas.

        Com o layout desligado, `activate()` não faz nada ("age como se não
        existisse", diz a documentação do Qt). Os `show()` acontecem aqui
        dentro, então o agendado pelo Qt encontra o widget já visível e não
        faz nada. Religado, o layout está sujo e se refaz uma vez só, no
        próximo ciclo de eventos.
        """
        limpar_layout(self)
        self.setEnabled(False)
        try:
            for widget in widgets:
                self.addWidget(widget)
                widget.show()
        finally:
            self.setEnabled(True)

    @nao_deixa_escapar(retorno=QSize(0, 0))
    def minimumSize(self) -> QSize:  # noqa: N802 (override Qt)
        # Uma célula e as margens: é o que garante que a grade nunca peça mais
        # largura do que a área oferece. Sai da medida guardada, e não de uma
        # volta pelos itens como no `FlowLayout`: o Qt pergunta isto oito vezes
        # a cada redimensionamento, e a volta custava 0,7ms de cada um.
        margens = self.contentsMargins()
        celula = self._tamanho_da_celula() if self._items else QSize(0, 0)
        return celula + QSize(margens.left() + margens.right(), margens.top() + margens.bottom())

    def _tamanho_da_celula(self) -> QSize:
        if self._celula is None:
            largura = max(item.minimumSize().width() for item in self._items)
            altura = max(item.sizeHint().height() for item in self._items)
            self._celula = QSize(max(1, largura), altura)
        return self._celula

    def _organizar(self, rect: QRect, medir_apenas: bool) -> int:
        if not self._items:
            return 0
        margens = self.contentsMargins()
        area = rect.marginsRemoved(margens)
        celula = self._tamanho_da_celula()
        espaco = self.spacing()

        colunas = max(1, (area.width() + espaco) // (celula.width() + espaco))
        linhas = -(-len(self._items) // colunas)
        altura = margens.top() + linhas * celula.height() + (linhas - 1) * espaco + margens.bottom()
        if medir_apenas:
            return altura

        # A sobra da divisão vai um pixel para cada uma das primeiras colunas:
        # é o que faz a última terminar exatamente na margem direita.
        base, sobra = divmod(area.width() - (colunas - 1) * espaco, colunas)
        for indice, item in enumerate(self._items):
            linha, coluna = divmod(indice, colunas)
            x = area.x() + coluna * (base + espaco) + min(coluna, sobra)
            y = area.y() + linha * (celula.height() + espaco)
            largura = base + 1 if coluna < sobra else base
            item.setGeometry(QRect(x, y, largura, celula.height()))
        return altura
