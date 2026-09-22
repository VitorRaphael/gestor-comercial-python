"""Linha de aviso que se apaga sozinha depois de `TEMPO_DE_VIDA_MS`.

Regra global da interface: todo aviso/feedback mostrado ao operador expira em
exatamente 3 segundos. A regra mora aqui, e só aqui — as views não criam
`QTimer` próprio; basta usar este widget (ou um filho dele) e chamar `setText`.

Por que apagar o texto em vez de `hide()`: o widget continua ocupando o mesmo
espaço no layout, então nada na tela "pula" quando o aviso some. E por que sem
fade-out com `QGraphicsOpacityEffect`: o efeito obriga o Qt a renderizar o
widget fora da tela a cada quadro, custo que a máquina do food truck não
precisa pagar por uma linha de texto (RNF de otimização).
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QWidget

from gestor_comercial.ui.widgets.estilo import aplicar_propriedade


TEMPO_DE_VIDA_MS = 3000


class AvisoTemporario(QLabel):
    """`QLabel` cujo texto expira `TEMPO_DE_VIDA_MS` depois do último `setText`.

    Um aviso novo chegando com outro ainda na tela reinicia a contagem: o
    operador sempre ganha os 3 segundos inteiros para ler o mais recente.
    """

    def __init__(self, texto: str = "", parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        # Filho do widget: morre junto com ele, sem vazar timer vivo apontando
        # para um label já destruído.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(TEMPO_DE_VIDA_MS)
        self._timer.timeout.connect(self._expirar)

    def setText(self, texto: str) -> None:  # noqa: N802 — assinatura do Qt
        super().setText(texto)
        if texto:
            # `start` num timer ativo já reinicia a contagem do zero.
            self._timer.start()
        else:
            self._timer.stop()

    def _expirar(self) -> None:
        # Volta ao tom apagado junto: um label vazio pintado de verde/âmbar
        # deixaria o fundo colorido (se o QSS tiver um) na tela.
        aplicar_propriedade(self, "tom", "")
        super().setText("")
