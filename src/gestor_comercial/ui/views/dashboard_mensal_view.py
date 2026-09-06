"""Dashboard Consolidado Mensal: KPIs, composição por forma de pagamento (com
barra de proporção) e mix de vendas do mês (ranking com barra de destaque).

Só QLabel/QProgressBar/QFrame de propósito — a máquina do food truck é um
Celeron com 4GB, sem margem para biblioteca de gráfico. Carrega sob demanda: o
construtor não consulta nada, só `atualizar()` (chamada pela navegação, ao
entrar na aba) busca `CaixaService.resumo_mensal`.
"""

from __future__ import annotations

from collections.abc import Callable

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
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
from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets.filtro_periodo_operador import FiltroPeriodoOperador
from gestor_comercial.ui.widgets.kpi_card import CardKpi
from gestor_comercial.ui.widgets.paineis_relatorio import (
    PainelAtendentes,
    PainelGaveta,
    linha_barra_proporcao,
)
from gestor_comercial.ui.widgets.thumbnail_cache import obter_pixmap
from gestor_comercial.ui.widgets.layout_utils import limpar_layout

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

_ROTULO_FORMA = {
    "CREDITO": "Crédito",
    "DEBITO": "Débito",
    "DINHEIRO": "Dinheiro",
    "PIX": "PIX",
    "CONSUMO_INTERNO": "Consumo interno",
}

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
        self._montar_layout()

    # ------------------------------------------------------------------
    # Montagem do layout
    # ------------------------------------------------------------------

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(0, 0, 0, 0)
        layout_externo.setSpacing(16)

        self._filtro = FiltroPeriodoOperador(self._funcionarios)
        self._filtro.periodo_mudou.connect(self._carregar)
        self._filtro.operador_mudou.connect(self._carregar)
        layout_externo.addWidget(self._filtro)

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
        self._painel_gaveta = PainelGaveta()
        self._painel_atendentes = PainelAtendentes()
        painel_fechamento.addWidget(self._painel_gaveta, 35)
        painel_fechamento.addWidget(self._painel_atendentes, 65)
        layout_conteudo.addLayout(painel_fechamento)

        rolagem = QScrollArea()
        rolagem.setObjectName("relatoriosRolagemHistorico")
        rolagem.setWidget(conteudo)
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout_externo.addWidget(rolagem, 1)

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

    # ------------------------------------------------------------------
    # Carregamento / preenchimento
    # ------------------------------------------------------------------

    def atualizar(self) -> None:
        """Chamada só quando a aba é aberta — nunca no construtor (carregamento
        estritamente sob demanda). Sempre busca de novo: é assim que o painel
        reflete um fechamento de caixa feito desde a última visita à aba."""
        self._filtro.atualizar_operadores()
        self._carregar()

    def periodo_atual(self) -> str:
        return self._filtro.texto_periodo()

    def conectar_mudanca_periodo(self, callback: Callable[[int], None]) -> None:
        self._filtro.conectar_mudanca_periodo(callback)

    def _carregar(self) -> None:
        self._label_erro.setText("")
        ano_mes = self._filtro.ano_mes()
        if ano_mes is None:
            return
        ano, mes = ano_mes
        usuario_id = self._filtro.operador_id()
        try:
            resumo = self._caixas.resumo_mensal(ano, mes, usuario_id)
            fechamentos = self._caixas.listar_fechamentos_do_mes_civil(ano, mes, usuario_id)
            gaveta = self._caixas.fechamento_da_gaveta_do_periodo([c.id for c in fechamentos])
            ranking_atendentes = self._caixas.ranking_por_atendente([c.id for c in fechamentos])
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._preencher(resumo)
        self._painel_gaveta.preencher(gaveta)
        self._painel_atendentes.preencher(ranking_atendentes)

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
                linha_barra_proporcao(
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


def _contar_comandas(resumo: ResumoMensal) -> int:
    # `ResumoMensal` não expõe contagem de comandas separadamente; aproxima
    # pelo total de faturamento / ticket médio (mesma conta usada pra chegar
    # no ticket médio na origem), evitando nova consulta ao banco.
    if resumo.ticket_medio == 0:
        return 0
    return int(resumo.faturamento_bruto / resumo.ticket_medio)


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


_TITULOS_CARD = {
    "faturamento": "Faturamento bruto",
    "turnos": "Turnos fechados",
    "ticket_medio": "Ticket médio",
    "cancelamentos": "Cancelamentos",
}

_ALINHAR_DIREITA = Qt.AlignmentFlag.AlignRight
