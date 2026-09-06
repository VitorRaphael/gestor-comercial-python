"""Histórico Diário: fechamentos do mês selecionado, com comprovante digital
e reimpressão (Controle de Turnos).

A COMPETÊNCIA de cada fechamento é a data de ABERTURA do caixa (§ virada de
noite): um caixa aberto às 23h e fechado de madrugada no dia seguinte aparece
como fechamento do dia em que foi aberto — por isso a consulta usa
`CaixaService.listar_historico_mensal` (eixo `aberto_em`), não
`listar_historico` (eixo `fechado_em`, usado só para achar "o Nº fechamento
de hoje" na hora de fechar o caixa).

Só lê o que `CaixaService`/`AuthService`/`FuncionarioService` já expõem — nenhuma regra de negócio
mora aqui, igual às outras views (§ arquitetura, camadas). As ações "Ver
cancelamentos"/"Reimprimir fechamento" são acionadas pela barra de ações
compartilhada em `RelatoriosView` (ver `ver_cancelamentos`/`reimprimir`
abaixo); esta view só sabe operar sobre o fechamento selecionado na tabela.
"""

from __future__ import annotations

from collections.abc import Callable

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import (
    CaixaService,
    ResumoCaixa,
    ResumoCancelamentos,
)
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.formatacao import formatar_reais, formatar_reais_com_sinal
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao
from gestor_comercial.ui.widgets.comprovante_dialog import (
    ComprovanteFechamentoDialog,
    montar_texto_comprovante,
)
from gestor_comercial.ui.widgets.kpi_card import CardKpi
from gestor_comercial.ui.widgets.filtro_periodo_operador import FiltroPeriodoOperador
from gestor_comercial.ui.widgets.paineis_relatorio import PainelAtendentes, PainelGaveta
from gestor_comercial.ui.widgets.secao_cancelamentos import SecaoCancelamentos
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.tabelas import definir_celula, limpar_tabela
from gestor_comercial.ui.widgets.modais import executar_modal

_COLUNAS = ["DATA", "TURNO / SEQ", "OPERADOR", "FATURAMENTO", "DIFERENÇA", "AÇÕES"]
_COLUNA_ACOES = 5
_ALTURA_MAXIMA_TABELA = 420

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

class HistoricoCaixaView(QWidget):
    """Fechamentos do mês selecionado: KPIs, tabela de turnos e comprovante."""

    def __init__(
        self,
        caixa_service: CaixaService,
        auth_service: AuthService,
        impressao_service: ImpressaoService,
        funcionario_service: FuncionarioService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._caixas = caixa_service
        self._auth = auth_service
        self._impressao = impressao_service
        self._funcionarios = funcionario_service
        self._fechamentos: list[Caixa] = []
        self._resumos: dict[int, ResumoCaixa] = {}

        self._montar_layout()

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

        self._aviso_impressao = AvisoDeImpressao()
        layout_externo.addWidget(self._aviso_impressao)

        # Corpo rolável: cards, tabela e painéis de fechamento não competem
        # por espaço na altura fixa da janela (máquina do food truck) — a
        # tabela de turnos sempre reserva altura própria (`setMinimumHeight`)
        # e o que não couber rola, em vez de ser espremido até ficar ilegível.
        conteudo = QWidget()
        layout_conteudo = QVBoxLayout(conteudo)
        layout_conteudo.setContentsMargins(0, 0, 4, 0)
        layout_conteudo.setSpacing(16)

        grade_cards = QGridLayout()
        grade_cards.setSpacing(14)
        layout_conteudo.addLayout(grade_cards)
        self._card_faturamento = CardKpi("Faturamento no período")
        self._card_ticket = CardKpi("Ticket médio por turno")
        self._card_diferenca = CardKpi("Diferença acumulada")
        self._card_diferenca.definir_sub_rotulo("Conferir caixa")
        self._card_operador = CardKpi("Operador")
        self._card_operador.definir_sub_rotulo("Filtro ativo")
        for coluna, card in enumerate(
            (self._card_faturamento, self._card_ticket, self._card_diferenca, self._card_operador)
        ):
            grade_cards.addWidget(card, 0, coluna)

        self._tabela = QTableWidget(0, len(_COLUNAS))
        self._tabela.setHorizontalHeaderLabels(_COLUNAS)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        cabecalho_tabela = self._tabela.horizontalHeader()
        for coluna in (0, 1, 3, 4):
            cabecalho_tabela.setSectionResizeMode(coluna, QHeaderView.ResizeMode.ResizeToContents)
        cabecalho_tabela.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        # `Fixed` (não `ResizeToContents`) porque essa coluna hospeda um
        # `QPushButton` — sem largura própria garantida, o botão "🖨 2ª via"
        # ficava espremido/cortado ao invés de manter respiro (padding) igual
        # ao resto da pílula.
        cabecalho_tabela.setSectionResizeMode(_COLUNA_ACOES, QHeaderView.ResizeMode.Fixed)
        self._tabela.setColumnWidth(_COLUNA_ACOES, 140)
        self._tabela.cellDoubleClicked.connect(self._ao_dar_duplo_clique)
        self._tabela.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout_conteudo.addWidget(self._tabela)

        self._rodape_tabela = self._montar_rodape_tabela()
        layout_conteudo.addWidget(self._rodape_tabela)

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

    def _montar_rodape_tabela(self) -> QFrame:
        rodape = QFrame()
        rodape.setObjectName("relatoriosPainel")
        layout = QHBoxLayout(rodape)
        layout.setContentsMargins(20, 14, 20, 14)

        self._label_turnos_fechados = QLabel("0 TURNOS FECHADOS")
        self._label_turnos_fechados.setObjectName("relatoriosRodapeRotulo")
        layout.addWidget(self._label_turnos_fechados)
        layout.addStretch()
        self._label_total_periodo = QLabel("R$ 0,00")
        self._label_total_periodo.setObjectName("relatoriosRodapeValor")
        layout.addWidget(self._label_total_periodo)
        return rodape

    # ------------------------------------------------------------------
    # Carregamento / preenchimento
    # ------------------------------------------------------------------

    def atualizar(self) -> None:
        self._label_erro.setText("")
        self._aviso_impressao.limpar()
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
        try:
            fechamentos = self._caixas.listar_historico_mensal(ano, mes)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return

        funcionario_id = self._filtro.operador_id()
        if funcionario_id is not None:
            fechamentos = [
                caixa
                for caixa in fechamentos
                if funcionario_id in (caixa.aberto_por_id, caixa.fechado_por_id)
            ]
        self._fechamentos = fechamentos
        self._resumos = {caixa.id: self._caixas.resumo(caixa.id) for caixa in fechamentos}
        self._preencher_tabela()
        self._preencher_kpis()

        ids = [caixa.id for caixa in fechamentos]
        self._painel_gaveta.preencher(self._caixas.fechamento_da_gaveta_do_periodo(ids))
        self._painel_atendentes.preencher(self._caixas.ranking_por_atendente(ids))

    def _preencher_kpis(self) -> None:
        faturamentos = [_faturamento_total(resumo) for resumo in self._resumos.values()]
        diferencas = [
            diferenca
            for diferenca in (resumo.diferenca_total for resumo in self._resumos.values())
            if diferenca is not None
        ]

        faturamento_periodo = sum(faturamentos, Decimal(0))
        ticket_medio = faturamento_periodo / len(faturamentos) if faturamentos else Decimal(0)
        diferenca_acumulada = sum(diferencas, Decimal(0))

        self._card_faturamento.definir_valor(formatar_reais(faturamento_periodo))
        self._card_faturamento.definir_sub_rotulo(f"{len(self._fechamentos)} turnos")
        self._card_ticket.definir_valor(formatar_reais(ticket_medio))

        tom_diferenca = "neutro" if diferenca_acumulada == 0 else ("positivo" if diferenca_acumulada > 0 else "negativo")
        self._card_diferenca.definir_valor(formatar_reais_com_sinal(diferenca_acumulada), tom=tom_diferenca)

        self._card_operador.definir_valor(self._filtro.nome_operador())

        self._label_turnos_fechados.setText(f"{len(self._fechamentos)} TURNOS FECHADOS")
        self._label_total_periodo.setText(formatar_reais(faturamento_periodo))

    def _preencher_tabela(self) -> None:
        limpar_tabela(self._tabela, linhas=len(self._fechamentos))
        for linha, caixa in enumerate(self._fechamentos):
            self._preencher_linha(linha, caixa)
        self._tabela.clearSelection()
        self._ajustar_altura_tabela()

    def _ajustar_altura_tabela(self) -> None:
        # `QTableWidget` não recalcula seu `sizeHint` pelo conteúdo real das
        # linhas — sem isso, o layout reservava sempre a mesma altura (vazia
        # com poucos turnos, ou cortada com muitos), deixando o rodapé
        # "N TURNOS FECHADOS" longe da última linha visível. Mede a altura
        # real (cabeçalho + linhas) e trava nela, com teto pra lista grande
        # continuar rolando dentro da própria tabela em vez de esticar a
        # página.
        self._tabela.resizeRowsToContents()
        altura = self._tabela.horizontalHeader().height() + 2 * self._tabela.frameWidth()
        for linha in range(self._tabela.rowCount()):
            altura += self._tabela.rowHeight(linha)
        altura = max(altura, self._tabela.horizontalHeader().height() + 56)
        self._tabela.setFixedHeight(min(altura, _ALTURA_MAXIMA_TABELA))

    def _preencher_linha(self, linha: int, caixa: Caixa) -> None:
        operador = caixa.fechado_por.nome if caixa.fechado_por is not None else "—"
        resumo = self._resumos[caixa.id]
        faturamento = _faturamento_total(resumo)
        diferenca_total = resumo.diferenca_total
        diferenca = "—" if diferenca_total is None else formatar_reais_com_sinal(diferenca_total)
        turno = "—" if caixa.numero_sequencial_dia is None else f"T{caixa.numero_sequencial_dia}"
        periodo = self._caixas.identificacao_turno(caixa).removeprefix("Caixa Turno - ")
        sequencial = f"{periodo} · {turno}"

        self._tabela.setItem(linha, 0, QTableWidgetItem(caixa.aberto_em.strftime("%d/%m")))
        self._tabela.setItem(linha, 1, QTableWidgetItem(sequencial))
        self._tabela.setItem(linha, 2, QTableWidgetItem(operador))
        self._tabela.setItem(linha, 3, QTableWidgetItem(formatar_reais(faturamento)))

        item_diferenca = QTableWidgetItem(diferenca)
        if diferenca_total is not None and diferenca_total != 0:
            t = ThemeController.instancia().tokens_atuais
            cor = t["sucesso"] if diferenca_total > 0 else t["perigo_hover"]
            item_diferenca.setForeground(QColor(cor))
        self._tabela.setItem(linha, 4, item_diferenca)

        botao_ver = QPushButton("🖨 2ª via")
        botao_ver.setProperty("variante", "pilula-impressora")
        botao_ver.clicked.connect(lambda _=False, caixa_id=caixa.id: self._abrir_comprovante(caixa_id))
        definir_celula(self._tabela, linha, _COLUNA_ACOES, botao_ver)

    # ------------------------------------------------------------------
    # Ações (acionadas pela barra de ações compartilhada de RelatoriosView)
    # ------------------------------------------------------------------

    def tem_selecao(self) -> bool:
        return self._caixa_selecionado() is not None

    def _caixa_selecionado(self) -> Caixa | None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._fechamentos):
            return None
        return self._fechamentos[linha]

    def _ao_dar_duplo_clique(self, linha: int, _coluna: int) -> None:
        if linha < 0 or linha >= len(self._fechamentos):
            return
        self._abrir_comprovante(self._fechamentos[linha].id)

    def _abrir_comprovante(self, caixa_id: int) -> None:
        self._label_erro.setText("")
        try:
            caixa = self._caixas.buscar(caixa_id)
            texto = montar_texto_comprovante(self._caixas, caixa)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        modal = ComprovanteFechamentoDialog(caixa, texto, self)
        executar_modal(modal)

    def reimprimir(self) -> None:
        self._label_erro.setText("")
        caixa = self._caixa_selecionado()
        if caixa is None:
            self._label_erro.setText("Selecione um fechamento na lista para reimprimir.")
            return

        try:
            resultado = executar_impressao(
                lambda: self._impressao.imprimir_fechamento_caixa(caixa.id)
            )
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._aviso_impressao.mostrar_um(resultado, contexto="Fechamento de caixa")

    def ver_cancelamentos(self) -> None:
        self._label_erro.setText("")
        caixa = self._caixa_selecionado()
        if caixa is None:
            self._label_erro.setText("Selecione um fechamento na lista para ver os cancelamentos.")
            return

        try:
            titulo = self._caixas.titulo_fechamento(caixa.id)
        except _ERROS_SERVICE:
            titulo = f"Caixa {caixa.id}"
        resumo = self._caixas.resumo_cancelamentos(caixa.id)

        modal = _CancelamentosDialog(titulo, resumo, self)
        executar_modal(modal)

class _CancelamentosDialog(QDialog):
    """Modal com a auditoria de itens cancelados de um fechamento passado."""

    def __init__(
        self, titulo_fechamento: str, resumo: ResumoCancelamentos, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Itens cancelados — {titulo_fechamento}")
        self.resize(640, 480)

        layout = QVBoxLayout(self)
        secao = SecaoCancelamentos()
        secao.carregar(resumo)
        layout.addWidget(secao)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botoes.rejected.connect(self.reject)
        botoes.accepted.connect(self.accept)
        botoes.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        layout.addWidget(botoes)


def _faturamento_total(resumo: ResumoCaixa) -> Decimal:
    # Mesma regra da linha "Total" de `conferencia_pagamentos`.
    return resumo.total_dinheiro + resumo.total_maquininha + resumo.total_consumo_interno

