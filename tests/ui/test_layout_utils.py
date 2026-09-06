"""O helper único de limpeza de layout — ver `REMASTERIZACAO-V1.md` §3.7.

O projeto carregava de quatro a seis cópias deste laço. Duas já traziam a
correção do `setParent(None)` (e o comentário explicando o bug); as outras não.
Este arquivo tranca a versão corrigida antes de a Fase 4 apagar as cópias.

O bug que se repetiu duas vezes: `takeAt` tira o item do LAYOUT, mas o widget
continua **filho visível** do container até o `deleteLater()` agendado rodar.
Quem limpa e repopula no mesmo ciclo — trocar de mês no Dashboard, trocar o
filtro de operador no Histórico — via a linha antiga empilhada por baixo da nova
e texto sobreposto no repaint.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gestor_comercial.ui.widgets.flow_layout import FlowLayout
from gestor_comercial.ui.widgets.layout_utils import limpar_layout


def _container_com(quantidade: int) -> tuple[QWidget, QVBoxLayout]:
    container = QWidget()
    layout = QVBoxLayout(container)
    for indice in range(quantidade):
        layout.addWidget(QLabel(f"linha {indice}"))
    return container, layout


def test_esvazia_o_layout(qapp):
    _container, layout = _container_com(5)

    limpar_layout(layout)

    assert layout.count() == 0


def test_o_widget_sai_da_arvore_na_hora_sem_esperar_o_ciclo_de_eventos(qapp):
    """Este é o bug do §3.7, e é o motivo de o `setParent(None)` existir.

    A conferência é feita **antes** de qualquer `processEvents()`, de propósito:
    é exatamente essa janela — limpar e repopular sem devolver o controle ao Qt
    — que produzia o texto sobreposto na tela do usuário.
    """
    container, layout = _container_com(5)

    limpar_layout(layout)

    ainda_filhos = container.findChildren(QLabel)
    assert ainda_filhos == [], (
        f"{len(ainda_filhos)} widgets antigos continuam filhos do container e "
        "vão aparecer por baixo dos novos no próximo repaint."
    )


def test_widget_e_destruido_de_verdade(qapp, assentar):
    """`setParent(None)` tira da tela; `deleteLater()` tira da memória. O §3.7 é
    sobre o primeiro, mas quem paga a conta na máquina do food truck é o
    segundo."""
    _container, layout = _container_com(30)

    limpar_layout(layout)
    assentar()

    assert layout.count() == 0


def test_manter_ao_final_preserva_o_espacador_fixo(qapp):
    """`mesas_view` insere as comandas ativas ANTES de um `addStretch()` que
    precisa continuar sendo o último item — por isso limpava com
    `while layout.count() > 1`. Sem este parâmetro, o helper genérico comeria o
    stretch e a lista passaria a esticar as linhas pela altura toda."""
    container, layout = _container_com(4)
    layout.addStretch()

    limpar_layout(layout, manter_ao_final=1)

    assert layout.count() == 1
    assert layout.itemAt(0).spacerItem() is not None
    assert container.findChildren(QLabel) == []


def test_sub_layout_e_esvaziado_e_descartado_junto(qapp):
    """Um `QHBoxLayout` aninhado não é widget: `setParent(None)` não se aplica a
    ele. Se ficasse para trás, seguraria os próprios filhos — que é como as
    linhas 'rótulo ... valor' do Histórico e do Dashboard são montadas."""
    container = QWidget()
    layout = QVBoxLayout(container)
    linha = QHBoxLayout()
    linha.addWidget(QLabel("rótulo"))
    linha.addWidget(QLabel("valor"))
    layout.addLayout(linha)

    limpar_layout(layout)

    assert layout.count() == 0
    assert container.findChildren(QLabel) == []


def test_funciona_no_flow_layout(qapp):
    """A Central de Loja usa `FlowLayout`, um `QLayout` customizado cujo `takeAt`
    devolve `None` fora da faixa. A guarda do helper existe para que um layout
    assim não vire laço infinito na cara do usuário."""
    container = QWidget()
    layout = FlowLayout(container)
    for indice in range(6):
        layout.addWidget(QLabel(f"card {indice}"))

    limpar_layout(layout)

    assert layout.count() == 0
    assert container.findChildren(QLabel) == []


def test_limpar_layout_vazio_nao_faz_nada(qapp):
    _container, layout = _container_com(0)

    limpar_layout(layout)

    assert layout.count() == 0


def test_repopular_muitas_vezes_nao_acumula(qapp, assentar):
    """O caminho real: toda tela que limpa e repopula a cada `atualizar()`."""
    container, layout = _container_com(0)

    for _ in range(20):
        limpar_layout(layout)
        for indice in range(5):
            layout.addWidget(QLabel(f"linha {indice}"))
    assentar()

    assert len(container.findChildren(QLabel)) == 5
