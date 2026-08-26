"""Caixa do dia: status, abertura/fechamento e movimentos da gaveta — porte
visual da tela de caixa do front-end web (`GESTOR COMERCIAL/.../desktop/js/app.js`,
funções `abrirCaixa`/`fecharCaixa`/`registrarMovimento`).

Sangria/reforço/despesa e o próprio abrir/fechar exigem gerente logado —
quem barra isso é `CaixaService` (via `AuthService.exigir_gerente`), então
aqui só se mostra o erro que o service levantar.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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

from gestor_comercial.domain.enums import StatusCaixa, TipoMovimento
from gestor_comercial.domain.movimento_caixa import MovimentoCaixa
from gestor_comercial.services.caixa_service import CaixaService, ResumoCaixa
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao
from gestor_comercial.ui.widgets.secao_cancelamentos import SecaoCancelamentos

_COLUNAS_MOVIMENTOS = ["Quando", "Tipo", "Descrição", "Valor"]

_ROTULOS_TIPO_MOVIMENTO = {
    TipoMovimento.SANGRIA: "Sangria",
    TipoMovimento.REFORCO: "Reforço",
    TipoMovimento.DESPESA: "Despesa",
}

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)


class CaixaView(QWidget):
    """Status do caixa, abertura/fechamento, movimentos da gaveta e conferência."""

    def __init__(
        self,
        caixa_service: CaixaService,
        impressao_service: ImpressaoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._caixa_service = caixa_service
        self._impressao_service = impressao_service
        self._caixa_id: int | None = None
        # Guarda o último caixa conhecido mesmo depois de fechado: o relatório
        # de fechamento é justamente o papel que some ou borra na hora errada,
        # e sem isto o gerente perderia a reimpressão no instante em que fechou.
        self._ultimo_caixa_id: int | None = None

        self._montar_layout()
        self.atualizar()

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)

        cabecalho = QHBoxLayout()
        self._label_titulo = QLabel("Caixa")
        self._label_titulo.setStyleSheet("font-weight: 600; font-size: 18px;")
        cabecalho.addWidget(self._label_titulo)
        cabecalho.addStretch()

        self._botao_abrir = QPushButton("Abrir caixa")
        self._botao_abrir.setProperty("variante", "primario")
        self._botao_abrir.clicked.connect(self._abrir_caixa)
        cabecalho.addWidget(self._botao_abrir)

        self._botao_imprimir = QPushButton("Imprimir fechamento")
        self._botao_imprimir.setProperty("variante", "secundario")
        self._botao_imprimir.setToolTip(
            "Relatório de conferência da gaveta. Funciona com o caixa ainda aberto."
        )
        self._botao_imprimir.clicked.connect(self._imprimir_fechamento)
        cabecalho.addWidget(self._botao_imprimir)

        self._botao_fechar = QPushButton("Fechar caixa")
        self._botao_fechar.setProperty("variante", "perigo")
        self._botao_fechar.clicked.connect(self._fechar_caixa)
        cabecalho.addWidget(self._botao_fechar)
        layout_externo.addLayout(cabecalho)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout_externo.addWidget(self._label_erro)

        self._aviso_impressao = AvisoDeImpressao()
        layout_externo.addWidget(self._aviso_impressao)

        self._label_resumo = QLabel("")
        layout_externo.addWidget(self._label_resumo)

        barra_movimentos = QHBoxLayout()
        barra_movimentos.addWidget(QLabel("Movimentos"))
        barra_movimentos.addStretch()
        self._botoes_movimento_por_tipo: dict[TipoMovimento, QPushButton] = {}
        for tipo in (TipoMovimento.SANGRIA, TipoMovimento.REFORCO, TipoMovimento.DESPESA):
            botao = QPushButton(f"+ {_ROTULOS_TIPO_MOVIMENTO[tipo]}")
            botao.setProperty("variante", "secundario")
            botao.clicked.connect(lambda _checked=False, t=tipo: self._abrir_modal_movimento(t))
            self._botoes_movimento_por_tipo[tipo] = botao
            barra_movimentos.addWidget(botao)
        layout_externo.addLayout(barra_movimentos)

        self._tabela = QTableWidget(0, len(_COLUNAS_MOVIMENTOS))
        self._tabela.setHorizontalHeaderLabels(_COLUNAS_MOVIMENTOS)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tabela.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout_externo.addWidget(self._tabela)

        self._secao_cancelamentos = SecaoCancelamentos()
        layout_externo.addWidget(self._secao_cancelamentos)

    def atualizar(self) -> None:
        self._label_erro.setText("")
        self._aviso_impressao.limpar()
        try:
            caixa = self._caixa_service.buscar_aberto()
        except RegraDeNegocioError:
            self._caixa_id = None
            self._label_titulo.setText("Caixa — fechado")
            self._label_resumo.setText("Nenhum caixa aberto. Abra o caixa para começar o dia.")
            self._tabela.setRowCount(0)
            self._definir_acoes_disponiveis(caixa_aberto=False)
            return

        self._caixa_id = caixa.id
        self._ultimo_caixa_id = caixa.id
        self._label_titulo.setText(f"Caixa {caixa.id} — aberto")
        self._definir_acoes_disponiveis(caixa_aberto=True)
        self._atualizar_resumo()
        self._atualizar_movimentos()
        self._atualizar_cancelamentos()

    def _definir_acoes_disponiveis(self, *, caixa_aberto: bool) -> None:
        self._botao_abrir.setEnabled(not caixa_aberto)
        self._botao_fechar.setEnabled(caixa_aberto)
        # Reimprimir o relatório do caixa recém-fechado continua valendo, então
        # este botão segue o último caixa conhecido, não o que está aberto.
        self._botao_imprimir.setEnabled(self._ultimo_caixa_id is not None)
        for botao in self._botoes_movimento_por_tipo.values():
            botao.setEnabled(caixa_aberto)

    def _atualizar_resumo(self) -> None:
        if self._caixa_id is None:
            return
        resumo = self._caixa_service.resumo(self._caixa_id)
        self._label_resumo.setText(_formatar_resumo(resumo))

    def _atualizar_movimentos(self) -> None:
        if self._caixa_id is None:
            return
        movimentos = self._caixa_service.listar_movimentos(self._caixa_id)
        self._tabela.setRowCount(len(movimentos))
        for linha, movimento in enumerate(movimentos):
            self._preencher_linha(linha, movimento)

    def _atualizar_cancelamentos(self) -> None:
        if self._caixa_id is None:
            return
        self._secao_cancelamentos.carregar(
            self._caixa_service.resumo_cancelamentos(self._caixa_id)
        )

    def _preencher_linha(self, linha: int, movimento: MovimentoCaixa) -> None:
        quando = movimento.registrado_em.strftime("%d/%m %H:%M")
        tipo = _ROTULOS_TIPO_MOVIMENTO.get(movimento.tipo, movimento.tipo.value)
        self._tabela.setItem(linha, 0, QTableWidgetItem(quando))
        self._tabela.setItem(linha, 1, QTableWidgetItem(tipo))
        self._tabela.setItem(linha, 2, QTableWidgetItem(movimento.descricao or ""))
        self._tabela.setItem(linha, 3, QTableWidgetItem(_formatar_reais(movimento.valor)))

    def _abrir_caixa(self) -> None:
        modal = _ValorDialog("Abrir caixa", "Valor de abertura", self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            valor = modal.valor()
        except InvalidOperation:
            self._label_erro.setText("Valor inválido. Informe um valor em reais, como 50.00.")
            return

        self._label_erro.setText("")
        try:
            self._caixa_service.abrir(valor)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()

    def _fechar_caixa(self) -> None:
        if self._caixa_id is None:
            return
        modal = _FecharCaixaDialog(self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            valor_contado, observacao = modal.resultado()
        except InvalidOperation:
            self._label_erro.setText("Valor inválido. Informe um valor em reais, como 50.00.")
            return

        self._label_erro.setText("")
        try:
            self._caixa_service.fechar(self._caixa_id, valor_contado, observacao)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()
        # O relatório sai sozinho no fim do turno — é o momento em que o gerente
        # confere a gaveta, e esperar que ele lembre de clicar em Imprimir depois
        # de o caixa já estar fechado é pedir para o papel nunca sair. Vem DEPOIS
        # do `fechar` porque impressão não pode, em hipótese alguma, impedir o
        # fechamento: se falhar, vira aviso na tela e o caixa continua fechado.
        self._imprimir_fechamento()

    def _imprimir_fechamento(self) -> None:
        """Relatório de conferência da gaveta, na impressora padrão."""
        caixa_id = self._ultimo_caixa_id
        if caixa_id is None:
            return

        try:
            resultado = executar_impressao(
                lambda: self._impressao_service.imprimir_fechamento_caixa(caixa_id)
            )
        except _ERROS_SERVICE as erro:
            # Impressora quebrada volta em `resultado`; aqui só chega caixa
            # inexistente ou sessão perdida.
            self._label_erro.setText(str(erro))
            return
        self._aviso_impressao.mostrar_um(resultado, contexto="Fechamento de caixa")

    def _abrir_modal_movimento(self, tipo: TipoMovimento) -> None:
        modal = _MovimentoDialog(_ROTULOS_TIPO_MOVIMENTO[tipo], self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            valor, descricao = modal.resultado()
        except InvalidOperation:
            self._label_erro.setText("Valor inválido. Informe um valor em reais, como 50.00.")
            return

        self._label_erro.setText("")
        try:
            self._caixa_service.registrar_movimento(tipo, valor, descricao)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar_resumo()
        self._atualizar_movimentos()


class _ValorDialog(QDialog):
    """Modal simples de um único valor em reais (abertura do caixa)."""

    def __init__(self, titulo: str, rotulo_campo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_valor = QLineEdit()
        formulario.addRow(rotulo_campo, self._campo_valor)
        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def valor(self) -> Decimal:
        return Decimal(self._campo_valor.text().strip().replace(",", "."))


class _MovimentoDialog(QDialog):
    """Modal de sangria/reforço/despesa: valor e descrição."""

    def __init__(self, titulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_valor = QLineEdit()
        formulario.addRow("Valor", self._campo_valor)

        self._campo_descricao = QLineEdit()
        self._campo_descricao.setPlaceholderText("Ex.: troco para padaria")
        formulario.addRow("Descrição", self._campo_descricao)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[Decimal, str | None]:
        valor = Decimal(self._campo_valor.text().strip().replace(",", "."))
        descricao = self._campo_descricao.text().strip() or None
        return valor, descricao


class _FecharCaixaDialog(QDialog):
    """Modal de fechamento: valor contado na gaveta e observação livre."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fechar caixa")

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_valor_contado = QLineEdit()
        formulario.addRow("Valor contado", self._campo_valor_contado)

        self._campo_observacao = QLineEdit()
        self._campo_observacao.setPlaceholderText("Opcional")
        formulario.addRow("Observação", self._campo_observacao)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Fechar caixa")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[Decimal, str | None]:
        valor_contado = Decimal(self._campo_valor_contado.text().strip().replace(",", "."))
        observacao = self._campo_observacao.text().strip() or None
        return valor_contado, observacao


def _formatar_resumo(resumo: ResumoCaixa) -> str:
    linhas = [
        f"Abertura: {_formatar_reais(resumo.valor_abertura)}",
        f"Dinheiro: {_formatar_reais(resumo.total_dinheiro)}",
        f"Maquininha: {_formatar_reais(resumo.total_maquininha)}",
        f"Consumo interno: {_formatar_reais(resumo.total_consumo_interno)}",
        f"Reforços: {_formatar_reais(resumo.reforcos)}",
        f"Sangrias: {_formatar_reais(resumo.sangrias)}",
        f"Despesas: {_formatar_reais(resumo.despesas)}",
        f"Saldo esperado na gaveta: {_formatar_reais(resumo.saldo_esperado)}",
    ]
    if resumo.valor_contado is not None:
        linhas.append(f"Valor contado: {_formatar_reais(resumo.valor_contado)}")
    if resumo.diferenca is not None:
        linhas.append(f"Diferença: {_formatar_reais(resumo.diferenca)}")
    return "\n".join(linhas)


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")
