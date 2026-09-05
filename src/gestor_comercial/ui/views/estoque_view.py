"""Tela de Estoque -- placeholder.

O módulo de controle de estoque está no backlog pós-V1 (ver
`docs/arquitetura.md` §3: "Fora da V1"). Esta view só existe para o item
"Estoque" ter destino na sidebar/Central de Loja sem quebrar a navegação;
a implementação real (insumos, saldos mínimos, custo) entra quando a fase
de estoque começar.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class EstoqueView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(4)

        eyebrow = QLabel("CATÁLOGO E PRODUÇÃO")
        eyebrow.setObjectName("configEyebrow")
        layout.addWidget(eyebrow)

        titulo = QLabel("Estoque")
        titulo.setObjectName("configTitulo")
        layout.addWidget(titulo)

        subtitulo = QLabel("Insumos, saldos mínimos e custo -- em breve.")
        subtitulo.setObjectName("configSubtitulo")
        layout.addWidget(subtitulo)

        layout.addStretch()

    def atualizar(self) -> None:
        """Sem estado próprio ainda -- existe só para casar com a
        convenção de recarregar do dict de destinos em `MainWindow`."""
