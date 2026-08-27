"""Reautenticação por PIN de gerente para acessar uma área sensível da sidebar
(hoje só "Relatórios"), mesmo com um gerente já logado no PDV.

Mesmo padrão de `CancelamentoDialog`/`PagamentoDialog`: reautenticação por
PIN digitado na hora, não a sessão corrente — o caixa pode estar destravado
na mão de qualquer um, e "Relatórios" expõe faturamento e diferença de caixa
de todo o mês. Quem confere o PIN de verdade é `AuthService.validar_pin_gerente`;
este modal só coleta o dígito e mantém a tela aberta em caso de erro, para o
gerente poder tentar de novo sem reabrir o menu.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.exceptions import AcessoNegadoError, NaoAutorizadoError


class SenhaGerenteDialog(QDialog):
    """Pede o PIN do gerente e só fecha (accept) quando ele bate."""

    def __init__(self, auth_service: AuthService, titulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auth = auth_service
        self.setWindowTitle(titulo)

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_pin = QLineEdit()
        self._campo_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self._campo_pin.returnPressed.connect(self._confirmar)
        formulario.addRow("PIN do gerente", self._campo_pin)
        layout.addLayout(formulario)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout.addWidget(self._label_erro)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Entrar")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

        self._campo_pin.setFocus()

    def _confirmar(self) -> None:
        pin = self._campo_pin.text().strip()
        try:
            self._auth.validar_pin_gerente(pin)
        except (NaoAutorizadoError, AcessoNegadoError) as erro:
            self._label_erro.setText(str(erro))
            self._campo_pin.clear()
            self._campo_pin.setFocus()
            return
        self.accept()
