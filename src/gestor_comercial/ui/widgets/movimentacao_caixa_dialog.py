"""Modal único de movimentação manual da gaveta: sangria, reforço e despesa.

Substitui o `_MovimentoDialog` que morava dentro de `caixa_view.py` — dois
`QLineEdit` num `QFormLayout` com a moldura de janela do sistema, onde o valor
era **digitado como texto** (`"50,00"`, `"R$ 50"`, `"50.00"`) e depois lido de
volta por `safe_decimal`. No balcão do food truck aquilo era a interação errada
pelo mesmo motivo do modal de PIN e do de lançar item (§9.4): quem opera está de
pé, com a mão ocupada, e o teclado físico fica atrás do monitor.

Aqui é **uma classe só**, parametrizada por `TipoMovimento`. Sangria, reforço e
despesa não são três telas: são a mesma tela — valor, descrição, confirmar — com
ícone, texto e sugestões diferentes. Três classes (ou três `if tipo is ...`
espalhados) seriam a repetição que `test_paineis_de_relatorio.py` reprova, e o
que se copiaria não é decoração: é o **acumulador de centavos** e o **ciclo de
vida**, as duas coisas que quebram em silêncio.

## O que NÃO mudou

**Nenhuma regra financeira, e nenhuma gravação nova.** O diálogo não conhece
`CaixaService`: ele coleta um `DadosMovimento` (valor + descrição) e a
`CaixaView` chama `registrar_movimento(tipo, valor, descricao)` exatamente como
antes — mesma assinatura, mesmo tipo, mesma ordem. Quem exige gerente para
sangria e despesa continua sendo o service (§3.1, via `AuthService.exigir_gerente`),
quem recusa valor menor ou igual a zero continua sendo o service, e o erro que
ele levantar continua aparecendo na linha de erro da tela de trás. Este modal
não abriu caminho novo para o banco; abriu uma porta melhor para o caminho que
já existia.

O `Decimal` que sai daqui passa por `dinheiro()` (via `formatacao`/`ZERO`) como
todo dinheiro do sistema, e o texto do visor sai de `formatar_reais` — o mesmo
`R$ 1.234,50` do resto do app e do cupom impresso (§3.8).

## Por que centavos inteiros, e não texto de campo

O visor é um `int` de centavos que cresce pela direita, como máquina de cartão:
digitar `5`, `0`, `0`, `0` mostra `R$ 0,05` → `R$ 0,50` → `R$ 5,00` → `R$ 50,00`.
Isso apaga uma classe inteira de defeito que o modal antigo tinha: não existe
mais "valor ilegível". `safe_decimal` continua existindo e continua certo, mas
ele resolve o problema de **ler** o que foi digitado — e aqui não há o que ler,
porque nunca houve texto.

A conta e o teclado que a alimenta **não moram mais neste arquivo**: saíram
para `teclado_numerico.py` no §9.7, quando a abertura e o fechamento do caixa
ganharam o mesmo numpad e a quarta cópia do laço `novo = novo * 10 + dígito`
ficaria pendurada em quatro telas que gravam dinheiro. O teto continua vindo de
`dinheiro.LIMITE`, pelo mesmo motivo de sempre: assim o numpad não consegue
montar um valor que o service recusaria com `ValueError` — que, por não estar
em `_ERROS_SERVICE`, subiria como estouro em vez de virar mensagem na tela.

## Ciclo de vida (o RNF do Celeron, e §3.2/§3.9/§3.14)

O briefing pediu, no vocabulário do Tkinter, `destroy()` + `unbind()` +
`after_cancel` ao fechar. Em PySide6 os três equivalentes estão aqui, e todos
passam por `done()` — o único portão por onde saem o Confirmar, o Cancelar, o ✕
e o Esc:

* **destroy** — `executar_modal()` (§3.2) faz o `deleteLater()` do diálogo
  depois de ler o resultado, e com ele vão os filhos, em C++. O que `done()`
  acrescenta é soltar o **escurecedor**, que é filho da janela principal e não
  do diálogo: sem isso, um turno de sangrias e reforços deixaria uma pilha de
  retângulos pretos invisíveis pendurada no `MainWindow`, que vive o processo
  inteiro;
* **unbind** — há um `eventFilter` instalado no campo de descrição (é ele que
  faz o `Tab` voltar para o visor, ver §"Teclado"), e `done()` o remove
  explicitamente. `QShortcut` não existe: o teclado é lido no `keyPressEvent` do
  próprio diálogo, que morre com ele;
* **after_cancel** — não há timer nenhum, e isso é decisão, não descuido. O
  visor é recalculado na tecla (uma formatação de `Decimal`), não há busca a
  agrupar e nada é agendado. Não há `after_cancel` a fazer porque não há
  `after`.

Sinal nenhum é ligado por `lambda` (§3.14): as teclas do numpad, os atalhos de
valor e os chips de descrição entram todos por método ligado, e quem disparou
sai do `sender()`. `lambda` captura `self`, a conexão vive no botão, o botão é
filho do diálogo — e o ciclo se fecha sem ninguém para desfazê-lo.

## Teclado

O balcão tem teclado numérico USB, e ele tem que fazer o mesmo que o dedo na
tela: `0`-`9` e o numpad alimentam o visor, `Backspace` apaga o último dígito,
`Enter` confirma (se o valor for maior que zero), `Esc` fecha sem gravar e `Tab`
alterna entre o visor e o campo de descrição.

O `Tab` precisa dos dois lados porque só existem dois destinos de foco e um
deles é o próprio diálogo, que tem `FocusPolicy.NoFocus` (como todo modal em
cartão daqui — ver `cartao_modal.preparar_botao`): a navegação natural do Qt
pularia o diálogo e o `Tab` não faria nada. Então o diálogo manda o foco para o
campo, e o `eventFilter` do campo o manda de volta.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPainterPath, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.domain.enums import TipoMovimento
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.flow_layout import FlowLayout
from gestor_comercial.ui.widgets.teclado_numerico import (
    AcumuladorDeCentavos,
    TecladoNumerico,
)

# Desenhos possíveis do badge do cabeçalho (ver `_IconeMovimento`). São nomes
# de forma, e não de operação, porque é a forma que o `QPainter` escolhe.
GLIFO_SAIDA = "saida"
GLIFO_ENTRADA = "entrada"
GLIFO_RECIBO = "recibo"


@dataclass(frozen=True, slots=True)
class Operacao:
    """Tudo o que separa uma sangria de um reforço — numa linha só.

    `papel` é a chave que o QSS lê (`[operacao="sangria"]`), e `token_tinta` /
    `token_glifo` são os nomes dos tokens de tema que o badge usa. Ficam aqui,
    e não montados por f-string na hora de pintar, porque uma chave inventada
    estouraria `KeyError` dentro de um `paintEvent` — que, blindado por
    `nao_deixa_escapar`, simplesmente não desenharia nada e não avisaria
    ninguém. Como nome de token, `test_movimentacao_caixa_dialog.py` confere os
    seis contra as duas paletas.
    """

    tipo: TipoMovimento
    papel: str
    titulo: str
    subtitulo: str
    rotulo_confirmar: str
    placeholder: str
    tags: tuple[str, ...]
    glifo: str
    token_tinta: str
    token_glifo: str


# As três movimentações **manuais** da gaveta, na ordem em que aparecem na tela
# de Caixa. `CONSUMO_FUNCIONARIO` fica de fora de propósito: `registrar_movimento`
# o recusa (consumo interno já é rastreado como pagamento da comanda, e um
# movimento manual descontaria a mesma dívida duas vezes), então oferecer um
# botão para ele seria oferecer um erro.
#
# É a MESMA lista que a tela de Caixa lê para o rótulo do botão ("+ Sangria") e
# para o badge da tabela de movimentos. Enquanto eram três dicionários paralelos
# lá dentro (`_ROTULOS_TIPO_MOVIMENTO`, `_TIPO_BADGE` e o de variante), "Reforço"
# precisava estar certo em três lugares ao mesmo tempo — é o mesmo remédio que o
# §9.5 aplicou em `CARGOS`.
OPERACOES: dict[TipoMovimento, Operacao] = {
    TipoMovimento.SANGRIA: Operacao(
        tipo=TipoMovimento.SANGRIA,
        papel="sangria",
        titulo="Sangria",
        subtitulo="Retirada de dinheiro da gaveta para o cofre.",
        rotulo_confirmar="Confirmar sangria",
        placeholder="Ex.: troco para o malote",
        tags=("Envio ao cofre", "Troco para o malote", "Retirada do gerente"),
        glifo=GLIFO_SAIDA,
        token_tinta="mov_sangria_tinta",
        token_glifo="mov_sangria_glifo",
    ),
    TipoMovimento.REFORCO: Operacao(
        tipo=TipoMovimento.REFORCO,
        papel="reforco",
        titulo="Reforço",
        subtitulo="Entrada de troco ou suprimento na gaveta.",
        rotulo_confirmar="Confirmar reforço",
        placeholder="Ex.: troco inicial do turno",
        tags=("Troco inicial", "Aporte de moedas", "Suprimento extra"),
        glifo=GLIFO_ENTRADA,
        token_tinta="mov_reforco_tinta",
        token_glifo="mov_reforco_glifo",
    ),
    TipoMovimento.DESPESA: Operacao(
        tipo=TipoMovimento.DESPESA,
        papel="despesa",
        titulo="Despesa",
        subtitulo="Pagamento imediato de despesa com o saldo da gaveta.",
        rotulo_confirmar="Confirmar despesa",
        placeholder="Ex.: compra de gelo",
        tags=("Compra de gelo", "Gás de cozinha", "Hortifrúti urgente", "Manutenção"),
        glifo=GLIFO_RECIBO,
        token_tinta="mov_despesa_tinta",
        token_glifo="mov_despesa_glifo",
    ),
}

# Atalhos de valor da fileira de pílulas, em reais. São as notas que circulam no
# caixa do food truck — o operador raramente faz sangria de R$ 37,40.
ATALHOS_EM_REAIS: tuple[int, ...] = (10, 20, 50, 100, 200, 500)

_SEM_OPERADOR = "—"


def rotulo_do_movimento(tipo: TipoMovimento) -> str:
    """`SANGRIA` vira `"Sangria"` — o rótulo humano do tipo, em um lugar só.

    Aceita `CONSUMO_FUNCIONARIO` (que não tem `Operacao`, por não ser
    movimentação manual) e devolve o valor cru do enum: ele aparece na tabela de
    movimentos do turno, gravado por outro caminho, e a linha não pode sair em
    branco por isso.
    """
    operacao = OPERACOES.get(tipo)
    return operacao.titulo if operacao is not None else tipo.value


def papel_do_movimento(tipo: TipoMovimento) -> str:
    """A chave de estilo do tipo (`"sangria"`), para o badge da tabela.

    Tipo sem `Operacao` devolve string vazia — o badge sai sem cor de estado,
    que é como a tabela já tratava o caso.
    """
    operacao = OPERACOES.get(tipo)
    return operacao.papel if operacao is not None else ""


@dataclass(frozen=True, slots=True)
class DadosMovimento:
    """O que o modal devolve. A view leva isto para `CaixaService.registrar_movimento`."""

    valor: Decimal
    descricao: str | None


class _IconeMovimento(QWidget):
    """O ícone do badge do cabeçalho, desenhado à mão.

    Mesma decisão do cadeado do `pin_pad_dialog`, da lupa do
    `adicionar_item_dialog` e do usuário do `funcionario_dialog`: o glifo
    equivalente ou não existe fora do bloco de emoji (o recibo da despesa) ou
    cai no Segoe UI Emoji, sai colorido e chapado e ignora o tema (as setas) —
    e a máquina limpa do food truck pode nem ter a fonte. A cor daqui é relida a
    cada repintura, então o ícone acompanha o alternador Claro/Escuro de graça
    (§3.15).

    Um widget só para os três desenhos: o que muda entre eles é o traço, não o
    ciclo de vida nem a leitura de tema.
    """

    LADO_PX = 20

    def __init__(self, operacao: Operacao, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._operacao = operacao
        self.setObjectName("movCaixaGlifo")
        self.setFixedSize(self.LADO_PX, self.LADO_PX)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        cor = QColor(ThemeController.instancia().tokens_atuais[self._operacao.token_glifo])
        caneta = QPen(cor, 1.9)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)

        if self._operacao.glifo == GLIFO_SAIDA:
            self._desenhar_seta(pintor, QPointF(4.5, 15.5), QPointF(15.5, 4.5))
        elif self._operacao.glifo == GLIFO_ENTRADA:
            self._desenhar_seta(pintor, QPointF(15.5, 4.5), QPointF(4.5, 15.5))
        else:
            self._desenhar_recibo(pintor)
        pintor.end()

    @staticmethod
    def _desenhar_seta(pintor: QPainter, origem: QPointF, ponta: QPointF) -> None:
        """Diagonal com a farpa em L na ponta — o `↗` da sangria e o `↙` do reforço.

        A farpa sai da ponta na horizontal e na vertical (e não em 45°) de
        propósito: em 20px, duas linhas oblíquas de 6px viram um borrão, e o L
        continua lendo como seta mesmo com o antialias apagando meio pixel.
        """
        pintor.drawLine(origem, ponta)
        recuo = 6.0 if ponta.x() > origem.x() else -6.0
        pintor.drawLine(ponta, QPointF(ponta.x() - recuo, ponta.y()))
        pintor.drawLine(ponta, QPointF(ponta.x(), ponta.y() - recuo))

    @staticmethod
    def _desenhar_recibo(pintor: QPainter) -> None:
        """O papelzinho da despesa: retângulo com a serrilha embaixo e duas linhas."""
        contorno = QPainterPath()
        contorno.moveTo(4.0, 3.5)
        contorno.lineTo(16.0, 3.5)
        contorno.lineTo(16.0, 14.5)
        for x in (13.0, 10.0, 7.0, 4.0):
            # A serrilha alterna vale e crista: dente para baixo, dente de
            # volta. Quatro passos fecham a base em `x = 4`, onde a lateral
            # esquerda sobe.
            contorno.lineTo(x + 1.5, 17.0)
            contorno.lineTo(x, 14.5)
        contorno.closeSubpath()
        pintor.drawPath(contorno)
        pintor.drawLine(QPointF(7.0, 7.2), QPointF(13.0, 7.2))
        pintor.drawLine(QPointF(7.0, 10.4), QPointF(13.0, 10.4))


class MovimentacaoCaixaDialog(QDialog):
    """Cartão de sangria/reforço/despesa: visor, numpad, atalhos e descrição."""

    LARGURA_CARTAO_PX = 460
    # A largura que sobra para o conteúdo depois das margens laterais do corpo e
    # da borda de 1px do cartão. É constante porque o cartão tem largura fixa —
    # e por ser constante, a altura das faixas que quebram linha
    # (`FlowLayout.heightForWidth`) pode ser calculada sem a tela existir, que é
    # o que faz a suíte `offscreen` conseguir conferir o layout.
    MARGEM_LATERAL_PX = 22
    LARGURA_UTIL_PX = LARGURA_CARTAO_PX - 2 * MARGEM_LATERAL_PX - 2
    LADO_BOTAO_FECHAR_PX = 32
    ALTURA_VISOR_PX = 80
    LIMITE_DESCRICAO = 120
    # O teto do visor é o do banco, não um número escolhido aqui: as colunas
    # monetárias são `NUMERIC(10,2)` e `dinheiro()` recusa acima disso. Sem
    # amarrar os dois, o numpad conseguiria montar um valor que `registrar_movimento`
    # rejeitaria com `ValueError` — que não está em `_ERROS_SERVICE` e subiria
    # como estouro, não como mensagem na tela. Mora no acumulador compartilhado
    # (`teclado_numerico.py`) desde o §9.7; o nome fica aqui porque é por ele
    # que a suíte confere a amarração.
    TETO_EM_CENTAVOS = AcumuladorDeCentavos.TETO_EM_CENTAVOS

    def __init__(
        self,
        tipo: TipoMovimento,
        operador: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        operacao = OPERACOES.get(tipo)
        if operacao is None:
            # Chegar aqui é erro de programação, não de operação: só existem três
            # movimentações manuais, e `CONSUMO_FUNCIONARIO` é recusado pelo
            # próprio service. Falhar na construção é melhor que abrir um cartão
            # sem título, sem sugestões e sem cor.
            raise ValueError(
                f"{tipo} não é uma movimentação manual de caixa. "
                f"Aceitos: {', '.join(t.value for t in OPERACOES)}."
            )
        self._operacao = operacao
        self._valor = AcumuladorDeCentavos()
        self._backdrop: Backdrop | None = None
        self._atalhos: dict[int, QPushButton] = {}
        self._chips: dict[str, QPushButton] = {}

        # O numpad é o mesmo dos modais de abertura e fechamento de caixa
        # (§9.7): o que muda entre os três é para onde os dígitos vão, e isso
        # quem decide é o slot daqui, não o teclado.
        self._teclado = TecladoNumerico()
        self._teclado.digitou.connect(self._digitar)
        self._teclado.apagou.connect(self._apagar)
        self._teclas = self._teclado.teclas

        self.setObjectName("movCaixaDialog")
        self.setWindowTitle(operacao.titulo)
        # Sem moldura do sistema: o cabeçalho (badge, título, subtítulo e o ✕) é
        # do cartão, e o fundo translúcido é o que faz os cantos de 16px saírem
        # redondos em vez de recortados contra um retângulo opaco.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)

        cartao = QFrame()
        cartao.setObjectName("movCaixaCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        # Margem zero e espaçamento zero no corpo: cada seção traz a própria
        # margem, e é isso que faz os dois divisores irem de borda a borda do
        # cartão como no mockup. Com uma margem lateral no corpo, eles nasceriam
        # encolhidos e o cartão pareceria ter três caixas soltas dentro.
        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(0, 0, 0, 0)
        corpo.setSpacing(0)
        corpo.addLayout(self._montar_cabecalho())
        corpo.addWidget(self._divisor())
        corpo.addLayout(self._montar_meio())
        corpo.addWidget(self._divisor())
        corpo.addLayout(self._montar_rodape(operador))

        self._pintar_valor()
        self._ajustar_faixas()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar_cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setContentsMargins(self.MARGEM_LATERAL_PX, 14, 14, 14)
        linha.setSpacing(12)

        badge = QFrame()
        badge.setObjectName("movCaixaBadge")
        badge.setProperty("operacao", self._operacao.papel)
        badge.setFixedSize(42, 42)
        dentro = QHBoxLayout(badge)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(_IconeMovimento(self._operacao), 0, Qt.AlignmentFlag.AlignCenter)
        linha.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel(self._operacao.titulo)
        titulo.setObjectName("movCaixaTitulo")
        textos.addWidget(titulo)
        subtitulo = QLabel(self._operacao.subtitulo)
        subtitulo.setObjectName("movCaixaSubtitulo")
        textos.addWidget(subtitulo)
        linha.addLayout(textos)
        linha.addStretch()

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("movCaixaFechar")
        self._botao_fechar.setFixedSize(self.LADO_BOTAO_FECHAR_PX, self.LADO_BOTAO_FECHAR_PX)
        self._botao_fechar.setToolTip("Fechar (Esc)")
        cartao_modal.preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignTop)
        return linha

    def _montar_meio(self) -> QVBoxLayout:
        coluna = QVBoxLayout()
        coluna.setContentsMargins(self.MARGEM_LATERAL_PX, 14, self.MARGEM_LATERAL_PX, 14)
        coluna.setSpacing(10)
        coluna.addWidget(self._montar_visor())
        coluna.addWidget(self._montar_atalhos())
        coluna.addWidget(self._teclado)
        coluna.addWidget(self._rotulo("DESCRIÇÃO"))
        coluna.addWidget(self._montar_campo_descricao())
        coluna.addWidget(self._montar_chips())
        return coluna

    def _montar_visor(self) -> QFrame:
        visor = QFrame()
        visor.setObjectName("movCaixaVisor")
        visor.setProperty("foco", True)
        visor.setFixedHeight(self.ALTURA_VISOR_PX)
        self._visor = visor

        dentro = QVBoxLayout(visor)
        dentro.setContentsMargins(18, 10, 18, 10)
        dentro.setSpacing(2)

        rotulo = QLabel("VALOR")
        rotulo.setObjectName("movCaixaVisorRotulo")
        rotulo.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dentro.addWidget(rotulo)

        self._label_valor = QLabel()
        self._label_valor.setObjectName("movCaixaVisorValor")
        self._label_valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dentro.addWidget(self._label_valor)
        return visor

    def _montar_atalhos(self) -> QWidget:
        """A fileira `+10 … +500`, que quebra linha sozinha se não couber.

        `FlowLayout` e não `QHBoxLayout` pela mesma razão da faixa de categorias
        do §9.4: um `QHBoxLayout` espremeria as pílulas até o rótulo sumir, que
        é o defeito que a Fase 7 achou na tela de Configurações.
        """
        self._faixa_atalhos = QWidget()
        self._faixa_atalhos.setObjectName("movCaixaFaixa")
        fluxo = FlowLayout(self._faixa_atalhos, spacing=6)
        for reais in ATALHOS_EM_REAIS:
            pill = QPushButton(f"+{reais}")
            pill.setObjectName("movCaixaAtalho")
            # O valor vive na propriedade, e não numa `lambda` amarrada no
            # clique: ver §3.14 no cabeçalho do arquivo.
            pill.setProperty("reais", reais)
            cartao_modal.preparar_botao(pill)
            pill.clicked.connect(self._atalho_clicado)
            fluxo.addWidget(pill)
            self._atalhos[reais] = pill
        return self._faixa_atalhos

    def _montar_campo_descricao(self) -> QLineEdit:
        self._campo_descricao = QLineEdit()
        self._campo_descricao.setObjectName("movCaixaDescricao")
        self._campo_descricao.setPlaceholderText(self._operacao.placeholder)
        self._campo_descricao.setMaxLength(self.LIMITE_DESCRICAO)
        # O único `eventFilter` do arquivo, e `done()` o remove: é ele que
        # devolve o `Tab` ao visor e mantém o anel de foco em dia quando o
        # operador entra no campo com o dedo em vez do teclado.
        self._campo_descricao.installEventFilter(self)
        return self._campo_descricao

    def _montar_chips(self) -> QWidget:
        self._faixa_chips = QWidget()
        self._faixa_chips.setObjectName("movCaixaFaixa")
        fluxo = FlowLayout(self._faixa_chips, spacing=6)
        for tag in self._operacao.tags:
            chip = QPushButton(tag)
            chip.setObjectName("movCaixaChip")
            cartao_modal.preparar_botao(chip)
            chip.clicked.connect(self._chip_clicado)
            fluxo.addWidget(chip)
            self._chips[tag] = chip
        return self._faixa_chips

    def _montar_rodape(self, operador: str | None) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setContentsMargins(self.MARGEM_LATERAL_PX, 10, self.MARGEM_LATERAL_PX, 12)
        linha.setSpacing(10)

        nome = (operador or "").strip() or _SEM_OPERADOR
        self._label_operador = QLabel(f"OPERADOR · {nome.upper()}")
        self._label_operador.setObjectName("movCaixaOperador")
        self._label_operador.setWordWrap(True)
        linha.addWidget(self._label_operador, 1)

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.setObjectName("movCaixaCancelar")
        cartao_modal.preparar_botao(self._botao_cancelar)
        self._botao_cancelar.clicked.connect(self.reject)
        linha.addWidget(self._botao_cancelar)

        self._botao_confirmar = QPushButton(self._operacao.rotulo_confirmar)
        self._botao_confirmar.setObjectName("movCaixaConfirmar")
        self._botao_confirmar.setProperty("operacao", self._operacao.papel)
        cartao_modal.preparar_botao(self._botao_confirmar)
        self._botao_confirmar.clicked.connect(self._confirmar)
        linha.addWidget(self._botao_confirmar)
        return linha

    def _divisor(self) -> QFrame:
        divisor = QFrame()
        divisor.setObjectName("movCaixaDivisor")
        divisor.setFixedHeight(1)
        return divisor

    def _rotulo(self, texto: str) -> QLabel:
        rotulo = QLabel(texto)
        rotulo.setObjectName("movCaixaRotulo")
        return rotulo

    def _ajustar_faixas(self) -> None:
        """Fecha as duas faixas na altura real do que elas comportam.

        `FlowLayout.sizeHint()` devolve o **mínimo** (uma fileira), então sem
        isto a segunda fileira de chips seria pintada por cima do rodapé — foi
        assim que o defeito apareceu na faixa de categorias do §9.4, com o
        cardápio real. A despesa tem quatro sugestões e é a que estoura primeiro.

        Roda na construção (a largura é constante, ver `LARGURA_UTIL_PX`) e de
        novo no `showEvent`, porque a altura de uma pílula só é verdade depois
        do primeiro `polish`: antes disso o `sizeHint` não conhece o `padding`
        que o QSS global aplica.
        """
        for faixa in (self._faixa_atalhos, self._faixa_chips):
            fluxo = faixa.layout()
            if fluxo is None:
                continue
            faixa.setFixedHeight(fluxo.heightForWidth(self.LARGURA_UTIL_PX))

    # ------------------------------------------------------------------
    # O visor — centavos entrando pela direita
    # ------------------------------------------------------------------

    def _digitar(self, digitos: str) -> None:
        """Empurra dígitos pela direita, como máquina de cartão.

        A conta mora em `AcumuladorDeCentavos` (§9.7) e é a mesma dos modais de
        abertura e fechamento: o que este método faz é repintar depois.
        """
        self._valor.digitar(digitos)
        self._pintar_valor()

    def _apagar(self) -> None:
        self._valor.apagar()
        self._pintar_valor()

    def _somar(self, reais: int) -> None:
        self._valor.somar_reais(reais)
        self._pintar_valor()

    def valor(self) -> Decimal:
        """O que está no visor, como `Decimal` de duas casas."""
        return self._valor.valor

    def _pintar_valor(self) -> None:
        # `formatar_reais` é o mesmo do resto do app e do cupom (§3.8): o valor
        # que o operador confere aqui sai idêntico na tabela de movimentos e no
        # relatório de fechamento.
        self._label_valor.setText(formatar_reais(self.valor()))
        # Sem valor não há movimento: `registrar_movimento` recusa zero, e
        # deixar o botão aceso só faria o operador levar o erro de volta para a
        # linha vermelha da tela de trás.
        self._botao_confirmar.setEnabled(self._valor.centavos > 0)

    # ------------------------------------------------------------------
    # Cliques (nenhum ligado por lambda — §3.14)
    # ------------------------------------------------------------------

    def _atalho_clicado(self) -> None:
        botao = self.sender()
        if not isinstance(botao, QPushButton):
            return
        self._somar(int(botao.property("reais") or 0))

    def _chip_clicado(self) -> None:
        """A sugestão **substitui** o que estava escrito, e não emenda.

        Emendar produziria "Envio ao cofreTroco para o malote" no primeiro
        clique errado, e o operador teria que apagar com o dedo no campo — que é
        exatamente o que os chips existem para evitar.
        """
        botao = self.sender()
        if not isinstance(botao, QPushButton):
            return
        self._campo_descricao.setText(botao.text())

    def _confirmar(self) -> None:
        if self._valor.centavos <= 0:
            return
        self.accept()

    # ------------------------------------------------------------------
    # Foco (visor ↔ descrição)
    # ------------------------------------------------------------------

    def _focar_visor(self) -> None:
        self.setFocus(Qt.FocusReason.TabFocusReason)
        self._marcar_foco_do_visor(True)

    def _focar_descricao(self) -> None:
        self._campo_descricao.setFocus(Qt.FocusReason.TabFocusReason)
        self._marcar_foco_do_visor(False)

    def _marcar_foco_do_visor(self, aceso: bool) -> None:
        # Repolir custa um recálculo de estilo: só paga quem mudou de estado
        # (mesma economia do `_pintar_marcadores` do modal de PIN).
        if self._visor.property("foco") != aceso:
            aplicar_propriedade(self._visor, "foco", aceso)

    # ------------------------------------------------------------------
    # Resultado
    # ------------------------------------------------------------------

    def resultado(self) -> DadosMovimento:
        """O que a view leva para `CaixaService.registrar_movimento`.

        Lido DEPOIS do `exec()` — o `executar_modal` (§3.2) só descarta o
        diálogo na volta.
        """
        return DadosMovimento(
            valor=self.valor(),
            descricao=self._campo_descricao.text().strip() or None,
        )

    # ------------------------------------------------------------------
    # Overrides do Qt
    # ------------------------------------------------------------------

    @nao_deixa_escapar(retorno=False)
    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:  # noqa: N802 (override Qt)
        """O campo de descrição devolvendo o `Tab` — e mantendo o anel em dia.

        O `QLineEdit` trata `Tab` como navegação de foco, então ele nunca
        chegaria ao `keyPressEvent` do diálogo. Consumir o evento aqui (devolver
        `True`) é o que fecha o par de dois destinos que o briefing pediu.
        """
        if watched is not self._campo_descricao:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                self._focar_visor()
                return True
        elif event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self._marcar_foco_do_visor(event.type() == QEvent.Type.FocusOut)
        return super().eventFilter(watched, event)

    @nao_deixa_escapar()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        """O teclado físico (ou o numérico USB) faz o mesmo que o dedo na tela.

        Só chega aqui o que o campo de descrição não quis: com o cursor no
        campo, dígito é texto de descrição, e é assim que tem que ser. `Enter` e
        `Esc` chegam dos dois lados, porque o `QLineEdit` ignora os dois.

        O Esc cai no `super()` de propósito: lá o `QDialog` o traduz em
        `reject()`, que passa por `done()` e portanto pela mesma limpeza dos
        outros caminhos de saída.
        """
        tecla = event.key()
        if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirmar()
            return
        if tecla == Qt.Key.Key_Backspace:
            self._apagar()
            return
        if tecla in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self._focar_descricao()
            return
        texto = event.text()
        # `len(texto) == 1` antes do `isdigit()`: `"²"` e outros dígitos Unicode
        # passam no `isdigit()` e estourariam o `int()` do acumulador.
        if len(texto) == 1 and texto in "0123456789":
            self._digitar(texto)
            return
        super().keyPressEvent(event)

    @nao_deixa_escapar()
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        if self._backdrop is None:
            self._backdrop = cartao_modal.montar(self)
        self._ajustar_faixas()
        self.adjustSize()
        cartao_modal.centralizar_no_pai(self)
        # O diálogo, e não um botão, é quem lê o teclado: o modal abre com o
        # visor "aceso", que é o que o operador vem fazer aqui.
        self._focar_visor()

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única — e por isso o lugar certo da limpeza.

        Confirmar, Cancelar, o ✕ e o Esc passam todos por aqui; `closeEvent`
        sozinho não serviria, porque `done()` faz `hide()`, não `close()`
        (§3.9). Saem juntos o filtro de eventos do campo de descrição, as três
        tabela de atalhos, a de chips, a de teclas (que mora no teclado
        compartilhado) e o escurecedor, que é filho da JANELA e não do diálogo.

        O valor digitado NÃO é zerado aqui: `resultado()` é lido depois do
        `exec()`, e limpá-lo faria toda sangria ser gravada como R$ 0,00 — o
        oposto do que a limpeza equivalente do modal de PIN faz, onde o segredo
        precisa sumir da memória e ninguém o lê de volta.
        """
        self._campo_descricao.removeEventFilter(self)
        self._atalhos.clear()
        self._teclado.soltar()
        self._chips.clear()
        backdrop, self._backdrop = self._backdrop, None
        cartao_modal.descartar(backdrop)
        super().done(resultado)
