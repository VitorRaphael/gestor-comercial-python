"""As peças que todo modal em cartão do app compartilha.

Modal em cartão é o diálogo sem moldura do sistema, com o cabeçalho desenhado
por ele mesmo e o fundo da janela escurecido: hoje o de PIN
(`pin_pad_dialog.py`) e o de lançar item (`adicionar_item_dialog.py`). Tudo
aqui nasceu dentro do primeiro e saiu de lá quando o segundo apareceu — uma
segunda cópia seria a repetição que `test_paineis_de_relatorio.py` reprova, e
o que se copiaria não é decoração: é **ciclo de vida** e **foco de teclado**,
as duas coisas que quebram em silêncio.

Por que o escurecedor é um `QWidget` filho da janela, e não uma janela própria
translúcida: um widget comum dentro do backing store do Qt já compõe por cima
dos irmãos, e isso custa uma pintura chapada. Abrir uma segunda janela do
tamanho da tela numa máquina sem GPU (o Celeron do food truck) custa muito
mais.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QPushButton, QWidget

from gestor_comercial.core.resilience import nao_deixa_escapar


class Backdrop(QWidget):
    """Retângulo preto translúcido cobrindo a janela inteira do parent."""

    OPACIDADE = 150  # 0-255 (~59%)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("modalBackdrop")

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        pintor = QPainter(self)
        pintor.fillRect(self.rect(), QColor(0, 0, 0, self.OPACIDADE))
        pintor.end()


def montar(dono: QWidget) -> Backdrop | None:
    """Cria, posiciona e mostra o escurecedor sobre a janela que hospeda `dono`.

    Devolve `None` quando o diálogo não tem parent (caso dos testes que montam
    o modal solto): sem janela de trás não há o que escurecer, e o modal
    continua funcionando igual.
    """
    pai = dono.parentWidget()
    if pai is None:
        return None
    janela = pai.window()
    backdrop = Backdrop(janela)
    backdrop.setGeometry(janela.rect())
    backdrop.raise_()
    backdrop.show()
    return backdrop


def descartar(backdrop: Backdrop | None) -> None:
    """Solta o escurecedor do parent AGORA, não quando o Qt passar recolhendo.

    `deleteLater()` sozinho só marca; até o laço de eventos girar, o widget
    continua filho da janela principal — e a janela principal vive o processo
    inteiro. O `setParent(None)` é o que garante que uma tarde de idas e voltas
    ao modal não deixe uma pilha de escurecedores invisíveis pendurada lá.
    """
    if backdrop is None:
        return
    backdrop.hide()
    backdrop.setParent(None)
    backdrop.deleteLater()


def preparar_botao(botao: QPushButton) -> None:
    """Tira o botão da roda de foco e do papel de "botão padrão".

    As duas coisas pela mesma razão: num modal em cartão quem lê o teclado é o
    **diálogo**, no `keyPressEvent` dele. Com o foco parado num botão, o Enter
    dispararia aquele botão em vez da ação que o operador espera, e o Espaço
    "clicaria" o último botão usado — bug clássico de teclado em Qt, e no
    balcão ele vira item errado na comanda ou PIN recusado sem motivo.
    """
    botao.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    botao.setAutoDefault(False)
    botao.setDefault(False)
    botao.setCursor(Qt.CursorShape.PointingHandCursor)


def centralizar_no_pai(dialogo: QWidget) -> None:
    """Põe o cartão no meio da janela que o abriu.

    Sem parent (ou com a janela ainda invisível, como na suíte `offscreen`) não
    há em relação a que centralizar, e a função simplesmente não mexe na
    posição — o Qt já põe o diálogo em algum lugar razoável.
    """
    pai = dialogo.parentWidget()
    if pai is None:
        return
    janela = pai.window()
    if not janela.isVisible():
        return
    centro = janela.frameGeometry().center()
    dialogo.move(centro.x() - dialogo.width() // 2, centro.y() - dialogo.height() // 2)
