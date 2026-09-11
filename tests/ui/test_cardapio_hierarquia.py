"""A tela de Cardápio como hierarquia Categoria → Subcategoria → Produtos. §9.9.

A primeira versão da subcategoria (§9.8) a pendurou como um selo na linha do
produto. Estava de cabeça para baixo — a subcategoria **contém** produtos — e o
Vitor apontou. Esta suíte cobre a estrutura que ficou no lugar, e as quatro
coisas que a fariam atrapalhar em vez de ajudar:

1. **a árvore mostra a hierarquia** — abrir uma categoria revela as subdivisões
   dela com a contagem de cada uma, e uma categoria aberta por vez;
2. **a lista agrupa** — os itens vêm em blocos por subdivisão, e escolher uma
   subdivisão na árvore mostra só ela;
3. **nada fica cortado** — foi o pedido explícito. O nome da categoria tem que
   caber na coluna, e a linha da árvore tem que ter a altura do que mora dentro
   dela;
4. **nada sobra na memória** — o RNF do Celeron, numa tela que fica aberta o
   turno inteiro.

## O que mudou no §9.11, e por que estes testes mudaram junto

A direita deixou de ser uma tabela e virou blocos pintados por delegado, e a
árvore deixou de hospedar um widget por categoria. Os testes que liam a tabela
por dentro (`tabela`, `cellWidget`, `itemWidget`) passaram a ler o mesmo dado
pelo instantâneo que cada linha carrega — a asserção de comportamento de cada
um é a mesma. Três coisas mudaram de propósito, e os testes delas dizem o novo:

* numa subdivisão escolhida o **cabeçalho do bloco aparece** — o topo do
  painel passou a ser a categoria, e é o bloco que diz qual subdivisão está na
  tela (antes era um título "Podrão" no topo, e o cabeçalho sobrava);
* as **pílulas de filtro saíram** — repetiam a árvore, filtrando sem mover a
  seleção dela; os testes delas viraram os equivalentes na árvore;
* o selo **VAZIO** virou o contador redondo com **0**, que é o do mockup.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QFontMetrics
from PySide6.QtWidgets import QWidget

import gestor_comercial
from gestor_comercial.ui.views.cardapio_view import (
    _SUB_NENHUMA,
    _SUB_TODAS,
    CardapioView,
    SelecaoCardapio,
)
from gestor_comercial.ui.widgets.cardapio_cartoes import PAPEL_LINHA, TipoDeItem, _fonte


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


@pytest.fixture
def com_metrica_de_texto(qapp):
    """A fonte da marca registrada, para as medidas de largura valerem.

    A plataforma `offscreen` sobe com o banco de fontes vazio, e sem fonte todo
    texto mede quase nada — um teste de "o nome cabe" passaria verde sem ter
    medido o nome que o balcão vê. Mesmo motivo e mesma fonte da fixture gêmea
    de `test_mesas_ocupadas_em_vermelho.py`.
    """
    caminho = (
        Path(gestor_comercial.__file__).resolve().parents[2]
        / "resources"
        / "fonts"
        / "ArchivoBlack-Regular.ttf"
    )
    if not caminho.exists():  # pragma: no cover - só num checkout incompleto
        pytest.skip(f"fonte da marca ausente em {caminho}")
    identificador = QFontDatabase.addApplicationFont(str(caminho))
    assert identificador != -1, "o Qt recusou a fonte da marca"
    try:
        yield
    finally:
        QFontDatabase.removeApplicationFont(identificador)


def _item_categoria(tela: CardapioView, nome: str):
    painel = tela._painel_categorias
    for indice in range(painel.arvore.topLevelItemCount()):
        item = painel.arvore.topLevelItem(indice)
        if painel._nome_da_categoria(item) == nome:
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
    linhas = [item.child(i).data(0, PAPEL_LINHA) for i in range(item.childCount())]
    return [(linha.rotulo, str(linha.total)) for linha in linhas]


def _linhas_visiveis(tela: CardapioView) -> list[str]:
    """O que a lista mostra, com os cabeçalhos de bloco marcados por `#`.

    A busca não esconde linha: ela refaz a lista a partir do instantâneo, então
    "visível" é simplesmente "está na lista".
    """
    lista = tela._painel_produtos.lista
    saida = []
    for linha in range(lista.count()):
        dado = lista.item_da_linha(linha)
        if dado.tipo is TipoDeItem.CABECALHO:
            saida.append(f"# {dado.grupo.rotulo.upper()}")
        elif dado.tipo is TipoDeItem.PRODUTO:
            saida.append(dado.produto.nome)
        elif dado.tipo is TipoDeItem.VAZIO:
            saida.append("(vazio)")
    return saida


def _foto(tela: CardapioView, nome: str):
    lista = tela._painel_produtos.lista
    for linha in range(lista.count()):
        dado = lista.item_da_linha(linha)
        if dado.produto is not None and dado.produto.nome == nome:
            return dado.produto
    raise AssertionError(f"'{nome}' não está na lista")


# ---------------------------------------------------------------------------
# A árvore
# ---------------------------------------------------------------------------


def test_a_categoria_mostra_quantas_subs_e_quantos_itens_tem(tela):
    linha = _item_categoria(tela, "Lanches").data(0, PAPEL_LINHA)

    assert linha.subtitulo == "2 SUBCATEGORIAS"
    assert linha.produtos == 4, "o contador redondo da categoria é o total de produtos"


def test_a_categoria_vazia_mostra_zero_no_contador(tela, cardapio):
    """O selo VAZIO do §9.9 virou o contador com 0 do mockup — a mesma
    informação, no lugar em que as outras categorias dizem quantos têm."""
    cardapio.criar_categoria("Doces")
    tela.atualizar()

    linha = _item_categoria(tela, "Doces").data(0, PAPEL_LINHA)

    assert linha.produtos == 0
    assert linha.subtitulo == "0 SUBCATEGORIAS"


def test_categoria_desativada_diz_isso_no_subtitulo(tela, cardapio, cardapio_montado):
    """Desativar a categoria tira os produtos dela do balcão: é a única coisa
    da linha que muda o que se vende, e ela tem que estar escrita."""
    cardapio.desativar_categoria(cardapio_montado["bebidas"].id)
    tela.atualizar()

    linha = _item_categoria(tela, "Bebidas").data(0, PAPEL_LINHA)

    assert linha.ativa is False
    assert linha.subtitulo == "DESATIVADA · 0 SUBCATEGORIAS"


def test_abrir_a_categoria_revela_as_subdivisoes_com_a_contagem(tela):
    item = _abrir(tela, "Lanches")

    assert _filhos(item) == [
        ("Todas as subcategorias", "4"),
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
        "Todas as subcategorias",
        "Artesanal",
        "Podrão",
    ]


def test_categoria_sem_subdivisao_so_tem_todos_os_produtos(tela):
    """"Todas as subcategorias" numa categoria que não tem nenhuma seria a
    tela falando de uma coisa que não existe ali."""
    assert [nome for nome, _ in _filhos(_abrir(tela, "Bebidas"))] == ["Todos os produtos"]


def test_uma_categoria_aberta_por_vez(tela):
    """Com quinze categorias, deixar todas expandidas transforma a coluna num
    rolo — e o gerente organiza uma de cada vez."""
    _abrir(tela, "Lanches")

    _abrir(tela, "Bebidas")

    assert _item_categoria(tela, "Lanches").isExpanded() is False
    assert _item_categoria(tela, "Bebidas").isExpanded() is True


def test_a_linha_da_categoria_tem_a_altura_do_que_mora_dentro_dela(
    qapp, com_metrica_de_texto, cardapio, cardapio_montado
):
    """O defeito que o Vitor viu no §9.9: a linha de duas alturas (nome +
    subtítulo) era desenhada dentro da altura de uma e saía cortada ao meio.
    Agora a altura sai da fonte — e é isso que este teste cobra, com a fonte
    da marca registrada, senão ele mediria outra coisa."""
    tela = CardapioView(cardapio)
    tela.resize(1366, 738)
    tela.show()
    qapp.processEvents()
    try:
        arvore = tela._painel_categorias.arvore
        item = _item_categoria(tela, "Lanches")

        altura = arvore.visualItemRect(item).height()
        conteudo = arvore.itemDelegate().altura_do_conteudo(arvore.font())

        assert altura >= conteudo, (
            f"a linha tem {altura}px para {conteudo}px de conteúdo — o texto sai cortado"
        )
    finally:
        tela.close()
        tela.deleteLater()


def test_o_nome_da_categoria_cabe_na_coluna(qapp, com_metrica_de_texto, cardapio, gerente):
    """O outro corte do §9.9: "Acompanhamentos" saía "Acompa". A linha agora é
    uma coluna só, da largura inteira — nenhuma coluna de contagem rouba
    espaço do nome —, e o nome mais comprido do cardápio real cabe inteiro."""
    cardapio.criar_categoria("Acompanhamentos")
    tela = CardapioView(cardapio)
    tela.resize(1366, 738)
    tela.show()
    qapp.processEvents()
    try:
        arvore = tela._painel_categorias.arvore
        item = _item_categoria(tela, "Acompanhamentos")

        retangulo = arvore.visualItemRect(item)
        area = arvore.itemDelegate().area_do_nome(retangulo)
        largura = QFontMetrics(_fonte(arvore.font(), 13)).horizontalAdvance("Acompanhamentos")

        assert arvore.columnCount() == 1
        assert retangulo.width() >= arvore.viewport().width() - 1, (
            "a linha da categoria não ocupa a largura inteira"
        )
        assert largura <= area.width(), (
            f"'Acompanhamentos' mede {largura}px e o espaço do nome tem {area.width():.0f}px"
        )
    finally:
        tela.close()
        tela.deleteLater()


def test_a_busca_acha_a_categoria_pela_subdivisao(tela):
    """Buscar "podrão" e não achar nada porque "Podrão" é subcategoria, e não
    categoria, seria a busca mentindo sobre o que existe no cardápio."""
    tela._painel_categorias._campo_busca.setText("podrao")

    assert _item_categoria(tela, "Lanches").isHidden() is False
    assert _item_categoria(tela, "Bebidas").isHidden() is True


@pytest.mark.parametrize("termo", ["todas", "sem sub", "todos os produtos"])
def test_a_busca_da_arvore_nao_casa_pelas_entradas_fixas(tela, termo):
    """"Todas as subcategorias" e "Sem subcategoria" existem em quase toda
    categoria: casar por elas trazia o cardápio inteiro para qualquer busca
    com "sub" ou "todas"."""
    tela._painel_categorias._campo_busca.setText(termo)

    assert _item_categoria(tela, "Lanches").isHidden() is True
    assert _item_categoria(tela, "Bebidas").isHidden() is True


# ---------------------------------------------------------------------------
# A lista em blocos
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


def test_o_cabecalho_do_bloco_diz_quantos_produtos_tem(tela):
    _abrir(tela, "Lanches")

    cabecalho = tela._painel_produtos.lista.item_da_linha(0)

    assert cabecalho.tipo is TipoDeItem.CABECALHO
    assert cabecalho.grupo.contagem_texto == "1 PRODUTO"


def test_escolher_uma_subdivisao_mostra_so_ela_com_o_cabecalho_dela(tela):
    """O topo do painel passou a ser a CATEGORIA (§9.11); quem diz qual
    subdivisão está na tela é o cabeçalho do bloco — e ele traz o link de
    editá-la."""
    item = _abrir(tela, "Lanches")
    tela._painel_categorias.arvore.setCurrentItem(item.child(2))  # Podrão

    assert _linhas_visiveis(tela) == ["# PODRÃO", "X Burguer", "X Tudo"]
    assert tela._painel_produtos._titulo.texto_completo() == "Lanches"


def test_sem_subcategoria_mostra_a_fila_de_trabalho(tela):
    item = _abrir(tela, "Lanches")
    tela._painel_categorias.arvore.setCurrentItem(item.child(3))

    assert _linhas_visiveis(tela) == ["# SEM SUBCATEGORIA", "X Egg"]


def test_a_subdivisao_vazia_aparece_com_o_aviso(tela, cardapio, cardapio_montado):
    """"Está aqui, sem itens ainda" — enquanto uma tela em branco diria "não
    existe". É o estado normal de quem acabou de criar a subdivisão."""
    cardapio.criar_subcategoria(cardapio_montado["lanches"].id, "Prensado")
    tela.atualizar()
    item = _abrir(tela, "Lanches")
    tela._painel_categorias.arvore.setCurrentItem(item.child(3))  # Prensado

    assert _linhas_visiveis(tela) == ["# PRENSADO", "(vazio)"]


def test_o_topo_diz_a_categoria_e_a_impressora(tela, cardapio, cardapio_montado):
    """A impressora está ali porque é para onde os itens daquela categoria vão
    sair — e é a informação que a subcategoria NÃO muda (§9.8)."""
    impressora = cardapio.criar_impressora("Cozinha")
    cardapio.associar_impressora(cardapio_montado["lanches"].id, impressora.id)
    tela.atualizar()

    _abrir(tela, "Lanches")

    painel = tela._painel_produtos
    assert painel._titulo.texto_completo() == "Lanches"
    assert painel._meta.texto_completo() == "COZINHA · 4 ITENS · 2 SUBCATEGORIAS"


def test_categoria_sem_impressora_diz_isso_em_vez_de_ficar_em_branco(tela):
    _abrir(tela, "Lanches")

    assert tela._painel_produtos._meta.texto_completo().startswith("SEM IMPRESSORA · ")


def test_categoria_sem_subdivisao_nao_tem_cabecalho_de_bloco(tela):
    """Um "SEM SUBCATEGORIA" em cima de todos os itens de uma categoria que não
    tem subdivisão nenhuma diria o óbvio — o bloco sai sem cabeçalho."""
    _abrir(tela, "Bebidas")

    assert _linhas_visiveis(tela) == ["Coca Lata"]


def test_a_contagem_do_bloco_nao_encolhe_com_a_busca(tela):
    """Era a garantia das pílulas do §9.9, e continua valendo no cabeçalho do
    bloco: buscar não pode fazer a subdivisão parecer ter encolhido."""
    _abrir(tela, "Lanches")

    tela._painel_produtos._campo_busca.setText("burguer")

    cabecalho = tela._painel_produtos.lista.item_da_linha(0)
    assert _linhas_visiveis(tela) == ["# PODRÃO", "X Burguer"]
    assert cabecalho.grupo.contagem_texto == "2 PRODUTOS"


def test_trocar_de_categoria_solta_a_subdivisao(tela):
    """Estar em "Lanches → Podrão" e clicar em Bebidas não pode levar o filtro
    junto: a lista ficaria vazia sem nada na tela explicando por quê."""
    item = _abrir(tela, "Lanches")
    tela._painel_categorias.arvore.setCurrentItem(item.child(2))  # Podrão

    _abrir(tela, "Bebidas")

    assert _linhas_visiveis(tela) == ["Coca Lata"]
    assert tela._painel_categorias.selecao_atual().chave == _SUB_TODAS


# ---------------------------------------------------------------------------
# A linha do produto
# ---------------------------------------------------------------------------


def test_o_produto_nao_carrega_mais_o_selo_da_subcategoria(tela):
    """O selo saiu no §9.9: ele repetia, uma vez por linha, o que o cabeçalho
    do bloco diz uma vez — e disputava largura justamente com o nome."""
    _abrir(tela, "Lanches")

    foto = _foto(tela, "X Burguer")

    assert foto.nome == "X Burguer"
    assert "PODRÃO" not in foto.selos
    assert foto.selos == ()


def test_o_combo_e_selo_ao_lado_do_nome(tela, cardapio, cardapio_montado):
    """COMBO aparece em 4 dos 113 produtos do cardápio real: é selo ao lado do
    nome, e não uma coluna inteira reservada para ele."""
    cardapio.criar_produto(
        "Combo Casal", Decimal("40.00"), cardapio_montado["lanches"].id, is_combo=True
    )
    tela.atualizar()
    _abrir(tela, "Lanches")

    assert _foto(tela, "Combo Casal").selos == ("COMBO",)


def test_produto_desativado_ganha_o_selo_no_lugar_da_coluna_de_status(
    tela, cardapio, cardapio_montado
):
    """A coluna "Status" saiu com a tabela. O ATIVO repetido em toda linha era
    ruído; o que precisa aparecer é a exceção."""
    x_tudo = next(p for p in cardapio.listar_produtos() if p.nome == "X Tudo")
    cardapio.desativar_produto(x_tudo.id)
    tela.atualizar()
    _abrir(tela, "Lanches")

    foto = _foto(tela, "X Tudo")
    assert foto.ativo is False
    assert foto.selos == ("DESATIVADO",)
    assert _foto(tela, "X Burguer").selos == ()


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
    cabecalho = painel.lista.item(0)

    assert not cabecalho.flags() & Qt.ItemFlag.ItemIsSelectable
    painel.lista.setCurrentItem(cabecalho)

    # `produto_atual()` sozinho responderia `None` de qualquer jeito (a linha
    # não tem produto), então ele não distingue nada. O que distingue é a linha
    # NÃO ficar marcada: com ela selecionada, a lista mostraria um cabeçalho
    # destacado e o rodapé diria "SELECIONE UM PRODUTO" ao lado dele.
    assert painel.lista.selectedItems() == [], "o cabeçalho de bloco ficou selecionado"
    assert painel.produto_atual() is None
    assert painel._botao_editar.isEnabled() is False


def test_selecionar_um_produto_com_a_lista_agrupada_devolve_o_produto_certo(tela):
    """Com cabeçalho de bloco no meio, o índice da linha deixou de ser o índice
    do produto — e `produto_atual()` continua tendo que acertar."""
    _abrir(tela, "Lanches")
    painel = tela._painel_produtos

    painel.lista.setCurrentRow(1)

    assert painel.produto_atual().nome == "X Missão Impossível"


# ---------------------------------------------------------------------------
# Memória
# ---------------------------------------------------------------------------


def test_trocar_de_categoria_nao_acumula_widgets(tela, assentar):
    """O RNF do Celeron, numa tela que fica aberta o turno inteiro. Era o teste
    das pílulas do §9.9; sem pílula e sem widget por linha, o que se conta é a
    lista inteira — e ela não pode crescer."""
    _abrir(tela, "Lanches")
    assentar()
    lista = tela._painel_produtos.lista
    antes = len(lista.findChildren(QWidget))

    for _ in range(10):
        _abrir(tela, "Lanches")
        _abrir(tela, "Bebidas")
    _abrir(tela, "Lanches")
    assentar()

    depois = len(lista.findChildren(QWidget))
    assert depois == antes, f"a lista foi de {antes} para {depois} widgets em 10 trocas"


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
    assert _linhas_visiveis(tela) == ["# PODRÃO", "X Burguer", "X Tudo"]


def test_selecao_cardapio_e_um_tipo_e_nao_dois_parametros_soltos():
    """Uma subcategoria sem a categoria dela não identifica nada: "Podrão" pode
    existir em duas categorias."""
    selecao = SelecaoCardapio(categoria=None)

    assert selecao.chave == _SUB_TODAS
    assert selecao.e_todas is True
    assert SelecaoCardapio(categoria=None, chave=_SUB_NENHUMA).e_todas is False
