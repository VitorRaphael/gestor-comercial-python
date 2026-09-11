"""Token de tema → `QColor`, aceitando as duas grafias que a paleta usa.

A paleta (`tokens.py`) foi escrita para o QSS, e o QSS aceita tanto `#1C1C1A`
quanto `rgba(255, 255, 255, 0.08)`. O `QColor` do Qt **não** aceita a segunda:
`QColor("rgba(255, 255, 255, 0.08)")` devolve uma cor inválida, que pinta como
preto opaco — sem erro, sem aviso.

Quem pinta com `QPainter` lendo token (`thumbnail_cache`, os delegados do
Cardápio) caía nisso em silêncio: a borda do placeholder das miniaturas saía
preta no tema escuro, onde o token é `rgba(255, 255, 255, 0.08)`, desde que a
paleta "Concreto" trocou os hex por transparências (§9.11).
"""

from __future__ import annotations

import re

from PySide6.QtGui import QColor

_RGBA = re.compile(
    r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([0-9]*\.?[0-9]+)\s*)?\)"
)


def cor_do_token(valor: str) -> QColor:
    """`QColor` de um valor de token, em hex ou em `rgb()`/`rgba()` do CSS.

    O alfa do CSS vai de 0 a 1; o do Qt, de 0 a 255 — a conversão arredonda,
    então `0.08` vira 20, o mesmo que o QSS usa ao pintar o mesmo token.
    """
    casou = _RGBA.fullmatch(valor.strip())
    if casou is None:
        return QColor(valor)
    vermelho, verde, azul, alfa = casou.groups()
    cor = QColor(int(vermelho), int(verde), int(azul))
    if alfa is not None:
        cor.setAlpha(max(0, min(255, round(float(alfa) * 255))))
    return cor
