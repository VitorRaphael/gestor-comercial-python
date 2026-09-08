"""Modal "Adicionar item": busca do cardápio com miniatura, filtro por
categoria, quantidade e observação — o lançamento de produto na comanda.

Substitui o `_AdicionarItemDialog` que morava dentro de `comanda_view.py`, um
`QFormLayout` com a moldura de janela do sistema, `QSpinBox` de setinha e uma
lista de texto corrido (`"Arroz — R$ 10,00 — Acompanhamentos"`). No balcão do
food truck aquilo era a interação errada pelo mesmo motivo do modal de PIN:
quem opera está de pé, com a mão ocupada, e precisa achar o produto pela foto
antes de ler o nome.

## O que NÃO mudou

Nenhuma regra de negócio. O diálogo continua sem conhecer `ComandaService`:
recebe um `lancar_item(produto_id, quantidade, observacao)` e chama. Preço,
total da comanda e taxa de serviço continuam sendo conta de quem lança — o
`R$ 0,00` do rodapé daqui é **prévia visual** (preço do produto destacado ×
quantidade escolhida), não entra em cálculo nenhum e não é gravado.

O fluxo rápido também é o de antes: `Enter` no item destacado lança e o modal
**continua aberto**, com quantidade e observação zeradas e o foco de volta na
busca, para o próximo produto. É aí que está o ganho de tempo numa mesa de
oito pessoas.

## Ciclo de vida (o RNF do Celeron, e §3.2/§3.9/§3.14)

O briefing pediu, no vocabulário do Tkinter, `destroy()` + `unbind` +
`after_cancel` ao fechar. Em PySide6 os três equivalentes estão aqui, e todos
passam por `done()` — o único portão por onde saem o botão Adicionar, o
Fechar, o ✕ e o Esc:

* **timers** — `after_cancel` vira `QTimer.stop()`. São dois: o que agrupa as
  teclas da busca e o que apaga o aviso de item lançado. Nenhum dos dois pode
  disparar depois do fechamento;
* **atalhos** — não há `QShortcut` a desamarrar (o teclado é lido em
  `keyPressEvent`, um método do próprio diálogo, que morre com ele), mas há um
  `eventFilter` instalado no campo de busca, e `done()` o remove
  explicitamente;
* **widgets** — `executar_modal()` (§3.2) já faz o `deleteLater()` do diálogo
  inteiro depois do `exec()`, e com ele vão os filhos, em C++. O que `done()`
  acrescenta é soltar o **escurecedor**, que é filho da janela principal e não
  do diálogo, e esvaziar a lista: cada item guarda um `_LinhaProduto`, e
  segurar o instantâneo do cardápio inteiro depois de fechado é memória parada
  numa máquina de 4 GB.

Sinal nenhum é ligado por `lambda` (§3.14): as pílulas de categoria e os
passos de quantidade entram todos por método ligado, e quem disparou sai do
`sender()`. `lambda` captura `self`, a conexão vive no botão, o botão é filho
do diálogo — e o ciclo se fecha sem ninguém para desfazê-lo.

## Por que uma `QStyledItemDelegate`, e não um widget por linha

`funcionarios_view` monta um `QWidget` por linha e está certo lá: a lista muda
quando alguém clica num filtro. Aqui ela é refiltrada **a cada tecla
digitada**, e um widget por produto significaria destruir e reconstruir o
cardápio inteiro em widgets a cada letra — exatamente o lag que o RNF proíbe.

Com um delegado, cada linha é só um `QListWidgetItem` carregando um
`_LinhaProduto` (uma tupla de textos já prontos), e o desenho acontece só nas
~4 linhas visíveis. As miniaturas saem do `thumbnail_cache`, já recortadas em
círculo — a pintura não redimensiona imagem nenhuma.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import QEvent, QModelIndex, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.busca_produto import filtrar_produtos
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.flow_layout import FlowLayout
from gestor_comercial.ui.widgets.thumbnail_cache import FORMATO_CIRCULO, obter_pixmap

# Os mesmos quatro erros que `comanda_view` já tratava ao lançar item: eles
# viram texto na linha de aviso do rodapé, nunca exceção subindo pro Qt.
_ERROS_SERVICE = (
    RegraDeNegocioError,
    RecursoNaoEncontradoError,
    NaoAutorizadoError,
    AcessoNegadoError,
)

_TODAS_AS_CATEGORIAS = ""
_ROTULO_TODAS = "TODOS"
_SEM_SELECAO = "SELECIONE UM PRODUTO"
_DICA_PADRAO = "DUPLO CLIQUE LANÇA DIRETO"


@dataclass(frozen=True, slots=True)
class _LinhaProduto:
    """Instantâneo do que a linha da lista precisa desenhar.

    Existe para o `Produto` do SQLAlchemy não ser tocado durante a digitação.
    `listar_produtos_ativos()` não traz a categoria junto (a relação é `lazy`),
    então ler `produto.categoria.nome` dispara consulta. Isso NÃO acontecia a
    cada tecla no modal antigo — a instância guarda a relação já carregada, e a
    segunda tecla saía de graça. O problema era outro, e pior, porque mora
    justamente no laço deste modal: **`lancar_item` faz commit, e o commit
    expira os atributos das instâncias**. Ou seja, era depois de cada item
    lançado — com o modal ainda aberto, que é o fluxo rápido — que a digitação
    voltava a bater no banco. Medido sobre o cardápio real (113 produtos), com
    as consultas contadas por um `after_cursor_execute`:

        ANTIGO  primeira tecla, lista fria                    9 consultas
        ANTIGO  teclas 2 a 4                                  0 consultas
        ANTIGO  3 teclas DEPOIS de lançar um item           120 consultas

        NOVO    abertura do modal (instantâneo, frio)       128 consultas
        NOVO    teclas 2 a 4                                  0 consultas
        NOVO    3 teclas DEPOIS de lançar um item             0 consultas

    A troca é deliberada: paga-se **uma vez**, na abertura, o que antes se
    pagava de novo a cada lançamento, e o caminho da tecla fica sem banco em
    qualquer estado. As 128 da abertura são o N+1 do §3.6 aparecendo aqui e
    poderiam virar 2 com `selectinload` no repositório — fica registrado, mas é
    mudança no repositório, que serve outras telas, e não neste arquivo.

    O que a digitação também deixou de refazer, e não aparece na conta acima:
    `formatar_reais` (que passa por `Decimal.quantize`) e um `QIcon` por
    produto, ambos por tecla, para o cardápio inteiro filtrado.
    """

    produto_id: int
    nome: str
    preco: Decimal
    preco_texto: str
    categoria: str
    metadados: str
    imagem_path: str | None


def _instantaneo(produtos: list[Produto]) -> list[_LinhaProduto]:
    linhas = []
    for produto in produtos:
        categoria = produto.categoria.nome
        # O `[COMBO]` do modal antigo virava um sufixo no meio do nome. Aqui
        # ele desce para a linha de metadados, junto da categoria, e o nome do
        # produto fica limpo para a busca e para o olho.
        metadados = f"{categoria} · COMBO" if produto.is_combo else categoria
        linhas.append(
            _LinhaProduto(
                produto_id=produto.id,
                nome=produto.nome,
                preco=produto.preco,
                preco_texto=formatar_reais(produto.preco),
                categoria=categoria,
                metadados=metadados.upper(),
                imagem_path=produto.imagem_path,
            )
        )
    return linhas


class _IconeLupa(QWidget):
    """A lupa do campo de busca, desenhada à mão.

    Mesma decisão do cadeado do `pin_pad_dialog`: o glifo de lupa mora no bloco
    de emoji, cai no Segoe UI Emoji, sai colorido e chapado e ignora o tema —
    e a máquina limpa do food truck pode nem ter a fonte. Oito linhas de
    `QPainter` custam menos, e a cor daqui é relida a cada repintura, então o
    ícone acompanha o alternador Claro/Escuro de graça (§3.15).
    """

    LADO_PX = 16

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("addItemLupa")
        self.setFixedSize(self.LADO_PX, self.LADO_PX)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        cor = QColor(ThemeController.instancia().tokens_atuais["texto_fraquissimo"])
        caneta = QPen(cor, 1.4)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)

        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawEllipse(QRectF(2.0, 2.0, 9.0, 9.0))
        pintor.drawLine(QPointF(10.4, 10.4), QPointF(14.0, 14.0))
        pintor.end()


class _DelegadoProduto(QStyledItemDelegate):
    """Desenha uma linha da lista: miniatura circular, nome, categoria, preço."""

    ALTURA_PX = 58
    LADO_MINIATURA_PX = 40
    MARGEM_PX = 10
    ESPACO_APOS_MINIATURA_PX = 12
    # Folga entre o fim do nome e o começo do preço. Sem ela, um nome comprido
    # encosta no valor e os dois viram uma palavra só.
    FOLGA_ANTES_DO_PRECO_PX = 14
    LARGURA_INDICADOR_PX = 3

    @nao_deixa_escapar()
    def paint(  # override Qt
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        linha = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(linha, _LinhaProduto):
            super().paint(painter, option, index)
            return

        tokens = ThemeController.instancia().tokens_atuais
        selecionada = bool(option.state & QStyle.StateFlag.State_Selected)
        sob_o_mouse = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(option.rect).adjusted(1.0, 1.0, -1.0, -1.0)

        if selecionada or sob_o_mouse:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens["superficie_2"]))
            painter.drawRoundedRect(area, 10.0, 10.0)
        if selecionada:
            # A barra âmbar diz QUAL linha o Enter vai lançar — com o foco
            # sempre no campo de busca, ela é o único sinal de destino.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens["acento"]))
            indicador = QRectF(
                area.left(),
                area.top() + 10.0,
                float(self.LARGURA_INDICADOR_PX),
                area.height() - 20.0,
            )
            painter.drawRoundedRect(indicador, 1.5, 1.5)

        lado = self.LADO_MINIATURA_PX
        pixmap = obter_pixmap(linha.imagem_path, lado, linha.nome, formato=FORMATO_CIRCULO)
        x_miniatura = area.left() + self.MARGEM_PX + self.LARGURA_INDICADOR_PX
        painter.drawPixmap(
            QPointF(x_miniatura, area.top() + (area.height() - lado) / 2.0),
            pixmap,
        )

        fonte_preco = QFont(option.font)
        fonte_preco.setPixelSize(13)
        fonte_preco.setBold(True)
        largura_preco = QFontMetrics(fonte_preco).horizontalAdvance(linha.preco_texto)
        x_preco = area.right() - self.MARGEM_PX - largura_preco

        x_texto = x_miniatura + lado + self.ESPACO_APOS_MINIATURA_PX
        largura_texto = max(0.0, x_preco - self.FOLGA_ANTES_DO_PRECO_PX - x_texto)

        fonte_nome = QFont(option.font)
        fonte_nome.setPixelSize(13)
        fonte_nome.setBold(True)
        nome = QFontMetrics(fonte_nome).elidedText(
            linha.nome, Qt.TextElideMode.ElideRight, int(largura_texto)
        )
        painter.setFont(fonte_nome)
        painter.setPen(QColor(tokens["texto"]))
        painter.drawText(
            QRectF(x_texto, area.top() + 11.0, largura_texto, 18.0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            nome,
        )

        fonte_meta = QFont(option.font)
        fonte_meta.setPixelSize(9)
        fonte_meta.setBold(True)
        fonte_meta.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        meta = QFontMetrics(fonte_meta).elidedText(
            linha.metadados, Qt.TextElideMode.ElideRight, int(largura_texto)
        )
        painter.setFont(fonte_meta)
        painter.setPen(QColor(tokens["texto_fraco"]))
        painter.drawText(
            QRectF(x_texto, area.top() + 29.0, largura_texto, 14.0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            meta,
        )

        painter.setFont(fonte_preco)
        painter.setPen(QColor(tokens["texto"]))
        painter.drawText(
            QRectF(x_preco, area.top(), float(largura_preco), area.height()),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            linha.preco_texto,
        )
        painter.restore()

    @nao_deixa_escapar(retorno=QSize(0, ALTURA_PX))
    def sizeHint(  # noqa: N802 (override Qt)
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        # Largura zero: em modo lista a `QListWidget` já estica o item até a
        # borda do viewport, e devolver uma largura própria só criaria barra de
        # rolagem horizontal onde não há conteúdo para rolar.
        return QSize(0, self.ALTURA_PX)


class AdicionarItemDialog(QDialog):
    """Cartão de lançamento rápido: busca, categorias, quantidade e observação."""

    LARGURA_CARTAO_PX = 500
    ALTURA_LISTA_PX = 244
    LADO_BOTAO_FECHAR_PX = 32
    LADO_BOTAO_PASSO_PX = 34
    ALTURA_BUSCA_PX = 46
    QUANTIDADE_MAXIMA = 999
    LIMITE_OBSERVACAO = 120
    # Agrupa as teclas de uma digitação rápida numa refiltragem só. Curto o
    # bastante para a lista parecer instantânea e longo o bastante para quem
    # digita "coca" não pagar quatro varreduras do cardápio.
    MS_ENTRE_FILTROS = 60
    MS_AVISO_NA_TELA = 2200
    # Teto da faixa de categorias, em fileiras de pílula. O cardápio real do
    # food truck tem quinze categorias: sem teto a faixa empurraria a lista
    # para fora do cartão, e num monitor de 768px o cartão sairia da tela. Com
    # ele, quem passa de duas fileiras rola a faixa — e continua tendo a busca,
    # que é o caminho rápido de qualquer jeito.
    FILEIRAS_DE_CATEGORIA = 2

    def __init__(
        self,
        produtos: list[Produto],
        contexto: str,
        lancar_item: Callable[[int, int, str | None], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._lancar_item = lancar_item
        self._linhas = _instantaneo(produtos)
        self._categoria_ativa = _TODAS_AS_CATEGORIAS
        self._quantidade = 1
        self._backdrop: Backdrop | None = None
        self._pills: dict[str, QPushButton] = {}

        self.setObjectName("addItemDialog")
        self.setWindowTitle("Adicionar item")
        # Sem moldura do sistema: o cabeçalho (contexto, título e o ✕) é do
        # cartão, e o fundo translúcido é o que faz os cantos de 16px saírem
        # redondos em vez de recortados contra um retângulo opaco.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        self._timer_filtro = QTimer(self)
        self._timer_filtro.setSingleShot(True)
        self._timer_filtro.timeout.connect(self._filtrar_agora)

        self._timer_aviso = QTimer(self)
        self._timer_aviso.setSingleShot(True)
        self._timer_aviso.timeout.connect(self._restaurar_dica)

        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)

        cartao = QFrame()
        cartao.setObjectName("addItemCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(22, 18, 22, 18)
        corpo.setSpacing(13)
        corpo.addLayout(self._montar_cabecalho(contexto))
        corpo.addWidget(self._montar_busca())
        corpo.addWidget(self._montar_categorias())
        corpo.addWidget(self._montar_lista())
        corpo.addWidget(self._montar_rodape())
        corpo.addLayout(self._montar_acoes())

        self._definir_quantidade(1)
        self._filtrar_agora()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar_cabecalho(self, contexto: str) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(12)

        textos = QVBoxLayout()
        textos.setSpacing(3)
        rotulo_contexto = QLabel(f"{contexto.upper()} · LANÇAMENTO RÁPIDO")
        rotulo_contexto.setObjectName("addItemContexto")
        textos.addWidget(rotulo_contexto)
        titulo = QLabel("Adicionar item")
        titulo.setObjectName("addItemTitulo")
        textos.addWidget(titulo)
        linha.addLayout(textos)
        linha.addStretch()

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("addItemFechar")
        self._botao_fechar.setFixedSize(self.LADO_BOTAO_FECHAR_PX, self.LADO_BOTAO_FECHAR_PX)
        self._botao_fechar.setToolTip("Fechar (Esc)")
        cartao_modal.preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignTop)
        return linha

    def _montar_busca(self) -> QFrame:
        self._caixa_busca = QFrame()
        self._caixa_busca.setObjectName("addItemBuscaCaixa")
        self._caixa_busca.setFixedHeight(self.ALTURA_BUSCA_PX)
        self._caixa_busca.setProperty("foco", False)

        dentro = QHBoxLayout(self._caixa_busca)
        dentro.setContentsMargins(14, 0, 16, 0)
        dentro.setSpacing(10)
        dentro.addWidget(_IconeLupa(), 0, Qt.AlignmentFlag.AlignVCenter)

        self._campo_busca = QLineEdit()
        self._campo_busca.setObjectName("addItemBusca")
        self._campo_busca.setPlaceholderText("Buscar produto por nome...")
        self._campo_busca.textChanged.connect(self._ao_digitar)
        # O anel âmbar é do QUADRO, e o foco é do campo lá dentro: sem este
        # filtro o `[foco="true"]` nunca acenderia. É o único `eventFilter` do
        # arquivo, e `done()` o remove.
        self._campo_busca.installEventFilter(self)
        dentro.addWidget(self._campo_busca, 1)

        dica_enter = QLabel("ENTER\nLANÇA")
        dica_enter.setObjectName("addItemDicaEnter")
        dica_enter.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dentro.addWidget(dica_enter, 0, Qt.AlignmentFlag.AlignVCenter)
        return self._caixa_busca

    def _montar_categorias(self) -> QScrollArea:
        """Uma pílula por categoria presente no cardápio ativo, mais "TODOS".

        Montadas UMA vez: a lista de categorias não muda enquanto o modal está
        aberto, então clicar num filtro só troca uma propriedade de estilo — não
        reconstrói botão nenhum.

        O `FlowLayout` (o mesmo dos cards da Central de Loja) quebra a faixa em
        outra fileira quando as pílulas não cabem na largura do cartão; um
        `QHBoxLayout` as espremeria até o rótulo sumir, que é o defeito que a
        Fase 7 achou na tela de Configurações. Quem limita a faixa a duas
        fileiras é a área de rolagem em volta — ver `FILEIRAS_DE_CATEGORIA`.
        """
        self._faixa_categorias = QWidget()
        fluxo = FlowLayout(self._faixa_categorias, spacing=6)

        vistas: list[str] = []
        for linha in self._linhas:
            if linha.categoria not in vistas:
                vistas.append(linha.categoria)

        pares = [(_TODAS_AS_CATEGORIAS, _ROTULO_TODAS)] + [(c, c.upper()) for c in vistas]
        for chave, rotulo in pares:
            pill = QPushButton(rotulo)
            pill.setObjectName("addItemCategoria")
            pill.setProperty("categoria", chave)
            pill.setProperty("ativa", chave == self._categoria_ativa)
            cartao_modal.preparar_botao(pill)
            pill.clicked.connect(self._categoria_clicada)
            fluxo.addWidget(pill)
            self._pills[chave] = pill

        self._rolagem_categorias = QScrollArea()
        self._rolagem_categorias.setObjectName("addItemFaixa")
        self._rolagem_categorias.setWidget(self._faixa_categorias)
        self._rolagem_categorias.setWidgetResizable(True)
        self._rolagem_categorias.setFrameShape(QFrame.Shape.NoFrame)
        self._rolagem_categorias.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._rolagem_categorias.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        return self._rolagem_categorias

    def _ajustar_altura_da_faixa(self) -> None:
        """Fecha a faixa na altura real das pílulas, até o teto de fileiras.

        Roda no `showEvent`, e não na construção, porque a altura de uma pílula
        só é verdade **depois** do primeiro `polish`: antes disso o `sizeHint`
        não conhece o `padding` que o QSS global aplica, e a faixa fecharia
        apertada demais.

        Sem este ajuste a faixa fica com a altura de UMA fileira (o
        `sizeHint()` do `FlowLayout` devolve o mínimo) e as demais são pintadas
        por cima da lista de produtos — foi assim que o defeito apareceu na
        primeira renderização com o cardápio real.
        """
        largura = self._rolagem_categorias.viewport().width()
        fluxo = self._faixa_categorias.layout()
        if largura <= 0 or fluxo is None:
            return
        altura_conteudo = fluxo.heightForWidth(largura)
        altura_fileira = max(
            (pill.sizeHint().height() for pill in self._pills.values()), default=24
        )
        teto = self.FILEIRAS_DE_CATEGORIA * altura_fileira + (
            self.FILEIRAS_DE_CATEGORIA - 1
        ) * fluxo.spacing()

        self._faixa_categorias.setFixedHeight(altura_conteudo)
        self._rolagem_categorias.setFixedHeight(min(altura_conteudo, teto))

    def _montar_lista(self) -> QListWidget:
        self._lista = QListWidget()
        self._lista.setObjectName("addItemLista")
        self._lista.setFixedHeight(self.ALTURA_LISTA_PX)
        self._lista.setFrameShape(QFrame.Shape.NoFrame)
        # Sem foco: o campo de busca é dono do cursor do começo ao fim, e um
        # clique numa linha seleciona sem tirar o teclado de lá — o operador
        # clica no produto e continua digitando o próximo.
        self._lista.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._lista.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._lista.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._lista.setUniformItemSizes(True)
        self._lista.setMouseTracking(True)
        # O delegado é filho da lista de propósito: `setItemDelegate` NÃO toma
        # posse, e sem parent o objeto morreria com o nome Python enquanto o
        # Qt ainda o chamasse para pintar.
        self._delegado = _DelegadoProduto(self._lista)
        self._lista.setItemDelegate(self._delegado)
        self._lista.currentItemChanged.connect(self._ao_trocar_selecao)
        self._lista.itemDoubleClicked.connect(self._ao_duplo_clique)
        return self._lista

    def _montar_rodape(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("addItemRodape")
        grade = QGridLayout(painel)
        grade.setContentsMargins(16, 12, 16, 12)
        grade.setHorizontalSpacing(18)
        grade.setVerticalSpacing(8)

        rotulo_quantidade = QLabel("QUANTIDADE")
        rotulo_quantidade.setObjectName("addItemRotulo")
        grade.addWidget(rotulo_quantidade, 0, 0)

        passos = QHBoxLayout()
        passos.setSpacing(10)
        self._botao_menos = self._criar_passo("−", -1, "Uma unidade a menos")
        passos.addWidget(self._botao_menos)
        self._label_quantidade = QLabel("1")
        self._label_quantidade.setObjectName("addItemQuantidade")
        self._label_quantidade.setMinimumWidth(28)
        self._label_quantidade.setAlignment(Qt.AlignmentFlag.AlignCenter)
        passos.addWidget(self._label_quantidade)
        self._botao_mais = self._criar_passo("+", 1, "Uma unidade a mais")
        passos.addWidget(self._botao_mais)
        grade.addLayout(passos, 1, 0)

        self._campo_observacao = QLineEdit()
        self._campo_observacao.setObjectName("addItemObservacao")
        self._campo_observacao.setPlaceholderText("Observação (ex.: sem cebola)")
        self._campo_observacao.setMaxLength(self.LIMITE_OBSERVACAO)
        grade.addWidget(self._campo_observacao, 0, 1)

        resumo = QHBoxLayout()
        resumo.setSpacing(10)
        self._label_resumo = QLabel(_SEM_SELECAO)
        self._label_resumo.setObjectName("addItemRotulo")
        resumo.addWidget(self._label_resumo, 1)
        self._label_total = QLabel(formatar_reais(Decimal("0")))
        self._label_total.setObjectName("addItemTotal")
        self._label_total.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        resumo.addWidget(self._label_total)
        grade.addLayout(resumo, 1, 1)

        grade.setColumnStretch(1, 1)
        return painel

    def _criar_passo(self, rotulo: str, delta: int, dica: str) -> QPushButton:
        botao = QPushButton(rotulo)
        botao.setObjectName("addItemPasso")
        botao.setFixedSize(self.LADO_BOTAO_PASSO_PX, self.LADO_BOTAO_PASSO_PX)
        botao.setToolTip(dica)
        # O delta vive na propriedade, e não numa `lambda` amarrada no clique:
        # ver §3.14 no cabeçalho do arquivo.
        botao.setProperty("delta", delta)
        cartao_modal.preparar_botao(botao)
        botao.clicked.connect(self._passo_clicado)
        return botao

    def _montar_acoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(10)

        self._label_aviso = QLabel(_DICA_PADRAO)
        self._label_aviso.setObjectName("addItemAviso")
        self._label_aviso.setProperty("estado", "dica")
        linha.addWidget(self._label_aviso, 1)

        self._botao_cancelar = QPushButton("Fechar")
        self._botao_cancelar.setObjectName("addItemCancelar")
        cartao_modal.preparar_botao(self._botao_cancelar)
        self._botao_cancelar.clicked.connect(self.reject)
        linha.addWidget(self._botao_cancelar)

        self._botao_confirmar = QPushButton("Adicionar")
        self._botao_confirmar.setObjectName("addItemConfirmar")
        cartao_modal.preparar_botao(self._botao_confirmar)
        self._botao_confirmar.clicked.connect(self._lancar_selecionado)
        linha.addWidget(self._botao_confirmar)
        return linha

    # ------------------------------------------------------------------
    # Filtragem
    # ------------------------------------------------------------------

    def _ao_digitar(self, texto: str) -> None:
        self._timer_filtro.start(self.MS_ENTRE_FILTROS)

    def _garantir_filtro_aplicado(self) -> None:
        """Adianta a refiltragem pendente.

        O agrupamento de teclas cria uma janela de ~60 ms em que a lista ainda
        mostra o resultado anterior. Sem isto, quem digita o nome e bate `Enter`
        na mesma batida lançaria o produto do filtro ANTIGO — o pior tipo de bug
        de PDV, porque o item errado entra na comanda sem ninguém ver.
        """
        if self._timer_filtro.isActive():
            self._timer_filtro.stop()
            self._filtrar_agora()

    def _filtrar_agora(self) -> None:
        linhas = self._linhas
        if self._categoria_ativa:
            linhas = [linha for linha in linhas if linha.categoria == self._categoria_ativa]
        # `filtrar_produtos` é a mesma função da busca antiga (substring
        # tolerante a acento e caixa, palavra por palavra) e continua com os
        # testes dela em `tests/unit/test_busca_produto.py`. O que mudou é o que
        # ela recebe: `_LinhaProduto` em vez de `Produto`.
        linhas = filtrar_produtos(linhas, self._campo_busca.text())

        self._lista.clear()
        for linha in linhas:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, linha)
            self._lista.addItem(item)
        if self._lista.count() > 0:
            self._lista.setCurrentRow(0)
        self._atualizar_resumo()

    def _categoria_clicada(self) -> None:
        botao = self.sender()
        if not isinstance(botao, QPushButton):
            return
        self._categoria_ativa = str(botao.property("categoria") or _TODAS_AS_CATEGORIAS)
        for chave, pill in self._pills.items():
            ativa = chave == self._categoria_ativa
            # Repolir custa um recálculo de estilo: só quem mudou de estado
            # paga (mesma economia do `_pintar_marcadores` do modal de PIN).
            if pill.property("ativa") != ativa:
                aplicar_propriedade(pill, "ativa", ativa)
        self._filtrar_agora()
        self._campo_busca.setFocus(Qt.FocusReason.OtherFocusReason)

    # ------------------------------------------------------------------
    # Quantidade e resumo
    # ------------------------------------------------------------------

    def _passo_clicado(self) -> None:
        botao = self.sender()
        if not isinstance(botao, QPushButton):
            return
        self._definir_quantidade(self._quantidade + int(botao.property("delta") or 0))

    def _definir_quantidade(self, valor: int) -> None:
        # Mínimo de 1: lançar "zero unidades" não é operação que exista na
        # comanda, e o dedo erra o `−` com frequência no balcão.
        self._quantidade = max(1, min(self.QUANTIDADE_MAXIMA, valor))
        self._label_quantidade.setText(str(self._quantidade))
        self._botao_menos.setEnabled(self._quantidade > 1)
        self._botao_mais.setEnabled(self._quantidade < self.QUANTIDADE_MAXIMA)
        self._atualizar_resumo()

    def _linha_selecionada(self) -> _LinhaProduto | None:
        item = self._lista.currentItem()
        if item is None:
            return None
        linha = item.data(Qt.ItemDataRole.UserRole)
        return linha if isinstance(linha, _LinhaProduto) else None

    def _atualizar_resumo(self) -> None:
        """Prévia visual do que o Enter vai lançar. Não é cálculo de comanda.

        O total da comanda, a taxa de serviço e o arredondamento continuam
        inteiros em `ComandaService`/`services.dinheiro` — aqui é preço ×
        quantidade, formatado pelo mesmo `formatar_reais` do resto do app
        (§3.8), só para o operador conferir antes de apertar.
        """
        linha = self._linha_selecionada()
        self._botao_confirmar.setEnabled(linha is not None)
        if linha is None:
            self._label_resumo.setText(_SEM_SELECAO)
            self._label_total.setText(formatar_reais(Decimal("0")))
            return
        self._label_resumo.setText(linha.nome.upper())
        self._label_total.setText(formatar_reais(linha.preco * self._quantidade))

    def _ao_trocar_selecao(
        self, atual: QListWidgetItem | None, anterior: QListWidgetItem | None
    ) -> None:
        self._atualizar_resumo()

    def _mover_selecao(self, delta: int) -> None:
        total = self._lista.count()
        if total == 0:
            return
        atual = self._lista.currentRow()
        novo = 0 if atual == -1 else max(0, min(total - 1, atual + delta))
        self._lista.setCurrentRow(novo)
        self._lista.scrollToItem(self._lista.currentItem())

    # ------------------------------------------------------------------
    # Lançamento
    # ------------------------------------------------------------------

    def _ao_duplo_clique(self, item: QListWidgetItem) -> None:
        self._lista.setCurrentItem(item)
        self._lancar_selecionado()

    def _lancar_selecionado(self) -> None:
        self._garantir_filtro_aplicado()
        linha = self._linha_selecionada()
        if linha is None:
            return

        quantidade = self._quantidade
        observacao = self._campo_observacao.text().strip() or None
        try:
            self._lancar_item(linha.produto_id, quantidade, observacao)
        except _ERROS_SERVICE as erro:
            self._avisar(str(erro).upper(), "erro")
            return

        # Item lançado: reseta para o próximo, mas mantém o modal aberto e o
        # foco na busca — é aí que está o ganho de velocidade do PDV.
        self._definir_quantidade(1)
        self._campo_observacao.clear()
        self._campo_busca.clear()
        self._garantir_filtro_aplicado()
        self._campo_busca.setFocus(Qt.FocusReason.OtherFocusReason)
        self._avisar(f"{quantidade}× {linha.nome.upper()} LANÇADO", "sucesso")

    def _avisar(self, mensagem: str, estado: str) -> None:
        """Uma linha só no rodapé, que troca de papel entre dica, erro e aviso.

        O timer devolve a dica depois de alguns segundos, e só para o aviso de
        sucesso: erro de regra de negócio ("comanda fechada") fica na tela até
        o operador fazer outra coisa, porque sumir sozinho é como um item deixa
        de ser lançado sem ninguém perceber.
        """
        self._label_aviso.setText(mensagem)
        aplicar_propriedade(self._label_aviso, "estado", estado)
        self._timer_aviso.stop()
        if estado == "sucesso":
            self._timer_aviso.start(self.MS_AVISO_NA_TELA)

    def _restaurar_dica(self) -> None:
        self._timer_aviso.stop()
        self._label_aviso.setText(_DICA_PADRAO)
        aplicar_propriedade(self._label_aviso, "estado", "dica")

    # ------------------------------------------------------------------
    # Overrides do Qt
    # ------------------------------------------------------------------

    @nao_deixa_escapar(retorno=False)
    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:  # noqa: N802 (override Qt)
        if watched is self._campo_busca and event.type() in (
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
        ):
            aplicar_propriedade(self._caixa_busca, "foco", event.type() == QEvent.Type.FocusIn)
        return super().eventFilter(watched, event)

    @nao_deixa_escapar()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        """O teclado é lido aqui, e só aqui.

        Nem a lista nem os botões aceitam foco
        (`cartao_modal.preparar_botao`, `setFocusPolicy(NoFocus)`), então `↑`/`↓`/`Enter` chegam sempre a este
        método, venha o cursor do campo de busca ou do de observação. Ligar
        `returnPressed` dos campos ALÉM disto seria o caminho para o item ser
        lançado duas vezes com um Enter só.

        O Esc cai no `super()` de propósito: lá o `QDialog` o traduz em
        `reject()`, que passa por `done()` e portanto pela mesma limpeza dos
        outros caminhos de saída.
        """
        tecla = event.key()
        if tecla == Qt.Key.Key_Down:
            self._mover_selecao(1)
            return
        if tecla == Qt.Key.Key_Up:
            self._mover_selecao(-1)
            return
        if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._lancar_selecionado()
            return
        super().keyPressEvent(event)

    @nao_deixa_escapar()
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        if self._backdrop is None:
            self._backdrop = cartao_modal.montar(self)
        self._ajustar_altura_da_faixa()
        self.adjustSize()
        cartao_modal.centralizar_no_pai(self)
        self._campo_busca.setFocus(Qt.FocusReason.OtherFocusReason)

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única — e por isso o lugar certo da limpeza.

        Adicionar, Fechar, o ✕ e o Esc passam todos por aqui; `closeEvent`
        sozinho não serviria, porque `done()` faz `hide()`, não `close()`
        (§3.9). Saem juntos os dois timers, o filtro de eventos do campo de
        busca, o instantâneo do cardápio e o escurecedor.
        """
        self._timer_filtro.stop()
        self._timer_aviso.stop()
        self._campo_busca.removeEventFilter(self)
        self._lista.clear()
        self._linhas = []
        backdrop, self._backdrop = self._backdrop, None
        cartao_modal.descartar(backdrop)
        super().done(resultado)
