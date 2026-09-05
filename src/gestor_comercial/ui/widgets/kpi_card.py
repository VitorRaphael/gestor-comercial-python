"""Card de KPI reutilizado pelo módulo de Relatórios (Histórico Diário e
Dashboard Mensal): rótulo em caixa alta, valor em destaque e um sub-rótulo
opcional. Estilo definido em `ui/theme/qss_app.py` (`#relatoriosKpiCard`).
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

_OBJETO_VALOR = {
    "neutro": "relatoriosKpiValor",
    "positivo": "relatoriosKpiValorPositivo",
    "negativo": "relatoriosKpiValorNegativo",
}


class CardKpi(QFrame):
    """Card de métrica: RÓTULO (caixa alta) + valor grande + sub-rótulo opcional."""

    def __init__(self, rotulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("relatoriosKpiCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        self._rotulo = QLabel(rotulo.upper())
        self._rotulo.setObjectName("relatoriosKpiRotulo")
        layout.addWidget(self._rotulo)

        self._label_valor = QLabel("—")
        self._label_valor.setObjectName("relatoriosKpiValor")
        layout.addWidget(self._label_valor)

        self._label_sub = QLabel("")
        self._label_sub.setObjectName("relatoriosKpiSub")
        self._label_sub.hide()
        layout.addWidget(self._label_sub)

    def definir_valor(self, texto: str, *, tom: str = "neutro") -> None:
        self._label_valor.setText(texto)
        self._label_valor.setObjectName(_OBJETO_VALOR.get(tom, _OBJETO_VALOR["neutro"]))
        # Reaplica a folha de estilo ao trocar o objectName em runtime — QSS
        # só é reavaliado por seletor de #id na próxima polish/unpolish.
        self._label_valor.style().unpolish(self._label_valor)
        self._label_valor.style().polish(self._label_valor)

    def definir_sub_rotulo(self, texto: str | None) -> None:
        if texto:
            self._label_sub.setText(texto.upper())
            self._label_sub.show()
        else:
            self._label_sub.hide()
