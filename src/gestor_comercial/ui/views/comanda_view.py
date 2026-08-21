"""Detalhe da comanda: lista de itens + total, modal de adicionar item —
porte visual de `.comanda-detalhe`/`.tabela` e do modal `+ Item` do
front-end web (`GESTOR COMERCIAL/.../desktop/index.html` + `js/app.js`).

Fechamento, cancelamento e pagamento ficam para `pagamento_dialog.py` e o
modal de cancelamento (próximos itens da Fase 3) — esta tela cobre só a
lista de itens e o lançamento de novos.
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
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.exceptions import (
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)

_COLUNAS = ["Descrição", "Preço", "Qtd", "Total", ""]


class ComandaView(QWidget):
    """Lista de itens de uma comanda, com total e lançamento de novos itens."""

    def __init__(
        self,
        comanda_service: ComandaService,
        cardapio_service: CardapioService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._comanda_service = comanda_service
        self._cardapio_service = cardapio_service
        self._comanda: Comanda | None = None

        self._montar_layout()

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)

        cabecalho = QHBoxLayout()
        self._label_titulo = QLabel("")
        self._label_titulo.setStyleSheet("font-weight: 600; font-size: 18px;")
        cabecalho.addWidget(self._label_titulo)
        cabecalho.addStretch()

        self._botao_add_item = QPushButton("+ Item")
        self._botao_add_item.setProperty("variante", "secundario")
        self._botao_add_item.clicked.connect(self._abrir_modal_adicionar_item)
        cabecalho.addWidget(self._botao_add_item)
        layout_externo.addLayout(cabecalho)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout_externo.addWidget(self._label_erro)

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
        self._atualizar()

    def _atualizar(self) -> None:
        if self._comanda is None:
            return
        self._label_erro.setText("")

        titulo = f"Mesa {self._comanda.mesa.numero}" if self._comanda.mesa else "Balcão"
        self._label_titulo.setText(f"{titulo} — comanda {self._comanda.id}")

        itens = self._comanda_service.listar_itens(self._comanda.id)
        itens_ativos = [item for item in itens if not item.cancelado]

        self._tabela.setRowCount(len(itens_ativos))
        for linha, item in enumerate(itens_ativos):
            self._preencher_linha(linha, item)

        total = self._comanda_service.calcular_total(self._comanda.id)
        self._label_total.setText(_formatar_reais(total))

    def _preencher_linha(self, linha: int, item: ItemComanda) -> None:
        descricao = item.produto.nome
        if item.observacao:
            descricao += f" ({item.observacao})"
        total_item = item.preco_unit_congelado * item.quantidade

        self._tabela.setItem(linha, 0, QTableWidgetItem(descricao))
        self._tabela.setItem(linha, 1, QTableWidgetItem(_formatar_reais(item.preco_unit_congelado)))
        self._tabela.setItem(linha, 2, QTableWidgetItem(str(item.quantidade)))
        self._tabela.setItem(linha, 3, QTableWidgetItem(_formatar_reais(total_item)))

        botao_remover = QPushButton("Remover")
        botao_remover.setProperty("variante", "perigo")
        botao_remover.clicked.connect(lambda _checked=False, i=item: self._remover_item(i))
        self._tabela.setCellWidget(linha, 4, botao_remover)

    def _remover_item(self, item: ItemComanda) -> None:
        self._label_erro.setText("")
        try:
            self._comanda_service.remover_item(item.id)
        except (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError) as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar()

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
        except (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError) as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar()


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
