"""Dashboard Consolidado Mensal: KPIs, composição por forma de pagamento (com
barra de proporção) e mix de vendas do mês (ranking com barra de destaque).

Só QLabel/QProgressBar/QFrame de propósito — a máquina do food truck é um
Celeron com 4GB, sem margem para biblioteca de gráfico. Carrega sob demanda: o
construtor não consulta nada, só `atualizar()` (chamada pela navegação, ao
entrar na aba) busca `CaixaService.resumo_mensal`.
"""

from __future__ import annotations

from collections.abc import Callable

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
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.services.caixa_service import (
    CaixaService,
    FechamentoGaveta,
    ItemRankingAtendente,
    ResumoMensal,
)
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.ui.formatacao import formatar_reais, formatar_reais_com_sinal
from gestor_comercial.ui.widgets.kpi_card import CardKpi
from gestor_comercial.ui.widgets.thumbnail_cache import obter_pixmap
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.layout_utils import limpar_layout

# Sentinela do item "Todos" do filtro de operador — mesmo padrão do
# Histórico Diário (`historico_caixa_view._TODOS_OS_OPERADORES`).
_TODOS_OS_OPERADORES = None

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

    def __init__(
        self,
        caixa_service: CaixaService,
        funcionario_service: FuncionarioService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._caixas = caixa_service
        self._funcionarios = funcionario_service
        self._operador_selecionado: int | None = _TODOS_OS_OPERADORES
        # Mesmo padrão do Histórico Diário: nenhuma pílula vem destacada até o
        # usuário clicar em uma (igual ao seletor de operador do Login).
        self._algum_operador_clicado = False
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
        self._label_erro.setObjectName("labelErro")
        layout_externo.addWidget(self._label_erro)

        # Corpo rolável: sem isso, os painéis (formas de pagamento, mix de
        # vendas) disputavam a altura fixa da janela (máquina do food truck) e
        # o Qt ignorava a altura mínima deles, sobrepondo/cortando o conteúdo
        # em vez de simplesmente rolar — mesmo padrão do Histórico Diário
        # (`historico_caixa_view.HistoricoCaixaView._montar_layout`).
        conteudo = QWidget()
        layout_conteudo = QVBoxLayout(conteudo)
        layout_conteudo.setContentsMargins(0, 0, 4, 0)
        layout_conteudo.setSpacing(16)

        grade_cards = QGridLayout()
        grade_cards.setSpacing(14)
        layout_conteudo.addLayout(grade_cards)
        self._cards: dict[str, CardKpi] = {}
        for coluna, chave_titulo in enumerate(
            ["faturamento", "turnos", "ticket_medio", "cancelamentos"]
        ):
            card = CardKpi(_TITULOS_CARD[chave_titulo])
            self._cards[chave_titulo] = card
            grade_cards.addWidget(card, 0, coluna)

        painel_formas = self._montar_painel_formas_pagamento()
        painel_ranking = self._montar_painel_ranking()
        painel_formas.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        painel_formas.setMinimumWidth(320)
        painel_ranking.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        painel_graficos = QHBoxLayout()
        painel_graficos.setSpacing(16)
        painel_graficos.addWidget(painel_formas, 40)
        painel_graficos.addWidget(painel_ranking, 60)
        layout_conteudo.addLayout(painel_graficos)

        # §3.14 — seções complementares de fechamento, no final da tela.
        painel_fechamento = QHBoxLayout()
        painel_fechamento.setSpacing(16)
        painel_fechamento.addWidget(self._montar_painel_gaveta(), 35)
        painel_fechamento.addWidget(self._montar_painel_atendentes(), 65)
        layout_conteudo.addLayout(painel_fechamento)

        rolagem = QScrollArea()
        rolagem.setObjectName("relatoriosRolagemHistorico")
        rolagem.setWidget(conteudo)
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout_externo.addWidget(rolagem, 1)

    def _montar_filtro_mes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(8)

        self._layout_pills_operador = QHBoxLayout()
        self._layout_pills_operador.setSpacing(8)
        linha.addLayout(self._layout_pills_operador)
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

        conteudo_ranking = QWidget()
        self._layout_ranking = QVBoxLayout(conteudo_ranking)
        self._layout_ranking.setContentsMargins(0, 0, 0, 0)
        self._layout_ranking.setSpacing(12)

        rolagem = QScrollArea()
        rolagem.setObjectName("relatoriosRolagemRanking")
        rolagem.setWidget(conteudo_ranking)
        rolagem.setWidgetResizable(True)
        # Altura calculada pra caber 6 itens do ranking sem rolar: cada linha
        # tem ~46px (rótulo/qtd/valor + barra + espaçamento interno de 6px) e
        # o layout entre linhas soma 12px — o antigo 260px só exibia ~4.
        rolagem.setMinimumHeight(6 * 46 + 5 * 12)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(rolagem, 1)
        return painel

    def _montar_painel_gaveta(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("relatoriosPainel")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        titulo = QLabel("FECHAMENTO DA GAVETA")
        titulo.setObjectName("relatoriosPainelTitulo")
        layout.addWidget(titulo)

        self._label_gaveta_identificacao = QLabel("—")
        self._label_gaveta_identificacao.setObjectName("relatoriosFormaNome")
        self._label_gaveta_identificacao.setWordWrap(True)
        layout.addWidget(self._label_gaveta_identificacao)

        layout.addLayout(_linha_rotulo_valor("Total faturado", self, "_label_gaveta_faturado"))
        layout.addLayout(_linha_rotulo_valor("Saldo apurado", self, "_label_gaveta_saldo"))
        layout.addLayout(_linha_rotulo_valor("Diferença (quebra/sobra)", self, "_label_gaveta_diferenca"))
        layout.addStretch()
        return painel

    def _montar_painel_atendentes(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("relatoriosPainel")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        titulo = QLabel("PERFORMANCE POR ATENDENTE")
        titulo.setObjectName("relatoriosPainelTitulo")
        layout.addWidget(titulo)

        self._layout_atendentes = QVBoxLayout()
        self._layout_atendentes.setSpacing(10)
        layout.addLayout(self._layout_atendentes)
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
        self._popular_pills_operador()
        self._carregar()

    def periodo_atual(self) -> str:
        return self._seletor_mes.currentText()

    def conectar_mudanca_periodo(self, callback: Callable[[int], None]) -> None:
        self._seletor_mes.currentIndexChanged.connect(callback)

    def _popular_pills_operador(self) -> None:
        # Mesmo padrão do Histórico Diário: reconstrói do zero pra refletir
        # um Caixa desativado/cadastrado entre duas visitas à aba.
        selecionado = self._operador_selecionado
        limpar_layout(self._layout_pills_operador)

        opcoes: list[tuple[str, int | None]] = [("Todos", _TODOS_OS_OPERADORES)]
        opcoes.extend(
            (operador.nome, operador.id) for operador in self._funcionarios.listar_operadores_caixa()
        )
        if selecionado not in (valor for _, valor in opcoes):
            selecionado = _TODOS_OS_OPERADORES

        for nome, valor in opcoes:
            pill = QPushButton(nome)
            pill.setProperty("variante", "filtro-pill")
            pill.setProperty("ativo", self._algum_operador_clicado and valor == selecionado)
            pill.clicked.connect(lambda _=False, v=valor: self._selecionar_operador(v))
            self._layout_pills_operador.addWidget(pill)
        self._operador_selecionado = selecionado

    def _selecionar_operador(self, operador_id: int | None) -> None:
        self._operador_selecionado = operador_id
        self._algum_operador_clicado = True
        self._popular_pills_operador()
        self._carregar()

    def _carregar(self) -> None:
        self._label_erro.setText("")
        ano_mes = self._seletor_mes.currentData()
        if ano_mes is None:
            return
        ano, mes = ano_mes
        usuario_id = self._operador_selecionado
        try:
            resumo = self._caixas.resumo_mensal(ano, mes, usuario_id)
            fechamentos = self._caixas.listar_fechamentos_do_mes_civil(ano, mes, usuario_id)
            gaveta = self._caixas.fechamento_da_gaveta_do_periodo([c.id for c in fechamentos])
            ranking_atendentes = self._caixas.ranking_por_atendente([c.id for c in fechamentos])
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._preencher(resumo)
        self._preencher_gaveta(gaveta)
        self._preencher_atendentes(ranking_atendentes)

    def _preencher(self, resumo: ResumoMensal) -> None:
        self._cards["faturamento"].definir_valor(formatar_reais(resumo.faturamento_bruto))
        self._cards["faturamento"].definir_sub_rotulo("Mês corrente")
        self._cards["turnos"].definir_valor(str(resumo.turnos_fechados))
        self._cards["ticket_medio"].definir_valor(formatar_reais(resumo.ticket_medio))
        self._cards["ticket_medio"].definir_sub_rotulo(f"{_contar_comandas(resumo)} comandas")
        self._cards["cancelamentos"].definir_valor(f"{resumo.cancelamentos_quantidade} un")
        self._cards["cancelamentos"].definir_sub_rotulo(formatar_reais(resumo.cancelamentos_valor))

        self._preencher_formas_pagamento(resumo)
        self._preencher_ranking(resumo)

    def _preencher_formas_pagamento(self, resumo: ResumoMensal) -> None:
        limpar_layout(self._layout_formas)
        for item in resumo.formas_pagamento:
            self._layout_formas.addLayout(
                _criar_linha_forma(
                    _ROTULO_FORMA.get(item.forma.value, item.forma.value),
                    item.valor,
                    item.percentual,
                )
            )
        self._label_total_formas.setText(formatar_reais(resumo.faturamento_bruto))

    def _preencher_ranking(self, resumo: ResumoMensal) -> None:
        limpar_layout(self._layout_ranking)
        maior_valor = max((item.valor_total for item in resumo.ranking_produtos), default=Decimal(0))
        if resumo.ranking_produtos:
            lider = resumo.ranking_produtos[0]
            self._label_indicador_ranking.setText(f"↗ {formatar_reais(lider.valor_total)}")
        else:
            self._label_indicador_ranking.setText("")

        for indice, item in enumerate(resumo.ranking_produtos, start=1):
            proporcao = int((item.valor_total / maior_valor) * 100) if maior_valor else 0
            self._layout_ranking.addLayout(
                _criar_linha_ranking(
                    indice,
                    item.produto_nome,
                    item.quantidade,
                    item.valor_total,
                    proporcao,
                    item.imagem_path,
                )
            )
        self._layout_ranking.addStretch()


    def _preencher_gaveta(self, gaveta: FechamentoGaveta) -> None:
        self._label_gaveta_identificacao.setText(gaveta.identificacao)
        self._label_gaveta_faturado.setText(formatar_reais(gaveta.total_faturado))
        self._label_gaveta_saldo.setText(formatar_reais(gaveta.saldo_apurado))
        if gaveta.diferenca is None:
            self._label_gaveta_diferenca.setText("—")
        else:
            self._label_gaveta_diferenca.setText(formatar_reais_com_sinal(gaveta.diferenca))

    def _preencher_atendentes(self, ranking: list[ItemRankingAtendente]) -> None:
        limpar_layout(self._layout_atendentes)
        if not ranking:
            vazio = QLabel("Nenhuma venda vinculada a atendente neste período.")
            vazio.setObjectName("relatoriosFormaNome")
            self._layout_atendentes.addWidget(vazio)
            return
        for item in ranking:
            self._layout_atendentes.addLayout(
                _criar_linha_forma(item.atendente_nome, item.valor_total, item.percentual)
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
    label_valor = QLabel(formatar_reais(valor))
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


_TAMANHO_MINIATURA_RANKING = 28


def _criar_linha_ranking(
    indice: int,
    produto_nome: str,
    quantidade: int,
    valor_total: Decimal,
    proporcao: int,
    imagem_path: str | None = None,
) -> QVBoxLayout:
    bloco = QVBoxLayout()
    bloco.setSpacing(6)

    topo = QHBoxLayout()
    topo.setSpacing(10)
    label_indice = QLabel(f"{indice:02d}")
    label_indice.setObjectName("relatoriosRankIndice")
    label_indice.setFixedWidth(24)
    label_indice.setMinimumHeight(18)
    topo.addWidget(label_indice)

    label_miniatura = QLabel()
    label_miniatura.setFixedSize(_TAMANHO_MINIATURA_RANKING, _TAMANHO_MINIATURA_RANKING)
    label_miniatura.setPixmap(obter_pixmap(imagem_path, _TAMANHO_MINIATURA_RANKING, produto_nome))
    topo.addWidget(label_miniatura)

    label_nome = QLabel(produto_nome)
    label_nome.setObjectName("relatoriosRankNome")
    label_nome.setMinimumHeight(18)
    topo.addWidget(label_nome, 1)

    label_qtd = QLabel(f"{quantidade} un")
    label_qtd.setObjectName("relatoriosRankQtd")
    label_qtd.setMinimumHeight(18)
    topo.addWidget(label_qtd)

    label_valor = QLabel(formatar_reais(valor_total))
    label_valor.setObjectName("relatoriosRankValor")
    label_valor.setFixedWidth(90)
    label_valor.setMinimumHeight(18)
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


def _linha_rotulo_valor(rotulo: str, dono: QWidget, atributo_label_valor: str) -> QHBoxLayout:
    """Uma linha 'RÓTULO ... VALOR', guardando o QLabel do valor em `dono`
    (via `setattr`) para `_preencher_gaveta` atualizar depois."""
    linha = QHBoxLayout()
    label_rotulo = QLabel(rotulo)
    label_rotulo.setObjectName("relatoriosRodapeRotulo")
    linha.addWidget(label_rotulo)
    linha.addStretch()
    label_valor = QLabel("—")
    label_valor.setObjectName("relatoriosFormaValor")
    linha.addWidget(label_valor)
    setattr(dono, atributo_label_valor, label_valor)
    return linha


_TITULOS_CARD = {
    "faturamento": "Faturamento bruto",
    "turnos": "Turnos fechados",
    "ticket_medio": "Ticket médio",
    "cancelamentos": "Cancelamentos",
}

_ALINHAR_DIREITA = Qt.AlignmentFlag.AlignRight
