"""Os números do topo do Cardápio e a conta de margem, no service. §9.11.

Moravam na tela: `cardapio_view` recebia as listas cruas, contava, tirava média
e definia margem sozinha — e buscava as subcategorias uma categoria por vez só
para contá-las. Regra de negócio saiu da camada de visão; estes testes são o
contrato do que a tela passou a receber pronto.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from gestor_comercial.services.cardapio_service import CardapioService, margem_percentual


@pytest.fixture
def cardapio(uow, auth, gerente):
    return CardapioService(uow, auth)


# ---------------------------------------------------------------------------
# margem_percentual
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("preco", "custo", "esperado"),
    [
        (Decimal("10.00"), Decimal("3.20"), 68.0),
        (Decimal("5.00"), Decimal("0.00"), 100.0),
        (Decimal("12.00"), Decimal("12.00"), 0.0),
        # Custo acima do preço é venda no prejuízo — a margem negativa é a
        # informação certa, e a tela a pinta de vermelho.
        (Decimal("10.00"), Decimal("12.50"), -25.0),
    ],
)
def test_margem_e_o_que_sobra_do_preco(preco, custo, esperado):
    assert margem_percentual(preco, custo) == pytest.approx(esperado)


@pytest.mark.parametrize("preco", [None, Decimal("0.00"), Decimal("-1.00")])
def test_sem_preco_nao_ha_margem_e_nao_ha_divisao_por_zero(preco):
    assert margem_percentual(preco, Decimal("1.00")) == 0.0


def test_custo_ausente_conta_como_zero():
    assert margem_percentual(Decimal("8.00"), None) == 100.0


# ---------------------------------------------------------------------------
# resumo_do_cardapio
# ---------------------------------------------------------------------------


def test_resumo_de_um_cardapio_vazio(cardapio):
    resumo = cardapio.resumo_do_cardapio()

    assert (resumo.categorias, resumo.subcategorias, resumo.produtos) == (0, 0, 0)
    assert resumo.preco_medio == Decimal("0.00")
    assert resumo.margem_media == 0.0


def test_resumo_conta_e_tira_as_medias(cardapio):
    acompanhamentos = cardapio.criar_categoria("Acompanhamentos")
    bebidas = cardapio.criar_categoria("Bebidas")
    guarnicoes = cardapio.criar_subcategoria(acompanhamentos.id, "Guarnições")
    cardapio.criar_subcategoria(acompanhamentos.id, "Saladas")
    cardapio.criar_produto(
        "Arroz", Decimal("10.00"), acompanhamentos.id, Decimal("3.20"), subcategoria_id=guarnicoes.id
    )
    cardapio.criar_produto("Farofa", Decimal("5.00"), acompanhamentos.id, Decimal("1.40"))
    cardapio.criar_produto("Coca Lata", Decimal("8.00"), bebidas.id, Decimal("6.00"))
    cardapio.desativar_categoria(bebidas.id)

    resumo = cardapio.resumo_do_cardapio()

    assert resumo.categorias == 2
    assert resumo.categorias_ativas == 1
    assert resumo.subcategorias == 2
    assert resumo.produtos == 3
    # (10 + 5 + 8) / 3 = 7,666… → 7,67, meio centavo para cima (§dinheiro).
    assert resumo.preco_medio == Decimal("7.67")
    # Média das margens de cada produto (68, 72 e 25): 55%. A margem do
    # cardápio somado daria outra coisa — (23 − 10,60) / 23 = 53,9% —, e é
    # essa a conta que um item caro dominaria. Os números foram escolhidos
    # para as duas contas NÃO coincidirem: com a Coca a custo zero, as duas
    # davam exatamente 80% e o teste não distinguia uma da outra.
    assert resumo.margem_media == pytest.approx((68.0 + 72.0 + 25.0) / 3)


def test_produto_desativado_continua_no_resumo(cardapio):
    """O topo descreve o catálogo cadastrado — a mesma população que a árvore
    conta ao lado de cada categoria."""
    lanches = cardapio.criar_categoria("Lanches")
    produto = cardapio.criar_produto("X Tudo", Decimal("16.00"), lanches.id)
    cardapio.desativar_produto(produto.id)

    assert cardapio.resumo_do_cardapio().produtos == 1


def test_resumo_custa_tres_consultas_fixas(cardapio, uow):
    """Eram 17 consultas no cardápio real (duas listas e uma por categoria).
    O número agora não depende de quantas categorias existem."""
    from sqlalchemy import event

    def contar() -> int:
        total = [0]

        def _somar(*_argumentos, **_nomeados) -> None:
            total[0] += 1

        motor = uow.session.get_bind()
        event.listen(motor, "after_cursor_execute", _somar)
        try:
            cardapio.resumo_do_cardapio()
        finally:
            event.remove(motor, "after_cursor_execute", _somar)
        return total[0]

    for indice in range(3):
        categoria = cardapio.criar_categoria(f"Categoria {indice}")
        cardapio.criar_subcategoria(categoria.id, "Sub")
    poucas = contar()
    for indice in range(3, 15):
        categoria = cardapio.criar_categoria(f"Categoria {indice}")
        cardapio.criar_subcategoria(categoria.id, "Sub")

    assert contar() == poucas == 3


# ---------------------------------------------------------------------------
# listar_todas_as_subcategorias
# ---------------------------------------------------------------------------


def test_listar_todas_as_subcategorias_traz_as_de_toda_categoria(cardapio):
    lanches = cardapio.criar_categoria("Lanches")
    porcoes = cardapio.criar_categoria("Porções")
    cardapio.criar_subcategoria(lanches.id, "Podrão")
    cardapio.criar_subcategoria(porcoes.id, "Fritas")
    cardapio.criar_subcategoria(lanches.id, "Artesanal")

    pares = [(s.categoria_id, s.nome) for s in cardapio.listar_todas_as_subcategorias()]

    assert pares == [(lanches.id, "Artesanal"), (lanches.id, "Podrão"), (porcoes.id, "Fritas")]
