"""O painel "Próxima ação" da tela da mesa (§9.27).

Substitui a fileira de seis pílulas do cabeçalho da tela antiga, onde "Receber
pagamento" e "Cancelar comanda" moravam lado a lado com o mesmo peso. Aqui a
ordem é a do fluxo, de cima para baixo:

1. **Fechar para conferência** — o âmbar cheio, a ação principal da mesa aberta;
2. **Receber pagamento** — contornado, liga quando a pré-conta saiu;
3. **Reabrir comanda** — só EXISTE com a conta em conferência (decisão do
   Vitor, perguntada antes de começar: botão próprio, e não escondido num menu
   "Mais"). Numa mesa aberta ele seria um botão sempre apagado — e pelo mesmo
   motivo o "Fechar para conferência" some quando a conta JÁ está em
   conferência: os dois trocam de lugar, e o painel tem sempre quatro botões.
   Com os cinco, a coluna não cabia nos 738px úteis do monitor do food truck e
   ganhava rolagem justamente na hora de receber (medido na renderização);
4. **2ª via** — o cupom da cozinha inteiro de novo;
5. **Cancelar comanda** — isolado na base, depois de um divisor, em texto
   vermelho sem fundo: é destrutivo e exige PIN, e não pode estar a um
   escorregão do "Receber pagamento".

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
    GLIFO_IMPRESSORA,
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
    """Os cinco botões da mesa, na ordem do fluxo."""

    fechar_conferencia = Signal()
    receber_pagamento = Signal()
    reabrir = Signal()
    segunda_via = Signal()
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
            "Fechar para conferência",
            GLIFO_DOCUMENTO_VISTO,
            "acento_texto",
            "mesaDetBotaoFechar",
            "Trava novos itens e emite a pré-conta para o cliente conferir na mesa.",
        )
        self.botao_fechar.clicked.connect(self.fechar_conferencia)
        coluna.addWidget(self.botao_fechar)

        self.botao_receber = _botao(
            "Receber pagamento",
            GLIFO_CIFRAO,
            "mesa_detalhe_receber_texto",
            "mesaDetBotaoReceber",
            "Abre o recebimento da conta. Liga depois que a pré-conta sai.",
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

        self.botao_segunda_via = _botao(
            "2ª via",
            GLIFO_IMPRESSORA,
            "texto",
            "mesaDetBotaoNeutro",
            "Repete a comanda inteira, para cupom rasgado ou perdido.",
        )
        self.botao_segunda_via.clicked.connect(self.segunda_via)
        coluna.addWidget(self.botao_segunda_via)

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
        receber só em conferência (a aberta ainda pode ganhar item); cancelar só
        a aberta (o service recusa as outras); 2ª via com qualquer item — o cupom
        da cozinha some ou rasga depois do pagamento também.
        """
        self.botao_fechar.setEnabled(painel.aberta and painel.tem_itens)
        self.botao_fechar.setVisible(not painel.em_conferencia)
        self.botao_receber.setEnabled(painel.em_conferencia)
        self.botao_reabrir.setVisible(painel.em_conferencia)
        self.botao_segunda_via.setEnabled(painel.tem_itens)
        self.botao_cancelar.setEnabled(painel.aberta)
