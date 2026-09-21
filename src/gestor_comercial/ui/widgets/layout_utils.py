"""Esvaziar um layout do Qt — a versão única e correta — e a rolagem de coluna.

`rolagem_vertical` mora aqui desde o §9.27: a tela de pagamento e a tela da
mesa montavam a mesma `QScrollArea` sem moldura, cada uma com a sua cópia.

Ver `REMASTERIZACAO-V1.md` §3.7. O projeto tinha de quatro a seis cópias deste
laço, com comportamentos divergentes: duas já corrigidas
(`historico_caixa_view`, `dashboard_mensal_view`) e as outras ainda carregando
a versão latente de um bug **que já foi diagnosticado e corrigido duas vezes**.

## O bug que o `setParent(None)` mata

`takeAt` só tira o item do LAYOUT. O widget continua filho visível do container
até o `deleteLater()` agendado realmente rodar, no próximo ciclo de eventos.
Entre um `_preencher_*` e o outro — trocar de mês no Dashboard, trocar o filtro
de operador no Histórico — isso empilhava a linha antiga por baixo da nova, na
mesma posição, e o repaint saía com texto sobreposto. `setParent(None)` desliga
o widget da árvore na hora, antes mesmo de o GC de verdade acontecer.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLayout, QScrollArea, QWidget


def rolagem_vertical(conteudo: QWidget, nome_objeto: str) -> QScrollArea:
    """Põe `conteudo` numa rolagem só vertical, sem moldura.

    É a saída para coluna que não cabe inteira em 768px: sem rolagem o Qt não
    corta, ele ESPREME (§9.1, Fase 7) — e abaixo do tamanho natural para de
    desenhar o texto dos botões. A barra horizontal fica desligada porque a
    coluna acompanha a largura da rolagem (`setWidgetResizable`).
    """
    rolagem = QScrollArea()
    rolagem.setObjectName(nome_objeto)
    rolagem.setWidget(conteudo)
    rolagem.setWidgetResizable(True)
    rolagem.setFrameShape(QFrame.Shape.NoFrame)
    rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return rolagem


def limpar_layout(layout: QLayout, *, manter_ao_final: int = 0) -> None:
    """Remove e destrói tudo o que estiver no layout, de cima para baixo.

    `manter_ao_final` preserva os N últimos itens. Serve para os layouts que
    terminam com um espaçador fixo — `mesas_view` insere as comandas ativas
    *antes* de um `addStretch()` que precisa continuar sendo o último item, e
    por isso limpava com `while layout.count() > 1`.

    Sub-layouts são esvaziados recursivamente e descartados junto: um
    `QHBoxLayout` aninhado não é widget, então `setParent(None)` não se aplica a
    ele, mas ele ainda seguraria os filhos se ficasse para trás.
    """
    while layout.count() > manter_ao_final:
        item = layout.takeAt(0)
        if item is None:
            # `takeAt` devolve None quando o índice não existe. Não deveria
            # acontecer com `count()` acima do piso, mas um layout customizado
            # (temos um: `flow_layout.py`) pode discordar — e sem esta saída o
            # `while` viraria laço infinito na tela do usuário.
            return

        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
            continue

        sub_layout = item.layout()
        if sub_layout is not None:
            limpar_layout(sub_layout)
            sub_layout.deleteLater()
