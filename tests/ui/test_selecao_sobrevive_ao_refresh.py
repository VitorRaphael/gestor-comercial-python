"""A seleção do usuário sobrevive ao refresh da tela. Ver §3.3, Fase 5.

Estes testes existem por causa de uma armadilha da própria Fase 5. As views
nunca zeravam a tabela antes de repopular — chamavam `setRowCount(len(dados))`
direto —, e nesse caminho o Qt **mantém** a linha corrente enquanto a contagem
não encolher. Trocar por uma limpeza de verdade (`limpar_tabela`) é o certo
para o determinismo de repaint, mas passar pelo zero larga a seleção.

Onde isso apareceria para o pai do Vitor: ele seleciona um produto, clica em
"Editar", salva — e o produto sai selecionado sozinho, com os botões Editar/
Excluir/Combo apagando na cara dele. Mesma coisa na tela de Impressoras, onde a
linha selecionada é o que decide qual impressora aparece no painel lateral.

`test_tabelas.py` prova a mecânica de `preservar_selecao`. Estes daqui provam a
consequência, nas duas telas reais que leem `currentRow()` logo depois de
repopular: são eles que ficam vermelhos se alguém tirar o `preservar_selecao=True`
de `cardapio_view` ou de `impressoras_view`.
"""

from __future__ import annotations

from decimal import Decimal

from gestor_comercial.ui.views.cardapio_view import CardapioView
from gestor_comercial.ui.views.impressoras_view import ImpressorasView

PRODUTOS = 4
LINHA_ESCOLHIDA = 2


def _cardapio_com_produtos(cardapio, categoria) -> CardapioView:
    for indice in range(PRODUTOS):
        cardapio.criar_produto(
            nome=f"Produto {indice}", preco=Decimal("10.00"), categoria_id=categoria.id
        )
    view = CardapioView(cardapio)
    view.atualizar()
    return view


def test_cardapio_mantem_o_produto_selecionado_depois_de_atualizar(
    qapp, cardapio, categoria, gerente
):
    view = _cardapio_com_produtos(cardapio, categoria)
    painel = view._painel_produtos
    painel.tabela.selectRow(LINHA_ESCOLHIDA)
    escolhido = painel.produto_atual()
    assert escolhido is not None, "o teste precisa de um produto selecionado para valer"

    view.atualizar()

    assert painel.tabela.currentRow() == LINHA_ESCOLHIDA
    assert painel.produto_atual().id == escolhido.id


def test_cardapio_mantem_os_botoes_do_rodape_habilitados_depois_de_atualizar(
    qapp, cardapio, categoria, gerente
):
    """O sintoma visível: `_emitir_selecao()` roda no fim de `atualizar()` e é
    ele que liga/desliga Editar, Ativar/Desativar e Excluir pela seleção."""
    view = _cardapio_com_produtos(cardapio, categoria)
    painel = view._painel_produtos
    painel.tabela.selectRow(LINHA_ESCOLHIDA)

    view.atualizar()

    assert painel._botao_editar.isEnabled()
    assert painel._botao_excluir.isEnabled()


def test_cardapio_nao_avisa_selecao_vazia_durante_o_refresh(qapp, cardapio, categoria, gerente):
    """`produto_selecionado` é ouvido pela `CardapioView` para montar a barra de
    ações. Um `None` no meio do refresh não pode vazar para fora — do lado de
    quem escuta, a seleção nunca deixou de existir."""
    view = _cardapio_com_produtos(cardapio, categoria)
    painel = view._painel_produtos
    painel.tabela.selectRow(LINHA_ESCOLHIDA)
    avisos: list[object] = []
    painel.produto_selecionado.connect(avisos.append)

    view.atualizar()

    assert None not in avisos, f"a tela anunciou seleção vazia durante o refresh: {avisos}"


def test_impressoras_mantem_a_linha_selecionada_depois_de_atualizar(
    qapp, cardapio, impressao, uow, impressora
):
    """A linha corrente é o que alimenta o painel lateral de categorias e o
    rótulo "SELECIONADA · ...". Perdê-la a cada `atualizar()` esvaziaria os dois
    logo depois de o usuário editar a impressora que estava vendo."""
    from gestor_comercial.domain.impressora import Impressora

    uow.impressoras.salvar(Impressora(nome="Balcão", colunas=32, ativa=True))
    view = ImpressorasView(cardapio, impressao)
    view.atualizar()
    view._tabela.selectRow(1)
    escolhida = view._impressora_selecionada()
    assert escolhida is not None, "o teste precisa de uma impressora selecionada para valer"

    view.atualizar()

    assert view._tabela.currentRow() == 1
    assert view._impressora_selecionada().id == escolhida.id
