"""O Cardápio em cartões pintados — as garantias do §9.11.

A estrutura (árvore, blocos por subcategoria) é coberta em
`test_cardapio_hierarquia.py`. Este arquivo cobra o que o pedido do §9.11 exigiu
por escrito, uma trava por item:

1. **nenhum widget por linha** — as duas listas são pintadas; não há o que
   sobrar, sobrepor ou esquecer de desconectar;
2. **pintar não toca o banco** — a lista pinta um instantâneo, e rolar ou
   passar o mouse não pode virar consulta depois de um commit;
3. **o gerente fica onde estava** — salvar um produto não solta a seleção, não
   fecha o acordeão e não rola a lista para o topo; renomear a subcategoria
   escolhida não o leva para a primeira categoria;
4. **os gestos do mockup** — duplo clique edita, o link do bloco edita a
   subcategoria DAQUELE bloco;
5. **os números do topo** vêm do service, e **as cores** seguem o tema;
6. **a recarga não cresce com o cardápio** — o N+1 da árvore acabou.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QWidget
from sqlalchemy import event

import gestor_comercial.ui.views.cardapio_view as modulo_da_tela
from gestor_comercial.ui.theme import tokens
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.cores import cor_do_token
from gestor_comercial.ui.views.cardapio_view import _SUB_TODAS, CardapioView, DadosProduto
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    DelegadoProdutos,
    FotoGrupo,
    FotoProduto,
    TipoDeItem,
    montar_itens,
)


@pytest.fixture
def lanches(cardapio, gerente):
    """Lanches com Podrão (2) e Artesanal (1), e Bebidas sem subdivisão."""
    categoria = cardapio.criar_categoria("Lanches")
    bebidas = cardapio.criar_categoria("Bebidas")
    podrao = cardapio.criar_subcategoria(categoria.id, "Podrão")
    artesanal = cardapio.criar_subcategoria(categoria.id, "Artesanal")
    cardapio.criar_produto("X Burguer", Decimal("13.00"), categoria.id, subcategoria_id=podrao.id)
    cardapio.criar_produto("X Tudo", Decimal("16.00"), categoria.id, subcategoria_id=podrao.id)
    cardapio.criar_produto(
        "X Missão Impossível", Decimal("28.00"), categoria.id, subcategoria_id=artesanal.id
    )
    cardapio.criar_produto("Coca Lata", Decimal("8.00"), bebidas.id)
    return {"lanches": categoria, "bebidas": bebidas, "podrao": podrao, "artesanal": artesanal}


@pytest.fixture
def tela(qapp, cardapio, lanches):
    view = CardapioView(cardapio)
    view.resize(1366, 738)
    yield view
    view.close()
    view.deleteLater()


@pytest.fixture
def tema(qapp):
    """QSS global aplicado, e o tema escuro de volta no fim (singleton)."""
    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    try:
        yield controlador
    finally:
        controlador.alternar_para(False)


def _item_categoria(tela: CardapioView, nome: str):
    painel = tela._painel_categorias
    for indice in range(painel.arvore.topLevelItemCount()):
        item = painel.arvore.topLevelItem(indice)
        if painel._nome_da_categoria(item) == nome:
            return item
    raise AssertionError(f"categoria '{nome}' não está na árvore")


def _abrir(tela: CardapioView, nome: str):
    item = _item_categoria(tela, nome)
    arvore = tela._painel_categorias.arvore
    arvore.setCurrentItem(item)
    tela._painel_categorias._ao_clicar(item, 0)
    arvore.setCurrentItem(item.child(0))
    return item


def _linha_do_produto(tela: CardapioView, nome: str) -> int:
    lista = tela._painel_produtos.lista
    for linha in range(lista.count()):
        dado = lista.item_da_linha(linha)
        if dado.produto is not None and dado.produto.nome == nome:
            return linha
    raise AssertionError(f"'{nome}' não está na lista")


def _linha_do_cabecalho(tela: CardapioView, rotulo: str) -> int:
    lista = tela._painel_produtos.lista
    for linha in range(lista.count()):
        dado = lista.item_da_linha(linha)
        if dado.tipo is TipoDeItem.CABECALHO and dado.grupo.rotulo == rotulo:
            return linha
    raise AssertionError(f"bloco '{rotulo}' não está na lista")


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
# 1. Nenhum widget por linha
# ---------------------------------------------------------------------------


def test_nenhuma_linha_das_duas_listas_e_widget(qapp, tela):
    """A garantia de construção: com linha pintada, "widget fantasma" deixa de
    ser uma classe de defeito possível nesta tela."""
    tela.show()
    _abrir(tela, "Lanches")
    qapp.processEvents()
    arvore = tela._painel_categorias.arvore
    lista = tela._painel_produtos.lista

    assert lista.count() > 0 and arvore.topLevelItemCount() > 0, "a premissa precisa de linhas"
    assert lista.viewport().findChildren(QWidget) == []
    assert arvore.viewport().findChildren(QWidget) == []
    for indice in range(arvore.topLevelItemCount()):
        item = arvore.topLevelItem(indice)
        assert arvore.itemWidget(item, 0) is None
        for filho in range(item.childCount()):
            assert arvore.itemWidget(item.child(filho), 0) is None


def test_trocar_de_categoria_sessenta_vezes_nao_cresce_a_tela(qapp, tela, assentar):
    """Quatro voltas pelas categorias, como o turno faz: a tela inteira (não só
    as listas) termina com os mesmos widgets com que começou."""
    tela.show()
    _abrir(tela, "Lanches")
    assentar()
    antes = len(tela.findChildren(QWidget))

    for _ in range(30):
        _abrir(tela, "Bebidas")
        _abrir(tela, "Lanches")
    assentar()

    assert len(tela.findChildren(QWidget)) == antes


# ---------------------------------------------------------------------------
# 2. Pintar não toca o banco
# ---------------------------------------------------------------------------


def test_premissa_ler_o_produto_depois_do_commit_vai_ao_banco(cardapio, lanches, uow):
    """Por que o instantâneo existe: o commit expira as instâncias, e ler um
    atributo depois dele é uma consulta. Se isto um dia deixar de ser verdade,
    o teste de baixo continua certo, mas deixa de ser necessário."""
    produto = cardapio.listar_produtos()[0]
    cardapio.criar_produto("Qualquer", Decimal("1.00"), lanches["bebidas"].id)  # commit

    with _Contador(uow.session.get_bind()) as contador:
        _ = produto.nome

    assert contador.total > 0


def test_pintar_as_listas_nao_toca_no_banco(qapp, tela, cardapio, lanches, uow):
    """Rolar e passar o mouse repintam a lista o tempo todo. Com o `Produto`
    na pintura, cada repintura depois de um produto salvo seria uma rajada de
    consultas; com o instantâneo, é zero."""
    tela.show()
    _abrir(tela, "Lanches")
    qapp.processEvents()
    cardapio.criar_produto("Outro", Decimal("2.00"), lanches["bebidas"].id)  # expira tudo

    with _Contador(uow.session.get_bind()) as contador:
        tela._painel_produtos.lista.viewport().grab()
        tela._painel_categorias.arvore.viewport().grab()

    assert contador.total == 0, f"a pintura foi {contador.total} vez(es) ao banco"


# ---------------------------------------------------------------------------
# 3. O gerente fica onde estava
# ---------------------------------------------------------------------------


def test_a_selecao_volta_pelo_id_e_nao_pelo_numero_da_linha(tela, cardapio, lanches):
    """Um produto novo cadastrado ANTES do escolhido desloca as linhas. Voltar
    pelo número da linha deixaria o vizinho selecionado — e o próximo "Editar"
    abriria o produto errado."""
    item = _abrir(tela, "Lanches")
    tela._painel_categorias.arvore.setCurrentItem(item.child(2))  # Podrão
    painel = tela._painel_produtos
    painel.lista.setCurrentRow(_linha_do_produto(tela, "X Tudo"))
    cardapio.criar_produto(
        "X Abacate", Decimal("12.00"), lanches["lanches"].id, subcategoria_id=lanches["podrao"].id
    )

    tela.atualizar()

    assert painel.produto_atual().nome == "X Tudo"


def test_salvar_um_produto_nao_fecha_o_acordeao_nem_rola_para_o_topo(
    qapp, tela, cardapio, lanches, monkeypatch
):
    """O pedido de preservação de estado, pelo caminho real do "Editar": o
    modal devolve o formulário, o service grava, e a tela se recarrega — a
    seleção, a categoria aberta e as DUAS rolagens têm que continuar onde
    estavam."""
    for indice in range(30):
        cardapio.criar_produto(f"Suco {indice:02d}", Decimal("9.00"), lanches["bebidas"].id)
    for indice in range(12):
        cardapio.criar_categoria(f"Categoria {indice:02d}")
    tela.atualizar()
    tela.show()
    _abrir(tela, "Bebidas")
    qapp.processEvents()

    painel = tela._painel_produtos
    painel.lista.setCurrentRow(painel.lista.count() - 1)
    barra = painel.lista.verticalScrollBar()
    barra.setValue(barra.maximum())
    barra_da_arvore = tela._painel_categorias.arvore.verticalScrollBar()
    barra_da_arvore.setValue(barra_da_arvore.maximum())
    rolagem_da_lista, rolagem_da_arvore = barra.value(), barra_da_arvore.value()
    escolhido = painel.produto_atual()
    assert rolagem_da_lista > 0 and rolagem_da_arvore > 0, "a premissa precisa de rolagem"

    class _ModalQueSalva(QDialog):
        def __init__(self, _titulo, _categorias, parent=None, **iniciais) -> None:
            super().__init__(parent)
            self._iniciais = iniciais
            self._aberturas = 0

        def exec(self) -> int:
            self._aberturas += 1
            aceito = self._aberturas == 1
            return QDialog.DialogCode.Accepted if aceito else QDialog.DialogCode.Rejected

        def resultado(self) -> DadosProduto:
            return DadosProduto(
                nome=self._iniciais["nome_inicial"],
                preco=Decimal("10.50"),
                custo=Decimal("3.00"),
                categoria_id=self._iniciais["categoria_id_inicial"],
                descricao=None,
                imagem_path=None,
                subcategoria=None,
            )

        def confirmar_remocao_de_imagem_trocada(self) -> None:
            pass

        def mostrar_erro_servico(self, mensagem: str) -> None:
            raise AssertionError(mensagem)

    monkeypatch.setattr(modulo_da_tela, "_ProdutoDialog", _ModalQueSalva)
    painel.editar()
    qapp.processEvents()

    selecao = tela._painel_categorias.selecao_atual()
    assert painel.produto_atual().id == escolhido.id
    assert painel.produto_atual().preco == Decimal("10.50"), "o salvamento não aconteceu"
    assert selecao.categoria.nome == "Bebidas" and selecao.chave == _SUB_TODAS
    assert _item_categoria(tela, "Bebidas").isExpanded()
    assert barra.value() == rolagem_da_lista, "a lista voltou para o topo depois de salvar"
    assert barra_da_arvore.value() == rolagem_da_arvore, "a árvore voltou para o topo"


def test_a_rolagem_volta_mesmo_sem_produto_escolhido(qapp, tela, cardapio, lanches):
    """Com produto escolhido, o próprio Qt rola até ele e o defeito se esconde.
    Sem produto — o gerente só descendo a lista para conferir preços — a
    recarga (toda navegação até a tela chama uma) jogava a lista para cima: o
    alcance da barra que sobra do `clear()` é menor que o da lista cheia."""
    for indice in range(30):
        cardapio.criar_produto(f"Suco {indice:02d}", Decimal("9.00"), lanches["bebidas"].id)
    tela.atualizar()
    tela.show()
    _abrir(tela, "Bebidas")
    qapp.processEvents()
    painel = tela._painel_produtos
    painel.lista.clearSelection()
    barra = painel.lista.verticalScrollBar()
    barra.setValue(barra.maximum() * 3 // 4)
    rolagem = barra.value()
    assert painel.produto_atual() is None and rolagem > 0, "premissa"

    tela.atualizar()

    assert barra.value() == rolagem


class _ModalDeSubcategoria(QDialog):
    """Faz as vezes do cartão de subcategoria: devolve `nome` e fecha."""

    abertos: list[str] = []
    nome_a_devolver: str | None = None

    def __init__(self, _categoria, _impressora, _existentes, parent=None, *, nome_inicial="") -> None:
        super().__init__(parent)
        _ModalDeSubcategoria.abertos.append(nome_inicial)
        self._respondido = False

    def exec(self) -> int:
        if self._respondido or _ModalDeSubcategoria.nome_a_devolver is None:
            return QDialog.DialogCode.Rejected
        self._respondido = True
        return QDialog.DialogCode.Accepted

    def resultado(self):
        return type("Resultado", (), {"nome": _ModalDeSubcategoria.nome_a_devolver})()

    def mostrar_erro_servico(self, mensagem: str) -> None:
        raise AssertionError(mensagem)


@pytest.fixture
def modal_de_subcategoria(monkeypatch):
    _ModalDeSubcategoria.abertos = []
    _ModalDeSubcategoria.nome_a_devolver = None
    monkeypatch.setattr(modulo_da_tela, "SubcategoriaDialog", _ModalDeSubcategoria)
    return _ModalDeSubcategoria


def test_renomear_a_subcategoria_escolhida_mantem_a_selecao(tela, modal_de_subcategoria):
    """O defeito que o §9.11 achou no caminho: a recarga procurava a
    subdivisão pelo nome ANTIGO, não achava, e levava o gerente para a
    primeira categoria da lista — renomear fechava o acordeão em que ele
    trabalhava."""
    item = _abrir(tela, "Lanches")
    tela._painel_categorias.arvore.setCurrentItem(item.child(2))  # Podrão
    modal_de_subcategoria.nome_a_devolver = "Podrão Raiz"

    tela._painel_categorias.editar_subcategoria()

    selecao = tela._painel_categorias.selecao_atual()
    assert selecao.categoria.nome == "Lanches"
    assert selecao.chave == "Podrão Raiz"
    assert _item_categoria(tela, "Lanches").isExpanded()


def test_quando_a_subdivisao_escolhida_some_o_gerente_fica_na_categoria(tela, cardapio, lanches):
    """Classificar o último item solto faz "Sem subcategoria" sumir da árvore
    — e quem estava nela tem que continuar em Lanches ("Todas"), e não ser
    levado para Bebidas, a primeira categoria da lista."""
    solto = cardapio.criar_produto("X Egg", Decimal("15.00"), lanches["lanches"].id)
    tela.atualizar()
    item = _abrir(tela, "Lanches")
    tela._painel_categorias.arvore.setCurrentItem(item.child(item.childCount() - 1))
    assert tela._painel_categorias.selecao_atual().chave != _SUB_TODAS, "premissa"

    cardapio.atualizar_produto(
        solto.id, solto.nome, solto.preco, solto.custo, lanches["lanches"].id,
        subcategoria_id=lanches["podrao"].id,
    )
    tela.atualizar()

    selecao = tela._painel_categorias.selecao_atual()
    assert selecao.categoria.nome == "Lanches"
    assert selecao.chave == _SUB_TODAS


def test_duplo_clique_na_categoria_nao_a_fecha_de_novo(qapp, tela):
    """O clique simples já abre a categoria; o duplo clique do Qt alternava o
    ramo em seguida, e abrir com duplo clique a fechava de novo.

    A categoria clicada fica ACIMA da aberta de propósito: abrir uma de baixo
    fecha a de cima, as linhas sobem, e o duplo clique cai em outro item — o
    defeito só aparece quando a linha não sai do lugar entre os dois cliques."""
    _abrir(tela, "Lanches")
    tela.show()
    qapp.processEvents()
    arvore = tela._painel_categorias.arvore
    item = _item_categoria(tela, "Bebidas")

    _duplo_clique(arvore.viewport(), arvore.visualItemRect(item).center())

    assert item.isExpanded() is True


def test_criar_uma_categoria_ja_abre_ela(tela, monkeypatch):
    """Quem cria uma categoria vai cadastrar as subdivisões dela em seguida; a
    árvore antiga levava o gerente de volta para a primeira da lista."""

    class _ModalDeCategoria(QDialog):
        def exec(self) -> int:
            return QDialog.DialogCode.Accepted

        def nome(self) -> str:
            return "Doces"

    monkeypatch.setattr(
        modulo_da_tela, "_CategoriaDialog", lambda _titulo, parent=None, **_: _ModalDeCategoria(parent)
    )
    _abrir(tela, "Lanches")

    tela._painel_categorias.criar()

    assert tela._painel_categorias.selecao_atual().categoria.nome == "Doces"
    assert _item_categoria(tela, "Doces").isExpanded()


# ---------------------------------------------------------------------------
# 4. Os gestos do mockup
# ---------------------------------------------------------------------------


def test_o_link_editar_subcategoria_abre_a_subcategoria_daquele_bloco(
    qapp, tela, modal_de_subcategoria
):
    """Em "Todas" há vários blocos, e o link edita o bloco em que foi clicado —
    não a subdivisão destacada na árvore (que ali é "Todas")."""
    tela.show()
    _abrir(tela, "Lanches")
    qapp.processEvents()
    lista = tela._painel_produtos.lista
    cabecalho = lista.item(_linha_do_cabecalho(tela, "Podrão"))
    retangulo = lista.visualItemRect(cabecalho)
    link = lista.delegado().retangulo_do_link(retangulo, lista.font())

    QTest.mouseClick(lista.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, link.center())

    assert modal_de_subcategoria.abertos == ["Podrão"]


def test_clicar_no_cabecalho_fora_do_link_nao_edita_nada(qapp, tela, modal_de_subcategoria):
    tela.show()
    _abrir(tela, "Lanches")
    qapp.processEvents()
    lista = tela._painel_produtos.lista
    retangulo = lista.visualItemRect(lista.item(_linha_do_cabecalho(tela, "Podrão")))

    QTest.mouseClick(
        lista.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(retangulo.left() + 70, retangulo.center().y()),
    )

    assert modal_de_subcategoria.abertos == []


def _duplo_clique(alvo: QWidget, ponto: QPoint) -> None:
    """O duplo clique como o sistema operacional o entrega: clique e duplo clique.

    O `QTest.mouseDClick` do Qt 6 manda SÓ o `MouseButtonDblClick`, sem o
    pressionar/soltar que o Windows sempre manda antes — e a lista do Qt só
    anuncia duplo clique no item que recebeu o clique anterior. Com o
    `mouseDClick` sozinho o teste reprovava um código certo.
    """
    QTest.mouseClick(alvo, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, ponto)
    QTest.mouseDClick(alvo, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, ponto)


def test_duplo_clique_no_produto_abre_a_edicao_dele(qapp, tela, monkeypatch):
    abertos: list[str] = []

    class _ModalQueSoRegistra(QDialog):
        def __init__(self, _titulo, _categorias, parent=None, **iniciais) -> None:
            super().__init__(parent)
            abertos.append(iniciais.get("nome_inicial", ""))

        def exec(self) -> int:
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(modulo_da_tela, "_ProdutoDialog", _ModalQueSoRegistra)
    tela.show()
    _abrir(tela, "Lanches")
    qapp.processEvents()
    lista = tela._painel_produtos.lista
    produto = lista.item(_linha_do_produto(tela, "X Tudo"))
    cabecalho = lista.item(_linha_do_cabecalho(tela, "Artesanal"))

    _duplo_clique(lista.viewport(), lista.visualItemRect(produto).center())
    assert abertos == ["X Tudo"]

    # Com "X Tudo" ainda selecionado: o duplo clique num cabeçalho não pode
    # abrir o formulário do produto que ficou escolhido de antes.
    _duplo_clique(lista.viewport(), lista.visualItemRect(cabecalho).center())
    assert abertos == ["X Tudo"], "o duplo clique no cabeçalho abriu um formulário"

    # O Qt já não anuncia duplo clique em linha desabilitada, e o cabeçalho é
    # uma. A guarda da tela é a segunda camada — para o dia em que o cabeçalho
    # ganhar flag —, e é ela que se confere aqui, pelo sinal direto.
    lista.itemDoubleClicked.emit(cabecalho)
    assert abertos == ["X Tudo"], "a guarda do duplo clique deixou passar um cabeçalho"


def test_a_seta_do_teclado_pula_os_cabecalhos(qapp, tela):
    """Cabeçalho e espaço entram sem flag: a seta para baixo sai do último
    produto de um bloco direto para o primeiro do seguinte."""
    tela.show()
    _abrir(tela, "Lanches")
    qapp.processEvents()
    lista = tela._painel_produtos.lista
    lista.setFocus()
    lista.setCurrentRow(_linha_do_produto(tela, "X Missão Impossível"))

    QTest.keyClick(lista, Qt.Key.Key_Down)

    assert tela._painel_produtos.produto_atual().nome == "X Burguer"


# ---------------------------------------------------------------------------
# 5. Os números do topo e as cores
# ---------------------------------------------------------------------------


def _kpi(card) -> tuple[str, str]:
    return card._label_valor.text(), card._label_legenda.texto_completo()


def test_os_kpis_do_topo(tela, cardapio, lanches):
    """(13 + 16 + 28 + 8) / 4 = R$ 16,25 de preço médio; custo zero em tudo,
    margem de 100%. É o service quem faz a conta — a tela só escreve."""
    assert _kpi(tela._kpi_categorias) == ("2", "grupos ativos")
    assert _kpi(tela._kpi_subcategorias) == ("2", "divisões organizadas")
    assert _kpi(tela._kpi_produtos) == ("4", "itens cadastrados")
    assert _kpi(tela._kpi_preco_medio) == ("R$ 16,25", "100% de margem média")


def test_os_kpis_acompanham_o_cadastro(tela, cardapio, lanches):
    burguer = next(p for p in cardapio.listar_produtos() if p.nome == "X Burguer")
    cardapio.atualizar_produto(
        burguer.id,
        burguer.nome,
        burguer.preco,
        Decimal("6.50"),
        lanches["lanches"].id,
        subcategoria_id=lanches["podrao"].id,
    )
    cardapio.desativar_categoria(lanches["bebidas"].id)

    tela.atualizar()

    # Margens: 50% (X Burguer) e 100% nos outros três — média de 87,5, que o
    # rótulo arredonda como o resto da tela.
    assert _kpi(tela._kpi_preco_medio) == ("R$ 16,25", "88% de margem média")
    assert _kpi(tela._kpi_categorias) == ("2", "1 ativo · 1 desativado")


def test_as_cores_da_lista_acompanham_o_tema(qapp, tema, tela):
    """A cor da linha é lida do tema a CADA pintura — alternar Claro/Escuro
    repinta os blocos sem ninguém assinar o sinal do controlador (§3.14)."""
    tela.show()
    _abrir(tela, "Bebidas")
    qapp.processEvents()
    lista = tela._painel_produtos.lista
    retangulo = lista.visualItemRect(lista.item(_linha_do_produto(tela, "Coca Lata")))
    ponto = QPoint(retangulo.left() + 8, retangulo.center().y())

    escuro = lista.viewport().grab().toImage().pixelColor(ponto).name()
    tema.alternar_para(True)
    qapp.processEvents()
    claro = lista.viewport().grab().toImage().pixelColor(ponto).name()

    assert escuro == cor_do_token(tokens.TEMA_ESCURO["cardapio_bloco_bg"]).name()
    assert claro == cor_do_token(tokens.TEMA_CLARO["cardapio_bloco_bg"]).name()


def test_o_excluir_e_vermelho_ferrari_nos_dois_temas(tela):
    """O pedido nomeou a cor: `#DC2626`, a mesma da mesa ocupada — o vermelho
    que este app reserva para o que não volta."""
    assert tela._painel_produtos._botao_excluir.objectName() == "cardapioBotaoExcluir"
    assert tokens.TEMA_ESCURO["cardapio_excluir_bg"] == "#DC2626"
    assert tokens.TEMA_CLARO["cardapio_excluir_bg"] == "#DC2626"


def test_a_linha_de_erro_so_ocupa_espaco_quando_tem_erro(tela):
    """Num monitor de 768px, a linha de erro em branco custava a altura que as
    duas listas não tinham."""
    assert tela._label_erro.isVisibleTo(tela) is False

    tela._mostrar_erro("Selecione um produto antes de gerenciar o combo.")
    assert tela._label_erro.isVisibleTo(tela) is True

    tela._mostrar_erro("")
    assert tela._label_erro.isVisibleTo(tela) is False


# ---------------------------------------------------------------------------
# 6. A recarga não cresce com o cardápio
# ---------------------------------------------------------------------------


def test_recarregar_a_tela_nao_cresce_com_o_numero_de_categorias(qapp, cardapio, gerente, uow):
    """Eram 39 consultas por recarga no cardápio real: a árvore e os KPIs
    pediam as subcategorias uma categoria por vez (§3.6). Agora o número é
    fixo — o mesmo com 3 categorias e com 15."""

    def povoar(de: int, ate: int) -> None:
        for indice in range(de, ate):
            categoria = cardapio.criar_categoria(f"Categoria {indice:02d}")
            sub = cardapio.criar_subcategoria(categoria.id, "Sub")
            cardapio.criar_produto(
                f"Produto {indice:02d}", Decimal("5.00"), categoria.id, subcategoria_id=sub.id
            )

    povoar(0, 3)
    tela = CardapioView(cardapio)
    tela.atualizar()
    with _Contador(uow.session.get_bind()) as poucas:
        tela.atualizar()

    povoar(3, 15)
    tela.atualizar()
    with _Contador(uow.session.get_bind()) as muitas:
        tela.atualizar()
    tela.deleteLater()

    assert muitas.total == poucas.total, (
        f"{poucas.total} consultas com 3 categorias e {muitas.total} com 15"
    )


# ---------------------------------------------------------------------------
# A composição da lista e a geometria da linha, sem janela nenhuma
# ---------------------------------------------------------------------------


def _foto(nome: str, busca: str | None = None) -> FotoProduto:
    return FotoProduto(
        produto_id=hash(nome) & 0xFFFF,
        nome=nome,
        preco_texto="R$ 10,00",
        custo_texto="R$ 3,00",
        margem=70.0,
        ativo=True,
        selos=(),
        imagem_path=None,
        busca=busca or nome.lower(),
    )


def test_quem_fecha_o_bloco_e_recalculado_depois_da_busca():
    """Filtrar o último produto de um bloco passa o "fecha" (os cantos de baixo
    do cartão) para a linha de cima — senão o cartão ficaria aberto embaixo."""
    grupo = FotoGrupo("Podrão", "Podrão", True, (_foto("x burguer"), _foto("x tudo")))

    itens = montar_itens([grupo], "burguer", com_cabecalho=True, normalizar=str.lower, texto_vazio="")

    produtos = [item for item in itens if item.tipo is TipoDeItem.PRODUTO]
    assert [p.produto.nome for p in produtos] == ["x burguer"]
    assert produtos[0].fecha is True


def test_a_busca_sem_resultado_diz_o_que_foi_buscado():
    grupo = FotoGrupo("Podrão", "Podrão", True, (_foto("x burguer"),))

    itens = montar_itens([grupo], "pizza", com_cabecalho=True, normalizar=str.lower, texto_vazio="")

    assert [item.tipo for item in itens] == [TipoDeItem.VAZIO]
    assert itens[0].texto == "NENHUM PRODUTO ENCONTRADO PARA “pizza”"


def test_os_blocos_sao_separados_por_um_espaco():
    grupos = [
        FotoGrupo("A", "A", True, (_foto("um"),)),
        FotoGrupo("B", "B", True, (_foto("dois"),)),
    ]

    itens = montar_itens(grupos, "", com_cabecalho=True, normalizar=str.lower, texto_vazio="")

    assert [item.tipo for item in itens] == [
        TipoDeItem.CABECALHO,
        TipoDeItem.PRODUTO,
        TipoDeItem.ESPACO,
        TipoDeItem.CABECALHO,
        TipoDeItem.PRODUTO,
    ]


def test_nome_comprido_sai_com_reticencias_e_nunca_cortado(qapp):
    """"Salada de Maion…", como no mockup: o nome encolhe com reticências e
    cabe no espaço dele — nunca com a letra cortada ao meio pela coluna do
    preço."""
    delegado = DelegadoProdutos()
    fonte = QFont()
    comprido = _foto("Caipivodka Abacaxi/Limão/Maracujá/Morango 500ml")
    curto = _foto("Arroz")
    linha = QRect(0, 0, 420, 60)

    visivel = delegado.nome_visivel(comprido, linha, fonte)

    assert visivel.endswith("…") and visivel != comprido.nome
    assert delegado.nome_visivel(curto, linha, fonte) == "Arroz"


@pytest.mark.parametrize("largura", [760, 460, 400, 360, 320])
def test_o_nome_nunca_fica_abaixo_do_piso_antes_de_custo_e_barra_sairem(qapp, largura):
    """O nome é o que se procura na linha, e é o último a perder espaço: numa
    linha estreita o custo sai primeiro, depois a barra de margem. Medido com a
    fonte do sistema da suíte, que no `offscreen` mede MAIS largo que a da
    marca — o degrau tem que funcionar com qualquer fonte, não só com a
    Archivo Black."""
    delegado = DelegadoProdutos()

    colunas = delegado.colunas(QRect(0, 0, largura, 60), QFont())

    if colunas.custo.width() > 0:
        assert colunas.barra.width() > 0, "a barra saiu antes do custo"
    if colunas.nome.width() < DelegadoProdutos.NOME_MINIMO_PX:
        assert colunas.custo.width() == 0 and colunas.barra.width() == 0, (
            f"o nome ficou com {colunas.nome.width():.0f}px com coluna sobrando para ceder"
        )
    assert colunas.nome.right() <= colunas.preco.left(), "o nome invadiu a coluna do preço"


def test_na_linha_larga_todas_as_colunas_aparecem(qapp):
    colunas = DelegadoProdutos().colunas(QRect(0, 0, 1200, 60), QFont())

    assert colunas.custo.width() > 0
    assert colunas.barra.width() > 0
    assert colunas.nome.width() >= DelegadoProdutos.NOME_MINIMO_PX
