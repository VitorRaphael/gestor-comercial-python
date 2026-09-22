"""O painel "Próxima ação" da tela da mesa (§9.27).

Substitui a fileira de seis pílulas do cabeçalho da tela antiga, onde "Receber
pagamento" e "Cancelar comanda" moravam lado a lado com o mesmo peso. Aqui a
ordem é a do fluxo, de cima para baixo:

1. **Gerar Conta** — o âmbar cheio: imprime a pré-conta e passa a conta para
   conferência num clique só, sem modal de confirmação;
2. **Fechar Mesa** — contornado, SEMPRE ligado: o operador pode ir direto ao
   pagamento sem gerar a conta antes (a `MesaDetalheView` põe a conta em
   conferência por baixo);
3. **Reabrir comanda** — só EXISTE com a conta em conferência (decisão do
   Vitor, perguntada antes de começar: botão próprio, e não escondido num menu
   "Mais"). Numa mesa aberta ele seria um botão sempre apagado — e pelo mesmo
   motivo o "Gerar Conta" some quando a conta JÁ está em conferência: os dois
   trocam de lugar, e o painel tem sempre três botões;
4. **Cancelar comanda** — isolado na base, depois de um divisor, em texto
   vermelho sem fundo: é destrutivo e exige PIN, e não pode estar a um
   escorregão do "Fechar Mesa".

A "2ª via" da cozinha saiu do painel: era a quarta opção de impressão perto
do fechamento e confundia com a pré-conta.

O painel NÃO conhece service nenhum: emite um sinal por botão, e quem decide o
que cada clique faz é a `MesaDetalheView`. As regras de quando cada botão liga
são as mesmas da tela antiga, lidas do `PainelDaComanda`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from gestor_comercial.services.comanda_service import PainelDaComanda
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_CADEADO_ABERTO,
    GLIFO_CIFRAO,
    GLIFO_DOCUMENTO_VISTO,
    GLIFO_LIXEIRA,
    BotaoComGlifo,
)
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado

_TOKEN_DESLIGADO = "pilula_disabled_texto"


def _botao(texto: str, glifo: str, token: str, nome_objeto: str, dica: str) -> BotaoComGlifo:
    botao = BotaoComGlifo(texto, glifo, token, _TOKEN_DESLIGADO, centrado=True)
    botao.setObjectName(nome_objeto)
    botao.setToolTip(dica)
    botao.setCursor(Qt.CursorShape.PointingHandCursor)
    return botao


class PainelAcoesWidget(PainelPontilhado):
    """Os botões da mesa, na ordem do fluxo."""

    fechar_conferencia = Signal()
    receber_pagamento = Signal()
    reabrir = Signal()
    cancelar_comanda = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mesaDetCartao")
        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(18, 14, 18, 12)
        coluna.setSpacing(7)

        sobrescrito = QLabel("PRÓXIMA AÇÃO")
        sobrescrito.setObjectName("mesaDetRotuloSecao")
        coluna.addWidget(sobrescrito)
        coluna.addSpacing(2)

        self.botao_fechar = _botao(
            "Gerar Conta",
            GLIFO_DOCUMENTO_VISTO,
            "acento_texto",
            "mesaDetBotaoFechar",
            "Imprime a pré-conta na impressora do caixa e trava novos itens.",
        )
        self.botao_fechar.clicked.connect(self.fechar_conferencia)
        coluna.addWidget(self.botao_fechar)

        self.botao_receber = _botao(
            "Fechar Mesa",
            GLIFO_CIFRAO,
            "mesa_detalhe_receber_texto",
            "mesaDetBotaoReceber",
            "Vai direto para o recebimento da conta.",
        )
        self.botao_receber.clicked.connect(self.receber_pagamento)
        coluna.addWidget(self.botao_receber)

        self.botao_reabrir = _botao(
            "Reabrir comanda",
            GLIFO_CADEADO_ABERTO,
            "texto",
            "mesaDetBotaoNeutro",
            "Volta a aceitar itens. Exige PIN de gerente.",
        )
        self.botao_reabrir.clicked.connect(self.reabrir)
        self.botao_reabrir.setVisible(False)
        coluna.addWidget(self.botao_reabrir)

        coluna.addSpacing(2)
        divisor = QFrame()
        divisor.setObjectName("mesaDetDivisor")
        divisor.setFixedHeight(1)
        coluna.addWidget(divisor)

        self.botao_cancelar = _botao(
            "Cancelar comanda",
            GLIFO_LIXEIRA,
            "mesa_detalhe_perigo_texto",
            "mesaDetBotaoCancelar",
            "Cancela a comanda inteira. Exige PIN de gerente e motivo.",
        )
        self.botao_cancelar.clicked.connect(self.cancelar_comanda)
        coluna.addWidget(self.botao_cancelar)

    def mostrar(self, painel: PainelDaComanda) -> None:
        """Liga e mostra cada botão pelo estado da conta.

        As regras são as da tela antiga, uma a uma: fechar só a aberta com item;
        "Fechar Mesa" sempre ligado — ir ao pagamento não depende da pré-conta;
        cancelar só a aberta (o service recusa as outras).
        """
        self.botao_fechar.setEnabled(painel.aberta and painel.tem_itens)
        self.botao_fechar.setVisible(not painel.em_conferencia)
        self.botao_receber.setEnabled(True)
        self.botao_reabrir.setVisible(painel.em_conferencia)
        self.botao_cancelar.setEnabled(painel.aberta)
