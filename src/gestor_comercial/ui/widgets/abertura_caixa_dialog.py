"""Modal de abertura do caixa: o fundo de troco que começa o turno — §9.7.

Substitui o `_ValorDialog` que morava dentro de `caixa_view.py`: **um**
`QLineEdit` num `QFormLayout` com a moldura de janela do sistema, onde o valor
era digitado como texto (`"100,00"`, `"R$ 100"`, `"100.00"`) e lido de volta por
`safe_decimal` com `padrao=None` — daí o `_ERRO_VALOR` ("Valor inválido...") que
a tela mostrava quando não conseguia entender.

No balcão do food truck aquilo era a interação errada pelo mesmo motivo do modal
de PIN, do de lançar item (§9.4) e do de movimentação (§9.6): quem abre o caixa
está de pé, com a mão ocupada, e o teclado físico fica atrás do monitor. Agora o
valor entra por numpad, em centavos pela direita, e a classe inteira de defeito
do "valor ilegível" deixa de existir neste caminho — não há texto para ler de
volta.

## O que NÃO mudou

**Nenhuma regra financeira.** O diálogo não conhece `CaixaService`: ele coleta um
`DadosAbertura` (valor + observação) e a `CaixaView` chama `abrir(...)`
exatamente como antes. Quem exige gerente continua sendo o service (§3.1, via
`AuthService.exigir_gerente`), quem recusa valor negativo continua sendo o
service, e quem barra a abertura com um turno anterior esquecido continua sendo
o service (`TurnoAnteriorPendenteError`, §3.13) — o erro que ele levantar segue
aparecendo na linha de erro da tela de trás.

R$ 0,00 é valor **legítimo** aqui, e por isso o botão nasce aceso: existe turno
que começa sem fundo de troco na gaveta, e `abrir` só recusa negativo. É a
diferença para o modal de movimentação, onde zero é recusado pelo service e o
botão nasce desligado.

## A observação, e por que ela grava

O mockup pede um campo de observação na abertura ("Ex.: fundo recebido do
cofre"). Um campo que o operador preenche e o sistema descarta é pior que campo
nenhum — numa tela que declara dinheiro, é o tipo de coisa que só se descobre
quando alguém procura a anotação e ela nunca existiu. Então o §9.7 acrescentou
`Caixa.observacao_abertura` (coluna nova, migração `d9b4c7e21f30`), o parâmetro
opcional em `CaixaService.abrir` e a linha correspondente no relatório de
fechamento impresso, ao lado da observação de fechamento que já saía lá.

## As pílulas definem, e não somam

`R$ 50`, `R$ 100`, `R$ 150`, `R$ 200` são as notas com que o fundo de troco é
montado. Elas **trocam** o valor do visor em vez de somar, ao contrário das
pílulas `+10 … +500` do modal de movimentação — porque o rótulo é absoluto: uma
pílula que diz "R$ 100" e produz R$ 150 mente para quem apertou. Quem quer somar
tem o numpad ao lado.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cartao_de_turno import (
    PAPEL_ABERTURA,
    CartaoDeTurnoDialog,
    IconeDeGaveta,
)
from gestor_comercial.ui.widgets.flow_layout import FlowLayout
from gestor_comercial.ui.widgets.teclado_numerico import AcumuladorDeCentavos

# Os fundos de troco que o food truck usa de verdade. São valores redondos
# porque fundo de troco é feito de notas, não de apuração.
ATALHOS_EM_REAIS: tuple[int, ...] = (50, 100, 150, 200)

TOKEN_GLIFO = "caixa_abertura_glifo"

_SEM_OPERADOR = "—"


def _nome_do_operador(nome: str | None) -> str:
    """`"  "` e `None` viram travessão — o rótulo de tela nunca sai em branco.

    Quem barra a ação sem login é o service, na hora de gravar; a view lê
    `AuthService.usuario_logado` (que pode ser `None`) justamente para o modal
    conseguir abrir e mostrar o erro certo depois.
    """
    return (nome or "").strip() or _SEM_OPERADOR


@dataclass(frozen=True, slots=True)
class DadosAbertura:
    """O que o modal devolve. A view leva isto para `CaixaService.abrir`."""

    valor: Decimal
    observacao: str | None


class AberturaCaixaDialog(CartaoDeTurnoDialog):
    """Cartão de abertura: visor de fundo de troco, pílulas, contexto e numpad."""

    ALTURA_VISOR_PX = 84

    def __init__(
        self,
        turno: str,
        operador: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            PAPEL_ABERTURA,
            "Abrir caixa",
            "Informe o fundo de troco para iniciar o turno.",
            parent,
        )
        self._valor = AcumuladorDeCentavos()
        self._registrar_alvos(self._valor)
        self._atalhos: dict[int, QPushButton] = {}

        self._montar_cartao(
            self._montar_coluna(turno, operador),
            icone=IconeDeGaveta(TOKEN_GLIFO),
            rotulo_teclado="TECLADO DE VALOR",
            rotulo_confirmar="Abrir caixa",
        )
        self._pintar()
        self._ajustar_faixa()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar_coluna(self, turno: str, operador: str | None) -> QWidget:
        coluna = QWidget()
        layout = QVBoxLayout(coluna)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._montar_visor())
        layout.addWidget(self._montar_atalhos())
        layout.addWidget(self._montar_contexto(turno, operador))
        layout.addWidget(self._rotulo("OBSERVAÇÃO (opcional)"))
        self._campo_observacao = self._campo_de_observacao("Ex.: fundo recebido do cofre")
        layout.addWidget(self._campo_observacao)
        layout.addStretch()
        return coluna

    def _montar_visor(self) -> QFrame:
        self._visor = QFrame()
        self._visor.setObjectName("turnoVisor")
        self._visor.setProperty("ativa", True)
        self._visor.setFixedHeight(self.ALTURA_VISOR_PX)

        dentro = QVBoxLayout(self._visor)
        dentro.setContentsMargins(18, 12, 18, 12)
        dentro.setSpacing(2)

        rotulo = QLabel("VALOR DE ABERTURA")
        rotulo.setObjectName("turnoVisorRotulo")
        rotulo.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dentro.addWidget(rotulo)

        self._label_valor = QLabel()
        self._label_valor.setObjectName("turnoVisorValor")
        self._label_valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dentro.addWidget(self._label_valor)
        return self._visor

    def _montar_atalhos(self) -> QWidget:
        """A fileira `R$ 50 … R$ 200`, que quebra linha sozinha se não couber.

        `FlowLayout` e não `QHBoxLayout` pela mesma razão da faixa de categorias
        do §9.4 e das pílulas do §9.6: um `QHBoxLayout` espremeria as pílulas
        até o rótulo sumir, que é o defeito que a Fase 7 achou em Configurações.
        """
        self._faixa = QWidget()
        self._faixa.setObjectName("turnoFaixa")
        fluxo = FlowLayout(self._faixa, spacing=6)
        for reais in ATALHOS_EM_REAIS:
            pill = QPushButton(f"R$ {reais}")
            pill.setObjectName("turnoAtalho")
            # O valor vive na propriedade, e não numa `lambda` amarrada no
            # clique (§3.14): `lambda` captura `self`, a conexão vive no botão,
            # o botão é filho do diálogo — e o ciclo se fecha sozinho.
            pill.setProperty("reais", reais)
            cartao_modal.preparar_botao(pill)
            pill.clicked.connect(self._atalho_clicado)
            fluxo.addWidget(pill)
            self._atalhos[reais] = pill
        return self._faixa

    def _montar_contexto(self, turno: str, operador: str | None) -> QFrame:
        """O bloco que diz QUAL turno está sendo aberto e QUEM responde por ele.

        Não é decoração: abertura de caixa exige gerente, e o fundo declarado
        aqui é conferido no fim da noite contra a gaveta física. Quem está com o
        terminal na mão precisa ver o próprio nome antes de declarar o valor.
        """
        cartao = QFrame()
        cartao.setObjectName("turnoContexto")
        layout = QVBoxLayout(cartao)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self._label_turno = QLabel(turno)
        self._label_turno.setObjectName("turnoContextoTitulo")
        layout.addWidget(self._label_turno)

        self._label_operador = QLabel(
            f"Operador {_nome_do_operador(operador)} · "
            "o valor será registrado como fundo de troco."
        )
        self._label_operador.setObjectName("turnoContextoTexto")
        self._label_operador.setWordWrap(True)
        layout.addWidget(self._label_operador)
        return cartao

    def _ajustar_faixa(self) -> None:
        """Fecha a fileira de pílulas na altura real do que ela comporta.

        `FlowLayout.sizeHint()` devolve o **mínimo** (uma fileira), então sem
        isto uma segunda fileira seria pintada por cima do cartão de contexto —
        foi assim que o defeito apareceu na faixa de categorias do §9.4, com o
        cardápio real. Roda na construção (a largura da coluna é constante) e de
        novo no `showEvent`, porque a altura de uma pílula só é verdade depois
        do primeiro `polish`.
        """
        fluxo = self._faixa.layout()
        if fluxo is not None:
            self._faixa.setFixedHeight(fluxo.heightForWidth(self.LARGURA_COLUNA_PX))

    # ------------------------------------------------------------------
    # Reação
    # ------------------------------------------------------------------

    def _atalho_clicado(self) -> None:
        botao = self.sender()
        if not isinstance(botao, QPushButton):
            return
        self._valor.definir(Decimal(int(botao.property("reais") or 0)))
        self._pintar()

    def _pintar(self) -> None:
        # `AcumuladorDeCentavos.texto` sai de `formatar_reais`, o mesmo do resto
        # do app e do cupom impresso (§3.8): o valor que o gerente declara aqui
        # aparece idêntico na linha "Abertura" do resumo do turno.
        self._label_valor.setText(self._valor.texto)
        # O anel diz PARA ONDE o próximo dígito vai: aceso, para o valor;
        # apagado, o cursor está na observação e dígito é texto.
        self._marcar(self._visor, self._digitando_no_teclado())

    def _soltar(self) -> None:
        self._atalhos.clear()

    def resultado(self) -> DadosAbertura:
        """O que a view leva para `CaixaService.abrir`.

        Lido DEPOIS do `exec()` — o `executar_modal` (§3.2) só descarta o
        diálogo na volta, e é por isso que `done()` não zera o valor.
        """
        return DadosAbertura(
            valor=self._valor.valor,
            observacao=self._campo_observacao.text().strip() or None,
        )

    def _antes_de_medir(self) -> None:
        self._ajustar_faixa()
