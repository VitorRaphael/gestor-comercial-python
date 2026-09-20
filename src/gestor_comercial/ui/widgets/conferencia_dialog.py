"""O cartão "Fechar conta para conferência" da mesa (§9.23).

Substitui o `_FecharConferenciaDialog` de fábrica que morava dentro de
`comanda_view.py` — moldura do Windows, um parágrafo de aviso, um `QCheckBox`
"Cobrar taxa de serviço (10%)" e os botões OK/Cancelar do sistema. O garçom
marcava a caixa às cegas: a tela não dizia quanto a mesa ia pagar, e ele só
descobria o total no papel que saía da impressora.

O cartão do mockup do Vitor diz o número ANTES de imprimir: o subtotal dos
itens, a taxa em reais e o total da pré-conta, que muda na hora em que a taxa é
marcada ou desmarcada. É o 12º modal em cartão do app.

## A conta mora no service, não aqui

O cartão recebe um `PreviaDeConferencia` (o instantâneo que
`ComandaService.previa_de_conferencia` monta na abertura) e só MOSTRA as contas
dele — `valor_da_taxa` é a mesma função com que `fechar_para_conferencia` grava
`valor_taxa_servico`, o número que o cupom imprime e o fechamento do dia soma.
Clicar na taxa não toca no banco: é conta sobre o instantâneo, e um teste conta
zero SQL em cem cliques.

## Quem decide a taxa é a Central de Loja, não este cartão (§9.25)

O cartão **não pergunta nada**. Com a loja cobrando a taxa (o interruptor da
tela de Configurações), o bloco aparece dizendo que ela está na conta, e o total
já vem com ela; com a loja sem taxa, o bloco não é escondido: ele **não é
criado**, e o total é o subtotal.

A caixinha que se marcava viveu um dia. Ela nasceu no §9.23 (por pedido, e
desmarcada por pedido) e saiu no §9.25, também por pedido: "deixa de existir
como etapa de escolha do operador". A conta do salão passou a ser uma regra da
loja, decidida uma vez pelo dono, e não uma pergunta feita ao garçom em toda
mesa — que é onde a taxa era esquecida ou cobrada por engano.

O que o cartão devolve é o percentual a congelar na comanda (`resultado()`), ou
`None`; o valor em reais quem grava é o service, na mesma conta que a prévia
mostrou. E quem recusa a taxa com a loja desligada continua sendo o service
(`fechar_para_conferencia`), que confere a regra outra vez na hora de gravar: o
cartão é uma foto tirada na abertura.

## Teclado

Enter fecha e imprime, Esc cancela. Os botões não entram na roda de foco
(`cartao_modal.preparar_botao`): quem lê o teclado é o diálogo.

## Ciclo de vida (o RNF do Celeron, §3.2/§3.9/§3.14)

O pedido escrito falava em `destroy()` e em desfazer atalhos. Os equivalentes:

* **destroy** — quem destrói é `executar_modal()` (§3.2), com `deleteLater()`
  depois de a view ler `resultado()`. Os filhos morrem com o cartão; o único
  widget que não é filho dele é o **escurecedor**, filho da janela, e por isso
  `done()` o solta na hora;
* **atalhos** — nenhum `QShortcut`: quem lê Enter, Esc e Espaço é o
  `keyPressEvent` do próprio diálogo, e não há nada registrado fora dele para
  sobrar depois;
* **sinais** — as três ligações saem uma a uma em `_soltar_recursos()`,
  nenhuma é `lambda`, e a trava `_limpo` torna a limpeza idempotente;
* **timers** — nenhum.

Cartão de **uma abertura só** (`executar_modal`, nunca `while modal.exec()`): a
limpeza em `done()` desliga os botões.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QKeyEvent, QPainter, QPaintEvent, QShowEvent
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
from gestor_comercial.services.comanda_service import PreviaDeConferencia
from gestor_comercial.services.formatador_cupom import percentual
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.cores import cor_do_token
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_ARQUIVO_TEXTO,
    GLIFO_CADEADO,
    GLIFO_DOCUMENTO_VISTO,
    GLIFO_ESCUDO,
    GLIFO_IMPRESSORA,
    GLIFO_VISTO,
    BotaoComGlifo,
    GlifoSolto,
    desenhar_glifo,
)
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado

SUBTITULO = "Revise os valores antes de imprimir a pré-conta."
AVISO_TEXTO = (
    "Novos itens serão bloqueados e a pré-conta será impressa. "
    "Para desfazer, use “Reabrir” com o PIN de gerente."
)


def _onde(previa: PreviaDeConferencia) -> tuple[str, str]:
    """Como o cartão chama a conta: ("MESA 12", "mesa") ou ("BALCÃO", "comanda").

    A comanda de balcão também passa por aqui (o "Fechar conta" é o mesmo), e
    "A mesa ficará em conferência" sobre uma comanda sem mesa seria o cartão
    dizendo uma coisa que não existe.
    """
    if previa.mesa_numero is None:
        return "BALCÃO", "comanda"
    return f"MESA {previa.mesa_numero}", "mesa"


class _MarcaDaTaxa(QWidget):
    """O selo da taxa: quadradinho âmbar com o visto, dizendo que ela está na conta.

    Era a caixinha que se marcava (§9.23) e virou selo no §9.25, quando a
    escolha saiu: o desenho ficou, porque é ele que diz num relance "a taxa
    está aqui dentro". Pintado, e não um `QCheckBox`, pelo motivo do
    `Interruptor`: o indicador do Qt não faz caixa cheia com o visto do app, e a
    cor tem que ser lida a cada pintura para acompanhar o alternador de tema
    (§3.15).
    """

    LADO_PX = 22
    RAIO_PX = 6.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("confDialogMarca")
        self.setFixedSize(self.LADO_PX, self.LADO_PX)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        tokens = ThemeController.instancia().tokens_atuais
        area = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(cor_do_token(tokens["conferencia_mesa_marca_bg"]))
        pintor.drawRoundedRect(area, self.RAIO_PX, self.RAIO_PX)
        miolo = area.adjusted(4.0, 4.0, -4.0, -4.0)
        desenhar_glifo(
            pintor, GLIFO_VISTO, miolo, cor_do_token(tokens["conferencia_mesa_marca_glifo"]), 3.0
        )
        pintor.end()


class _CartaoTaxa(QFrame):
    """A linha da taxa de serviço: o selo, o texto e o valor que está na conta.

    Não recebe clique nenhum desde o §9.25 — é informação, não controle.
    """

    def __init__(self, previa: PreviaDeConferencia, onde: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("confDialogTaxa")

        linha = QHBoxLayout(self)
        linha.setContentsMargins(16, 14, 18, 14)
        linha.setSpacing(14)

        self.marca = _MarcaDaTaxa()
        linha.addWidget(self.marca, 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setSpacing(3)
        titulo = QLabel("Taxa de serviço incluída")
        titulo.setObjectName("confDialogTaxaTitulo")
        textos.addWidget(titulo)
        descricao = QLabel(f"{percentual(previa.taxa_percentual)}% sobre o consumo da {onde}")
        descricao.setObjectName("confDialogTaxaDescricao")
        textos.addWidget(descricao)
        linha.addLayout(textos, 1)

        self.valor = QLabel(formatar_reais(previa.valor_da_taxa))
        self.valor.setObjectName("confDialogTaxaValor")
        self.valor.setProperty("cobrada", True)
        linha.addWidget(self.valor, 0, Qt.AlignmentFlag.AlignVCenter)


class ConferenciaMesaDialog(QDialog):
    """Cartão de fechamento da conta para conferência, com a prévia da pré-conta."""

    # A largura da imagem do mockup. O rodapé mais largo ("AÇÃO SEGURA" +
    # "Cancelar" + "Fechar e imprimir") pede ~440px com a fonte da marca, e os
    # dois cartões de valor lado a lado são o que pede a largura toda.
    LARGURA_CARTAO_PX = 576
    LADO_BOTAO_FECHAR_PX = 32
    LADO_BADGE_PX = 44

    def __init__(self, previa: PreviaDeConferencia, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._previa = previa
        self._backdrop: Backdrop | None = None
        self._limpo = False
        self._contexto, self._onde = _onde(previa)

        self.setObjectName("confDialog")
        self.setWindowTitle("Fechar conta para conferência")
        # Sem moldura do sistema: o cabeçalho é do cartão, e o fundo translúcido
        # é o que faz os cantos de 16px saírem redondos de verdade.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        # Não há campo: é o próprio diálogo que recebe o foco e lê o teclado.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)

        cartao = QFrame()
        cartao.setObjectName("confDialogCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(0, 0, 0, 0)
        corpo.setSpacing(0)
        corpo.addWidget(self._montar_cabecalho())
        corpo.addWidget(self._divisor())
        corpo.addWidget(self._montar_corpo())
        corpo.addWidget(self._divisor())
        corpo.addWidget(self._montar_rodape())

    # ------------------------------------------------------------------
    # O que a view lê
    # ------------------------------------------------------------------

    def resultado(self) -> Decimal | None:
        """O percentual que `fechar_para_conferencia` vai congelar na comanda.

        `None` com a loja sem taxa — nunca zero, que é como a comanda aberta já
        nasce e o que faz o cupom omitir a linha.
        """
        return self._previa.percentual_a_gravar

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _divisor(self) -> QFrame:
        linha = QFrame()
        linha.setObjectName("confDialogDivisor")
        linha.setFixedHeight(1)
        return linha

    def _montar_cabecalho(self) -> QWidget:
        faixa = QWidget()
        faixa.setObjectName("confDialogCabecalho")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(24, 20, 20, 20)
        linha.setSpacing(16)

        badge = QFrame()
        badge.setObjectName("confDialogBadge")
        badge.setFixedSize(self.LADO_BADGE_PX, self.LADO_BADGE_PX)
        dentro = QHBoxLayout(badge)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(
            GlifoSolto(GLIFO_DOCUMENTO_VISTO, 20, "conferencia_mesa_badge_glifo"),
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        linha.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(4)
        self._secao = QLabel(f"{self._contexto} · CONFERÊNCIA")
        self._secao.setObjectName("confDialogSecao")
        textos.addWidget(self._secao)
        self._titulo = QLabel("Fechar conta para conferência")
        self._titulo.setObjectName("confDialogTitulo")
        textos.addWidget(self._titulo)
        self._subtitulo = QLabel(SUBTITULO)
        self._subtitulo.setObjectName("confDialogSubtitulo")
        textos.addWidget(self._subtitulo)
        linha.addLayout(textos, 1)

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("confDialogFechar")
        self._botao_fechar.setFixedSize(self.LADO_BOTAO_FECHAR_PX, self.LADO_BOTAO_FECHAR_PX)
        self._botao_fechar.setToolTip("Fechar (Esc)")
        cartao_modal.preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignTop)
        return faixa

    def _montar_corpo(self) -> QWidget:
        """A faixa pontilhada do meio: os dois valores, a taxa e o aviso.

        `PainelPontilhado` pela mesma razão do §9.12 e do §9.18: é a textura que
        o mockup mostra atrás do conteúdo.
        """
        faixa = PainelPontilhado()
        faixa.setObjectName("confDialogCorpo")
        coluna = QVBoxLayout(faixa)
        coluna.setContentsMargins(24, 22, 24, 22)
        coluna.setSpacing(14)

        valores = QHBoxLayout()
        valores.setSpacing(12)
        subtotal, self._valor_subtotal = self._cartao_de_valor(
            "confDialogSubtotal",
            GLIFO_ARQUIVO_TEXTO,
            "conferencia_mesa_rotulo",
            "SUBTOTAL",
            "confDialogValor",
        )
        self._valor_subtotal.setText(formatar_reais(self._previa.subtotal))
        valores.addWidget(subtotal, 1)
        total, self._valor_total = self._cartao_de_valor(
            "confDialogTotal",
            GLIFO_VISTO,
            "conferencia_mesa_total_texto",
            "TOTAL DA PRÉ-CONTA",
            "confDialogValorTotal",
        )
        self._valor_total.setText(formatar_reais(self._previa.total))
        valores.addWidget(total, 1)
        coluna.addLayout(valores)

        # Loja sem taxa: o bloco NÃO É CRIADO, e não só escondido (a forma do
        # modo componente do §9.15). Nenhum widget invisível ocupando memória.
        self._cartao_taxa: _CartaoTaxa | None = None
        if self._previa.oferece_taxa:
            self._cartao_taxa = _CartaoTaxa(self._previa, self._onde)
            coluna.addWidget(self._cartao_taxa)

        coluna.addWidget(self._montar_aviso())
        return faixa

    def _cartao_de_valor(
        self, nome_do_cartao: str, glifo: str, token_glifo: str, rotulo: str, nome_do_valor: str
    ) -> tuple[QFrame, QLabel]:
        """Um dos dois cartões de cima: o glifo, o rótulo em caixa alta e o valor.

        Uma função para os dois — subtotal e total são a mesma peça com outra
        moldura, e a moldura vem do QSS pelo nome do objeto.
        """
        cartao = QFrame()
        cartao.setObjectName(nome_do_cartao)
        coluna = QVBoxLayout(cartao)
        coluna.setContentsMargins(16, 16, 16, 16)
        coluna.setSpacing(10)

        topo = QHBoxLayout()
        topo.setSpacing(8)
        topo.addWidget(GlifoSolto(glifo, 14, token_glifo), 0, Qt.AlignmentFlag.AlignVCenter)
        etiqueta = QLabel(rotulo)
        etiqueta.setObjectName(f"{nome_do_cartao}Rotulo")
        topo.addWidget(etiqueta, 1)
        coluna.addLayout(topo)

        valor = QLabel()
        valor.setObjectName(nome_do_valor)
        coluna.addWidget(valor)
        return cartao, valor

    def _montar_aviso(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("confDialogAviso")
        linha = QHBoxLayout(painel)
        linha.setContentsMargins(16, 14, 16, 16)
        linha.setSpacing(12)
        linha.addWidget(
            GlifoSolto(GLIFO_CADEADO, 18, "conferencia_mesa_aviso_glifo"),
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        textos = QVBoxLayout()
        textos.setSpacing(6)
        self._aviso_titulo = QLabel(f"A {self._onde} ficará em conferência")
        self._aviso_titulo.setObjectName("confDialogAvisoTitulo")
        self._aviso_titulo.setWordWrap(True)
        textos.addWidget(self._aviso_titulo)
        self._aviso_texto = QLabel(AVISO_TEXTO)
        self._aviso_texto.setObjectName("confDialogAvisoTexto")
        self._aviso_texto.setWordWrap(True)
        textos.addWidget(self._aviso_texto)
        linha.addLayout(textos, 1)
        return painel

    def _montar_rodape(self) -> QWidget:
        faixa = QWidget()
        faixa.setObjectName("confDialogRodape")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(24, 16, 24, 18)
        linha.setSpacing(12)

        linha.addWidget(
            GlifoSolto(GLIFO_ESCUDO, 15, "conferencia_mesa_seguro_glifo"),
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        seguro = QLabel("AÇÃO SEGURA")
        seguro.setObjectName("confDialogSeguro")
        linha.addWidget(seguro, 0, Qt.AlignmentFlag.AlignVCenter)
        linha.addStretch()

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.setObjectName("confDialogCancelar")
        cartao_modal.preparar_botao(self._botao_cancelar)
        self._botao_cancelar.clicked.connect(self.reject)
        linha.addWidget(self._botao_cancelar)

        self._botao_confirmar = BotaoComGlifo(
            "Fechar e imprimir", GLIFO_IMPRESSORA, "acento_texto", "pilula_disabled_texto"
        )
        self._botao_confirmar.setObjectName("confDialogConfirmar")
        cartao_modal.preparar_botao(self._botao_confirmar)
        self._botao_confirmar.clicked.connect(self.accept)
        linha.addWidget(self._botao_confirmar)
        return faixa

    # ------------------------------------------------------------------
    # Overrides do Qt
    # ------------------------------------------------------------------

    @nao_deixa_escapar()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        """Enter fecha e imprime; Esc cancela.

        O Esc cai no `super()`: lá o `QDialog` o traduz em `reject()`, que passa
        por `done()` e pela mesma limpeza dos outros caminhos de saída.
        """
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
            return
        super().keyPressEvent(event)

    @nao_deixa_escapar()
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        self._backdrop = cartao_modal.apresentar(self, self._backdrop)
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única — Fechar e imprimir, Cancelar, ✕, Enter e Esc passam
        todos por aqui. `closeEvent` sozinho não serviria: `done()` faz `hide()`,
        não `close()` (§3.9)."""
        self._soltar_recursos()
        super().done(resultado)

    def _soltar_recursos(self) -> None:
        """Desliga o que este cartão ligou — e só uma vez.

        As três ligações de sinal saem nominalmente, e o escurecedor é solto da
        janela agora (ele é o único widget que o Qt não recolheria junto com o
        cartão). A trava `_limpo` é a do §9.12: o segundo `disconnect` não
        estoura nesta versão do PySide6, mas imprime um `RuntimeWarning` por
        ligação.
        """
        if self._limpo:
            return
        self._limpo = True
        self._botao_fechar.clicked.disconnect(self.reject)
        self._botao_cancelar.clicked.disconnect(self.reject)
        self._botao_confirmar.clicked.disconnect(self.accept)
        backdrop, self._backdrop = self._backdrop, None
        cartao_modal.descartar(backdrop)
