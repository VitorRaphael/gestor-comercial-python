"""Detalhe da comanda: lista de itens + total, modal de adicionar item,
cancelamento de item/comanda com PIN de gerente — porte visual de
`.comanda-detalhe`/`.tabela` e dos modais `+ Item`/`Cancelar` do front-end
web (`GESTOR COMERCIAL/.../desktop/index.html` + `js/app.js`).

Não conhece `PagamentoDialog` nem navegação: emite `pagamento_solicitado`,
`voltar` e `comanda_cancelada` e deixa a janela principal decidir o que
fazer com cada um (o mesmo padrão de `MesasView.comanda_aberta`).
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import StatusComanda
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.views.cancelamento_dialog import CancelamentoDialog
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao

_COLUNAS = ["Descrição", "Preço", "Qtd", "Total", ""]
_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

_NADA_NOVO_PARA_IMPRIMIR = (
    "Nada novo para a produção: todos os itens desta comanda já foram enviados. "
    "Use '2ª via' para repetir o cupom inteiro."
)


class ComandaView(QWidget):
    """Lista de itens de uma comanda, com total, lançamento e cancelamento."""

    voltar = Signal()
    pagamento_solicitado = Signal(int)
    comanda_cancelada = Signal(int)

    def __init__(
        self,
        comanda_service: ComandaService,
        cardapio_service: CardapioService,
        impressao_service: ImpressaoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._comanda_service = comanda_service
        self._cardapio_service = cardapio_service
        self._impressao_service = impressao_service
        self._comanda: Comanda | None = None

        self._montar_layout()

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)

        cabecalho = QHBoxLayout()

        self._botao_voltar = QPushButton("← Mesas")
        self._botao_voltar.setProperty("variante", "secundario")
        self._botao_voltar.clicked.connect(self._voltar_clicado)
        cabecalho.addWidget(self._botao_voltar)

        self._label_titulo = QLabel("")
        self._label_titulo.setStyleSheet("font-weight: 600; font-size: 18px;")
        cabecalho.addWidget(self._label_titulo)
        cabecalho.addStretch()

        self._botao_add_item = QPushButton("+ Item")
        self._botao_add_item.setProperty("variante", "secundario")
        self._botao_add_item.clicked.connect(self._abrir_modal_adicionar_item)
        cabecalho.addWidget(self._botao_add_item)

        self._botao_imprimir = QPushButton("Imprimir")
        self._botao_imprimir.setProperty("variante", "secundario")
        self._botao_imprimir.setToolTip("Manda para a produção só o que ainda não foi impresso.")
        self._botao_imprimir.clicked.connect(self._imprimir_producao)
        cabecalho.addWidget(self._botao_imprimir)

        self._botao_segunda_via = QPushButton("2ª via")
        self._botao_segunda_via.setProperty("variante", "secundario")
        self._botao_segunda_via.setToolTip("Repete a comanda inteira, para cupom rasgado ou perdido.")
        self._botao_segunda_via.clicked.connect(self._imprimir_segunda_via)
        cabecalho.addWidget(self._botao_segunda_via)

        self._botao_pagamento = QPushButton("Receber pagamento")
        self._botao_pagamento.setProperty("variante", "primario")
        self._botao_pagamento.clicked.connect(self._solicitar_pagamento)
        cabecalho.addWidget(self._botao_pagamento)

        self._botao_cancelar_comanda = QPushButton("Cancelar comanda")
        self._botao_cancelar_comanda.setProperty("variante", "perigo")
        self._botao_cancelar_comanda.clicked.connect(self._cancelar_comanda)
        cabecalho.addWidget(self._botao_cancelar_comanda)
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
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout_externo.addWidget(self._tabela)

        linha_total = QHBoxLayout()
        linha_total.addStretch()
        linha_total.addWidget(QLabel("Total"))
        self._label_total = QLabel("R$ 0,00")
        self._label_total.setStyleSheet("font-weight: 700; font-size: 16px;")
        linha_total.addWidget(self._label_total)
        layout_externo.addLayout(linha_total)

    def carregar_comanda(self, comanda: Comanda) -> None:
        self._comanda = comanda
        self.atualizar()

    def atualizar(self) -> None:
        if self._comanda is None:
            return
        self._label_erro.setText("")
        # Qualquer mudança na comanda — outra mesa, item novo, item cancelado —
        # envelhece o aviso do último cupom. Mantê-lo faria o operador achar que
        # a cozinha já viu o item que ele acabou de lançar.
        self._aviso_impressao.limpar()
        # Recarrega para pegar o status mais recente (ex.: acabou de ser
        # cancelada por este mesmo modal) — o objeto passado a
        # `carregar_comanda` pode estar desatualizado.
        self._comanda = self._comanda_service.buscar(self._comanda.id)

        titulo = f"Mesa {self._comanda.mesa.numero}" if self._comanda.mesa else "Balcão"
        self._label_titulo.setText(f"{titulo} — comanda {self._comanda.id}")

        itens = self._comanda_service.listar_itens(self._comanda.id)
        itens_ativos = [item for item in itens if not item.cancelado]

        self._tabela.setRowCount(len(itens_ativos))
        for linha, item in enumerate(itens_ativos):
            self._preencher_linha(linha, item)

        total = self._comanda_service.calcular_total(self._comanda.id)
        self._label_total.setText(_formatar_reais(total))

        aberta = self._comanda.status is StatusComanda.ABERTA
        self._botao_add_item.setEnabled(aberta)
        self._botao_pagamento.setEnabled(aberta)
        self._botao_cancelar_comanda.setEnabled(aberta)
        # Via de acréscimo só faz sentido na comanda aberta — a fechada não
        # recebe mais item. A 2ª via continua liberada: cupom da cozinha some
        # ou rasga depois do pagamento também.
        self._botao_imprimir.setEnabled(aberta)
        self._botao_segunda_via.setEnabled(len(itens_ativos) > 0)

    def _preencher_linha(self, linha: int, item: ItemComanda) -> None:
        descricao = item.produto.nome
        if item.observacao:
            descricao += f" ({item.observacao})"
        total_item = item.preco_unit_congelado * item.quantidade

        self._tabela.setItem(linha, 0, QTableWidgetItem(descricao))
        self._tabela.setItem(linha, 1, QTableWidgetItem(_formatar_reais(item.preco_unit_congelado)))
        self._tabela.setItem(linha, 2, QTableWidgetItem(str(item.quantidade)))
        self._tabela.setItem(linha, 3, QTableWidgetItem(_formatar_reais(total_item)))

        acoes_item = QWidget()
        layout_acoes = QHBoxLayout(acoes_item)
        layout_acoes.setContentsMargins(0, 0, 0, 0)

        botao_remover = QPushButton("Remover")
        botao_remover.setProperty("variante", "perigo")
        botao_remover.clicked.connect(lambda _checked=False, i=item: self._remover_item(i))
        # Item que já foi pra cozinha só sai por Cancelar (com PIN e motivo). O
        # service barra isso de qualquer jeito; desabilitar aqui é para o
        # operador entender a regra antes de clicar, e não depois do erro.
        if item.impresso_em is not None:
            botao_remover.setEnabled(False)
            botao_remover.setToolTip(
                "Já enviado para a produção. Use Cancelar, que exige autorização do gerente."
            )
        layout_acoes.addWidget(botao_remover)

        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.setProperty("variante", "perigo")
        botao_cancelar.clicked.connect(lambda _checked=False, i=item: self._cancelar_item(i))
        layout_acoes.addWidget(botao_cancelar)

        self._tabela.setCellWidget(linha, 4, acoes_item)

    def _remover_item(self, item: ItemComanda) -> None:
        self._label_erro.setText("")
        try:
            self._comanda_service.remover_item(item.id)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()

    def _cancelar_item(self, item: ItemComanda) -> None:
        modal = CancelamentoDialog(f"Cancelar item — {item.produto.nome}", self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        motivo, pin_gerente = modal.resultado()

        self._label_erro.setText("")
        try:
            self._comanda_service.cancelar_item(item.id, motivo, pin_gerente)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()

    def _cancelar_comanda(self) -> None:
        if self._comanda is None:
            return
        modal = CancelamentoDialog(f"Cancelar comanda {self._comanda.id}", self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        motivo, pin_gerente = modal.resultado()

        self._label_erro.setText("")
        try:
            self._comanda_service.cancelar(self._comanda.id, motivo, pin_gerente)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        comanda_id = self._comanda.id
        self.atualizar()
        self.comanda_cancelada.emit(comanda_id)

    def _imprimir_producao(self) -> None:
        """Via de acréscimo: manda para a cozinha só o que ela ainda não viu."""
        if self._comanda is None:
            return
        comanda_id = self._comanda.id

        self._label_erro.setText("")
        try:
            resultados = executar_impressao(
                lambda: self._impressao_service.imprimir_comanda(comanda_id)
            )
        except _ERROS_SERVICE as erro:
            # Impressora com defeito não passa por aqui: volta dentro de
            # `resultados` com sucesso=False. Aqui só chega comanda inexistente
            # ou sessão perdida, que são erro de verdade.
            self._label_erro.setText(str(erro))
            return
        self._aviso_impressao.mostrar(resultados, vazio=_NADA_NOVO_PARA_IMPRIMIR)

    def _imprimir_segunda_via(self) -> None:
        """Repete a comanda inteira sem mexer no que já foi marcado como impresso."""
        if self._comanda is None:
            return
        comanda_id = self._comanda.id

        self._label_erro.setText("")
        try:
            resultados = executar_impressao(
                lambda: self._impressao_service.reimprimir_comanda(comanda_id)
            )
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._aviso_impressao.mostrar(resultados, vazio="Esta comanda não tem itens para reimprimir.")

    def _voltar_clicado(self) -> None:
        self.voltar.emit()

    def _solicitar_pagamento(self) -> None:
        if self._comanda is None:
            return
        self.pagamento_solicitado.emit(self._comanda.id)

    def _abrir_modal_adicionar_item(self) -> None:
        if self._comanda is None:
            return
        produtos = self._cardapio_service.listar_produtos_ativos()
        if not produtos:
            self._label_erro.setText("Não há produtos ativos no cardápio.")
            return

        modal = _AdicionarItemDialog(produtos, self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return

        produto_id, quantidade, observacao = modal.resultado()
        self._label_erro.setText("")
        try:
            self._comanda_service.lancar_item(
                self._comanda.id, produto_id, quantidade, observacao
            )
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()


class _AdicionarItemDialog(QDialog):
    """Modal `+ Item`: produto, quantidade e observação livre."""

    def __init__(self, produtos: list[Produto], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Adicionar item")
        self._produtos = produtos

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._combo_produto = QComboBox()
        for produto in produtos:
            self._combo_produto.addItem(f"{produto.nome} — {_formatar_reais(produto.preco)}", produto.id)
        formulario.addRow("Produto", self._combo_produto)

        self._campo_quantidade = QSpinBox()
        self._campo_quantidade.setMinimum(1)
        self._campo_quantidade.setMaximum(999)
        self._campo_quantidade.setValue(1)
        formulario.addRow("Quantidade", self._campo_quantidade)

        self._campo_observacao = QLineEdit()
        self._campo_observacao.setPlaceholderText("Ex.: sem cebola")
        formulario.addRow("Observação", self._campo_observacao)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Adicionar")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[int, int, str | None]:
        produto_id = self._combo_produto.currentData()
        quantidade = self._campo_quantidade.value()
        observacao = self._campo_observacao.text().strip() or None
        return produto_id, quantidade, observacao


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")
