"""A textura de pontos sai igual quando só um pedaço do painel é repintado. §9.11.

O `PainelPontilhado` passou a desenhar só os pontos da região que o Qt manda
repintar — no Cardápio as listas têm fundo transparente, e passar o mouse por
uma linha repinta o pedaço de painel atrás dela. A promessa da mudança é de
desempenho, não de aparência: o pixel tem que ser o mesmo que a pintura do
painel inteiro produz. Um erro de uma coluna na conta inversa dos índices
apagaria (ou cortaria ao meio) os pontos da borda de cada região repintada —
exatamente o tipo de defeito que só aparece ao passar o mouse.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPixmap, QRegion

from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado


@pytest.mark.parametrize(
    "regiao",
    [
        QRect(0, 0, 300, 220),  # o painel inteiro
        QRect(50, 50, 60, 60),  # começa e termina entre pontos
        QRect(13, 13, 3, 3),  # exatamente sobre o primeiro ponto
        QRect(41, 0, 1, 220),  # uma coluna de 1px cortando pontos ao meio
        QRect(0, 69, 300, 4),  # uma faixa fina como a de uma linha sob o mouse
        # Começando 1px DEPOIS do centro de um ponto (os centros ficam em
        # 14 + 28k): a borda antisserrilhada do ponto de trás ainda cai aqui, e
        # é a folga do raio na conta inversa que o mantém na pintura.
        QRect(43, 0, 3, 220),
        QRect(0, 43, 300, 3),
    ],
)
# O raio de verdade (1px) e um fracionário. Com raio 1 e centros inteiros, a
# folga do raio na conta inversa é inerte — o ponto cobre os pixels c−1 e c, e a
# conta sem folga já acerta. Ela existe para o raio que não for inteiro, e é
# com ele que a folga é cobrada: sem ela, o ponto que invade a região pela
# metade some da repintura.
@pytest.mark.parametrize("raio", [1.0, 1.5])
def test_repintar_um_pedaco_da_os_mesmos_pixels_que_repintar_tudo(qapp, monkeypatch, regiao, raio):
    monkeypatch.setattr(PainelPontilhado, "_RAIO_PONTO_PX", raio)
    painel = PainelPontilhado()
    painel.setStyleSheet("background: #121211;")
    painel.resize(300, 220)

    inteiro = painel.grab().toImage()
    pedaco = QPixmap(regiao.size())
    pedaco.fill(Qt.GlobalColor.transparent)
    painel.render(pedaco, QPoint(0, 0), QRegion(regiao))
    parcial = pedaco.toImage()

    for y in range(regiao.height()):
        for x in range(regiao.width()):
            esperado = inteiro.pixelColor(regiao.x() + x, regiao.y() + y)
            obtido = parcial.pixelColor(x, y)
            assert obtido == esperado, (
                f"pixel ({regiao.x() + x}, {regiao.y() + y}) repintado sozinho saiu "
                f"{obtido.name()}, e na pintura inteira é {esperado.name()}"
            )
    painel.deleteLater()
