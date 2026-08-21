"""Tela de login por PIN — porte visual de `.tela-login`/`.cartao-login` do
front-end web (`GESTOR COMERCIAL/.../desktop/index.html`).

Sem teclado físico confiável na máquina do food truck: o funcionário digita
o PIN só pelo teclado numérico em tela.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.services.auth_service import PIN_MAX_DIGITOS, AuthService
from gestor_comercial.services.exceptions import NaoAutorizadoError

_TECLAS = [
    ["1", "2", "3"],
    ["4", "5", "6"],
    ["7", "8", "9"],
    ["limpar", "0", "apagar"],
]


class LoginView(QWidget):
    """Pin pad de login. Emite `autenticado` com o funcionário ao logar."""

    autenticado = Signal(Funcionario)

    def __init__(self, auth_service: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tela-login")
        self._auth_service = auth_service
        self._pin = ""

        self._montar_layout()

    def _montar_layout(self) -> None:
        cartao = QFrame(self)
        cartao.setObjectName("cartao-login")
        cartao.setFixedWidth(340)
        layout_cartao = QVBoxLayout(cartao)
        layout_cartao.setContentsMargins(28, 32, 28, 32)
        layout_cartao.setSpacing(0)

        marca = QLabel("Gestor Comercial")
        marca.setStyleSheet("font-weight: 600; font-size: 16px;")
        marca.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_cartao.addWidget(marca)

        subtitulo = QLabel("Digite seu PIN para continuar")
        subtitulo.setObjectName("login-subtitulo")
        subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_cartao.addSpacing(10)
        layout_cartao.addWidget(subtitulo)
        layout_cartao.addSpacing(12)

        self._campo_pin = QLineEdit()
        self._campo_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self._campo_pin.setMaxLength(PIN_MAX_DIGITOS)
        self._campo_pin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._campo_pin.setReadOnly(True)
        layout_cartao.addWidget(self._campo_pin)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        self._label_erro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_erro.setFixedHeight(18)
        layout_cartao.addWidget(self._label_erro)
        layout_cartao.addSpacing(8)

        layout_cartao.addLayout(self._montar_teclado())
        layout_cartao.addSpacing(14)

        self._botao_entrar = QPushButton("Entrar")
        self._botao_entrar.setProperty("variante", "primario")
        self._botao_entrar.clicked.connect(self._tentar_login)
        layout_cartao.addWidget(self._botao_entrar)

        layout_externo = QVBoxLayout(self)
        layout_externo.addStretch()
        layout_externo.addWidget(cartao, 0, Qt.AlignmentFlag.AlignCenter)
        layout_externo.addStretch()

    def _montar_teclado(self) -> QGridLayout:
        grade = QGridLayout()
        grade.setSpacing(8)
        for linha, teclas in enumerate(_TECLAS):
            for coluna, tecla in enumerate(teclas):
                botao = QPushButton(_rotulo_tecla(tecla))
                botao.setProperty("variante", "secundario")
                botao.setFixedHeight(48)
                botao.clicked.connect(lambda _checked=False, t=tecla: self._tecla_pressionada(t))
                grade.addWidget(botao, linha, coluna)
        return grade

    def _tecla_pressionada(self, tecla: str) -> None:
        self._label_erro.setText("")
        if tecla == "apagar":
            self._pin = self._pin[:-1]
        elif tecla == "limpar":
            self._pin = ""
        elif len(self._pin) < PIN_MAX_DIGITOS:
            self._pin += tecla
        self._campo_pin.setText(self._pin)

    def _tentar_login(self) -> None:
        try:
            funcionario = self._auth_service.login(self._pin)
        except NaoAutorizadoError as erro:
            self._label_erro.setText(str(erro))
            self._pin = ""
            self._campo_pin.setText("")
            return
        self._pin = ""
        self._campo_pin.setText("")
        self.autenticado.emit(funcionario)


def _rotulo_tecla(tecla: str) -> str:
    return {"apagar": "⌫", "limpar": "C"}.get(tecla, tecla)
