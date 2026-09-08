"""Modal único de elevação por PIN, com teclado numérico na própria tela.

Substitui `GerentePinDialog` e `LojaPinDialog`, que eram cópia um do outro em
tudo menos duas linhas — o título e qual método de `AuthService` chamar — e
pediam o segredo num `QLineEdit` solto dentro de um `QFormLayout` com a
moldura de janela do sistema. No balcão do food truck isso é a interação
errada: quem opera está de pé, com a mão ocupada, e o teclado físico fica
atrás do monitor.

Aqui é uma classe só, parametrizada por título, subtítulo e **validador** —
os dois usos entram pelos construtores nomeados `para_caixa` e `para_loja`,
que são o único lugar do arquivo onde o nível de acesso aparece.

## O que NÃO mudou

A cascata de 3 níveis (§3.13) continua inteira e continua morando no
`AuthService`: `para_caixa` chama `validar_pin_gerente` (Nível 2 — aceita a
Senha Operacional ou, herdando de cima, a Master) e `para_loja` chama
`validar_pin_dono` (Nível 3 — só a Master). Este diálogo não sabe o que é
nível, não compara hash e não decide nada: ele coleta dígitos, entrega a
string ao validador que recebeu e só faz `accept()` se ninguém levantar
exceção. Trocar a regra de acesso continua sendo trabalho de uma linha no
service, sem passar por aqui.

## Ciclo de vida (§3.2/§3.9, e o RNF do Celeron)

Um modal que fica pendurado no `MainWindow` fica até o app fechar — as dez
telas são montadas no boot e vivem o processo inteiro. Como a Central de Loja
exige o PIN a **cada** acesso (`MainWindow._abrir_area_loja`), é um diálogo por
ida e volta ao hub; num turno inteiro isso soma.

O que este arquivo garante, e `tests/ui/test_vazamento_modais.py` cobra:

* quem abre passa por `executar_modal()`, que descarta a instância depois de
  ler o código de saída;
* `done()` — o único hook por onde passam Entrar, Cancelar, o ✕ e o Esc — solta
  o PIN digitado, **para o timer do aviso de erro** e destrói o escurecedor de
  fundo. Nada agendado sobrevive ao fechamento;
* o teclado não cria widget por tecla digitada: os marcadores são um conjunto
  fixo, montado uma vez, que só troca de propriedade — e só quando ela muda
  de verdade.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.exceptions import AcessoNegadoError, NaoAutorizadoError
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade

# Um validador recebe o PIN digitado e levanta `NaoAutorizadoError` /
# `AcessoNegadoError` quando ele não confere. O retorno (o `Usuario` que
# autoriza) não interessa a este diálogo: quem precisa dele para auditoria
# chama o service direto.
Validador = Callable[[str], object]


class _Backdrop(QWidget):
    """Escurecedor da janela de trás, para o olho ir ao cartão.

    É filho da janela principal, não uma janela própria: um `QWidget` comum
    dentro do backing store do Qt já compõe por cima dos irmãos, e isso custa
    uma pintura chapada — bem menos que abrir uma segunda janela translúcida do
    tamanho da tela numa máquina sem GPU para gastar.
    """

    OPACIDADE = 150  # 0-255 (~59%)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("pinPadBackdrop")

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        pintor = QPainter(self)
        pintor.fillRect(self.rect(), QColor(0, 0, 0, self.OPACIDADE))
        pintor.end()


class _IconeCadeado(QWidget):
    """O cadeado do cabeçalho, desenhado à mão.

    O app usa glifo Unicode como ícone em outros lugares (o de impressora e o
    de engrenagem no `LojaHubView`), mas não existe cadeado fora do bloco de
    emoji: o padrão cai no Segoe UI Emoji, sai colorido e chapado e ignora o
    ciano do tema. Vinte linhas de `QPainter` custam menos que depender de uma
    fonte que a máquina limpa do food truck pode não ter — e, ao contrário de
    um `setStyleSheet` resolvido na construção (§3.15), a cor daqui é relida a
    cada repintura, o que faz o ícone acompanhar o alternador Claro/Escuro de
    graça.
    """

    LADO_PX = 22

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pinPadCadeado")
        self.setFixedSize(self.LADO_PX, self.LADO_PX)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        paleta = ThemeController.instancia().tokens_atuais
        cor = QColor(paleta["pin_icone_glifo"])

        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Haste: meia-volta de cima (0° a 180°, em 1/16 de grau, como o Qt pede).
        caneta = QPen(cor, 1.8)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawArc(QRectF(6.0, 3.5, 10.0, 11.0), 0, 180 * 16)

        # Corpo, encostado onde a haste termina.
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(cor)
        pintor.drawRoundedRect(QRectF(4.0, 9.0, 14.0, 10.0), 2.5, 2.5)

        # Furo da fechadura, vazado na cor da caixa que envolve o ícone.
        pintor.setBrush(QColor(paleta["pin_icone_bg"]))
        pintor.drawEllipse(QRectF(9.4, 12.4, 3.2, 3.2))
        pintor.end()


class PinPadDialog(QDialog):
    """Cartão de PIN com numpad 3x4, aceitando clique **e** teclado físico."""

    LARGURA_CARTAO_PX = 360
    ALTURA_TECLA_PX = 48
    # Piso de marcadores mostrados com o campo vazio. Seis, e não quatro, para
    # caber a Senha Master de fábrica ("050727") sem a fileira crescer no meio
    # da digitação; a Operacional tem oito e passa do piso, daí a fileira ser
    # elástica em vez de fixa.
    DOTS_MINIMOS = 6
    DOTS_MAXIMOS = 12
    # As senhas só têm mínimo (4 caracteres, `LojaConfigService`), não máximo.
    # O teto aqui é do widget, não da regra: evita que um dedo preso na tecla
    # faça a string crescer sem fim na memória do Celeron.
    LIMITE_DE_DIGITOS = 32
    MS_ATE_APAGAR_O_ERRO = 2500

    INSTRUCAO = "DIGITE O PIN DE ACESSO"

    def __init__(
        self,
        titulo: str,
        subtitulo: str,
        validador: Validador,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._validar = validador
        self._pin = ""
        self._backdrop: _Backdrop | None = None
        self._dots: list[QFrame] = []

        self.setObjectName("pinPadDialog")
        self.setWindowTitle(titulo)
        # Sem moldura do sistema: o cabeçalho (título, subtítulo e o botão de
        # fechar) é do cartão, e o fundo translúcido é o que faz os cantos de
        # 16px saírem redondos em vez de recortados contra um retângulo opaco.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        self._timer_erro = QTimer(self)
        self._timer_erro.setSingleShot(True)
        self._timer_erro.timeout.connect(self._limpar_erro)

        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)

        cartao = QFrame()
        cartao.setObjectName("pinPadCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(20, 18, 20, 18)
        corpo.setSpacing(16)
        corpo.addLayout(self._montar_cabecalho(titulo, subtitulo))
        corpo.addLayout(self._montar_marcadores())
        corpo.addLayout(self._montar_teclado())
        corpo.addWidget(self._montar_rodape())

        self._pintar_marcadores()

    # ------------------------------------------------------------------
    # Construtores nomeados -- o ÚNICO lugar que sabe de nível de acesso
    # ------------------------------------------------------------------

    @classmethod
    def para_caixa(cls, auth: AuthService, parent: QWidget | None = None) -> "PinPadDialog":
        """Nível 2 (§3.13): Senha Operacional ou, herdando de cima, a Master."""
        return cls("Caixa", "PIN DE AUTORIZAÇÃO", auth.validar_pin_gerente, parent)

    @classmethod
    def para_loja(cls, auth: AuthService, parent: QWidget | None = None) -> "PinPadDialog":
        """Nível 3 (§3.13): só a Senha Master abre a Central de Loja."""
        return cls("Área da Loja", "PIN DE SUPERVISOR", auth.validar_pin_dono, parent)

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _preparar_botao(self, botao: QPushButton) -> None:
        """Tira o botão da roda de foco e do papel de "botão padrão".

        As duas coisas pela mesma razão: quem lê o teclado é o diálogo, em
        `keyPressEvent`. Com foco num botão, o Enter dispararia aquele botão em
        vez de confirmar, e o Espaço "clicaria" a última tecla usada — bug
        clássico de numpad em Qt.
        """
        botao.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        botao.setAutoDefault(False)
        botao.setDefault(False)
        botao.setCursor(Qt.CursorShape.PointingHandCursor)

    def _montar_cabecalho(self, titulo: str, subtitulo: str) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(12)

        caixa_icone = QFrame()
        caixa_icone.setObjectName("pinPadIcone")
        caixa_icone.setFixedSize(44, 44)
        dentro = QHBoxLayout(caixa_icone)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(_IconeCadeado(), 0, Qt.AlignmentFlag.AlignCenter)
        linha.addWidget(caixa_icone, 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(3)
        textos.addStretch()
        rotulo = QLabel(titulo)
        rotulo.setObjectName("pinPadTitulo")
        textos.addWidget(rotulo)
        sub = QLabel(subtitulo.upper())
        sub.setObjectName("pinPadSubtitulo")
        textos.addWidget(sub)
        textos.addStretch()
        linha.addLayout(textos)
        linha.addStretch()

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("pinPadFechar")
        self._botao_fechar.setFixedSize(32, 32)
        self._botao_fechar.setToolTip("Fechar")
        self._preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignTop)
        return linha

    def _montar_marcadores(self) -> QVBoxLayout:
        coluna = QVBoxLayout()
        coluna.setSpacing(10)

        fila = QHBoxLayout()
        fila.setSpacing(10)
        fila.addStretch()
        for _ in range(self.DOTS_MAXIMOS):
            dot = QFrame()
            dot.setObjectName("pinPadDot")
            dot.setFixedSize(10, 10)
            dot.setProperty("estado", "vazio")
            fila.addWidget(dot)
            self._dots.append(dot)
        fila.addStretch()
        coluna.addLayout(fila)

        # Uma linha só embaixo dos marcadores, que troca de texto e de cor
        # entre a instrução e o aviso de PIN recusado. Duas linhas — uma fixa e
        # outra reservada para o erro — mudariam a altura do cartão no meio da
        # digitação, e cartão que pula de tamanho é o tipo de coisa que faz o
        # dedo errar a tecla.
        self._label_instrucao = QLabel(self.INSTRUCAO)
        self._label_instrucao.setObjectName("pinPadInstrucao")
        self._label_instrucao.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_instrucao.setProperty("estado", "normal")
        coluna.addWidget(self._label_instrucao)
        return coluna

    def _tecla(self, rotulo: str) -> QPushButton:
        botao = QPushButton(rotulo)
        botao.setObjectName("pinPadTecla")
        botao.setMinimumHeight(self.ALTURA_TECLA_PX)
        self._preparar_botao(botao)
        return botao

    def _montar_teclado(self) -> QGridLayout:
        grade = QGridLayout()
        grade.setSpacing(8)

        for indice, digito in enumerate("123456789"):
            botao = self._tecla(digito)
            botao.clicked.connect(self._tecla_clicada)
            grade.addWidget(botao, indice // 3, indice % 3)

        apagar = self._tecla("⌫")
        apagar.setToolTip("Apagar o último dígito")
        apagar.clicked.connect(self._apagar)
        grade.addWidget(apagar, 3, 0)

        zero = self._tecla("0")
        zero.clicked.connect(self._tecla_clicada)
        grade.addWidget(zero, 3, 1)

        self._botao_confirmar = QPushButton("ENTRAR")
        self._botao_confirmar.setObjectName("pinPadConfirmar")
        self._botao_confirmar.setMinimumHeight(self.ALTURA_TECLA_PX)
        self._preparar_botao(self._botao_confirmar)
        self._botao_confirmar.clicked.connect(self._confirmar)
        grade.addWidget(self._botao_confirmar, 3, 2)
        return grade

    def _montar_rodape(self) -> QPushButton:
        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.setObjectName("pinPadCancelar")
        self._preparar_botao(self._botao_cancelar)
        self._botao_cancelar.clicked.connect(self.reject)
        return self._botao_cancelar

    # ------------------------------------------------------------------
    # Digitação (clique e teclado físico entram pelos mesmos três métodos)
    # ------------------------------------------------------------------

    def _tecla_clicada(self) -> None:
        """Digita o rótulo da tecla que disparou o clique.

        Por que `sender()` e não uma `lambda` amarrando o dígito na criação: a
        `lambda` captura `self`, a conexão vive no botão e o botão é filho do
        diálogo — o ciclo se fecha e nem o `gc` do Python nem o Qt o desfazem.
        Medido com a bancada de `test_vazamento_modais.py`, dez aberturas com
        `exec()` e fechamento pelo Cancelar:

            teclas ligadas por lambda        : 10 de 10 diálogos presos à view
            teclas ligadas por método ligado :  0 de 10

        É o §3.14 — "assinar sinal com lambda não dá ao Qt um objeto para
        vigiar" — aparecendo em `clicked` em vez de em `ThemeController.mudou`.
        Com um método ligado, o `self` do outro lado é o que o Qt vigia.
        """
        botao = self.sender()
        if not isinstance(botao, QPushButton):
            return
        rotulo = botao.text()
        # `len(rotulo) == 1` antes do `in`: string vazia é subcadeia de
        # qualquer coisa, e sem isso um botão sem rótulo digitaria "".
        if len(rotulo) == 1 and rotulo in "0123456789":
            self._digitar(rotulo)

    def _digitar(self, digito: str) -> None:
        if len(self._pin) >= self.LIMITE_DE_DIGITOS:
            return
        self._limpar_erro()
        self._pin += digito
        self._pintar_marcadores()

    def _apagar(self) -> None:
        self._limpar_erro()
        self._pin = self._pin[:-1]
        self._pintar_marcadores()

    def _confirmar(self) -> None:
        if not self._pin:
            return
        try:
            self._validar(self._pin)
        except (AcessoNegadoError, NaoAutorizadoError) as erro:
            self._recusar(str(erro))
            return
        self.accept()

    # ------------------------------------------------------------------
    # Estado visual
    # ------------------------------------------------------------------

    def _pintar_marcadores(self, erro: bool = False) -> None:
        """Acende um marcador por dígito, com a fileira elástica entre o piso e
        o teto — e sem repolir o que já está do jeito certo.

        O `unpolish`/`polish` de `aplicar_propriedade` é o que faz o QSS
        reavaliar o widget (§3.15), mas ele não é de graça: sem a comparação
        abaixo seriam doze recálculos de estilo por tecla digitada, num
        Celeron, para mudar um marcador.
        """
        visiveis = max(self.DOTS_MINIMOS, min(len(self._pin), self.DOTS_MAXIMOS))
        for indice, dot in enumerate(self._dots):
            dot.setVisible(indice < visiveis)
            if erro:
                estado = "erro"
            elif indice < len(self._pin):
                estado = "cheio"
            else:
                estado = "vazio"
            if dot.property("estado") != estado:
                aplicar_propriedade(dot, "estado", estado)

    def _recusar(self, mensagem: str) -> None:
        """PIN errado: marcadores em coral, aviso discreto e campo limpo.

        Nada trava e nada fecha — o operador tenta de novo na mesma tela, que é
        o que o balcão exige. O timer só existe para o aviso não ficar aceso na
        tela para sempre se ninguém voltar ao teclado; ele é filho do diálogo e
        morre com ele, e `done()` ainda o para explicitamente.
        """
        self._pin = ""
        self._pintar_marcadores(erro=True)
        self._label_instrucao.setText(mensagem.upper())
        aplicar_propriedade(self._label_instrucao, "estado", "erro")
        self._timer_erro.start(self.MS_ATE_APAGAR_O_ERRO)

    def _limpar_erro(self) -> None:
        if self._label_instrucao.property("estado") != "erro":
            return
        self._timer_erro.stop()
        self._label_instrucao.setText(self.INSTRUCAO)
        aplicar_propriedade(self._label_instrucao, "estado", "normal")
        self._pintar_marcadores()

    # ------------------------------------------------------------------
    # Escurecedor de fundo
    # ------------------------------------------------------------------

    def _montar_backdrop(self) -> None:
        pai = self.parentWidget()
        if pai is None or self._backdrop is not None:
            return
        janela = pai.window()
        self._backdrop = _Backdrop(janela)
        self._backdrop.setGeometry(janela.rect())
        self._backdrop.raise_()
        self._backdrop.show()

    def _descartar_backdrop(self) -> None:
        """Solta o escurecedor do parent AGORA, não quando o Qt passar recolhendo.

        `deleteLater()` sozinho só marca; até o laço de eventos girar, o widget
        continua filho da janela principal — e a janela principal vive o
        processo inteiro. O `setParent(None)` é o que garante que uma tarde de
        idas e voltas à Central de Loja não deixe uma pilha de escurecedores
        invisíveis pendurada no `MainWindow`.
        """
        if self._backdrop is None:
            return
        backdrop, self._backdrop = self._backdrop, None
        backdrop.hide()
        backdrop.setParent(None)
        backdrop.deleteLater()

    # ------------------------------------------------------------------
    # Overrides do Qt
    # ------------------------------------------------------------------

    @nao_deixa_escapar()
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        self._montar_backdrop()
        self.adjustSize()
        self._centralizar_no_pai()
        # O diálogo, e não um botão, é quem lê o teclado (ver `_preparar_botao`).
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _centralizar_no_pai(self) -> None:
        pai = self.parentWidget()
        if pai is None:
            return
        janela = pai.window()
        if not janela.isVisible():
            return
        centro = janela.frameGeometry().center()
        self.move(centro.x() - self.width() // 2, centro.y() - self.height() // 2)

    @nao_deixa_escapar()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        """Entrada híbrida: o teclado físico (ou o numérico USB) faz o mesmo que
        o dedo na tela.

        O Esc cai no `super()` de propósito — lá o `QDialog` o traduz em
        `reject()`, que passa por `done()` e portanto pela mesma limpeza dos
        outros dois caminhos de saída.
        """
        tecla = event.key()
        if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirmar()
            return
        if tecla == Qt.Key.Key_Backspace:
            self._apagar()
            return
        texto = event.text()
        if len(texto) == 1 and texto in "0123456789":
            self._digitar(texto)
            return
        super().keyPressEvent(event)

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única — e por isso o lugar certo da limpeza.

        `accept()` (ENTRAR), `reject()` (Cancelar, o botão de fechar e o Esc) e
        o `closeEvent` passam todos por aqui; `closeEvent` sozinho não, porque
        `done()` faz `hide()`, não `close()` (§3.9 — medido, o `clear()`
        pendurado no `closeEvent` era código morto nos três caminhos que o
        operador usa).

        Três coisas saem juntas: o PIN digitado, o timer do aviso de erro (que
        de outro modo poderia disparar depois do fechamento) e o escurecedor.
        """
        self._pin = ""
        self._timer_erro.stop()
        self._pintar_marcadores()
        self._descartar_backdrop()
        super().done(resultado)
