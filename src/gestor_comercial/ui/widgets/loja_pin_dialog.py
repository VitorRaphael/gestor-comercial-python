"""Elevação rápida por PIN para a área "Loja" da sidebar.

Antes tinha um código de supervisor único e fixo (hash SHA-256 embutido no
próprio arquivo), sem passar por `AuthService` nem por `LojaConfig` — pura
duplicação do que já existia no módulo "Senhas e Acesso" (§3.13). Unificado:
agora reautentica contra a Senha Master (Dono, Nível 3 da cascata) através
de `AuthService.validar_pin_dono`, igual a `GerentePinDialog` faz para o
Nível 2 — mesmo mecanismo, hash+salt vindos de `LojaConfig`, PIN padrão de
fábrica "050727" (`LojaConfigService.SENHA_MASTER_PADRAO`).
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
from gestor_comercial.ui.theme.controller import ThemeController


class LojaPinDialog(QDialog):
    """Pede a Senha Master (Dono) da área Loja e só fecha (accept) quando bate."""

    def __init__(self, auth_service: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auth = auth_service
        self.setWindowTitle("Área Loja — PIN de supervisor")

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_pin = QLineEdit()
        self._campo_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self._campo_pin.returnPressed.connect(self._confirmar)
        formulario.addRow("PIN da Loja", self._campo_pin)
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
            self._auth.validar_pin_dono(pin)
        except (AcessoNegadoError, NaoAutorizadoError) as erro:
            self._label_erro.setText(str(erro))
            self._campo_pin.clear()
            self._campo_pin.setFocus()
            return
        self.accept()

    def done(self, resultado: int) -> None:  # noqa: N802 - override Qt
        # Limpa o PIN digitado da memória do widget antes de descartar o
        # modal — não há motivo pra ele sobreviver no heap do Celeron.
        #
        # O hook certo é `done()`, não `closeEvent()` (§3.9): `accept()` (botão
        # Entrar), `reject()` (Cancelar) e o Esc passam todos por `done()`, que
        # faz `hide()` — não `close()`. Só o X da janela dispara `closeEvent`,
        # e um modal de PIN nem sempre tem X. Medido: com `closeEvent`, o campo
        # continuava com o PIN depois do `exec()` nos três caminhos.
        self._campo_pin.clear()
        super().done(resultado)
