"""Modal de cancelamento (item ou comanda inteira): motivo + PIN de gerente.

Porte visual do modal `Cancelar` do front-end web
(`GESTOR COMERCIAL/.../desktop/js/app.js`, função `confirmarCancelamento`).
Reautenticação por PIN, não a sessão corrente — o atendente pode estar
logado, mas só um gerente autoriza um cancelamento (§3.1). Quem valida o
PIN e o motivo de verdade é `ComandaService.cancelar_item`/`cancelar`; este
modal só coleta os dois campos.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class CancelamentoDialog(QDialog):
    """Modal genérico de cancelamento: motivo obrigatório + PIN de gerente."""

    def __init__(self, titulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_motivo = QLineEdit()
        self._campo_motivo.setPlaceholderText("Ex.: pedido errado, cliente desistiu")
        formulario.addRow("Motivo", self._campo_motivo)

        self._campo_pin_gerente = QLineEdit()
        self._campo_pin_gerente.setEchoMode(QLineEdit.EchoMode.Password)
        formulario.addRow("PIN do gerente", self._campo_pin_gerente)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Cancelar")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Voltar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[str, str]:
        motivo = self._campo_motivo.text().strip()
        pin_gerente = self._campo_pin_gerente.text().strip()
        return motivo, pin_gerente
