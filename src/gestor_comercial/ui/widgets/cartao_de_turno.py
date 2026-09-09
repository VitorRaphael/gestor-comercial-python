"""A moldura dos dois modais que abrem e fecham o turno — §9.7.

Abrir e fechar o caixa são a **mesma cerimônia** vista de dois lados: alguém de
pé no balcão declara um número que ninguém mais vai conferir depois, e esse
número decide se o turno fechou certo. O que muda entre as duas telas é a
coluna da esquerda (um valor a declarar × duas contagens a conferir); o
cabeçalho, o teclado da direita, o rodapé, o teclado físico e o ciclo de vida
são idênticos — e é isso que mora aqui.

## Por que uma base, e não uma classe parametrizada

O §9.6 resolveu sangria/reforço/despesa com **uma** classe parametrizada, e
estava certo: as três são a mesma tela com outro rótulo. Aqui não. A abertura
tem um visor, quatro pílulas de valor e um cartão de contexto; o fechamento tem
duas contagens selecionáveis, uma diferença que se recalcula a cada tecla e um
atalho que preenche o esperado. Espremer as duas num `if tipo is ...` produziria
o tipo de classe em que metade dos atributos é `None` conforme o modo — e num
modal que grava dinheiro, "este atributo às vezes existe" é como um valor sai
errado sem ninguém ver.

O que elas repetiriam de verdade — cabeçalho, rodapé, roteamento de teclado,
`done()` — é justamente o que quebra em silêncio, e é o que a base entrega
pronto. A suíte reprova corpo de função duplicado na camada de UI
(`test_paineis_de_relatorio.py`), então a alternativa nem passaria.

## Foco, e por que o `Tab` precisa de uma lista

Os dois modais têm **mais de um destino** para os dígitos: a abertura tem o
valor e a observação; o fechamento tem dinheiro, maquininha e observação. Quem
guarda a ordem é a base (`_alvos` + `_campos`), e o `Tab` percorre os alvos
numéricos primeiro e o texto por último, voltando ao começo.

Isso não é conveniência: o teclado numérico USB do balcão não tem para onde
apontar sozinho. Sem o rótulo da direita dizer `DIGITANDO DINHEIRO` e sem o
anel de foco no destino ativo, o operador digita a contagem da maquininha em
cima da contagem da gaveta e só descobre no papel impresso.

## Ciclo de vida

O briefing pediu, no vocabulário do Tkinter, `destroy()` + `unbind()` +
`after_cancel`. Os três equivalentes em PySide6 passam por `done()`, o único
portão por onde saem Confirmar, Cancelar, ✕ e Esc — `closeEvent` não serviria,
porque `done()` faz `hide()`, não `close()` (§3.9):

* **destroy** — `executar_modal()` (§3.2) faz o `deleteLater()` depois de ler o
  resultado; `done()` acrescenta soltar o **escurecedor**, que é filho da
  janela principal e não do diálogo, e a tabela de teclas do numpad;
* **unbind** — os `eventFilter` instalados nos campos de texto saem
  explicitamente. `QShortcut` não existe: o teclado é lido no `keyPressEvent`
  do próprio diálogo, que morre com ele;
* **after_cancel** — não há timer nenhum, e isso é decisão. Cada tecla recalcula
  um `Decimal` e repinta três rótulos; não há busca a agrupar nem nada agendado,
  então não há `after_cancel` a fazer porque não há `after`.

O valor digitado **não** é zerado em `done()` — o oposto do modal de PIN, e de
propósito: `resultado()` é lido depois do `exec()` (§3.2), e limpar faria todo
fechamento ser gravado como R$ 0,00.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
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
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.teclado_numerico import AcumuladorDeCentavos, TecladoNumerico

# As duas cerimônias do turno. É o valor que o QSS lê (`[papel="abertura"]`) e
# que escolhe a cor do badge e do botão que grava — os dois únicos lugares onde
# abrir e fechar têm cor diferente.
PAPEL_ABERTURA = "abertura"
PAPEL_FECHAMENTO = "fechamento"

# A dica do rodapé é a mesma nos dois: os dois atalhos que o teclado físico
# oferece, escritos onde o operador olha antes de apertar.
DICA_DE_TECLADO = "ENTER CONFIRMA · ESC CANCELA"


class IconeDeGaveta(QWidget):
    """A gaveta do badge do cabeçalho — aberta na abertura, trancada no fechamento.

    Desenhada à mão pela mesma razão do cadeado do PIN, da lupa do "Adicionar
    item", do usuário do "Novo funcionário" e das setas da movimentação: o
    glifo equivalente ou não existe fora do bloco de emoji ou cai no Segoe UI
    Emoji, sai colorido e chapado e ignora o tema — e a máquina limpa do food
    truck pode nem ter a fonte. A cor é relida a cada repintura, então o ícone
    acompanha o alternador Claro/Escuro de graça (§3.15).

    **O mesmo móvel nos dois estados**, e não dois desenhos diferentes: é a
    mesma gaveta que o turno abre no começo da noite e tranca no fim. Aberta,
    ela mostra os dois puxadores; trancada, um cadeado ocupa o lugar deles.
    """

    LADO_PX = 20

    def __init__(
        self, token_cor: str, trancada: bool = False, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._token_cor = token_cor
        self._trancada = trancada
        self.setObjectName("turnoGlifo")
        self.setFixedSize(self.LADO_PX, self.LADO_PX)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        cor = QColor(ThemeController.instancia().tokens_atuais[self._token_cor])
        caneta = QPen(cor, 1.8)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)

        # O móvel: contorno e a linha que separa as duas gavetas.
        pintor.drawRoundedRect(QRectF(3.5, 3.5, 13.0, 13.0), 2.0, 2.0)
        pintor.drawLine(QPointF(3.5, 10.0), QPointF(16.5, 10.0))

        if self._trancada:
            self._desenhar_cadeado(pintor, cor)
        else:
            # Os dois puxadores, um por gaveta.
            pintor.drawLine(QPointF(8.0, 6.9), QPointF(12.0, 6.9))
            pintor.drawLine(QPointF(8.0, 13.2), QPointF(12.0, 13.2))
        pintor.end()

    @staticmethod
    def _desenhar_cadeado(pintor: QPainter, cor: QColor) -> None:
        """Um cadeado pequeno no lugar dos puxadores, na gaveta de baixo.

        Construído de propósito diferente do cadeado do `pin_pad_dialog` — lá o
        cadeado *é* o ícone e ocupa os 22px inteiros; aqui ele é um detalhe de
        4px dentro do móvel, e o que informa é o móvel.
        """
        haste = QPainterPath()
        arco = QRectF(8.4, 11.4, 3.2, 3.2)
        haste.arcMoveTo(arco, 0)
        haste.arcTo(arco, 0, 180)
        pintor.drawPath(haste)

        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(cor)
        pintor.drawRoundedRect(QRectF(7.8, 12.8, 4.4, 3.4), 0.8, 0.8)


class CartaoDeTurnoDialog(QDialog):
    """Cartão sem moldura, dividido: conteúdo à esquerda, numpad à direita.

    A subclasse monta a própria coluna da esquerda e chama `_montar_cartao()`
    no fim do `__init__`. A base não constrói nada sozinha de propósito: se ela
    chamasse um `_montar_coluna_esquerda()` abstrato de dentro do próprio
    `__init__`, a subclasse teria que ter todos os atributos prontos *antes* do
    `super().__init__()` — que é como se escreve um `AttributeError` que só
    aparece no balcão.
    """

    LARGURA_CARTAO_PX = 640
    LARGURA_TECLADO_PX = 204
    MARGEM_LATERAL_PX = 22
    ESPACO_ENTRE_COLUNAS_PX = 18
    LADO_BOTAO_FECHAR_PX = 32
    LIMITE_OBSERVACAO = 120
    # A largura que sobra para a coluna da esquerda depois das margens, da borda
    # de 1px de cada lado do cartão, do teclado e do espaço entre os dois. É
    # constante porque o cartão tem largura fixa — e por ser constante, a altura
    # de uma faixa que quebra linha (`FlowLayout.heightForWidth`) pode ser
    # calculada sem a tela existir, que é o que faz a suíte `offscreen`
    # conseguir conferir o layout.
    LARGURA_COLUNA_PX = (
        LARGURA_CARTAO_PX
        - 2 * MARGEM_LATERAL_PX
        - 2
        - LARGURA_TECLADO_PX
        - ESPACO_ENTRE_COLUNAS_PX
    )

    def __init__(
        self,
        papel: str,
        titulo: str,
        subtitulo: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._papel = papel
        self._titulo = titulo
        self._subtitulo = subtitulo
        self._backdrop: Backdrop | None = None
        # Os destinos do teclado, na ordem em que o `Tab` os percorre: primeiro
        # os numéricos, depois os campos de texto.
        self._alvos: list[AcumuladorDeCentavos] = []
        self._indice_alvo = 0
        self._campos: list[QLineEdit] = []

        self._teclado = TecladoNumerico()
        self._teclado.digitou.connect(self._digitar)
        self._teclado.apagou.connect(self._apagar)

        self.setObjectName("turnoDialog")
        self.setWindowTitle(titulo)
        # Sem moldura do sistema: o cabeçalho (badge, título, subtítulo e o ✕) é
        # do cartão, e o fundo translúcido é o que faz os cantos de 16px saírem
        # redondos em vez de recortados contra um retângulo opaco.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

    # ------------------------------------------------------------------
    # Montagem — chamada pela subclasse
    # ------------------------------------------------------------------

    def _montar_cartao(
        self,
        esquerda: QWidget,
        *,
        icone: QWidget,
        rotulo_teclado: str,
        rotulo_confirmar: str,
    ) -> None:
        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)

        cartao = QFrame()
        cartao.setObjectName("turnoCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        # Margem zero e espaçamento zero no corpo: cada seção traz a própria
        # margem, e é isso que faz os dois divisores irem de borda a borda do
        # cartão como no mockup.
        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(0, 0, 0, 0)
        corpo.setSpacing(0)
        corpo.addLayout(self._montar_cabecalho(icone))
        corpo.addWidget(self._divisor())
        corpo.addLayout(self._montar_meio(esquerda, rotulo_teclado))
        corpo.addWidget(self._divisor())
        corpo.addLayout(self._montar_rodape(rotulo_confirmar))

    def _montar_cabecalho(self, icone: QWidget) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setContentsMargins(self.MARGEM_LATERAL_PX, 14, 14, 14)
        linha.setSpacing(12)

        badge = QFrame()
        badge.setObjectName("turnoBadge")
        badge.setProperty("papel", self._papel)
        badge.setFixedSize(42, 42)
        dentro = QHBoxLayout(badge)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(icone, 0, Qt.AlignmentFlag.AlignCenter)
        linha.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel(self._titulo)
        titulo.setObjectName("turnoTitulo")
        textos.addWidget(titulo)
        subtitulo = QLabel(self._subtitulo)
        subtitulo.setObjectName("turnoSubtitulo")
        textos.addWidget(subtitulo)
        linha.addLayout(textos)
        linha.addStretch()

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("turnoFechar")
        self._botao_fechar.setFixedSize(self.LADO_BOTAO_FECHAR_PX, self.LADO_BOTAO_FECHAR_PX)
        self._botao_fechar.setToolTip("Fechar (Esc)")
        cartao_modal.preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignTop)
        return linha

    def _montar_meio(self, esquerda: QWidget, rotulo_teclado: str) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setContentsMargins(self.MARGEM_LATERAL_PX, 16, self.MARGEM_LATERAL_PX, 16)
        linha.setSpacing(self.ESPACO_ENTRE_COLUNAS_PX)
        esquerda.setObjectName("turnoColuna")
        linha.addWidget(esquerda, 1)

        coluna = QVBoxLayout()
        coluna.setSpacing(10)
        # O rótulo é atributo porque o fechamento o reescreve a cada troca de
        # alvo (`DIGITANDO DINHEIRO` / `DIGITANDO MAQUININHAS`) — é ele que diz
        # para onde o próximo toque vai.
        self._rotulo_teclado = QLabel(rotulo_teclado)
        self._rotulo_teclado.setObjectName("turnoRotulo")
        coluna.addWidget(self._rotulo_teclado)
        self._teclado.setFixedWidth(self.LARGURA_TECLADO_PX)
        coluna.addWidget(self._teclado)
        coluna.addStretch()
        linha.addLayout(coluna)
        return linha

    def _montar_rodape(self, rotulo_confirmar: str) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setContentsMargins(self.MARGEM_LATERAL_PX, 12, self.MARGEM_LATERAL_PX, 14)
        linha.setSpacing(10)

        dica = QLabel(DICA_DE_TECLADO)
        dica.setObjectName("turnoDica")
        linha.addWidget(dica, 1)

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.setObjectName("turnoCancelar")
        cartao_modal.preparar_botao(self._botao_cancelar)
        self._botao_cancelar.clicked.connect(self.reject)
        linha.addWidget(self._botao_cancelar)

        self._botao_confirmar = QPushButton(rotulo_confirmar)
        self._botao_confirmar.setObjectName("turnoConfirmar")
        self._botao_confirmar.setProperty("papel", self._papel)
        cartao_modal.preparar_botao(self._botao_confirmar)
        self._botao_confirmar.clicked.connect(self._confirmar)
        linha.addWidget(self._botao_confirmar)
        return linha

    # ------------------------------------------------------------------
    # Peças que as duas colunas da esquerda usam
    # ------------------------------------------------------------------

    @staticmethod
    def _divisor() -> QFrame:
        divisor = QFrame()
        divisor.setObjectName("turnoDivisor")
        divisor.setFixedHeight(1)
        return divisor

    @staticmethod
    def _rotulo(texto: str) -> QLabel:
        rotulo = QLabel(texto)
        rotulo.setObjectName("turnoRotulo")
        return rotulo

    def _campo_de_observacao(self, placeholder: str) -> QLineEdit:
        """O campo de texto livre do rodapé da coluna, com o filtro de `Tab` posto.

        O `QLineEdit` trata `Tab` como navegação de foco, então ele nunca
        chegaria ao `keyPressEvent` do diálogo — e como o diálogo tem
        `FocusPolicy.NoFocus` (todo modal em cartão daqui tem, ver
        `cartao_modal.preparar_botao`), a navegação natural do Qt pularia o
        cartão inteiro e o `Tab` não faria nada. O filtro fecha esse par, e
        `done()` o remove.
        """
        campo = QLineEdit()
        campo.setObjectName("turnoCampo")
        campo.setPlaceholderText(placeholder)
        campo.setMaxLength(self.LIMITE_OBSERVACAO)
        campo.installEventFilter(self)
        self._campos.append(campo)
        return campo

    def _registrar_alvos(self, *alvos: AcumuladorDeCentavos) -> None:
        """Diz à base quais valores o teclado alimenta, e em que ordem.

        Chamado pela subclasse antes de montar o cartão. A abertura registra um;
        o fechamento, dois.
        """
        self._alvos = list(alvos)
        self._indice_alvo = 0

    # ------------------------------------------------------------------
    # O teclado e o alvo ativo
    # ------------------------------------------------------------------

    def _alvo(self) -> AcumuladorDeCentavos:
        return self._alvos[self._indice_alvo]

    def _selecionar_alvo(self, indice: int) -> None:
        """Aponta o teclado para outro valor — o clique nos cartões do fechamento.

        Traz o foco de volta ao diálogo: se o operador estava no campo de
        observação e tocou no cartão de "Dinheiro", o dígito seguinte tem que ir
        para a contagem, não continuar virando texto da observação.
        """
        if not 0 <= indice < len(self._alvos):
            return
        self._indice_alvo = indice
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._pintar()

    def _digitar(self, digitos: str) -> None:
        self._alvo().digitar(digitos)
        self._pintar()

    def _apagar(self) -> None:
        self._alvo().apagar()
        self._pintar()

    def _confirmar(self) -> None:
        self.accept()

    def _campo_em_foco(self) -> QLineEdit | None:
        for campo in self._campos:
            if campo.hasFocus():
                return campo
        return None

    def _avancar_foco(self) -> None:
        """O `Tab`: alvos numéricos na ordem, depois o texto, depois de volta ao começo."""
        if self._campo_em_foco() is not None:
            self._focar_alvo(0)
            return
        proximo = self._indice_alvo + 1
        if proximo < len(self._alvos):
            self._focar_alvo(proximo)
        elif self._campos:
            self._campos[0].setFocus(Qt.FocusReason.TabFocusReason)
            self._pintar()
        else:
            self._focar_alvo(0)

    def _focar_alvo(self, indice: int) -> None:
        self._indice_alvo = indice
        self.setFocus(Qt.FocusReason.TabFocusReason)
        self._pintar()

    def _digitando_no_teclado(self) -> bool:
        """`False` quando o cursor está num campo de texto.

        É o que o anel de foco desenha: com o cursor na observação, dígito é
        texto de observação — e é assim que tem que ser.
        """
        return self._campo_em_foco() is None

    def _marcar(self, widget: QWidget, aceso: bool) -> None:
        """Acende/apaga o anel de um widget, repolindo só quem mudou de estado.

        Repolir custa um recálculo de estilo, e este método é chamado a cada
        tecla — a mesma economia do `_pintar_marcadores` do modal de PIN.
        """
        if widget.property("ativa") != aceso:
            aplicar_propriedade(widget, "ativa", aceso)

    def _pintar(self) -> None:
        """Repinta valores e anéis. Implementado pela subclasse."""
        raise NotImplementedError

    def _antes_de_medir(self) -> None:
        """Gancho chamado no `showEvent`, ANTES de o cartão ser medido e centralizado.

        É onde entra o ajuste que muda a ALTURA do conteúdo (a faixa de pílulas
        que quebra linha, por exemplo): feito depois do `adjustSize()`, o cartão
        cresceria já centralizado pela altura antiga e nasceria torto.
        """

    def _soltar(self) -> None:
        """Gancho de limpeza da subclasse, chamado por `done()`.

        A base solta o que ela criou (filtros, teclado, escurecedor); as tabelas
        de widget que a coluna da esquerda montou são da subclasse, e é aqui que
        ela as solta. Vazio por padrão: nem toda coluna guarda tabela.
        """

    # ------------------------------------------------------------------
    # Overrides do Qt
    # ------------------------------------------------------------------

    @nao_deixa_escapar(retorno=False)
    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:  # noqa: N802 (override Qt)
        """O campo de texto devolvendo o `Tab` — e mantendo o anel em dia."""
        if watched not in self._campos:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                self._avancar_foco()
                return True
        elif event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self._pintar()
        return super().eventFilter(watched, event)

    @nao_deixa_escapar()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        """O teclado físico (ou o numérico USB) faz o mesmo que o dedo na tela.

        Só chega aqui o que o campo de texto não quis: com o cursor na
        observação, dígito é texto. `Enter` e `Esc` chegam dos dois lados,
        porque o `QLineEdit` ignora os dois.

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
            self._avancar_foco()
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
        self._antes_de_medir()
        self.adjustSize()
        cartao_modal.centralizar_no_pai(self)
        # O diálogo, e não um botão, é quem lê o teclado: o modal abre com o
        # primeiro alvo aceso, que é o que o operador vem fazer aqui.
        self._focar_alvo(0)

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única — e por isso o lugar certo da limpeza. Ver o topo do arquivo."""
        for campo in self._campos:
            campo.removeEventFilter(self)
        self._campos.clear()
        self._teclado.soltar()
        self._soltar()
        backdrop, self._backdrop = self._backdrop, None
        cartao_modal.descartar(backdrop)
        super().done(resultado)
