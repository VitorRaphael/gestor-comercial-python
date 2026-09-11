"""O Cardápio em cartões (§9.11): glifos, insígnia, e as duas listas pintadas.

A tela do Cardápio tinha duas colunas feitas de widgets: a árvore da esquerda
montava um `QWidget` com quatro rótulos para cada categoria, e a tabela da
direita, cinco células com widget próprio para cada produto — ~58 widgets
polidos por QSS a cada troca de categoria, destruídos e refeitos. Não vazava
(a contagem de widgets ficava estável), mas custava: medido sobre o cardápio
real, 34 ms por troca de categoria e +21 MB de RSS na primeira passada pelas
quinze categorias, que é o preço de criar e polir widget contra um QSS de 94 KB.

Aqui as duas colunas são **pintadas**. Cada linha é um item de modelo que
carrega um instantâneo imutável (`LinhaDeCategoria`, `LinhaDeSubdivisao`,
`ItemDaLista`) e um delegado desenha só as linhas que estão na tela. É a mesma
decisão do modal "Adicionar item" (§9.4), e pelo mesmo motivo: widget por linha
só se justifica quando a linha precisa de um controle de verdade dentro dela —
aqui não precisa. De quebra, a classe inteira de defeito "widget fantasma" deixa
de existir por construção: não há widget por linha para sobrar, sobrepor ou
esquecer de desconectar.

## Por que instantâneo, e não o `Produto` direto

Mesma lição do §9.4: **todo `commit` expira as instâncias do SQLAlchemy**, e o
Cardápio faz commit a cada produto salvo. Um delegado que lesse `produto.nome`
na hora de pintar voltaria ao banco a cada repintura — rolar a lista ou passar
o mouse por cima dela viraria consulta. O instantâneo é montado uma vez, na
recarga, e a pintura nunca toca o banco (`test_pintar_nao_toca_no_banco`).

## Cor

Tudo é lido de `ThemeController.instancia().tokens_atuais` **a cada pintura**,
então o alternador Claro/Escuro repinta de graça (§3.15) — nenhuma cor fica
congelada num `setStyleSheet`, e ninguém assina o sinal `mudou` do controlador
(§3.14). Os tokens passam por `cor_do_token`, porque metade da paleta está em
`rgba()` do CSS e o `QColor` não entende essa grafia.

Os glifos são desenhados à mão pelo motivo de sempre (§9.4, §9.9, §9.10): o
símbolo equivalente mora no bloco de emoji, sai colorido e chapado, ignora o
tema — e o `⌄` que a árvore antiga usava como seta nem existe na fonte da marca:
saía como um quadradinho.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from PySide6.QtCore import QModelIndex, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.cores import cor_do_token
from gestor_comercial.ui.widgets.thumbnail_cache import obter_pixmap

# O papel de dado onde cada item das duas listas guarda o seu instantâneo. Um
# acima dos três que a árvore já usava para identidade (`UserRole` a `+2`).
PAPEL_LINHA = Qt.ItemDataRole.UserRole + 3

RETICENCIAS = "…"

# ---------------------------------------------------------------------------
# Glifos
# ---------------------------------------------------------------------------

GLIFO_CAMADAS = "camadas"
GLIFO_ETIQUETA = "etiqueta"
GLIFO_CAIXA = "caixa"
GLIFO_CIFRAO = "cifrao"
GLIFO_PASTA = "pasta"
GLIFO_LUPA = "lupa"
GLIFO_SETA_DIREITA = "seta_direita"
GLIFO_SETA_BAIXO = "seta_baixo"

# Os glifos são traçados numa grade de 24x24 e escalados para o tamanho pedido,
# então um desenho só serve a insígnia de 40px e a seta de 12px.
_GRADE = 24.0


@lru_cache(maxsize=None)
def _caminho_do_glifo(nome: str) -> QPainterPath:
    """O traço do glifo, montado uma vez por nome e reaproveitado.

    `lru_cache` porque o caminho é o mesmo em toda pintura — a árvore desenha
    uma seta por categoria a cada repintura, e remontar quinze `QPainterPath`
    idênticos por quadro é o tipo de trabalho que o Celeron sente.
    """
    p = QPainterPath()
    if nome == GLIFO_CAMADAS:
        p.moveTo(12.0, 3.0)
        p.lineTo(21.0, 7.5)
        p.lineTo(12.0, 12.0)
        p.lineTo(3.0, 7.5)
        p.closeSubpath()
        p.moveTo(3.0, 12.0)
        p.lineTo(12.0, 16.5)
        p.lineTo(21.0, 12.0)
        p.moveTo(3.0, 16.5)
        p.lineTo(12.0, 21.0)
        p.lineTo(21.0, 16.5)
    elif nome == GLIFO_ETIQUETA:
        p.moveTo(3.5, 3.5)
        p.lineTo(11.2, 3.5)
        p.lineTo(20.5, 12.8)
        p.lineTo(12.8, 20.5)
        p.lineTo(3.5, 11.2)
        p.closeSubpath()
        p.addEllipse(QPointF(8.0, 8.0), 1.4, 1.4)
    elif nome == GLIFO_CAIXA:
        p.moveTo(12.0, 2.5)
        p.lineTo(20.5, 7.0)
        p.lineTo(20.5, 17.0)
        p.lineTo(12.0, 21.5)
        p.lineTo(3.5, 17.0)
        p.lineTo(3.5, 7.0)
        p.closeSubpath()
        p.moveTo(3.5, 7.0)
        p.lineTo(12.0, 11.5)
        p.lineTo(20.5, 7.0)
        p.moveTo(12.0, 11.5)
        p.lineTo(12.0, 21.5)
        p.moveTo(7.75, 4.75)
        p.lineTo(16.25, 9.25)
    elif nome == GLIFO_CIFRAO:
        p.addEllipse(QPointF(12.0, 12.0), 9.5, 9.5)
        # O "S": meia-volta pela esquerda em cima, meia-volta pela direita
        # embaixo. Ângulos do Qt: 0° às 3 horas, positivo no anti-horário.
        p.moveTo(15.2, 8.6)
        p.lineTo(10.6, 8.6)
        p.arcTo(QRectF(8.8, 8.6, 3.6, 3.6), 90.0, 180.0)
        p.lineTo(13.4, 12.2)
        p.arcTo(QRectF(11.6, 12.2, 3.6, 3.6), 90.0, -180.0)
        p.lineTo(8.8, 15.8)
        p.moveTo(12.0, 6.4)
        p.lineTo(12.0, 8.6)
        p.moveTo(12.0, 15.8)
        p.lineTo(12.0, 17.6)
    elif nome == GLIFO_PASTA:
        p.moveTo(3.5, 6.5)
        p.quadTo(3.5, 4.5, 5.5, 4.5)
        p.lineTo(9.2, 4.5)
        p.lineTo(11.2, 6.8)
        p.lineTo(18.5, 6.8)
        p.quadTo(20.5, 6.8, 20.5, 8.8)
        p.lineTo(20.5, 17.5)
        p.quadTo(20.5, 19.5, 18.5, 19.5)
        p.lineTo(5.5, 19.5)
        p.quadTo(3.5, 19.5, 3.5, 17.5)
        p.closeSubpath()
        p.moveTo(3.5, 10.2)
        p.lineTo(20.5, 10.2)
    elif nome == GLIFO_LUPA:
        p.addEllipse(QPointF(10.5, 10.5), 6.5, 6.5)
        p.moveTo(15.4, 15.4)
        p.lineTo(20.5, 20.5)
    elif nome == GLIFO_SETA_DIREITA:
        p.moveTo(9.0, 5.5)
        p.lineTo(15.5, 12.0)
        p.lineTo(9.0, 18.5)
    elif nome == GLIFO_SETA_BAIXO:
        p.moveTo(5.5, 9.0)
        p.lineTo(12.0, 15.5)
        p.lineTo(18.5, 9.0)
    return p


def desenhar_glifo(
    pintor: QPainter,
    nome: str,
    area: QRectF,
    cor: QColor,
    espessura: float = 1.8,
) -> None:
    """Traça o glifo `nome` dentro de `area`, na cor dada.

    `espessura` é em unidades da grade de 24: 1.8 vira ~1.5px numa insígnia de
    40px e ~1px na lupa de 14px, que é a proporção do mockup.
    """
    pintor.save()
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    lado = min(area.width(), area.height())
    pintor.translate(
        area.left() + (area.width() - lado) / 2.0, area.top() + (area.height() - lado) / 2.0
    )
    pintor.scale(lado / _GRADE, lado / _GRADE)
    caneta = QPen(cor, espessura)
    caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
    caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pintor.setPen(caneta)
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawPath(_caminho_do_glifo(nome))
    pintor.restore()


def desenhar_insignia(pintor: QPainter, area: QRectF, glifo: str, tokens: dict[str, str]) -> None:
    """O círculo âmbar com o glifo no meio — KPIs, cabeçalho do painel e blocos.

    Uma função só para os três lugares: é o mesmo elemento visual, e três
    cópias divergiriam na primeira vez que alguém ajustasse o tamanho do glifo.
    """
    pintor.save()
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setPen(QPen(cor_do_token(tokens["cardapio_icone_borda"]), 1.0))
    pintor.setBrush(cor_do_token(tokens["cardapio_icone_tinta"]))
    pintor.drawEllipse(area.adjusted(0.5, 0.5, -0.5, -0.5))
    lado = area.width() * 0.48
    alvo = QRectF(area.center().x() - lado / 2.0, area.center().y() - lado / 2.0, lado, lado)
    desenhar_glifo(pintor, glifo, alvo, cor_do_token(tokens["cardapio_icone_glifo"]))
    pintor.restore()


def encurtar(texto: str, metricas: QFontMetrics, largura: float) -> str:
    """O texto inteiro se couber em `largura`; senão, cortado com reticências.

    Mede com `horizontalAdvance`, e não com `elidedText`, por causa da armadilha
    registrada no §9.8: `elidedText` ignora o espaçamento entre letras, e os
    carimbos em caixa alta desta tela todos têm espaçamento. Lá ele devolveu
    88px para um teto de 76px e a primeira letra saiu cortada.
    """
    if largura <= 0:
        return ""
    if metricas.horizontalAdvance(texto) <= largura:
        return texto
    fim = len(texto)
    while fim > 0:
        fim -= 1
        candidato = texto[:fim].rstrip() + RETICENCIAS
        if metricas.horizontalAdvance(candidato) <= largura:
            return candidato
    return ""


def _fonte(base: QFont, pixels: int, *, negrito: bool = True, espacamento: float = 0.0) -> QFont:
    """Deriva a fonte de pintura da fonte da própria lista.

    Parte de `option.font` e não de um `QFont()` novo pela segunda armadilha do
    §9.8: a fonte que o QSS global aplica (Archivo Black) vence `setFont`, e
    medir com a fonte padrão do sistema daria outra largura que a pintada.
    """
    fonte = QFont(base)
    fonte.setPixelSize(pixels)
    fonte.setBold(negrito)
    if espacamento:
        fonte.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, espacamento)
    return fonte


def _moldura(
    pintor: QPainter,
    area: QRectF,
    fundo: QColor,
    borda: QColor,
    raio: float,
    *,
    cantos_em_cima: bool,
    cantos_embaixo: bool,
) -> None:
    """Um pedaço de cartão: o bloco inteiro é feito de linhas empilhadas.

    Cada linha desenha a sua fatia do mesmo retângulo arredondado. A que abre o
    bloco estende o retângulo para BAIXO e recorta, e sobram só os cantos de
    cima; a que fecha estende para cima; as do meio estendem para os dois lados
    e ficam só com as laterais. Empilhadas sem folga, as fatias formam um
    cartão contínuo, sem widget nenhum por trás.
    """
    estendida = QRectF(area)
    if not cantos_em_cima:
        estendida.setTop(area.top() - 2 * raio)
    if not cantos_embaixo:
        estendida.setBottom(area.bottom() + 2 * raio)
    pintor.save()
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setClipRect(QRectF(area.left() - 1.0, area.top(), area.width() + 2.0, area.height()))
    pintor.setPen(QPen(borda, 1.0))
    pintor.setBrush(fundo)
    pintor.drawRoundedRect(estendida.adjusted(0.5, 0.5, -0.5, -0.5), raio, raio)
    pintor.restore()


# ---------------------------------------------------------------------------
# Peças de tela
# ---------------------------------------------------------------------------


class InsigniaCardapio(QWidget):
    """A insígnia redonda como widget: os quatro KPIs e o cabeçalho do painel."""

    def __init__(self, glifo: str, lado: int = 40, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._glifo = glifo
        self.setObjectName("cardapioInsignia")
        self.setFixedSize(lado, lado)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        pintor = QPainter(self)
        desenhar_insignia(
            pintor, QRectF(self.rect()), self._glifo, ThemeController.instancia().tokens_atuais
        )
        pintor.end()


class GlifoSolto(QWidget):
    """Um glifo sem insígnia, na cor de um token — a lupa das buscas."""

    def __init__(
        self, glifo: str, lado: int, token: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._glifo = glifo
        self._token = token
        self.setObjectName("cardapioGlifo")
        self.setFixedSize(lado, lado)
        # O clique sobre a lupa tem que chegar ao campo de busca embaixo dela.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        cor = cor_do_token(ThemeController.instancia().tokens_atuais[self._token])
        pintor = QPainter(self)
        desenhar_glifo(pintor, self._glifo, QRectF(self.rect()), cor, espessura=2.0)
        pintor.end()


def campo_de_busca(texto_de_ajuda: str, parent: QWidget | None = None) -> QLineEdit:
    """O campo em cápsula com a lupa desenhada dentro.

    A lupa é FILHA do campo, e não um vizinho num quadro em volta dele (como
    no modal "Adicionar item"): assim o anel de foco é o `:focus` do próprio
    `QLineEdit` no QSS, sem `eventFilter` para instalar e desinstalar.
    """
    campo = QLineEdit(parent)
    campo.setObjectName("cardapioBusca")
    campo.setPlaceholderText(texto_de_ajuda)
    campo.setClearButtonEnabled(True)
    campo.setFixedHeight(40)
    lupa = GlifoSolto(GLIFO_LUPA, 15, "texto_fraquissimo", campo)
    lupa.move(15, (40 - 15) // 2)
    return campo


def divisor() -> QFrame:
    """A linha de 1px que separa as faixas dos dois painéis."""
    linha = QFrame()
    linha.setObjectName("cardapioDivisor")
    linha.setFixedHeight(1)
    return linha


class RotuloComReticencias(QLabel):
    """`QLabel` que encolhe cortando com reticências, em vez de cortar a letra.

    O `QLabel` comum pede a largura do texto inteiro como mínimo: o nome de um
    produto comprido no rodapé empurraria os botões para fora do painel, e o
    `QSplitter` resolveria espremendo alguém. Este aceita qualquer largura e
    encurta o texto para caber — medindo com a fonte do próprio rótulo, depois
    de polido, porque é a do QSS que pinta (§9.8).
    """

    def __init__(self, texto: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._completo = texto
        super().setText(texto)

    @nao_deixa_escapar()
    def setText(self, texto: str) -> None:  # noqa: N802 (override Qt)
        self._completo = texto
        self._encaixar()

    def texto_completo(self) -> str:
        return self._completo

    @nao_deixa_escapar(retorno=QSize(0, 0))
    def minimumSizeHint(self) -> QSize:  # noqa: N802 (override Qt)
        return QSize(0, super().minimumSizeHint().height())

    @nao_deixa_escapar()
    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (override Qt)
        super().resizeEvent(event)
        self._encaixar()

    def _encaixar(self) -> None:
        self.ensurePolished()
        largura = self.contentsRect().width()
        if largura <= 0:
            super().setText(self._completo)
            return
        super().setText(encurtar(self._completo, self.fontMetrics(), largura))


# ---------------------------------------------------------------------------
# A árvore da esquerda
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LinhaDeCategoria:
    """O que a linha de uma categoria desenha — sem ORM atrás."""

    nome: str
    subcategorias: int
    produtos: int
    ativa: bool

    @property
    def subtitulo(self) -> str:
        plural = "SUBCATEGORIA" if self.subcategorias == 1 else "SUBCATEGORIAS"
        texto = f"{self.subcategorias} {plural}"
        # Categoria desativada some do balcão junto com os produtos (§9.9): é a
        # única coisa da linha que muda o que se vende, então ela diz isso em
        # texto, e não só num tom mais apagado que ninguém interpreta.
        return texto if self.ativa else f"DESATIVADA · {texto}"


@dataclass(frozen=True, slots=True)
class LinhaDeSubdivisao:
    """Uma entrada dentro da categoria aberta: "Todas", uma subcategoria, ou
    "Sem subcategoria"."""

    rotulo: str
    total: int
    # A última filha fecha o cartão da categoria aberta: cantos de baixo
    # arredondados e o respiro antes da próxima categoria.
    ultima: bool


class DelegadoArvore(QStyledItemDelegate):
    """Pinta a árvore Categoria → Subcategoria como no mockup.

    A categoria aberta vira um cartão: a linha dela é o topo, as filhas são o
    corpo, e a última fecha. Uma guia vertical liga as filhas à seta da
    categoria, e a subdivisão escolhida é uma pílula no `acento`.
    """

    ALTURA_CATEGORIA_PX = 54
    ALTURA_FILHA_PX = 34
    # O fundo do cartão aberto abaixo da última filha, mais o respiro até a
    # próxima categoria.
    FUNDO_DO_CARTAO_PX = 7
    RESPIRO_PX = 5
    RAIO_PX = 12.0
    MARGEM_VERTICAL_PX = 3
    DIAMETRO_CONTADOR_PX = 24

    @nao_deixa_escapar()
    def paint(  # override Qt
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        linha = index.data(PAPEL_LINHA)
        tokens = ThemeController.instancia().tokens_atuais
        if isinstance(linha, LinhaDeCategoria):
            self._pintar_categoria(painter, option, index, linha, tokens)
        elif isinstance(linha, LinhaDeSubdivisao):
            self._pintar_filha(painter, option, linha, tokens)
        else:
            super().paint(painter, option, index)

    @nao_deixa_escapar(retorno=QSize(0, ALTURA_CATEGORIA_PX))
    def sizeHint(  # noqa: N802 (override Qt)
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        linha = index.data(PAPEL_LINHA)
        if isinstance(linha, LinhaDeSubdivisao):
            extra = self.FUNDO_DO_CARTAO_PX + self.RESPIRO_PX if linha.ultima else 0
            return QSize(0, self.ALTURA_FILHA_PX + extra)
        return QSize(0, self.altura_da_categoria(option.font))

    def altura_do_conteudo(self, fonte: QFont) -> int:
        """Nome + subtítulo + folga de dentro: o que a linha não pode cortar.

        A altura sai da fonte, e não só de uma constante: é o que faltava na
        lista antiga do §9.9, onde a linha de duas alturas era desenhada dentro
        da altura de uma e saía cortada ao meio.
        """
        nome = QFontMetrics(_fonte(fonte, 13)).height()
        sub = QFontMetrics(_fonte(fonte, 9, espacamento=1.2)).height()
        return nome + 3 + sub + 14

    def altura_da_categoria(self, fonte: QFont) -> int:
        return max(
            self.ALTURA_CATEGORIA_PX,
            self.altura_do_conteudo(fonte) + 2 * self.MARGEM_VERTICAL_PX,
        )

    def area_do_nome(self, retangulo: QRect) -> QRectF:
        """Onde o nome da categoria mora dentro da linha — o que sobra entre a
        seta e o contador. É isto que `test_o_nome_da_categoria_cabe` mede."""
        area = QRectF(retangulo).adjusted(2.0, 0.0, -2.0, 0.0)
        esquerda = area.left() + 38.0
        direita = area.right() - 12.0 - self.DIAMETRO_CONTADOR_PX - 10.0
        return QRectF(esquerda, area.top(), max(0.0, direita - esquerda), area.height())

    def _aberta(self, index: QModelIndex) -> bool:
        vista = self.parent()
        return isinstance(vista, QTreeView) and vista.isExpanded(index)

    def _pintar_categoria(
        self,
        pintor: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
        linha: LinhaDeCategoria,
        tokens: dict[str, str],
    ) -> None:
        aberta = self._aberta(index)
        realce = bool(
            option.state & (QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_Selected)
        )
        area = QRectF(option.rect).adjusted(2.0, float(self.MARGEM_VERTICAL_PX), -2.0, 0.0)
        conteudo = QRectF(area.left(), area.top(), area.width(), area.height() - self.MARGEM_VERTICAL_PX)
        borda = cor_do_token(tokens["cardapio_card_borda"])

        pintor.save()
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        if aberta:
            fundo = cor_do_token(tokens["cardapio_arvore_aberta_bg"])
            _moldura(pintor, area, fundo, borda, self.RAIO_PX, cantos_em_cima=True, cantos_embaixo=False)
            pintor.setPen(QPen(borda, 1.0))
            base = area.bottom() - 0.5
            pintor.drawLine(QPointF(area.left() + 1.0, base), QPointF(area.right() - 1.0, base))
        elif realce:
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(cor_do_token(tokens["cardapio_linha_hover_bg"]))
            pintor.drawRoundedRect(conteudo, self.RAIO_PX, self.RAIO_PX)

        meio_y = conteudo.center().y()
        cor_seta = tokens["acento"] if aberta else tokens["texto_fraquissimo"]
        desenhar_glifo(
            pintor,
            GLIFO_SETA_BAIXO if aberta else GLIFO_SETA_DIREITA,
            QRectF(conteudo.left() + 12.0, meio_y - 7.0, 14.0, 14.0),
            cor_do_token(cor_seta),
            espessura=2.4,
        )

        diametro = float(self.DIAMETRO_CONTADOR_PX)
        contador = QRectF(
            conteudo.right() - 12.0 - diametro, meio_y - diametro / 2.0, diametro, diametro
        )
        pintor.setPen(QPen(cor_do_token(tokens["cardapio_contador_borda"]), 1.0))
        pintor.setBrush(cor_do_token(tokens["cardapio_contador_bg"]))
        pintor.drawEllipse(contador.adjusted(0.5, 0.5, -0.5, -0.5))
        fonte_contador = _fonte(option.font, 10)
        pintor.setFont(fonte_contador)
        cor_contador = "cardapio_contador_texto" if linha.produtos else "texto_fraquissimo"
        pintor.setPen(cor_do_token(tokens[cor_contador]))
        pintor.drawText(contador, int(Qt.AlignmentFlag.AlignCenter), str(linha.produtos))

        nome_area = self.area_do_nome(option.rect)
        fonte_nome = _fonte(option.font, 13)
        fonte_sub = _fonte(option.font, 9, espacamento=1.2)
        metricas_nome, metricas_sub = QFontMetrics(fonte_nome), QFontMetrics(fonte_sub)
        altura_textos = metricas_nome.height() + 3 + metricas_sub.height()
        topo = meio_y - altura_textos / 2.0

        pintor.setFont(fonte_nome)
        pintor.setPen(cor_do_token(tokens["texto" if linha.ativa else "texto_fraquissimo"]))
        pintor.drawText(
            QRectF(nome_area.left(), topo, nome_area.width(), metricas_nome.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metricas_nome.elidedText(linha.nome, Qt.TextElideMode.ElideRight, int(nome_area.width())),
        )
        pintor.setFont(fonte_sub)
        pintor.setPen(cor_do_token(tokens["texto_fraquissimo"]))
        pintor.drawText(
            QRectF(
                nome_area.left(),
                topo + metricas_nome.height() + 3,
                nome_area.width(),
                metricas_sub.height(),
            ),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            encurtar(linha.subtitulo, metricas_sub, nome_area.width()),
        )
        pintor.restore()

    def _pintar_filha(
        self,
        pintor: QPainter,
        option: QStyleOptionViewItem,
        linha: LinhaDeSubdivisao,
        tokens: dict[str, str],
    ) -> None:
        selecionada = bool(option.state & QStyle.StateFlag.State_Selected)
        sob_o_mouse = bool(option.state & QStyle.StateFlag.State_MouseOver)
        area = QRectF(option.rect).adjusted(2.0, 0.0, -2.0, 0.0)
        faixa = QRectF(area.left(), area.top(), area.width(), float(self.ALTURA_FILHA_PX))
        if linha.ultima:
            corpo = QRectF(
                area.left(), area.top(), area.width(), faixa.height() + self.FUNDO_DO_CARTAO_PX
            )
        else:
            corpo = area
        borda = cor_do_token(tokens["cardapio_card_borda"])

        pintor.save()
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        _moldura(
            pintor,
            corpo,
            cor_do_token(tokens["cardapio_arvore_filhos_bg"]),
            borda,
            self.RAIO_PX,
            cantos_em_cima=False,
            cantos_embaixo=linha.ultima,
        )

        # A guia desce da seta da categoria e dá um "degrau" até cada filha.
        guia_x = area.left() + 19.0
        meio_y = faixa.center().y()
        pintor.setPen(QPen(cor_do_token(tokens["cardapio_arvore_guia"]), 1.0))
        fim_da_guia = meio_y if linha.ultima else faixa.bottom()
        pintor.drawLine(QPointF(guia_x, faixa.top()), QPointF(guia_x, fim_da_guia))
        pintor.drawLine(QPointF(guia_x, meio_y), QPointF(guia_x + 7.0, meio_y))

        pilula = QRectF(guia_x + 10.0, faixa.top() + 3.0, area.right() - 8.0 - (guia_x + 10.0), 28.0)
        if selecionada:
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(cor_do_token(tokens["acento"]))
            pintor.drawRoundedRect(pilula, 14.0, 14.0)
        elif sob_o_mouse:
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(cor_do_token(tokens["cardapio_linha_hover_bg"]))
            pintor.drawRoundedRect(pilula, 14.0, 14.0)

        fonte_total = _fonte(option.font, 10)
        metricas_total = QFontMetrics(fonte_total)
        texto_total = str(linha.total)
        largura_total = max(20.0, metricas_total.horizontalAdvance(texto_total) + 12.0)
        caixa_total = QRectF(pilula.right() - 5.0 - largura_total, pilula.center().y() - 9.0, largura_total, 18.0)
        if selecionada:
            # O contador ganha um fundo próprio dentro da pílula acesa — sem
            # ele o número se funde ao rótulo e vira "Guarnições3".
            tinta = cor_do_token(tokens["acento_texto"])
            tinta.setAlpha(34)
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(tinta)
            pintor.drawRoundedRect(caixa_total, 9.0, 9.0)
        pintor.setFont(fonte_total)
        cor_total = "acento_texto" if selecionada else "texto_fraquissimo"
        pintor.setPen(cor_do_token(tokens[cor_total]))
        pintor.drawText(caixa_total, int(Qt.AlignmentFlag.AlignCenter), texto_total)

        fonte_rotulo = _fonte(option.font, 12)
        metricas_rotulo = QFontMetrics(fonte_rotulo)
        texto_x = pilula.left() + 12.0
        largura_rotulo = max(0.0, caixa_total.left() - 6.0 - texto_x)
        pintor.setFont(fonte_rotulo)
        if selecionada:
            cor_rotulo = "acento_texto"
        elif sob_o_mouse:
            cor_rotulo = "texto"
        else:
            cor_rotulo = "texto_fraco"
        pintor.setPen(cor_do_token(tokens[cor_rotulo]))
        pintor.drawText(
            QRectF(texto_x, pilula.top(), largura_rotulo, pilula.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metricas_rotulo.elidedText(linha.rotulo, Qt.TextElideMode.ElideRight, int(largura_rotulo)),
        )
        pintor.restore()


# ---------------------------------------------------------------------------
# A lista de produtos da direita
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FotoProduto:
    """O instantâneo de um produto: tudo o que a linha pinta, já formatado.

    `busca` é o texto que o campo "Buscar produto" casa — nome + subcategoria,
    já normalizado, para a digitação não normalizar nem tocar o banco.
    """

    produto_id: int
    nome: str
    preco_texto: str
    custo_texto: str
    margem: float
    ativo: bool
    # Os selos ao lado do nome ("COMBO", "DESATIVADO"). A subcategoria NÃO é
    # um deles, e isto é de propósito desde o §9.9: quem diz a subdivisão é o
    # cabeçalho do bloco, uma vez, e não cada linha.
    selos: tuple[str, ...]
    imagem_path: str | None
    busca: str

    @property
    def margem_texto(self) -> str:
        return f"{self.margem:.0f}%"


@dataclass(frozen=True, slots=True)
class FotoGrupo:
    """Uma subdivisão e os produtos dela — um bloco na lista."""

    rotulo: str
    # A chave de seleção da árvore: o nome da subcategoria, ou a chave
    # especial de "Sem subcategoria". É o que o link "Editar subcategoria"
    # devolve para a árvore saber qual abrir.
    chave: str
    # "Sem subcategoria" não é uma subcategoria cadastrada: não tem o que editar.
    editavel: bool
    produtos: tuple[FotoProduto, ...]

    @property
    def contagem_texto(self) -> str:
        total = len(self.produtos)
        return f"{total} {'PRODUTO' if total == 1 else 'PRODUTOS'}"


class TipoDeItem(Enum):
    CABECALHO = "cabecalho"
    PRODUTO = "produto"
    VAZIO = "vazio"
    ESPACO = "espaco"


@dataclass(frozen=True, slots=True)
class ItemDaLista:
    """Uma linha da lista de produtos, com o lugar dela dentro do bloco.

    `abre`/`fecha` dizem se a linha arredonda em cima ou embaixo. São
    calculados DEPOIS da busca: se o último produto de um bloco é filtrado, a
    linha de cima é que passa a fechar o cartão.
    """

    tipo: TipoDeItem
    grupo: FotoGrupo | None = None
    produto: FotoProduto | None = None
    abre: bool = False
    fecha: bool = False
    texto: str = ""


def montar_itens(
    grupos: list[FotoGrupo],
    termo: str,
    *,
    com_cabecalho: bool,
    normalizar: Callable[[str], str],
    texto_vazio: str,
) -> list[ItemDaLista]:
    """Os blocos da lista, já filtrados pela busca e com a posição de cada linha.

    Função pura — sem Qt e sem banco — para a composição da lista poder ser
    testada inteira sem desenhar nada.

    * Cada grupo vira um bloco: cabeçalho (quando a categoria tem subdivisões),
      os produtos, e um espaço antes do bloco seguinte.
    * Um grupo que a busca esvaziou some junto com o cabeçalho: um "GUARNIÇÕES
      · 3 PRODUTOS" sem nada embaixo pareceria um defeito.
    * Um grupo vazio SEM busca aparece com um aviso: é a subcategoria recém-
      criada, e "está aqui, sem itens ainda" é diferente de "não existe".
    """
    # `normalizar` vem de fora (é a `chave_de_agrupamento` de `services/texto`)
    # para esta função não importar service nenhum: a regra de "podrao" casar
    # com "Podrão" é uma só no app, e mora lá.
    alvo = normalizar(termo) if termo.strip() else ""
    itens: list[ItemDaLista] = []
    for grupo in grupos:
        visiveis = [p for p in grupo.produtos if not alvo or alvo in p.busca]
        if alvo and not visiveis:
            continue
        if itens:
            itens.append(ItemDaLista(TipoDeItem.ESPACO))
        if com_cabecalho:
            itens.append(ItemDaLista(TipoDeItem.CABECALHO, grupo=grupo, abre=True))
        if not visiveis:
            itens.append(
                ItemDaLista(
                    TipoDeItem.VAZIO,
                    grupo=grupo,
                    abre=not com_cabecalho,
                    fecha=True,
                    texto="NENHUM PRODUTO NESTA SUBCATEGORIA AINDA"
                    if com_cabecalho
                    else texto_vazio,
                )
            )
            continue
        for posicao, produto in enumerate(visiveis):
            itens.append(
                ItemDaLista(
                    TipoDeItem.PRODUTO,
                    grupo=grupo,
                    produto=produto,
                    abre=posicao == 0 and not com_cabecalho,
                    fecha=posicao == len(visiveis) - 1,
                )
            )
    if not itens:
        texto = f"NENHUM PRODUTO ENCONTRADO PARA “{termo.strip()}”" if alvo else texto_vazio
        itens.append(ItemDaLista(TipoDeItem.VAZIO, abre=True, fecha=True, texto=texto))
    return itens


class _Colunas:
    """As colunas de uma linha de produto, da direita para a esquerda.

    Calculadas da largura real da linha, em degraus: se o nome ficaria abaixo
    do piso, o CUSTO sai de cena; se ainda assim não couber, sai a BARRA de
    margem (o percentual fica, que é o número). O nome é o que se procura na
    linha e é o último a perder espaço — e nunca invade o preço.
    """

    __slots__ = ("miniatura", "nome", "preco", "custo", "barra", "percentual")

    def __init__(
        self,
        area: QRectF,
        fontes: dict[str, QFont],
        lado_miniatura: float,
        nome_minimo: float,
    ) -> None:
        largura_pct = QFontMetrics(fontes["percentual"]).horizontalAdvance("100%") + 2.0
        largura_preco = QFontMetrics(fontes["preco"]).horizontalAdvance("R$ 999,99") + 2.0
        largura_custo = QFontMetrics(fontes["custo"]).horizontalAdvance("R$ 999,99") + 2.0

        self.miniatura = QRectF(
            area.left() + 16.0,
            area.center().y() - lado_miniatura / 2.0,
            lado_miniatura,
            lado_miniatura,
        )
        direita = area.right() - 14.0
        self.percentual = QRectF(direita - largura_pct, area.top(), largura_pct, area.height())
        largura_barra = max(56.0, min(120.0, area.width() * 0.16))

        self._distribuir(area, largura_barra, largura_custo, largura_preco)
        if self.nome.width() < nome_minimo:
            self._distribuir(area, largura_barra, 0.0, largura_preco)
        if self.nome.width() < nome_minimo:
            self._distribuir(area, 0.0, 0.0, largura_preco)

    def _distribuir(
        self, area: QRectF, largura_barra: float, largura_custo: float, largura_preco: float
    ) -> None:
        """Encaixa barra, custo, preço e nome — coluna de largura zero some."""
        cursor = self.percentual.left()
        if largura_barra > 0:
            cursor -= 10.0 + largura_barra
        self.barra = QRectF(cursor, area.center().y() - 3.0, largura_barra, 6.0)
        if largura_custo > 0:
            cursor -= 16.0 + largura_custo
        self.custo = QRectF(cursor, area.top(), largura_custo, area.height())
        cursor -= 18.0 + largura_preco
        self.preco = QRectF(cursor, area.top(), largura_preco, area.height())
        inicio_nome = self.miniatura.right() + 12.0
        self.nome = QRectF(
            inicio_nome, area.top(), max(0.0, self.preco.left() - 16.0 - inicio_nome), area.height()
        )


class DelegadoProdutos(QStyledItemDelegate):
    """Pinta a lista da direita: blocos por subcategoria, linhas de produto.

    Não há widget em linha nenhuma. O bloco é desenhado em fatias
    (`_moldura`), a miniatura sai pronta do `thumbnail_cache`, e a barra de
    margem é um retângulo — o que o `_BarraMargem` antigo fazia com dois
    `QFrame` por produto.
    """

    ALTURA_ESPACO_PX = 14
    ALTURA_CABECALHO_PX = 58
    ALTURA_PRODUTO_PX = 60
    ALTURA_VAZIO_PX = 52
    RAIO_PX = 12.0
    LADO_MINIATURA_PX = 36
    LADO_INSIGNIA_PX = 32
    # Abaixo disto o nome do produto vira duas letras e reticências: é o piso
    # que faz custo e barra saírem da linha antes (ver `_Colunas`).
    NOME_MINIMO_PX = 90
    TEXTO_LINK = "Editar subcategoria"

    _ALTURAS = {
        TipoDeItem.ESPACO: ALTURA_ESPACO_PX,
        TipoDeItem.CABECALHO: ALTURA_CABECALHO_PX,
        TipoDeItem.PRODUTO: ALTURA_PRODUTO_PX,
        TipoDeItem.VAZIO: ALTURA_VAZIO_PX,
    }

    @nao_deixa_escapar()
    def paint(  # override Qt
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        item = index.data(PAPEL_LINHA)
        if not isinstance(item, ItemDaLista):
            super().paint(painter, option, index)
            return
        if item.tipo is TipoDeItem.ESPACO:
            return
        tokens = ThemeController.instancia().tokens_atuais
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if item.tipo is TipoDeItem.CABECALHO:
            self._pintar_cabecalho(painter, option, index, item, tokens)
        elif item.tipo is TipoDeItem.PRODUTO:
            self._pintar_produto(painter, option, item, tokens)
        else:
            self._pintar_vazio(painter, option, item, tokens)
        painter.restore()

    @nao_deixa_escapar(retorno=QSize(0, ALTURA_PRODUTO_PX))
    def sizeHint(  # noqa: N802 (override Qt)
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        item = index.data(PAPEL_LINHA)
        tipo = item.tipo if isinstance(item, ItemDaLista) else TipoDeItem.PRODUTO
        # Largura zero: em modo lista a vista estica o item até a borda, e uma
        # largura própria só criaria rolagem horizontal sem conteúdo.
        return QSize(0, self._ALTURAS[tipo])

    # -- geometria exposta (para a lista e para os testes) --------------------

    def retangulo_do_link(self, linha: QRect, fonte: QFont) -> QRect:
        """A área clicável de "Editar subcategoria" dentro do cabeçalho."""
        metricas = QFontMetrics(_fonte(fonte, 11))
        largura = metricas.horizontalAdvance(self.TEXTO_LINK)
        direita = linha.right() - 16
        return QRect(direita - largura - 6, linha.center().y() - 13, largura + 12, 26)

    def colunas(self, linha: QRect, fonte: QFont) -> _Colunas:
        return self._colunas(QRectF(linha), self._fontes(fonte))

    def _colunas(self, area: QRectF, fontes: dict[str, QFont]) -> _Colunas:
        return _Colunas(
            area, fontes, float(self.LADO_MINIATURA_PX), float(self.NOME_MINIMO_PX)
        )

    def nome_visivel(self, produto: FotoProduto, linha: QRect, fonte: QFont) -> str:
        """O nome como ele sai na linha — inteiro, ou encurtado com reticências."""
        fontes = self._fontes(fonte)
        largura = self._largura_do_nome(produto, self.colunas(linha, fonte), fontes)
        return QFontMetrics(fontes["nome"]).elidedText(
            produto.nome, Qt.TextElideMode.ElideRight, int(largura)
        )

    # -- pintura ---------------------------------------------------------------

    @staticmethod
    def _fontes(base: QFont) -> dict[str, QFont]:
        return {
            "nome": _fonte(base, 13),
            "preco": _fonte(base, 13),
            "custo": _fonte(base, 12, negrito=False),
            "percentual": _fonte(base, 11),
            "selo": _fonte(base, 8, espacamento=1.0),
            "titulo": _fonte(base, 14),
            "contagem": _fonte(base, 9, espacamento=1.4),
            "link": _fonte(base, 11),
            "aviso": _fonte(base, 9, espacamento=1.4),
        }

    def _pintar_cabecalho(
        self,
        pintor: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
        item: ItemDaLista,
        tokens: dict[str, str],
    ) -> None:
        area = QRectF(option.rect)
        borda = cor_do_token(tokens["cardapio_bloco_borda"])
        _moldura(
            pintor,
            area,
            cor_do_token(tokens["cardapio_bloco_topo_bg"]),
            borda,
            self.RAIO_PX,
            cantos_em_cima=True,
            cantos_embaixo=False,
        )
        pintor.setPen(QPen(borda, 1.0))
        base = area.bottom() - 0.5
        pintor.drawLine(QPointF(area.left() + 1.0, base), QPointF(area.right() - 1.0, base))

        lado = float(self.LADO_INSIGNIA_PX)
        desenhar_insignia(
            pintor,
            QRectF(area.left() + 16.0, area.center().y() - lado / 2.0, lado, lado),
            GLIFO_ETIQUETA,
            tokens,
        )

        grupo = item.grupo
        fontes = self._fontes(option.font)
        texto_x = area.left() + 16.0 + lado + 12.0
        link = QRectF(self.retangulo_do_link(option.rect, option.font))
        limite = (link.left() - 12.0) if grupo is not None and grupo.editavel else area.right() - 16.0
        largura = max(0.0, limite - texto_x)

        metricas_titulo = QFontMetrics(fontes["titulo"])
        metricas_contagem = QFontMetrics(fontes["contagem"])
        altura = metricas_titulo.height() + 2 + metricas_contagem.height()
        topo = area.center().y() - altura / 2.0
        pintor.setFont(fontes["titulo"])
        pintor.setPen(cor_do_token(tokens["texto"]))
        pintor.drawText(
            QRectF(texto_x, topo, largura, metricas_titulo.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metricas_titulo.elidedText(
                grupo.rotulo if grupo else "", Qt.TextElideMode.ElideRight, int(largura)
            ),
        )
        pintor.setFont(fontes["contagem"])
        pintor.setPen(cor_do_token(tokens["texto_fraquissimo"]))
        pintor.drawText(
            QRectF(texto_x, topo + metricas_titulo.height() + 2, largura, metricas_contagem.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            encurtar(grupo.contagem_texto if grupo else "", metricas_contagem, largura),
        )

        if grupo is not None and grupo.editavel:
            vista = self.parent()
            aceso = getattr(vista, "linha_do_link_sob_o_mouse", -1) == index.row()
            pintor.setFont(fontes["link"])
            pintor.setPen(cor_do_token(tokens["acento" if aceso else "texto_fraco"]))
            pintor.drawText(link, int(Qt.AlignmentFlag.AlignCenter), self.TEXTO_LINK)

    def _largura_do_nome(
        self, produto: FotoProduto, colunas: _Colunas, fontes: dict[str, QFont]
    ) -> float:
        """O que sobra para o nome depois dos selos que vão ao lado dele."""
        metricas_selo = QFontMetrics(fontes["selo"])
        ocupado = sum(metricas_selo.horizontalAdvance(s) + 12.0 + 6.0 for s in produto.selos)
        return max(0.0, colunas.nome.width() - ocupado)

    def _pintar_produto(
        self,
        pintor: QPainter,
        option: QStyleOptionViewItem,
        item: ItemDaLista,
        tokens: dict[str, str],
    ) -> None:
        produto = item.produto
        if produto is None:
            return
        area = QRectF(option.rect)
        selecionada = bool(option.state & QStyle.StateFlag.State_Selected)
        sob_o_mouse = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selecionada:
            fundo = cor_do_token(tokens["cardapio_linha_selecionada_bg"])
        elif sob_o_mouse:
            fundo = cor_do_token(tokens["cardapio_linha_hover_bg"])
        else:
            fundo = cor_do_token(tokens["cardapio_bloco_bg"])
        _moldura(
            pintor,
            area,
            fundo,
            cor_do_token(tokens["cardapio_bloco_borda"]),
            self.RAIO_PX,
            cantos_em_cima=item.abre,
            cantos_embaixo=item.fecha,
        )
        if not item.fecha:
            pintor.setPen(QPen(cor_do_token(tokens["cardapio_bloco_divisor"]), 1.0))
            base = area.bottom() - 0.5
            pintor.drawLine(QPointF(area.left() + 1.0, base), QPointF(area.right() - 1.0, base))
        if selecionada:
            # A barra âmbar diz QUAL linha o Editar/Excluir do rodapé vão pegar.
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(cor_do_token(tokens["acento"]))
            pintor.drawRoundedRect(
                QRectF(area.left() + 1.5, area.top() + 14.0, 3.0, area.height() - 28.0), 1.5, 1.5
            )

        fontes = self._fontes(option.font)
        colunas = self._colunas(area, fontes)
        lado = self.LADO_MINIATURA_PX
        if not produto.ativo:
            pintor.setOpacity(0.45)
        pintor.drawPixmap(colunas.miniatura.topLeft(), obter_pixmap(produto.imagem_path, lado, produto.nome))
        pintor.setOpacity(1.0)

        # Nome e selos.
        metricas_nome = QFontMetrics(fontes["nome"])
        largura_nome = self._largura_do_nome(produto, colunas, fontes)
        nome = metricas_nome.elidedText(produto.nome, Qt.TextElideMode.ElideRight, int(largura_nome))
        pintor.setFont(fontes["nome"])
        pintor.setPen(cor_do_token(tokens["texto" if produto.ativo else "texto_fraquissimo"]))
        pintor.drawText(
            QRectF(colunas.nome.left(), area.top(), largura_nome, area.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            nome,
        )
        selo_x = colunas.nome.left() + metricas_nome.horizontalAdvance(nome) + 8.0
        metricas_selo = QFontMetrics(fontes["selo"])
        pintor.setFont(fontes["selo"])
        for selo in produto.selos:
            largura = metricas_selo.horizontalAdvance(selo) + 12.0
            caixa = QRectF(selo_x, area.center().y() - 8.0, largura, 16.0)
            familia = "badge_combo" if selo == "COMBO" else "badge_desativado"
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(cor_do_token(tokens[f"{familia}_bg"]))
            pintor.drawRoundedRect(caixa, 4.0, 4.0)
            pintor.setPen(cor_do_token(tokens[f"{familia}_texto"]))
            pintor.drawText(caixa, int(Qt.AlignmentFlag.AlignCenter), selo)
            selo_x += largura + 6.0

        direita_e_centro = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        pintor.setFont(fontes["preco"])
        pintor.setPen(cor_do_token(tokens["texto" if produto.ativo else "texto_fraquissimo"]))
        pintor.drawText(colunas.preco, direita_e_centro, produto.preco_texto)
        if colunas.custo.width() > 0:
            pintor.setFont(fontes["custo"])
            pintor.setPen(cor_do_token(tokens["texto_fraquissimo"]))
            pintor.drawText(colunas.custo, direita_e_centro, produto.custo_texto)

        # Barra de margem: trilho + preenchimento proporcional (0 a 100%). Numa
        # linha estreita demais ela sai (largura zero) e fica só o percentual.
        if colunas.barra.width() > 0:
            pintor.setPen(Qt.PenStyle.NoPen)
            pintor.setBrush(cor_do_token(tokens["cardapio_margem_trilho"]))
            pintor.drawRoundedRect(colunas.barra, 3.0, 3.0)
            proporcao = max(0.0, min(100.0, produto.margem)) / 100.0
            if proporcao > 0:
                cheia = QRectF(colunas.barra)
                cheia.setWidth(max(6.0, colunas.barra.width() * proporcao))
                pintor.setBrush(cor_do_token(tokens["cardapio_margem"]))
                pintor.drawRoundedRect(cheia, 3.0, 3.0)
        # Margem negativa é produto vendido no prejuízo: a barra fica vazia e o
        # número sai no vermelho de alerta, que é a leitura que interessa.
        pintor.setFont(fontes["percentual"])
        cor_pct = "perigo" if produto.margem < 0 else "texto"
        pintor.setPen(cor_do_token(tokens[cor_pct]))
        pintor.drawText(colunas.percentual, direita_e_centro, produto.margem_texto)

    def _pintar_vazio(
        self,
        pintor: QPainter,
        option: QStyleOptionViewItem,
        item: ItemDaLista,
        tokens: dict[str, str],
    ) -> None:
        area = QRectF(option.rect)
        _moldura(
            pintor,
            area,
            cor_do_token(tokens["cardapio_bloco_bg"]),
            cor_do_token(tokens["cardapio_bloco_borda"]),
            self.RAIO_PX,
            cantos_em_cima=item.abre,
            cantos_embaixo=item.fecha,
        )
        fonte = self._fontes(option.font)["aviso"]
        pintor.setFont(fonte)
        pintor.setPen(cor_do_token(tokens["texto_fraquissimo"]))
        largura = area.width() - 32.0
        pintor.drawText(
            QRectF(area.left() + 16.0, area.top(), largura, area.height()),
            int(Qt.AlignmentFlag.AlignCenter),
            encurtar(item.texto, QFontMetrics(fonte), largura),
        )


class ListaDeProdutos(QListWidget):
    """A lista da direita: um `QListWidget` com o delegado e o link do bloco.

    Os cabeçalhos, os espaços e os avisos entram **sem flag nenhuma**: não são
    selecionáveis nem habilitados, e é isso que faz a seta do teclado pular por
    cima deles (o `QListView` salta linha desabilitada) e o clique neles não
    desmarcar o produto escolhido.
    """

    editar_subcategoria_pedida = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cardapioProdutos")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setUniformItemSizes(False)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        # Filho da lista de propósito: `setItemDelegate` NÃO toma posse, e sem
        # parent o delegado morreria com o nome Python enquanto o Qt ainda o
        # chamasse para pintar (mesma nota do modal "Adicionar item").
        self._delegado = DelegadoProdutos(self)
        self.setItemDelegate(self._delegado)
        # Linha do cabeçalho cujo link está sob o mouse (-1 = nenhuma). Lido
        # pelo delegado para acender o "Editar subcategoria".
        self.linha_do_link_sob_o_mouse = -1

    def delegado(self) -> DelegadoProdutos:
        return self._delegado

    def definir_itens(
        self, itens: list[ItemDaLista], *, selecionar: int | None, rolagem: int
    ) -> None:
        """Troca o conteúdo inteiro, devolvendo seleção e rolagem ao lugar.

        A seleção volta pelo **id do produto**, e não pelo número da linha: a
        lista agrupada tem cabeçalhos no meio, e um produto novo cadastrado
        antes do escolhido deslocaria o índice — a seleção pularia para o
        vizinho. Os sinais ficam bloqueados pelo trecho inteiro, então quem
        escuta não vê a seleção vazia que existe entre o `clear()` e a volta
        (`test_cardapio_nao_avisa_selecao_vazia_durante_o_refresh`).

        `clear()` destrói os itens de verdade: são objetos C++ sem widget
        nenhum pendurado, e o instantâneo que cada um carregava é solto junto.
        """
        bloqueado = self.blockSignals(True)
        try:
            self.clear()
            self.linha_do_link_sob_o_mouse = -1
            alvo: QListWidgetItem | None = None
            for dado in itens:
                item = QListWidgetItem()
                item.setData(PAPEL_LINHA, dado)
                if dado.tipo is TipoDeItem.PRODUTO and dado.produto is not None:
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    produto = dado.produto
                    item.setToolTip(
                        f"{produto.nome}\nPreço {produto.preco_texto} · "
                        f"Custo {produto.custo_texto} · Margem {produto.margem_texto}"
                    )
                    if produto.produto_id == selecionar:
                        alvo = item
                else:
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.addItem(item)
            if alvo is not None:
                self.setCurrentItem(alvo)
            # Linha DEFENSIVA, e o registro é honesto sobre isso: o layout do
            # `QListView` é preguiçoso, e o alcance que a barra guarda depois
            # do `clear()` é um detalhe interno do Qt. Nesta lista ele
            # sobrevive intacto (medido: 1359 antes e depois); numa lista solta
            # do mesmo Qt ele caiu e cortou a rolagem pedida (452 de 1052px).
            # Forçar o layout aqui não custa nada — é o mesmo cálculo que o Qt
            # faria antes da próxima pintura, só que antes — e tira a volta da
            # rolagem da dependência desse detalhe. A conferência por mutação
            # do §9.11 não consegue reprová-la, e está registrado por quê.
            self.doItemsLayout()
            self.verticalScrollBar().setValue(rolagem)
        finally:
            self.blockSignals(bloqueado)

    def item_da_linha(self, linha: int) -> ItemDaLista | None:
        item = self.item(linha)
        dado = item.data(PAPEL_LINHA) if item is not None else None
        return dado if isinstance(dado, ItemDaLista) else None

    def produto_selecionado(self) -> FotoProduto | None:
        for item in self.selectedItems():
            dado = item.data(PAPEL_LINHA)
            if isinstance(dado, ItemDaLista) and dado.produto is not None:
                return dado.produto
        return None

    def _link_em(self, posicao: QPoint) -> ItemDaLista | None:
        """O cabeçalho cujo link está sob `posicao`, ou `None`."""
        indice = self.indexAt(posicao)
        if not indice.isValid():
            return None
        dado = indice.data(PAPEL_LINHA)
        if not (
            isinstance(dado, ItemDaLista)
            and dado.tipo is TipoDeItem.CABECALHO
            and dado.grupo is not None
            and dado.grupo.editavel
        ):
            return None
        retangulo = self._delegado.retangulo_do_link(self.visualRect(indice), self.font())
        return dado if retangulo.contains(posicao) else None

    @nao_deixa_escapar()
    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        posicao = event.position().toPoint()
        linha = self.indexAt(posicao).row() if self._link_em(posicao) is not None else -1
        if linha != self.linha_do_link_sob_o_mouse:
            anterior = self.linha_do_link_sob_o_mouse
            self.linha_do_link_sob_o_mouse = linha
            for alvo in (anterior, linha):
                if alvo >= 0 and self.item(alvo) is not None:
                    self.viewport().update(self.visualItemRect(self.item(alvo)))
            if linha >= 0:
                self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    @nao_deixa_escapar()
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            dado = self._link_em(event.position().toPoint())
            if dado is not None and dado.grupo is not None:
                event.accept()
                self.editar_subcategoria_pedida.emit(dado.grupo.chave)
                return
        super().mouseReleaseEvent(event)
