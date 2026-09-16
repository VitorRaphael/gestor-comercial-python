"""O campo de dinheiro digitado — um só para todo valor monetário da UI (§9.20).

Antes dele, preço e custo do produto eram `QLineEdit` crus: aceitavam "12,5abc",
"R$ 15,90 kg" e três vírgulas, e só descobriam o problema no OK, quando
`safe_decimal` não conseguia ler e a linha vermelha dizia "Informe um preço
válido". O operador digitava às cegas e era corrigido depois.

## Uma porta só: o validador

A regra mora num `QValidator` que **reescreve** o texto (`ValidadorMoeda`), e não
num `keyPressEvent`. É o validador que o `QLineEdit` consulta em TODA mudança de
texto — tecla, Ctrl+V, Shift+Insert, "Colar" do menu de contexto, arrastar e
soltar, `setText` —, então não há caminho de entrada esquecido. Interceptar o
Ctrl+V no teclado deixaria o "Colar" do botão direito passar: aquela ação é
ligada em C++ ao slot `paste()`, que um override em Python não enxerga.

Custo por tecla: uma chamada de `validate` e algumas listas curtas. Quando o
texto precisa ser reescrito (tecla recusada, colagem suja) são **duas** chamadas
— a segunda recebe o texto já limpo e o devolve igual, que é o ponto fixo de
`sanitizar_edicao_moeda`. Não há sinal ligado, timer nem objeto criado por tecla.

A reescrita tem um preço conhecido do Qt: ela limpa o histórico de desfazer do
campo. Só acontece quando algo foi recusado ou convertido (o ponto que vira
vírgula), e num campo de preço o Ctrl+Z não é gesto de balcão.

## O "R$" não é texto

É um `QLabel` filho do campo, pintado dentro da margem esquerda do texto
(`setTextMargins`). O cursor não alcança o que não é texto, então Home +
Backspace não apaga o símbolo, `text()` nunca o contém e ninguém precisa tirá-lo
de volta antes de converter. Ele é transparente ao mouse: clicar no "R$" é
clicar no campo.

## O que o campo devolve

`valor()` devolve `Decimal` de 2 casas, ou `None` para campo vazio — nunca
`float`, que `dinheiro()` recusa de propósito, e nunca negativo, porque o sinal
não entra no texto. A leitura é a `safe_decimal` de sempre (§3.8): o campo não
tem conversor próprio para divergir.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent, QResizeEvent, QValidator
from PySide6.QtWidgets import QLabel, QLineEdit, QStyle, QStyleOptionFrame, QWidget

from gestor_comercial.ui.formatacao import (
    SIMBOLO,
    formatar_para_campo,
    safe_decimal,
    sanitizar_edicao_moeda,
)
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade

# Distância entre o "R$" e o primeiro dígito. Um espaço da fonte do campo, que é
# como `formatar_reais` separa os dois no resto das telas.
FOLGA_PREFIXO_PX = 6


class ValidadorMoeda(QValidator):
    """Deixa no campo só o que `sanitizar_edicao_moeda` aceita.

    Guarda o último texto aceito para saber o que cada edição trouxe — é isso
    que separa "a vírgula que já estava" da "segunda vírgula digitada". Por isso
    é **um validador por campo**: compartilhado, um campo leria a edição do
    outro. `CampoMoeda` cria o seu.

    Nunca devolve `Invalid`. Com `Invalid` o Qt desfaz a edição quando ela veio
    do teclado, mas NÃO quando veio de `setText` — o texto recusado ficaria no
    campo. Devolver o texto limpo funciona igual pelos dois caminhos.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._aceito = ""

    def validate(self, texto: str, cursor: int) -> tuple[QValidator.State, str, int]:
        limpo, cursor_limpo = sanitizar_edicao_moeda(self._aceito, texto, cursor)
        self._aceito = limpo
        return QValidator.State.Acceptable, limpo, cursor_limpo


class CampoMoeda(QLineEdit):
    """`QLineEdit` de valor em reais: "R$" fixo, só dígitos e uma vírgula.

    Continua sendo um `QLineEdit` de propósito: o QSS de campo (borda, anel
    âmbar no foco, `[erro="true"]`) e os utilitários de erro das telas valem
    para ele sem cópia nenhuma.
    """

    def __init__(self, valor: Decimal | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Antes do primeiro `setText`: o validador precisa ver o texto inicial
        # entrar para saber, na edição seguinte, o que já estava lá.
        self.setValidator(ValidadorMoeda(self))

        self._prefixo = QLabel(SIMBOLO, self)
        self._prefixo.setObjectName("campoMoedaPrefixo")
        self._prefixo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._prefixo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.definir_valor(valor)
        self._acomodar_prefixo()

    def valor(self) -> Decimal | None:
        """O que está digitado, em `Decimal` de 2 casas; `None` se não há número.

        `None` e não zero para quem chama poder distinguir "vazio" de "zero": o
        preço vazio é "informe o preço", o zero é "maior que zero".
        """
        return safe_decimal(self.text(), padrao=None)

    def definir_valor(self, valor: Decimal | None) -> None:
        self.setText(formatar_para_campo(valor))

    # ------------------------------------------------------------------
    # Foco: o "R$" acende junto com a borda, e os centavos são completados
    # ------------------------------------------------------------------

    def focusInEvent(self, evento: QFocusEvent) -> None:
        super().focusInEvent(evento)
        aplicar_propriedade(self._prefixo, "foco", True)

    def focusOutEvent(self, evento: QFocusEvent) -> None:
        super().focusOutEvent(evento)
        # O menu de contexto rouba o foco para abrir. Formatar ali trocaria o
        # texto debaixo da seleção de quem está prestes a clicar em "Colar".
        if evento.reason() == Qt.FocusReason.PopupFocusReason:
            return
        aplicar_propriedade(self._prefixo, "foco", False)
        self._completar_centavos()

    def _completar_centavos(self) -> None:
        """"12" vira "12,00" e ",5" vira "0,50"; vazio continua vazio.

        Vazio não vira "0,00": para o preço, campo em branco é "não informado",
        e a linha de erro precisa poder dizer isso. O `if` não é por sinal —
        `setText` com o mesmo texto não emite `textChanged` —, é pelo histórico:
        todo `setText` apaga o Ctrl+Z, e sem o `if` cada Tab o apagaria.
        """
        valor = self.valor()
        texto = "" if valor is None else formatar_para_campo(valor)
        if texto != self.text():
            self.setText(texto)

    # ------------------------------------------------------------------
    # Geometria do "R$"
    # ------------------------------------------------------------------

    def resizeEvent(self, evento: QResizeEvent) -> None:
        super().resizeEvent(evento)
        self._acomodar_prefixo()

    def changeEvent(self, evento: QEvent) -> None:
        super().changeEvent(evento)
        if evento.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._acomodar_prefixo()

    def _acomodar_prefixo(self) -> None:
        """Reserva a margem do "R$" e o põe no começo da área de texto.

        A área vem do estilo (`SE_LineEditContents`), e não de um número fixo,
        porque é o QSS que decide o `padding` do campo — e ele muda de uma tela
        para outra. A largura é medida na fonte do PRÓPRIO rótulo depois de
        polido: o QSS o deixa em negrito, e medir antes mediria outra fonte (a
        armadilha do §9.8).

        `setTextMargins` só é chamado quando a margem muda: ele pede nova
        geometria ao layout, e o `resizeEvent` que isso pode gerar volta aqui
        com a margem já igual — o laço termina na segunda passada.
        """
        self._prefixo.ensurePolished()
        largura = self._prefixo.fontMetrics().horizontalAdvance(SIMBOLO)
        margens = self.textMargins()
        esquerda = largura + FOLGA_PREFIXO_PX
        if margens.left() != esquerda:
            self.setTextMargins(esquerda, margens.top(), margens.right(), margens.bottom())

        opcao = QStyleOptionFrame()
        self.initStyleOption(opcao)
        area = self.style().subElementRect(QStyle.SubElement.SE_LineEditContents, opcao, self)
        self._prefixo.setGeometry(area.left(), area.top(), largura, area.height())
