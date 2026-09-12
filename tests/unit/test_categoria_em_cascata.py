"""Excluir a categoria inteira, com itens e subcategorias dentro. §9.14.

Pedido do Vitor: "deixando excluir toda uma categoria por mais que tenha itens e
subclasses, mas deverá gerar uma tela de senha de pin exigindo a senha master".
É o §9.13 um nível acima — e o nível acima tem uma diferença que decide o
desenho inteiro:

**`produtos.categoria_id` é NOT NULL.** A FK do produto para a SUBcategoria é
anulável (`ondelete="SET NULL"`), então a subdivisão sempre sai do banco. A da
categoria não é: um produto que precisa sobreviver à exclusão (porque já foi
vendido, e apagá-lo arrancaria o item da comanda e o cupom junto) tem que
continuar apontando para alguma categoria. Por isso a cascata da categoria tem
DOIS finais, e é isso que esta suíte cobra:

* **nada a guardar** → a categoria é apagada de verdade, e as subdivisões vão
  junto pelo `cascade` da relação;
* **algo a guardar** → a categoria fica MARCADA (`arquivado`), some de todas as
  telas, e é a linha dela que sustenta a venda antiga.

A outra coisa que se cobra aqui é o nome: `categorias.nome` é `UNIQUE`, e a
categoria guardada continuaria ocupando "Lanches" — que é justamente o nome que
o gerente vai querer recadastrar ao reorganizar o cardápio.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from tests.conftest import PIN_ATENDENTE


@pytest.fixture
def cardapio(uow, auth, gerente):
    return CardapioService(uow, auth)


@pytest.fixture
def comandas(uow, auth):
    return ComandaService(uow, auth)


@pytest.fixture
def lanches(cardapio):
    return cardapio.criar_categoria("Lanches")


def _vender(uow, gerente, caixa_aberto, produto):
    comanda = uow.comandas.salvar(
        Comanda(
            aberta_em=datetime(2026, 9, 12, 12, 0),
            usuario_id=gerente.id,
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


# ---------------------------------------------------------------------------
# A exclusão simples só passa com a categoria VAZIA
# ---------------------------------------------------------------------------


def test_categoria_vazia_sai_num_clique(cardapio, lanches):
    cardapio.excluir_categoria(lanches.id)

    assert cardapio.listar_categorias() == []


def test_categoria_com_produto_e_recusada_com_o_numero(cardapio, lanches):
    cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)

    with pytest.raises(RegraDeNegocioError, match="ela tem 1 produto"):
        cardapio.excluir_categoria(lanches.id)

    assert [c.nome for c in cardapio.listar_categorias()] == ["Lanches"]


def test_categoria_com_subcategoria_e_recusada(cardapio, lanches):
    """Mudou no §9.14: a subdivisão ia junto em silêncio, num clique."""
    cardapio.criar_subcategoria(lanches.id, "Podrão")

    with pytest.raises(RegraDeNegocioError, match="ela tem 1 subcategoria"):
        cardapio.excluir_categoria(lanches.id)


def test_a_recusa_soma_as_duas_coisas(cardapio, lanches):
    """O gerente precisa do tamanho do trabalho, e ele tem duas parcelas."""
    cardapio.criar_subcategoria(lanches.id, "Podrão")
    cardapio.criar_subcategoria(lanches.id, "Artesanal")
    cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)

    with pytest.raises(RegraDeNegocioError, match="ela tem 1 produto e 2 subcategorias"):
        cardapio.excluir_categoria(lanches.id)


def test_contar_conteudo_e_o_par_que_a_tela_pergunta_antes(cardapio, lanches):
    assert cardapio.contar_conteudo_da_categoria(lanches.id) == (0, 0)

    cardapio.criar_subcategoria(lanches.id, "Podrão")
    cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)

    assert cardapio.contar_conteudo_da_categoria(lanches.id) == (1, 1)


# ---------------------------------------------------------------------------
# A cascata: o final em que tudo sai do banco
# ---------------------------------------------------------------------------


def test_sem_venda_registrada_a_categoria_sai_de_verdade(cardapio, lanches, uow):
    """O caso limpo: nada tem histórico, nada precisa ficar."""
    podrao = cardapio.criar_subcategoria(lanches.id, "Podrão")
    cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id)
    cardapio.criar_produto("X Egg", Decimal("15.00"), lanches.id)

    resultado = cardapio.excluir_categoria_em_cascata(lanches.id)

    assert (resultado.excluidos, resultado.arquivados) == (2, 0)
    assert resultado.grupo_arquivado is False
    assert uow.categorias.buscar_por_id(lanches.id) is None
    assert uow.subcategorias.listar_todos() == []
    assert uow.produtos.listar_todos() == []


# ---------------------------------------------------------------------------
# A cascata: o final em que a categoria precisa ficar
# ---------------------------------------------------------------------------


def test_com_venda_registrada_a_categoria_fica_guardada(
    cardapio, lanches, uow, gerente, caixa_aberto
):
    """A diferença para a subcategoria, medida.

    O produto vendido não pode sair do banco, e `produtos.categoria_id` é NOT
    NULL — então a linha da categoria continua, marcada. O que o gerente vê é o
    mesmo: some da tela.
    """
    vendido = cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)
    item = _vender(uow, gerente, caixa_aberto, vendido)

    resultado = cardapio.excluir_categoria_em_cascata(lanches.id)

    assert (resultado.excluidos, resultado.arquivados) == (0, 1)
    assert resultado.grupo_arquivado is True
    guardada = uow.categorias.buscar_por_id(lanches.id)
    assert guardada is not None and guardada.arquivado is True
    assert cardapio.listar_categorias() == []
    assert cardapio.listar_categorias_ativas() == []
    # A venda continua inteira, apontando para o produto e para a categoria.
    assert uow.itens.buscar_por_id(item.id).produto_id == vendido.id
    guardado = uow.produtos.buscar_por_id(vendido.id)
    assert guardado.categoria_id == lanches.id
    # `ativo` desce junto com `arquivado`: é `ativo` que `lancar_item` confere,
    # e um item excluído não pode ser lançável por caminho nenhum.
    assert (guardado.arquivado, guardado.ativo) == (True, False)


def test_o_que_nao_tem_venda_sai_mesmo_quando_a_categoria_fica(
    cardapio, lanches, uow, gerente, caixa_aberto
):
    """Os dois destinos convivem na mesma cascata, produto a produto."""
    vendido = cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)
    limpo = cardapio.criar_produto("X Egg", Decimal("15.00"), lanches.id)
    _vender(uow, gerente, caixa_aberto, vendido)

    resultado = cardapio.excluir_categoria_em_cascata(lanches.id)

    assert (resultado.excluidos, resultado.arquivados) == (1, 1)
    assert uow.produtos.buscar_por_id(limpo.id) is None
    assert uow.produtos.buscar_por_id(vendido.id).arquivado is True


def test_as_subcategorias_saem_mesmo_com_a_categoria_guardada(
    cardapio, lanches, uow, gerente, caixa_aberto
):
    """Subdivisão de categoria invisível não é alcançável por tela nenhuma.

    O produto guardado perde a subdivisão pelo `ondelete="SET NULL"` e mantém a
    categoria, que é o que a FK exige.
    """
    podrao = cardapio.criar_subcategoria(lanches.id, "Podrão")
    vendido = cardapio.criar_produto(
        "X Burguer", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id
    )
    _vender(uow, gerente, caixa_aberto, vendido)

    cardapio.excluir_categoria_em_cascata(lanches.id)

    assert uow.subcategorias.listar_todos() == []
    guardado = uow.produtos.buscar_por_id(vendido.id)
    assert guardado.subcategoria_id is None
    assert guardado.categoria_id == lanches.id


def test_a_categoria_guardada_libera_o_nome(cardapio, lanches, uow, gerente, caixa_aberto):
    """`categorias.nome` é UNIQUE, e reorganizar cardápio é recadastrar nome.

    Sem liberar, excluir "Lanches" e cadastrar "Lanches" de novo esbarraria numa
    linha que ninguém vê, com um erro que ninguém entende. O marcador leva o id,
    então é único mesmo que o mesmo nome seja excluído duas vezes.
    """
    vendido = cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)
    _vender(uow, gerente, caixa_aberto, vendido)

    cardapio.excluir_categoria_em_cascata(lanches.id)
    nova = cardapio.criar_categoria("Lanches")

    assert uow.categorias.buscar_por_id(lanches.id).nome == f"Lanches [excluída #{lanches.id}]"
    assert [c.nome for c in cardapio.listar_categorias()] == ["Lanches"]
    assert nova.id != lanches.id


def test_o_nome_guardado_nao_estoura_a_coluna(cardapio, uow, gerente, caixa_aberto):
    """A coluna é String(80): nome longo perde o fim do NOME, não o marcador —
    é o marcador que dá a unicidade."""
    comprida = cardapio.criar_categoria("C" * 80)
    vendido = cardapio.criar_produto("X Burguer", Decimal("13.00"), comprida.id)
    _vender(uow, gerente, caixa_aberto, vendido)

    cardapio.excluir_categoria_em_cascata(comprida.id)

    guardada = uow.categorias.buscar_por_id(comprida.id)
    assert len(guardada.nome) == 80
    assert guardada.nome.endswith(f"[excluída #{comprida.id}]")


def test_a_categoria_guardada_nao_volta(cardapio, lanches, uow, gerente, caixa_aberto):
    """Arquivada não é desativada: não há como reativá-la, e nem faria sentido —
    os itens dela continuam arquivados."""
    vendido = cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)
    _vender(uow, gerente, caixa_aberto, vendido)
    cardapio.excluir_categoria_em_cascata(lanches.id)

    for chamada in (
        lambda: cardapio.ativar_categoria(lanches.id),
        lambda: cardapio.desativar_categoria(lanches.id),
        lambda: cardapio.editar_categoria(lanches.id, "Lanches de novo"),
        lambda: cardapio.criar_subcategoria(lanches.id, "Podrão"),
    ):
        with pytest.raises(RecursoNaoEncontradoError, match="foi excluída do cardápio"):
            chamada()


def test_a_guardada_sai_do_seletor_mesmo_marcada_como_ativa(cardapio, lanches, uow):
    """As duas marcas são redundantes DE PROPÓSITO, e este teste é o que prova.

    A cascata desliga `ativo` junto com `arquivado`, então no caminho normal
    qualquer uma das duas já tiraria a categoria do seletor de cadastro. A
    condição de `arquivado` em `listar_ativas` existe para o caso de as duas
    divergirem — e sem este teste ela seria código que nenhuma mutação reprova,
    ou seja, código que ninguém saberia se ainda funciona. Mesmo par (e mesma
    razão) do `Produto.arquivado` no §9.13.
    """
    lanches.arquivado = True
    uow.categorias.salvar(lanches)
    uow.commit()

    assert uow.categorias.buscar_por_id(lanches.id).ativo is True, "premissa: só a marca"
    assert cardapio.listar_categorias_ativas() == []


def test_nao_se_cadastra_produto_dentro_de_categoria_guardada(
    cardapio, lanches, uow, gerente, caixa_aberto
):
    """O seletor do cadastro já não a oferece; esta é a trava do service, para o
    instantâneo de um formulário aberto antes da exclusão."""
    vendido = cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)
    _vender(uow, gerente, caixa_aberto, vendido)
    cardapio.excluir_categoria_em_cascata(lanches.id)

    with pytest.raises(RecursoNaoEncontradoError, match="foi excluída do cardápio"):
        cardapio.criar_produto("X Novo", Decimal("10.00"), lanches.id)


def test_o_produto_guardado_nao_pode_ser_vendido(
    cardapio, comandas, lanches, uow, gerente, caixa_aberto, mesa
):
    vendido = cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)
    _vender(uow, gerente, caixa_aberto, vendido)
    cardapio.excluir_categoria_em_cascata(lanches.id)
    comanda = comandas.abrir_por_mesa(mesa.id)

    with pytest.raises(RegraDeNegocioError, match="foi excluído do cardápio"):
        comandas.lancar_item(comanda.id, vendido.id, 1)


def test_a_categoria_guardada_some_dos_kpis(cardapio, lanches, uow, gerente, caixa_aberto):
    outra = cardapio.criar_categoria("Bebidas")
    cardapio.criar_produto("Coca", Decimal("8.00"), outra.id)
    vendido = cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)
    _vender(uow, gerente, caixa_aberto, vendido)

    cardapio.excluir_categoria_em_cascata(lanches.id)

    resumo = cardapio.resumo_do_cardapio()
    assert (resumo.categorias, resumo.produtos) == (1, 1)


def test_a_categoria_guardada_some_da_tela_de_impressoras(
    cardapio, lanches, uow, gerente, caixa_aberto
):
    """A regra de ouro pelo avesso: a impressora não é tocada, e a categoria
    arquivada para de aparecer como vinculada a ela."""
    impressora = cardapio.criar_impressora("Cozinha")
    cardapio.associar_impressora(lanches.id, impressora.id)
    vendido = cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)
    _vender(uow, gerente, caixa_aberto, vendido)

    cardapio.excluir_categoria_em_cascata(lanches.id)

    assert cardapio.listar_categorias_da_impressora(impressora.id) == []
    assert uow.categorias.buscar_por_id(lanches.id).impressora_id == impressora.id


def test_a_cascata_da_categoria_exige_gerente(cardapio, lanches, auth, atendente):
    """A Senha Master é barreira de TELA (§9.10); o perfil continua no service."""
    auth.login_como(atendente.id, PIN_ATENDENTE)

    with pytest.raises(AcessoNegadoError):
        cardapio.excluir_categoria_em_cascata(lanches.id)


def test_a_cascata_nao_toca_em_outra_categoria(cardapio, lanches):
    bebidas = cardapio.criar_categoria("Bebidas")
    cardapio.criar_produto("Coca", Decimal("8.00"), bebidas.id)
    cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id)

    cardapio.excluir_categoria_em_cascata(lanches.id)

    assert [c.nome for c in cardapio.listar_categorias()] == ["Bebidas"]
    assert [p.nome for p in cardapio.listar_produtos()] == ["Coca"]
