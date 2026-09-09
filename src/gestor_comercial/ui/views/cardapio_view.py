"""Cardápio: árvore Categoria → Subcategoria (esquerda) e os produtos da
seleção (direita), tudo em ordem alfabética.

## A hierarquia é o desenho da tela (§9.9)

A primeira versão da subcategoria (§9.8) a tratou como uma **etiqueta pendurada
no produto**: um selo ao lado do nome, na linha do item. Estava de cabeça para
baixo, e o Vitor apontou — a subcategoria **contém** produtos, não o contrário.
Abrir "Lanches" tem que mostrar as subdivisões dele, e é entrando numa
subdivisão que se chega aos itens.

Então a tela virou a hierarquia:

* a **árvore** da esquerda expande a categoria e mostra `Todas`, cada
  subcategoria e (quando há item solto) `Sem subcategoria`, com a contagem de
  cada uma. Uma categoria por vez fica aberta — com quinze categorias, deixar
  todas expandidas transformaria a coluna num rolo;
* a **tabela** da direita agrupa por subcategoria, com uma linha de cabeçalho
  por grupo (`GUARNIÇÕES · 3 ITENS`). O selo que existia na linha do produto
  **saiu**: ele dizia a mesma coisa que o cabeçalho do grupo, uma vez por
  linha.

Combo não é aba separada — é um Produto com `is_combo=True`, ligado pelo
service assim que ganha o primeiro componente (ver
`CardapioService.associar_componente`). A badge "COMBO" perdeu a coluna própria
e virou um selo ao lado do nome: a coluna existia para uma marca que aparece em
4 dos 113 produtos do cardápio real, e a largura dela fazia falta ao nome.

Cabeçalho traz 4 KPIs (categorias, subcategorias, produtos, margem média) e as
duas ações de topo (Gerenciar combo / Novo item). Editar/Ativar-Desativar/
Excluir de produto moram no rodapé do painel de produtos; os mesmos três em
categoria saem por menu de contexto (botão direito na árvore) — a categoria não
tem barra própria no design, só o "+ Nova categoria".
Os atalhos de teclado (Ctrl+N/F2/Delete) continuam despachando pelo
`_contexto` (qual lado está com foco), sem precisar de botões visíveis.
Associação de impressora não mora aqui — isso é responsabilidade exclusiva
da tela "Impressoras". O que esta tela faz é **mostrar** a impressora da
categoria no cabeçalho da direita (`ACOMPANHAMENTOS · COZINHA`), porque é a
informação que diz para onde os itens daquela categoria vão sair.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from decimal import Decimal

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import (
    QColor,
    QKeySequence,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
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
from gestor_comercial.services.imagem_service import processar_imagem_produto, remover_thumbnail
from gestor_comercial.services.texto import chave_de_agrupamento
from gestor_comercial.services.dinheiro import ZERO
from gestor_comercial.ui.formatacao import (
    formatar_para_campo,
    formatar_reais,
    safe_decimal,
)
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.busca_produto import BuscaProdutoWidget
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.flow_layout import FlowLayout
from gestor_comercial.ui.widgets.modais import descartar_modal, executar_modal
from gestor_comercial.ui.widgets.subcategoria_dialog import SubcategoriaDialog
from gestor_comercial.ui.widgets.tabelas import definir_celula, limpar_tabela
from gestor_comercial.ui.widgets.thumbnail_cache import obter_pixmap

# A coluna "Tipo" saiu: ela existia para a badge COMBO, que aparece em 4 dos
# 113 produtos do cardápio real e agora é um selo ao lado do nome. Os 90px que
# ela ocupava voltaram para a coluna "Produto", que é a que estava apertada.
_COLUNAS_PRODUTOS = ["Produto", "Preço", "Custo", "Margem", "Status"]
_COLUNAS_COMPONENTES = ["Componente", "Quantidade"]

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

# O que cada item da árvore carrega. São papéis de dado do Qt e não colunas: o
# item mostra um widget próprio (a categoria) ou o texto dele mesmo (a
# subcategoria), e a identidade tem que viajar junto em qualquer um dos dois.
_PAPEL_CATEGORIA = Qt.ItemDataRole.UserRole
_PAPEL_CHAVE = Qt.ItemDataRole.UserRole + 1
_PAPEL_ROTULO = Qt.ItemDataRole.UserRole + 2

# As duas seleções da árvore que não são o nome de uma subcategoria. Começam com
# `\x00` porque QUALQUER string é um nome de subcategoria válido: usar `""` para
# "todas" faria uma subcategoria chamada "" (impossível hoje, mas a garantia é
# do service e não desta tela) colidir com a seleção.
_SUB_TODAS = "\x00todas"
_SUB_NENHUMA = "\x00nenhuma"

_ROTULO_TODAS = "Todas"
_ROTULO_SEM_SUBCATEGORIA = "Sem subcategoria"


@dataclass(frozen=True, slots=True)
class DadosProduto:
    """O que o modal de produto devolve — o formulário inteiro, de uma vez.

    Era uma tupla de seis posições desempacotada em dois lugares
    (`_ProdutosPainel.criar` e `.editar`). A subcategoria seria a sétima, e uma
    tupla de sete que se desempacota por ORDEM é o tipo de coisa que quebra
    calada: trocar duas posições do mesmo tipo — `descricao` e `subcategoria`,
    ambas `str | None` — passaria pelo interpretador e gravaria a descrição no
    lugar da subcategoria.

    Mesma decisão (e mesmo formato) de `DadosFuncionario`, `DadosMovimento` e
    `DadosAbertura`: o diálogo devolve dados, a view chama o service.
    """

    nome: str
    preco: Decimal
    custo: Decimal
    categoria_id: int
    descricao: str | None
    imagem_path: str | None
    # O ID da subdivisão escolhida, ou `None` para "Sem subcategoria" — desde o
    # §9.9 a subcategoria é uma entidade, e a tela escolhe uma que existe em vez
    # de digitar um nome novo.
    subcategoria: int | None


@dataclass(frozen=True, slots=True)
class SelecaoCardapio:
    """Onde a árvore está: uma categoria e, dentro dela, o que mostrar.

    `chave` é `_SUB_TODAS` (a categoria inteira, agrupada), `_SUB_NENHUMA` (só
    os itens ainda não classificados) ou o nome de uma subcategoria.

    Existe como tipo próprio, e não como dois parâmetros de sinal, porque os
    dois andam sempre juntos: uma subcategoria sem a categoria dela não
    identifica nada — "Podrão" pode existir em duas categorias.
    """

    categoria: Categoria | None
    chave: str = _SUB_TODAS

    @property
    def e_todas(self) -> bool:
        return self.chave == _SUB_TODAS


@dataclass(frozen=True, slots=True)
class _Grupo:
    """Uma subcategoria e os produtos dentro dela, prontos para a tabela.

    `nome=None` é o grupo dos itens sem subcategoria — o último da lista, e o
    único cujo rótulo não é dado pelo gerente.
    """

    nome: str | None
    produtos: list[Produto]

    @property
    def rotulo(self) -> str:
        return self.nome if self.nome is not None else _ROTULO_SEM_SUBCATEGORIA

    @property
    def chave(self) -> str:
        return self.nome if self.nome is not None else _SUB_NENHUMA


def _agrupar_por_subcategoria(produtos: list[Produto]) -> list[_Grupo]:
    """Os produtos repartidos entre as subcategorias, em ordem alfabética.

    O grupo dos **sem subcategoria** vai por último de propósito: numa categoria
    em organização, ele é a fila de trabalho de quem está classificando, e
    fila de trabalho fica no fim, não na frente do que já está pronto.

    Grupo vazio não sai daqui: esta função reparte PRODUTOS, e produto nenhum
    significa grupo nenhum. Quem precisa desenhar uma subdivisão recém-criada,
    ainda sem itens, monta o `_Grupo` vazio por conta própria — é o painel de
    produtos, que tem a lista de subdivisões cadastradas em mãos.
    """
    por_nome: dict[str, list[Produto]] = {}
    soltos: list[Produto] = []
    for produto in produtos:
        if produto.subcategoria is not None:
            por_nome.setdefault(produto.subcategoria.nome, []).append(produto)
        else:
            soltos.append(produto)

    grupos = [
        _Grupo(nome, _por_nome(por_nome[nome]))
        for nome in sorted(por_nome, key=str.lower)
    ]
    if soltos:
        grupos.append(_Grupo(None, _por_nome(soltos)))
    return grupos


def _por_nome(itens: list) -> list:
    """Ordem alfabética (A-Z) case-insensitive, como pedido na tela."""
    return sorted(itens, key=lambda item: item.nome.lower())


def _margem_percentual(produto: Produto) -> float:
    if produto.preco is None or produto.preco <= 0:
        return 0.0
    return float((produto.preco - produto.custo) / produto.preco * 100)


class CardapioView(QWidget):
    """Cardápio unificado: KPIs no topo, categorias à esquerda, produtos à direita."""

    def __init__(self, cardapio_service: CardapioService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = cardapio_service
        self._contexto = "categoria"  # "categoria" | "produto" — quem recebe os atalhos F2/Delete

        self._painel_categorias = _CategoriasPainel(self._service, self._mostrar_erro)
        self._painel_produtos = _ProdutosPainel(self._service, self._mostrar_erro)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        layout.addLayout(self._criar_cabecalho())
        layout.addLayout(self._criar_grade_kpis())

        self._label_erro = QLabel("")
        self._label_erro.setObjectName("labelErro")
        layout.addWidget(self._label_erro)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._painel_categorias)
        splitter.addWidget(self._painel_produtos)
        splitter.setStretchFactor(0, 30)
        splitter.setStretchFactor(1, 70)
        # Tamanhos iniciais explícitos: só o fator de esticar deixava a árvore
        # nascer no `sizeHint` (estreita demais para "Acompanhamentos") e ela só
        # ganhava largura se alguém arrastasse o divisor.
        splitter.setSizes([330, 790])
        layout.addWidget(splitter, stretch=1)

        self._painel_categorias.selecao_mudou.connect(self._painel_produtos.exibir)
        self._painel_categorias.selecao_mudou.connect(self._ao_mudar_selecao_categoria)
        self._painel_categorias.alterado.connect(self._ao_alterar_categoria)
        self._painel_produtos.alterado.connect(self._ao_alterar_produto)
        self._painel_produtos.produto_selecionado.connect(self._ao_mudar_selecao_produto)

        # Detecta em qual lado está o foco pra saber quem recebe F2/Delete/Ctrl+N.
        self._painel_categorias.arvore.installEventFilter(self)
        self._painel_produtos.tabela.installEventFilter(self)

        QShortcut(QKeySequence("Ctrl+N"), self, self._novo_padrao)
        QShortcut(QKeySequence(Qt.Key.Key_F2), self, self._editar)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, self._excluir)

        self.atualizar()

    def _criar_cabecalho(self) -> QHBoxLayout:
        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(12)

        coluna_titulo = QVBoxLayout()
        coluna_titulo.setSpacing(2)
        titulo = QLabel("Cardápio")
        titulo.setStyleSheet("font-size: 22px; font-weight: 700;")
        coluna_titulo.addWidget(titulo)
        subtitulo = QLabel("Categorias, subcategorias, produtos e margens da operação")
        subtitulo.setProperty("variante", "fraco")
        coluna_titulo.addWidget(subtitulo)
        cabecalho.addLayout(coluna_titulo)
        cabecalho.addStretch()

        self._botao_combo = QPushButton("Gerenciar combo")
        self._botao_combo.setProperty("variante", "neutro")
        self._botao_combo.setEnabled(False)
        self._botao_combo.clicked.connect(self._painel_produtos.gerenciar_combo)
        cabecalho.addWidget(self._botao_combo)

        botao_novo_item = QPushButton("Novo item")
        botao_novo_item.setProperty("variante", "primario")
        botao_novo_item.clicked.connect(self._painel_produtos.criar)
        cabecalho.addWidget(botao_novo_item)

        return cabecalho

    def _criar_grade_kpis(self) -> QHBoxLayout:
        grade = QHBoxLayout()
        grade.setSpacing(12)

        # "Preço médio" saiu para a SUBCATEGORIAS entrar. Média de preço sobre
        # um cardápio que vai de R$ 0,50 (chiclete) a R$ 48,00 (dois espetos de
        # picanha) não é um número que decida nada; quantas subdivisões existem,
        # sim — é o que diz se a organização do catálogo avançou.
        self._kpi_categorias = _CardKpi("🗂️", "Categorias")
        self._kpi_subcategorias = _CardKpi("🌿", "Subcategorias")
        self._kpi_produtos = _CardKpi("📦", "Produtos")
        self._kpi_margem_media = _CardKpi("%", "Margem média")
        for card in (
            self._kpi_categorias,
            self._kpi_subcategorias,
            self._kpi_produtos,
            self._kpi_margem_media,
        ):
            grade.addWidget(card)
        return grade

    @nao_deixa_escapar(retorno=False)
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - override Qt
        if event.type() == QEvent.Type.FocusIn:
            if obj is self._painel_categorias.arvore:
                self._contexto = "categoria"
            elif obj is self._painel_produtos.tabela:
                self._contexto = "produto"
        return super().eventFilter(obj, event)

    def _ao_mudar_selecao_categoria(self, _selecao: SelecaoCardapio) -> None:
        pass

    def _ao_mudar_selecao_produto(self, produto: Produto | None) -> None:
        self._botao_combo.setEnabled(produto is not None)

    def _ao_alterar_categoria(self) -> None:
        self._painel_produtos.atualizar()
        self._atualizar_kpis()

    def _ao_alterar_produto(self) -> None:
        self._painel_categorias.atualizar_mantendo_selecao()
        self._atualizar_kpis()

    def _novo_padrao(self) -> None:
        """Ctrl+N segue o contexto atual: categoria selecionada cria produto, senão categoria."""
        if self._contexto == "produto" or self._painel_categorias.categoria_atual() is not None:
            self._painel_produtos.criar()
        else:
            self._painel_categorias.criar()

    def _editar(self) -> None:
        if self._contexto == "categoria":
            self._painel_categorias.editar()
        else:
            self._painel_produtos.editar()

    def _excluir(self) -> None:
        if self._contexto == "categoria":
            self._painel_categorias.excluir()
        else:
            self._painel_produtos.excluir()

    def atualizar(self) -> None:
        """Recarrega a tela SEM tirar o gerente de onde ele estava.

        `atualizar()` é chamado no boot e depois de cada alteração (editar um
        produto, criar uma subdivisão). No boot não há seleção e a árvore abre
        na primeira categoria; depois, voltar para a primeira seria a tela
        largando o trabalho a cada item salvo — é o mesmo contrato que a tabela
        de produtos já cumpre com `preservar_selecao=True`, e que
        `test_selecao_sobrevive_ao_refresh.py` cobra do lado dela.
        """
        self._label_erro.setText("")
        self._painel_categorias.atualizar_mantendo_selecao()
        self._atualizar_kpis()

    def _atualizar_kpis(self) -> None:
        categorias = self._service.listar_categorias()
        produtos = self._service.listar_produtos()

        self._kpi_categorias.definir_valor(str(len(categorias)))
        self._kpi_produtos.definir_valor(str(len(produtos)))
        self._kpi_subcategorias.definir_valor(
            str(sum(len(self._service.listar_subcategorias(c.id)) for c in categorias))
        )

        produtos_precificados = [p for p in produtos if p.preco and p.preco > 0]
        margem_media = (
            sum(_margem_percentual(p) for p in produtos_precificados) / len(produtos_precificados)
            if produtos_precificados
            else 0.0
        )
        self._kpi_margem_media.definir_valor(f"{margem_media:.0f}%")

    def _mostrar_erro(self, mensagem: str) -> None:
        self._label_erro.setText(mensagem)


class _CardKpi(QFrame):
    """Card de métrica: ícone em selo quadrado, rótulo em caixa alta e valor grande."""

    def __init__(self, icone: str, titulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("variante", "cartao")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        selo_icone = QLabel(icone)
        selo_icone.setFixedSize(36, 36)
        selo_icone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        selo_icone.setStyleSheet(
            "background-color: rgba(229, 169, 60, 0.14);"
            "border-radius: 8px;"
            "font-size: 16px;"
        )
        layout.addWidget(selo_icone)

        rotulo = QLabel(titulo.upper())
        rotulo.setProperty("variante", "fraco")
        rotulo.setStyleSheet("font-size: 11px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(rotulo)

        self._label_valor = QLabel("—")
        self._label_valor.setStyleSheet("font-weight: 700; font-size: 24px;")
        layout.addWidget(self._label_valor)

    def definir_valor(self, texto: str) -> None:
        self._label_valor.setText(texto)


class _BarraMargem(QWidget):
    """Barra fina de margem: trilho + preenchimento verde proporcional ao percentual."""

    _ALTURA = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self._ALTURA)
        self._trilho = QFrame(self)
        self._trilho.setObjectName("margemTrilho")
        self._preenchida = QFrame(self)
        self._preenchida.setObjectName("margemPreenchida")
        self._percentual = 0.0

    def definir_percentual(self, percentual: float) -> None:
        self._percentual = max(0.0, min(100.0, percentual))
        self._reposicionar()

    @nao_deixa_escapar()
    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (override Qt)
        super().resizeEvent(event)
        self._reposicionar()

    def _reposicionar(self) -> None:
        self._trilho.setGeometry(0, 0, self.width(), self._ALTURA)
        largura = round(self.width() * self._percentual / 100)
        self._preenchida.setGeometry(0, 0, largura, self._ALTURA)


class _CategoriasPainel(QFrame):
    """Bloco da esquerda: a árvore Categoria → Subcategoria (§9.9).

    Era uma lista rasa de categorias. Virou árvore porque a subcategoria
    **contém** produtos: abrir "Lanches" tem que mostrar as subdivisões dele,
    e é entrando numa que se chega aos itens.

    Uma categoria expandida por vez, de propósito. O cardápio real tem quinze
    categorias; deixar todas abertas produziria uma coluna de sessenta linhas
    onde a rolagem vira o trabalho principal — e o gerente organiza uma
    categoria de cada vez, não quinze.

    O `QTreeWidget` substituiu o `QListWidget` também por um motivo de
    desenho: `setItemWidget` numa lista **não** dimensiona o item, e as linhas
    de duas alturas (nome + "2 SUBS · 5 ITENS") vinham sendo desenhadas dentro
    da altura de uma — o nome e o subtítulo saíam cortados ao meio. Aqui cada
    item recebe o `sizeHint` explícito de quem mora dentro dele.
    """

    selecao_mudou = Signal(object)  # SelecaoCardapio
    alterado = Signal()

    ALTURA_CATEGORIA_PX = 50
    ALTURA_SUBCATEGORIA_PX = 30
    RECUO_PX = 14
    # A coluna da contagem, à direita de cada subdivisão. Fixa e estreita: o
    # número é o dado secundário da linha, e uma coluna elástica roubaria do
    # nome, que é o que se procura.
    LARGURA_CONTAGEM_PX = 34
    # Piso da coluna inteira. Sem ele o `QSplitter` a espremia até "Acompanha…",
    # e nome de categoria cortado é o defeito que esta tela veio consertar.
    LARGURA_MINIMA_PX = 300

    def __init__(
        self,
        service: CardapioService,
        mostrar_erro: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._service = service
        self._mostrar_erro = mostrar_erro
        self._categorias: list[Categoria] = []
        self._expandida_id: int | None = None
        self._selecao = SelecaoCardapio(categoria=None)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        cabecalho = QHBoxLayout()
        rotulo = QLabel("CATEGORIAS")
        rotulo.setObjectName("cardapioEyebrow")
        cabecalho.addWidget(rotulo)
        cabecalho.addStretch()
        self._label_contador = QLabel("0")
        self._label_contador.setProperty("variante", "fraco")
        cabecalho.addWidget(self._label_contador)
        layout.addLayout(cabecalho)

        self._campo_busca = QLineEdit()
        self._campo_busca.setPlaceholderText("🔎  Buscar categoria")
        self._campo_busca.textChanged.connect(self._filtrar)
        layout.addWidget(self._campo_busca)

        self.arvore = QTreeWidget(columnCount=2)
        self.arvore.setObjectName("arvoreCardapio")
        self.arvore.setHeaderHidden(True)
        self.arvore.setIndentation(self.RECUO_PX)
        # Sem a seta de expandir do Qt: ela é pintada na área de `::branch`, que
        # não aceita o mesmo arredondamento do item e sobrava como um quadrado
        # de outra cor ao lado da linha selecionada. O chevron passou a ser
        # desenhado dentro do widget da categoria, onde o estilo é nosso.
        self.arvore.setRootIsDecorated(False)
        self.arvore.setUniformRowHeights(False)
        cabecalho_arvore = self.arvore.header()
        # `stretchLastSection` é o padrão do Qt e nasce LIGADO: com ele a coluna
        # da contagem tomava metade da largura (medido: 146 de 293px) e o nome
        # da categoria era cortado em "Acompa". Desligar é o que faz o
        # `setSectionResizeMode` abaixo valer alguma coisa.
        cabecalho_arvore.setStretchLastSection(False)
        cabecalho_arvore.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        cabecalho_arvore.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        cabecalho_arvore.resizeSection(1, self.LARGURA_CONTAGEM_PX)
        self.arvore.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.arvore.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.arvore.currentItemChanged.connect(self._ao_trocar_item)
        self.arvore.itemClicked.connect(self._ao_clicar)
        self.arvore.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.arvore.customContextMenuRequested.connect(self._menu_contexto)
        layout.addWidget(self.arvore, stretch=1)

        # Empilhados e não lado a lado: com a coluna em 300px, dois botões
        # numa linha cortavam o próprio rótulo ("ova categ", "Subcategor") —
        # exatamente o defeito de aperto que `test_telas_cabem_na_tela.py`
        # existe para pegar.
        acoes = QVBoxLayout()
        acoes.setSpacing(6)
        botao_nova = QPushButton("+ Nova categoria")
        botao_nova.setProperty("variante", "tracejado")
        botao_nova.clicked.connect(self.criar)
        acoes.addWidget(botao_nova)

        # A criação de subdivisão fica ao lado da de categoria porque as duas
        # são a mesma tarefa — montar a estrutura do cardápio —, e escondê-la só
        # no menu de contexto deixaria a funcionalidade invisível para quem não
        # clica com o botão direito.
        self._botao_nova_sub = QPushButton("+ Subcategoria")
        self._botao_nova_sub.setProperty("variante", "tracejado")
        self._botao_nova_sub.setEnabled(False)
        self._botao_nova_sub.clicked.connect(self.criar_subcategoria)
        acoes.addWidget(self._botao_nova_sub)
        layout.addLayout(acoes)

        self.setMinimumWidth(self.LARGURA_MINIMA_PX)

    # ------------------------------------------------------------------
    # Montagem da árvore
    # ------------------------------------------------------------------

    def atualizar(self) -> None:
        self._montar(manter_selecao=False)

    def atualizar_mantendo_selecao(self) -> None:
        self._montar(manter_selecao=True)

    def _montar(self, *, manter_selecao: bool) -> None:
        alvo = self._selecao if manter_selecao else None

        self._categorias = _por_nome(self._service.listar_categorias())
        self._label_contador.setText(str(len(self._categorias)))
        produtos_por_categoria = self._contar_produtos()
        contagem_sub = self._service.contagem_de_produtos_por_subcategoria()

        if alvo is not None and alvo.categoria is not None:
            self._expandida_id = alvo.categoria.id
        elif self._expandida_id is None and self._categorias:
            self._expandida_id = self._categorias[0].id

        self.arvore.blockSignals(True)
        self.arvore.clear()
        item_a_selecionar: QTreeWidgetItem | None = None
        for categoria in self._categorias:
            subcategorias = self._service.listar_subcategorias(categoria.id)
            produtos = produtos_por_categoria.get(categoria.id, 0)
            item = self._criar_item_categoria(categoria, len(subcategorias), produtos)
            self.arvore.addTopLevelItem(item)
            # Depois do `addTopLevelItem`, e não antes: o span mora no MODELO da
            # árvore, e um item ainda solto não tem modelo onde gravá-lo. A
            # linha da categoria hospeda um widget próprio e precisa da largura
            # inteira — sem isto ele para na borda da coluna da contagem.
            item.setFirstColumnSpanned(True)
            self.arvore.setItemWidget(
                item,
                0,
                _criar_linha_categoria(
                    categoria,
                    len(subcategorias),
                    produtos,
                    expandida=categoria.id == self._expandida_id,
                ),
            )

            classificados = sum(contagem_sub.get(sub.id, 0) for sub in subcategorias)
            filhos = [(_SUB_TODAS, _ROTULO_TODAS, produtos)]
            filhos += [
                (sub.nome, sub.nome, contagem_sub.get(sub.id, 0)) for sub in subcategorias
            ]
            soltos = produtos - classificados
            if subcategorias and soltos > 0:
                filhos.append((_SUB_NENHUMA, _ROTULO_SEM_SUBCATEGORIA, soltos))

            for chave, rotulo, total in filhos:
                filho = self._criar_item_filho(categoria, chave, rotulo, total)
                item.addChild(filho)
                if alvo is not None and alvo.categoria is not None:
                    if categoria.id == alvo.categoria.id and chave == alvo.chave:
                        item_a_selecionar = filho

            item.setExpanded(categoria.id == self._expandida_id)
        self.arvore.blockSignals(False)

        self._filtrar(self._campo_busca.text())

        if item_a_selecionar is None:
            item_a_selecionar = self._primeiro_filho_visivel()
        if item_a_selecionar is not None:
            self.arvore.setCurrentItem(item_a_selecionar)
        else:
            self._selecao = SelecaoCardapio(categoria=None)
            self.selecao_mudou.emit(self._selecao)

    def _criar_item_categoria(
        self, categoria: Categoria, subcategorias: int, produtos: int
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setData(0, _PAPEL_CATEGORIA, categoria.id)
        item.setData(0, _PAPEL_CHAVE, _SUB_TODAS)
        # O `sizeHint` explícito é o que faltava na lista antiga: sem ele, o
        # widget de duas linhas era desenhado na altura de uma e saía cortado.
        item.setSizeHint(0, QSize(0, self.ALTURA_CATEGORIA_PX))
        return item

    def _criar_item_filho(
        self, categoria: Categoria, chave: str, rotulo: str, total: int
    ) -> QTreeWidgetItem:
        filho = QTreeWidgetItem()
        filho.setData(0, _PAPEL_CATEGORIA, categoria.id)
        filho.setData(0, _PAPEL_CHAVE, chave)
        filho.setData(0, _PAPEL_ROTULO, rotulo)
        filho.setSizeHint(0, QSize(0, self.ALTURA_SUBCATEGORIA_PX))
        filho.setText(0, rotulo)
        filho.setText(1, str(total))
        filho.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return filho

    def _contar_produtos(self) -> dict[int, int]:
        contagem: dict[int, int] = {}
        for produto in self._service.listar_produtos():
            contagem[produto.categoria_id] = contagem.get(produto.categoria_id, 0) + 1
        return contagem

    # ------------------------------------------------------------------
    # Seleção
    # ------------------------------------------------------------------

    def _ao_clicar(self, item: QTreeWidgetItem, _coluna: int) -> None:
        """Clicar numa categoria abre ela e fecha a anterior.

        A troca acontece no CLIQUE e não na seleção porque a seleção também
        muda ao andar de seta pelo teclado, e ali fechar o ramo debaixo do
        cursor tiraria o próprio item selecionado da tela.
        """
        if item.parent() is not None:
            return
        categoria_id = item.data(0, _PAPEL_CATEGORIA)
        if self._expandida_id == categoria_id and item.isExpanded():
            return
        self._expandida_id = categoria_id
        for indice in range(self.arvore.topLevelItemCount()):
            topo = self.arvore.topLevelItem(indice)
            aberta = topo.data(0, _PAPEL_CATEGORIA) == categoria_id
            topo.setExpanded(aberta)
            # O chevron mora no widget da linha, então virá-lo é redesenhar a
            # linha — barato (um `QLabel` por categoria) e sem um segundo
            # caminho de estado para divergir do `isExpanded()`.
            widget = self.arvore.itemWidget(topo, 0)
            if isinstance(widget, QWidget):
                seta = widget.findChild(QLabel, "categoriaSeta")
                if seta is not None:
                    seta.setText("⌄" if aberta else "›")

    def _ao_trocar_item(
        self, atual: QTreeWidgetItem | None, _anterior: QTreeWidgetItem | None
    ) -> None:
        if atual is None:
            return
        categoria = self._categoria_por_id(atual.data(0, _PAPEL_CATEGORIA))
        chave = atual.data(0, _PAPEL_CHAVE) or _SUB_TODAS
        # Clicar na linha da CATEGORIA equivale a escolher "Todas" dentro dela:
        # é o que o gerente espera de clicar no nome do grupo, e evita um
        # estado em que a direita não sabe o que mostrar.
        self._selecao = SelecaoCardapio(categoria=categoria, chave=chave)
        self._botao_nova_sub.setEnabled(categoria is not None)
        self.selecao_mudou.emit(self._selecao)

    def _categoria_por_id(self, categoria_id: int | None) -> Categoria | None:
        for categoria in self._categorias:
            if categoria.id == categoria_id:
                return categoria
        return None

    def _primeiro_filho_visivel(self) -> QTreeWidgetItem | None:
        """A primeira subdivisão selecionável — abrindo a categoria dela.

        O `setExpanded` não é enfeite: o Qt **recusa** `setCurrentItem` num
        filho de ramo fechado, e sem ele esta função devolvia um item que a
        árvore ignorava. O efeito era a seleção "ficar onde estava" por acidente
        do Qt, e não porque alguém tivesse decidido isso — o tipo de coisa que
        funciona até o dia em que o ramo já está aberto.
        """
        for indice in range(self.arvore.topLevelItemCount()):
            topo = self.arvore.topLevelItem(indice)
            if topo.isHidden() or topo.childCount() == 0:
                continue
            self._expandida_id = topo.data(0, _PAPEL_CATEGORIA)
            topo.setExpanded(True)
            return topo.child(0)
        return None

    def selecao_atual(self) -> SelecaoCardapio:
        return self._selecao

    def categoria_atual(self) -> Categoria | None:
        return self._selecao.categoria

    def subcategoria_selecionada(self) -> str | None:
        """O NOME da subcategoria destacada, ou `None` em "Todas"/"Sem subcategoria".

        É o que decide se o menu de contexto oferece renomear/excluir: os dois
        pseudo-itens da árvore não são subdivisões e não podem ser editados.
        """
        chave = self._selecao.chave
        if chave in (_SUB_TODAS, _SUB_NENHUMA):
            return None
        return chave

    # ------------------------------------------------------------------
    # Busca
    # ------------------------------------------------------------------

    def _filtrar(self, texto: str) -> None:
        """Esconde categoria que não casa — pelo nome dela OU de uma subdivisão.

        Buscar "podrão" e não achar nada porque "Podrão" é subcategoria, e não
        categoria, seria a busca mentindo sobre o que existe no cardápio. A
        categoria que casa por uma filha abre sozinha, senão o resultado ficaria
        escondido dentro de um ramo fechado.
        """
        alvo = chave_de_agrupamento(texto) if texto.strip() else ""
        for indice in range(self.arvore.topLevelItemCount()):
            item = self.arvore.topLevelItem(indice)
            if not alvo:
                item.setHidden(False)
                item.setExpanded(item.data(0, _PAPEL_CATEGORIA) == self._expandida_id)
                continue
            nomes = [self._nome_da_categoria(item)] + [
                item.child(pos).data(0, _PAPEL_ROTULO) or ""
                for pos in range(item.childCount())
            ]
            casou = any(alvo in chave_de_agrupamento(nome) for nome in nomes)
            item.setHidden(not casou)
            if casou:
                item.setExpanded(True)

    def _nome_da_categoria(self, item: QTreeWidgetItem) -> str:
        categoria = self._categoria_por_id(item.data(0, _PAPEL_CATEGORIA))
        return categoria.nome if categoria is not None else ""

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------

    def _menu_contexto(self, posicao) -> None:
        item = self.arvore.itemAt(posicao)
        if item is None:
            return
        self.arvore.setCurrentItem(item)
        categoria = self.categoria_atual()
        if categoria is None:
            return

        menu = QMenu(self)
        if self.subcategoria_selecionada() is not None:
            menu.addAction("Renomear subcategoria", self.editar_subcategoria)
            menu.addAction("Excluir subcategoria", self.excluir_subcategoria)
        else:
            menu.addAction("Nova subcategoria", self.criar_subcategoria)
            menu.addSeparator()
            menu.addAction("Editar categoria", self.editar)
            menu.addAction("Ativar" if not categoria.ativo else "Desativar", self.alternar_status)
            menu.addAction("Excluir categoria", self.excluir)
        menu.exec(self.arvore.viewport().mapToGlobal(posicao))

    def criar(self) -> None:
        modal = _CategoriaDialog("Nova categoria", self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        self._mostrar_erro("")
        try:
            self._service.criar_categoria(modal.nome())
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()
        self.alterado.emit()

    def criar_subcategoria(self) -> None:
        """Abre o cartão de cadastro de subdivisão na categoria selecionada."""
        categoria = self.categoria_atual()
        if categoria is None:
            self._mostrar_erro("Selecione uma categoria antes de criar uma subcategoria.")
            return
        existentes = [s.nome for s in self._service.listar_subcategorias(categoria.id)]
        modal = SubcategoriaDialog(
            categoria.nome,
            categoria.impressora.nome if categoria.impressora is not None else None,
            existentes,
            self,
        )
        self._mostrar_erro("")
        try:
            while modal.exec() == QDialog.DialogCode.Accepted:
                try:
                    self._service.criar_subcategoria(categoria.id, modal.resultado().nome)
                except _ERROS_SERVICE as erro:
                    modal.mostrar_erro_servico(str(erro))
                    continue
                self.atualizar_mantendo_selecao()
                self.alterado.emit()
                return
        finally:
            descartar_modal(modal)

    def editar_subcategoria(self) -> None:
        categoria = self.categoria_atual()
        nome_atual = self.subcategoria_selecionada()
        if categoria is None or nome_atual is None:
            return
        subcategoria = self._subcategoria_por_nome(categoria.id, nome_atual)
        if subcategoria is None:
            return
        existentes = [s.nome for s in self._service.listar_subcategorias(categoria.id)]
        modal = SubcategoriaDialog(
            categoria.nome,
            categoria.impressora.nome if categoria.impressora is not None else None,
            existentes,
            self,
            nome_inicial=subcategoria.nome,
        )
        self._mostrar_erro("")
        try:
            while modal.exec() == QDialog.DialogCode.Accepted:
                try:
                    self._service.editar_subcategoria(subcategoria.id, modal.resultado().nome)
                except _ERROS_SERVICE as erro:
                    modal.mostrar_erro_servico(str(erro))
                    continue
                self.atualizar_mantendo_selecao()
                self.alterado.emit()
                return
        finally:
            descartar_modal(modal)

    def excluir_subcategoria(self) -> None:
        categoria = self.categoria_atual()
        nome_atual = self.subcategoria_selecionada()
        if categoria is None or nome_atual is None:
            return
        subcategoria = self._subcategoria_por_nome(categoria.id, nome_atual)
        if subcategoria is None:
            return

        caixa = QMessageBox(self)
        caixa.setWindowTitle("Excluir subcategoria")
        caixa.setIcon(QMessageBox.Icon.Warning)
        # A mensagem diz o que acontece com os PRODUTOS, que é a única dúvida
        # real de quem clica: eles não somem, voltam para "Sem subcategoria".
        caixa.setText(
            f"Excluir a subcategoria '{subcategoria.nome}'?\n\n"
            "Os produtos dela NÃO são excluídos: eles voltam para "
            "\"Sem subcategoria\" e continuam à venda, na mesma impressora."
        )
        botao_cancelar = caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        botao_confirmar = caixa.addButton("Excluir", QMessageBox.ButtonRole.DestructiveRole)
        botao_confirmar.setProperty("variante", "perigo")
        caixa.setDefaultButton(botao_cancelar)
        caixa.setEscapeButton(botao_cancelar)
        executar_modal(caixa)
        if caixa.clickedButton() is not botao_confirmar:
            return

        self._mostrar_erro("")
        try:
            self._service.excluir_subcategoria(subcategoria.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self._selecao = SelecaoCardapio(categoria=categoria, chave=_SUB_TODAS)
        self.atualizar_mantendo_selecao()
        self.alterado.emit()

    def _subcategoria_por_nome(self, categoria_id: int, nome: str):
        for subcategoria in self._service.listar_subcategorias(categoria_id):
            if subcategoria.nome == nome:
                return subcategoria
        return None

    def editar(self) -> None:
        categoria = self.categoria_atual()
        if categoria is None:
            return
        modal = _CategoriaDialog("Editar categoria", self, nome_inicial=categoria.nome)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        self._mostrar_erro("")
        try:
            self._service.editar_categoria(categoria.id, modal.nome())
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar_mantendo_selecao()
        self.alterado.emit()

    def alternar_status(self) -> None:
        categoria = self.categoria_atual()
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

    def excluir(self) -> None:
        categoria = self.categoria_atual()
        if categoria is None:
            return
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Atenção: Exclusão de Categoria")
        caixa.setIcon(QMessageBox.Icon.Warning)
        caixa.setText(
            f"Você tem certeza que deseja excluir a categoria '{categoria.nome}'? "
            "Todos os produtos vinculados a ela também serão excluídos permanentemente."
        )
        botao_cancelar = caixa.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        botao_confirmar = caixa.addButton("Sim, excluir tudo", QMessageBox.ButtonRole.DestructiveRole)
        botao_confirmar.setProperty("variante", "perigo")
        caixa.setDefaultButton(botao_cancelar)
        caixa.setEscapeButton(botao_cancelar)
        executar_modal(caixa)
        if caixa.clickedButton() is not botao_confirmar:
            return
        self._mostrar_erro("")
        try:
            self._service.excluir_categoria(categoria.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self._expandida_id = None
        self.atualizar()
        self.alterado.emit()


class _ProdutosPainel(QFrame):
    """Bloco da direita: os produtos da seleção, agrupados por subcategoria.

    O cabeçalho diz onde se está em duas linhas: `ACOMPANHAMENTOS · COZINHA`
    (a categoria e a impressora dela, que é para onde os itens vão sair) e o
    título — `Todas as subcategorias` ou o nome da subdivisão escolhida.

    A tabela agrupa quando a categoria tem subdivisões E a seleção é "Todas":
    cada grupo ganha uma linha de cabeçalho (`GUARNIÇÕES · 3 ITENS`) e os
    produtos vêm embaixo. Numa subdivisão específica o agrupamento é
    suprimido — haveria um cabeçalho só, dizendo o que o título da tela já diz.
    """

    alterado = Signal()
    produto_selecionado = Signal(object)  # Produto | None

    def __init__(
        self,
        service: CardapioService,
        mostrar_erro: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._service = service
        self._mostrar_erro = mostrar_erro
        self._selecao = SelecaoCardapio(categoria=None)
        self._grupos: list[_Grupo] = []
        # Um item por LINHA da tabela: `None` nas linhas de cabeçalho de grupo.
        # É o que permite `produto_atual()` responder certo com a tabela
        # agrupada — o índice da linha deixou de ser o índice do produto.
        self._linhas: list[Produto | None] = []
        self._pills: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        cabecalho = QHBoxLayout()
        coluna_titulo = QVBoxLayout()
        coluna_titulo.setSpacing(2)
        self._eyebrow = QLabel("CARDÁPIO")
        self._eyebrow.setObjectName("cardapioEyebrow")
        coluna_titulo.addWidget(self._eyebrow)
        self._titulo = QLabel("Selecione uma categoria")
        self._titulo.setObjectName("cardapioTituloPainel")
        coluna_titulo.addWidget(self._titulo)
        cabecalho.addLayout(coluna_titulo)
        cabecalho.addStretch()

        self._campo_busca = QLineEdit()
        self._campo_busca.setPlaceholderText("🔎  Buscar produto")
        self._campo_busca.setFixedWidth(220)
        self._campo_busca.textChanged.connect(self._filtrar)
        cabecalho.addWidget(self._campo_busca)
        layout.addLayout(cabecalho)

        self._faixa = QWidget()
        self._fluxo = FlowLayout(self._faixa, spacing=6)
        self._faixa.setVisible(False)
        layout.addWidget(self._faixa)

        self.tabela = QTableWidget(0, len(_COLUNAS_PRODUTOS))
        self.tabela.setHorizontalHeaderLabels(_COLUNAS_PRODUTOS)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabela.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabela.setShowGrid(False)
        cabecalho_tabela = self.tabela.horizontalHeader()
        cabecalho_tabela.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for coluna in range(1, len(_COLUNAS_PRODUTOS)):
            cabecalho_tabela.setSectionResizeMode(coluna, QHeaderView.ResizeMode.Fixed)
        self.tabela.setColumnWidth(1, 100)
        self.tabela.setColumnWidth(2, 100)
        self.tabela.setColumnWidth(3, 140)
        self.tabela.setColumnWidth(4, 110)
        self.tabela.verticalHeader().setDefaultSectionSize(38)
        self.tabela.currentCellChanged.connect(lambda *_: self._emitir_selecao())
        layout.addWidget(self.tabela, stretch=1)

        layout.addLayout(self._criar_rodape())

    def _criar_rodape(self) -> QHBoxLayout:
        rodape = QHBoxLayout()
        self._label_dica = QLabel("SELECIONE UM PRODUTO PARA EDITAR")
        self._label_dica.setObjectName("cardapioEyebrow")
        rodape.addWidget(self._label_dica)
        rodape.addStretch()

        self._botao_editar = QPushButton("Editar")
        self._botao_editar.setProperty("variante", "neutro")
        self._botao_editar.setEnabled(False)
        self._botao_editar.clicked.connect(self.editar)
        rodape.addWidget(self._botao_editar)

        self._botao_status = QPushButton("Desativar")
        self._botao_status.setProperty("variante", "ciano")
        self._botao_status.setEnabled(False)
        self._botao_status.clicked.connect(self.alternar_status)
        rodape.addWidget(self._botao_status)

        self._botao_excluir = QPushButton("Excluir")
        self._botao_excluir.setProperty("variante", "perigo")
        self._botao_excluir.setEnabled(False)
        self._botao_excluir.clicked.connect(self.excluir)
        rodape.addWidget(self._botao_excluir)

        return rodape

    # ------------------------------------------------------------------
    # Exibição
    # ------------------------------------------------------------------

    def exibir(self, selecao: SelecaoCardapio) -> None:
        self._selecao = selecao
        self.atualizar()

    def exibir_categoria(self, categoria: Categoria | None) -> None:
        """Atalho para quem só tem a categoria em mãos (a categoria inteira)."""
        self.exibir(SelecaoCardapio(categoria=categoria))

    def atualizar(self) -> None:
        categoria = self._selecao.categoria
        if categoria is not None:
            # Categoria pode ter sido renomeada/desativada por fora; pega a
            # versão atual antes de desenhar o cabeçalho com ela.
            todas = {c.id: c for c in self._service.listar_categorias()}
            categoria = todas.get(categoria.id)
            self._selecao = SelecaoCardapio(categoria=categoria, chave=self._selecao.chave)

        produtos = (
            []
            if categoria is None
            else _por_nome(
                [p for p in self._service.listar_produtos() if p.categoria_id == categoria.id]
            )
        )
        subcategorias = (
            [] if categoria is None else self._service.listar_subcategorias(categoria.id)
        )
        self._grupos = self._montar_grupos(produtos, subcategorias)

        self._atualizar_cabecalho(categoria)
        self._montar_pills(subcategorias)
        self._preencher_tabela()
        self._filtrar(self._campo_busca.text())
        self._emitir_selecao()

    def _montar_grupos(self, produtos: list, subcategorias: list) -> list[_Grupo]:
        """Os grupos que a tabela vai desenhar, já filtrados pela seleção.

        Uma subdivisão VAZIA aparece assim mesmo quando a seleção é ela: é o
        estado normal de quem acabou de criá-la, e uma tabela vazia com o nome
        dela no título diz "está aqui, sem itens ainda" — enquanto uma tela em
        branco diria "não existe".
        """
        por_nome = _agrupar_por_subcategoria(produtos)
        if self._selecao.chave == _SUB_NENHUMA:
            return [g for g in por_nome if g.nome is None]
        if not self._selecao.e_todas:
            escolhidos = [g for g in por_nome if g.nome == self._selecao.chave]
            if escolhidos:
                return escolhidos
            if any(sub.nome == self._selecao.chave for sub in subcategorias):
                return [_Grupo(self._selecao.chave, [])]
            return []
        return por_nome

    def _atualizar_cabecalho(self, categoria: Categoria | None) -> None:
        if categoria is None:
            self._eyebrow.setText("CARDÁPIO")
            self._titulo.setText("Selecione uma categoria")
            return
        impressora = categoria.impressora.nome if categoria.impressora is not None else None
        self._eyebrow.setText(
            f"{categoria.nome.upper()} · {(impressora or 'SEM IMPRESSORA').upper()}"
        )
        if self._selecao.e_todas:
            self._titulo.setText("Todas as subcategorias")
        elif self._selecao.chave == _SUB_NENHUMA:
            self._titulo.setText(_ROTULO_SEM_SUBCATEGORIA)
        else:
            self._titulo.setText(self._selecao.chave)

    def _montar_pills(self, subcategorias: list) -> None:
        """A faixa de filtro, refeita a cada categoria.

        Destrói as antigas de verdade, e não só as esconde: numa tela que fica
        aberta o turno inteiro, um `QPushButton` órfão por troca de categoria é
        o vazamento que o RNF do Celeron proíbe.
        """
        while (item := self._fluxo.takeAt(0)) is not None:
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._pills.clear()

        if not subcategorias:
            self._faixa.setVisible(False)
            return

        contagem = {sub.nome: 0 for sub in subcategorias}
        soltos = 0
        for grupo in self._grupos_completos():
            if grupo.nome is None:
                soltos = len(grupo.produtos)
            else:
                contagem[grupo.nome] = len(grupo.produtos)

        pares = [(_SUB_TODAS, _ROTULO_TODAS.upper(), sum(contagem.values()) + soltos)]
        pares += [(sub.nome, sub.nome.upper(), contagem.get(sub.nome, 0)) for sub in subcategorias]
        if soltos:
            pares.append((_SUB_NENHUMA, _ROTULO_SEM_SUBCATEGORIA.upper(), soltos))

        for chave, rotulo, total in pares:
            pill = QPushButton(f"{rotulo} · {total}" if chave != _SUB_TODAS else rotulo)
            pill.setObjectName("pillSubcategoria")
            pill.setCursor(Qt.CursorShape.PointingHandCursor)
            pill.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            pill.setProperty("chave", chave)
            pill.setProperty("ativa", chave == self._selecao.chave)
            pill.clicked.connect(self._pill_clicada)
            self._fluxo.addWidget(pill)
            self._pills[chave] = pill
        self._faixa.setVisible(True)

    def _grupos_completos(self) -> list[_Grupo]:
        """Todos os grupos da categoria, ignorando o filtro — para as contagens.

        As pílulas mostram quantos itens cada subdivisão tem, e esse número não
        pode mudar conforme o filtro aplicado: seria a tela dizendo que a
        subcategoria encolheu quando o gerente clicou em outra.
        """
        categoria = self._selecao.categoria
        if categoria is None:
            return []
        produtos = [
            p for p in self._service.listar_produtos() if p.categoria_id == categoria.id
        ]
        return _agrupar_por_subcategoria(_por_nome(produtos))

    def _pill_clicada(self) -> None:
        botao = self.sender()
        if not isinstance(botao, QPushButton):
            return
        self._selecao = SelecaoCardapio(
            categoria=self._selecao.categoria,
            chave=str(botao.property("chave") or _SUB_TODAS),
        )
        self.atualizar()

    def _preencher_tabela(self) -> None:
        agrupar = self._selecao.e_todas and len(self._grupos) > 1
        self._linhas = []
        for grupo in self._grupos:
            if agrupar:
                self._linhas.append(None)
            self._linhas.extend(grupo.produtos)

        # `clearSpans` antes de repopular: um span deixado de um refresh
        # anterior mesclaria uma linha de produto e esconderia preço e status.
        self.tabela.clearSpans()
        limpar_tabela(self.tabela, linhas=len(self._linhas), preservar_selecao=True)

        for linha, produto in enumerate(self._linhas):
            if produto is None:
                self._desenhar_cabecalho_de_grupo(linha)
                continue
            definir_celula(self.tabela, linha, 0, _criar_celula_produto(produto))
            self.tabela.setItem(linha, 1, QTableWidgetItem(formatar_reais(produto.preco)))
            self.tabela.setItem(linha, 2, QTableWidgetItem(formatar_reais(produto.custo)))
            definir_celula(
                self.tabela, linha, 3, _criar_celula_margem(_margem_percentual(produto))
            )
            definir_celula(self.tabela, linha, 4, _criar_badge_status(produto.ativo))

    def _desenhar_cabecalho_de_grupo(self, linha: int) -> None:
        grupo = self._grupo_da_linha(linha)
        if grupo is None:
            return
        self.tabela.setSpan(linha, 0, 1, len(_COLUNAS_PRODUTOS))
        definir_celula(
            self.tabela, linha, 0, _criar_cabecalho_de_grupo(grupo.rotulo, len(grupo.produtos))
        )
        self.tabela.setRowHeight(linha, _ALTURA_CABECALHO_GRUPO_PX)
        # Linha de cabeçalho não é selecionável: clicar nela não pode habilitar
        # Editar/Excluir apontando para produto nenhum.
        for coluna in range(len(_COLUNAS_PRODUTOS)):
            if self.tabela.item(linha, coluna) is None:
                self.tabela.setItem(linha, coluna, QTableWidgetItem())
            self.tabela.item(linha, coluna).setFlags(Qt.ItemFlag.ItemIsEnabled)

    def _grupo_da_linha(self, linha: int) -> _Grupo | None:
        """Qual grupo começa nesta linha de cabeçalho."""
        vistos = 0
        for grupo in self._grupos:
            if vistos == linha:
                return grupo
            vistos += 1 + len(grupo.produtos)
        return None

    # ------------------------------------------------------------------
    # Filtro e seleção
    # ------------------------------------------------------------------

    def _filtrar(self, texto: str) -> None:
        """Esconde as linhas que não casam — e o cabeçalho que ficou sem itens.

        A busca casa contra nome **e** subcategoria, a mesma regra do modal de
        lançamento: telas que buscam diferente sobre o mesmo cardápio é como o
        gerente conclui que o produto sumiu.
        """
        alvo = chave_de_agrupamento(texto) if texto.strip() else ""
        visiveis_por_grupo: dict[int, int] = {}
        linha_do_grupo: dict[int, int] = {}
        grupo_atual = -1

        for linha, produto in enumerate(self._linhas):
            if produto is None:
                grupo_atual = linha
                linha_do_grupo[grupo_atual] = linha
                visiveis_por_grupo[grupo_atual] = 0
                continue
            sub = produto.subcategoria.nome if produto.subcategoria is not None else ""
            casou = not alvo or alvo in chave_de_agrupamento(f"{produto.nome} {sub}")
            self.tabela.setRowHidden(linha, not casou)
            if casou and grupo_atual >= 0:
                visiveis_por_grupo[grupo_atual] += 1

        for chave, linha in linha_do_grupo.items():
            self.tabela.setRowHidden(linha, visiveis_por_grupo.get(chave, 0) == 0)

    def produto_atual(self) -> Produto | None:
        linha = self.tabela.currentRow()
        if linha < 0 or linha >= len(self._linhas):
            return None
        return self._linhas[linha]

    def _emitir_selecao(self) -> None:
        produto = self.produto_atual()
        self._atualizar_rodape(produto)
        self.produto_selecionado.emit(produto)

    def _atualizar_rodape(self, produto: Produto | None) -> None:
        self._label_dica.setText(
            "SELECIONE UM PRODUTO PARA EDITAR" if produto is None else produto.nome.upper()
        )
        self._botao_editar.setEnabled(produto is not None)
        self._botao_status.setEnabled(produto is not None)
        self._botao_status.setText("Ativar" if produto is not None and not produto.ativo else "Desativar")
        self._botao_excluir.setEnabled(produto is not None)

    def _categorias_ativas(self) -> list[Categoria]:
        return _por_nome(self._service.listar_categorias_ativas())

    def _subcategorias_por_categoria(self, categorias: list[Categoria]) -> dict[int, list]:
        """Instantâneo das subdivisões por categoria, para o seletor do modal.

        Montado na ABERTURA do modal e não a cada troca do seletor: o cadastro
        tem 15 categorias no cardápio real, e ir ao banco a cada clique no
        `QComboBox` colocaria consulta no caminho de um gesto que o gerente
        repete enquanto procura a categoria certa.
        """
        return {
            categoria.id: self._service.listar_subcategorias(categoria.id)
            for categoria in categorias
        }

    # ------------------------------------------------------------------
    # Ações de produto
    # ------------------------------------------------------------------

    def criar(self) -> None:
        categorias = self._categorias_ativas()
        if not categorias:
            self._mostrar_erro("Cadastre uma categoria ativa antes de criar um produto.")
            return
        categoria = self._selecao.categoria
        modal = _ProdutoDialog(
            "Novo produto",
            categorias,
            self,
            categoria_id_inicial=categoria.id if categoria else None,
            subcategoria_id_inicial=self._subcategoria_id_da_selecao(),
            subcategorias_por_categoria=self._subcategorias_por_categoria(categorias),
        )
        self._mostrar_erro("")
        try:
            while modal.exec() == QDialog.DialogCode.Accepted:
                dados = modal.resultado()
                if self._produto_duplicado(dados.nome) and not self._confirmar_duplicidade(dados.nome):
                    continue
                try:
                    self._service.criar_produto(
                        dados.nome,
                        dados.preco,
                        dados.categoria_id,
                        dados.custo,
                        dados.descricao,
                        imagem_path=dados.imagem_path,
                        subcategoria_id=dados.subcategoria,
                    )
                except _ERROS_SERVICE as erro:
                    modal.mostrar_erro_servico(str(erro))
                    continue
                modal.confirmar_remocao_de_imagem_trocada()
                self.atualizar()
                self.alterado.emit()
                return
        finally:
            descartar_modal(modal)

    def _subcategoria_id_da_selecao(self) -> int | None:
        """Cadastrar dentro de uma subdivisão já a traz preenchida.

        É o ganho de estar navegando pela árvore: quem abriu "Lanches → Podrão"
        e clicou em "Novo item" quer um podrão, e não teria por que escolher de
        novo o que já escolheu na coluna da esquerda.
        """
        categoria = self._selecao.categoria
        if categoria is None or self._selecao.e_todas or self._selecao.chave == _SUB_NENHUMA:
            return None
        for subcategoria in self._service.listar_subcategorias(categoria.id):
            if subcategoria.nome == self._selecao.chave:
                return subcategoria.id
        return None

    def editar(self) -> None:
        produto = self.produto_atual()
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
            imagem_path_inicial=produto.imagem_path,
            nome_produto_inicial=produto.nome,
            subcategoria_id_inicial=produto.subcategoria_id,
            subcategorias_por_categoria=self._subcategorias_por_categoria(categorias),
        )
        self._mostrar_erro("")
        try:
            while modal.exec() == QDialog.DialogCode.Accepted:
                dados = modal.resultado()
                if self._produto_duplicado(
                    dados.nome, ignorar_id=produto.id
                ) and not self._confirmar_duplicidade(dados.nome):
                    continue
                try:
                    self._service.atualizar_produto(
                        produto.id,
                        dados.nome,
                        dados.preco,
                        dados.custo,
                        dados.categoria_id,
                        dados.descricao,
                        imagem_path=dados.imagem_path,
                        subcategoria_id=dados.subcategoria,
                    )
                except _ERROS_SERVICE as erro:
                    modal.mostrar_erro_servico(str(erro))
                    continue
                modal.confirmar_remocao_de_imagem_trocada()
                self.atualizar()
                self.alterado.emit()
                return
        finally:
            descartar_modal(modal)

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
        instância, campos preservados) ou segue.
        """
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Produto já existe")
        caixa.setIcon(QMessageBox.Icon.Warning)
        caixa.setText(
            f"Já existe um produto chamado '{nome}'.\n\n"
            "Deseja cadastrar assim mesmo?"
        )
        botao_voltar = caixa.addButton("Voltar e Editar", QMessageBox.ButtonRole.RejectRole)
        botao_criar = caixa.addButton("Criar Mesmo Assim", QMessageBox.ButtonRole.AcceptRole)
        caixa.setDefaultButton(botao_voltar)
        caixa.setEscapeButton(botao_voltar)
        executar_modal(caixa)
        return caixa.clickedButton() is botao_criar

    def gerenciar_combo(self) -> None:
        produto = self.produto_atual()
        if produto is None:
            self._mostrar_erro("Selecione um produto antes de gerenciar o combo.")
            return
        candidatos = [p for p in self._service.listar_produtos_ativos() if p.id != produto.id]
        modal = _ComboComponentesDialog(self._service, produto, candidatos, self)
        executar_modal(modal)
        self._mostrar_erro("")
        self.atualizar()
        self.alterado.emit()

    def alternar_status(self) -> None:
        produto = self.produto_atual()
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

    def excluir(self) -> None:
        produto = self.produto_atual()
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
        self._label_erro.setObjectName("labelErro")
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
        limpar_tabela(self._tabela, linhas=len(self._componentes), preservar_selecao=True)
        for linha, item in enumerate(self._componentes):
            self._tabela.setItem(linha, 0, QTableWidgetItem(item.produto.nome))
            self._tabela.setItem(linha, 1, QTableWidgetItem(str(item.quantidade)))

    def _adicionar_componente(self) -> None:
        candidatos = [p for p in self._candidatos if p.id != self._combo.id]
        if not candidatos:
            self._label_erro.setText("Não há outro produto disponível para virar componente.")
            return
        modal = _ComponenteDialog(candidatos, self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
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


class _ProdutoDialog(QDialog):
    """Modal de criação/edição de produto: nome, preço, custo, categoria,
    subcategoria e descrição.

    Não tem campo "é combo": isso o service decide sozinho, a partir de o
    produto ter ou não componentes (ver `_ComboComponentesDialog`).

    **Categoria é obrigatória; subcategoria é opcional**, e as duas são
    seletores fechados. A categoria decide em qual impressora o item sai
    (`produto.categoria.impressora`, §3.12); a subcategoria não decide nada, só
    agrupa o catálogo — mas desde o §9.9 ela é uma **entidade**, com cadastro
    próprio, e por isso aqui se ESCOLHE uma que existe em vez de digitar um nome.
    Deixar digitar criaria subdivisão pela porta dos fundos, sem passar pela tela
    que existe para isso, e é assim que nascem duas com o mesmo nome.
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
        imagem_path_inicial: str | None = None,
        nome_produto_inicial: str = "",
        subcategoria_id_inicial: int | None = None,
        subcategorias_por_categoria: dict[int, list] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)

        # Instantâneo das subdivisões por categoria, montado por quem abre o
        # modal. O diálogo não conhece o `CardapioService` — é a mesma linha
        # que `categorias` já seguia — e assim trocar de categoria no seletor
        # troca as sugestões sem ir ao banco de novo a cada clique.
        self._subcategorias_por_categoria = subcategorias_por_categoria or {}

        # Estado interno da foto: só é gravado no banco quando o modal fecha
        # com OK. `_imagem_path_processada` é o nome do arquivo JÁ comprimido
        # (ver imagem_service) — nunca o caminho do arquivo original escolhido
        # no QFileDialog. `_imagem_path_para_remover` guarda uma foto antiga
        # que ficou órfã (trocada ou removida) pra ser apagada do disco só
        # depois que o service confirmar a gravação, evitando apagar um
        # arquivo em uso caso o usuário cancele o diálogo.
        self._imagem_path_processada: str | None = imagem_path_inicial
        self._imagem_path_para_remover: str | None = None
        self._nome_produto_atual = nome_produto_inicial or titulo

        layout = QVBoxLayout(self)

        linha_imagem = QHBoxLayout()
        self._preview_imagem = QLabel()
        self._preview_imagem.setFixedSize(80, 80)
        self._preview_imagem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        linha_imagem.addWidget(self._preview_imagem)

        botoes_imagem = QVBoxLayout()
        self._botao_escolher_imagem = QPushButton("Escolher imagem")
        self._botao_escolher_imagem.clicked.connect(self._escolher_imagem)
        botoes_imagem.addWidget(self._botao_escolher_imagem)
        self._botao_remover_imagem = QPushButton("Remover imagem")
        self._botao_remover_imagem.clicked.connect(self._remover_imagem)
        botoes_imagem.addWidget(self._botao_remover_imagem)
        linha_imagem.addLayout(botoes_imagem)
        linha_imagem.addStretch()
        layout.addLayout(linha_imagem)

        self._atualizar_preview_imagem()

        formulario = QFormLayout()

        self._campo_nome = QLineEdit(nome_inicial)
        formulario.addRow("Nome", self._campo_nome)
        self._erro_nome = _criar_rotulo_erro()
        formulario.addRow("", self._erro_nome)

        self._campo_preco = QLineEdit(formatar_para_campo(preco_inicial))
        formulario.addRow("Preço", self._campo_preco)
        self._erro_preco = _criar_rotulo_erro()
        formulario.addRow("", self._erro_preco)

        self._campo_custo = QLineEdit(formatar_para_campo(custo_inicial))
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

        # A subcategoria é um SELETOR fechado, e não mais um campo de texto: ela
        # deixou de ser uma etiqueta digitada para virar uma entidade com
        # cadastro próprio (§9.9). Digitar aqui criaria uma subdivisão pela
        # porta dos fundos, sem passar pela tela que existe para isso — e é
        # exatamente assim que nascem duas subdivisões com o mesmo nome.
        self._seletor_subcategoria = QComboBox()
        self._seletor_subcategoria.setObjectName("seletorSubcategoria")
        formulario.addRow("Subcategoria", self._seletor_subcategoria)
        # Sem `lambda` (§3.14): trocar a categoria troca a lista de subdivisões,
        # e o que mudou sai do próprio seletor.
        self._seletor_categoria.currentIndexChanged.connect(self._ao_trocar_categoria)
        self._montar_subcategorias(subcategoria_id_inicial)

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

        preco = safe_decimal(self._campo_preco.text(), padrao=None)
        if preco is None or preco <= 0:
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

    def _escolher_imagem(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher imagem do produto",
            "",
            "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not caminho:
            return
        try:
            novo_nome = processar_imagem_produto(caminho)
        except ValueError as erro:
            QMessageBox.warning(self, "Imagem inválida", str(erro))
            return

        # A foto antiga (se houver) fica marcada pra remoção do disco só
        # quando o modal for aceito — se o usuário cancelar o diálogo depois
        # de trocar a foto, a antiga continua valendo e nada é apagado aqui.
        if self._imagem_path_processada:
            self._imagem_path_para_remover = self._imagem_path_processada
        self._imagem_path_processada = novo_nome
        self._atualizar_preview_imagem()

    def _remover_imagem(self) -> None:
        if self._imagem_path_processada:
            self._imagem_path_para_remover = self._imagem_path_processada
        self._imagem_path_processada = None
        self._atualizar_preview_imagem()

    def _atualizar_preview_imagem(self) -> None:
        nome_para_letra = self._campo_nome.text().strip() if hasattr(self, "_campo_nome") else ""
        pixmap = obter_pixmap(
            self._imagem_path_processada, 80, nome_para_letra or self._nome_produto_atual
        )
        self._preview_imagem.setPixmap(pixmap)

    # ------------------------------------------------------------------
    # Subcategoria (§9.9)
    # ------------------------------------------------------------------

    def _ao_trocar_categoria(self, _indice: int) -> None:
        """Trocar a categoria troca a lista de subdivisões oferecidas.

        A escolha anterior é **perdida** de propósito, e a diferença para os
        outros campos do formulário é a que importa: nome e preço continuam
        valendo em qualquer categoria, mas uma subdivisão pertence a UMA
        categoria — manter "Podrão (de Lanches)" selecionado depois de mudar
        para "Porções" ofereceria gravar um vínculo que o service recusa. O
        seletor volta a "Sem subcategoria", que é sempre válido.
        """
        self._montar_subcategorias(None)

    def _montar_subcategorias(self, selecionada_id: int | None) -> None:
        """(Re)popula o seletor com as subdivisões da categoria atual.

        A primeira opção é sempre "Sem subcategoria" (`None`), e não um item em
        branco: produto sem subdivisão é estado normal e legítimo, e vale a pena
        que ele tenha nome na tela em vez de ser a ausência de escolha.

        `blockSignals` no meio porque `clear()` dispara `currentIndexChanged`,
        que chamaria `_ao_trocar_categoria` de volta — a recursão que apagaria a
        seleção que este método acabou de receber.
        """
        bloqueado = self._seletor_subcategoria.blockSignals(True)
        try:
            self._seletor_subcategoria.clear()
            self._seletor_subcategoria.addItem(_ROTULO_SEM_SUBCATEGORIA, None)
            for subcategoria in self._subcategorias_por_categoria.get(
                self._seletor_categoria.currentData(), []
            ):
                self._seletor_subcategoria.addItem(subcategoria.nome, subcategoria.id)
            if selecionada_id is not None:
                indice = self._seletor_subcategoria.findData(selecionada_id)
                if indice >= 0:
                    self._seletor_subcategoria.setCurrentIndex(indice)
        finally:
            self._seletor_subcategoria.blockSignals(bloqueado)

    def resultado(self) -> DadosProduto:
        # Só é chamado depois de `_validar()` aprovar o preço, então o `or ZERO`
        # é cinto de segurança e não regra: se alguém inverter a ordem um dia, o
        # produto nasce com preço zero e visível na tela, em vez de o clique
        # morrer sem explicação.
        nome = self._campo_nome.text().strip()
        preco = safe_decimal(self._campo_preco.text(), padrao=None) or ZERO
        # Custo em branco é legítimo (produto sem custo cadastrado ainda), e é
        # por isso que este usa o padrão zero em vez de `None`.
        custo = safe_decimal(self._campo_custo.text()) or ZERO
        return DadosProduto(
            nome=nome,
            preco=preco,
            custo=custo,
            categoria_id=self._seletor_categoria.currentData(),
            descricao=self._campo_descricao.text().strip() or None,
            imagem_path=self._imagem_path_processada,
            # O id da subdivisão escolhida, ou `None` em "Sem subcategoria".
            # Quem confere se ela pertence à categoria selecionada é o service —
            # a tela tem só o instantâneo da abertura do modal, e o gerente pode
            # ter trocado a categoria depois de escolher a subdivisão.
            subcategoria=self._seletor_subcategoria.currentData(),
        )

    def confirmar_remocao_de_imagem_trocada(self) -> None:
        """Apaga do disco a foto antiga que foi trocada/removida neste modal.

        Só deve ser chamado DEPOIS que o service confirmou a gravação do
        produto com o novo `imagem_path` — nunca antes, senão um cancelamento
        do usuário perderia a foto antiga sem motivo.
        """
        if self._imagem_path_para_remover:
            remover_thumbnail(self._imagem_path_para_remover)
            self._imagem_path_para_remover = None


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


def _criar_linha_categoria(
    categoria: Categoria,
    quantidade_subcategorias: int,
    quantidade_produtos: int,
    *,
    expandida: bool = False,
) -> QWidget:
    """Linha da árvore: nome + subtítulo "N SUBS · M ITENS" + badge de status.

    O subtítulo conta as duas coisas porque as duas são a pergunta de quem abre
    a tela: quantas subdivisões esta categoria já tem, e quantos itens no total.
    A impressora saiu daqui — ela aparece no cabeçalho da direita, onde há
    largura para o nome inteiro dela, em vez de disputar 200px com o nome da
    categoria e com o badge.
    """
    linha = QWidget()
    linha.setObjectName("linhaCategoria")
    layout_externo = QHBoxLayout(linha)
    layout_externo.setContentsMargins(6, 6, 8, 6)
    layout_externo.setSpacing(8)

    seta = QLabel("⌄" if expandida else "›")
    seta.setObjectName("categoriaSeta")
    seta.setFixedWidth(12)
    seta.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout_externo.addWidget(seta, 0, Qt.AlignmentFlag.AlignVCenter)

    coluna_texto = QVBoxLayout()
    coluna_texto.setSpacing(2)
    nome = QLabel(categoria.nome)
    nome.setObjectName("categoriaNome")
    coluna_texto.addWidget(nome)

    plural_subs = "SUB" if quantidade_subcategorias == 1 else "SUBS"
    plural_itens = "ITEM" if quantidade_produtos == 1 else "ITENS"
    subtitulo = QLabel(
        f"{quantidade_subcategorias} {plural_subs} · {quantidade_produtos} {plural_itens}"
    )
    subtitulo.setObjectName("categoriaSubtitulo")
    coluna_texto.addWidget(subtitulo)

    layout_externo.addLayout(coluna_texto, stretch=1)
    layout_externo.addWidget(
        _criar_badge_categoria(categoria, quantidade_produtos), 0, Qt.AlignmentFlag.AlignVCenter
    )
    return linha


def _criar_badge_categoria(categoria: Categoria, quantidade_produtos: int) -> QWidget:
    """VAZIO (cinza) quando não há produtos; senão ATIVO/DESATIVADO como de costume."""
    if quantidade_produtos == 0:
        label = QLabel("VAZIO")
        label.setObjectName("badgeVazio")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label
    return _criar_badge_status(categoria.ativo, centralizado=False)


_ALTURA_CABECALHO_GRUPO_PX = 30


def _criar_cabecalho_de_grupo(rotulo: str, quantidade: int) -> QWidget:
    """A linha que abre um grupo na tabela: `⌂ GUARNIÇÕES · 3 ITENS`.

    É a peça que substituiu o selo que o §9.8 punha na linha de cada produto.
    O selo repetia a mesma informação uma vez por item e disputava largura com
    o nome; o cabeçalho a diz uma vez, e diz também **quantos** — que é a
    pergunta seguinte de quem está organizando.
    """
    faixa = QWidget()
    faixa.setObjectName("grupoSubcategoria")
    layout = QHBoxLayout(faixa)
    layout.setContentsMargins(12, 0, 12, 0)
    layout.setSpacing(8)

    layout.addWidget(_IconeDeGrupo(), 0, Qt.AlignmentFlag.AlignVCenter)

    nome = QLabel(rotulo.upper())
    nome.setObjectName("grupoNome")
    layout.addWidget(nome)

    plural = "ITEM" if quantidade == 1 else "ITENS"
    total = QLabel(f"· {quantidade} {plural}")
    total.setObjectName("grupoContagem")
    layout.addWidget(total)
    layout.addStretch()
    return faixa


class _IconeDeGrupo(QWidget):
    """O mesmo glifo de ramo do modal de subcategoria, em 14px.

    Desenhado à mão pelo mesmo motivo de sempre (§9.4): o símbolo equivalente
    mora no bloco de emoji, sairia colorido e chapado e ignoraria o tema — e a
    cor daqui é relida a cada repintura, então ele acompanha o alternador
    Claro/Escuro de graça (§3.15).
    """

    LADO_PX = 14

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("grupoGlifo")
        self.setFixedSize(self.LADO_PX, self.LADO_PX)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        cor = QColor(ThemeController.instancia().tokens_atuais["subcategoria_glifo"])
        caneta = QPen(cor, 1.3)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)

        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawLine(QPointF(3.0, 2.0), QPointF(3.0, 11.0))
        pintor.drawLine(QPointF(3.0, 5.0), QPointF(7.5, 5.0))
        pintor.drawLine(QPointF(3.0, 11.0), QPointF(7.5, 11.0))
        pintor.setBrush(cor)
        pintor.drawRoundedRect(QRectF(7.8, 3.4, 4.2, 3.2), 1.0, 1.0)
        pintor.drawRoundedRect(QRectF(7.8, 9.4, 4.2, 3.2), 1.0, 1.0)
        pintor.end()


def _celula_centralizada(widget: QWidget) -> QWidget:
    """Envolve um badge para uso em `setCellWidget`.

    `setCellWidget` estica o widget pra ocupar a célula inteira; sem isso o
    QLabel do badge herdaria o fundo escuro padrão de QWidget (base.qss) e
    pintaria a célula toda, virando uma barra sólida em vez de um selo
    compacto centralizado.
    """
    celula = QWidget()
    celula.setObjectName("celulaTransparente")
    layout = QHBoxLayout(celula)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(widget)
    return celula


def _criar_badge_status(ativo: bool, *, centralizado: bool = True) -> QWidget:
    """Etiqueta de status: verde para ATIVO, cinza para DESATIVADO.

    `centralizado=False` devolve o `QLabel` cru, para quem já o põe num layout
    próprio (a linha da árvore de categorias). O embrulho existe só para
    `setCellWidget`, que estica o ocupante até a célula inteira.
    """
    label = QLabel("ATIVO" if ativo else "DESATIVADO")
    label.setObjectName("badgeAtivo" if ativo else "badgeDesativado")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return _celula_centralizada(label) if centralizado else label


_TAMANHO_MINIATURA_PRODUTO = 28


def _criar_celula_produto(produto: Produto) -> QWidget:
    """Miniatura + nome do produto + badge COMBO, coluna "Produto".

    Sem a miniatura, a única foto visível no fluxo inteiro era o preview dentro
    do dialog de edição — impossível saber de relance quais itens já têm foto e
    quais ainda dependem do placeholder (ver pedido do Vitor).

    O selo da subcategoria que morava aqui (§9.8) **saiu**: ele repetia, uma vez
    por linha, o que o cabeçalho do grupo agora diz uma vez só — e disputava
    largura justamente com o nome do produto, a ponto de cortá-lo. No lugar dele
    entrou o COMBO, que veio da coluna "Tipo": é uma marca de 4 dos 113 produtos
    do cardápio real, e uma coluna inteira reservada para ela custava 90px de
    largura que faziam falta ao nome.
    """
    celula = QWidget()
    celula.setObjectName("celulaTransparente")
    layout = QHBoxLayout(celula)
    layout.setContentsMargins(10, 0, 6, 0)
    layout.setSpacing(8)

    miniatura = QLabel()
    miniatura.setFixedSize(_TAMANHO_MINIATURA_PRODUTO, _TAMANHO_MINIATURA_PRODUTO)
    miniatura.setPixmap(obter_pixmap(produto.imagem_path, _TAMANHO_MINIATURA_PRODUTO, produto.nome))
    layout.addWidget(miniatura)

    rotulo = QLabel(produto.nome)
    rotulo.setObjectName("produtoNome")
    layout.addWidget(rotulo, stretch=1)

    if produto.is_combo:
        badge = QLabel("COMBO")
        badge.setObjectName("badgeCombo")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
    return celula


def _criar_celula_margem(percentual: float) -> QWidget:
    """Barra verde proporcional + percentual numérico, lado a lado."""
    celula = QWidget()
    celula.setObjectName("celulaTransparente")
    layout = QHBoxLayout(celula)
    layout.setContentsMargins(10, 0, 10, 0)
    layout.setSpacing(8)

    barra = _BarraMargem()
    barra.setMinimumWidth(48)
    barra.definir_percentual(percentual)
    layout.addWidget(barra, stretch=1)

    rotulo = QLabel(f"{percentual:.0f}%")
    rotulo.setObjectName("margemPercentual")
    layout.addWidget(rotulo)
    return celula


def _criar_rotulo_erro() -> QLabel:
    rotulo = QLabel()
    rotulo.setObjectName("campoErroRotulo")
    rotulo.setWordWrap(True)
    rotulo.setVisible(False)
    return rotulo


def _marcar_erro(campo: QLineEdit, rotulo: QLabel, mensagem: str) -> None:
    aplicar_propriedade(campo, "erro", True)
    rotulo.setText(mensagem)
    rotulo.setVisible(True)


def _limpar_erro(campo: QLineEdit, rotulo: QLabel) -> None:
    aplicar_propriedade(campo, "erro", False)
    rotulo.setVisible(False)
