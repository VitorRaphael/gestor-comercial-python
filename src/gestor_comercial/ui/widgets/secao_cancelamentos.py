"""Auditoria de Itens Cancelados: os três níveis do relatório na tela (§ Auditoria
de Itens Cancelados).

Componente único, reusado por `CaixaView` (turno em andamento) e por
`HistoricoCaixaView` (fechamentos passados) — para os dois a leitura vem do
mesmo `CaixaService.resumo_cancelamentos`, então o jeito de mostrar não deve
divergir entre os dois lugares.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.services.caixa_service import ResumoCancelamentos

_COLUNAS_POR_PRODUTO = ["Produto", "Qtd cancelada", "Subtotal"]
_COLUNAS_DETALHADO = ["Horário", "Origem", "Item", "Autorizado por", "Motivo"]


class SecaoCancelamentos(QWidget):
    """Totalizador + consolidado por produto + histórico cronológico de cancelamentos."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        titulo = QLabel("Itens Cancelados no Turno")
        titulo.setStyleSheet("font-weight: 600; font-size: 15px;")
        layout.addWidget(titulo)

        self._label_totais = QLabel("")
        layout.addWidget(self._label_totais)

        self._label_por_produto = QLabel("Por produto")
        self._label_por_produto.setStyleSheet("font-weight: 600; font-size: 12px;")
        layout.addWidget(self._label_por_produto)

        self._tabela_por_produto = QTableWidget(0, len(_COLUNAS_POR_PRODUTO))
        self._tabela_por_produto.setHorizontalHeaderLabels(_COLUNAS_POR_PRODUTO)
        self._tabela_por_produto.verticalHeader().setVisible(False)
        self._tabela_por_produto.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_por_produto.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tabela_por_produto.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self._tabela_por_produto)

        self._label_detalhado = QLabel("Histórico de cancelamentos")
        self._label_detalhado.setStyleSheet("font-weight: 600; font-size: 12px;")
        layout.addWidget(self._label_detalhado)

        self._tabela_detalhado = QTableWidget(0, len(_COLUNAS_DETALHADO))
        self._tabela_detalhado.setHorizontalHeaderLabels(_COLUNAS_DETALHADO)
        self._tabela_detalhado.verticalHeader().setVisible(False)
        self._tabela_detalhado.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_detalhado.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tabela_detalhado.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self._tabela_detalhado)

    def carregar(self, resumo: ResumoCancelamentos) -> None:
        if resumo.quantidade_total == 0:
            self._label_totais.setText("Nenhum item cancelado neste turno.")
            self._label_por_produto.setVisible(False)
            self._label_detalhado.setVisible(False)
            self._tabela_por_produto.setVisible(False)
            self._tabela_detalhado.setVisible(False)
            self._tabela_por_produto.setRowCount(0)
            self._tabela_detalhado.setRowCount(0)
            return

        self._label_por_produto.setVisible(True)
        self._label_detalhado.setVisible(True)
        self._tabela_por_produto.setVisible(True)
        self._tabela_detalhado.setVisible(True)

        self._label_totais.setText(
            f"Quantidade total cancelada: {resumo.quantidade_total} un"
            f"    |    Impacto financeiro: {_formatar_reais(resumo.valor_total)}"
        )

        self._tabela_por_produto.setRowCount(len(resumo.por_produto))
        for linha, item in enumerate(resumo.por_produto):
            self._tabela_por_produto.setItem(linha, 0, QTableWidgetItem(item.produto_nome))
            self._tabela_por_produto.setItem(
                linha, 1, QTableWidgetItem(f"{item.quantidade} un")
            )
            self._tabela_por_produto.setItem(
                linha, 2, QTableWidgetItem(_formatar_reais(item.valor))
            )

        self._tabela_detalhado.setRowCount(len(resumo.detalhado))
        for linha, ocorrencia in enumerate(resumo.detalhado):
            self._tabela_detalhado.setItem(
                linha, 0, QTableWidgetItem(ocorrencia.quando.strftime("%H:%M"))
            )
            self._tabela_detalhado.setItem(linha, 1, QTableWidgetItem(ocorrencia.origem))
            self._tabela_detalhado.setItem(
                linha, 2, QTableWidgetItem(f"{ocorrencia.quantidade}x {ocorrencia.produto_nome}")
            )
            self._tabela_detalhado.setItem(
                linha, 3, QTableWidgetItem(ocorrencia.autorizado_por)
            )
            self._tabela_detalhado.setItem(
                linha, 4, QTableWidgetItem(ocorrencia.motivo or "—")
            )


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")
