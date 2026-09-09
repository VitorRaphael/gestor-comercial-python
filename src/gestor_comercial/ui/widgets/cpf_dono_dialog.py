"""Modal "Confirmar identidade": o CPF do Dono como chave para ver um segredo.

**Oitavo modal em cartão do app**, e o segundo que autentica (o primeiro é o
`pin_pad_dialog`). Abre quando alguém clica no olho de uma das quatro linhas de
"Senhas e Acesso" (§3.13) e é a única barreira entre um clique e a senha da
loja aparecendo na tela.

## Por que um cartão com teclado, e não um campo de texto

Mesmo motivo do §9.6/§9.7: quem opera está de pé, com a mão ocupada, e o
teclado físico fica atrás do monitor. E o CPF são onze dígitos — exatamente o
tipo de coisa que se erra digitando e não se descobre porque o campo está
mascarado. Aqui o visor mostra `123.4••.•••-••` enquanto se digita, com a
pontuação já no lugar: o dono confere o que digitou antes de confirmar, e o
`•` marca o que ainda falta.

## O que este diálogo NÃO faz

Não compara nada. Ele coleta onze dígitos e entrega a string ao **validador**
que recebeu — na prática `LojaConfigService.revelar`, que confere o CPF contra
o cadastrado e devolve o segredo. Se o validador levantar, o cartão fica aberto
e mostra o motivo; se passar, o valor devolvido fica em `resultado()`. Trocar a
regra continua sendo trabalho de uma linha no service.

## Ciclo de vida (§3.2/§3.9, e o RNF do Celeron)

* **destroy** — quem abre passa por `executar_modal()`, que descarta a
  instância depois de ler o resultado;
* **unbind** — nenhum `connect` usa `lambda` (§3.14): tudo liga um filho a um
  método deste diálogo, a conexão vive no filho e o filho morre com o pai. O
  `TecladoNumerico` ainda solta a própria tabela de teclas no `done()`;
* **timers** — um só, o que apaga o aviso de erro. `done()` o para
  explicitamente, para nada agendado sobreviver ao fechamento — e `done()` é a
  saída única (Visualizar, Cancelar, o ✕ e o Esc passam todos por lá).

O CPF digitado é zerado no `done()` pelo mesmo motivo pelo qual o
`pin_pad_dialog` zera o PIN: um diálogo fechado não deve continuar carregando a
credencial que recebeu.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RegraDeNegocioError,
)
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.icone_olho import IconeOlho
from gestor_comercial.ui.widgets.teclado_numerico import TecladoNumerico

# Recebe os 11 dígitos e devolve o valor revelado; levanta quando o CPF não
# confere ou quando não há cópia daquele segredo.
Revelador = Callable[[str], str]

DIGITOS_DO_CPF = 11
# Onde a pontuação entra, contada em dígitos já digitados. É a máscara
# `•••.•••.•••-••` descrita de um jeito que o formatador consegue percorrer.
_PONTUACAO = {3: ".", 6: ".", 9: "-"}
_VAGO = "•"

_ERROS_ESPERADOS = (RegraDeNegocioError, AcessoNegadoError, NaoAutorizadoError)


def formatar_cpf_parcial(digitos: str) -> str:
    """`"1234"` → `"123.4••.•••-••"`. Sempre 14 caracteres, sempre pontuado.

    Função de módulo, e testável sem tela, porque é a única regra do visor: um
    erro aqui é o dono conferindo um CPF que não é o que ele digitou.
    """
    partes = []
    for indice in range(DIGITOS_DO_CPF):
        if indice in _PONTUACAO:
            partes.append(_PONTUACAO[indice])
        partes.append(digitos[indice] if indice < len(digitos) else _VAGO)
    return "".join(partes)


class CpfDonoDialog(QDialog):
    """Cartão que pede o CPF do Dono para revelar um segredo da loja."""

    LARGURA_CARTAO_PX = 400
    LADO_BOTAO_FECHAR_PX = 32
    MS_ATE_APAGAR_O_ERRO = 3500

    INSTRUCAO = "DIGITE O CPF DO DONO"

    def __init__(
        self,
        rotulo_do_segredo: str,
        revelador: Revelador,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._revelar = revelador
        self._digitos = ""
        self._revelado: str | None = None
        self._backdrop: Backdrop | None = None

        self.setObjectName("cpfDialog")
        self.setWindowTitle("Confirmar identidade")
        # Sem moldura do sistema: o cabeçalho é do cartão, e o fundo translúcido
        # é o que faz os cantos de 16px saírem redondos de verdade.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        self._timer_erro = QTimer(self)
        self._timer_erro.setSingleShot(True)
        self._timer_erro.timeout.connect(self._limpar_erro)

        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)

        cartao = QFrame()
        cartao.setObjectName("cpfDialogCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(22, 18, 22, 18)
        corpo.setSpacing(14)
        corpo.addLayout(self._montar_cabecalho())
        corpo.addWidget(self._montar_contexto(rotulo_do_segredo))
        corpo.addLayout(self._montar_visor())
        corpo.addWidget(self._montar_teclado())
        corpo.addLayout(self._montar_acoes())

        self._pintar_visor()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar_cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(12)

        selo = QFrame()
        selo.setObjectName("cpfDialogIcone")
        selo.setFixedSize(42, 42)
        dentro = QHBoxLayout(selo)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(IconeOlho(), 0, Qt.AlignmentFlag.AlignCenter)
        linha.addWidget(selo, 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(3)
        titulo = QLabel("Confirmar identidade")
        titulo.setObjectName("cpfDialogTitulo")
        textos.addWidget(titulo)
        subtitulo = QLabel("CPF DO DONO")
        subtitulo.setObjectName("cpfDialogSubtitulo")
        textos.addWidget(subtitulo)
        linha.addLayout(textos, 1)

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("cpfDialogFechar")
        self._botao_fechar.setFixedSize(self.LADO_BOTAO_FECHAR_PX, self.LADO_BOTAO_FECHAR_PX)
        self._botao_fechar.setToolTip("Fechar (Esc)")
        cartao_modal.preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignTop)
        return linha

    def _montar_contexto(self, rotulo_do_segredo: str) -> QFrame:
        """QUAL segredo está prestes a aparecer.

        O olho é o mesmo desenho nas quatro linhas de "Senhas e Acesso", e o
        cartão abre igual nas quatro: sem esta faixa, quem clicou por engano na
        linha de cima confirmaria a identidade sem nunca saber que estava
        pedindo outra coisa.
        """
        painel = QFrame()
        painel.setObjectName("cpfDialogContexto")
        linha = QHBoxLayout(painel)
        linha.setContentsMargins(14, 11, 14, 11)
        linha.setSpacing(10)

        rotulo = QLabel("VISUALIZAR")
        rotulo.setObjectName("cpfDialogRotulo")
        linha.addWidget(rotulo)

        alvo = QLabel(rotulo_do_segredo.upper())
        alvo.setObjectName("cpfDialogAlvo")
        alvo.setWordWrap(True)
        linha.addWidget(alvo, 1)
        return painel

    def _montar_visor(self) -> QVBoxLayout:
        coluna = QVBoxLayout()
        coluna.setSpacing(8)

        self._visor = QLabel()
        self._visor.setObjectName("cpfDialogVisor")
        self._visor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        coluna.addWidget(self._visor)

        # Uma linha só, que troca entre instrução e erro — como no
        # `pin_pad_dialog`, e pelo mesmo motivo: duas linhas (uma fixa e outra
        # reservada ao erro) mudariam a altura do cartão no meio da digitação, e
        # cartão que pula de tamanho faz o dedo errar a tecla.
        self._instrucao = QLabel(self.INSTRUCAO)
        self._instrucao.setObjectName("cpfDialogInstrucao")
        self._instrucao.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._instrucao.setWordWrap(True)
        self._instrucao.setProperty("estado", "normal")
        coluna.addWidget(self._instrucao)
        return coluna

    def _montar_teclado(self) -> QWidget:
        self._teclado = TecladoNumerico()
        self._teclado.digitou.connect(self._digitar)
        self._teclado.apagou.connect(self._apagar)
        return self._teclado

    def _montar_acoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(10)

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.setObjectName("cpfDialogCancelar")
        cartao_modal.preparar_botao(self._botao_cancelar)
        self._botao_cancelar.clicked.connect(self.reject)
        linha.addWidget(self._botao_cancelar, 1)

        self._botao_confirmar = QPushButton("Visualizar")
        self._botao_confirmar.setObjectName("cpfDialogConfirmar")
        cartao_modal.preparar_botao(self._botao_confirmar)
        self._botao_confirmar.clicked.connect(self._confirmar)
        linha.addWidget(self._botao_confirmar, 1)
        return linha

    # ------------------------------------------------------------------
    # Digitação
    # ------------------------------------------------------------------

    def _digitar(self, digitos: str) -> None:
        """Empurra dígitos pela direita, até os onze do CPF.

        A tecla `00` do teclado compartilhado manda dois de uma vez: com dez
        dígitos no visor, entra o que cabe e o outro é descartado — o teto é do
        CPF, não da tecla.
        """
        if len(self._digitos) >= DIGITOS_DO_CPF:
            return
        self._limpar_erro()
        self._digitos = (self._digitos + digitos)[:DIGITOS_DO_CPF]
        self._pintar_visor()

    def _apagar(self) -> None:
        self._limpar_erro()
        self._digitos = self._digitos[:-1]
        self._pintar_visor()

    def _pintar_visor(self) -> None:
        self._visor.setText(formatar_cpf_parcial(self._digitos))
        # O botão só liga com o CPF inteiro: onze dígitos é a única quantidade
        # que o service aceita, e um "Visualizar" que só pode dar erro é pior
        # que um botão desligado.
        self._botao_confirmar.setEnabled(len(self._digitos) == DIGITOS_DO_CPF)

    def _confirmar(self) -> None:
        if len(self._digitos) != DIGITOS_DO_CPF:
            return
        try:
            self._revelado = self._revelar(self._digitos)
        except _ERROS_ESPERADOS as erro:
            self._recusar(str(erro))
            return
        self.accept()

    def _recusar(self, mensagem: str) -> None:
        """CPF recusado: aviso na linha de instrução e visor limpo.

        Nada trava e nada fecha — quem errou um dígito tenta de novo na mesma
        tela. O timer só existe para o aviso não ficar aceso para sempre; ele é
        filho do diálogo e morre com ele, e `done()` ainda o para
        explicitamente.
        """
        self._digitos = ""
        self._pintar_visor()
        self._instrucao.setText(mensagem.upper())
        aplicar_propriedade(self._instrucao, "estado", "erro")
        self._timer_erro.start(self.MS_ATE_APAGAR_O_ERRO)

    def _limpar_erro(self) -> None:
        if self._instrucao.property("estado") != "erro":
            return
        self._timer_erro.stop()
        self._instrucao.setText(self.INSTRUCAO)
        aplicar_propriedade(self._instrucao, "estado", "normal")

    def resultado(self) -> str | None:
        """O valor revelado, ou `None` se o cartão foi fechado sem confirmar.

        Lido depois do `exec()`, como em todo modal do app. `done()` não o
        apaga de propósito (o oposto do PIN, e pelo mesmo motivo do §9.6:
        `resultado()` é lido DEPOIS do `exec()`); quem o tira da memória é o
        descarte da instância inteira, em `executar_modal`.
        """
        return self._revelado

    # ------------------------------------------------------------------
    # Overrides do Qt
    # ------------------------------------------------------------------

    @nao_deixa_escapar()
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        if self._backdrop is None:
            self._backdrop = cartao_modal.montar(self)
        self.adjustSize()
        cartao_modal.centralizar_no_pai(self)
        # O diálogo, e não um botão, é quem lê o teclado
        # (ver `cartao_modal.preparar_botao`).
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    @nao_deixa_escapar()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        """O teclado físico (ou o numérico USB) faz o mesmo que o dedo na tela.

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
        texto = event.text()
        if len(texto) == 1 and texto.isdigit():
            self._digitar(texto)
            return
        super().keyPressEvent(event)

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única — e por isso o lugar certo da limpeza.

        Visualizar, Cancelar, o ✕ e o Esc passam todos por aqui; `closeEvent`
        sozinho não serviria, porque `done()` faz `hide()`, não `close()`
        (§3.9). Saem juntos: os dígitos digitados, o timer do aviso (que de
        outro modo poderia disparar depois do fechamento), a tabela de teclas
        do teclado e o escurecedor, que é filho da JANELA e não do diálogo.
        """
        self._digitos = ""
        self._timer_erro.stop()
        self._teclado.soltar()
        backdrop, self._backdrop = self._backdrop, None
        cartao_modal.descartar(backdrop)
        super().done(resultado)
