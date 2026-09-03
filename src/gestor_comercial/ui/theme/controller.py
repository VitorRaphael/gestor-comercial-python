"""Estado do tema claro/escuro do app inteiro, num único lugar.

O app já tinha o alternador claro/escuro na tela de login (`login_view.py`),
mas escopado só a ela — trocar de tema ali não mudava o resto do shell (ver
`main_window.py`) porque cada tela vivia com sua própria cópia da paleta.
Este controller substitui isso por um estado único: qualquer widget que
alterne o tema (a pílula do login ou a da sidebar) chama `alternar_para`,
que recalcula `app.setStyleSheet(...)` pra janela inteira e emite `mudou`
pros widgets que precisam reagir além do QSS (ex.: o logo isométrico do
login, pintado via `QPainter`, não CSS).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from gestor_comercial.ui.theme import tokens
from gestor_comercial.ui.theme.qss_app import construir_qss_app


class ThemeController(QObject):
    mudou = Signal(dict)

    _instancia: "ThemeController | None" = None

    def __init__(self) -> None:
        super().__init__()
        self._claro = False
        self._tokens = tokens.TEMA_ESCURO

    @classmethod
    def instancia(cls) -> "ThemeController":
        if cls._instancia is None:
            cls._instancia = cls()
        return cls._instancia

    @property
    def tokens_atuais(self) -> dict[str, str]:
        return self._tokens

    @property
    def claro(self) -> bool:
        return self._claro

    def aplicar_inicial(self) -> None:
        """Chamado uma vez, no boot do app (ver `main.py`)."""
        app = QApplication.instance()
        assert app is not None
        app.setStyleSheet(construir_qss_app(self._tokens))

    def alternar_para(self, claro: bool) -> None:
        if claro == self._claro:
            return
        self._claro = claro
        self._tokens = tokens.TEMA_CLARO if claro else tokens.TEMA_ESCURO
        app = QApplication.instance()
        assert app is not None
        app.setStyleSheet(construir_qss_app(self._tokens))
        self.mudou.emit(self._tokens)
