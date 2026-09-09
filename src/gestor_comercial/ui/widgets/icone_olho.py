"""O olho de "ver o valor" — desenhado à mão, em duas peças que o compartilham.

## Por que não o emoji `👁`

Foi o que o pedido dizia, e é a única coisa aqui que não segue o pedido ao pé
da letra. `👁` (U+1F441) mora no bloco de emoji: no Windows ele cai no *Segoe
UI Emoji*, sai colorido e chapado, ignora a paleta e fica do tamanho errado ao
lado de um botão de 32px. É a mesma armadilha já registrada no cadeado do
`pin_pad_dialog`, na lupa do `adicionar_item_dialog` e no ramo do
`subcategoria_dialog` — e vale em dobro aqui, porque a máquina limpa do food
truck pode nem ter a fonte de emoji instalada, e aí o botão sai como um
retângulo vazio.

Vinte linhas de `QPainter` custam menos que depender disso, e têm um ganho de
graça: a cor é relida a cada repintura, então o ícone acompanha o alternador
Claro/Escuro sem ninguém reconectar nada (§3.15).

## Por que uma função de desenho e duas classes

O mesmo desenho aparece em dois papéis: o **botão** de cada linha de "Senhas e
Acesso" e o **selo do cabeçalho** do modal que pede o CPF. Um `QPushButton` e
um `QWidget` puro não podem ser a mesma classe (o botão precisa do fundo, da
borda e do clique que o QSS lhe dá), mas o traço é um só — e duas cópias dele
seriam duas figuras que divergem na primeira vez que alguém ajustar a curva.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QPushButton, QWidget

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.ui.theme.controller import ThemeController

LADO_PX = 18
LADO_BOTAO_PX = 32


def desenhar_olho(pintor: QPainter, cor: QColor, lado: float, riscado: bool) -> None:
    """Desenha a amêndoa, a pupila e — quando `riscado` — o traço que a corta.

    O traço é o que diz "clique para ocultar": o olho aberto e o olho cortado
    são o mesmo controle em dois estados, e não dois botões diferentes.
    """
    centro = lado / 2
    margem = lado * 0.11
    abertura = lado * 0.34

    amendoa = QPainterPath()
    amendoa.moveTo(QPointF(margem, centro))
    amendoa.quadTo(QPointF(centro, centro - abertura), QPointF(lado - margem, centro))
    amendoa.quadTo(QPointF(centro, centro + abertura), QPointF(margem, centro))

    caneta = QPen(cor, lado * 0.085)
    caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
    caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pintor.setPen(caneta)
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawPath(amendoa)

    raio = lado * 0.145
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(cor)
    pintor.drawEllipse(QRectF(centro - raio, centro - raio, raio * 2, raio * 2))

    if riscado:
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawLine(
            QPointF(margem * 1.4, lado - margem * 1.4),
            QPointF(lado - margem * 1.4, margem * 1.4),
        )


class IconeOlho(QWidget):
    """O olho como selo — sem clique, para o cabeçalho de um cartão."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("iconeOlho")
        self.setFixedSize(LADO_PX, LADO_PX)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        desenhar_olho(
            pintor,
            QColor(ThemeController.instancia().tokens_atuais["badge_icone_glifo"]),
            LADO_PX,
            riscado=False,
        )
        pintor.end()


class BotaoOlho(QPushButton):
    """O olho como botão, uma por linha de "Senhas e Acesso".

    Herda de `QPushButton` para o QSS lhe dar fundo, borda e realce ao passar o
    mouse como em qualquer botão do app — o que muda é que o miolo é pintado
    aqui em cima do que o estilo desenhou, em vez de ser um caractere de fonte.

    `revelado` é propriedade Qt, e não só um atributo Python: o QSS acende a
    borda do botão que está com o valor à mostra, e a propriedade é o que
    permite escrever isso como regra de estilo (`[revelado="true"]`) em vez de
    um `setStyleSheet` que congelaria a cor no tema vigente (§3.15).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("botaoOlho")
        self.setFixedSize(LADO_BOTAO_PX, LADO_BOTAO_PX)
        self.setProperty("revelado", False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoDefault(False)
        self.setDefault(False)

    def definir_revelado(self, revelado: bool) -> None:
        """Troca o estado do ícone (aberto ↔ cortado) e repolir o botão.

        Importado tarde, e não no topo: `estilo.aplicar_propriedade` importa
        widgets do Qt que já estão aqui, mas o import no topo criaria uma
        dependência circular entre os dois módulos de widget na primeira vez
        que `estilo` precisar de um ícone.
        """
        from gestor_comercial.ui.widgets.estilo import aplicar_propriedade

        if self.property("revelado") == revelado:
            return
        aplicar_propriedade(self, "revelado", revelado)
        self.update()

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        # `super()` primeiro: é ele quem pinta o fundo, a borda e o estado de
        # hover que o QSS descreve. O olho vem por cima.
        super().paintEvent(event)
        paleta = ThemeController.instancia().tokens_atuais
        cor = QColor(paleta["acento"] if self.property("revelado") else paleta["texto_fraco"])

        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        desvio = (LADO_BOTAO_PX - LADO_PX) / 2
        pintor.translate(desvio, desvio)
        desenhar_olho(pintor, cor, LADO_PX, riscado=bool(self.property("revelado")))
        pintor.end()
