"""Histórico Diário: fechamentos do mês selecionado, com comprovante digital
e reimpressão (Controle de Turnos).

A COMPETÊNCIA de cada fechamento é a data de ABERTURA do caixa (§ virada de
noite): um caixa aberto às 23h e fechado de madrugada no dia seguinte aparece
como fechamento do dia em que foi aberto — por isso a consulta usa
`CaixaService.listar_historico_mensal` (eixo `aberto_em`), não
`listar_historico` (eixo `fechado_em`, usado só para achar "o Nº fechamento
de hoje" na hora de fechar o caixa).

Só lê o que `CaixaService`/`AuthService` já expõem — nenhuma regra de negócio
mora aqui, igual às outras views (§ arquitetura, camadas). As ações "Ver
cancelamentos"/"Reimprimir fechamento" são acionadas pela barra de ações
compartilhada em `RelatoriosView` (ver `ver_cancelamentos`/`reimprimir`
abaixo); esta view só sabe operar sobre o fechamento selecionado na tabela.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
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
    FechamentoGaveta,
    ItemRankingAtendente,
    ResumoCaixa,
    ResumoCancelamentos,
)
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.theme.tokens import PERIGO_HOVER, SUCESSO
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao
from gestor_comercial.ui.widgets.comprovante_dialog import (
    ComprovanteFechamentoDialog,
    montar_texto_comprovante,
)
from gestor_comercial.ui.widgets.kpi_card import CardKpi
from gestor_comercial.ui.widgets.secao_cancelamentos import SecaoCancelamentos

_COLUNAS = ["DATA", "TURNO / SEQ", "OPERADOR", "FATURAMENTO", "DIFERENÇA", "AÇÕES"]
_COLUNA_ACOES = 5
_ALTURA_MAXIMA_TABELA = 420

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

_MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

# Sentinela do item "Todos" do filtro de operador — combina com o `userData`
# de cada pílula, que também guarda `int` de verdade para cada funcionário.
_TODOS_OS_OPERADORES = None


class HistoricoCaixaView(QWidget):
    """Fechamentos do mês selecionado: KPIs, tabela de turnos e comprovante."""

    def __init__(
        self,
        caixa_service: CaixaService,
        auth_service: AuthService,
        impressao_service: ImpressaoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._caixas = caixa_service
        self._auth = auth_service
        self._impressao = impressao_service
        self._fechamentos: list[Caixa] = []
        self._resumos: dict[int, ResumoCaixa] = {}
        self._operador_selecionado: int | None = _TODOS_OS_OPERADORES
        self._nome_operador_selecionado = "Todos"

        self._montar_layout()

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(0, 0, 0, 0)
        layout_externo.setSpacing(16)

        layout_externo.addLayout(self._montar_filtros())

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
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
        for coluna in (0, 1, 3, 4, _COLUNA_ACOES):
            cabecalho_tabela.setSectionResizeMode(coluna, QHeaderView.ResizeMode.ResizeToContents)
        cabecalho_tabela.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._tabela.setColumnWidth(_COLUNA_ACOES, 110)
        self._tabela.cellDoubleClicked.connect(self._ao_dar_duplo_clique)
        self._tabela.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout_conteudo.addWidget(self._tabela)

        self._rodape_tabela = self._montar_rodape_tabela()
        layout_conteudo.addWidget(self._rodape_tabela)

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

    def _montar_filtros(self) -> QHBoxLayout:
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
        # Mesmo padrão do Histórico Mensal: mês vigente primeiro, mais 11 pra
        # trás, mesmo sem nenhum fechamento ainda naquele mês.
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
        self._label_erro.setText("")
        self._aviso_impressao.limpar()
        self._popular_pills_operador()
        self._carregar()

    def periodo_atual(self) -> str:
        return self._seletor_mes.currentText()

    def conectar_mudanca_periodo(self, callback) -> None:
        self._seletor_mes.currentIndexChanged.connect(callback)

    def _popular_pills_operador(self) -> None:
        # Reconstrói do zero: um funcionário desativado entre duas visitas à
        # tela ainda tem que aparecer, porque o histórico é dele mesmo assim.
        selecionado = self._operador_selecionado
        _limpar_layout_horizontal(self._layout_pills_operador)

        opcoes: list[tuple[str, int | None]] = [("Todos", _TODOS_OS_OPERADORES)]
        opcoes.extend((funcionario.nome, funcionario.id) for funcionario in self._auth.listar_todos())
        if selecionado not in (valor for _, valor in opcoes):
            selecionado = _TODOS_OS_OPERADORES

        for nome, valor in opcoes:
            pill = QPushButton(nome)
            pill.setProperty("variante", "filtro-pill")
            pill.setProperty("ativo", valor == selecionado)
            pill.clicked.connect(lambda _=False, v=valor: self._selecionar_operador(v))
            self._layout_pills_operador.addWidget(pill)
            if valor == selecionado:
                self._nome_operador_selecionado = nome
        self._operador_selecionado = selecionado

    def _selecionar_operador(self, operador_id: int | None) -> None:
        self._operador_selecionado = operador_id
        self._popular_pills_operador()
        self._carregar()

    def _carregar(self) -> None:
        self._label_erro.setText("")
        ano_mes = self._seletor_mes.currentData()
        if ano_mes is None:
            return
        ano, mes = ano_mes
        try:
            fechamentos = self._caixas.listar_historico_mensal(ano, mes)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return

        funcionario_id = self._operador_selecionado
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
        self._preencher_gaveta(self._caixas.fechamento_da_gaveta_do_periodo(ids))
        self._preencher_atendentes(self._caixas.ranking_por_atendente(ids))

    def _preencher_kpis(self) -> None:
        faturamentos = [_faturamento_total(resumo) for resumo in self._resumos.values()]
        diferencas = [d for d in (_diferenca_total(resumo) for resumo in self._resumos.values()) if d is not None]

        faturamento_periodo = sum(faturamentos, Decimal(0))
        ticket_medio = faturamento_periodo / len(faturamentos) if faturamentos else Decimal(0)
        diferenca_acumulada = sum(diferencas, Decimal(0))

        self._card_faturamento.definir_valor(_formatar_reais(faturamento_periodo))
        self._card_faturamento.definir_sub_rotulo(f"{len(self._fechamentos)} turnos")
        self._card_ticket.definir_valor(_formatar_reais(ticket_medio))

        tom_diferenca = "neutro" if diferenca_acumulada == 0 else ("positivo" if diferenca_acumulada > 0 else "negativo")
        self._card_diferenca.definir_valor(_formatar_reais_com_sinal(diferenca_acumulada), tom=tom_diferenca)

        self._card_operador.definir_valor(self._nome_operador_selecionado)

        self._label_turnos_fechados.setText(f"{len(self._fechamentos)} TURNOS FECHADOS")
        self._label_total_periodo.setText(_formatar_reais(faturamento_periodo))

    def _preencher_tabela(self) -> None:
        self._tabela.setRowCount(len(self._fechamentos))
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
        diferenca_total = _diferenca_total(resumo)
        diferenca = "—" if diferenca_total is None else _formatar_reais_com_sinal(diferenca_total)
        turno = "—" if caixa.numero_sequencial_dia is None else f"T{caixa.numero_sequencial_dia}"
        periodo = self._caixas.identificacao_turno(caixa).removeprefix("Caixa Turno - ")
        sequencial = f"{periodo} · {turno}"

        self._tabela.setItem(linha, 0, QTableWidgetItem(caixa.aberto_em.strftime("%d/%m")))
        self._tabela.setItem(linha, 1, QTableWidgetItem(sequencial))
        self._tabela.setItem(linha, 2, QTableWidgetItem(operador))
        self._tabela.setItem(linha, 3, QTableWidgetItem(_formatar_reais(faturamento)))

        item_diferenca = QTableWidgetItem(diferenca)
        if diferenca_total is not None and diferenca_total != 0:
            cor = SUCESSO if diferenca_total > 0 else PERIGO_HOVER
            item_diferenca.setForeground(QColor(cor))
        self._tabela.setItem(linha, 4, item_diferenca)

        botao_ver = QPushButton("🖨 2ª via")
        botao_ver.setProperty("variante", "pilula-impressora")
        botao_ver.clicked.connect(lambda _=False, caixa_id=caixa.id: self._abrir_comprovante(caixa_id))
        self._tabela.setCellWidget(linha, _COLUNA_ACOES, botao_ver)

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
        modal.exec()

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
        modal.exec()

    def _preencher_gaveta(self, gaveta: FechamentoGaveta) -> None:
        self._label_gaveta_identificacao.setText(gaveta.identificacao)
        self._label_gaveta_faturado.setText(_formatar_reais(gaveta.total_faturado))
        self._label_gaveta_saldo.setText(_formatar_reais(gaveta.saldo_apurado))
        if gaveta.diferenca is None:
            self._label_gaveta_diferenca.setText("—")
        else:
            self._label_gaveta_diferenca.setText(_formatar_reais_com_sinal(gaveta.diferenca))

    def _preencher_atendentes(self, ranking: list[ItemRankingAtendente]) -> None:
        _limpar_layout_vertical(self._layout_atendentes)
        if not ranking:
            vazio = QLabel("Nenhuma venda vinculada a atendente neste período.")
            vazio.setObjectName("relatoriosFormaNome")
            self._layout_atendentes.addWidget(vazio)
            return
        for item in ranking:
            self._layout_atendentes.addLayout(
                _criar_linha_atendente(item.atendente_nome, item.valor_total, item.percentual)
            )


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


def _diferenca_total(resumo: ResumoCaixa) -> Decimal | None:
    if resumo.diferenca_dinheiro is None:
        return None
    return resumo.diferenca_dinheiro + resumo.diferenca_maquininha


def _limpar_layout_horizontal(layout: QHBoxLayout) -> None:
    # Ver o comentário de `_limpar_layout_vertical` abaixo — mesmo bug,
    # mesma correção: `setParent(None)` antes do `deleteLater()`.
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


def _limpar_layout_vertical(layout: QVBoxLayout) -> None:
    # `takeAt` só tira o item do LAYOUT — o widget continua filho visível do
    # container até o `deleteLater()` agendado realmente rodar no próximo
    # ciclo de eventos. Entre um `_preencher_*` e o outro (trocar de mês,
    # trocar filtro de operador), isso empilhava a linha antiga por baixo da
    # nova na mesma posição, produzindo texto sobreposto/corrompido no
    # repaint. `setParent(None)` desliga o widget da árvore na hora.
    while layout.count():
        item = layout.takeAt(0)
        sub_layout = item.layout()
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif sub_layout is not None:
            _limpar_layout_vertical(sub_layout)
            sub_layout.deleteLater()


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


def _criar_linha_atendente(nome: str, valor: Decimal, percentual: Decimal) -> QVBoxLayout:
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


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")


def _formatar_reais_com_sinal(valor: Decimal) -> str:
    if valor == 0:
        return "—"
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {abs(valor):.2f}".replace(".", ",")
