"""O helper único de limpeza de layout — ver `REMASTERIZACAO-V1.md` §3.7.

O projeto carregava de quatro a seis cópias deste laço. Duas já traziam a
correção do `setParent(None)` (e o comentário explicando o bug); as outras não.
Este arquivo trancou a versão corrigida antes de a Fase 4 apagar as cópias.
Com a Fase 4 concluída existe **uma** cópia, e os dois últimos testes daqui
cobrem os dois sites que ainda carregavam a versão com bug.

O bug que se repetiu duas vezes: `takeAt` tira o item do LAYOUT, mas o widget
continua **filho visível** do container até o `deleteLater()` agendado rodar.
Quem limpa e repopula no mesmo ciclo — trocar de mês no Dashboard, trocar o
filtro de operador no Histórico — via a linha antiga empilhada por baixo da nova
e texto sobreposto no repaint.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gestor_comercial.ui.views.caixa_view import CaixaView
from gestor_comercial.ui.views.mesas_view import MesasView
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


# ----------------------------------------------------------------------
# Os dois sites que carregavam a versão SEM `setParent(None)` — §3.7.
#
# `caixa_view` e `mesas_view` ficaram com o bug latente enquanto
# `historico_caixa_view` e `dashboard_mensal_view` já tinham sido corrigidos
# (duas vezes, separadamente). Os testes abaixo exercitam as views de verdade
# para que a correção não possa ser desfeita sem a suíte avisar.
#
# A asserção é sobre o MESMO ciclo, sem `assentar()`, de propósito: o defeito
# do §3.7 nunca foi acúmulo ao longo do tempo — o Qt recolhia depois. Era a
# janela entre limpar e repopular, em que a linha antiga continuava filha
# visível do container e aparecia por baixo da nova no repaint.
# ----------------------------------------------------------------------


def _widgets_do_layout(layout) -> set:
    """Só o que o layout de fato segura.

    Não serve olhar todos os filhos do container: o card do Caixa tem um título
    estático ("Últimos fechamentos") que é irmão do layout e sobrevive a toda
    recarga por construção — contá-lo acusaria bug onde não há.
    """
    return {
        item.widget()
        for indice in range(layout.count())
        if (item := layout.itemAt(indice)) is not None and item.widget() is not None
    }


def test_caixa_view_nao_deixa_fechamento_antigo_por_baixo_do_novo(
    qapp, caixas_service, impressao, gerente, caixa_aberto
):
    """`_atualizar_fechamentos()` roda a cada abertura da tela do Caixa."""
    view = CaixaView(caixas_service, impressao)
    view.atualizar()
    container = view._layout_fechamentos.parentWidget()
    antes = _widgets_do_layout(view._layout_fechamentos)
    assert antes, "o layout de fechamentos ficou vazio — o teste não provaria nada"

    view.atualizar()  # sem assentar(): o repaint acontece ANTES do ciclo de eventos

    ainda_na_arvore = {w for w in antes if w.parent() is container}
    assert not ainda_na_arvore, (
        f"{len(ainda_na_arvore)} widget(s) da leva anterior continuam filhos do container "
        "depois de repopular — é o texto sobreposto do §3.7 de volta."
    )


def test_mesas_view_nao_deixa_cartao_antigo_por_baixo_do_novo(qapp, comandas, mesa):
    """A grade de mesas é reorganizada a cada troca de filtro (Todas / Livres /
    Ocupadas / Fechando), que é o clique mais frequente da tela principal."""
    view = MesasView(comandas)
    view.carregar_mesas()
    container = view._grade.parentWidget()
    antes = _widgets_do_layout(view._grade)
    assert antes, "a grade ficou vazia — o teste não provaria nada"

    view.carregar_mesas()

    ainda_na_arvore = {w for w in antes if w.parent() is container}
    assert not ainda_na_arvore, (
        f"{len(ainda_na_arvore)} cartão(ões) da leva anterior continuam filhos da grade."
    )


def test_mesas_view_preserva_o_espacador_da_lista_de_comandas(qapp, comandas, mesa):
    """`manter_ao_final=1` não é detalhe: o último item do layout é um stretch
    fixo, e a lista de comandas ativas é inserida ANTES dele. Perder o stretch
    espalharia as linhas pela altura toda do painel."""
    view = MesasView(comandas)
    layout = view._layout_lista_comandas

    view.carregar_mesas()
    view.carregar_mesas()

    assert layout.count() >= 1
    assert layout.itemAt(layout.count() - 1).spacerItem() is not None, (
        "o stretch fixo do fim da lista foi levado junto na limpeza"
    )
