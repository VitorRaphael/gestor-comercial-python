"""Cardápio: árvore Categoria → Subcategoria (esquerda) e os produtos da
seleção em blocos por subcategoria (direita), tudo em ordem alfabética.

## Cartões pintados, e não tabela (§9.11)

O §9.9 acertou a hierarquia — a subcategoria **contém** os produtos — mas a
direita continuava sendo uma tabela linear, com linhas de cabeçalho no meio.
O mockup do Vitor desenha o que a hierarquia sugere: cada subcategoria é um
**bloco** (cabeçalho com o nome, a contagem e "Editar subcategoria") e os
produtos são linhas dentro dele — miniatura, nome, preço, custo e a barra de
margem.

As duas colunas deixaram de ser feitas de widgets e passaram a ser **pintadas**
por delegado (`widgets/cardapio_cartoes.py`, onde está a medição do porquê).
Esta view ficou com o que é dela: ler o service, montar os instantâneos,
reagir a clique — e **manter o gerente onde ele estava**. A categoria aberta, a
subdivisão escolhida, o produto selecionado e a rolagem das duas listas
sobrevivem a qualquer recarga: salvar um produto não pode fechar o acordeão nem
jogar a lista para o topo.

Por consequência, a subdivisão escolhida na árvore é dita pelo **cabeçalho do
bloco**, e não mais por um título "Podrão" no topo do painel: o topo passou a
ser a categoria (`Acompanhamentos`, `COZINHA · 5 ITENS · 2 SUBCATEGORIAS`). As
pílulas de filtro que o §9.9 punha entre a busca e a tabela saíram — repetiam a
árvore, com uma divergência sutil (filtravam sem mover a seleção dela).

## O que não mudou

Combo não é aba separada — é um Produto com `is_combo=True`, ligado pelo
service assim que ganha o primeiro componente (ver
`CardapioService.associar_componente`); na linha ele é um selo ao lado do nome.
Editar/Ativar-Desativar/Excluir de produto moram no rodapé do painel; os mesmos
três em categoria saem por menu de contexto (botão direito na árvore). Os
atalhos de teclado (Ctrl+N/F2/Delete) despacham pelo `_contexto` (qual lado
está com foco). Associação de impressora mora na tela "Impressoras": aqui ela
só é **mostrada**, no topo do painel, porque é para onde os itens daquela
categoria vão sair — e é a informação que a subcategoria NÃO muda (§9.8).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
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
from gestor_comercial.services.cardapio_service import (
    CardapioService,
    ResumoCardapio,
    margem_percentual,
)
from gestor_comercial.services.dinheiro import ZERO
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.imagem_service import processar_imagem_produto, remover_thumbnail
from gestor_comercial.services.texto import chave_de_agrupamento
from gestor_comercial.ui.formatacao import (
    formatar_para_campo,
    formatar_reais,
    safe_decimal,
)
from gestor_comercial.ui.widgets.busca_produto import BuscaProdutoWidget
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_CAIXA,
    GLIFO_CAMADAS,
    GLIFO_CIFRAO,
    GLIFO_ETIQUETA,
    GLIFO_PASTA,
    PAPEL_LINHA,
    DelegadoArvore,
    FotoGrupo,
    FotoProduto,
    InsigniaCardapio,
    ItemDaLista,
    LinhaDeCategoria,
    LinhaDeSubdivisao,
    ListaDeProdutos,
    RotuloComReticencias,
    campo_de_busca,
    divisor,
    montar_itens,
)
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.modais import descartar_modal, executar_modal
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado
from gestor_comercial.ui.widgets.subcategoria_dialog import SubcategoriaDialog
from gestor_comercial.ui.widgets.tabelas import limpar_tabela
from gestor_comercial.ui.widgets.thumbnail_cache import obter_pixmap

_COLUNAS_COMPONENTES = ["Componente", "Quantidade"]

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

# O que cada item da árvore carrega além do instantâneo que o delegado pinta
# (`PAPEL_LINHA`): a identidade, que viaja junto em qualquer item.
_PAPEL_CATEGORIA = Qt.ItemDataRole.UserRole
_PAPEL_CHAVE = Qt.ItemDataRole.UserRole + 1
_PAPEL_ROTULO = Qt.ItemDataRole.UserRole + 2

# As duas seleções da árvore que não são o nome de uma subcategoria. Começam com
# `\x00` porque QUALQUER string é um nome de subcategoria válido: usar `""` para
# "todas" faria uma subcategoria chamada "" (impossível hoje, mas a garantia é
# do service e não desta tela) colidir com a seleção.
_SUB_TODAS = "\x00todas"
_SUB_NENHUMA = "\x00nenhuma"

# "Todas as subcategorias" só faz sentido onde há subcategoria; numa categoria
# sem subdivisão nenhuma a mesma entrada se chama pelo que ela mostra.
_ROTULO_TODAS = "Todas as subcategorias"
_ROTULO_TODOS_OS_PRODUTOS = "Todos os produtos"
_ROTULO_SEM_SUBCATEGORIA = "Sem subcategoria"

_DICA_SEM_SELECAO = "SELECIONE UM PRODUTO PARA EDITAR"


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

    def mesmo_lugar_que(self, outra: SelecaoCardapio) -> bool:
        """Mesma categoria (pelo id) e mesma subdivisão.

        Pelo id, e não por `==`: a `Categoria` é uma instância do SQLAlchemy, e
        a mesma categoria relida depois de um commit pode ser outro objeto.
        """
        meu_id = self.categoria.id if self.categoria is not None else None
        outro_id = outra.categoria.id if outra.categoria is not None else None
        return meu_id == outro_id and self.chave == outra.chave


def _por_nome(itens: list) -> list:
    """Ordem alfabética (A-Z) case-insensitive, como pedido na tela."""
    return sorted(itens, key=lambda item: item.nome.lower())


def _plural(total: int, singular: str, plural: str) -> str:
    return f"{total} {singular if total == 1 else plural}"


def _fotografar(produto: Produto, nome_da_subcategoria: str | None) -> FotoProduto:
    """O instantâneo que a linha da lista pinta — lido do `Produto` UMA vez.

    É aqui, na recarga, que a tela toca o SQLAlchemy; a pintura só lê o que
    ficou guardado (ver `widgets/cardapio_cartoes.py`).
    """
    selos = []
    if produto.is_combo:
        selos.append("COMBO")
    if not produto.ativo:
        selos.append("DESATIVADO")
    return FotoProduto(
        produto_id=produto.id,
        nome=produto.nome,
        preco_texto=formatar_reais(produto.preco),
        custo_texto=formatar_reais(produto.custo),
        margem=margem_percentual(produto.preco, produto.custo),
        ativo=produto.ativo,
        selos=tuple(selos),
        imagem_path=produto.imagem_path,
        # Nome + subcategoria, a mesma regra do modal de lançamento: telas que
        # buscam diferente sobre o mesmo cardápio é como o gerente conclui que o
        # produto sumiu.
        busca=chave_de_agrupamento(f"{produto.nome} {nome_da_subcategoria or ''}"),
    )


def _legenda_das_categorias(resumo: ResumoCardapio) -> str:
    """"grupos ativos" só quando é verdade — senão diz quantos estão fora."""
    if resumo.categorias == 0:
        return "nenhum grupo ainda"
    desativadas = resumo.categorias - resumo.categorias_ativas
    if not desativadas:
        return "grupos ativos"
    return (
        f"{_plural(resumo.categorias_ativas, 'ativo', 'ativos')} · "
        f"{_plural(desativadas, 'desativado', 'desativados')}"
    )


class CardapioView(QWidget):
    """Cardápio: KPIs no topo, a árvore à esquerda, os blocos de produto à direita."""

    def __init__(self, cardapio_service: CardapioService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = cardapio_service
        self._contexto = "categoria"  # "categoria" | "produto" — quem recebe os atalhos F2/Delete

        self._painel_categorias = _CategoriasPainel(self._service, self._mostrar_erro)
        self._painel_produtos = _ProdutosPainel(self._service, self._mostrar_erro)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        layout.addLayout(self._criar_cabecalho())
        layout.addLayout(self._criar_grade_kpis())

        # Escondida quando vazia: numa tela de 768px de altura, uma linha de
        # erro em branco custava ~30px que as duas listas não tinham.
        self._label_erro = QLabel("")
        self._label_erro.setObjectName("labelErro")
        self._label_erro.setWordWrap(True)
        self._label_erro.setVisible(False)
        layout.addWidget(self._label_erro)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("cardapioDivisaoPaineis")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
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
        self._painel_categorias.alterado.connect(self._ao_alterar_categoria)
        self._painel_produtos.alterado.connect(self._ao_alterar_produto)
        self._painel_produtos.produto_selecionado.connect(self._ao_mudar_selecao_produto)
        # O link "Editar subcategoria" mora no bloco da direita, mas quem sabe
        # editar subcategoria — e manter a seleção depois de renomeá-la — é a
        # árvore da esquerda.
        self._painel_produtos.editar_subcategoria_pedida.connect(
            self._painel_categorias.editar_subcategoria_por_nome
        )

        # Detecta em qual lado está o foco pra saber quem recebe F2/Delete/Ctrl+N.
        self._painel_categorias.arvore.installEventFilter(self)
        self._painel_produtos.lista.installEventFilter(self)

        QShortcut(QKeySequence("Ctrl+N"), self, self._novo_padrao)
        QShortcut(QKeySequence(Qt.Key.Key_F2), self, self._editar)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, self._excluir)

        self.atualizar()

    def _criar_cabecalho(self) -> QHBoxLayout:
        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(10)

        coluna_titulo = QVBoxLayout()
        coluna_titulo.setSpacing(2)
        titulo = QLabel("Cardápio")
        titulo.setObjectName("cardapioTitulo")
        coluna_titulo.addWidget(titulo)
        subtitulo = QLabel("Categorias, subcategorias, produtos e margens da operação")
        subtitulo.setObjectName("cardapioSubtitulo")
        coluna_titulo.addWidget(subtitulo)
        cabecalho.addLayout(coluna_titulo)
        cabecalho.addStretch()

        self._botao_combo = QPushButton("Gerenciar combo")
        self._botao_combo.setObjectName("cardapioBotaoTopo")
        self._botao_combo.setProperty("variante", "neutro")
        self._botao_combo.setEnabled(False)
        self._botao_combo.clicked.connect(self._painel_produtos.gerenciar_combo)
        cabecalho.addWidget(self._botao_combo)

        botao_novo_item = QPushButton("Novo item")
        botao_novo_item.setObjectName("cardapioBotaoTopo")
        botao_novo_item.setProperty("variante", "primario")
        botao_novo_item.clicked.connect(self._painel_produtos.criar)
        cabecalho.addWidget(botao_novo_item)

        return cabecalho

    def _criar_grade_kpis(self) -> QHBoxLayout:
        grade = QHBoxLayout()
        grade.setSpacing(12)

        # "Preço médio" VOLTOU (§9.11), agora com a margem média de legenda: é o
        # quarto card do mockup do Vitor. O §9.9 o tinha tirado — média de preço
        # num cardápio de R$ 0,50 a R$ 48,00 decide pouco sozinha —, e a margem,
        # que era o número que decide, continua na tela, logo embaixo dele.
        self._kpi_categorias = _CardKpi(GLIFO_CAMADAS, "Categorias")
        self._kpi_subcategorias = _CardKpi(GLIFO_ETIQUETA, "Subcategorias")
        self._kpi_produtos = _CardKpi(GLIFO_CAIXA, "Produtos")
        self._kpi_preco_medio = _CardKpi(GLIFO_CIFRAO, "Preço médio")
        for card in (
            self._kpi_categorias,
            self._kpi_subcategorias,
            self._kpi_produtos,
            self._kpi_preco_medio,
        ):
            grade.addWidget(card)
        return grade

    @nao_deixa_escapar(retorno=False)
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - override Qt
        if event.type() == QEvent.Type.FocusIn:
            if obj is self._painel_categorias.arvore:
                self._contexto = "categoria"
            elif obj is self._painel_produtos.lista:
                self._contexto = "produto"
        return super().eventFilter(obj, event)

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

        `atualizar()` é chamado no boot e a cada navegação até a tela. No boot
        não há seleção e a árvore abre na primeira categoria; depois, voltar
        para a primeira seria a tela largando o trabalho — a categoria aberta, a
        subdivisão, o produto e as duas rolagens voltam ao lugar
        (`test_selecao_sobrevive_ao_refresh.py`, `test_cardapio_cartoes.py`).
        """
        self._mostrar_erro("")
        self._painel_categorias.atualizar_mantendo_selecao()
        self._atualizar_kpis()

    def _atualizar_kpis(self) -> None:
        # Três consultas fixas, feitas pelo service: a tela não conta nem tira
        # média de nada (antes eram 17 consultas e a conta de margem morava aqui).
        resumo = self._service.resumo_do_cardapio()
        self._kpi_categorias.definir(str(resumo.categorias), _legenda_das_categorias(resumo))
        self._kpi_subcategorias.definir(str(resumo.subcategorias), "divisões organizadas")
        self._kpi_produtos.definir(str(resumo.produtos), "itens cadastrados")
        self._kpi_preco_medio.definir(
            formatar_reais(resumo.preco_medio), f"{resumo.margem_media:.0f}% de margem média"
        )

    def _mostrar_erro(self, mensagem: str) -> None:
        self._label_erro.setText(mensagem)
        self._label_erro.setVisible(bool(mensagem))


class _CardKpi(QFrame):
    """Card de métrica do mockup: insígnia à esquerda; rótulo, valor e legenda."""

    def __init__(self, glifo: str, titulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cardapioKpi")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)
        layout.addWidget(InsigniaCardapio(glifo, 40), 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        rotulo = QLabel(titulo.upper())
        rotulo.setObjectName("cardapioKpiRotulo")
        textos.addWidget(rotulo)
        self._label_valor = QLabel("—")
        self._label_valor.setObjectName("cardapioKpiValor")
        textos.addWidget(self._label_valor)
        self._label_legenda = RotuloComReticencias("")
        self._label_legenda.setObjectName("cardapioKpiLegenda")
        textos.addWidget(self._label_legenda)
        layout.addLayout(textos, 1)

    def definir(self, valor: str, legenda: str) -> None:
        self._label_valor.setText(valor)
        self._label_legenda.setText(legenda)


class _CategoriasPainel(PainelPontilhado):
    """Bloco da esquerda: a árvore Categoria → Subcategoria (§9.9, §9.11).

    Uma categoria expandida por vez, de propósito. O cardápio real tem quinze
    categorias; deixar todas abertas produziria uma coluna de sessenta linhas
    onde a rolagem vira o trabalho principal — e o gerente organiza uma
    categoria de cada vez, não quinze.

    Nenhuma linha tem widget: o `DelegadoArvore` pinta a categoria (seta,
    nome, "2 SUBCATEGORIAS", contador) e as filhas, e a altura de cada linha
    sai da própria fonte — o defeito do §9.9 (linha de duas alturas desenhada
    na altura de uma) não tem mais onde acontecer.
    """

    selecao_mudou = Signal(object)  # SelecaoCardapio
    alterado = Signal()

    # Piso da coluna inteira. Sem ele o `QSplitter` a espremia até "Acompanha…",
    # e nome de categoria cortado é o defeito que o §9.9 veio consertar.
    LARGURA_MINIMA_PX = 300

    def __init__(
        self,
        service: CardapioService,
        mostrar_erro: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cardapioPainel")
        self._service = service
        self._mostrar_erro = mostrar_erro
        self._categorias: list[Categoria] = []
        self._expandida_id: int | None = None
        self._selecao = SelecaoCardapio(categoria=None)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._criar_topo())
        layout.addWidget(divisor())

        self.arvore = QTreeWidget(columnCount=1)
        self.arvore.setObjectName("arvoreCardapio")
        self.arvore.setHeaderHidden(True)
        # Recuo zero e sem a seta de expandir do Qt: a área de `::branch` é
        # pintada pelo estilo com o azul de seleção do sistema (a faixa azul que
        # a tela antiga mostrava ao lado de "Todas"). O recuo, a guia e a seta
        # são todos do delegado.
        self.arvore.setIndentation(0)
        self.arvore.setRootIsDecorated(False)
        self.arvore.setUniformRowHeights(False)
        # O duplo clique do Qt alterna o ramo — e o clique simples já o abriu:
        # abrir uma categoria com duplo clique a fechava de novo.
        self.arvore.setExpandsOnDoubleClick(False)
        self.arvore.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.arvore.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.arvore.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.arvore.setMouseTracking(True)
        self.arvore.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        # Filho da árvore: `setItemDelegate` não toma posse (ver a lista da
        # direita), e o delegado lê o estado aberto/fechado pela árvore-mãe.
        self._delegado = DelegadoArvore(self.arvore)
        self.arvore.setItemDelegate(self._delegado)
        self.arvore.currentItemChanged.connect(self._ao_trocar_item)
        self.arvore.itemClicked.connect(self._ao_clicar)
        self.arvore.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.arvore.customContextMenuRequested.connect(self._menu_contexto)
        corpo = QVBoxLayout()
        corpo.setContentsMargins(10, 10, 10, 6)
        corpo.addWidget(self.arvore)
        layout.addLayout(corpo, 1)

        layout.addWidget(divisor())
        layout.addLayout(self._criar_acoes())

        self.setMinimumWidth(self.LARGURA_MINIMA_PX)

    def _criar_topo(self) -> QWidget:
        topo = QWidget()
        topo.setObjectName("cardapioPainelTopo")
        coluna = QVBoxLayout(topo)
        coluna.setContentsMargins(18, 16, 18, 14)
        coluna.setSpacing(12)

        linha = QHBoxLayout()
        linha.setSpacing(10)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel("Organização do cardápio")
        titulo.setObjectName("cardapioPainelTitulo")
        textos.addWidget(titulo)
        subtitulo = QLabel("Categoria → subcategoria")
        subtitulo.setObjectName("cardapioPainelSub")
        textos.addWidget(subtitulo)
        linha.addLayout(textos, 1)

        self._label_contador = QLabel("0")
        self._label_contador.setObjectName("cardapioContador")
        self._label_contador.setFixedSize(30, 30)
        self._label_contador.setAlignment(Qt.AlignmentFlag.AlignCenter)
        linha.addWidget(self._label_contador, 0, Qt.AlignmentFlag.AlignVCenter)
        coluna.addLayout(linha)

        self._campo_busca = campo_de_busca("Buscar categoria")
        self._campo_busca.textChanged.connect(self._filtrar)
        coluna.addWidget(self._campo_busca)
        return topo

    def _criar_acoes(self) -> QVBoxLayout:
        # Empilhados e não lado a lado: com a coluna em 300px, dois botões numa
        # linha cortavam o próprio rótulo ("ova categ", "Subcategor") — exatamente
        # o defeito de aperto que `test_telas_cabem_na_tela.py` existe para pegar.
        acoes = QVBoxLayout()
        acoes.setContentsMargins(12, 12, 12, 12)
        acoes.setSpacing(8)
        botao_nova = QPushButton("+  Nova categoria")
        botao_nova.setObjectName("cardapioBotaoEstrutura")
        botao_nova.clicked.connect(self.criar)
        acoes.addWidget(botao_nova)

        # A criação de subdivisão fica ao lado da de categoria porque as duas
        # são a mesma tarefa — montar a estrutura do cardápio —, e escondê-la só
        # no menu de contexto deixaria a funcionalidade invisível para quem não
        # clica com o botão direito.
        self._botao_nova_sub = QPushButton("+  Nova subcategoria")
        self._botao_nova_sub.setObjectName("cardapioBotaoEstrutura")
        self._botao_nova_sub.setEnabled(False)
        self._botao_nova_sub.clicked.connect(self.criar_subcategoria)
        acoes.addWidget(self._botao_nova_sub)
        return acoes

    # ------------------------------------------------------------------
    # Montagem da árvore
    # ------------------------------------------------------------------

    def atualizar(self) -> None:
        self._montar(manter_selecao=False)

    def atualizar_mantendo_selecao(self) -> None:
        self._montar(manter_selecao=True)

    def _montar(self, *, manter_selecao: bool) -> None:
        """Refaz a árvore e anuncia a seleção UMA vez, no fim.

        Os sinais da árvore ficam bloqueados pelo trecho inteiro: o `clear()`, a
        volta da seleção e o ajuste de rolagem produziriam uma rajada de
        `currentItemChanged` com estados que nunca existiram para o gerente — e
        cada um recarregaria a lista da direita. A seleção é anunciada à mão,
        uma vez, depois que tudo voltou ao lugar.
        """
        alvo = self._selecao if manter_selecao else None
        rolagem = self.arvore.verticalScrollBar().value() if manter_selecao else 0

        self._categorias = _por_nome(self._service.listar_categorias())
        self._label_contador.setText(str(len(self._categorias)))
        produtos_por_categoria = self._contar_produtos()
        contagem_sub = self._service.contagem_de_produtos_por_subcategoria()
        # Uma consulta para as subdivisões das quinze categorias — eram quinze
        # (uma por categoria), a cada recarga (§3.6, §9.11).
        subcategorias_por_categoria: dict[int, list] = {}
        for subcategoria in self._service.listar_todas_as_subcategorias():
            subcategorias_por_categoria.setdefault(subcategoria.categoria_id, []).append(subcategoria)

        ids = {categoria.id for categoria in self._categorias}
        if alvo is not None and alvo.categoria is not None and alvo.categoria.id in ids:
            self._expandida_id = alvo.categoria.id
        elif self._expandida_id not in ids:
            self._expandida_id = self._categorias[0].id if self._categorias else None

        bloqueado = self.arvore.blockSignals(True)
        try:
            self.arvore.clear()
            item_a_selecionar: QTreeWidgetItem | None = None
            reserva: QTreeWidgetItem | None = None
            for categoria in self._categorias:
                subcategorias = _por_nome(subcategorias_por_categoria.get(categoria.id, []))
                produtos = produtos_por_categoria.get(categoria.id, 0)
                item = self._criar_item_categoria(categoria, len(subcategorias), produtos)
                self.arvore.addTopLevelItem(item)

                classificados = sum(contagem_sub.get(sub.id, 0) for sub in subcategorias)
                rotulo_todas = _ROTULO_TODAS if subcategorias else _ROTULO_TODOS_OS_PRODUTOS
                filhos = [(_SUB_TODAS, rotulo_todas, produtos)]
                filhos += [
                    (sub.nome, sub.nome, contagem_sub.get(sub.id, 0)) for sub in subcategorias
                ]
                soltos = produtos - classificados
                if subcategorias and soltos > 0:
                    filhos.append((_SUB_NENHUMA, _ROTULO_SEM_SUBCATEGORIA, soltos))

                for posicao, (chave, rotulo, total) in enumerate(filhos):
                    ultima = posicao == len(filhos) - 1
                    filho = self._criar_item_filho(categoria, chave, rotulo, total, ultima=ultima)
                    item.addChild(filho)
                    if alvo is not None and alvo.categoria is not None:
                        if categoria.id == alvo.categoria.id:
                            if chave == alvo.chave:
                                item_a_selecionar = filho
                            elif chave == _SUB_TODAS:
                                # Se a subdivisão escolhida sumiu (excluída, ou o
                                # último item solto foi classificado), o gerente
                                # fica NA MESMA categoria, em "Todas" — e não é
                                # levado de volta para a primeira da lista.
                                reserva = filho

                item.setExpanded(categoria.id == self._expandida_id)

            self._filtrar(self._campo_busca.text())

            if item_a_selecionar is None:
                item_a_selecionar = reserva
            if item_a_selecionar is None:
                item_a_selecionar = self._primeiro_filho_visivel()
            if item_a_selecionar is not None:
                # O `setCurrentItem` rola a árvore até o item escolhido; a linha
                # de rolagem abaixo devolve a árvore aonde o GERENTE a deixou,
                # que pode não ser onde está a categoria aberta.
                self.arvore.setCurrentItem(item_a_selecionar)
            # Mesma linha defensiva da lista de produtos (ver o comentário em
            # `ListaDeProdutos.definir_itens`): o alcance da barra depois do
            # `clear()` é detalhe interno do Qt, e forçar o layout aqui é o
            # mesmo cálculo que ele faria antes de pintar.
            self.arvore.doItemsLayout()
            self.arvore.verticalScrollBar().setValue(rolagem)
        finally:
            self.arvore.blockSignals(bloqueado)

        if item_a_selecionar is not None:
            self._selecao = self._selecao_do_item(item_a_selecionar)
        else:
            self._selecao = SelecaoCardapio(categoria=None)
        self._botao_nova_sub.setEnabled(self._selecao.categoria is not None)
        self.selecao_mudou.emit(self._selecao)

    def _criar_item_categoria(
        self, categoria: Categoria, subcategorias: int, produtos: int
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setText(0, categoria.nome)
        item.setData(0, _PAPEL_CATEGORIA, categoria.id)
        item.setData(0, _PAPEL_CHAVE, _SUB_TODAS)
        item.setData(0, _PAPEL_ROTULO, categoria.nome)
        item.setData(
            0,
            PAPEL_LINHA,
            LinhaDeCategoria(
                nome=categoria.nome,
                subcategorias=subcategorias,
                produtos=produtos,
                ativa=categoria.ativo,
            ),
        )
        return item

    def _criar_item_filho(
        self, categoria: Categoria, chave: str, rotulo: str, total: int, *, ultima: bool
    ) -> QTreeWidgetItem:
        filho = QTreeWidgetItem()
        filho.setText(0, rotulo)
        filho.setData(0, _PAPEL_CATEGORIA, categoria.id)
        filho.setData(0, _PAPEL_CHAVE, chave)
        filho.setData(0, _PAPEL_ROTULO, rotulo)
        filho.setData(0, PAPEL_LINHA, LinhaDeSubdivisao(rotulo=rotulo, total=total, ultima=ultima))
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
        """Clicar numa categoria abre ela, fecha a anterior e escolhe "Todas".

        A troca acontece no CLIQUE e não na seleção porque a seleção também
        muda ao andar de seta pelo teclado, e ali fechar o ramo debaixo do
        cursor tiraria o próprio item selecionado da tela.

        O "Todas" vira a seleção de propósito: é ele que acende na pílula âmbar
        do mockup. A lista da direita não recarrega duas vezes por isso — a
        seleção da categoria e a do "Todas" dela são o mesmo lugar, e
        `_ao_trocar_item` não anuncia o mesmo lugar duas vezes.
        """
        if item.parent() is not None:
            return
        categoria_id = item.data(0, _PAPEL_CATEGORIA)
        if not (self._expandida_id == categoria_id and item.isExpanded()):
            self._expandida_id = categoria_id
            for indice in range(self.arvore.topLevelItemCount()):
                topo = self.arvore.topLevelItem(indice)
                topo.setExpanded(topo.data(0, _PAPEL_CATEGORIA) == categoria_id)
        if item.childCount() > 0:
            self.arvore.setCurrentItem(item.child(0))

    def _ao_trocar_item(
        self, atual: QTreeWidgetItem | None, _anterior: QTreeWidgetItem | None
    ) -> None:
        if atual is None:
            return
        # Clicar na linha da CATEGORIA equivale a escolher "Todas" dentro dela:
        # é o que o gerente espera de clicar no nome do grupo, e evita um
        # estado em que a direita não sabe o que mostrar.
        selecao = self._selecao_do_item(atual)
        self._botao_nova_sub.setEnabled(selecao.categoria is not None)
        mesmo_lugar = selecao.mesmo_lugar_que(self._selecao)
        self._selecao = selecao
        if not mesmo_lugar:
            self.selecao_mudou.emit(selecao)

    def _selecao_do_item(self, item: QTreeWidgetItem) -> SelecaoCardapio:
        categoria = self._categoria_por_id(item.data(0, _PAPEL_CATEGORIA))
        return SelecaoCardapio(categoria=categoria, chave=item.data(0, _PAPEL_CHAVE) or _SUB_TODAS)

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

        As entradas fixas ("Todas as subcategorias", "Sem subcategoria") ficam
        FORA da comparação: existem em quase toda categoria, e buscar "sub" ou
        "todas" casava com o cardápio inteiro.
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
                if item.child(pos).data(0, _PAPEL_CHAVE) not in (_SUB_TODAS, _SUB_NENHUMA)
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
            categoria = self._service.criar_categoria(modal.nome())
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        # A categoria nova já abre selecionada: quem acabou de criá-la vai
        # cadastrar as subdivisões dela em seguida, e a árvore antiga levava o
        # gerente de volta para a primeira categoria da lista.
        self._selecao = SelecaoCardapio(categoria=categoria, chave=_SUB_TODAS)
        self.atualizar_mantendo_selecao()
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
        """Renomeia a subcategoria destacada na árvore (menu de contexto)."""
        nome = self.subcategoria_selecionada()
        if nome is not None:
            self.editar_subcategoria_por_nome(nome)

    def editar_subcategoria_por_nome(self, nome: str) -> None:
        """Renomeia a subcategoria `nome` da categoria aberta.

        Existe separado de `editar_subcategoria` porque o link "Editar
        subcategoria" do bloco da direita edita a subdivisão DAQUELE bloco, que
        não é necessariamente a destacada na árvore (em "Todas" há vários).

        Renomear a subdivisão selecionada troca a chave da seleção junto. Sem
        isso a recarga procurava a subdivisão pelo nome ANTIGO, não achava, e
        levava o gerente para a primeira categoria — editar o nome fechava o
        acordeão em que ele estava trabalhando.
        """
        categoria = self.categoria_atual()
        if categoria is None or not nome:
            return
        subcategoria = self._subcategoria_por_nome(categoria.id, nome)
        if subcategoria is None:
            return
        nome_antigo = subcategoria.nome
        existentes = [s.nome for s in self._service.listar_subcategorias(categoria.id)]
        modal = SubcategoriaDialog(
            categoria.nome,
            categoria.impressora.nome if categoria.impressora is not None else None,
            existentes,
            self,
            nome_inicial=nome_antigo,
        )
        self._mostrar_erro("")
        try:
            while modal.exec() == QDialog.DialogCode.Accepted:
                try:
                    renomeada = self._service.editar_subcategoria(
                        subcategoria.id, modal.resultado().nome
                    )
                except _ERROS_SERVICE as erro:
                    modal.mostrar_erro_servico(str(erro))
                    continue
                if self._selecao.chave == nome_antigo:
                    self._selecao = SelecaoCardapio(categoria=categoria, chave=renomeada.nome)
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


class _ProdutosPainel(PainelPontilhado):
    """Bloco da direita: os produtos da seleção, em blocos por subcategoria.

    O topo diz onde se está: a categoria (`Acompanhamentos`) e, embaixo, a
    impressora dela, quantos itens e quantas subdivisões
    (`COZINHA · 5 ITENS · 2 SUBCATEGORIAS`) — a impressora porque é para onde os
    itens vão sair, e é o que a subcategoria não muda.

    A lista é um bloco por subcategoria quando a categoria tem subdivisões; numa
    categoria sem nenhuma, um bloco só, sem cabeçalho — um "SEM SUBCATEGORIA"
    em cima de todos os itens diria o óbvio.
    """

    alterado = Signal()
    produto_selecionado = Signal(object)  # Produto | None
    editar_subcategoria_pedida = Signal(str)

    LARGURA_BUSCA_PX = 240

    def __init__(
        self,
        service: CardapioService,
        mostrar_erro: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cardapioPainel")
        self._service = service
        self._mostrar_erro = mostrar_erro
        self._selecao = SelecaoCardapio(categoria=None)
        self._grupos: list[FotoGrupo] = []
        self._com_cabecalho = False
        # O `Produto` de cada linha, para as ações do rodapé. A PINTURA não o
        # usa (lê o instantâneo); editar/excluir sim, e aí tocar o banco é certo.
        self._produtos_por_id: dict[int, Produto] = {}
        # Onde a lista estava no último desenho (categoria, subdivisão).
        # Recarregar no MESMO lugar devolve seleção e rolagem; trocar de lugar
        # começa do topo, sem produto escolhido.
        self._lugar_desenhado: tuple[int | None, str] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._criar_topo())
        layout.addWidget(divisor())

        self.lista = ListaDeProdutos()
        self.lista.itemSelectionChanged.connect(self._emitir_selecao)
        self.lista.itemDoubleClicked.connect(self._ao_duplo_clique)
        self.lista.editar_subcategoria_pedida.connect(self.editar_subcategoria_pedida)
        corpo = QVBoxLayout()
        corpo.setContentsMargins(20, 18, 20, 14)
        corpo.addWidget(self.lista)
        layout.addLayout(corpo, 1)

        layout.addWidget(self._criar_rodape())

    def _criar_topo(self) -> QWidget:
        topo = QWidget()
        topo.setObjectName("cardapioPainelTopo")
        linha = QHBoxLayout(topo)
        linha.setContentsMargins(20, 16, 20, 16)
        linha.setSpacing(14)
        linha.addWidget(InsigniaCardapio(GLIFO_PASTA, 44), 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setSpacing(3)
        self._titulo = RotuloComReticencias("Selecione uma categoria")
        self._titulo.setObjectName("cardapioPainelTituloGrande")
        textos.addWidget(self._titulo)
        self._meta = RotuloComReticencias("")
        self._meta.setObjectName("cardapioPainelMeta")
        textos.addWidget(self._meta)
        linha.addLayout(textos, 1)

        self._campo_busca = campo_de_busca("Buscar produto")
        self._campo_busca.setFixedWidth(self.LARGURA_BUSCA_PX)
        self._campo_busca.textChanged.connect(self._ao_buscar)
        linha.addWidget(self._campo_busca, 0, Qt.AlignmentFlag.AlignVCenter)
        return topo

    def _criar_rodape(self) -> QWidget:
        rodape = QWidget()
        rodape.setObjectName("cardapioRodape")
        linha = QHBoxLayout(rodape)
        linha.setContentsMargins(20, 12, 20, 12)
        linha.setSpacing(10)

        self._label_dica = RotuloComReticencias(_DICA_SEM_SELECAO)
        self._label_dica.setObjectName("cardapioDica")
        linha.addWidget(self._label_dica, 1)

        self._botao_editar = QPushButton("Editar")
        self._botao_editar.setObjectName("cardapioBotaoRodape")
        self._botao_editar.setProperty("variante", "neutro")
        self._botao_editar.setEnabled(False)
        self._botao_editar.clicked.connect(self.editar)
        linha.addWidget(self._botao_editar)

        # Ativar/Desativar ficou, embora o mockup mostre só Editar e Excluir: é
        # o gesto de todo dia do food truck ("acabou o pão de hambúrguer"), e
        # tirá-lo daqui deixaria desativar produto sem caminho nenhum na tela.
        self._botao_status = QPushButton("Desativar")
        self._botao_status.setObjectName("cardapioBotaoRodape")
        self._botao_status.setProperty("variante", "ciano")
        self._botao_status.setEnabled(False)
        self._botao_status.clicked.connect(self.alternar_status)
        linha.addWidget(self._botao_status)

        self._botao_excluir = QPushButton("Excluir")
        self._botao_excluir.setObjectName("cardapioBotaoExcluir")
        self._botao_excluir.setEnabled(False)
        self._botao_excluir.clicked.connect(self.excluir)
        linha.addWidget(self._botao_excluir)
        return rodape

    # ------------------------------------------------------------------
    # Exibição
    # ------------------------------------------------------------------

    def exibir(self, selecao: SelecaoCardapio) -> None:
        self._selecao = selecao
        self.atualizar()

    def atualizar(self, *, selecionar: int | None = None) -> None:
        """Relê a categoria e redesenha a lista no mesmo lugar.

        `selecionar` põe um produto em destaque (o recém-cadastrado); sem ele, o
        produto que já estava escolhido continua escolhido, pelo id.
        """
        categoria = self._categoria_atualizada()
        self._selecao = SelecaoCardapio(categoria=categoria, chave=self._selecao.chave)
        if categoria is None:
            produtos: list[Produto] = []
            subcategorias: list = []
        else:
            subcategorias = _por_nome(self._service.listar_subcategorias(categoria.id))
            produtos = _por_nome(
                [p for p in self._service.listar_produtos() if p.categoria_id == categoria.id]
            )
        self._produtos_por_id = {produto.id: produto for produto in produtos}
        self._com_cabecalho = bool(subcategorias)
        self._grupos = self._montar_grupos(produtos, subcategorias)
        self._atualizar_cabecalho(categoria, len(produtos), len(subcategorias))

        lugar = (categoria.id if categoria is not None else None, self._selecao.chave)
        mesmo_lugar = lugar == self._lugar_desenhado
        self._lugar_desenhado = lugar
        if selecionar is None and mesmo_lugar:
            selecionar = self._id_selecionado()
        rolagem = self.lista.verticalScrollBar().value() if mesmo_lugar else 0
        self._redesenhar(selecionar=selecionar, rolagem=rolagem)
        self._emitir_selecao()

    def _categoria_atualizada(self) -> Categoria | None:
        """A categoria da seleção relida — pode ter sido renomeada ou desativada."""
        categoria = self._selecao.categoria
        if categoria is None:
            return None
        return {c.id: c for c in self._service.listar_categorias()}.get(categoria.id)

    def _montar_grupos(self, produtos: list[Produto], subcategorias: list) -> list[FotoGrupo]:
        """Os blocos que a lista vai desenhar, já filtrados pela seleção.

        A subcategoria de cada produto sai do `subcategoria_id` casado com a
        lista de subdivisões já lida — e não de `produto.subcategoria.nome`, que
        é uma relação e iria ao banco uma vez por subdivisão.

        Em "Todas", subdivisão vazia não vira bloco (seria um cabeçalho sem nada
        embaixo no meio do cardápio). Escolhida na árvore, vira: é o estado
        normal de quem acabou de criá-la, e "está aqui, sem itens ainda" é
        diferente de "não existe".
        """
        nomes = {sub.id: sub.nome for sub in subcategorias}
        por_subcategoria: dict[int, list[FotoProduto]] = {sub.id: [] for sub in subcategorias}
        soltos: list[FotoProduto] = []
        for produto in produtos:
            foto = _fotografar(produto, nomes.get(produto.subcategoria_id))
            if produto.subcategoria_id in por_subcategoria:
                por_subcategoria[produto.subcategoria_id].append(foto)
            else:
                soltos.append(foto)

        grupos = [
            FotoGrupo(
                rotulo=sub.nome, chave=sub.nome, editavel=True, produtos=tuple(por_subcategoria[sub.id])
            )
            for sub in subcategorias
        ]
        # O grupo dos sem subcategoria vai por último: numa categoria em
        # organização ele é a fila de trabalho de quem classifica, e fila de
        # trabalho fica no fim, não na frente do que já está pronto.
        sem_subcategoria = FotoGrupo(
            rotulo=_ROTULO_SEM_SUBCATEGORIA,
            chave=_SUB_NENHUMA,
            editavel=False,
            produtos=tuple(soltos),
        )
        chave = self._selecao.chave
        if chave == _SUB_TODAS:
            escolhidos = [grupo for grupo in grupos if grupo.produtos]
            if soltos or not subcategorias:
                escolhidos.append(sem_subcategoria)
            return escolhidos
        if chave == _SUB_NENHUMA:
            return [sem_subcategoria]
        return [grupo for grupo in grupos if grupo.chave == chave]

    def _atualizar_cabecalho(self, categoria: Categoria | None, itens: int, subdivisoes: int) -> None:
        if categoria is None:
            self._titulo.setText("Selecione uma categoria")
            self._meta.setText("")
            return
        impressora = categoria.impressora.nome if categoria.impressora is not None else None
        partes = [
            (impressora or "Sem impressora").upper(),
            _plural(itens, "ITEM", "ITENS"),
            _plural(subdivisoes, "SUBCATEGORIA", "SUBCATEGORIAS"),
        ]
        if not categoria.ativo:
            partes.append("DESATIVADA")
        self._titulo.setText(categoria.nome)
        self._meta.setText(" · ".join(partes))

    def _texto_vazio(self) -> str:
        if self._selecao.categoria is None:
            return "SELECIONE UMA CATEGORIA NA COLUNA AO LADO"
        return "NENHUM PRODUTO NESTA CATEGORIA AINDA"

    def _redesenhar(self, *, selecionar: int | None, rolagem: int) -> None:
        itens = montar_itens(
            self._grupos,
            self._campo_busca.text(),
            com_cabecalho=self._com_cabecalho,
            normalizar=chave_de_agrupamento,
            texto_vazio=self._texto_vazio(),
        )
        self.lista.definir_itens(itens, selecionar=selecionar, rolagem=rolagem)
        atual = self.lista.currentItem()
        if selecionar is not None and atual is not None and atual.isSelected():
            self.lista.scrollToItem(atual)

    def _ao_buscar(self, _texto: str) -> None:
        """A busca refaz a lista do instantâneo — sem banco, e sem soltar o
        produto escolhido se ele continua entre os resultados."""
        self._redesenhar(selecionar=self._id_selecionado(), rolagem=0)
        self._emitir_selecao()

    # ------------------------------------------------------------------
    # Seleção
    # ------------------------------------------------------------------

    def _id_selecionado(self) -> int | None:
        foto = self.lista.produto_selecionado()
        return foto.produto_id if foto is not None else None

    def produto_atual(self) -> Produto | None:
        produto_id = self._id_selecionado()
        return self._produtos_por_id.get(produto_id) if produto_id is not None else None

    def _emitir_selecao(self) -> None:
        foto = self.lista.produto_selecionado()
        self._atualizar_rodape(foto)
        self.produto_selecionado.emit(
            self._produtos_por_id.get(foto.produto_id) if foto is not None else None
        )

    def _atualizar_rodape(self, foto: FotoProduto | None) -> None:
        self._label_dica.setText(_DICA_SEM_SELECAO if foto is None else foto.nome.upper())
        self._botao_editar.setEnabled(foto is not None)
        self._botao_status.setEnabled(foto is not None)
        self._botao_status.setText("Ativar" if foto is not None and not foto.ativo else "Desativar")
        self._botao_excluir.setEnabled(foto is not None)

    def _ao_duplo_clique(self, item: QListWidgetItem) -> None:
        """Duplo clique no produto abre a edição direto (pedido do mockup).

        No cabeçalho, no espaço e no aviso não faz nada: eles não carregam
        produto, e o duplo clique não pode abrir o formulário do último
        produto escolhido vindo de um clique que não era nele.
        """
        dado = item.data(PAPEL_LINHA)
        if isinstance(dado, ItemDaLista) and dado.produto is not None:
            self.editar()

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
                    produto = self._service.criar_produto(
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
                # O produto novo já sai selecionado quando cai no bloco que está
                # na tela: é a confirmação visual de que ele entrou, e onde.
                self.atualizar(selecionar=produto.id)
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
