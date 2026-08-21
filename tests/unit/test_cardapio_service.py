from datetime import datetime
from decimal import Decimal

import pytest

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from tests.conftest import PIN_ATENDENTE


@pytest.fixture
def cardapio(uow, auth, gerente):
    """Service com um gerente logado — o estado em que as telas de cadastro abrem."""
    return CardapioService(uow, auth)


@pytest.fixture
def como_atendente(auth, atendente):
    """Troca a sessão para um atendente, para testar o bloqueio de perfil de §3.1."""
    auth.login(PIN_ATENDENTE)
    return atendente


def vender(uow, gerente, caixa_aberto, produto):
    """Deixa o produto com histórico de venda, que é o que bloqueia a exclusão."""
    comanda = uow.comandas.salvar(
        Comanda(
            aberta_em=datetime(2026, 8, 20, 12, 0),
            funcionario_id=gerente.id,
            caixa_id=caixa_aberto.id,
        )
    )
    return uow.itens.salvar(
        ItemComanda(
            quantidade=1,
            preco_unit_congelado=produto.preco,
            comanda_id=comanda.id,
            produto_id=produto.id,
        )
    )


# ----------------------------------------------------------------------
# Categorias
# ----------------------------------------------------------------------


def test_criar_categoria_nasce_ativa_com_nome_limpo(cardapio):
    nova = cardapio.criar_categoria("  Bebidas  ")

    assert nova.id is not None
    assert nova.nome == "Bebidas"
    assert nova.ativo is True


def test_criar_categoria_com_nome_vazio(cardapio):
    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_categoria("   ")


def test_criar_categoria_com_nome_repetido(cardapio, categoria):
    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_categoria("Lanches")


def test_criar_categoria_exige_gerente(cardapio, como_atendente):
    with pytest.raises(AcessoNegadoError):
        cardapio.criar_categoria("Bebidas")


def test_listar_categorias_traz_ativas_e_inativas(cardapio, categoria):
    bebidas = cardapio.criar_categoria("Bebidas")
    cardapio.desativar_categoria(bebidas.id)

    assert [c.nome for c in cardapio.listar_categorias()] == ["Bebidas", "Lanches"]


def test_listar_categorias_ativas_ignora_desativadas(cardapio, categoria):
    cardapio.criar_categoria("Bebidas")
    cardapio.desativar_categoria(categoria.id)

    assert [c.nome for c in cardapio.listar_categorias_ativas()] == ["Bebidas"]


def test_listar_categorias_nao_exige_gerente(cardapio, categoria, como_atendente):
    assert [c.nome for c in cardapio.listar_categorias()] == ["Lanches"]
    assert [c.nome for c in cardapio.listar_categorias_ativas()] == ["Lanches"]


def test_buscar_categoria_por_id(cardapio, categoria):
    assert cardapio.buscar_categoria(categoria.id) is categoria


def test_buscar_categoria_inexistente(cardapio):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.buscar_categoria(9999)


def test_editar_categoria_troca_o_nome(cardapio, categoria):
    editada = cardapio.editar_categoria(categoria.id, "  Sanduíches  ")

    assert editada.nome == "Sanduíches"
    assert cardapio.buscar_categoria(categoria.id).nome == "Sanduíches"


def test_editar_categoria_aceita_o_proprio_nome(cardapio, categoria):
    """Salvar a tela sem mexer no nome não pode acusar nome duplicado."""
    editada = cardapio.editar_categoria(categoria.id, "Lanches")
    assert editada.nome == "Lanches"


def test_editar_categoria_com_nome_de_outra(cardapio, categoria):
    bebidas = cardapio.criar_categoria("Bebidas")
    with pytest.raises(RegraDeNegocioError):
        cardapio.editar_categoria(bebidas.id, "Lanches")


def test_editar_categoria_com_nome_vazio(cardapio, categoria):
    with pytest.raises(RegraDeNegocioError):
        cardapio.editar_categoria(categoria.id, "")


def test_editar_categoria_inexistente(cardapio):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.editar_categoria(9999, "Bebidas")


def test_editar_categoria_exige_gerente(cardapio, categoria, como_atendente):
    with pytest.raises(AcessoNegadoError):
        cardapio.editar_categoria(categoria.id, "Bebidas")


def test_desativar_categoria_e_soft(cardapio, categoria):
    desativada = cardapio.desativar_categoria(categoria.id)

    assert desativada.ativo is False
    assert cardapio.buscar_categoria(categoria.id) is not None


def test_desativar_categoria_ja_desativada(cardapio, categoria):
    cardapio.desativar_categoria(categoria.id)
    with pytest.raises(RegraDeNegocioError):
        cardapio.desativar_categoria(categoria.id)


def test_desativar_categoria_exige_gerente(cardapio, categoria, como_atendente):
    with pytest.raises(AcessoNegadoError):
        cardapio.desativar_categoria(categoria.id)


def test_excluir_categoria_sem_produtos(cardapio, categoria):
    bebidas = cardapio.criar_categoria("Bebidas")
    cardapio.excluir_categoria(bebidas.id)

    assert [c.nome for c in cardapio.listar_categorias()] == ["Lanches"]


def test_excluir_categoria_com_produto_vinculado(cardapio, categoria, produto):
    with pytest.raises(RegraDeNegocioError):
        cardapio.excluir_categoria(categoria.id)


def test_excluir_categoria_inexistente(cardapio):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.excluir_categoria(9999)


def test_excluir_categoria_exige_gerente(cardapio, categoria, como_atendente):
    with pytest.raises(AcessoNegadoError):
        cardapio.excluir_categoria(categoria.id)


def test_associar_impressora_a_categoria(cardapio, categoria):
    impressora = cardapio.criar_impressora("Cozinha")
    associada = cardapio.associar_impressora(categoria.id, impressora.id)

    assert associada.impressora_id == impressora.id


def test_associar_impressora_a_categoria_inexistente(cardapio):
    impressora = cardapio.criar_impressora("Cozinha")
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.associar_impressora(9999, impressora.id)


def test_associar_impressora_inexistente(cardapio, categoria):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.associar_impressora(categoria.id, 9999)


def test_associar_impressora_exige_gerente(cardapio, categoria, como_atendente):
    with pytest.raises(AcessoNegadoError):
        cardapio.associar_impressora(categoria.id, 1)


# ----------------------------------------------------------------------
# Produtos
# ----------------------------------------------------------------------


def test_criar_produto_grava_valores_e_nasce_ativo(cardapio, categoria):
    novo = cardapio.criar_produto(
        "  X-Salada  ",
        Decimal("18.5"),
        categoria.id,
        custo=Decimal("7.25"),
        descricao="  Com queijo  ",
    )

    assert novo.id is not None
    assert novo.nome == "X-Salada"
    assert novo.preco == Decimal("18.50")
    assert novo.custo == Decimal("7.25")
    assert novo.descricao == "Com queijo"
    assert novo.categoria_id == categoria.id
    assert novo.ativo is True
    assert novo.is_combo is False


def test_criar_produto_sem_custo_fica_zerado(cardapio, categoria):
    novo = cardapio.criar_produto("Água", Decimal("5.00"), categoria.id)

    assert novo.custo == Decimal("0.00")
    assert novo.descricao is None


def test_criar_produto_arredonda_meio_centavo_pra_cima(cardapio, categoria):
    novo = cardapio.criar_produto("Suco", Decimal("4.005"), categoria.id, custo=Decimal("1.004"))

    assert novo.preco == Decimal("4.01")
    assert novo.custo == Decimal("1.00")


def test_criar_produto_com_nome_vazio(cardapio, categoria):
    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_produto("   ", Decimal("10.00"), categoria.id)


def test_criar_produto_com_preco_zerado(cardapio, categoria):
    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_produto("Brinde", Decimal("0.00"), categoria.id)


def test_criar_produto_com_preco_negativo(cardapio, categoria):
    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_produto("Brinde", Decimal("-1.00"), categoria.id)


def test_criar_produto_com_custo_negativo(cardapio, categoria):
    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_produto("X-Tudo", Decimal("20.00"), categoria.id, custo=Decimal("-0.01"))


def test_criar_produto_recusa_preco_em_float(cardapio, categoria):
    """Float é erro de programação da tela (esqueceu de converter pra Decimal),
    não erro de digitação do operador — mesmo critério de caixa/pagamento."""
    with pytest.raises(TypeError):
        cardapio.criar_produto("X-Tudo", 20.0, categoria.id)


def test_criar_produto_recusa_preco_none(cardapio, categoria):
    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_produto("X-Tudo", None, categoria.id)


def test_criar_produto_com_preco_ilegivel(cardapio, categoria):
    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_produto("X-Tudo", "vinte reais", categoria.id)


def test_criar_produto_com_categoria_inexistente(cardapio):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.criar_produto("X-Tudo", Decimal("20.00"), 9999)


def test_criar_produto_exige_gerente(cardapio, categoria, como_atendente):
    with pytest.raises(AcessoNegadoError):
        cardapio.criar_produto("X-Tudo", Decimal("20.00"), categoria.id)


def test_listar_produtos_traz_ativos_e_inativos(cardapio, categoria, produto):
    refrigerante = cardapio.criar_produto("Refrigerante", Decimal("6.00"), categoria.id)
    cardapio.desativar_produto(refrigerante.id)

    assert [p.nome for p in cardapio.listar_produtos()] == ["Refrigerante", "X-Burger"]


def test_listar_produtos_ativos_ignora_desativados(cardapio, categoria, produto):
    cardapio.criar_produto("Água", Decimal("5.00"), categoria.id)
    cardapio.desativar_produto(produto.id)

    assert [p.nome for p in cardapio.listar_produtos_ativos()] == ["Água"]


def test_listar_produtos_ativos_ignora_produto_de_categoria_desativada(cardapio, categoria, produto):
    bebidas = cardapio.criar_categoria("Bebidas")
    cardapio.criar_produto("Água", Decimal("5.00"), bebidas.id)
    cardapio.desativar_categoria(categoria.id)

    assert [p.nome for p in cardapio.listar_produtos_ativos()] == ["Água"]


def test_listar_produtos_nao_exige_gerente(cardapio, produto, como_atendente):
    assert [p.nome for p in cardapio.listar_produtos()] == ["X-Burger"]
    assert [p.nome for p in cardapio.listar_produtos_ativos()] == ["X-Burger"]


def test_buscar_produto_por_id(cardapio, produto):
    assert cardapio.buscar_produto(produto.id) is produto


def test_buscar_produto_inexistente(cardapio):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.buscar_produto(9999)


def test_atualizar_produto_troca_dados_e_categoria(cardapio, categoria, produto):
    bebidas = cardapio.criar_categoria("Bebidas")
    atualizado = cardapio.atualizar_produto(
        produto.id, "X-Burger Duplo", Decimal("24.90"), Decimal("9.10"), bebidas.id, "Dois hambúrgueres"
    )

    assert atualizado.nome == "X-Burger Duplo"
    assert atualizado.preco == Decimal("24.90")
    assert atualizado.custo == Decimal("9.10")
    assert atualizado.categoria_id == bebidas.id
    assert atualizado.descricao == "Dois hambúrgueres"


def test_atualizar_produto_com_preco_zerado(cardapio, categoria, produto):
    with pytest.raises(RegraDeNegocioError):
        cardapio.atualizar_produto(produto.id, "X-Burger", Decimal("0.00"), Decimal("1.00"), categoria.id)


def test_atualizar_produto_com_custo_negativo(cardapio, categoria, produto):
    with pytest.raises(RegraDeNegocioError):
        cardapio.atualizar_produto(produto.id, "X-Burger", Decimal("10.00"), Decimal("-1.00"), categoria.id)


def test_atualizar_produto_com_nome_vazio(cardapio, categoria, produto):
    with pytest.raises(RegraDeNegocioError):
        cardapio.atualizar_produto(produto.id, " ", Decimal("10.00"), Decimal("1.00"), categoria.id)


def test_atualizar_produto_com_categoria_inexistente(cardapio, produto):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.atualizar_produto(produto.id, "X-Burger", Decimal("10.00"), Decimal("1.00"), 9999)


def test_atualizar_produto_inexistente(cardapio, categoria):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.atualizar_produto(9999, "X-Burger", Decimal("10.00"), Decimal("1.00"), categoria.id)


def test_atualizar_produto_exige_gerente(cardapio, categoria, produto, como_atendente):
    with pytest.raises(AcessoNegadoError):
        cardapio.atualizar_produto(produto.id, "X-Burger", Decimal("10.00"), Decimal("1.00"), categoria.id)


def test_desativar_produto_e_soft(cardapio, produto):
    desativado = cardapio.desativar_produto(produto.id)

    assert desativado.ativo is False
    assert cardapio.buscar_produto(produto.id) is not None


def test_desativar_produto_ja_desativado(cardapio, produto):
    cardapio.desativar_produto(produto.id)
    with pytest.raises(RegraDeNegocioError):
        cardapio.desativar_produto(produto.id)


def test_desativar_produto_exige_gerente(cardapio, produto, como_atendente):
    with pytest.raises(AcessoNegadoError):
        cardapio.desativar_produto(produto.id)


def test_excluir_produto_nunca_vendido(cardapio, categoria):
    agua = cardapio.criar_produto("Água", Decimal("5.00"), categoria.id)
    cardapio.excluir_produto(agua.id)

    assert cardapio.listar_produtos() == []


def test_excluir_produto_ja_vendido(cardapio, uow, gerente, caixa_aberto, produto):
    vender(uow, gerente, caixa_aberto, produto)

    with pytest.raises(RegraDeNegocioError):
        cardapio.excluir_produto(produto.id)


def test_excluir_produto_que_e_combo(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    cardapio.associar_componente(combo.id, produto.id, 1)

    with pytest.raises(RegraDeNegocioError):
        cardapio.excluir_produto(combo.id)


def test_excluir_produto_que_e_componente_de_combo(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    cardapio.associar_componente(combo.id, produto.id, 1)

    with pytest.raises(RegraDeNegocioError):
        cardapio.excluir_produto(produto.id)


def test_excluir_produto_inexistente(cardapio):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.excluir_produto(9999)


def test_excluir_produto_exige_gerente(cardapio, produto, como_atendente):
    with pytest.raises(AcessoNegadoError):
        cardapio.excluir_produto(produto.id)


# ----------------------------------------------------------------------
# Combos (§3.3 — um único nível de composição)
# ----------------------------------------------------------------------


def test_associar_componente_marca_o_produto_como_combo(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    item = cardapio.associar_componente(combo.id, produto.id, 2)

    assert item.id is not None
    assert item.combo_id == combo.id
    assert item.produto_id == produto.id
    assert item.quantidade == 2
    assert cardapio.buscar_produto(combo.id).is_combo is True


def test_associar_componente_a_si_mesmo(cardapio, categoria, produto):
    with pytest.raises(RegraDeNegocioError):
        cardapio.associar_componente(produto.id, produto.id, 1)


def test_associar_combo_dentro_de_outro_combo(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    cardapio.associar_componente(combo.id, produto.id, 1)
    outro = cardapio.criar_produto("Combo Família", Decimal("80.00"), categoria.id)

    with pytest.raises(RegraDeNegocioError):
        cardapio.associar_componente(outro.id, combo.id, 1)


def test_associar_componente_a_produto_que_ja_e_item_de_outro_combo(cardapio, categoria, produto):
    """Sem esta trava, A conteria B e B conteria C — dois níveis de composição."""
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    cardapio.associar_componente(combo.id, produto.id, 1)
    refrigerante = cardapio.criar_produto("Refrigerante", Decimal("6.00"), categoria.id)

    with pytest.raises(RegraDeNegocioError):
        cardapio.associar_componente(produto.id, refrigerante.id, 1)


def test_associar_o_mesmo_componente_duas_vezes(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    cardapio.associar_componente(combo.id, produto.id, 1)

    with pytest.raises(RegraDeNegocioError):
        cardapio.associar_componente(combo.id, produto.id, 1)

    assert len(cardapio.listar_componentes(combo.id)) == 1


def test_associar_componente_com_quantidade_zero(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    with pytest.raises(RegraDeNegocioError):
        cardapio.associar_componente(combo.id, produto.id, 0)


def test_associar_componente_com_quantidade_negativa(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    with pytest.raises(RegraDeNegocioError):
        cardapio.associar_componente(combo.id, produto.id, -1)


def test_associar_componente_com_quantidade_nao_inteira(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    with pytest.raises(RegraDeNegocioError):
        cardapio.associar_componente(combo.id, produto.id, "2")


def test_associar_componente_com_combo_inexistente(cardapio, produto):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.associar_componente(9999, produto.id, 1)


def test_associar_componente_inexistente(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.associar_componente(combo.id, 9999, 1)


def test_associar_componente_exige_gerente(cardapio, categoria, produto, como_atendente):
    with pytest.raises(AcessoNegadoError):
        cardapio.associar_componente(produto.id, 1, 1)


def test_listar_componentes_do_combo(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    refrigerante = cardapio.criar_produto("Refrigerante", Decimal("6.00"), categoria.id)
    cardapio.associar_componente(combo.id, produto.id, 1)
    cardapio.associar_componente(combo.id, refrigerante.id, 2)

    componentes = cardapio.listar_componentes(combo.id)

    assert [c.produto_id for c in componentes] == [produto.id, refrigerante.id]
    assert [c.quantidade for c in componentes] == [1, 2]


def test_listar_componentes_de_produto_sem_combo(cardapio, produto):
    assert cardapio.listar_componentes(produto.id) == []


def test_listar_componentes_de_produto_inexistente(cardapio):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.listar_componentes(9999)


def test_remover_ultimo_componente_desfaz_o_combo(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    item = cardapio.associar_componente(combo.id, produto.id, 1)

    cardapio.remover_componente(item.id)

    assert cardapio.listar_componentes(combo.id) == []
    assert cardapio.buscar_produto(combo.id).is_combo is False


def test_remover_componente_mantendo_o_combo_com_os_outros(cardapio, categoria, produto):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    refrigerante = cardapio.criar_produto("Refrigerante", Decimal("6.00"), categoria.id)
    item = cardapio.associar_componente(combo.id, produto.id, 1)
    cardapio.associar_componente(combo.id, refrigerante.id, 1)

    cardapio.remover_componente(item.id)

    assert [c.produto_id for c in cardapio.listar_componentes(combo.id)] == [refrigerante.id]
    assert cardapio.buscar_produto(combo.id).is_combo is True


def test_remover_componente_inexistente(cardapio):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.remover_componente(9999)


def test_remover_componente_exige_gerente(cardapio, categoria, produto, auth, atendente):
    combo = cardapio.criar_produto("Combo Lanche", Decimal("30.00"), categoria.id)
    item = cardapio.associar_componente(combo.id, produto.id, 1)
    auth.login(PIN_ATENDENTE)

    with pytest.raises(AcessoNegadoError):
        cardapio.remover_componente(item.id)


# ----------------------------------------------------------------------
# Impressoras
# ----------------------------------------------------------------------


def test_criar_impressora(cardapio):
    impressora = cardapio.criar_impressora("  Cozinha  ")

    assert impressora.id is not None
    assert impressora.nome == "Cozinha"


def test_criar_impressora_com_nome_repetido(cardapio):
    cardapio.criar_impressora("Cozinha")
    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_impressora("Cozinha")


def test_criar_impressora_com_nome_vazio(cardapio):
    with pytest.raises(RegraDeNegocioError):
        cardapio.criar_impressora("  ")


def test_criar_impressora_exige_gerente(cardapio, como_atendente):
    with pytest.raises(AcessoNegadoError):
        cardapio.criar_impressora("Cozinha")


def test_listar_impressoras(cardapio):
    cardapio.criar_impressora("Cozinha")
    cardapio.criar_impressora("Bar")

    assert [i.nome for i in cardapio.listar_impressoras()] == ["Cozinha", "Bar"]


def test_buscar_impressora_por_id(cardapio):
    impressora = cardapio.criar_impressora("Cozinha")
    assert cardapio.buscar_impressora(impressora.id) is impressora


def test_buscar_impressora_inexistente(cardapio):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.buscar_impressora(9999)
