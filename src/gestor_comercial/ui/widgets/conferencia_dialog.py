"""O cartão "Fechar conta para conferência" da mesa (§9.23).

Substitui o `_FecharConferenciaDialog` de fábrica que morava dentro de
`comanda_view.py` — moldura do Windows, um parágrafo de aviso, um `QCheckBox`
"Cobrar taxa de serviço (10%)" e os botões OK/Cancelar do sistema. O garçom
marcava a caixa às cegas: a tela não dizia quanto a mesa ia pagar, e ele só
descobria o total no papel que saía da impressora.

O cartão do mockup do Vitor diz o número ANTES de imprimir. É o 12º modal em
cartão do app.

## A conta mora no service, não aqui

O cartão recebe um `PreviaDeConferencia` (o instantâneo que
`ComandaService.previa_de_conferencia` monta na abertura) e só MOSTRA o número
dele. Não toca no banco: um teste conta zero SQL com o cartão aberto.

## O que a taxa de serviço deixou aqui (§9.26)

Entre o §9.23 e o §9.26 este cartão mostrava três números — subtotal, taxa e
total — e devolvia à view o percentual a congelar na comanda. A taxa foi
removida do sistema: o cartão mostra UM número, o total da pré-conta, e não
devolve nada além do "confirmou" do `QDialog`.

Ele continua existindo, e essa foi uma decisão do Vitor no §9.25, perguntada
entre "um clique sem tela nenhuma" e "o cartão só confirma": fechar a conta
trava os itens e só o PIN de gerente reabre, e um clique errado não pode fazer
isso sem perguntar.

O selo da taxa morreu duas mortes. Nasceu caixinha marcável no §9.23,
virou selo informativo no §9.25 ("deixa de existir como etapa de escolha do
operador") e saiu de vez no §9.26, com a cobrança.

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

from PySide6.QtCore import Qt
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
from gestor_comercial.services.comanda_service import PreviaDeConferencia
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_CADEADO,
    GLIFO_DOCUMENTO_VISTO,
    GLIFO_ESCUDO,
    GLIFO_IMPRESSORA,
    GLIFO_VISTO,
    BotaoComGlifo,
    GlifoSolto,
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
        """A faixa pontilhada do meio: o total da pré-conta e o aviso.

        `PainelPontilhado` pela mesma razão do §9.12 e do §9.18: é a textura que
        o mockup mostra atrás do conteúdo.

        UM cartão de valor, e não dois (§9.26): sem a taxa, o subtotal dos itens
        e o total da pré-conta são o MESMO número, e dois cartões lado a lado
        repetindo-o fariam o garçom procurar a diferença entre eles.
        """
        faixa = PainelPontilhado()
        faixa.setObjectName("confDialogCorpo")
        coluna = QVBoxLayout(faixa)
        coluna.setContentsMargins(24, 22, 24, 22)
        coluna.setSpacing(14)

        total, self._valor_total = self._cartao_de_valor(
            "confDialogTotal",
            GLIFO_VISTO,
            "conferencia_mesa_total_texto",
            "TOTAL DA PRÉ-CONTA",
            "confDialogValorTotal",
        )
        self._valor_total.setText(formatar_reais(self._previa.total))
        coluna.addWidget(total)

        coluna.addWidget(self._montar_aviso())
        return faixa

    def _cartao_de_valor(
        self, nome_do_cartao: str, glifo: str, token_glifo: str, rotulo: str, nome_do_valor: str
    ) -> tuple[QFrame, QLabel]:
        """O cartão do valor: o glifo, o rótulo em caixa alta e o número.

        Continua parametrizado, e com um só chamador: a moldura vem do QSS pelo
        nome do objeto, e é isso que mantém a peça fácil de repetir se um
        segundo valor voltar a existir.
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
