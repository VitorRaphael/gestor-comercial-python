"""Dashboard Consolidado Mensal: KPIs, composição por forma de pagamento (com
barra de proporção) e mix de vendas do mês (ranking com barra de destaque).

Só QLabel/QProgressBar/QFrame de propósito — a máquina do food truck é um
Celeron com 4GB, sem margem para biblioteca de gráfico. Carrega sob demanda: o
construtor não consulta nada, só `atualizar()` (chamada pela navegação, ao
entrar na aba) busca `CaixaService.resumo_mensal`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
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
from gestor_comercial.ui.widgets.kpi_card import CardKpi

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

_ROTULO_FORMA = {
    "CREDITO": "Crédito",
    "DEBITO": "Débito",
    "DINHEIRO": "Dinheiro",
    "PIX": "PIX",
    "CONSUMO_INTERNO": "Consumo interno",
}

_MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


class DashboardMensalView(QWidget):
    """Painel gerencial acumulado do mês civil, com seletor de meses anteriores."""

    def __init__(self, caixa_service: CaixaService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._caixas = caixa_service
        self._montar_layout()

    # ------------------------------------------------------------------
    # Montagem do layout
    # ------------------------------------------------------------------

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(0, 0, 0, 0)
        layout_externo.setSpacing(16)

        layout_externo.addLayout(self._montar_filtro_mes())

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout_externo.addWidget(self._label_erro)

        grade_cards = QGridLayout()
        grade_cards.setSpacing(14)
        layout_externo.addLayout(grade_cards)
        self._cards: dict[str, CardKpi] = {}
        for coluna, chave_titulo in enumerate(
            ["faturamento", "turnos", "ticket_medio", "cancelamentos"]
        ):
            card = CardKpi(_TITULOS_CARD[chave_titulo])
            self._cards[chave_titulo] = card
            grade_cards.addWidget(card, 0, coluna)

        painel_graficos = QHBoxLayout()
        painel_graficos.setSpacing(16)
        painel_graficos.addWidget(self._montar_painel_formas_pagamento(), 35)
        painel_graficos.addWidget(self._montar_painel_ranking(), 65)
        layout_externo.addLayout(painel_graficos, 1)

    def _montar_filtro_mes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.addStretch()

        frame_mes = QFrame()
        frame_mes.setObjectName("relatoriosFiltroMes")
        layout_mes = QHBoxLayout(frame_mes)
        layout_mes.setContentsMargins(12, 4, 8, 4)
        layout_mes.setSpacing(4)
        icone = QLabel("📅")
        icone.setObjectName("relatoriosFiltroMesIcone")
        layout_mes.addWidget(icone)
        self._seletor_mes = QComboBox()
        self._seletor_mes.setObjectName("relatoriosComboMes")
        self._popular_seletor_mes()
        self._seletor_mes.currentIndexChanged.connect(self._carregar)
        layout_mes.addWidget(self._seletor_mes)
        linha.addWidget(frame_mes)
        return linha

    def _montar_painel_formas_pagamento(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("relatoriosPainel")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        titulo = QLabel("COMPOSIÇÃO POR FORMA DE PAGAMENTO")
        titulo.setObjectName("relatoriosPainelTitulo")
        layout.addWidget(titulo)

        self._layout_formas = QVBoxLayout()
        self._layout_formas.setSpacing(12)
        layout.addLayout(self._layout_formas)
        layout.addStretch()

        rodape = QHBoxLayout()
        rotulo_total = QLabel("TOTAL")
        rotulo_total.setObjectName("relatoriosRodapeRotulo")
        rodape.addWidget(rotulo_total)
        rodape.addStretch()
        self._label_total_formas = QLabel("R$ 0,00")
        self._label_total_formas.setObjectName("relatoriosRodapeValor")
        rodape.addWidget(self._label_total_formas)
        layout.addLayout(rodape)
        return painel

    def _montar_painel_ranking(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("relatoriosPainel")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        cabecalho = QHBoxLayout()
        titulo = QLabel("MIX DE VENDAS DO MÊS")
        titulo.setObjectName("relatoriosPainelTitulo")
        cabecalho.addWidget(titulo)
        cabecalho.addStretch()
        self._label_indicador_ranking = QLabel("")
        self._label_indicador_ranking.setObjectName("relatoriosPainelIndicador")
        cabecalho.addWidget(self._label_indicador_ranking)
        layout.addLayout(cabecalho)

        self._layout_ranking = QVBoxLayout()
        self._layout_ranking.setSpacing(10)
        layout.addLayout(self._layout_ranking)
        layout.addStretch()
        return painel

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

    # ------------------------------------------------------------------
    # Carregamento / preenchimento
    # ------------------------------------------------------------------

    def atualizar(self) -> None:
        """Chamada só quando a aba é aberta — nunca no construtor (carregamento
        estritamente sob demanda). Sempre busca de novo: é assim que o painel
        reflete um fechamento de caixa feito desde a última visita à aba."""
        self._carregar()

    def periodo_atual(self) -> str:
        return self._seletor_mes.currentText()

    def conectar_mudanca_periodo(self, callback) -> None:
        self._seletor_mes.currentIndexChanged.connect(callback)

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
        self._cards["faturamento"].definir_sub_rotulo("Mês corrente")
        self._cards["turnos"].definir_valor(str(resumo.turnos_fechados))
        self._cards["ticket_medio"].definir_valor(_formatar_reais(resumo.ticket_medio))
        self._cards["ticket_medio"].definir_sub_rotulo(f"{_contar_comandas(resumo)} comandas")
        self._cards["cancelamentos"].definir_valor(f"{resumo.cancelamentos_quantidade} un")
        self._cards["cancelamentos"].definir_sub_rotulo(_formatar_reais(resumo.cancelamentos_valor))

        self._preencher_formas_pagamento(resumo)
        self._preencher_ranking(resumo)

    def _preencher_formas_pagamento(self, resumo: ResumoMensal) -> None:
        _limpar_layout(self._layout_formas)
        for item in resumo.formas_pagamento:
            self._layout_formas.addLayout(
                _criar_linha_forma(
                    _ROTULO_FORMA.get(item.forma.value, item.forma.value),
                    item.valor,
                    item.percentual,
                )
            )
        self._label_total_formas.setText(_formatar_reais(resumo.faturamento_bruto))

    def _preencher_ranking(self, resumo: ResumoMensal) -> None:
        _limpar_layout(self._layout_ranking)
        maior_valor = max((item.valor_total for item in resumo.ranking_produtos), default=Decimal(0))
        if resumo.ranking_produtos:
            lider = resumo.ranking_produtos[0]
            self._label_indicador_ranking.setText(f"↗ {_formatar_reais(lider.valor_total)}")
        else:
            self._label_indicador_ranking.setText("")

        for indice, item in enumerate(resumo.ranking_produtos, start=1):
            proporcao = int((item.valor_total / maior_valor) * 100) if maior_valor else 0
            self._layout_ranking.addLayout(
                _criar_linha_ranking(indice, item.produto_nome, item.quantidade, item.valor_total, proporcao)
            )


def _contar_comandas(resumo: ResumoMensal) -> int:
    # `ResumoMensal` não expõe contagem de comandas separadamente; aproxima
    # pelo total de faturamento / ticket médio (mesma conta usada pra chegar
    # no ticket médio na origem), evitando nova consulta ao banco.
    if resumo.ticket_medio == 0:
        return 0
    return int(resumo.faturamento_bruto / resumo.ticket_medio)


def _criar_linha_forma(nome: str, valor: Decimal, percentual: Decimal) -> QVBoxLayout:
    bloco = QVBoxLayout()
    bloco.setSpacing(4)

    topo = QHBoxLayout()
    label_nome = QLabel(nome)
    label_nome.setObjectName("relatoriosFormaNome")
    topo.addWidget(label_nome)
    topo.addStretch()
    label_valor = QLabel(_formatar_reais(valor))
    label_valor.setObjectName("relatoriosFormaValor")
    topo.addWidget(label_valor)
    bloco.addLayout(topo)

    barra = QProgressBar()
    barra.setObjectName("relatoriosBarraForma")
    barra.setRange(0, 100)
    barra.setValue(min(100, max(0, int(percentual))))
    barra.setTextVisible(False)
    bloco.addWidget(barra)

    label_percentual = QLabel(f"{percentual:.1f}%")
    label_percentual.setObjectName("relatoriosFormaPercentual")
    bloco.addWidget(label_percentual)
    return bloco


def _criar_linha_ranking(
    indice: int, produto_nome: str, quantidade: int, valor_total: Decimal, proporcao: int
) -> QVBoxLayout:
    bloco = QVBoxLayout()
    bloco.setSpacing(4)

    topo = QHBoxLayout()
    topo.setSpacing(10)
    label_indice = QLabel(f"{indice:02d}")
    label_indice.setObjectName("relatoriosRankIndice")
    label_indice.setFixedWidth(24)
    topo.addWidget(label_indice)

    label_nome = QLabel(produto_nome)
    label_nome.setObjectName("relatoriosRankNome")
    topo.addWidget(label_nome, 1)

    label_qtd = QLabel(f"{quantidade} un")
    label_qtd.setObjectName("relatoriosRankQtd")
    topo.addWidget(label_qtd)

    label_valor = QLabel(_formatar_reais(valor_total))
    label_valor.setObjectName("relatoriosRankValor")
    label_valor.setFixedWidth(90)
    label_valor.setAlignment(label_valor.alignment() | _ALINHAR_DIREITA)
    topo.addWidget(label_valor)
    bloco.addLayout(topo)

    barra = QProgressBar()
    barra.setObjectName("relatoriosBarraRanking")
    barra.setRange(0, 100)
    barra.setValue(min(100, max(0, proporcao)))
    barra.setTextVisible(False)
    bloco.addWidget(barra)
    return bloco


def _limpar_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        sub_layout = item.layout()
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif sub_layout is not None:
            _limpar_layout(sub_layout)
            sub_layout.deleteLater()


_TITULOS_CARD = {
    "faturamento": "Faturamento bruto",
    "turnos": "Turnos fechados",
    "ticket_medio": "Ticket médio",
    "cancelamentos": "Cancelamentos",
}

_ALINHAR_DIREITA = Qt.AlignmentFlag.AlignRight


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")
