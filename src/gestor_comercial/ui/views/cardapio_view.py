"""Cardápio: tela única com Categorias (esquerda) e Produtos da categoria
selecionada (direita), ambos em ordem alfabética. Combo não é mais uma aba
separada — é um Produto normal com `is_combo=True`, ligado a ele
automaticamente pelo service assim que ganha o primeiro componente (ver
`CardapioService.associar_componente`). Aqui só exibimos a badge "COMBO" e
damos o botão "Gerenciar combo" pra abrir esse cadastro de componentes.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
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
from gestor_comercial.ui.widgets.busca_produto import BuscaProdutoWidget

_COLUNAS_PRODUTOS = ["Produto", "Tipo", "Preço", "Custo", "Status"]
_COLUNAS_COMPONENTES = ["Componente", "Quantidade"]

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

_ID_CATEGORIA = Qt.ItemDataRole.UserRole


def _por_nome(itens: list) -> list:
    """Ordem alfabética (A-Z) case-insensitive, como pedido na tela."""
    return sorted(itens, key=lambda item: item.nome.lower())


class CardapioView(QWidget):
    """Cardápio unificado: categorias à esquerda, produtos da categoria à direita."""

    def __init__(self, cardapio_service: CardapioService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = cardapio_service

        layout = QVBoxLayout(self)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout.addWidget(self._label_erro)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, stretch=1)

        self._painel_categorias = _CategoriasPainel(self._service, self._mostrar_erro)
        self._painel_produtos = _ProdutosPainel(self._service, self._mostrar_erro)
        splitter.addWidget(self._painel_categorias)
        splitter.addWidget(self._painel_produtos)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self._painel_categorias.categoria_selecionada.connect(self._painel_produtos.exibir_categoria)
        self._painel_categorias.alterado.connect(self._painel_produtos.atualizar)
        self._painel_produtos.alterado.connect(self._painel_categorias.atualizar_mantendo_selecao)

        self.atualizar()

    def atualizar(self) -> None:
        self._label_erro.setText("")
        self._painel_categorias.atualizar()

    def _mostrar_erro(self, mensagem: str) -> None:
        self._label_erro.setText(mensagem)


class _CategoriasPainel(QWidget):
    """Bloco da esquerda: lista de categorias em ordem alfabética."""

    categoria_selecionada = Signal(object)  # Categoria | None
    alterado = Signal()

    def __init__(self, service: CardapioService, mostrar_erro, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._mostrar_erro = mostrar_erro
        self._categorias: list[Categoria] = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Categorias</b>"))

        self._lista = QListWidget()
        self._lista.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._lista.currentRowChanged.connect(self._emitir_selecao)
        layout.addWidget(self._lista, stretch=1)

        barra1 = QHBoxLayout()
        botao_nova = QPushButton("Nova categoria")
        botao_nova.setProperty("variante", "primario")
        botao_nova.clicked.connect(self._criar)
        barra1.addWidget(botao_nova)
        self._botao_editar = QPushButton("Editar")
        self._botao_editar.setProperty("variante", "neutro")
        self._botao_editar.clicked.connect(self._editar)
        barra1.addWidget(self._botao_editar)
        layout.addLayout(barra1)

        barra2 = QHBoxLayout()
        self._botao_impressora = QPushButton("Impressora")
        self._botao_impressora.setProperty("variante", "neutro")
        self._botao_impressora.clicked.connect(self._associar_impressora)
        barra2.addWidget(self._botao_impressora)
        self._botao_status = QPushButton("Desativar")
        self._botao_status.setProperty("variante", "perigo")
        self._botao_status.clicked.connect(self._alternar_status)
        barra2.addWidget(self._botao_status)
        layout.addLayout(barra2)

        botao_excluir = QPushButton("Excluir categoria")
        botao_excluir.setProperty("variante", "perigo")
        botao_excluir.clicked.connect(self._excluir)
        layout.addWidget(botao_excluir)

        QShortcut(QKeySequence("Ctrl+N"), self, self._criar)
        QShortcut(QKeySequence(Qt.Key.Key_F2), self, self._editar)

    def atualizar(self) -> None:
        self._atualizar(manter_selecao=False)

    def atualizar_mantendo_selecao(self) -> None:
        self._atualizar(manter_selecao=True)

    def _atualizar(self, *, manter_selecao: bool) -> None:
        categoria_id_atual = self.categoria_selecionada_id() if manter_selecao else None
        self._categorias = _por_nome(self._service.listar_categorias())

        self._lista.blockSignals(True)
        self._lista.clear()
        for categoria in self._categorias:
            item = QListWidgetItem()
            item.setData(_ID_CATEGORIA, categoria.id)
            self._lista.addItem(item)
            self._lista.setItemWidget(item, _criar_linha_categoria(categoria))
        self._lista.blockSignals(False)

        indice = 0
        if categoria_id_atual is not None:
            for linha, categoria in enumerate(self._categorias):
                if categoria.id == categoria_id_atual:
                    indice = linha
                    break
        if self._categorias:
            self._lista.setCurrentRow(indice)
        else:
            self._emitir_selecao(-1)

    def categoria_selecionada_id(self) -> int | None:
        item = self._lista.currentItem()
        return item.data(_ID_CATEGORIA) if item is not None else None

    def _categoria_atual(self) -> Categoria | None:
        categoria_id = self.categoria_selecionada_id()
        if categoria_id is None:
            return None
        for categoria in self._categorias:
            if categoria.id == categoria_id:
                return categoria
        return None

    def _emitir_selecao(self, linha: int) -> None:
        categoria = self._categoria_atual() if linha >= 0 else None
        self._botao_status.setEnabled(categoria is not None)
        self._botao_status.setText(
            "Ativar" if categoria is not None and not categoria.ativo else "Desativar"
        )
        self._botao_editar.setEnabled(categoria is not None)
        self._botao_impressora.setEnabled(categoria is not None)
        self.categoria_selecionada.emit(categoria)

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
        categoria = self._categoria_atual()
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
        self.atualizar_mantendo_selecao()
        self.alterado.emit()

    def _associar_impressora(self) -> None:
        categoria = self._categoria_atual()
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
        self.atualizar_mantendo_selecao()

    def _alternar_status(self) -> None:
        categoria = self._categoria_atual()
        if categoria is None:
            return
        self._mostrar_erro("")
        try:
            if categoria.ativo:
                self._service.desativar_categoria(categoria.id)
            else:
                self._service.ativar_categoria(categoria.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar_mantendo_selecao()
        self.alterado.emit()

    def _excluir(self) -> None:
        categoria = self._categoria_atual()
        if categoria is None:
            return
        resposta = QMessageBox.question(
            self,
            "Excluir categoria",
            f"Excluir a categoria '{categoria.nome}' permanentemente? Esta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        self._mostrar_erro("")
        try:
            self._service.excluir_categoria(categoria.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()


class _ProdutosPainel(QWidget):
    """Bloco da direita: produtos da categoria selecionada, em ordem alfabética."""

    alterado = Signal()

    def __init__(self, service: CardapioService, mostrar_erro, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._mostrar_erro = mostrar_erro
        self._categoria: Categoria | None = None
        self._produtos: list[Produto] = []

        layout = QVBoxLayout(self)

        self._titulo = QLabel("<b>Produtos</b>")
        layout.addWidget(self._titulo)

        self._tabela = QTableWidget(0, len(_COLUNAS_PRODUTOS))
        self._tabela.setHorizontalHeaderLabels(_COLUNAS_PRODUTOS)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        cabecalho = self._tabela.horizontalHeader()
        cabecalho.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for coluna in (1, 2, 3, 4):
            cabecalho.setSectionResizeMode(coluna, QHeaderView.ResizeMode.Fixed)
        self._tabela.setColumnWidth(1, 90)
        self._tabela.setColumnWidth(2, 90)
        self._tabela.setColumnWidth(3, 90)
        self._tabela.setColumnWidth(4, 110)
        self._tabela.verticalHeader().setDefaultSectionSize(36)
        self._tabela.currentCellChanged.connect(lambda *_: self._atualizar_botoes())
        layout.addWidget(self._tabela, stretch=1)

        acoes = QHBoxLayout()
        self._botao_novo = QPushButton("Novo produto")
        self._botao_novo.setProperty("variante", "primario")
        self._botao_novo.clicked.connect(self._criar)
        acoes.addWidget(self._botao_novo)

        self._botao_editar = QPushButton("Editar")
        self._botao_editar.setProperty("variante", "neutro")
        self._botao_editar.clicked.connect(self._editar)
        acoes.addWidget(self._botao_editar)

        self._botao_combo = QPushButton("Gerenciar combo")
        self._botao_combo.setProperty("variante", "neutro")
        self._botao_combo.clicked.connect(self._gerenciar_combo)
        acoes.addWidget(self._botao_combo)

        self._botao_status = QPushButton("Desativar")
        self._botao_status.setProperty("variante", "perigo")
        self._botao_status.clicked.connect(self._alternar_status)
        acoes.addWidget(self._botao_status)

        self._botao_excluir = QPushButton("Excluir")
        self._botao_excluir.setProperty("variante", "perigo")
        self._botao_excluir.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        self._botao_excluir.clicked.connect(self._excluir)
        acoes.addWidget(self._botao_excluir)
        acoes.addStretch()
        layout.addLayout(acoes)

        QShortcut(QKeySequence("Ctrl+N"), self, self._criar)
        QShortcut(QKeySequence(Qt.Key.Key_F2), self, self._editar)

        self._atualizar_botoes()

    def exibir_categoria(self, categoria: Categoria | None) -> None:
        self._categoria = categoria
        self.atualizar()

    def atualizar(self) -> None:
        categoria = self._categoria
        if categoria is not None:
            # Categoria pode ter sido renomeada/desativada por fora; pega a versão atual.
            todas = {c.id: c for c in self._service.listar_categorias()}
            categoria = todas.get(categoria.id)
            self._categoria = categoria

        if categoria is None:
            self._titulo.setText("<b>Produtos</b> — selecione uma categoria")
            self._produtos = []
        else:
            self._titulo.setText(f"<b>Produtos de {categoria.nome}</b>")
            self._produtos = _por_nome(
                [p for p in self._service.listar_produtos() if p.categoria_id == categoria.id]
            )

        self._tabela.setRowCount(len(self._produtos))
        for linha, produto in enumerate(self._produtos):
            self._tabela.setItem(linha, 0, QTableWidgetItem(produto.nome))
            self._tabela.setCellWidget(linha, 1, _criar_badge_tipo(produto.is_combo))
            self._tabela.setItem(linha, 2, QTableWidgetItem(_formatar_reais(produto.preco)))
            self._tabela.setItem(linha, 3, QTableWidgetItem(_formatar_reais(produto.custo)))
            self._tabela.setCellWidget(linha, 4, _criar_badge_status(produto.ativo))

        self._atualizar_botoes()

    def _produto_selecionado(self) -> Produto | None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._produtos):
            return None
        return self._produtos[linha]

    def _atualizar_botoes(self) -> None:
        produto = self._produto_selecionado()
        self._botao_novo.setEnabled(self._categoria is not None)
        self._botao_editar.setEnabled(produto is not None)
        self._botao_status.setEnabled(produto is not None)
        self._botao_status.setText("Ativar" if produto is not None and not produto.ativo else "Desativar")
        self._botao_excluir.setEnabled(produto is not None)
        self._botao_combo.setEnabled(produto is not None)

    def _categorias_ativas(self) -> list[Categoria]:
        return _por_nome(self._service.listar_categorias_ativas())

    def _criar(self) -> None:
        categorias = self._categorias_ativas()
        if not categorias:
            self._mostrar_erro("Cadastre uma categoria ativa antes de criar um produto.")
            return
        categoria_inicial_id = self._categoria.id if self._categoria else None
        modal = _ProdutoDialog("Novo produto", categorias, self, categoria_id_inicial=categoria_inicial_id)
        self._mostrar_erro("")
        while modal.exec() == QDialog.DialogCode.Accepted:
            nome, preco, custo, categoria_id, descricao = modal.resultado()
            if self._produto_duplicado(nome) and not self._confirmar_duplicidade(nome):
                continue
            try:
                self._service.criar_produto(nome, preco, categoria_id, custo, descricao)
            except _ERROS_SERVICE as erro:
                modal.mostrar_erro_servico(str(erro))
                continue
            self.atualizar()
            self.alterado.emit()
            return

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
        self._mostrar_erro("")
        while modal.exec() == QDialog.DialogCode.Accepted:
            nome, preco, custo, categoria_id, descricao = modal.resultado()
            if self._produto_duplicado(nome, ignorar_id=produto.id) and not self._confirmar_duplicidade(nome):
                continue
            try:
                self._service.atualizar_produto(produto.id, nome, preco, custo, categoria_id, descricao)
            except _ERROS_SERVICE as erro:
                modal.mostrar_erro_servico(str(erro))
                continue
            self.atualizar()
            self.alterado.emit()
            return

    def _produto_duplicado(self, nome: str, *, ignorar_id: int | None = None) -> bool:
        """Compara nomes ignorando maiúsculas/minúsculas e espaços nas pontas.

        Abrange ativos e desativados (`listar_produtos`, não só os ativos) —
        um item desativado ainda representa o mesmo produto no catálogo.
        """
        alvo = nome.strip().casefold()
        return any(
            produto.nome.strip().casefold() == alvo
            for produto in self._service.listar_produtos()
            if produto.id != ignorar_id
        )

    def _confirmar_duplicidade(self, nome: str) -> bool:
        """Soft-warning: pergunta se o cadastro duplicado é intencional.

        Retorna True só se o usuário escolher "Criar Mesmo Assim". O modal de
        cadastro por trás não é tocado — quem chama decide se reabre (mesma
        instância, mesmos dados) ou segue com o salvamento.
        """
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Item Já Cadastrado")
        caixa.setIcon(QMessageBox.Icon.Warning)
        caixa.setText(
            f"Já existe um item cadastrado com o nome \"{nome}\". "
            "Deseja cadastrar este item duplicado mesmo assim?"
        )
        botao_voltar = caixa.addButton("Voltar e Editar", QMessageBox.ButtonRole.RejectRole)
        botao_forcar = caixa.addButton("Criar Mesmo Assim", QMessageBox.ButtonRole.AcceptRole)
        # Enter confirma o caminho seguro; só um clique deliberado força a duplicidade.
        caixa.setDefaultButton(botao_voltar)
        caixa.setEscapeButton(botao_voltar)
        caixa.exec()
        return caixa.clickedButton() is botao_forcar

    def _gerenciar_combo(self) -> None:
        produto = self._produto_selecionado()
        if produto is None:
            return
        candidatos = [p for p in self._service.listar_produtos_ativos() if p.id != produto.id]
        modal = _ComboComponentesDialog(self._service, produto, candidatos, self)
        modal.exec()
        self._mostrar_erro("")
        self.atualizar()
        self.alterado.emit()

    def _alternar_status(self) -> None:
        produto = self._produto_selecionado()
        if produto is None:
            return
        self._mostrar_erro("")
        try:
            if produto.ativo:
                self._service.desativar_produto(produto.id)
            else:
                self._service.ativar_produto(produto.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()

    def _excluir(self) -> None:
        produto = self._produto_selecionado()
        if produto is None:
            return
        resposta = QMessageBox.question(
            self,
            "Excluir produto",
            f"Excluir o produto '{produto.nome}' permanentemente? Esta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        self._mostrar_erro("")
        try:
            self._service.excluir_produto(produto.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()


class _ComboComponentesDialog(QDialog):
    """Cadastro de componentes de um combo (o produto já selecionado no painel)."""

    def __init__(
        self,
        service: CardapioService,
        combo: Produto,
        candidatos: list[Produto],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._combo = combo
        self._candidatos = candidatos
        self._componentes: list[ComboItem] = []
        self.setWindowTitle(f"Combo: {combo.nome}")

        layout = QVBoxLayout(self)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout.addWidget(self._label_erro)

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

        fechar = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        fechar.rejected.connect(self.accept)
        fechar.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        layout.addWidget(fechar)

        self._atualizar_componentes()

    def _atualizar_componentes(self) -> None:
        self._label_erro.setText("")
        try:
            self._componentes = self._service.listar_componentes(self._combo.id)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            self._componentes = []
        self._tabela.setRowCount(len(self._componentes))
        for linha, item in enumerate(self._componentes):
            self._tabela.setItem(linha, 0, QTableWidgetItem(item.produto.nome))
            self._tabela.setItem(linha, 1, QTableWidgetItem(str(item.quantidade)))

    def _adicionar_componente(self) -> None:
        candidatos = [p for p in self._candidatos if p.id != self._combo.id]
        if not candidatos:
            self._label_erro.setText("Não há outro produto disponível para virar componente.")
            return
        modal = _ComponenteDialog(candidatos, self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        produto_id, quantidade = modal.resultado()

        self._label_erro.setText("")
        try:
            self._service.associar_componente(self._combo.id, produto_id, quantidade)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar_componentes()

    def _remover_componente(self) -> None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._componentes):
            return
        item = self._componentes[linha]
        self._label_erro.setText("")
        try:
            self._service.remover_componente(item.id)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
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
    """Modal de criação/edição de produto: nome, preço, custo, categoria e descrição.

    Não tem campo "é combo": isso o service decide sozinho, a partir de o
    produto ter ou não componentes (ver `_ComboComponentesDialog`).
    """

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
        self._erro_nome = _criar_rotulo_erro()
        formulario.addRow("", self._erro_nome)

        self._campo_preco = QLineEdit(_formatar_campo(preco_inicial))
        formulario.addRow("Preço", self._campo_preco)
        self._erro_preco = _criar_rotulo_erro()
        formulario.addRow("", self._erro_preco)

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

        self._erro_geral = _criar_rotulo_erro()
        layout.addWidget(self._erro_geral)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self._ao_confirmar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _ao_confirmar(self) -> None:
        """Só fecha o modal (accept) se a validação local passar.

        Em caso de erro, os campos preenchidos permanecem intactos — o modal
        nunca é recriado nem fechado por falha de validação.
        """
        if self._validar():
            self.accept()

    def _validar(self) -> bool:
        valido = True
        foco: QLineEdit | None = None

        nome = self._campo_nome.text().strip()
        if len(nome) < 2:
            _marcar_erro(self._campo_nome, self._erro_nome, "O nome do produto é obrigatório (mínimo 2 caracteres).")
            foco = foco or self._campo_nome
            valido = False
        else:
            _limpar_erro(self._campo_nome, self._erro_nome)

        preco_valido = True
        try:
            preco = Decimal(self._campo_preco.text().strip().replace(",", "."))
            if preco <= 0:
                preco_valido = False
        except InvalidOperation:
            preco_valido = False
        if not preco_valido:
            _marcar_erro(self._campo_preco, self._erro_preco, "Informe um preço válido, maior que zero.")
            foco = foco or self._campo_preco
            valido = False
        else:
            _limpar_erro(self._campo_preco, self._erro_preco)

        if foco is not None:
            foco.setFocus()
        return valido

    def mostrar_erro_servico(self, mensagem: str) -> None:
        """Exibe um erro vindo do backend sem fechar o modal nem perder dados."""
        self._erro_geral.setText(mensagem)
        self._erro_geral.setVisible(True)
        self._campo_nome.setFocus()

    def resultado(self) -> tuple[str, Decimal, Decimal, int, str | None]:
        nome = self._campo_nome.text().strip()
        preco = Decimal(self._campo_preco.text().strip().replace(",", "."))
        texto_custo = self._campo_custo.text().strip()
        custo = Decimal(texto_custo.replace(",", ".")) if texto_custo else Decimal("0")
        categoria_id = self._seletor_categoria.currentData()
        descricao = self._campo_descricao.text().strip() or None
        return nome, preco, custo, categoria_id, descricao


class _ComponenteDialog(QDialog):
    """Modal de associação de componente a um combo: busca instantânea de produto + quantidade."""

    def __init__(self, candidatos: list[Produto], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Adicionar componente")
        self.setMinimumWidth(420)
        self._produto_id: int | None = None

        layout = QVBoxLayout(self)

        self._busca = BuscaProdutoWidget(candidatos)
        self._busca.produto_selecionado.connect(self._produto_selecionado)
        self._busca.busca_cancelada.connect(self.reject)
        layout.addWidget(self._busca)

        formulario = QFormLayout()

        self._campo_quantidade = QSpinBox()
        self._campo_quantidade.setMinimum(1)
        self._campo_quantidade.setMaximum(99)
        self._campo_quantidade.setValue(1)
        formulario.addRow("Quantidade", self._campo_quantidade)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        botoes.rejected.connect(self.reject)

        self._botao_adicionar = botoes.addButton("Adicionar", QDialogButtonBox.ButtonRole.AcceptRole)
        self._botao_adicionar.setProperty("variante", "primario")
        self._botao_adicionar.clicked.connect(self._busca.confirmar_selecionado)

        layout.addWidget(botoes)

    def _produto_selecionado(self, produto_id: int) -> None:
        self._produto_id = produto_id
        self.accept()

    def resultado(self) -> tuple[int, int]:
        return self._produto_id, self._campo_quantidade.value()


def _criar_linha_categoria(categoria: Categoria) -> QWidget:
    """Linha da lista de categorias: nome à esquerda, badge de status à direita."""
    linha = QWidget()
    layout = QHBoxLayout(linha)
    layout.setContentsMargins(4, 0, 4, 0)
    layout.addWidget(QLabel(categoria.nome), stretch=1)
    layout.addWidget(_criar_badge_status(categoria.ativo))
    return linha


def _celula_centralizada(widget: QWidget) -> QWidget:
    """Envolve um badge para uso em `setCellWidget`.

    `setCellWidget` estica o widget pra ocupar a célula inteira; sem isso o
    QLabel do badge herdaria o fundo escuro padrão de QWidget (base.qss) e
    pintaria a célula toda, virando uma barra sólida em vez de um selo
    compacto centralizado.
    """
    celula = QWidget()
    celula.setStyleSheet("background: transparent;")
    layout = QHBoxLayout(celula)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(widget)
    return celula


def _criar_badge_status(ativo: bool) -> QWidget:
    """Etiqueta de status: verde para ATIVO, cinza/vermelho para DESATIVADO."""
    label = QLabel("ATIVO" if ativo else "DESATIVADO")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if ativo:
        cor_fundo, cor_texto = "#16a34a", "#f0fdf4"
    else:
        cor_fundo, cor_texto = "#57534e", "#fafaf9"
    label.setStyleSheet(
        f"background-color: {cor_fundo};"
        f"color: {cor_texto};"
        "font-weight: 700;"
        "font-size: 11px;"
        "border-radius: 4px;"
        "padding: 3px 10px;"
        "margin: 0px;"
    )
    return _celula_centralizada(label)


def _criar_badge_tipo(is_combo: bool) -> QWidget:
    """Etiqueta "COMBO" (âmbar/contrastante) na coluna Tipo; produto comum fica em branco."""
    label = QLabel("COMBO" if is_combo else "")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet("background: transparent;")
    if is_combo:
        label.setStyleSheet(
            "background-color: #f59e0b;"
            "color: #1c1917;"
            "font-weight: 700;"
            "font-size: 11px;"
            "border-radius: 4px;"
            "padding: 3px 10px;"
            "margin: 0px;"
        )
    return _celula_centralizada(label)


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")


def _formatar_campo(valor: Decimal | None) -> str:
    if valor is None:
        return ""
    return f"{valor:.2f}".replace(".", ",")


def _criar_rotulo_erro() -> QLabel:
    rotulo = QLabel()
    rotulo.setStyleSheet("color: #c0392b; font-size: 11px;")
    rotulo.setWordWrap(True)
    rotulo.setVisible(False)
    return rotulo


def _marcar_erro(campo: QLineEdit, rotulo: QLabel, mensagem: str) -> None:
    campo.setStyleSheet("border: 1px solid #c0392b; background-color: #fdecea;")
    rotulo.setText(mensagem)
    rotulo.setVisible(True)


def _limpar_erro(campo: QLineEdit, rotulo: QLabel) -> None:
    campo.setStyleSheet("")
    rotulo.setVisible(False)
