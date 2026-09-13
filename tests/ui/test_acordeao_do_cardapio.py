"""O acordeão da árvore do Cardápio: clicar na categoria aberta a recolhe. §9.17.

Até aqui o clique só sabia abrir. Na categoria já aberta ele reescolhia o
"Todas" e as subdivisões ficavam na tela para sempre — o gesto inverso não
existia. O que esta suíte cobra:

1. **o gesto** — o clique alterna, e vale na linha inteira: na seta, no nome e
   no contador, com mouse de verdade (`QTest`), e não chamando o slot;
2. **o que a tela mostra** — recolhida, as subdivisões saem da tela e a seta
   perde o âmbar; a seleção fica na linha da categoria, a direita na categoria
   inteira, e nada disso é desfeito por uma recarga;
3. **o gerente fica onde estava** — recolher não solta o produto escolhido nem
   joga a lista para o topo. O limite dessa regra também é cobrado: escolher
   uma subdivisão ou trocar de categoria continua soltando (§9.13);
4. **nada é criado a cada clique** — duzentos cliques com os mesmos widgets, os
   mesmos itens e nenhuma ida ao banco.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QWidget
from sqlalchemy import event

import gestor_comercial.ui.views.cardapio_view as modulo_da_tela
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.cores import cor_do_token
from gestor_comercial.ui.views.cardapio_view import _SUB_TODAS, CardapioView
from gestor_comercial.ui.widgets.cardapio_cartoes import TipoDeItem

LANCHES_INTEIRA = [
    "# ARTESANAL",
    "X Missão Impossível",
    "# PODRÃO",
    "X Burguer",
    "X Tudo",
    "# SEM SUBCATEGORIA",
    "X Egg",
]


@pytest.fixture
def cardapio_montado(cardapio, gerente):
    """Lanches com duas subdivisões e um item solto; Bebidas sem nenhuma.

    Em ordem alfabética Bebidas vem primeiro, e é ela que a tela abre no boot:
    Lanches começa FECHADA, o que deixa o primeiro clique de cada teste ser o
    de abrir.
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
    view.resize(1366, 738)
    view.show()
    qapp.processEvents()
    yield view
    view.close()
    view.deleteLater()


class _Contador:
    """Conta os comandos SQL que chegam ao banco enquanto está ligado."""

    def __init__(self, engine) -> None:
        self._engine = engine
        self.total = 0

    def _contar(self, *_argumentos, **_nomeados) -> None:
        self.total += 1

    def __enter__(self) -> _Contador:
        event.listen(self._engine, "after_cursor_execute", self._contar)
        return self

    def __exit__(self, *_erro) -> None:
        event.remove(self._engine, "after_cursor_execute", self._contar)


# ---------------------------------------------------------------------------
# Leitura e gestos
# ---------------------------------------------------------------------------


def _arvore(tela: CardapioView):
    return tela._painel_categorias.arvore


def _item_categoria(tela: CardapioView, nome: str):
    painel = tela._painel_categorias
    for indice in range(painel.arvore.topLevelItemCount()):
        item = painel.arvore.topLevelItem(indice)
        if painel._nome_da_categoria(item) == nome:
            return item
    raise AssertionError(f"categoria '{nome}' não está na árvore")


def _categorias(tela: CardapioView) -> list:
    arvore = _arvore(tela)
    return [arvore.topLevelItem(indice) for indice in range(arvore.topLevelItemCount())]


def _filho(item, rotulo: str):
    for posicao in range(item.childCount()):
        filho = item.child(posicao)
        if filho.data(0, modulo_da_tela._PAPEL_ROTULO) == rotulo:
            return filho
    raise AssertionError(f"'{rotulo}' não está sob a categoria")


def _ponto(tela: CardapioView, item, onde: str) -> QPoint:
    """Onde o dedo cai na linha da categoria.

    As coordenadas saem da geometria do próprio delegado (`DelegadoArvore`):
    a seta mora a 12px da borda do conteúdo, que começa 2px dentro da linha, e
    tem 14px de lado; o contador é o círculo de 24px encostado à direita.
    """
    arvore = _arvore(tela)
    retangulo = arvore.visualItemRect(item)
    meio_y = retangulo.center().y()
    if onde == "seta":
        return QPoint(retangulo.left() + 2 + 12 + 7, meio_y)
    if onde == "nome":
        return arvore.itemDelegate().area_do_nome(retangulo).center().toPoint()
    if onde == "contador":
        return QPoint(retangulo.right() - 2 - 12 - 12, meio_y)
    return retangulo.center()


def _clicar(qapp, tela: CardapioView, item, onde: str = "meio") -> None:
    arvore = _arvore(tela)
    QTest.mouseClick(
        arvore.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        _ponto(tela, item, onde),
    )
    qapp.processEvents()


def _linhas_visiveis(tela: CardapioView) -> list[str]:
    lista = tela._painel_produtos.lista
    saida = []
    for linha in range(lista.count()):
        dado = lista.item_da_linha(linha)
        if dado.tipo is TipoDeItem.CABECALHO:
            saida.append(f"# {dado.grupo.rotulo.upper()}")
        elif dado.tipo is TipoDeItem.PRODUTO:
            saida.append(dado.produto.nome)
    return saida


def _selecionar_produto(tela: CardapioView, nome: str) -> None:
    lista = tela._painel_produtos.lista
    for linha in range(lista.count()):
        dado = lista.item_da_linha(linha)
        if dado.produto is not None and dado.produto.nome == nome:
            lista.setCurrentItem(lista.item(linha))
            return
    raise AssertionError(f"'{nome}' não está na lista")


def _cabecalho(tela: CardapioView, rotulo: str):
    lista = tela._painel_produtos.lista
    for linha in range(lista.count()):
        dado = lista.item_da_linha(linha)
        if dado.tipo is TipoDeItem.CABECALHO and dado.grupo.rotulo == rotulo:
            return lista.item(linha)
    raise AssertionError(f"bloco '{rotulo}' não está na lista")


def _rotulo_do_rodape(tela: CardapioView) -> str:
    return tela._painel_produtos._label_dica.texto_completo()


# ---------------------------------------------------------------------------
# 1. O gesto
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("onde", ["seta", "nome", "contador"])
def test_o_clique_alterna_a_categoria_em_qualquer_ponto_da_linha(qapp, tela, onde):
    """A seta é pintura da linha, e não um botão à parte: no balcão o dedo cai
    onde cai, e a linha inteira tem que responder igual."""
    lanches = _item_categoria(tela, "Lanches")
    assert lanches.isExpanded() is False, "premissa: Lanches começa fechada"

    _clicar(qapp, tela, lanches, onde)
    assert lanches.isExpanded() is True

    _clicar(qapp, tela, lanches, onde)
    assert lanches.isExpanded() is False
    assert not any(item.isExpanded() for item in _categorias(tela)), (
        "recolher uma categoria abriu outra"
    )

    _clicar(qapp, tela, lanches, onde)
    assert lanches.isExpanded() is True


def test_abrir_outra_continua_fechando_a_anterior(qapp, tela):
    """O acordeão ganhou o fechar sem perder a regra de uma aberta por vez."""
    _clicar(qapp, tela, _item_categoria(tela, "Lanches"))

    _clicar(qapp, tela, _item_categoria(tela, "Bebidas"))

    assert _item_categoria(tela, "Lanches").isExpanded() is False
    assert _item_categoria(tela, "Bebidas").isExpanded() is True


# ---------------------------------------------------------------------------
# 2. O que a tela mostra
# ---------------------------------------------------------------------------


def _tem_a_cor(qapp, tela: CardapioView, regiao: QRect, cor) -> bool:
    qapp.processEvents()
    imagem = _arvore(tela).viewport().grab(regiao).toImage()
    return any(
        imagem.pixelColor(x, y).rgb() == cor.rgb()
        for x in range(imagem.width())
        for y in range(imagem.height())
    )


def test_recolhida_as_subdivisoes_saem_da_tela_e_a_seta_apaga(qapp, tela):
    """A seta âmbar para baixo é a categoria aberta; a apagada para o lado é a
    fechada. A guia vertical é pintada dentro das linhas das filhas — sair da
    tela junto com elas é o que a apaga."""
    lanches = _item_categoria(tela, "Lanches")
    acento = cor_do_token(ThemeController.instancia().tokens_atuais["acento"])

    def seta() -> QRect:
        retangulo = _arvore(tela).visualItemRect(lanches)
        return QRect(retangulo.left() + 14, retangulo.center().y() - 8, 16, 16)

    _clicar(qapp, tela, lanches)
    filhas = [lanches.child(posicao) for posicao in range(lanches.childCount())]
    assert all(not _arvore(tela).visualItemRect(filha).isEmpty() for filha in filhas)
    assert _tem_a_cor(qapp, tela, seta(), acento), "premissa: a seta aberta é âmbar"

    _clicar(qapp, tela, lanches)

    assert all(_arvore(tela).visualItemRect(filha).isEmpty() for filha in filhas), (
        "uma subdivisão continuou desenhada com a categoria recolhida"
    )
    assert not _tem_a_cor(qapp, tela, seta(), acento), "a seta continuou acesa"


def test_recolher_deixa_a_selecao_na_linha_da_categoria_e_a_direita_inteira(qapp, tela):
    """Recolher é voltar ao "Todas" da categoria. A seleção vai para a linha
    dela — o "atual" do Qt não pode ficar num filho que saiu da tela, senão a
    seta do teclado parte de um lugar invisível."""
    lanches = _item_categoria(tela, "Lanches")
    _clicar(qapp, tela, lanches)
    _clicar(qapp, tela, _filho(lanches, "Podrão"))
    assert _linhas_visiveis(tela) == ["# PODRÃO", "X Burguer", "X Tudo"], "premissa"

    _clicar(qapp, tela, lanches)

    selecao = tela._painel_categorias.selecao_atual()
    assert _arvore(tela).currentItem() is lanches
    assert selecao.categoria.nome == "Lanches" and selecao.chave == _SUB_TODAS
    assert _linhas_visiveis(tela) == LANCHES_INTEIRA
    assert _rotulo_do_rodape(tela) == "CATEGORIA: LANCHES"


def test_recolher_pelo_caminho_de_codigo_tambem_tira_a_selecao_do_filho(tela):
    """Pelo mouse, o pressionar já pôs a seleção na linha antes do clique. Pelo
    código (atalho, teste, outra tela), o "atual" estava no "Todas" — e o Qt
    o deixa lá quando o pai fecha."""
    painel = tela._painel_categorias
    lanches = _item_categoria(tela, "Lanches")
    painel._ao_clicar(lanches, 0)
    assert _arvore(tela).currentItem() is lanches.child(0), "premissa"

    painel._ao_clicar(lanches, 0)

    assert _arvore(tela).currentItem() is lanches


def test_a_recarga_nao_reabre_a_categoria_recolhida(qapp, tela):
    """`atualizar()` roda a cada navegação até a tela e depois de todo
    cadastro. Antes ele tratava "categoria selecionada" como "categoria
    aberta", e a recolhida voltaria aberta na primeira volta ao Cardápio."""
    lanches = _item_categoria(tela, "Lanches")
    _clicar(qapp, tela, lanches)
    _clicar(qapp, tela, lanches)

    tela.atualizar()

    lanches = _item_categoria(tela, "Lanches")  # a recarga refaz os itens
    selecao = tela._painel_categorias.selecao_atual()
    assert not any(item.isExpanded() for item in _categorias(tela))
    assert _arvore(tela).currentItem() is lanches
    assert selecao.categoria.nome == "Lanches" and selecao.chave == _SUB_TODAS

    _clicar(qapp, tela, lanches)
    assert lanches.isExpanded() is True, "depois da recarga o clique não reabriu"


def test_a_recarga_nao_troca_uma_subdivisao_escolhida_por_todas(qapp, tela):
    """A regra da recolhida vale só em "Todas", e este é o caminho que a exige.

    A seta → do teclado abre a categoria pelo próprio Qt, por fora do
    acordeão: `_expandida_id` continua dizendo "recolhida". Descer até
    "Podrão" e recarregar não pode fechar a categoria e devolver o gerente ao
    "Todas" em silêncio — a recarga nunca escolhe por ele."""
    arvore = _arvore(tela)
    lanches = _item_categoria(tela, "Lanches")
    _clicar(qapp, tela, lanches)
    _clicar(qapp, tela, lanches)
    arvore.setFocus()

    QTest.keyClick(arvore, Qt.Key.Key_Right)
    for _ in range(3):  # Todas → Artesanal → Podrão
        QTest.keyClick(arvore, Qt.Key.Key_Down)
    assert tela._painel_categorias.selecao_atual().chave == "Podrão", "premissa"

    tela.atualizar()

    assert tela._painel_categorias.selecao_atual().chave == "Podrão"
    assert _item_categoria(tela, "Lanches").isExpanded() is True


def test_a_direita_continua_certa_abrindo_fechando_e_reabrindo(qapp, tela):
    """O pedido de não-regressão, com e sem subcategoria: cada clique na
    sequência confere a lista, o topo do painel e a seleção."""
    roteiro = [
        ("Lanches", LANCHES_INTEIRA),  # abre
        ("Lanches", LANCHES_INTEIRA),  # recolhe
        ("Lanches", LANCHES_INTEIRA),  # reabre
        ("Bebidas", ["Coca Lata"]),  # abre outra, sem subdivisão
        ("Bebidas", ["Coca Lata"]),  # recolhe
        ("Bebidas", ["Coca Lata"]),  # reabre
        ("Lanches", LANCHES_INTEIRA),
    ]
    for passo, (nome, esperado) in enumerate(roteiro):
        _clicar(qapp, tela, _item_categoria(tela, nome))

        selecao = tela._painel_categorias.selecao_atual()
        assert _linhas_visiveis(tela) == esperado, f"passo {passo}: {nome}"
        assert (selecao.categoria.nome, selecao.chave) == (nome, _SUB_TODAS), f"passo {passo}"
        assert tela._painel_produtos._titulo.texto_completo() == nome, f"passo {passo}"


# ---------------------------------------------------------------------------
# 3. O gerente fica onde estava
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vindo_de", ["Todas as subcategorias", "Podrão"])
def test_recolher_mantem_o_produto_escolhido(qapp, tela, vindo_de):
    """O clique de navegação não desmarca o alvo do rodapé. Vindo de "Podrão"
    a lista muda (vira a categoria inteira), e o produto continua nela."""
    lanches = _item_categoria(tela, "Lanches")
    _clicar(qapp, tela, lanches)
    _clicar(qapp, tela, _filho(lanches, vindo_de))
    _selecionar_produto(tela, "X Tudo")

    _clicar(qapp, tela, lanches)

    assert lanches.isExpanded() is False
    assert tela._painel_produtos.produto_atual().nome == "X Tudo"
    assert _rotulo_do_rodape(tela) == "PRODUTO: X TUDO"


def test_escolher_a_subdivisao_do_produto_continua_soltando_ele(qapp, tela):
    """O limite da regra de cima: estreitar é escolher um alvo, e o §9.13 manda
    o rodapé agir sobre a subdivisão. "Podrão" contém "X Tudo" de propósito —
    sem o produto dentro, o teste passaria mesmo se a regra valesse aqui."""
    lanches = _item_categoria(tela, "Lanches")
    _clicar(qapp, tela, lanches)
    _selecionar_produto(tela, "X Tudo")

    _clicar(qapp, tela, _filho(lanches, "Podrão"))

    assert tela._painel_produtos.produto_atual() is None
    assert _rotulo_do_rodape(tela) == "SUBCATEGORIA: PODRÃO"


@pytest.fixture
def artesanal_comprida(cardapio, cardapio_montado):
    """Vinte e cinco lanches em "Artesanal", que vem antes de "Podrão": a
    categoria inteira passa a ter rolagem, e o bloco "Podrão" fica longe do
    topo."""
    for indice in range(25):
        cardapio.criar_produto(
            f"Artesanal {indice:02d}",
            Decimal("20.00"),
            cardapio_montado["lanches"].id,
            subcategoria_id=cardapio_montado["artesanal"].id,
        )


def _a_vista(lista, item) -> bool:
    retangulo = lista.visualItemRect(item)
    return not retangulo.isEmpty() and lista.viewport().rect().contains(retangulo.topLeft())


def test_recolher_sem_produto_deixa_a_vista_o_bloco_de_onde_o_gerente_veio(
    qapp, cardapio, artesanal_comprida
):
    """Sem produto escolhido, voltar ao topo da categoria mostraria 25 lanches
    artesanais no lugar do "Podrão" que o gerente estava olhando."""
    tela = CardapioView(cardapio)
    tela.resize(1366, 738)
    tela.show()
    qapp.processEvents()
    try:
        lanches = _item_categoria(tela, "Lanches")
        _clicar(qapp, tela, lanches)
        _clicar(qapp, tela, _filho(lanches, "Podrão"))
        assert tela._painel_produtos.produto_atual() is None, "premissa"

        _clicar(qapp, tela, lanches)

        lista = tela._painel_produtos.lista
        assert lista.verticalScrollBar().value() > 0, "a lista foi jogada para o topo"
        assert _a_vista(lista, _cabecalho(tela, "Podrão"))
    finally:
        tela.close()
        tela.deleteLater()


def test_recolher_em_todas_nao_mexe_na_lista_nem_vai_ao_banco(
    qapp, cardapio, artesanal_comprida, uow
):
    """Já em "Todas", recolher não troca de lugar: a lista não é refeita, a
    rolagem fica onde o gerente a deixou e o banco não é consultado."""
    tela = CardapioView(cardapio)
    tela.resize(1366, 738)
    tela.show()
    qapp.processEvents()
    try:
        lanches = _item_categoria(tela, "Lanches")
        _clicar(qapp, tela, lanches)
        barra = tela._painel_produtos.lista.verticalScrollBar()
        barra.setValue(barra.maximum() // 2)
        rolagem = barra.value()
        assert rolagem > 0, "premissa: a lista precisa ter rolagem"

        with _Contador(uow.session.get_bind()) as contador:
            _clicar(qapp, tela, lanches)

        assert lanches.isExpanded() is False
        assert barra.value() == rolagem
        assert contador.total == 0, f"recolher foi {contador.total} vez(es) ao banco"
    finally:
        tela.close()
        tela.deleteLater()


def test_trocar_de_categoria_comeca_do_topo_mesmo_com_subdivisao_de_mesmo_nome(
    qapp, cardapio, cardapio_montado, artesanal_comprida
):
    """"Podrão" pode existir em duas categorias. A âncora da rolagem vale
    dentro da MESMA categoria: vindo de Lanches → Podrão, abrir Porções não
    pode rolar até o "Podrão" de Porções."""
    porcoes = cardapio.criar_categoria("Porções")
    tradicional = cardapio.criar_subcategoria(porcoes.id, "Artesanal")
    podrao = cardapio.criar_subcategoria(porcoes.id, "Podrão")
    for indice in range(25):
        cardapio.criar_produto(
            f"Porção {indice:02d}", Decimal("30.00"), porcoes.id, subcategoria_id=tradicional.id
        )
    cardapio.criar_produto("Batata Podrão", Decimal("25.00"), porcoes.id, subcategoria_id=podrao.id)
    tela = CardapioView(cardapio)
    tela.resize(1366, 738)
    tela.show()
    qapp.processEvents()
    try:
        lanches = _item_categoria(tela, "Lanches")
        _clicar(qapp, tela, lanches)
        _clicar(qapp, tela, _filho(lanches, "Podrão"))

        _clicar(qapp, tela, _item_categoria(tela, "Porções"))

        assert tela._painel_produtos.lista.verticalScrollBar().value() == 0
    finally:
        tela.close()
        tela.deleteLater()


# ---------------------------------------------------------------------------
# Os caminhos que abrem a categoria por conta própria
# ---------------------------------------------------------------------------


class _ModalQueDevolve(QDialog):
    """Faz as vezes do cartão de organização (§9.12): aceita UMA vez com `nome`.

    A view reabre o mesmo diálogo num `while` enquanto o service recusar, e um
    dublê que sempre aceita giraria para sempre.
    """

    nome = ""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._respondido = False

    @classmethod
    def para_categoria(cls, _existentes, parent=None, *, nome_inicial=""):
        return cls(parent)

    @classmethod
    def para_subcategoria(cls, _categoria, _impressora, _existentes, parent=None, *, nome_inicial=""):
        return cls(parent)

    def exec(self) -> int:
        if self._respondido:
            return QDialog.DialogCode.Rejected
        self._respondido = True
        return QDialog.DialogCode.Accepted

    def resultado(self):
        return SimpleNamespace(nome=_ModalQueDevolve.nome)

    def mostrar_erro_servico(self, mensagem: str) -> None:
        raise AssertionError(mensagem)


@pytest.fixture
def modal(monkeypatch):
    monkeypatch.setattr(modulo_da_tela, "OrganizacaoCardapioDialog", _ModalQueDevolve)
    return _ModalQueDevolve


def test_criar_categoria_com_tudo_recolhido_ja_abre_a_nova(qapp, tela, modal):
    """A recarga respeita a recolhida — e a categoria nova não é a recolhida:
    quem acabou de criá-la vai cadastrar as subdivisões em seguida."""
    lanches = _item_categoria(tela, "Lanches")
    _clicar(qapp, tela, lanches)
    _clicar(qapp, tela, lanches)
    modal.nome = "Doces"

    tela._painel_categorias.criar()

    assert tela._painel_categorias.selecao_atual().categoria.nome == "Doces"
    assert _item_categoria(tela, "Doces").isExpanded() is True


def test_criar_subcategoria_com_a_categoria_recolhida_abre_ela(qapp, tela, modal):
    """Subdivisão vazia não vira bloco em "Todas": recolhida, a categoria não
    mostraria em lugar nenhum a subdivisão que acabou de ser criada."""
    lanches = _item_categoria(tela, "Lanches")
    _clicar(qapp, tela, lanches)
    _clicar(qapp, tela, lanches)
    modal.nome = "Combo pastel"

    tela._painel_categorias.criar_subcategoria()

    lanches = _item_categoria(tela, "Lanches")
    assert lanches.isExpanded() is True
    _filho(lanches, "Combo pastel")


def test_escolher_um_bloco_a_direita_com_a_categoria_recolhida_reabre_pelo_acordeao(qapp, tela):
    """O cabeçalho do bloco continua clicável com a categoria recolhida, e a
    árvore abre para mostrar a pílula. Pelo acordeão, e não pelo Qt: a busca
    da árvore, digitada e apagada, não pode fechar o ramo debaixo da
    subdivisão escolhida."""
    lanches = _item_categoria(tela, "Lanches")
    _clicar(qapp, tela, lanches)
    _clicar(qapp, tela, lanches)
    lista = tela._painel_produtos.lista
    retangulo = lista.visualItemRect(_cabecalho(tela, "Podrão"))

    QTest.mouseClick(
        lista.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(retangulo.left() + 70, retangulo.center().y()),
    )
    busca = tela._painel_categorias._campo_busca
    busca.setText("beb")
    busca.setText("")

    assert lanches.isExpanded() is True
    assert _arvore(tela).currentItem() is _filho(lanches, "Podrão")


# ---------------------------------------------------------------------------
# 4. Nada é criado a cada clique
# ---------------------------------------------------------------------------


def _itens_da_arvore(tela: CardapioView) -> int:
    return sum(1 + item.childCount() for item in _categorias(tela))


def _contagem(tela: CardapioView) -> tuple[int, int, int]:
    """Widgets e `QObject`s da tela INTEIRA, e itens da árvore.

    A tela inteira, e não só a árvore: recolher vindo de uma subdivisão refaz
    a lista da direita, e é lá que um objeto esquecido apareceria.
    """
    return (
        len(tela.findChildren(QWidget)),
        len(tela.findChildren(QObject)),
        _itens_da_arvore(tela),
    )


def test_abrir_e_fechar_duzentas_vezes_nao_cria_objeto_nem_vai_ao_banco(
    qapp, tela, assentar, uow
):
    """O RNF do Celeron, no gesto mais repetido da tela. As subdivisões nascem
    na montagem da árvore e o clique só muda o que o Qt desenha: nenhum widget,
    nenhum item, nenhum `QObject` a mais — e nenhuma consulta, porque abrir e
    recolher em "Todas" é sempre o mesmo lugar."""
    lanches = _item_categoria(tela, "Lanches")
    _clicar(qapp, tela, lanches)
    assentar()
    antes = _contagem(tela)

    with _Contador(uow.session.get_bind()) as contador:
        for _ in range(100):
            _clicar(qapp, tela, lanches)
            _clicar(qapp, tela, lanches)
    assentar()

    assert lanches.isExpanded() is True, "cliques em número par devolvem a categoria aberta"
    assert _contagem(tela) == antes
    assert _arvore(tela).viewport().findChildren(QWidget) == []
    assert contador.total == 0, f"abrir e fechar foi {contador.total} vez(es) ao banco"


def test_recolher_vindo_da_subdivisao_cem_vezes_nao_acumula_nada(qapp, tela, assentar):
    """O ciclo que troca de lugar: escolher "Podrão", recolher (a direita é
    refeita com a categoria inteira) e reabrir. É o caminho em que o gesto
    passa pela recarga da lista."""
    lanches = _item_categoria(tela, "Lanches")
    _clicar(qapp, tela, lanches)
    assentar()
    antes = _contagem(tela)

    for _ in range(100):
        _clicar(qapp, tela, _filho(lanches, "Podrão"))
        _clicar(qapp, tela, lanches)
        _clicar(qapp, tela, lanches)
    assentar()

    assert _linhas_visiveis(tela) == LANCHES_INTEIRA
    assert _contagem(tela) == antes
