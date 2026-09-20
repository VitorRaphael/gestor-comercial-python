"""O interruptor desenhado — trilho com a bolinha que corre de um lado ao outro.

Nasceu dentro do cartão de impressora (§9.19, "Impressora ativa") e saiu para cá
quando a tela de Configurações precisou do mesmo desenho para "Cobrar taxa de
serviço (10%)" (§9.23): a segunda cópia seria a pintura inteira, e é o tipo de
repetição que `test_nenhuma_funcao_da_ui_repete_o_corpo_de_outra` reprova. Os
tokens saíram junto — `impressora_interruptor_*` virou `interruptor_*`, o nome
do papel e não da tela, pelo critério de `botao_circular_*` (§9.4).

Pintado, e não um `QCheckBox` com QSS: o indicador de check do Qt não faz
trilho com bolinha, e uma imagem de interruptor por tema viraria arquivo a
trocar a cada alternância (§3.15). A cor é lida a cada pintura.

**Não recebe clique.** Quem recebe é o card em volta dele, que é o alvo que o
dedo acerta no balcão; o interruptor só mostra o estado que o card decidiu.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.cores import cor_do_token


class Interruptor(QWidget):
    """O desenho do interruptor, ligado ou desligado."""

    LARGURA_PX = 38
    ALTURA_PX = 22

    def __init__(self, parent: QWidget | None = None, *, ligado: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("interruptor")
        self.setFixedSize(self.LARGURA_PX, self.ALTURA_PX)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._ligado = ligado

    @property
    def ligado(self) -> bool:
        return self._ligado

    def definir(self, ligado: bool) -> None:
        if ligado != self._ligado:
            self._ligado = ligado
            self.update()

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        tokens = ThemeController.instancia().tokens_atuais
        sufixo = "ligado" if self._ligado else "desligado"
        trilho = cor_do_token(tokens[f"interruptor_{sufixo}"])
        botao = cor_do_token(tokens[f"interruptor_botao_{sufixo}"])
        area = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        raio = area.height() / 2.0
        folga = 3.0
        lado = area.height() - 2 * folga
        x = area.right() - folga - lado if self._ligado else area.left() + folga

        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(trilho)
        pintor.drawRoundedRect(area, raio, raio)
        pintor.setBrush(botao)
        pintor.drawEllipse(QRectF(x, area.top() + folga, lado, lado))
        pintor.end()
