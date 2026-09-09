"""O sub-modelo na tela de Cardápio: cadastro com sugestão, badge e filtro. §9.8.

A tela de Cardápio é onde o sub-modelo nasce e onde ele é usado para trabalhar.
Os testes abaixo cobrem as quatro coisas que fariam a subdivisão atrapalhar em
vez de ajudar:

1. **a sugestão tem que sugerir o que existe** — a faixa de pílulas do modal
   mostra os sub-modelos DAQUELA categoria, e trocar a categoria troca a faixa.
   Sugerir "Podrão" (de Lanches) dentro de "Bebidas" seria pior que não sugerir;
2. **a faixa some quando não há o que sugerir** — o cardápio de hoje não tem
   sub-modelo nenhum, e uma faixa vazia permanente comeria altura numa tela que
   já foi medida contra um monitor de 768px (`test_telas_cabem_na_tela.py`);
3. **o filtro filtra de verdade** — e "TODOS" devolve tudo. Um filtro que
   esconde a tabela sem dizer por quê é como o gerente conclui que o produto
   sumiu do cadastro;
4. **nada sobra na memória** — o RNF do Celeron. Trocar de categoria destrói as
   pílulas antigas em vez de acumulá-las numa tela que fica aberta o turno
   inteiro.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QLabel, QPushButton

import gestor_comercial
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.views.cardapio_view import (
    _SUBMODELO_NENHUM,
    _SUBMODELO_TODOS,
    CardapioView,
    DadosProduto,
    _ProdutoDialog,
)


@pytest.fixture
def com_a_fonte_da_marca(qapp):
    """Registra a fonte da marca e aplica o QSS global — o estado do app real.

    Sem os dois, o teste do selo comprido passa verde sem ter olhado. A
    plataforma `offscreen` sobe com o banco de fontes **vazio**, e é o QSS que
    veste o selo com a `Archivo Black`, ~20% mais larga que a fonte do sistema
    na mesma altura de 9px. É justamente essa diferença que
    `_criar_badge_submodelo` resolve com o `ensurePolished()`; medida sem
    fonte, ela não existe e a medição errada caberia por acaso.

    Mesmo arranjo (e mesmo motivo) de `test_mesas_ocupadas_em_vermelho`. A
    fonte sai do banco no fim, para não mudar a medida dos testes seguintes.
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

    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    try:
        yield
    finally:
        controlador.alternar_para(False)
        QFontDatabase.removeApplicationFont(identificador)


@pytest.fixture
def cardapio_com_submodelos(cardapio, gerente):
    """Lanches com dois sub-modelos e um item solto; Bebidas sem nenhum.

    É o estado intermediário real: o gerente classifica uma categoria por vez, e
    a tela tem que funcionar durante a classificação, não só no fim.
    """
    lanches = cardapio.criar_categoria("Lanches")
    bebidas = cardapio.criar_categoria("Bebidas")
    cardapio.criar_produto("X Podrão", Decimal("12.00"), lanches.id, subcategoria="Podrão")
    cardapio.criar_produto(
        "X Missão Impossível", Decimal("28.00"), lanches.id, subcategoria="Artesanal"
    )
    cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)
    cardapio.criar_produto("Coca Lata", Decimal("8.00"), bebidas.id)
    return lanches, bebidas


@pytest.fixture
def tela(qapp, cardapio, cardapio_com_submodelos):
    """A tela de Cardápio montada com o service real, descartada no fim."""
    view = CardapioView(cardapio)
    yield view
    view.deleteLater()


def _selecionar_categoria(tela: CardapioView, nome: str) -> None:
    """Faz o que o clique na lista de categorias faz.

    A view liga `categoria_selecionada` a `exibir_categoria`; chamar o destino
    direto evita depender do índice da linha, que muda com a ordem alfabética.
    """
    alvo = next(c for c in tela._service.listar_categorias() if c.nome == nome)
    tela._painel_produtos.exibir_categoria(alvo)


def _letras(badge: QLabel) -> int:
    """Quantas letras do sub-modelo sobraram no selo, sem contar a reticência."""
    return len(badge.text().rstrip("…"))


def _largura_do_selo(texto: str) -> int:
    """A largura que o selo teria com este texto, medida como a tela mede.

    Um `QLabel` de verdade, com o mesmo `objectName` e já polido — é a mesma
    conta que `_criar_badge_submodelo` faz, e não uma reimplementação dela.
    """
    rotulo = QLabel(texto)
    rotulo.setObjectName("badgeSubmodelo")
    rotulo.ensurePolished()
    try:
        return rotulo.sizeHint().width()
    finally:
        rotulo.deleteLater()


def _pills(painel) -> dict[str, str]:
    """chave da pílula -> rótulo exibido, na ordem em que aparecem."""
    return {
        chave: pill.text() for chave, pill in painel._pills_submodelo.items()
    }


def _visiveis(painel) -> list[str]:
    return [
        produto.nome
        for linha, produto in enumerate(painel._produtos)
        if not painel.tabela.isRowHidden(linha)
    ]


# ---------------------------------------------------------------------------
# Modal de cadastro: campo e sugestões
# ---------------------------------------------------------------------------


def _abrir_modal(cardapio, categoria_id, **extra) -> _ProdutoDialog:
    categorias = cardapio.listar_categorias_ativas()
    return _ProdutoDialog(
        "Novo produto",
        categorias,
        categoria_id_inicial=categoria_id,
        subcategorias_por_categoria={
            c.id: cardapio.listar_subcategorias(c.id) for c in categorias
        },
        **extra,
    )


def test_o_campo_de_submodelo_nasce_vazio_e_opcional(qapp, cardapio, cardapio_com_submodelos):
    lanches, _ = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, lanches.id)

    try:
        assert modal._campo_submodelo.text() == ""
        assert modal.resultado().subcategoria is None
    finally:
        modal.deleteLater()


def test_as_sugestoes_sao_as_da_categoria_selecionada(qapp, cardapio, cardapio_com_submodelos):
    lanches, _ = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, lanches.id)

    try:
        assert [pill.text() for pill in modal._pills_submodelo] == ["Artesanal", "Podrão"]
        assert modal._faixa_submodelos.isVisibleTo(modal) is True
    finally:
        modal.deleteLater()


def test_categoria_sem_submodelo_nao_mostra_faixa(qapp, cardapio, cardapio_com_submodelos):
    """O estado do cardápio de hoje: nenhuma faixa, nenhuma altura gasta."""
    _, bebidas = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, bebidas.id)

    try:
        assert modal._pills_submodelo == []
        assert modal._faixa_submodelos.isVisibleTo(modal) is False
    finally:
        modal.deleteLater()


def test_clicar_na_sugestao_preenche_o_campo(qapp, cardapio, cardapio_com_submodelos):
    lanches, _ = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, lanches.id)

    try:
        modal._pills_submodelo[1].click()

        assert modal._campo_submodelo.text() == "Podrão"
        assert modal.resultado().subcategoria == "Podrão"
    finally:
        modal.deleteLater()


def test_a_pilula_acende_junto_com_o_campo(qapp, cardapio, cardapio_com_submodelos):
    """O sinal de que o clique fez alguma coisa — e a única pista de que um
    segundo clique vai desfazer."""
    lanches, _ = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, lanches.id)

    try:
        modal._pills_submodelo[1].click()

        assert modal._pills_submodelo[1].property("ativa") is True
        assert modal._pills_submodelo[0].property("ativa") is False
    finally:
        modal.deleteLater()


def test_digitar_a_mao_acende_a_mesma_pilula(qapp, cardapio, cardapio_com_submodelos):
    """Quem digita "Podrão" tem que ver o mesmo sinal de quem clicou nela — a
    mensagem é "este item vai para este grupo", e ela não muda com o gesto."""
    lanches, _ = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, lanches.id)

    try:
        modal._campo_submodelo.setText("Podrão")

        assert modal._pills_submodelo[1].property("ativa") is True
    finally:
        modal.deleteLater()


def test_o_modal_de_edicao_abre_com_a_pilula_ja_acesa(qapp, cardapio, cardapio_com_submodelos):
    """Editar um produto já classificado mostra em qual grupo ele está, sem o
    gerente ter que comparar o texto do campo com a lista de pílulas."""
    lanches, _ = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, lanches.id, subcategoria_inicial="Podrão")

    try:
        assert modal._pills_submodelo[1].property("ativa") is True
    finally:
        modal.deleteLater()


def test_clicar_de_novo_na_mesma_sugestao_limpa(qapp, cardapio, cardapio_com_submodelos):
    """Sem isto, quem clica na pílula errada teria que apagar o texto à mão."""
    lanches, _ = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, lanches.id)

    try:
        modal._pills_submodelo[1].click()
        modal._pills_submodelo[1].click()

        assert modal._campo_submodelo.text() == ""
        assert modal.resultado().subcategoria is None
    finally:
        modal.deleteLater()


def test_trocar_de_categoria_troca_as_sugestoes(qapp, cardapio, cardapio_com_submodelos):
    lanches, bebidas = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, lanches.id)

    try:
        indice = modal._seletor_categoria.findData(bebidas.id)
        modal._seletor_categoria.setCurrentIndex(indice)

        assert modal._pills_submodelo == []
        assert modal._faixa_submodelos.isVisibleTo(modal) is False
    finally:
        modal.deleteLater()


def test_trocar_de_categoria_nao_apaga_o_que_foi_digitado(qapp, cardapio, cardapio_com_submodelos):
    """Quem escolheu a categoria errada e corrige não pode perder o sub-modelo
    que acabou de escrever."""
    lanches, bebidas = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, lanches.id)

    try:
        modal._campo_submodelo.setText("Refrigerante")
        modal._seletor_categoria.setCurrentIndex(modal._seletor_categoria.findData(bebidas.id))

        assert modal.resultado().subcategoria == "Refrigerante"
    finally:
        modal.deleteLater()


def test_trocar_de_categoria_nao_acumula_pilulas(qapp, assentar, cardapio, cardapio_com_submodelos):
    """O RNF do Celeron: as pílulas antigas morrem, não ficam penduradas.

    Dez idas e voltas no seletor, que é o que o gerente faz procurando a
    categoria certa. Sobram as duas de Lanches e nada mais.
    """
    lanches, bebidas = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, lanches.id)

    try:
        for _ in range(10):
            modal._seletor_categoria.setCurrentIndex(
                modal._seletor_categoria.findData(bebidas.id)
            )
            modal._seletor_categoria.setCurrentIndex(
                modal._seletor_categoria.findData(lanches.id)
            )
        assentar()

        pendurados = [
            botao
            for botao in modal._faixa_submodelos.findChildren(QPushButton)
            if botao.objectName() == "pillSubmodelo"
        ]
        assert len(pendurados) == 2, f"{len(pendurados)} pílulas presas depois de 10 trocas"
    finally:
        modal.deleteLater()


def test_o_resultado_leva_o_formulario_inteiro(qapp, cardapio, cardapio_com_submodelos):
    """A tupla de sete posições virou `DadosProduto` justamente para isto: os
    campos chegam ao service pelo NOME, e não pela ordem."""
    lanches, _ = cardapio_com_submodelos
    modal = _abrir_modal(cardapio, lanches.id)

    try:
        modal._campo_nome.setText("X Podrão Duplo")
        modal._campo_preco.setText("16,00")
        modal._campo_descricao.setText("Com dois hambúrgueres")
        modal._campo_submodelo.setText("  Podrão  ")

        dados = modal.resultado()

        assert dados == DadosProduto(
            nome="X Podrão Duplo",
            preco=Decimal("16.00"),
            custo=Decimal("0"),
            categoria_id=lanches.id,
            descricao="Com dois hambúrgueres",
            imagem_path=None,
            subcategoria="Podrão",
        )
    finally:
        modal.deleteLater()


# ---------------------------------------------------------------------------
# Painel de produtos: badge e filtro
# ---------------------------------------------------------------------------


def test_o_badge_do_submodelo_aparece_ao_lado_do_nome(tela, cardapio_com_submodelos):
    lanches, _ = cardapio_com_submodelos
    painel = tela._painel_produtos
    _selecionar_categoria(tela, "Lanches")

    linha = painel._produtos.index(
        next(p for p in painel._produtos if p.nome == "X Podrão")
    )
    celula = painel.tabela.cellWidget(linha, 0)
    badges = [
        rotulo.text()
        for rotulo in celula.findChildren(QLabel)
        if rotulo.objectName() == "badgeSubmodelo"
    ]

    assert badges == ["PODRÃO"]


def test_o_badge_comprido_e_encurtado_em_vez_de_comer_o_nome(
    qapp, com_a_fonte_da_marca, cardapio, gerente
):
    """O defeito que a primeira renderização com dado real mostrou.

    Com o sub-modelo "Cachorro Quente", o selo crescia até o `QLabel` do nome —
    que corta **sem reticências** — e "Cachorro Quente Linguiça" aparecia como
    "Cachorro Quente Lin", sem nada na tela dizendo que faltava texto. O nome do
    produto é o dado; o sub-modelo é a dica, e é a dica que encurta.

    O teto só é ultrapassável se a medição usar a fonte errada, e é por isso que
    este teste pede `com_a_fonte_da_marca`: sem ela o `ensurePolished()` de
    `_criar_badge_submodelo` poderia sumir sem ninguém notar.
    """
    from gestor_comercial.ui.views.cardapio_view import (
        _LARGURA_MAXIMA_BADGE_PX,
        _criar_celula_produto,
    )

    lanches = cardapio.criar_categoria("Lanches")
    produto = cardapio.criar_produto(
        "Cachorro Quente Linguiça",
        Decimal("14.00"),
        lanches.id,
        subcategoria="Cachorro Quente",
    )

    celula = _criar_celula_produto(produto)
    try:
        badge = next(
            r for r in celula.findChildren(QLabel) if r.objectName() == "badgeSubmodelo"
        )

        assert badge.text() != "CACHORRO QUENTE", "o selo não foi encurtado"
        assert badge.text().endswith("…")
        # O que a reticência comeu continua alcançável.
        assert badge.toolTip() == "Cachorro Quente"

        # As duas metades da medida certa. Só a primeira deixaria passar uma
        # medição feita com a fonte errada: cortar DEMAIS também cabe no teto, e
        # joga fora letra que o gerente conseguiria ler. É essa segunda metade
        # que reprova quem tirar o `ensurePolished()`.
        assert badge.sizeHint().width() <= _LARGURA_MAXIMA_BADGE_PX, "o selo passou do teto"
        assert _largura_do_selo("CACHORRO QUENTE"[: _letras(badge) + 1] + "…") > (
            _LARGURA_MAXIMA_BADGE_PX
        ), "o selo foi encurtado além do necessário — sobrou espaço para mais uma letra"
    finally:
        celula.deleteLater()


def test_o_badge_curto_nao_ganha_reticencia_nem_tooltip(qapp, cardapio, gerente):
    """O caso comum — "Podrão", "Fritas" — sai inteiro, sem enfeite."""
    from gestor_comercial.ui.views.cardapio_view import _criar_celula_produto

    lanches = cardapio.criar_categoria("Lanches")
    produto = cardapio.criar_produto(
        "X Burguer", Decimal("13.00"), lanches.id, subcategoria="Podrão"
    )

    celula = _criar_celula_produto(produto)
    try:
        badge = next(
            r for r in celula.findChildren(QLabel) if r.objectName() == "badgeSubmodelo"
        )

        assert badge.text() == "PODRÃO"
        assert badge.toolTip() == ""
    finally:
        celula.deleteLater()


def test_produto_sem_submodelo_nao_ganha_badge(tela, cardapio_com_submodelos):
    """Nem um selo vazio nem um espaço reservado: a célula é a de sempre."""
    painel = tela._painel_produtos
    _selecionar_categoria(tela, "Lanches")

    linha = painel._produtos.index(
        next(p for p in painel._produtos if p.nome == "X Burguer")
    )
    celula = painel.tabela.cellWidget(linha, 0)

    assert [r for r in celula.findChildren(QLabel) if r.objectName() == "badgeSubmodelo"] == []


def test_a_faixa_de_filtro_lista_os_submodelos_e_o_sem_submodelo(tela, cardapio_com_submodelos):
    painel = tela._painel_produtos
    _selecionar_categoria(tela, "Lanches")

    assert list(_pills(painel).values()) == [
        "TODOS",
        "ARTESANAL",
        "PODRÃO",
        "SEM SUB-MODELO",
    ]
    assert painel._faixa_submodelos.isVisibleTo(painel) is True


def test_a_faixa_some_na_categoria_sem_submodelo(tela, cardapio_com_submodelos):
    painel = tela._painel_produtos
    _selecionar_categoria(tela, "Bebidas")

    assert painel._pills_submodelo == {}
    assert painel._faixa_submodelos.isVisibleTo(painel) is False


def test_clicar_na_pilula_filtra_a_tabela(tela, cardapio_com_submodelos):
    painel = tela._painel_produtos
    _selecionar_categoria(tela, "Lanches")

    painel._pills_submodelo["Podrão"].click()

    assert _visiveis(painel) == ["X Podrão"]
    assert painel._pills_submodelo["Podrão"].property("ativa") is True
    assert painel._pills_submodelo[_SUBMODELO_TODOS].property("ativa") is False


def test_a_pilula_sem_submodelo_acha_quem_falta_classificar(tela, cardapio_com_submodelos):
    """A lista de trabalho de quem está organizando o cardápio."""
    painel = tela._painel_produtos
    _selecionar_categoria(tela, "Lanches")

    painel._pills_submodelo[_SUBMODELO_NENHUM].click()

    assert _visiveis(painel) == ["X Burguer"]


def test_todos_devolve_a_categoria_inteira(tela, cardapio_com_submodelos):
    painel = tela._painel_produtos
    _selecionar_categoria(tela, "Lanches")
    painel._pills_submodelo["Podrão"].click()

    painel._pills_submodelo[_SUBMODELO_TODOS].click()

    assert sorted(_visiveis(painel)) == ["X Burguer", "X Missão Impossível", "X Podrão"]


def test_busca_e_pilula_valem_juntas(tela, cardapio_com_submodelos):
    painel = tela._painel_produtos
    _selecionar_categoria(tela, "Lanches")
    painel._pills_submodelo["Podrão"].click()

    painel._campo_busca.setText("missão")

    assert _visiveis(painel) == []


def test_a_busca_do_cardapio_tambem_acha_pelo_submodelo(tela, cardapio_com_submodelos):
    """A mesma busca do modal de lançamento. Telas que buscam diferente sobre o
    mesmo cardápio é como o gerente conclui que o produto sumiu."""
    painel = tela._painel_produtos
    _selecionar_categoria(tela, "Lanches")

    painel._campo_busca.setText("artesanal")

    assert _visiveis(painel) == ["X Missão Impossível"]


def test_trocar_de_categoria_solta_o_filtro(tela, cardapio_com_submodelos):
    """O defeito que isto impede: filtrar Lanches por "Podrão" e clicar em
    Bebidas deixaria a tabela vazia, com a faixa escondida e nada na tela
    explicando por que a categoria "não tem produto"."""
    painel = tela._painel_produtos
    _selecionar_categoria(tela, "Lanches")
    painel._pills_submodelo["Podrão"].click()

    _selecionar_categoria(tela, "Bebidas")

    assert _visiveis(painel) == ["Coca Lata"]


def test_trocar_de_categoria_nao_acumula_pilulas_de_filtro(tela, assentar, cardapio_com_submodelos):
    """O mesmo RNF do modal, na tela que fica aberta o turno inteiro."""
    painel = tela._painel_produtos

    for _ in range(10):
        _selecionar_categoria(tela, "Lanches")
        _selecionar_categoria(tela, "Bebidas")
    _selecionar_categoria(tela, "Lanches")
    assentar()

    pendurados = [
        botao
        for botao in painel._faixa_submodelos.findChildren(QPushButton)
        if botao.objectName() == "pillSubmodelo"
    ]
    assert len(pendurados) == 4, f"{len(pendurados)} pílulas presas depois de 10 trocas"
