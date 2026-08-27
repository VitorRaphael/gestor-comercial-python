"""Dashboard Consolidado Mensal: cards de KPI + tabelas do mês selecionado.

Só QLabel e QTableWidget de propósito — a máquina do food truck é um Celeron
com 4GB, sem margem para biblioteca de gráfico. Carrega sob demanda: o
construtor não consulta nada, só `atualizar()` (chamada pela navegação, ao
entrar na aba) busca `CaixaService.resumo_mensal`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.services.caixa_service import CaixaService, ResumoMensal
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

_ROTULO_FORMA = {
    "CREDITO": "Cartão de crédito",
    "DEBITO": "Cartão de débito",
    "DINHEIRO": "Dinheiro",
    "PIX": "PIX",
    "CONSUMO_INTERNO": "Consumo interno",
}

_MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

_COLUNAS_RANKING = ["Produto", "Qtd vendida", "Faturamento"]


class DashboardMensalView(QWidget):
    """Painel gerencial acumulado do mês civil, com seletor de meses anteriores."""

    def __init__(self, caixa_service: CaixaService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._caixas = caixa_service
        self._montar_layout()

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)

        cabecalho = QHBoxLayout()
        titulo = QLabel("Dashboard Mensal")
        titulo.setStyleSheet("font-weight: 600; font-size: 18px;")
        cabecalho.addWidget(titulo)
        cabecalho.addStretch()

        cabecalho.addWidget(QLabel("Mês"))
        self._seletor_mes = QComboBox()
        self._popular_seletor_mes()
        self._seletor_mes.currentIndexChanged.connect(self._carregar)
        cabecalho.addWidget(self._seletor_mes)
        layout_externo.addLayout(cabecalho)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout_externo.addWidget(self._label_erro)

        self._grade_cards = QGridLayout()
        self._grade_cards.setSpacing(12)
        layout_externo.addLayout(self._grade_cards)
        self._cards: dict[str, _CardKpi] = {}
        for coluna, chave_titulo in enumerate(
            ["faturamento", "turnos", "ticket_medio", "cancelamentos"]
        ):
            card = _CardKpi(_TITULOS_CARD[chave_titulo])
            self._cards[chave_titulo] = card
            self._grade_cards.addWidget(card, 0, coluna)

        layout_tabelas = QHBoxLayout()

        coluna_formas = QVBoxLayout()
        rotulo_formas = QLabel("Composição por forma de pagamento")
        rotulo_formas.setStyleSheet("font-weight: 600; font-size: 13px;")
        coluna_formas.addWidget(rotulo_formas)
        self._tabela_formas = QTableWidget(0, 3)
        self._tabela_formas.setHorizontalHeaderLabels(["Forma", "Total", "%"])
        self._tabela_formas.verticalHeader().setVisible(False)
        self._tabela_formas.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_formas.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tabela_formas.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        coluna_formas.addWidget(self._tabela_formas)
        layout_tabelas.addLayout(coluna_formas, 1)

        coluna_ranking = QVBoxLayout()
        rotulo_ranking = QLabel("Mix de vendas do mês")
        rotulo_ranking.setStyleSheet("font-weight: 600; font-size: 13px;")
        coluna_ranking.addWidget(rotulo_ranking)
        self._tabela_ranking = QTableWidget(0, len(_COLUNAS_RANKING))
        self._tabela_ranking.setHorizontalHeaderLabels(_COLUNAS_RANKING)
        self._tabela_ranking.verticalHeader().setVisible(False)
        self._tabela_ranking.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_ranking.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tabela_ranking.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        coluna_ranking.addWidget(self._tabela_ranking)
        layout_tabelas.addLayout(coluna_ranking, 2)

        layout_externo.addLayout(layout_tabelas)

    def _popular_seletor_mes(self) -> None:
        # Mês vigente sempre entra primeiro, mesmo sem nenhum fechamento ainda —
        # é o caso normal de abrir o dashboard no primeiro dia do mês novo.
        hoje = date.today()
        self._seletor_mes.blockSignals(True)
        self._seletor_mes.clear()
        self._seletor_mes.addItem(f"{_MESES[hoje.month - 1]}/{hoje.year}", (hoje.year, hoje.month))
        ano, mes = hoje.year, hoje.month
        for _ in range(11):
            mes -= 1
            if mes == 0:
                mes = 12
                ano -= 1
            self._seletor_mes.addItem(f"{_MESES[mes - 1]}/{ano}", (ano, mes))
        self._seletor_mes.blockSignals(False)

    def atualizar(self) -> None:
        """Chamada só quando a aba é aberta — nunca no construtor (carregamento
        estritamente sob demanda). Sempre busca de novo: é assim que o painel
        reflete um fechamento de caixa feito desde a última visita à aba."""
        self._carregar()

    def _carregar(self) -> None:
        self._label_erro.setText("")
        ano_mes = self._seletor_mes.currentData()
        if ano_mes is None:
            return
        ano, mes = ano_mes
        try:
            resumo = self._caixas.resumo_mensal(ano, mes)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._preencher(resumo)

    def _preencher(self, resumo: ResumoMensal) -> None:
        self._cards["faturamento"].definir_valor(_formatar_reais(resumo.faturamento_bruto))
        self._cards["turnos"].definir_valor(str(resumo.turnos_fechados))
        self._cards["ticket_medio"].definir_valor(_formatar_reais(resumo.ticket_medio))
        self._cards["cancelamentos"].definir_valor(
            f"{resumo.cancelamentos_quantidade} un · {_formatar_reais(resumo.cancelamentos_valor)}"
        )

        self._tabela_formas.setRowCount(len(resumo.formas_pagamento))
        for linha, item in enumerate(resumo.formas_pagamento):
            self._tabela_formas.setItem(
                linha, 0, QTableWidgetItem(_ROTULO_FORMA.get(item.forma.value, item.forma.value))
            )
            self._tabela_formas.setItem(linha, 1, QTableWidgetItem(_formatar_reais(item.valor)))
            self._tabela_formas.setItem(linha, 2, QTableWidgetItem(f"{item.percentual:.1f}%"))

        self._tabela_ranking.setRowCount(len(resumo.ranking_produtos))
        for linha, item in enumerate(resumo.ranking_produtos):
            self._tabela_ranking.setItem(linha, 0, QTableWidgetItem(item.produto_nome))
            self._tabela_ranking.setItem(linha, 1, QTableWidgetItem(f"{item.quantidade} un"))
            self._tabela_ranking.setItem(linha, 2, QTableWidgetItem(_formatar_reais(item.valor_total)))


_TITULOS_CARD = {
    "faturamento": "Faturamento bruto",
    "turnos": "Turnos fechados",
    "ticket_medio": "Ticket médio",
    "cancelamentos": "Cancelamentos",
}


class _CardKpi(QFrame):
    """Card informativo leve: um rótulo e um valor grande, sem gráfico nenhum."""

    def __init__(self, titulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { border: 1px solid #333; border-radius: 8px; padding: 8px; }"
        )
        layout = QVBoxLayout(self)
        rotulo = QLabel(titulo)
        rotulo.setProperty("variante", "fraco")
        layout.addWidget(rotulo)
        self._label_valor = QLabel("—")
        self._label_valor.setStyleSheet("font-weight: 700; font-size: 20px;")
        layout.addWidget(self._label_valor)

    def definir_valor(self, texto: str) -> None:
        self._label_valor.setText(texto)


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")
