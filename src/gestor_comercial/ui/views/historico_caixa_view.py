"""Histórico de Fechamentos: consulta de caixas já encerrados, com filtro por
período e operador, e reimpressão do relatório de cada um (Controle de Turnos).

Só lê o que `CaixaService` e `AuthService` já expõem — nenhuma regra de
negócio mora aqui, igual às outras views (§ arquitetura, camadas).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao

_COLUNAS = ["Fechamento", "Aberto em", "Fechado em", "Aberto por", "Fechado por", "Diferença"]

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

# Sentinela do item "Todos" do combo de operador — combina com o `userData`
# de um QComboBox que também guarda `int` de verdade para cada funcionário.
_TODOS_OS_OPERADORES = None


class HistoricoCaixaView(QWidget):
    """Consulta de fechamentos passados: filtro por período/operador e reimpressão."""

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

        titulo = QLabel("Histórico de Fechamentos")
        titulo.setStyleSheet("font-weight: 600; font-size: 18px;")
        layout_externo.addWidget(titulo)

        filtros = QHBoxLayout()
        filtros.addWidget(QLabel("De"))
        self._campo_inicio = QLineEdit()
        self._campo_inicio.setPlaceholderText("dd/mm/aaaa")
        filtros.addWidget(self._campo_inicio)

        filtros.addWidget(QLabel("Até"))
        self._campo_fim = QLineEdit()
        self._campo_fim.setPlaceholderText("dd/mm/aaaa")
        filtros.addWidget(self._campo_fim)

        filtros.addWidget(QLabel("Operador"))
        self._combo_operador = QComboBox()
        filtros.addWidget(self._combo_operador)

        self._botao_filtrar = QPushButton("Filtrar")
        self._botao_filtrar.setProperty("variante", "secundario")
        self._botao_filtrar.clicked.connect(self._filtrar)
        filtros.addWidget(self._botao_filtrar)

        self._botao_limpar = QPushButton("Limpar filtros")
        self._botao_limpar.clicked.connect(self._limpar_filtros)
        filtros.addWidget(self._botao_limpar)
        filtros.addStretch()
        layout_externo.addLayout(filtros)

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
        self._tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout_externo.addWidget(self._tabela)

        rodape = QHBoxLayout()
        rodape.addStretch()
        self._botao_reimprimir = QPushButton("Reimprimir fechamento")
        self._botao_reimprimir.setProperty("variante", "primario")
        self._botao_reimprimir.clicked.connect(self._reimprimir)
        rodape.addWidget(self._botao_reimprimir)
        layout_externo.addLayout(rodape)

    def atualizar(self) -> None:
        self._label_erro.setText("")
        self._aviso_impressao.limpar()
        self._popular_combo_operador()
        self._filtrar()

    def _popular_combo_operador(self) -> None:
        # Reconstrói do zero: um funcionário desativado entre duas visitas à
        # tela ainda tem que aparecer, porque o histórico é dele mesmo assim.
        selecionado = self._combo_operador.currentData()
        self._combo_operador.clear()
        self._combo_operador.addItem("Todos", _TODOS_OS_OPERADORES)
        for funcionario in self._auth.listar_todos():
            self._combo_operador.addItem(funcionario.nome, funcionario.id)
        indice = self._combo_operador.findData(selecionado)
        self._combo_operador.setCurrentIndex(indice if indice >= 0 else 0)

    def _filtrar(self) -> None:
        self._label_erro.setText("")
        try:
            inicio = self._ler_data(self._campo_inicio.text())
            fim = self._ler_data(self._campo_fim.text())
        except ValueError:
            self._label_erro.setText("Data inválida. Use o formato dd/mm/aaaa.")
            return

        funcionario_id = self._combo_operador.currentData()
        self._fechamentos = self._caixas.listar_historico(
            inicio=inicio, fim=fim, funcionario_id=funcionario_id
        )
        self._preencher_tabela()

    def _limpar_filtros(self) -> None:
        self._campo_inicio.clear()
        self._campo_fim.clear()
        self._combo_operador.setCurrentIndex(0)
        self._filtrar()

    def _preencher_tabela(self) -> None:
        self._tabela.setRowCount(len(self._fechamentos))
        for linha, caixa in enumerate(self._fechamentos):
            self._preencher_linha(linha, caixa)
        self._tabela.clearSelection()

    def _preencher_linha(self, linha: int, caixa: Caixa) -> None:
        try:
            titulo = self._caixas.titulo_fechamento(caixa.id)
        except _ERROS_SERVICE:
            titulo = f"Caixa {caixa.id}"
        aberto_por = caixa.aberto_por.nome if caixa.aberto_por is not None else "—"
        fechado_por = caixa.fechado_por.nome if caixa.fechado_por is not None else "—"
        resumo = self._caixas.resumo(caixa.id)
        diferenca = "—" if resumo.diferenca is None else _formatar_reais(resumo.diferenca)

        self._tabela.setItem(linha, 0, QTableWidgetItem(titulo))
        self._tabela.setItem(linha, 1, QTableWidgetItem(_formatar_data_hora(caixa.aberto_em)))
        self._tabela.setItem(linha, 2, QTableWidgetItem(_formatar_data_hora(caixa.fechado_em)))
        self._tabela.setItem(linha, 3, QTableWidgetItem(aberto_por))
        self._tabela.setItem(linha, 4, QTableWidgetItem(fechado_por))
        self._tabela.setItem(linha, 5, QTableWidgetItem(diferenca))

    def _caixa_selecionado(self) -> Caixa | None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._fechamentos):
            return None
        return self._fechamentos[linha]

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

    @staticmethod
    def _ler_data(texto: str) -> date | None:
        limpo = texto.strip()
        if not limpo:
            return None
        return datetime.strptime(limpo, "%d/%m/%Y").date()


def _formatar_data_hora(momento: datetime | None) -> str:
    return "—" if momento is None else momento.strftime("%d/%m/%Y %H:%M")


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")
