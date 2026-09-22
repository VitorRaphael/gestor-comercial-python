"""Modal de fechamento do caixa: as duas contagens, às cegas — §9.7.

Substitui o `_FecharCaixaDialog` que morava dentro de `caixa_view.py` — três
`QLineEdit` num `QFormLayout` com a moldura de janela do sistema, onde as duas
contagens eram digitadas como texto e lidas de volta por `safe_decimal` com
`padrao=None`. O `padrao=None` estava certo e continua certo pelo motivo que a
própria view documentava: num fechamento, ler "não consegui entender o que ele
contou" como "ele contou zero" inventaria uma diferença do tamanho do turno.

Só que aquilo tratava o sintoma. O que este modal faz é tirar a possibilidade:
as contagens entram por numpad, em centavos pela direita, e não existe texto
para ler de volta. `safe_decimal` continua existindo e continua certo — ele
resolve o problema de *ler* o que foi digitado, e aqui não há o que ler.

## Esta é a tela mais cara do sistema

O fechamento é o único momento em que a gaveta física e o banco de dados se
encontram. Um número errado aqui não aparece como tela feia: aparece como
quebra de caixa no relatório impresso, no fim da noite, com o turno já
encerrado e ninguém conseguindo explicar. Daí três decisões:

1. **Fechamento cego (blind closing).** O operador informa só o que contou —
   o modal não recebe, não mostra e não calcula o esperado nem a diferença.
   Antes havia "Esperado R$ X" em cada linha, um cartão de diferença ao vivo e
   um botão "preencher valores esperados": juntos, eles permitiam ajustar a
   contagem até a diferença zerar, ou fechar sem contar a gaveta. A conferência
   (contado − esperado) acontece só no `CaixaService.fechar`, na gravação, e
   aparece no relatório impresso do gerente.
2. **O teclado tem um destino só por vez, e ele é dito em voz alta.** O rótulo
   da direita alterna entre `DIGITANDO DINHEIRO` e `DIGITANDO MAQUININHAS`, e o
   cartão ativo fica com o anel aceso. Sem isso, o operador digita o extrato da
   maquininha por cima da contagem da gaveta e nada avisa.
## O que NÃO mudou

**Nenhuma regra financeira, e nenhuma gravação nova.** O diálogo não conhece
`CaixaService`: devolve um `DadosFechamento` (dinheiro + maquininha +
observação) e a `CaixaView` chama
`fechar(caixa_id, valor_contado_dinheiro, valor_contado_maquininha, observacao)`
— mesma assinatura, mesmo tipo, mesma ordem. Quem exige gerente continua sendo
o service, quem recusa valor negativo continua sendo o service, quem barra o
fechamento com comanda em aberto continua sendo o service, e quem numera o
turno do dia continua sendo o service. A impressão do comprovante continua
saindo pelo mesmo caminho de sempre na view (`executar_impressao`, isolado pelo
disjuntor de §3.12) — **depois** do fechamento, para que impressora quebrada
nunca impeça o caixa de fechar.

"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.cartao_de_turno import (
    PAPEL_FECHAMENTO,
    CartaoDeTurnoDialog,
    IconeDeGaveta,
)
from gestor_comercial.ui.widgets.teclado_numerico import AcumuladorDeCentavos

# Desenhos possíveis dos ícones das linhas (ver `_IconeConferencia`). São nomes
# de forma, e não de conteúdo, porque é a forma que o `QPainter` escolhe.
GLIFO_CEDULA = "cedula"
GLIFO_CARTAO = "cartao"
TOKEN_GLIFO_BADGE = "caixa_fechamento_glifo"

@dataclass(frozen=True, slots=True)
class Contagem:
    """Tudo o que separa a contagem da gaveta da contagem da maquininha.

    Numa linha só, pelo mesmo critério de `OPERACOES` (§9.6) e `CARGOS` (§9.5):
    enquanto forem duas montagens paralelas, uma pode mudar sozinha — e as duas
    aparecem em três lugares cada (o cartão, o rótulo do teclado e a ordem do
    `Tab`).
    """

    titulo: str
    glifo: str
    token_glifo: str
    rotulo_teclado: str


# As duas contagens físicas do fechamento, na ordem em que o `Tab` as percorre.
# São duas e não uma porque a gaveta e o extrato da maquininha são conferências
# independentes (cada uma com o próprio esperado e a própria diferença, ambos
# apurados só no service) — foi o que a migração `b7c9e2f14a03` separou no banco.
CONTAGENS: tuple[Contagem, ...] = (
    Contagem(
        titulo="Dinheiro na gaveta",
        glifo=GLIFO_CEDULA,
        token_glifo="conferencia_dinheiro",
        rotulo_teclado="DIGITANDO DINHEIRO",
    ),
    Contagem(
        titulo="Vendas nas maquininhas",
        glifo=GLIFO_CARTAO,
        token_glifo="conferencia_maquininha",
        rotulo_teclado="DIGITANDO MAQUININHAS",
    ),
)


@dataclass(frozen=True, slots=True)
class DadosFechamento:
    """O que o modal devolve. A view leva isto para `CaixaService.fechar`."""

    dinheiro: Decimal
    maquininha: Decimal
    observacao: str | None


class _IconeConferencia(QWidget):
    """Cédula e cartão, desenhados à mão.

    Mesma decisão do cadeado do PIN, da lupa do §9.4, do usuário do §9.5 e das
    setas do §9.6: o glifo equivalente cai no Segoe UI Emoji, sai colorido e
    chapado e ignora o tema — e a máquina limpa do food truck pode nem ter a
    fonte. Um widget só para os dois desenhos: o que muda entre eles é o traço,
    não o ciclo de vida nem a leitura de tema.
    """

    LADO_PX = 18

    def __init__(self, glifo: str, token_cor: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._glifo = glifo
        self._token_cor = token_cor
        self.setObjectName("turnoGlifo")
        self.setFixedSize(self.LADO_PX, self.LADO_PX)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        cor = QColor(ThemeController.instancia().tokens_atuais[self._token_cor])
        caneta = QPen(cor, 1.5)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)

        if self._glifo == GLIFO_CEDULA:
            self._desenhar_cedula(pintor)
        else:
            self._desenhar_cartao(pintor, cor)
        pintor.end()

    @staticmethod
    def _desenhar_cedula(pintor: QPainter) -> None:
        """Nota de dinheiro: retângulo deitado com a moeda no meio."""
        pintor.drawRoundedRect(QRectF(1.5, 4.5, 15.0, 9.0), 1.6, 1.6)
        pintor.drawEllipse(QRectF(7.0, 7.0, 4.0, 4.0))

    @staticmethod
    def _desenhar_cartao(pintor: QPainter, cor: QColor) -> None:
        """Cartão de crédito: retângulo com a tarja preenchida em cima."""
        pintor.drawRoundedRect(QRectF(1.5, 4.0, 15.0, 10.0), 1.6, 1.6)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(cor)
        pintor.drawRect(QRectF(1.5, 6.4, 15.0, 2.2))

class _LinhaDeContagem(QFrame):
    """Uma linha de conferência — clicável, porque tocar nela aponta o teclado.

    É `QFrame` e não `QPushButton` por uma razão medida, não estética: um
    `QPushButton` calcula o próprio `sizeHint` a partir do texto e do ícone
    **dele**, e ignora o layout que se ponha dentro. Medido aqui, a linha nascia
    com 15px de altura e os três rótulos saíam com altura zero — um cartão
    invisível. O `QFrame` respeita o layout, e o clique custa este único
    override.

    O índice viaja no sinal em vez de numa `lambda` amarrada na construção
    (§3.14): `lambda` capturaria o diálogo, a conexão viveria na linha, a linha
    é filha do diálogo — e o ciclo se fecharia sem ninguém para desfazê-lo.
    """

    escolhida = Signal(int)

    def __init__(self, indice: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._indice = indice
        self.setObjectName("turnoContagem")
        self.setProperty("ativa", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @nao_deixa_escapar()
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.escolhida.emit(self._indice)
            return
        super().mousePressEvent(event)


class FechamentoCaixaDialog(CartaoDeTurnoDialog):
    """Cartão de fechamento cego: duas contagens e o numpad, sem esperado à vista."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            PAPEL_FECHAMENTO,
            "Fechar caixa",
            "Informe os valores contados. A conferência sai no relatório do gerente.",
            parent,
        )
        self._contados = [AcumuladorDeCentavos() for _ in CONTAGENS]
        self._registrar_alvos(*self._contados)

        self._cartoes: list[_LinhaDeContagem] = []
        self._labels_valor: list[QLabel] = []

        self._montar_cartao(
            self._montar_coluna(),
            icone=IconeDeGaveta(TOKEN_GLIFO_BADGE, trancada=True),
            rotulo_teclado=CONTAGENS[0].rotulo_teclado,
            rotulo_confirmar="Confirmar fechamento",
        )
        self._pintar()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar_coluna(self) -> QWidget:
        coluna = QWidget()
        layout = QVBoxLayout(coluna)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._rotulo("VALORES CONFERIDOS"))
        for indice, contagem in enumerate(CONTAGENS):
            layout.addWidget(self._montar_contagem(indice, contagem))
        layout.addWidget(self._rotulo("OBSERVAÇÃO (opcional)"))
        self._campo_observacao = self._campo_de_observacao("Ex.: conferido com o gerente")
        layout.addWidget(self._campo_observacao)
        layout.addStretch()
        return coluna

    def _montar_contagem(self, indice: int, contagem: Contagem) -> _LinhaDeContagem:
        cartao = _LinhaDeContagem(indice)
        cartao.escolhida.connect(self._selecionar_alvo)

        linha = QHBoxLayout(cartao)
        linha.setContentsMargins(14, 14, 16, 14)
        linha.setSpacing(12)
        linha.addWidget(
            _IconeConferencia(contagem.glifo, contagem.token_glifo),
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )

        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel(contagem.titulo)
        titulo.setObjectName("turnoContagemTitulo")
        textos.addWidget(titulo)
        linha.addLayout(textos)
        linha.addStretch()

        valor = QLabel()
        valor.setObjectName("turnoContagemValor")
        valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        linha.addWidget(valor)

        # Os rótulos são passageiros: sem isto, o clique que cai em cima do
        # texto (que é a maior parte da área da linha) dependeria de o `QLabel`
        # devolver o evento para o pai em vez de simplesmente engoli-lo.
        for filho in (titulo, valor):
            filho.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._cartoes.append(cartao)
        self._labels_valor.append(valor)
        return cartao

    # ------------------------------------------------------------------
    # Reação
    # ------------------------------------------------------------------

    def _pintar(self) -> None:
        for indice, label in enumerate(self._labels_valor):
            label.setText(self._contados[indice].texto)
            self._marcar(
                self._cartoes[indice],
                indice == self._indice_alvo and self._digitando_no_teclado(),
            )
        self._rotulo_teclado.setText(CONTAGENS[self._indice_alvo].rotulo_teclado)

    def _soltar(self) -> None:
        self._cartoes.clear()
        self._labels_valor.clear()

    def resultado(self) -> DadosFechamento:
        """O que a view leva para `CaixaService.fechar`.

        Lido DEPOIS do `exec()` — e é por isso que `done()` não zera as
        contagens: limpá-las faria todo turno ser gravado como R$ 0,00 contados,
        com a quebra do tamanho do faturamento da noite.
        """
        return DadosFechamento(
            dinheiro=self._contados[0].valor,
            maquininha=self._contados[1].valor,
            observacao=self._campo_observacao.text().strip() or None,
        )
