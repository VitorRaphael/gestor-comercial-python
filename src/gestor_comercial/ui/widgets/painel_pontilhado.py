"""`QFrame` com uma textura de grid de pontos brancos sutis desenhada por
cima do fundo/gradiente definido via QSS -- não dá pra fazer isso só em QSS
porque não há `background-repeat` para `background-image` no QSS do Qt.

Usado na tela de login (painel da marca) e na sidebar do shell autenticado
(`main_window.py`), daí viver num módulo próprio em vez de dentro de uma das
duas views.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QFrame, QWidget


class PainelPontilhado(QFrame):
    _ESPACAMENTO_PX = 28
    _RAIO_PONTO_PX = 1.0
    _OPACIDADE_PONTO = 18  # 0-255 (~7%), sutil o bastante pra não distrair.

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, self._OPACIDADE_PONTO)))

        espaco = self._ESPACAMENTO_PX
        raio = self._RAIO_PONTO_PX
        y = espaco / 2
        while y < self.height():
            x = espaco / 2
            while x < self.width():
                painter.drawEllipse(QPointF(x, y), raio, raio)
                x += espaco
            y += espaco
        painter.end()
