"""Estado do tema claro/escuro do app inteiro, num único lugar.

O app já tinha o alternador claro/escuro na tela de login (`login_view.py`),
mas escopado só a ela — trocar de tema ali não mudava o resto do shell (ver
`main_window.py`) porque cada tela vivia com sua própria cópia da paleta.
Este controller substitui isso por um estado único: qualquer widget que
alterne o tema (a pílula do login ou a da sidebar) chama `alternar_para`,
que recalcula `app.setStyleSheet(...)` pra janela inteira e emite `mudou`
pros widgets que precisam reagir além do QSS (ex.: o logo isométrico do
login, pintado via `QPainter`, não CSS).

## Persistência

O tema escolhido sobrevive ao fechamento do programa. O controller continua
sendo a ÚNICA fonte do tema em memória; o banco é só onde ele é lembrado. No
boot, `restaurar` recebe o lugar onde ler e gravar (`ArmazemDeTema`, que em
produção é o `PreferenciaService`) e aplica o tema salvo ANTES de qualquer
janela ser montada — as telas já nascem na paleta certa, sem repintura. Daí em
diante todo `alternar_para` grava, e é o único caminho de gravação: a pílula de
Configurações não sabe que existe banco.
"""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from gestor_comercial.ui.theme import tokens
from gestor_comercial.ui.theme.qss_app import construir_qss_app


class ArmazemDeTema(Protocol):
    """Onde o tema é lembrado entre uma abertura e outra do programa."""

    def tema_claro_gravado(self) -> bool | None: ...

    def gravar_tema(self, claro: bool) -> None: ...


class ThemeController(QObject):
    mudou = Signal(dict)

    _instancia: "ThemeController | None" = None

    def __init__(self) -> None:
        super().__init__()
        self._claro = False
        self._tokens = tokens.TEMA_ESCURO
        self._armazem: ArmazemDeTema | None = None

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
        """Chamado uma vez, no boot do app (ver `main.py`).

        Aplica o tema padrão antes de o banco existir, para a caixa "Erro ao
        iniciar" sair no visual do app se o banco não subir. O tema escolhido
        pelo operador entra logo depois, em `restaurar`.
        """
        self._aplicar_qss()

    def restaurar(self, armazem: ArmazemDeTema) -> None:
        """Aplica o tema gravado e passa a gravar cada troca daqui em diante.

        Chamado no boot, com o banco pronto e antes de a `MainWindow` existir:
        nenhum widget foi montado ainda, então trocar a paleta aqui custa um
        `setStyleSheet` sem nada para repolir, e ninguém escuta `mudou` — por
        isso ele não é emitido. Também não grava de volta o que acabou de ler.
        """
        self._armazem = armazem
        claro = armazem.tema_claro_gravado()
        if claro is None or claro == self._claro:
            return
        self._definir(claro)
        self._aplicar_qss()

    def alternar_para(self, claro: bool) -> None:
        if claro == self._claro:
            return
        self._definir(claro)
        self._aplicar_qss()
        # Grava ANTES de avisar os assinantes: uma tela que estoure ao
        # repintar não pode custar a preferência. E depois de aplicar: o
        # armazém nunca levanta (degrada sozinho), mas o visual é o que o
        # operador pediu e vem primeiro.
        if self._armazem is not None:
            self._armazem.gravar_tema(claro)
        self.mudou.emit(self._tokens)

    def _definir(self, claro: bool) -> None:
        self._claro = claro
        self._tokens = tokens.TEMA_CLARO if claro else tokens.TEMA_ESCURO

    def _aplicar_qss(self) -> None:
        app = QApplication.instance()
        assert app is not None
        app.setStyleSheet(construir_qss_app(self._tokens))
