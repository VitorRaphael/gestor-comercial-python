"""Hub central da área "Loja": 4 atalhos administrativos + voltar ao PDV.

Agrupa Cardápio, Impressoras, Funcionários e Relatórios atrás de um único
ponto de entrada na sidebar (ver `MainWindow._abrir_loja`), para não poluir
a navegação do dia a dia do operador de caixa nem exigir logout/login toda
vez que um gerente precisa mexer no cardápio no meio do expediente.
"""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import Signal

_DESTINOS = ("Cardápio", "Impressoras", "Funcionários", "Relatórios")


class LojaHubView(QWidget):
    destino_selecionado = Signal(str)
    voltar = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(20)

        titulo = QLabel("Loja")
        titulo.setStyleSheet("font-weight: 600; font-size: 20px;")
        layout.addWidget(titulo)

        grade = QGridLayout()
        grade.setSpacing(12)
        for indice, rotulo in enumerate(_DESTINOS):
            botao = QPushButton(rotulo)
            botao.setMinimumHeight(72)
            botao.setProperty("variante", "loja-hub")
            botao.clicked.connect(lambda _checked=False, r=rotulo: self.destino_selecionado.emit(r))
            grade.addWidget(botao, indice // 2, indice % 2)
        layout.addLayout(grade)

        botao_voltar = QPushButton("← Voltar ao PDV")
        botao_voltar.clicked.connect(self.voltar.emit)
        layout.addWidget(botao_voltar)

        layout.addStretch()
