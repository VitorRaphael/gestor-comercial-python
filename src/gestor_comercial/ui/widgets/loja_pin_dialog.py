"""Elevação rápida por PIN para a área "Loja" da sidebar.

Diferente de `SenhaGerenteDialog` (que reautentica contra o PIN de um
`Usuario` cadastrado), este PIN é um código de supervisor único e fixo,
compartilhado por quem tem autoridade para abrir Cardápio, Impressoras,
Funcionários e Relatórios sem precisar deslogar o operador de caixa que
está com a sessão aberta. Por isso não passa por `AuthService`: é só um
hash SHA-256 fixo, comparado em tempo constante.
"""

from __future__ import annotations

import hashlib

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

_PIN_LOJA_HASH = hashlib.sha256(b"050727").hexdigest()


def _confere_pin_loja(pin: str) -> bool:
    import hmac

    return hmac.compare_digest(hashlib.sha256(pin.encode()).hexdigest(), _PIN_LOJA_HASH)


class LojaPinDialog(QDialog):
    """Pede o PIN de supervisor da área Loja e só fecha (accept) quando bate."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Área Loja — PIN de supervisor")

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_pin = QLineEdit()
        self._campo_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self._campo_pin.returnPressed.connect(self._confirmar)
        formulario.addRow("PIN da Loja", self._campo_pin)
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
        if not _confere_pin_loja(pin):
            self._label_erro.setText("PIN inválido.")
            self._campo_pin.clear()
            self._campo_pin.setFocus()
            return
        self.accept()

    def closeEvent(self, event) -> None:  # noqa: N802 - override Qt
        # Limpa o PIN digitado da memória do widget antes de descartar o
        # modal — não há motivo pra ele sobreviver no heap do Celeron.
        self._campo_pin.clear()
        super().closeEvent(event)
