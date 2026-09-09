"""Modal de fechamento do caixa: as duas contagens e a diferença do turno — §9.7.

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

1. **A diferença é mostrada enquanto se digita**, e não depois de gravar. Antes,
   o operador confirmava às cegas e descobria a quebra no papel. Agora o cartão
   de diferença se recalcula a cada tecla — falta em vermelho, exato em verde,
   sobra em ciano.
2. **O teclado tem um destino só por vez, e ele é dito em voz alta.** O rótulo
   da direita alterna entre `DIGITANDO DINHEIRO` e `DIGITANDO MAQUININHAS`, e o
   cartão ativo fica com o anel aceso. Sem isso, o operador digita o extrato da
   maquininha por cima da contagem da gaveta e nada avisa.
3. **A conta da prévia é a mesma do service, e há teste provando.** A prévia não
   pode chamar `CaixaService.resumo()`, porque nada foi gravado ainda — então a
   igualdade não é garantida por código compartilhado, e sim por um teste que
   fecha o caixa de verdade e compara a prévia com o `ResumoCaixa.diferenca_total`
   que sai do banco.

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

## O atalho "preencher valores esperados"

Existe porque o turno que fecha certinho é o caso comum, e obrigar a redigitar
dois valores que já estão na tela convida ao erro de digitação. Mas ele é, por
construção, o botão que permite fechar o turno **sem contar a gaveta** — por
isso é um botão fantasma, discreto, e não um caminho em destaque. Ele preenche;
quem confirma continua sendo o gerente.
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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.services.dinheiro import ZERO, dinheiro
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cartao_de_turno import (
    PAPEL_FECHAMENTO,
    CartaoDeTurnoDialog,
    IconeDeGaveta,
)
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.teclado_numerico import AcumuladorDeCentavos

# Desenhos possíveis dos ícones das linhas (ver `_IconeConferencia`). São nomes
# de forma, e não de conteúdo, porque é a forma que o `QPainter` escolhe.
GLIFO_CEDULA = "cedula"
GLIFO_CARTAO = "cartao"
GLIFO_CALCULADORA = "calculadora"

TOKEN_GLIFO_BADGE = "caixa_fechamento_glifo"

# Os três tons da diferença. São chave de QSS (`[tom="falta"]`) e não cor: a cor
# vem da paleta e acompanha a troca de tema (§3.15).
TOM_FALTA = "falta"
TOM_EXATO = "exato"
TOM_SOBRA = "sobra"

TEXTO_SEM_DIFERENCA = "· Sem diferença"
TEXTO_SOBRA = "· Sobra"


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
# independentes, cada uma com o próprio esperado e a própria diferença — foi o
# que a migração `b7c9e2f14a03` separou no banco.
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
    """Cédula, cartão e calculadora, desenhados à mão.

    Mesma decisão do cadeado do PIN, da lupa do §9.4, do usuário do §9.5 e das
    setas do §9.6: o glifo equivalente cai no Segoe UI Emoji, sai colorido e
    chapado e ignora o tema — e a máquina limpa do food truck pode nem ter a
    fonte. Um widget só para os três desenhos: o que muda entre eles é o traço,
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
        elif self._glifo == GLIFO_CARTAO:
            self._desenhar_cartao(pintor, cor)
        else:
            self._desenhar_calculadora(pintor, cor)
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

    @staticmethod
    def _desenhar_calculadora(pintor: QPainter, cor: QColor) -> None:
        """Calculadora: corpo em pé, visor preenchido e quatro teclas."""
        pintor.drawRoundedRect(QRectF(3.5, 1.5, 11.0, 15.0), 1.6, 1.6)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(cor)
        pintor.drawRect(QRectF(5.5, 3.8, 7.0, 2.6))
        for x in (6.2, 10.2):
            for y in (9.0, 12.2):
                pintor.drawEllipse(QPointF(x, y), 0.9, 0.9)


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
    """Cartão de fechamento: duas contagens, a diferença ao vivo e o numpad."""

    def __init__(
        self,
        esperado_dinheiro: Decimal,
        esperado_maquininha: Decimal,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            PAPEL_FECHAMENTO,
            "Fechar caixa",
            "Confira os valores apurados antes de encerrar o turno.",
            parent,
        )
        # Os esperados passam por `dinheiro()` na entrada: eles vêm do
        # `ResumoCaixa` (já arredondado), e a prévia da diferença é subtração de
        # dinheiro — um valor com mais de duas casas aqui produziria uma prévia
        # que não bate com o que o service grava depois.
        self._esperados = [dinheiro(esperado_dinheiro), dinheiro(esperado_maquininha)]
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
        layout.addWidget(self._montar_diferenca())
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
        esperado = QLabel(f"Esperado {formatar_reais(self._esperados[indice])}")
        esperado.setObjectName("turnoContagemEsperado")
        textos.addWidget(esperado)
        linha.addLayout(textos)
        linha.addStretch()

        valor = QLabel()
        valor.setObjectName("turnoContagemValor")
        valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        linha.addWidget(valor)

        # Os rótulos são passageiros: sem isto, o clique que cai em cima do
        # texto (que é a maior parte da área da linha) dependeria de o `QLabel`
        # devolver o evento para o pai em vez de simplesmente engoli-lo.
        for filho in (titulo, esperado, valor):
            filho.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._cartoes.append(cartao)
        self._labels_valor.append(valor)
        return cartao

    def _montar_diferenca(self) -> QFrame:
        cartao = QFrame()
        cartao.setObjectName("turnoDiferenca")
        layout = QVBoxLayout(cartao)
        layout.setContentsMargins(14, 12, 16, 14)
        layout.setSpacing(10)

        linha = QHBoxLayout()
        linha.setSpacing(12)
        linha.addWidget(
            _IconeConferencia(GLIFO_CALCULADORA, "texto_fraco"),
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        titulo = QLabel("Diferença do fechamento")
        titulo.setObjectName("turnoContagemTitulo")
        linha.addWidget(titulo)
        linha.addStretch()

        self._label_diferenca = QLabel()
        self._label_diferenca.setObjectName("turnoDiferencaValor")
        self._label_diferenca.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        linha.addWidget(self._label_diferenca)
        layout.addLayout(linha)

        self._botao_preencher = QPushButton("PREENCHER VALORES ESPERADOS")
        self._botao_preencher.setObjectName("turnoPreencher")
        self._botao_preencher.setToolTip(
            "Copia o que o sistema apurou para as duas contagens. "
            "Use só depois de conferir a gaveta."
        )
        cartao_modal.preparar_botao(self._botao_preencher)
        self._botao_preencher.clicked.connect(self._preencher_esperados)
        layout.addWidget(self._botao_preencher)
        return cartao

    # ------------------------------------------------------------------
    # Reação
    # ------------------------------------------------------------------

    def _preencher_esperados(self) -> None:
        """Copia o apurado para as duas contagens.

        `definir` recusa valor negativo, e isso não é detalhe: o saldo esperado
        da gaveta fica negativo quando as sangrias passam do que entrou, e
        preencher a contagem física com um número negativo seria afirmar que a
        gaveta deve dinheiro. Nesse caso a contagem fica como está e o gerente
        digita o que contou.
        """
        for contado, esperado in zip(self._contados, self._esperados):
            contado.definir(esperado)
        self._pintar()

    def diferenca(self) -> Decimal:
        """A prévia da quebra/sobra do turno: contado − esperado, nas duas contagens.

        É a mesma conta de `ResumoCaixa.diferenca_total`
        (`diferenca_dinheiro + diferenca_maquininha`, cada uma sendo
        `contado − esperado`), e não pode ser importada de lá porque lá ela
        depende de um caixa já gravado. A igualdade é trancada por teste, que
        fecha o caixa de verdade e compara os dois números.
        """
        return dinheiro(
            sum(
                (contado.valor - esperado
                 for contado, esperado in zip(self._contados, self._esperados)),
                ZERO,
            )
        )

    def _pintar(self) -> None:
        for indice, label in enumerate(self._labels_valor):
            label.setText(self._contados[indice].texto)
            self._marcar(
                self._cartoes[indice],
                indice == self._indice_alvo and self._digitando_no_teclado(),
            )
        self._rotulo_teclado.setText(CONTAGENS[self._indice_alvo].rotulo_teclado)
        self._pintar_diferenca()

    def _pintar_diferenca(self) -> None:
        diferenca = self.diferenca()
        if diferenca == ZERO:
            # Zero aqui é a notícia boa, e merece ser lida como notícia — não
            # como mais um valor. É o mesmo critério do `formatar_reais_com_sinal`
            # nos relatórios, onde zero vira travessão.
            texto, tom = f"{formatar_reais(ZERO)} {TEXTO_SEM_DIFERENCA}", TOM_EXATO
        elif diferenca < ZERO:
            texto, tom = formatar_reais(diferenca), TOM_FALTA
        else:
            texto, tom = f"{formatar_reais(diferenca)} {TEXTO_SOBRA}", TOM_SOBRA
        self._label_diferenca.setText(texto)
        # Repolir custa um recálculo de estilo, e isto roda a cada tecla: só
        # paga quem mudou de estado (mesma economia do `_marcar` da base).
        if self._label_diferenca.property("tom") != tom:
            aplicar_propriedade(self._label_diferenca, "tom", tom)

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
