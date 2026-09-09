"""A tela de Cardápio como hierarquia Categoria → Subcategoria → Produtos. §9.9.

A primeira versão da subcategoria (§9.8) a pendurou como um selo na linha do
produto. Estava de cabeça para baixo — a subcategoria **contém** produtos — e o
Vitor apontou. Esta suíte cobre a estrutura que ficou no lugar, e as quatro
coisas que a fariam atrapalhar em vez de ajudar:

1. **a árvore mostra a hierarquia** — abrir uma categoria revela as subdivisões
   dela com a contagem de cada uma, e uma categoria aberta por vez;
2. **a tabela agrupa** — os itens vêm sob um cabeçalho por subdivisão, e clicar
   numa subdivisão (na árvore ou na pílula) mostra só ela;
3. **nada fica cortado** — foi o pedido explícito. O nome da categoria tem que
   caber na coluna, e a linha da árvore tem que ter a altura do que mora dentro
   dela. O defeito anterior era exatamente esse: `setItemWidget` numa lista
   **não** dimensiona o item, e as linhas de duas alturas eram desenhadas dentro
   da altura de uma;
4. **nada sobra na memória** — o RNF do Celeron, numa tela que fica aberta o
   turno inteiro.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from gestor_comercial.ui.views.cardapio_view import (
    _SUB_NENHUMA,
    _SUB_TODAS,
    CardapioView,
    SelecaoCardapio,
    _criar_celula_produto,
)


@pytest.fixture
def cardapio_montado(cardapio, gerente):
    """Lanches com duas subdivisões e um item solto; Bebidas sem nenhuma.

    É o estado intermediário real: o gerente organiza uma categoria por vez, e a
    tela tem que funcionar durante a organização, não só no fim.
    """
    lanches = cardapio.criar_categoria("Lanches")
    bebidas = cardapio.criar_categoria("Bebidas")
    podrao = cardapio.criar_subcategoria(lanches.id, "Podrão")
    artesanal = cardapio.criar_subcategoria(lanches.id, "Artesanal")
    cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id)
    cardapio.criar_produto("X Tudo", Decimal("16.00"), lanches.id, subcategoria_id=podrao.id)
    cardapio.criar_produto(
        "X Missão Impossível", Decimal("28.00"), lanches.id, subcategoria_id=artesanal.id
    )
    cardapio.criar_produto("X Egg", Decimal("15.00"), lanches.id)
    cardapio.criar_produto("Coca Lata", Decimal("8.00"), bebidas.id)
    return {"lanches": lanches, "bebidas": bebidas, "podrao": podrao, "artesanal": artesanal}


@pytest.fixture
def tela(qapp, cardapio, cardapio_montado):
    view = CardapioView(cardapio)
    yield view
    view.deleteLater()


def _item_categoria(tela: CardapioView, nome: str):
    arvore = tela._painel_categorias.arvore
    for indice in range(arvore.topLevelItemCount()):
        item = arvore.topLevelItem(indice)
        widget = arvore.itemWidget(item, 0)
        rotulos = [r.text() for r in widget.findChildren(QLabel)] if widget else []
        if nome in rotulos:
            return item
    raise AssertionError(f"categoria '{nome}' não está na árvore")


def _abrir(tela: CardapioView, nome: str):
    """Faz o que o clique na categoria faz: expande e seleciona "Todas"."""
    item = _item_categoria(tela, nome)
    arvore = tela._painel_categorias.arvore
    arvore.setCurrentItem(item)
    tela._painel_categorias._ao_clicar(item, 0)
    arvore.setCurrentItem(item.child(0))
    return item


def _filhos(item) -> list[tuple[str, str]]:
    return [(item.child(i).text(0), item.child(i).text(1)) for i in range(item.childCount())]


def _linhas_visiveis(tela: CardapioView) -> list[str]:
    """O que a tabela mostra, com os cabeçalhos de grupo marcados por `#`."""
    painel = tela._painel_produtos
    saida = []
    for linha, produto in enumerate(painel._linhas):
        if painel.tabela.isRowHidden(linha):
            continue
        if produto is None:
            celula = painel.tabela.cellWidget(linha, 0)
            nome = next(
                r.text() for r in celula.findChildren(QLabel) if r.objectName() == "grupoNome"
            )
            saida.append(f"# {nome}")
        else:
            saida.append(produto.nome)
    return saida


def _pills(tela: CardapioView) -> list[str]:
    return [pill.text() for pill in tela._painel_produtos._pills.values()]


# ---------------------------------------------------------------------------
# A árvore
# ---------------------------------------------------------------------------


def test_a_categoria_mostra_quantas_subs_e_quantos_itens_tem(tela):
    item = _item_categoria(tela, "Lanches")
    widget = tela._painel_categorias.arvore.itemWidget(item, 0)

    subtitulo = next(
        r.text() for r in widget.findChildren(QLabel) if r.objectName() == "categoriaSubtitulo"
    )

    assert subtitulo == "2 SUBS · 4 ITENS"


def test_a_categoria_vazia_ganha_o_badge_vazio(tela, cardapio):
    cardapio.criar_categoria("Doces")
    tela.atualizar()

    widget = tela._painel_categorias.arvore.itemWidget(_item_categoria(tela, "Doces"), 0)
    badges = [r.objectName() for r in widget.findChildren(QLabel) if r.text() in ("VAZIO", "ATIVO")]

    assert badges == ["badgeVazio"]


def test_abrir_a_categoria_revela_as_subdivisoes_com_a_contagem(tela):
    item = _abrir(tela, "Lanches")

    assert _filhos(item) == [
        ("Todas", "4"),
        ("Artesanal", "1"),
        ("Podrão", "2"),
        ("Sem subcategoria", "1"),
    ]


def test_sem_subcategoria_so_aparece_quando_ha_item_solto(tela, cardapio, cardapio_montado):
    """A fila de trabalho de quem organiza — e ela some quando o trabalho acabou."""
    solto = next(p for p in cardapio.listar_produtos() if p.nome == "X Egg")
    cardapio.atualizar_produto(
        solto.id,
        solto.nome,
        solto.preco,
        solto.custo,
        cardapio_montado["lanches"].id,
        subcategoria_id=cardapio_montado["podrao"].id,
    )
    tela.atualizar()

    assert [nome for nome, _ in _filhos(_abrir(tela, "Lanches"))] == [
        "Todas",
        "Artesanal",
        "Podrão",
    ]


def test_categoria_sem_subdivisao_so_tem_todas(tela):
    assert [nome for nome, _ in _filhos(_abrir(tela, "Bebidas"))] == ["Todas"]


def test_uma_categoria_aberta_por_vez(tela):
    """Com quinze categorias, deixar todas expandidas transforma a coluna num
    rolo — e o gerente organiza uma de cada vez."""
    _abrir(tela, "Lanches")

    _abrir(tela, "Bebidas")

    assert _item_categoria(tela, "Lanches").isExpanded() is False
    assert _item_categoria(tela, "Bebidas").isExpanded() is True


def test_a_linha_da_categoria_tem_a_altura_do_que_mora_dentro_dela(tela):
    """O defeito que o Vitor viu: `setItemWidget` numa lista NÃO dimensiona o
    item, e o widget de duas linhas era desenhado na altura de uma — nome e
    subtítulo saíam cortados ao meio."""
    arvore = tela._painel_categorias.arvore
    item = _item_categoria(tela, "Lanches")
    widget = arvore.itemWidget(item, 0)

    assert item.sizeHint(0).height() >= widget.sizeHint().height(), (
        "a linha da árvore é mais baixa que o conteúdo dela — o texto sai cortado"
    )


def test_o_nome_da_categoria_cabe_na_coluna(qapp, tela):
    """O outro corte: a coluna da contagem nasce com `stretchLastSection` ligado
    e tomava metade da largura, deixando "Acompanhamentos" em "Acompa"."""
    tela.resize(1366, 738)
    tela.show()
    qapp.processEvents()
    arvore = tela._painel_categorias.arvore
    item = _item_categoria(tela, "Lanches")

    widget = arvore.itemWidget(item, 0)

    assert widget.width() >= widget.sizeHint().width(), (
        f"o widget da categoria tem {widget.width()}px para {widget.sizeHint().width()}px "
        "de conteúdo — o nome sai cortado"
    )
    assert item.isFirstColumnSpanned(), "a linha da categoria não ocupa a largura inteira"
    # A coluna da contagem é do NOME DA SUBDIVISÃO que ela rouba, e a linha da
    # categoria não sente isso porque ocupa as duas colunas. Sem esta segunda
    # asserção, religar o `stretchLastSection` (que nasce ligado no Qt e já
    # tinha dado 146 dos 293px à contagem) passaria despercebido.
    largura_da_contagem = arvore.columnWidth(1)
    assert largura_da_contagem <= tela._painel_categorias.LARGURA_CONTAGEM_PX, (
        f"a coluna da contagem tomou {largura_da_contagem}px — o nome da "
        "subcategoria sai cortado"
    )


def test_a_busca_acha_a_categoria_pela_subdivisao(tela):
    """Buscar "podrão" e não achar nada porque "Podrão" é subcategoria, e não
    categoria, seria a busca mentindo sobre o que existe no cardápio."""
    tela._painel_categorias._campo_busca.setText("podrao")

    assert _item_categoria(tela, "Lanches").isHidden() is False
    assert _item_categoria(tela, "Bebidas").isHidden() is True


# ---------------------------------------------------------------------------
# A tabela agrupada
# ---------------------------------------------------------------------------


def test_todas_agrupa_os_produtos_por_subdivisao(tela):
    _abrir(tela, "Lanches")

    assert _linhas_visiveis(tela) == [
        "# ARTESANAL",
        "X Missão Impossível",
        "# PODRÃO",
        "X Burguer",
        "X Tudo",
        "# SEM SUBCATEGORIA",
        "X Egg",
    ]


def test_o_cabecalho_do_grupo_diz_quantos_itens_tem(tela):
    _abrir(tela, "Lanches")
    painel = tela._painel_produtos

    celula = painel.tabela.cellWidget(painel._linhas.index(None), 0)
    contagem = next(
        r.text() for r in celula.findChildren(QLabel) if r.objectName() == "grupoContagem"
    )

    assert contagem == "· 1 ITEM"


def test_escolher_uma_subdivisao_mostra_so_ela_e_sem_cabecalho(tela):
    """Numa subdivisão específica o cabeçalho de grupo seria um só, dizendo o
    que o título da tela já diz."""
    item = _abrir(tela, "Lanches")
    tela._painel_categorias.arvore.setCurrentItem(item.child(2))  # Podrão

    assert _linhas_visiveis(tela) == ["X Burguer", "X Tudo"]
    assert tela._painel_produtos._titulo.text() == "Podrão"


def test_sem_subcategoria_mostra_a_fila_de_trabalho(tela):
    item = _abrir(tela, "Lanches")
    tela._painel_categorias.arvore.setCurrentItem(item.child(3))

    assert _linhas_visiveis(tela) == ["X Egg"]
    assert tela._painel_produtos._titulo.text() == "Sem subcategoria"


def test_a_subdivisao_vazia_aparece_com_a_tabela_vazia(tela, cardapio, cardapio_montado):
    """"Está aqui, sem itens ainda" — enquanto uma tela em branco diria "não
    existe". É o estado normal de quem acabou de criar a subdivisão."""
    cardapio.criar_subcategoria(cardapio_montado["lanches"].id, "Prensado")
    tela.atualizar()
    item = _abrir(tela, "Lanches")
    tela._painel_categorias.arvore.setCurrentItem(item.child(3))  # Prensado

    assert tela._painel_produtos._titulo.text() == "Prensado"
    assert _linhas_visiveis(tela) == []


def test_o_cabecalho_diz_a_categoria_e_a_impressora(tela, cardapio, cardapio_montado):
    """A impressora está ali porque é para onde os itens daquela categoria vão
    sair — e é a informação que a subcategoria NÃO muda (§9.8)."""
    impressora = cardapio.criar_impressora("Cozinha")
    cardapio.associar_impressora(cardapio_montado["lanches"].id, impressora.id)
    tela.atualizar()

    _abrir(tela, "Lanches")

    assert tela._painel_produtos._eyebrow.text() == "LANCHES · COZINHA"
    assert tela._painel_produtos._titulo.text() == "Todas as subcategorias"


def test_categoria_sem_impressora_diz_isso_em_vez_de_ficar_em_branco(tela):
    _abrir(tela, "Lanches")

    assert tela._painel_produtos._eyebrow.text() == "LANCHES · SEM IMPRESSORA"


# ---------------------------------------------------------------------------
# As pílulas de filtro
# ---------------------------------------------------------------------------


def test_as_pilulas_listam_as_subdivisoes_com_a_contagem(tela):
    _abrir(tela, "Lanches")

    assert _pills(tela) == ["TODAS", "ARTESANAL · 1", "PODRÃO · 2", "SEM SUBCATEGORIA · 1"]


def test_a_faixa_de_pilulas_some_na_categoria_sem_subdivisao(tela):
    _abrir(tela, "Bebidas")

    assert tela._painel_produtos._pills == {}
    assert tela._painel_produtos._faixa.isVisibleTo(tela._painel_produtos) is False


def test_clicar_na_pilula_filtra_sem_mexer_na_arvore(tela):
    _abrir(tela, "Lanches")

    tela._painel_produtos._pills["Podrão"].click()

    assert _linhas_visiveis(tela) == ["X Burguer", "X Tudo"]
    assert tela._painel_produtos._pills["Podrão"].property("ativa") is True
    assert tela._painel_produtos._pills[_SUB_TODAS].property("ativa") is False


def test_a_contagem_da_pilula_nao_muda_com_o_filtro(tela):
    """Seria a tela dizendo que a subdivisão encolheu quando o gerente clicou
    em outra."""
    _abrir(tela, "Lanches")

    tela._painel_produtos._pills[_SUB_NENHUMA].click()

    assert _pills(tela) == ["TODAS", "ARTESANAL · 1", "PODRÃO · 2", "SEM SUBCATEGORIA · 1"]


def test_trocar_de_categoria_solta_o_filtro(tela):
    """Filtrar Lanches por "Podrão" e clicar em Bebidas deixaria a tabela vazia,
    com a faixa escondida e nada na tela explicando por quê."""
    _abrir(tela, "Lanches")
    tela._painel_produtos._pills["Podrão"].click()

    _abrir(tela, "Bebidas")

    assert _linhas_visiveis(tela) == ["Coca Lata"]


# ---------------------------------------------------------------------------
# A linha do produto
# ---------------------------------------------------------------------------


def test_o_produto_nao_carrega_mais_o_selo_da_subcategoria(tela, cardapio, cardapio_montado):
    """O selo saiu: ele repetia, uma vez por linha, o que o cabeçalho do grupo
    diz uma vez — e disputava largura justamente com o nome do produto."""
    produto = next(p for p in cardapio.listar_produtos() if p.nome == "X Burguer")

    celula = _criar_celula_produto(produto)
    try:
        nomes = [r.text() for r in celula.findChildren(QLabel) if r.text()]
        assert "PODRÃO" not in nomes
        assert "X Burguer" in nomes
    finally:
        celula.deleteLater()


def test_o_combo_virou_selo_ao_lado_do_nome(tela, cardapio, cardapio_montado):
    """A coluna "Tipo" existia para uma marca que aparece em 4 dos 113 produtos
    do cardápio real, e os 90px dela faziam falta ao nome."""
    from gestor_comercial.ui.views.cardapio_view import _COLUNAS_PRODUTOS

    combo = cardapio.criar_produto(
        "Combo Casal", Decimal("40.00"), cardapio_montado["lanches"].id, is_combo=True
    )

    celula = _criar_celula_produto(combo)
    try:
        badges = [r.objectName() for r in celula.findChildren(QLabel) if r.text() == "COMBO"]
        assert badges == ["badgeCombo"]
        assert "Tipo" not in _COLUNAS_PRODUTOS
    finally:
        celula.deleteLater()


def test_a_busca_do_cardapio_acha_pela_subcategoria(tela):
    """A mesma busca do modal de lançamento: telas que buscam diferente sobre o
    mesmo cardápio é como o gerente conclui que o produto sumiu."""
    _abrir(tela, "Lanches")

    tela._painel_produtos._campo_busca.setText("podrao")

    assert _linhas_visiveis(tela) == ["# PODRÃO", "X Burguer", "X Tudo"]


def test_o_cabecalho_de_grupo_some_quando_a_busca_esvazia_o_grupo(tela):
    _abrir(tela, "Lanches")

    tela._painel_produtos._campo_busca.setText("missão")

    assert _linhas_visiveis(tela) == ["# ARTESANAL", "X Missão Impossível"]


def test_o_cabecalho_de_grupo_nao_pode_ser_selecionado(tela):
    """Clicar nele não pode habilitar Editar/Excluir apontando para produto
    nenhum."""
    _abrir(tela, "Lanches")
    painel = tela._painel_produtos

    linha_do_grupo = painel._linhas.index(None)
    painel.tabela.selectRow(linha_do_grupo)

    # `produto_atual()` sozinho responderia `None` de qualquer jeito (a linha
    # não tem produto), então ele não distingue nada. O que distingue é a linha
    # NÃO ficar marcada: com ela selecionada, a tabela mostraria uma faixa azul
    # sobre um cabeçalho e o rodapé diria "SELECIONE UM PRODUTO" ao lado de uma
    # linha aparentemente escolhida.
    assert painel.tabela.selectedItems() == [], "o cabeçalho de grupo ficou selecionado"
    assert painel.produto_atual() is None
    assert painel._botao_editar.isEnabled() is False


def test_selecionar_um_produto_com_a_tabela_agrupada_devolve_o_produto_certo(tela):
    """Com cabeçalho de grupo no meio, o índice da linha deixou de ser o índice
    do produto — e `produto_atual()` continua tendo que acertar."""
    _abrir(tela, "Lanches")
    painel = tela._painel_produtos

    painel.tabela.selectRow(painel._linhas.index(None) + 1)

    assert painel.produto_atual().nome == "X Missão Impossível"


# ---------------------------------------------------------------------------
# Memória
# ---------------------------------------------------------------------------


def test_trocar_de_categoria_nao_acumula_pilulas(tela, assentar):
    """O RNF do Celeron, numa tela que fica aberta o turno inteiro."""
    for _ in range(10):
        _abrir(tela, "Lanches")
        _abrir(tela, "Bebidas")
    _abrir(tela, "Lanches")
    assentar()

    penduradas = [
        botao
        for botao in tela._painel_produtos._faixa.findChildren(QPushButton)
        if botao.objectName() == "pillSubcategoria"
    ]
    assert len(penduradas) == 4, f"{len(penduradas)} pílulas presas depois de 10 trocas"


def test_muitos_refreshs_nao_incham_a_arvore(tela, assentar):
    tela.atualizar()
    assentar()
    antes = len(tela._painel_categorias.arvore.findChildren(QWidget))

    for _ in range(20):
        tela.atualizar()
    assentar()

    depois = len(tela._painel_categorias.arvore.findChildren(QWidget))
    assert depois <= antes, f"a árvore cresceu de {antes} para {depois} widgets em 20 refreshs"


def test_a_selecao_sobrevive_ao_refresh(tela):
    """Editar um produto chama `atualizar()`, e a árvore não pode voltar para a
    primeira categoria levando o gerente junto."""
    item = _abrir(tela, "Lanches")
    tela._painel_categorias.arvore.setCurrentItem(item.child(2))  # Podrão
    assert tela._painel_categorias.selecao_atual().chave == "Podrão"

    tela.atualizar()

    selecao = tela._painel_categorias.selecao_atual()
    assert selecao.categoria.nome == "Lanches"
    assert selecao.chave == "Podrão"
    assert _linhas_visiveis(tela) == ["X Burguer", "X Tudo"]


def test_selecao_cardapio_e_um_tipo_e_nao_dois_parametros_soltos():
    """Uma subcategoria sem a categoria dela não identifica nada: "Podrão" pode
    existir em duas categorias."""
    selecao = SelecaoCardapio(categoria=None)

    assert selecao.chave == _SUB_TODAS
    assert selecao.e_todas is True
