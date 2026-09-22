"""Captura e redesenho da assinatura manuscrita (consumo interno).

Duas peças sobre o mesmo desenho:

- `SignaturePadWidget` — a área onde o colaborador assina com o mouse.
- `AssinaturaView` — o quadro só-leitura que redesenha um traço gravado.

As duas pintam por `desenhar_assinatura`, então o que aparece no detalhe da
retirada é o mesmo que a pessoa viu ao assinar, só escalado.

Leve de propósito (Celeron do food truck): nenhum pixmap, nenhuma imagem no
banco. O traço vive como listas de pontos inteiros e vira um `QPainterPath`
por pintura — algumas centenas de segmentos, custo desprezível.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.services.assinatura import Assinatura, Ponto, ler_assinatura
from gestor_comercial.services.exceptions import RegraDeNegocioError

# O papel é sempre claro, nos dois temas: assinatura é tinta escura no branco,
# como no papel que ela substitui.
COR_PAPEL = QColor("#f4f4f5")
COR_TINTA = QColor("#18181b")
COR_GUIA = QColor("#a1a1aa")
ESPESSURA_TINTA = 2.4
RAIO_PAPEL = 10.0


def caminho_do_traco(tracos: Sequence[Sequence[Ponto]]) -> QPainterPath:
    """Um `QPainterPath` com todos os traços; ponto solto vira um pinguinho."""
    caminho = QPainterPath()
    for traco in tracos:
        if not traco:
            continue
        x0, y0 = traco[0]
        caminho.moveTo(x0, y0)
        if len(traco) == 1:
            caminho.lineTo(x0 + 0.1, y0 + 0.1)
            continue
        # Curva pelos pontos médios: suaviza o serrilhado do mouse sem
        # inventar pontos que a pessoa não desenhou.
        for (xa, ya), (xb, yb) in zip(traco[1:], traco[2:]):
            caminho.quadTo(xa, ya, (xa + xb) / 2, (ya + yb) / 2)
        xf, yf = traco[-1]
        caminho.lineTo(xf, yf)
    return caminho


def _pintar_papel(pintor: QPainter, area: QRectF, *, guia: bool) -> None:
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(COR_PAPEL)
    pintor.drawRoundedRect(area, RAIO_PAPEL, RAIO_PAPEL)
    if guia:
        pintor.setPen(QPen(COR_GUIA, 1.2, Qt.PenStyle.DashLine))
        y = area.top() + area.height() * 0.68
        pintor.drawLine(QPointF(area.left() + 24, y), QPointF(area.right() - 24, y))
        pintor.drawText(QPointF(area.left() + 24, y - 6), "X")


def desenhar_assinatura(
    pintor: QPainter,
    area: QRectF,
    tracos: Sequence[Sequence[Ponto]],
    largura_origem: int,
    altura_origem: int,
) -> None:
    """Pinta os traços do espaço (largura_origem × altura_origem) dentro de `area`.

    Escala uniforme e centralizada: a assinatura nunca estica de lado.
    """
    if largura_origem <= 0 or altura_origem <= 0:
        return
    escala = min(area.width() / largura_origem, area.height() / altura_origem)
    dx = area.left() + (area.width() - largura_origem * escala) / 2
    dy = area.top() + (area.height() - altura_origem * escala) / 2
    pintor.save()
    pintor.translate(dx, dy)
    pintor.scale(escala, escala)
    caneta = QPen(COR_TINTA, ESPESSURA_TINTA, Qt.PenStyle.SolidLine)
    caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
    caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    # Espessura fixa na tela, qualquer que seja a escala do quadro.
    caneta.setCosmetic(True)
    pintor.setPen(caneta)
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawPath(caminho_do_traco(tracos))
    pintor.restore()


class SignaturePadWidget(QWidget):
    """A área de assinatura: press abaixa a caneta, move risca, release levanta."""

    assinatura_alterada = Signal(bool)  # True quando há traço

    # Distância mínima (px) entre dois pontos gravados: o mouse manda eventos
    # demais parado no lugar, e cada um seria bytes no banco sem mudar o desenho.
    PASSO_MINIMO = 2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("signaturePad")
        self.setMinimumSize(420, 170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._tracos: list[list[Ponto]] = []
        self._desenhando = False

    @nao_deixa_escapar(QSize(520, 190))
    def sizeHint(self) -> QSize:  # noqa: N802 (override Qt)
        return QSize(520, 190)

    @property
    def tem_traco(self) -> bool:
        return any(self._tracos)

    def limpar(self) -> None:
        self._tracos = []
        self._desenhando = False
        self.update()
        self.assinatura_alterada.emit(False)

    def assinatura(self) -> Assinatura:
        return Assinatura(
            self.width(),
            self.height(),
            tuple(tuple(traco) for traco in self._tracos if traco),
        )

    def para_json(self) -> str:
        return self.assinatura().para_json()

    def _ponto(self, event: QMouseEvent) -> Ponto:
        pos = event.position()
        x = min(max(round(pos.x()), 0), self.width())
        y = min(max(round(pos.y()), 0), self.height())
        return (x, y)

    @nao_deixa_escapar()
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._desenhando = True
        tinha = self.tem_traco
        self._tracos.append([self._ponto(event)])
        self.update()
        if not tinha:
            self.assinatura_alterada.emit(True)

    @nao_deixa_escapar()
    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if not self._desenhando or not self._tracos:
            return
        x, y = self._ponto(event)
        ultimo_x, ultimo_y = self._tracos[-1][-1]
        if abs(x - ultimo_x) + abs(y - ultimo_y) < self.PASSO_MINIMO:
            return
        self._tracos[-1].append((x, y))
        self.update()

    @nao_deixa_escapar()
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self._desenhando = False

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect())
        _pintar_papel(pintor, area, guia=True)
        # Na captura o espaço de origem é o próprio widget: escala 1.
        desenhar_assinatura(pintor, area, self._tracos, self.width(), self.height())
        pintor.end()


class AssinaturaView(QWidget):
    """Quadro só-leitura que redesenha uma assinatura gravada (auditoria)."""

    def __init__(self, traco_json: str | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("assinaturaView")
        self.setMinimumSize(280, 140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._assinatura: Assinatura | None = None
        self._aviso = "Retirada registrada antes da assinatura digital (autorizada por PIN)."
        if traco_json is not None:
            try:
                self._assinatura = ler_assinatura(traco_json)
            except RegraDeNegocioError:
                self._aviso = "A assinatura gravada não pôde ser lida."

    @property
    def assinatura(self) -> Assinatura | None:
        return self._assinatura

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect())
        _pintar_papel(pintor, area, guia=False)
        if self._assinatura is None:
            pintor.setPen(COR_GUIA)
            pintor.drawText(
                area.adjusted(16, 16, -16, -16),
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self._aviso,
            )
        else:
            a = self._assinatura
            desenhar_assinatura(pintor, area.adjusted(8, 8, -8, -8), a.tracos, a.largura, a.altura)
        pintor.end()
