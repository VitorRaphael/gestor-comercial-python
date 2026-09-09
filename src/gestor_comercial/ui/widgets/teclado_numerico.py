"""O teclado numérico dos modais em cartão — e o acumulador de centavos.

As duas peças moram juntas porque **uma não existe sem a outra**: o teclado só
sabe dizer "apertaram o 5" e "apertaram o apagar"; quem transforma isso em
dinheiro é o acumulador. Separá-las em dois arquivos faria a próxima tela
copiar a metade errada.

## Por que isto saiu de dentro do modal de movimentação

O §9.6 trouxe o segundo numpad do app (o primeiro é o do PIN) e, com ele, o
acumulador de centavos. O §9.7 — abertura e fechamento de caixa — traria o
terceiro e o quarto. Quatro cópias do mesmo laço `novo = novo * 10 + digito`
não é repetição de decoração: é repetição da **conta que vira dinheiro
gravado**, e a suíte já reprova corpo de função duplicado na camada de UI
(`test_paineis_de_relatorio.py::test_nenhuma_funcao_da_ui_repete_o_corpo_de_outra`).

O `pin_pad_dialog` ficou de fora de propósito, e não por esquecimento: o
teclado dele não tem `00`, tem uma tecla ENTRAR no lugar do apagar e alimenta
marcadores de dígito, não um valor em reais. Forçar as duas coisas na mesma
classe custaria mais condicional do que as vinte linhas que ele tem hoje.

## Por que centavos inteiros, e não texto de campo

Herdado do §9.6, e vale para os três modais que usam esta peça: o visor conta
**centavos inteiros entrando pela direita**, como máquina de cartão — `5`, `0`,
`0`, `0` mostra `R$ 0,05` → `R$ 0,50` → `R$ 5,00` → `R$ 50,00`. Isso apaga a
classe inteira de defeito do "valor ilegível": nunca há texto para ler de
volta, então não existe `"50,00"` digitado como `"50.00"`, `"R$ 50"` ou
`"5O,00"` (com a letra O) para `safe_decimal` recusar.

O teto sai de `dinheiro.LIMITE`, e não de um número escolhido na tela. É o teto
das colunas `NUMERIC(10,2)` do domain, e é o mesmo que `CaixaService` recusa
com `ValueError` — que **não** está no `_ERROS_SERVICE` da tela de Caixa e
subiria como estouro no balcão, não como mensagem. Amarrando os dois, o numpad
não consegue montar um valor que o service rejeitaria assim.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QPushButton, QWidget

from gestor_comercial.services.dinheiro import LIMITE, ZERO, dinheiro
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets import cartao_modal

# Os rótulos são o dado que o `_tecla_clicada` lê de volta do botão (§3.14: nada
# de `lambda` capturando `self`), então valem como constante e não como literal
# solto em três lugares.
ROTULO_APAGAR = "⌫"
ROTULO_DOIS_ZEROS = "00"

# Alvo de dedo num PDV. Foi a única medida que NÃO cedeu quando o cartão do
# §9.6 precisou encolher 30px para caber num monitor de 768px — e continua
# valendo aqui pelo mesmo motivo: quem opera está de pé.
ALTURA_TECLA_PX = 46


class AcumuladorDeCentavos:
    """Um valor em reais que só cresce por dígito, pela direita.

    Não é widget e não conhece Qt: é a regra do visor, isolada para poder ser
    testada sem tela e compartilhada pelos modais de sangria/reforço/despesa
    (§9.6) e de abertura/fechamento de caixa (§9.7).

    Os métodos que podem recusar devolvem `bool` em vez de levantar. Passar do
    teto simplesmente não faz nada: cortar o número pela metade, ou zerar,
    seria pior que ignorar a tecla — o operador olha para o visor, não para a
    tecla que apertou.
    """

    TETO_EM_CENTAVOS = int(LIMITE * 100)

    def __init__(self) -> None:
        self.centavos = 0

    @property
    def valor(self) -> Decimal:
        """Os centavos como `Decimal` de duas casas.

        `scaleb(-2)` e não `/ 100`: é deslocamento de expoente, exato por
        construção, e não depende da precisão do contexto decimal.
        """
        return Decimal(self.centavos).scaleb(-2)

    @property
    def texto(self) -> str:
        """O valor como o resto do app o mostra — `R$ 1.234,50` (§3.8)."""
        return formatar_reais(self.valor)

    def digitar(self, digitos: str) -> bool:
        """Empurra dígitos pela direita. Devolve `False` se estourariam o teto.

        Os dígitos entram todos ou nenhum: a tecla `00` no teto não pode
        acrescentar um zero e engolir o outro.
        """
        novo = self.centavos
        for digito in digitos:
            novo = novo * 10 + int(digito)
            if novo > self.TETO_EM_CENTAVOS:
                return False
        self.centavos = novo
        return True

    def apagar(self) -> None:
        """Tira o último dígito. Zero dividido continua zero — nunca negativo."""
        self.centavos //= 10

    def somar_reais(self, reais: int) -> bool:
        """A pílula `+50` do modal de movimentação: soma ao que já está no visor."""
        novo = self.centavos + reais * 100
        if novo > self.TETO_EM_CENTAVOS:
            return False
        self.centavos = novo
        return True

    def definir(self, valor: Decimal) -> bool:
        """Troca o valor inteiro de uma vez — a pílula `R$ 100` da abertura e o
        "preencher valores esperados" do fechamento.

        Recusa negativo e recusa acima do teto **antes** de chamar `dinheiro()`,
        que levantaria: este método é chamado de dentro de slot de clique, e um
        estouro ali evapora sem mensagem nenhuma (ver `core/resilience.py`).
        """
        if valor < ZERO or valor > LIMITE:
            return False
        self.centavos = int(dinheiro(valor).scaleb(2))
        return True

    def zerar(self) -> None:
        self.centavos = 0


class TecladoNumerico(QWidget):
    """A grade 3×4 de teclas: `1`-`9`, `00`, `0` e o apagar.

    Emite o que foi apertado e **não** guarda valor nenhum: quem soma é o
    `AcumuladorDeCentavos` do modal. É essa separação que permite ao modal de
    fechamento apontar o mesmo teclado ora para a contagem de dinheiro, ora
    para a da maquininha, sem o teclado saber que existem duas.

    As teclas ficam expostas em `teclas` (rótulo → botão) porque é assim que a
    suíte aperta uma tecla como o dedo aperta — pelo sinal do botão, não
    chamando o método por dentro.
    """

    digitou = Signal(str)
    apagou = Signal()

    def __init__(self, parent: QWidget | None = None, altura_tecla: int = ALTURA_TECLA_PX) -> None:
        super().__init__(parent)
        # `QWidget` cru herdaria a regra genérica `QWidget { background:
        # bg_marca }` do topo do QSS e pintaria um retângulo com a cor de fundo
        # do app por cima do cartão — o mesmo cuidado que `movCaixaFaixa` já
        # exigia.
        self.setObjectName("tecladoNumerico")
        self.teclas: dict[str, QPushButton] = {}
        self._altura_tecla = altura_tecla

        grade = QGridLayout(self)
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setSpacing(8)
        for indice, digito in enumerate("123456789"):
            grade.addWidget(self._tecla(digito), indice // 3, indice % 3)
        # Última fileira: `00` para os valores redondos (que são a maioria no
        # caixa), `0` e o apagar.
        grade.addWidget(self._tecla(ROTULO_DOIS_ZEROS), 3, 0)
        grade.addWidget(self._tecla("0"), 3, 1)
        apagar = self._tecla(ROTULO_APAGAR)
        apagar.setToolTip("Apagar o último dígito (Backspace)")
        grade.addWidget(apagar, 3, 2)

    def _tecla(self, rotulo: str) -> QPushButton:
        botao = QPushButton(rotulo)
        botao.setObjectName("teclaNumerica")
        botao.setMinimumHeight(self._altura_tecla)
        cartao_modal.preparar_botao(botao)
        botao.clicked.connect(self._tecla_clicada)
        self.teclas[rotulo] = botao
        return botao

    def _tecla_clicada(self) -> None:
        """Quem apertou sai do `sender()` — nenhuma conexão por `lambda` (§3.14).

        `lambda` capturaria `self`, a conexão viveria no botão, o botão é filho
        do teclado, o teclado é filho do modal — e o ciclo se fecharia sem
        ninguém para desfazê-lo.
        """
        botao = self.sender()
        if not isinstance(botao, QPushButton):
            return
        rotulo = botao.text()
        if rotulo.isdigit():
            self.digitou.emit(rotulo)
        else:
            self.apagou.emit()

    def soltar(self) -> None:
        """Solta a tabela rótulo → botão, no `done()` do modal que hospeda.

        Os botões em si são filhos deste widget e morrem com ele; o que a
        tabela guarda é a *referência do lado Python*, e é ela que sobreviveria
        a uma tarde de idas e voltas ao modal.
        """
        self.teclas.clear()
