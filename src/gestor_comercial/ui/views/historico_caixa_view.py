"""Histórico Diário: fechamentos do mês selecionado, com comprovante digital
e reimpressão (Controle de Turnos).

A COMPETÊNCIA de cada fechamento é a data de ABERTURA do caixa (§ virada de
noite): um caixa aberto às 23h e fechado de madrugada no dia seguinte aparece
como fechamento do dia em que foi aberto — por isso a consulta usa
`CaixaService.listar_historico_mensal` (eixo `aberto_em`), não
`listar_historico` (eixo `fechado_em`, usado só para achar "o Nº fechamento
de hoje" na hora de fechar o caixa).

Só lê o que `CaixaService`/`AuthService` já expõem — nenhuma regra de negócio
mora aqui, igual às outras views (§ arquitetura, camadas).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import CaixaService, ResumoCancelamentos
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao
from gestor_comercial.ui.widgets.comprovante_dialog import (
    ComprovanteFechamentoDialog,
    montar_texto_comprovante,
)
from gestor_comercial.ui.widgets.secao_cancelamentos import SecaoCancelamentos

_COLUNAS = [
    "Data (Dia/Mês)",
    "Turno/Seq",
    "Operador",
    "Faturamento Total (R$)",
    "Diferença/Quebra (R$)",
    "Ações",
]
_COLUNA_ACOES = 5

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

_MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

# Sentinela do item "Todos" do combo de operador — combina com o `userData`
# de um QComboBox que também guarda `int` de verdade para cada funcionário.
_TODOS_OS_OPERADORES = None


class HistoricoCaixaView(QWidget):
    """Fechamentos do mês selecionado: comprovante digital e reimpressão."""

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

        self._montar_layout()

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)

        cabecalho = QHBoxLayout()
        titulo = QLabel("Histórico Diário")
        titulo.setStyleSheet("font-weight: 600; font-size: 18px;")
        cabecalho.addWidget(titulo)
        cabecalho.addStretch()

        cabecalho.addWidget(QLabel("Mês"))
        self._seletor_mes = QComboBox()
        self._popular_seletor_mes()
        self._seletor_mes.currentIndexChanged.connect(self._carregar)
        cabecalho.addWidget(self._seletor_mes)

        cabecalho.addWidget(QLabel("Operador"))
        self._combo_operador = QComboBox()
        self._combo_operador.currentIndexChanged.connect(self._carregar)
        cabecalho.addWidget(self._combo_operador)
        layout_externo.addLayout(cabecalho)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout_externo.addWidget(self._label_erro)

        self._aviso_impressao = AvisoDeImpressao()
        layout_externo.addWidget(self._aviso_impressao)

        self._tabela = QTableWidget(0, len(_COLUNAS))
        self._tabela.setHorizontalHeaderLabels(_COLUNAS)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._tabela.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._tabela.cellDoubleClicked.connect(self._ao_dar_duplo_clique)
        layout_externo.addWidget(self._tabela)

        rodape = QHBoxLayout()
        rodape.addStretch()
        self._botao_cancelamentos = QPushButton("Ver cancelamentos")
        self._botao_cancelamentos.setProperty("variante", "secundario")
        self._botao_cancelamentos.clicked.connect(self._ver_cancelamentos)
        rodape.addWidget(self._botao_cancelamentos)

        self._botao_reimprimir = QPushButton("Reimprimir fechamento")
        self._botao_reimprimir.setProperty("variante", "primario")
        self._botao_reimprimir.clicked.connect(self._reimprimir)
        rodape.addWidget(self._botao_reimprimir)
        layout_externo.addLayout(rodape)

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

    def atualizar(self) -> None:
        self._label_erro.setText("")
        self._aviso_impressao.limpar()
        self._popular_combo_operador()
        self._carregar()

    def _popular_combo_operador(self) -> None:
        # Reconstrói do zero: um funcionário desativado entre duas visitas à
        # tela ainda tem que aparecer, porque o histórico é dele mesmo assim.
        selecionado = self._combo_operador.currentData()
        self._combo_operador.blockSignals(True)
        self._combo_operador.clear()
        self._combo_operador.addItem("Todos", _TODOS_OS_OPERADORES)
        for funcionario in self._auth.listar_todos():
            self._combo_operador.addItem(funcionario.nome, funcionario.id)
        indice = self._combo_operador.findData(selecionado)
        self._combo_operador.setCurrentIndex(indice if indice >= 0 else 0)
        self._combo_operador.blockSignals(False)

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

        funcionario_id = self._combo_operador.currentData()
        if funcionario_id is not None:
            fechamentos = [
                caixa
                for caixa in fechamentos
                if funcionario_id in (caixa.aberto_por_id, caixa.fechado_por_id)
            ]
        self._fechamentos = fechamentos
        self._preencher_tabela()

    def _preencher_tabela(self) -> None:
        self._tabela.setRowCount(len(self._fechamentos))
        for linha, caixa in enumerate(self._fechamentos):
            self._preencher_linha(linha, caixa)
        self._tabela.clearSelection()

    def _preencher_linha(self, linha: int, caixa: Caixa) -> None:
        operador = caixa.fechado_por.nome if caixa.fechado_por is not None else "—"
        resumo = self._caixas.resumo(caixa.id)
        faturamento = resumo.total_dinheiro + resumo.total_maquininha + resumo.total_consumo_interno
        diferenca = "—" if resumo.diferenca is None else _formatar_reais(resumo.diferenca)
        turno = "—" if caixa.numero_sequencial_dia is None else f"{caixa.numero_sequencial_dia}º"

        self._tabela.setItem(linha, 0, QTableWidgetItem(caixa.aberto_em.strftime("%d/%m")))
        self._tabela.setItem(linha, 1, QTableWidgetItem(turno))
        self._tabela.setItem(linha, 2, QTableWidgetItem(operador))
        self._tabela.setItem(linha, 3, QTableWidgetItem(_formatar_reais(faturamento)))
        item_diferenca = QTableWidgetItem(diferenca)
        if resumo.diferenca is not None and resumo.diferenca != 0:
            item_diferenca.setForeground(Qt.GlobalColor.red)
        self._tabela.setItem(linha, 4, item_diferenca)

        botao_ver = QPushButton("Ver Comprovante")
        botao_ver.setProperty("variante", "secundario")
        botao_ver.clicked.connect(lambda _=False, caixa_id=caixa.id: self._abrir_comprovante(caixa_id))
        self._tabela.setCellWidget(linha, _COLUNA_ACOES, botao_ver)

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

    def _reimprimir(self) -> None:
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

    def _ver_cancelamentos(self) -> None:
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


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")
