"""Elevação rápida por PIN de gerente para a área "Caixa" da sidebar.

Reautentica contra a Senha Operacional (Caixa, Nível 2) OU a Senha Master
(Dono, Nível 3) da loja (§3.13, cascata de `AuthService.validar_pin_nivel`)
— mesmo mecanismo que `AuthService.validar_pin_gerente` já usa para
autorizar cancelamento de item/comanda (ver `CancelamentoDialog`), só que
aqui trancando uma tela inteira em vez de uma ação pontual. Não há mais PIN
pessoal de `Usuario`: qualquer um dos dois segredos da loja libera."""

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
from gestor_comercial.ui.theme.controller import ThemeController


class GerentePinDialog(QDialog):
    """Pede o PIN de um gerente cadastrado e só fecha (accept) quando bate."""

    def __init__(self, auth_service: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auth = auth_service
        self.setWindowTitle("Caixa — PIN do gerente")

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_pin = QLineEdit()
        self._campo_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self._campo_pin.returnPressed.connect(self._confirmar)
        formulario.addRow("PIN do gerente", self._campo_pin)
        layout.addLayout(formulario)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet(
            f"color: {ThemeController.instancia().tokens_atuais['perigo']}; font-size: 12px;"
        )
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
        except (AcessoNegadoError, NaoAutorizadoError) as erro:
            self._label_erro.setText(str(erro))
            self._campo_pin.clear()
            self._campo_pin.setFocus()
            return
        self.accept()

    def closeEvent(self, event) -> None:  # noqa: N802 - override Qt
        # Limpa o PIN digitado da memória do widget antes de descartar o
        # modal — não há motivo pra ele sobreviver no heap do Celeron.
        self._campo_pin.clear()
        super().closeEvent(event)
