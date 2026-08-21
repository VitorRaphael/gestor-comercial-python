"""Cardápio: CRUD de categorias, produtos e combos — porte visual da tela de
cardápio do front-end web (`GESTOR COMERCIAL/.../desktop/js/app.js`, funções
`salvarProduto`/`salvarCategoria`/`montarCombo`).

Cadastrar, editar, desativar e excluir exigem gerente logado — quem barra
isso é `CardapioService` (via `AuthService.exigir_gerente`); aqui só se
mostra o erro que o service levantar.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Signal
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
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.combo_item import ComboItem
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)

_COLUNAS_CATEGORIAS = ["Nome", "Impressora", "Status"]
_COLUNAS_PRODUTOS = ["Nome", "Categoria", "Preço", "Custo", "Combo", "Status"]
_COLUNAS_COMPONENTES = ["Componente", "Quantidade"]

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)


class CardapioView(QWidget):
    """CRUD de categoria, produto e combo, em abas."""

    def __init__(self, cardapio_service: CardapioService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = cardapio_service

        layout = QVBoxLayout(self)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout.addWidget(self._label_erro)

        self._abas = QTabWidget()
        layout.addWidget(self._abas)

        self._aba_categorias = _CategoriasTab(self._service, self._mostrar_erro)
        self._aba_produtos = _ProdutosTab(self._service, self._mostrar_erro)
        self._aba_combos = _CombosTab(self._service, self._mostrar_erro)

        self._abas.addTab(self._aba_categorias, "Categorias")
        self._abas.addTab(self._aba_produtos, "Produtos")
        self._abas.addTab(self._aba_combos, "Combos")

        # Categoria/produto mudando numa aba pode afetar as combos de outra
        # (nome exibido, lista de produtos disponíveis).
        self._aba_categorias.alterado.connect(self._aba_produtos.atualizar)
        self._aba_produtos.alterado.connect(self._aba_combos.atualizar)

        self.atualizar()

    def atualizar(self) -> None:
        self._label_erro.setText("")
        self._aba_categorias.atualizar()
        self._aba_produtos.atualizar()
        self._aba_combos.atualizar()

    def _mostrar_erro(self, mensagem: str) -> None:
        self._label_erro.setText(mensagem)


class _CategoriasTab(QWidget):
    alterado = Signal()

    def __init__(self, service: CardapioService, mostrar_erro, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._mostrar_erro = mostrar_erro
        self._categorias: list[Categoria] = []

        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        barra.addStretch()
        botao_nova = QPushButton("Nova categoria")
        botao_nova.setProperty("variante", "primario")
        botao_nova.clicked.connect(self._criar)
        barra.addWidget(botao_nova)
        layout.addLayout(barra)

        self._tabela = QTableWidget(0, len(_COLUNAS_CATEGORIAS))
        self._tabela.setHorizontalHeaderLabels(_COLUNAS_CATEGORIAS)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._tabela)

        acoes = QHBoxLayout()
        self._botao_editar = QPushButton("Editar")
        self._botao_editar.clicked.connect(self._editar)
        acoes.addWidget(self._botao_editar)

        self._botao_impressora = QPushButton("Associar impressora")
        self._botao_impressora.clicked.connect(self._associar_impressora)
        acoes.addWidget(self._botao_impressora)

        self._botao_desativar = QPushButton("Desativar")
        self._botao_desativar.setProperty("variante", "perigo")
        self._botao_desativar.clicked.connect(self._desativar)
        acoes.addWidget(self._botao_desativar)

        self._botao_excluir = QPushButton("Excluir")
        self._botao_excluir.setProperty("variante", "perigo")
        self._botao_excluir.clicked.connect(self._excluir)
        acoes.addWidget(self._botao_excluir)
        acoes.addStretch()
        layout.addLayout(acoes)

    def atualizar(self) -> None:
        self._categorias = self._service.listar_categorias()
        self._tabela.setRowCount(len(self._categorias))
        for linha, categoria in enumerate(self._categorias):
            self._tabela.setItem(linha, 0, QTableWidgetItem(categoria.nome))
            nome_impressora = categoria.impressora.nome if categoria.impressora else "—"
            self._tabela.setItem(linha, 1, QTableWidgetItem(nome_impressora))
            status = "Ativa" if categoria.ativo else "Desativada"
            self._tabela.setItem(linha, 2, QTableWidgetItem(status))

    def _categoria_selecionada(self) -> Categoria | None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._categorias):
            return None
        return self._categorias[linha]

    def _criar(self) -> None:
        modal = _CategoriaDialog("Nova categoria", self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        self._mostrar_erro("")
        try:
            self._service.criar_categoria(modal.nome())
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()

    def _editar(self) -> None:
        categoria = self._categoria_selecionada()
        if categoria is None:
            return
        modal = _CategoriaDialog("Editar categoria", self, nome_inicial=categoria.nome)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        self._mostrar_erro("")
        try:
            self._service.editar_categoria(categoria.id, modal.nome())
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()

    def _associar_impressora(self) -> None:
        categoria = self._categoria_selecionada()
        if categoria is None:
            return
        impressoras = self._service.listar_impressoras()
        if not impressoras:
            self._mostrar_erro("Não há impressoras cadastradas.")
            return
        modal = _AssociarImpressoraDialog(impressoras, self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        self._mostrar_erro("")
        try:
            self._service.associar_impressora(categoria.id, modal.impressora_id())
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()

    def _desativar(self) -> None:
        categoria = self._categoria_selecionada()
        if categoria is None:
            return
        self._mostrar_erro("")
        try:
            self._service.desativar_categoria(categoria.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()

    def _excluir(self) -> None:
        categoria = self._categoria_selecionada()
        if categoria is None:
            return
        self._mostrar_erro("")
        try:
            self._service.excluir_categoria(categoria.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()


class _ProdutosTab(QWidget):
    alterado = Signal()

    def __init__(self, service: CardapioService, mostrar_erro, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._mostrar_erro = mostrar_erro
        self._produtos: list[Produto] = []

        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        barra.addStretch()
        botao_novo = QPushButton("Novo produto")
        botao_novo.setProperty("variante", "primario")
        botao_novo.clicked.connect(self._criar)
        barra.addWidget(botao_novo)
        layout.addLayout(barra)

        self._tabela = QTableWidget(0, len(_COLUNAS_PRODUTOS))
        self._tabela.setHorizontalHeaderLabels(_COLUNAS_PRODUTOS)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._tabela)

        acoes = QHBoxLayout()
        self._botao_editar = QPushButton("Editar")
        self._botao_editar.clicked.connect(self._editar)
        acoes.addWidget(self._botao_editar)

        self._botao_desativar = QPushButton("Desativar")
        self._botao_desativar.setProperty("variante", "perigo")
        self._botao_desativar.clicked.connect(self._desativar)
        acoes.addWidget(self._botao_desativar)

        self._botao_excluir = QPushButton("Excluir")
        self._botao_excluir.setProperty("variante", "perigo")
        self._botao_excluir.clicked.connect(self._excluir)
        acoes.addWidget(self._botao_excluir)
        acoes.addStretch()
        layout.addLayout(acoes)

    def atualizar(self) -> None:
        self._produtos = self._service.listar_produtos()
        self._tabela.setRowCount(len(self._produtos))
        for linha, produto in enumerate(self._produtos):
            self._tabela.setItem(linha, 0, QTableWidgetItem(produto.nome))
            self._tabela.setItem(linha, 1, QTableWidgetItem(produto.categoria.nome))
            self._tabela.setItem(linha, 2, QTableWidgetItem(_formatar_reais(produto.preco)))
            self._tabela.setItem(linha, 3, QTableWidgetItem(_formatar_reais(produto.custo)))
            self._tabela.setItem(linha, 4, QTableWidgetItem("Sim" if produto.is_combo else "Não"))
            status = "Ativo" if produto.ativo else "Desativado"
            self._tabela.setItem(linha, 5, QTableWidgetItem(status))

    def _produto_selecionado(self) -> Produto | None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._produtos):
            return None
        return self._produtos[linha]

    def _categorias_ativas(self) -> list[Categoria]:
        return self._service.listar_categorias_ativas()

    def _criar(self) -> None:
        categorias = self._categorias_ativas()
        if not categorias:
            self._mostrar_erro("Cadastre uma categoria ativa antes de criar um produto.")
            return
        modal = _ProdutoDialog("Novo produto", categorias, self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            nome, preco, custo, categoria_id, descricao = modal.resultado()
        except InvalidOperation:
            self._mostrar_erro("Preço ou custo inválido. Informe um valor em reais, como 12.50.")
            return

        self._mostrar_erro("")
        try:
            self._service.criar_produto(nome, preco, categoria_id, custo, descricao)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()

    def _editar(self) -> None:
        produto = self._produto_selecionado()
        if produto is None:
            return
        categorias = self._categorias_ativas()
        modal = _ProdutoDialog(
            "Editar produto",
            categorias,
            self,
            nome_inicial=produto.nome,
            preco_inicial=produto.preco,
            custo_inicial=produto.custo,
            categoria_id_inicial=produto.categoria_id,
            descricao_inicial=produto.descricao,
        )
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            nome, preco, custo, categoria_id, descricao = modal.resultado()
        except InvalidOperation:
            self._mostrar_erro("Preço ou custo inválido. Informe um valor em reais, como 12.50.")
            return

        self._mostrar_erro("")
        try:
            self._service.atualizar_produto(produto.id, nome, preco, custo, categoria_id, descricao)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()

    def _desativar(self) -> None:
        produto = self._produto_selecionado()
        if produto is None:
            return
        self._mostrar_erro("")
        try:
            self._service.desativar_produto(produto.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()

    def _excluir(self) -> None:
        produto = self._produto_selecionado()
        if produto is None:
            return
        self._mostrar_erro("")
        try:
            self._service.excluir_produto(produto.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()


class _CombosTab(QWidget):
    def __init__(self, service: CardapioService, mostrar_erro, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._mostrar_erro = mostrar_erro
        self._combos: list[Produto] = []
        self._componentes: list[ComboItem] = []

        layout = QVBoxLayout(self)

        barra_combo = QHBoxLayout()
        barra_combo.addWidget(QLabel("Combo"))
        self._seletor_combo = QComboBox()
        self._seletor_combo.currentIndexChanged.connect(self._atualizar_componentes)
        barra_combo.addWidget(self._seletor_combo, stretch=1)
        layout.addLayout(barra_combo)

        self._tabela = QTableWidget(0, len(_COLUNAS_COMPONENTES))
        self._tabela.setHorizontalHeaderLabels(_COLUNAS_COMPONENTES)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._tabela)

        acoes = QHBoxLayout()
        botao_adicionar = QPushButton("Adicionar componente")
        botao_adicionar.setProperty("variante", "primario")
        botao_adicionar.clicked.connect(self._adicionar_componente)
        acoes.addWidget(botao_adicionar)

        botao_remover = QPushButton("Remover componente")
        botao_remover.setProperty("variante", "perigo")
        botao_remover.clicked.connect(self._remover_componente)
        acoes.addWidget(botao_remover)
        acoes.addStretch()
        layout.addLayout(acoes)

    def atualizar(self) -> None:
        combo_selecionado_id = self._combo_id_selecionado()
        self._combos = self._service.listar_produtos_ativos()
        self._seletor_combo.blockSignals(True)
        self._seletor_combo.clear()
        for produto in self._combos:
            self._seletor_combo.addItem(produto.nome, produto.id)
        self._seletor_combo.blockSignals(False)

        if combo_selecionado_id is not None:
            indice = self._seletor_combo.findData(combo_selecionado_id)
            if indice >= 0:
                self._seletor_combo.setCurrentIndex(indice)
        self._atualizar_componentes()

    def _combo_id_selecionado(self) -> int | None:
        return self._seletor_combo.currentData()

    def _atualizar_componentes(self) -> None:
        combo_id = self._combo_id_selecionado()
        if combo_id is None:
            self._componentes = []
            self._tabela.setRowCount(0)
            return
        self._mostrar_erro("")
        try:
            self._componentes = self._service.listar_componentes(combo_id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            self._componentes = []
        self._tabela.setRowCount(len(self._componentes))
        for linha, item in enumerate(self._componentes):
            self._tabela.setItem(linha, 0, QTableWidgetItem(item.produto.nome))
            self._tabela.setItem(linha, 1, QTableWidgetItem(str(item.quantidade)))

    def _adicionar_componente(self) -> None:
        combo_id = self._combo_id_selecionado()
        if combo_id is None:
            self._mostrar_erro("Selecione um combo.")
            return
        candidatos = [produto for produto in self._combos if produto.id != combo_id]
        if not candidatos:
            self._mostrar_erro("Não há outro produto disponível para virar componente.")
            return
        modal = _ComponenteDialog(candidatos, self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        produto_id, quantidade = modal.resultado()

        self._mostrar_erro("")
        try:
            self._service.associar_componente(combo_id, produto_id, quantidade)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self._atualizar_componentes()

    def _remover_componente(self) -> None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._componentes):
            return
        item = self._componentes[linha]
        self._mostrar_erro("")
        try:
            self._service.remover_componente(item.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self._atualizar_componentes()


class _CategoriaDialog(QDialog):
    """Modal de criação/edição de categoria: só o nome."""

    def __init__(self, titulo: str, parent: QWidget | None = None, *, nome_inicial: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_nome = QLineEdit(nome_inicial)
        formulario.addRow("Nome", self._campo_nome)
        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def nome(self) -> str:
        return self._campo_nome.text().strip()


class _AssociarImpressoraDialog(QDialog):
    """Modal de escolha de impressora para uma categoria."""

    def __init__(self, impressoras: list, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Associar impressora")
        self._impressoras = impressoras

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._seletor = QComboBox()
        for impressora in impressoras:
            self._seletor.addItem(impressora.nome, impressora.id)
        formulario.addRow("Impressora", self._seletor)
        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def impressora_id(self) -> int:
        return self._seletor.currentData()


class _ProdutoDialog(QDialog):
    """Modal de criação/edição de produto: nome, preço, custo, categoria e descrição."""

    def __init__(
        self,
        titulo: str,
        categorias: list[Categoria],
        parent: QWidget | None = None,
        *,
        nome_inicial: str = "",
        preco_inicial: Decimal | None = None,
        custo_inicial: Decimal | None = None,
        categoria_id_inicial: int | None = None,
        descricao_inicial: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_nome = QLineEdit(nome_inicial)
        formulario.addRow("Nome", self._campo_nome)

        self._campo_preco = QLineEdit(_formatar_campo(preco_inicial))
        formulario.addRow("Preço", self._campo_preco)

        self._campo_custo = QLineEdit(_formatar_campo(custo_inicial))
        self._campo_custo.setPlaceholderText("Opcional, padrão 0,00")
        formulario.addRow("Custo", self._campo_custo)

        self._seletor_categoria = QComboBox()
        for categoria in categorias:
            self._seletor_categoria.addItem(categoria.nome, categoria.id)
        if categoria_id_inicial is not None:
            indice = self._seletor_categoria.findData(categoria_id_inicial)
            if indice >= 0:
                self._seletor_categoria.setCurrentIndex(indice)
        formulario.addRow("Categoria", self._seletor_categoria)

        self._campo_descricao = QLineEdit(descricao_inicial or "")
        self._campo_descricao.setPlaceholderText("Opcional")
        formulario.addRow("Descrição", self._campo_descricao)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[str, Decimal, Decimal, int, str | None]:
        nome = self._campo_nome.text().strip()
        preco = Decimal(self._campo_preco.text().strip().replace(",", "."))
        texto_custo = self._campo_custo.text().strip()
        custo = Decimal(texto_custo.replace(",", ".")) if texto_custo else Decimal("0")
        categoria_id = self._seletor_categoria.currentData()
        descricao = self._campo_descricao.text().strip() or None
        return nome, preco, custo, categoria_id, descricao


class _ComponenteDialog(QDialog):
    """Modal de associação de componente a um combo: produto e quantidade."""

    def __init__(self, candidatos: list[Produto], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Adicionar componente")

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._seletor_produto = QComboBox()
        for produto in candidatos:
            self._seletor_produto.addItem(produto.nome, produto.id)
        formulario.addRow("Produto", self._seletor_produto)

        self._campo_quantidade = QSpinBox()
        self._campo_quantidade.setMinimum(1)
        self._campo_quantidade.setMaximum(99)
        self._campo_quantidade.setValue(1)
        formulario.addRow("Quantidade", self._campo_quantidade)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[int, int]:
        return self._seletor_produto.currentData(), self._campo_quantidade.value()


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")


def _formatar_campo(valor: Decimal | None) -> str:
    if valor is None:
        return ""
    return f"{valor:.2f}".replace(".", ",")
