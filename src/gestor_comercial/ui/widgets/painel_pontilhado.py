"""`QFrame` com uma textura de grid de pontos brancos sutis desenhada por
cima do fundo/gradiente definido via QSS -- não dá pra fazer isso só em QSS
porque não há `background-repeat` para `background-image` no QSS do Qt.

Usado na tela de login (painel da marca), na sidebar do shell autenticado
(`main_window.py`) e nos dois painéis do Cardápio (§9.11), daí viver num módulo
próprio em vez de dentro de uma das views.

Desenha só os pontos da região que o Qt mandou repintar (`event.rect()`). No
Cardápio isso importa: as listas de lá têm fundo transparente para a textura
aparecer entre os blocos, então passar o mouse por uma linha repinta também o
pedaço de painel atrás dela — e percorrer os ~600 pontos do painel inteiro para
acender uma faixa de 60px é trabalho jogado fora num Celeron. O resultado em
pixel é o mesmo: o painter já recortava na região; o que muda é o laço não
visitar ponto que o recorte ia descartar.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QFrame, QWidget

from gestor_comercial.core.resilience import nao_deixa_escapar


class PainelPontilhado(QFrame):
    _ESPACAMENTO_PX = 28
    _RAIO_PONTO_PX = 1.0
    _OPACIDADE_PONTO = 18  # 0-255 (~7%), sutil o bastante pra não distrair.

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, self._OPACIDADE_PONTO)))

        espaco = self._ESPACAMENTO_PX
        raio = self._RAIO_PONTO_PX
        area = event.rect()
        # Os pontos ficam em `espaco/2 + k*espaco`. Os índices da faixa suja
        # saem da conta inversa, com o raio de folga dos dois lados para um
        # ponto cortado ao meio pela borda da região não sumir pela metade.
        primeira_coluna = max(0, math.ceil((area.left() - raio - espaco / 2) / espaco))
        primeira_linha = max(0, math.ceil((area.top() - raio - espaco / 2) / espaco))
        y = espaco / 2 + primeira_linha * espaco
        while y < self.height() and y - raio <= area.bottom() + 1:
            x = espaco / 2 + primeira_coluna * espaco
            while x < self.width() and x - raio <= area.right() + 1:
                painter.drawEllipse(QPointF(x, y), raio, raio)
                x += espaco
            y += espaco
        painter.end()
