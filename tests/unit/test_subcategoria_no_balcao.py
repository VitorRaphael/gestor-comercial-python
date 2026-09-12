"""A subcategoria passou a decidir o que se vende — e a poder levar os itens. §9.13.

Duas mudanças de regra do §9.13 moram aqui, e as duas **revertem decisões
escritas** do §9.9. Por isso cada uma tem teste próprio dizendo o que vale
agora:

1. **desativar a subdivisão tira os produtos dela do balcão.** O §9.9 dizia que
   subcategoria é só organização e que desativar não significaria nada; a
   pedido do Vitor ela virou a mesma regra da categoria, um nível abaixo. O que
   guarda a regra é a consulta de lançamento, num lugar só
   (`ProdutoRepository._vendavel`), porque é ela que todas as telas de venda
   usam;

2. **excluir uma subdivisão com itens dentro é recusado** — e a Senha Master
   libera a cascata. O §9.9 soltava os produtos em "Sem subcategoria"; agora
   isso exige decisão explícita. Na cascata, quem nunca foi vendido sai do
   banco e quem tem histórico é ARQUIVADO: some de todas as telas e a venda
   passada continua inteira, que é a única forma de atender "exclua tudo" sem
   reescrever o passado.

O que NÃO mudou, e é varrido aqui também: a impressora continua saindo da
categoria (§9.8). Desativar uma subdivisão não reconfigura bobina — ela apenas
deixa de ter item para mandar.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.exceptions import AcessoNegadoError, RegraDeNegocioError
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


@pytest.fixture
def podrao(cardapio, lanches):
    return cardapio.criar_subcategoria(lanches.id, "Podrão")


def _vender(uow, gerente, caixa_aberto, produto):
    """Deixa o produto com histórico: é o que decide entre apagar e arquivar."""
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


def _nomes(produtos) -> list[str]:
    return [p.nome for p in produtos]


# ---------------------------------------------------------------------------
# Desativar a subdivisão é regra de venda
# ---------------------------------------------------------------------------


def test_a_subcategoria_nasce_vendendo(cardapio, podrao):
    """Subdivisão recém-criada não pode nascer fora do balcão, calada."""
    assert podrao.ativo is True


def test_desativar_a_subcategoria_tira_os_produtos_dela_do_lancamento(
    cardapio, lanches, podrao
):
    """O pedido, na sua forma mais curta: "hoje não tem podrão".

    Sem isto, tirar um grupo do balcão exigiria desativar item por item — e
    devolvê-lo, reativar item por item lembrando quais eram.
    """
    cardapio.criar_produto("X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id)
    cardapio.criar_produto("X Egg", Decimal("15.00"), lanches.id)

    cardapio.desativar_subcategoria(podrao.id)

    assert _nomes(cardapio.listar_produtos_para_lancamento()) == ["X Egg"]
    assert _nomes(cardapio.listar_produtos_ativos()) == ["X Egg"]


def test_o_produto_sem_subcategoria_continua_vendendo(cardapio, lanches, podrao):
    """`subcategoria_id IS NULL` é o estado normal de quem ainda não foi
    classificado, e não pode custar a venda dele — é por isso que a consulta usa
    `outerjoin` e não `join`."""
    cardapio.criar_produto("X Egg", Decimal("15.00"), lanches.id)
    cardapio.desativar_subcategoria(podrao.id)

    assert _nomes(cardapio.listar_produtos_para_lancamento()) == ["X Egg"]


def test_o_produto_continua_inteiro_no_cardapio(cardapio, lanches, podrao):
    """Desativar não é excluir: o item some do balcão e fica na tela de cadastro,
    com preço, custo e classificação, esperando a subdivisão voltar."""
    produto = cardapio.criar_produto(
        "X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id
    )

    cardapio.desativar_subcategoria(podrao.id)

    guardado = cardapio.buscar_produto(produto.id)
    assert _nomes(cardapio.listar_produtos()) == ["X Podrão"]
    assert guardado.ativo is True
    assert guardado.subcategoria_id == podrao.id
    assert guardado.preco == Decimal("13.00")


def test_ativar_devolve_os_produtos_ao_balcao(cardapio, lanches, podrao):
    cardapio.criar_produto("X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id)
    cardapio.desativar_subcategoria(podrao.id)

    cardapio.ativar_subcategoria(podrao.id)

    assert _nomes(cardapio.listar_produtos_para_lancamento()) == ["X Podrão"]


def test_ativar_o_grupo_nao_desfaz_a_decisao_tomada_item_a_item(cardapio, lanches, podrao):
    """Reativar a subdivisão devolve os que ESTAVAM à venda.

    Um produto desativado sozinho ("acabou o pão") continua fora: religar o
    grupo não pode desfazer, calado, o que alguém decidiu item a item.
    """
    vendido = cardapio.criar_produto(
        "X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id
    )
    sem_pao = cardapio.criar_produto(
        "X Tudo", Decimal("16.00"), lanches.id, subcategoria_id=podrao.id
    )
    cardapio.desativar_produto(sem_pao.id)
    cardapio.desativar_subcategoria(podrao.id)

    cardapio.ativar_subcategoria(podrao.id)

    assert _nomes(cardapio.listar_produtos_para_lancamento()) == [vendido.nome]


def test_desativar_duas_vezes_e_recusado(cardapio, podrao):
    """Sem isto, um duplo clique no rodapé viraria dois commits e duas recargas."""
    cardapio.desativar_subcategoria(podrao.id)

    with pytest.raises(RegraDeNegocioError, match="já está desativada"):
        cardapio.desativar_subcategoria(podrao.id)


def test_ativar_o_que_ja_esta_ativo_e_recusado(cardapio, podrao):
    with pytest.raises(RegraDeNegocioError, match="já está ativa"):
        cardapio.ativar_subcategoria(podrao.id)


def test_desativar_subcategoria_exige_gerente(cardapio, podrao, auth, atendente):
    auth.login_como(atendente.id, PIN_ATENDENTE)

    with pytest.raises(AcessoNegadoError):
        cardapio.desativar_subcategoria(podrao.id)


def test_desativar_a_subcategoria_nao_encosta_na_impressora(cardapio, lanches, podrao):
    """A REGRA DE OURO do §9.8 sobre a regra nova.

    A subdivisão ganhou poder de sumir com produto do balcão, e não ganhou
    nenhum sobre a bobina: quem decide a impressora continua sendo a categoria.
    """
    impressora = cardapio.criar_impressora("Cozinha")
    cardapio.associar_impressora(lanches.id, impressora.id)
    produto = cardapio.criar_produto(
        "X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id
    )

    cardapio.desativar_subcategoria(podrao.id)

    assert cardapio.buscar_produto(produto.id).categoria.impressora_id == impressora.id
    assert cardapio.buscar_categoria(lanches.id).impressora_id == impressora.id


# ---------------------------------------------------------------------------
# A cascata da Senha Master
# ---------------------------------------------------------------------------


def test_a_cascata_apaga_quem_nunca_foi_vendido(cardapio, lanches, podrao, uow):
    """Produto sem histórico não deixa buraco nenhum: sai do banco de verdade."""
    cardapio.criar_produto("X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id)

    resultado = cardapio.excluir_subcategoria_em_cascata(podrao.id)

    assert (resultado.excluidos, resultado.arquivados) == (1, 0)
    assert cardapio.listar_produtos() == []
    assert cardapio.listar_subcategorias(lanches.id) == []


def test_a_cascata_arquiva_quem_ja_tem_venda_registrada(
    cardapio, lanches, podrao, uow, gerente, caixa_aberto
):
    """O caso que obrigou a existir uma marca em vez de um `DELETE`.

    Apagar a linha arrancaria o item da comanda, o total do turno e o cupom que
    já saiu na bobina. A marca some com o produto de todas as telas e deixa o
    passado inteiro — que é o que "exclua tudo" pode significar sem mentir.
    """
    produto = cardapio.criar_produto(
        "X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id
    )
    item = _vender(uow, gerente, caixa_aberto, produto)

    resultado = cardapio.excluir_subcategoria_em_cascata(podrao.id)

    assert (resultado.excluidos, resultado.arquivados) == (0, 1)
    guardado = cardapio.buscar_produto(produto.id)
    assert guardado.arquivado is True
    assert guardado.ativo is False
    # A venda continua apontando para ele, com o preço congelado do dia.
    assert uow.itens.buscar_por_id(item.id).produto_id == produto.id
    assert uow.itens.buscar_por_id(item.id).preco_unit_congelado == Decimal("13.00")


def test_o_arquivado_some_do_cardapio_e_do_lancamento(
    cardapio, lanches, podrao, uow, gerente, caixa_aberto
):
    """A diferença entre `arquivado` e `ativo=False`, medida.

    Um produto meramente desativado CONTINUA no Cardápio (é assim que se
    reativa); o arquivado não aparece em tela nenhuma, nem no KPI do topo.
    """
    produto = cardapio.criar_produto(
        "X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id
    )
    cardapio.criar_produto("X Egg", Decimal("15.00"), lanches.id)
    _vender(uow, gerente, caixa_aberto, produto)

    cardapio.excluir_subcategoria_em_cascata(podrao.id)

    assert _nomes(cardapio.listar_produtos()) == ["X Egg"]
    assert _nomes(cardapio.listar_produtos_para_lancamento()) == ["X Egg"]
    assert cardapio.resumo_do_cardapio().produtos == 1


def test_o_arquivado_nao_pode_ser_lancado_nem_por_tela_velha(
    cardapio, comandas, lanches, podrao, uow, gerente, caixa_aberto, mesa
):
    """O cinto do service, para o instantâneo de um modal já aberto.

    O modal "Adicionar item" monta a lista na abertura e não volta ao banco
    (§9.4). Um produto arquivado no meio do turno continuaria clicável naquele
    instantâneo — e é `lancar_item` quem barra.
    """
    produto = cardapio.criar_produto(
        "X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id
    )
    _vender(uow, gerente, caixa_aberto, produto)
    cardapio.excluir_subcategoria_em_cascata(podrao.id)
    comanda = comandas.abrir_por_mesa(mesa.id)

    with pytest.raises(RegraDeNegocioError, match="foi excluído do cardápio"):
        comandas.lancar_item(comanda.id, produto.id, 1)


def test_o_arquivado_sai_do_balcao_mesmo_marcado_como_ativo(cardapio, lanches, podrao, uow):
    """As duas marcas são redundantes DE PROPÓSITO, e este teste é o que prova.

    A cascata desliga `ativo` junto com `arquivado`, então no caminho normal
    qualquer uma das duas já tiraria o produto do balcão. A condição de
    `arquivado` na consulta de venda existe para o caso de as duas divergirem —
    e sem este teste ela seria código que nenhuma mutação reprova, ou seja,
    código que ninguém saberia se ainda funciona.
    """
    produto = cardapio.criar_produto(
        "X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id
    )
    produto.arquivado = True
    uow.produtos.salvar(produto)
    uow.commit()

    assert cardapio.buscar_produto(produto.id).ativo is True, "premissa: só a marca de arquivo"
    assert cardapio.listar_produtos_para_lancamento() == []
    assert cardapio.listar_produtos_ativos() == []


def test_o_arquivado_nao_pode_ser_reativado(cardapio, lanches, podrao, uow, gerente, caixa_aberto):
    """Arquivado não volta: a linha só continua no banco para o passado.

    Sem a recusa, o único caminho que ainda enxerga um arquivado — uma tela
    aberta antes da cascata, com o instantâneo velho — o traria de volta ao
    balcão calado.
    """
    produto = cardapio.criar_produto(
        "X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id
    )
    _vender(uow, gerente, caixa_aberto, produto)
    cardapio.excluir_subcategoria_em_cascata(podrao.id)

    with pytest.raises(RegraDeNegocioError, match="não pode ser reativado"):
        cardapio.ativar_produto(produto.id)


def test_a_cascata_nao_toca_em_produto_de_fora_da_subdivisao(cardapio, lanches, podrao):
    """O alcance da cascata é a subdivisão, e só ela."""
    cardapio.criar_produto("X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id)
    vizinho = cardapio.criar_produto("X Egg", Decimal("15.00"), lanches.id)

    cardapio.excluir_subcategoria_em_cascata(podrao.id)

    assert _nomes(cardapio.listar_produtos()) == [vizinho.nome]
    assert cardapio.buscar_produto(vizinho.id).arquivado is False


def test_a_cascata_arquiva_quem_esta_preso_a_um_combo(cardapio, lanches, podrao):
    """Combo é o outro vínculo que não pode ser arrancado.

    Apagar um componente desmontaria a composição de outro item do cardápio que
    ninguém mandou excluir — a mesma regra que `excluir_produto` já aplicava, só
    que aqui ela vira "arquiva" em vez de "recusa".
    """
    componente = cardapio.criar_produto(
        "Batata", Decimal("8.00"), lanches.id, subcategoria_id=podrao.id
    )
    combo = cardapio.criar_produto("Combo do dia", Decimal("25.00"), lanches.id)
    cardapio.associar_componente(combo.id, componente.id, 1)

    resultado = cardapio.excluir_subcategoria_em_cascata(podrao.id)

    assert (resultado.excluidos, resultado.arquivados) == (0, 1)
    assert cardapio.buscar_produto(componente.id).arquivado is True
    assert [c.produto_id for c in cardapio.listar_componentes(combo.id)] == [componente.id]


def test_a_cascata_exige_gerente(cardapio, podrao, auth, atendente):
    """A Senha Master é barreira de TELA (§9.10); o perfil continua sendo do service."""
    auth.login_como(atendente.id, PIN_ATENDENTE)

    with pytest.raises(AcessoNegadoError):
        cardapio.excluir_subcategoria_em_cascata(podrao.id)


def test_contar_produtos_da_subcategoria_e_o_numero_que_a_tela_avisa(
    cardapio, lanches, podrao
):
    """A tela pergunta isto antes de excluir, para escolher entre a confirmação
    simples e o aviso com a saída pela Senha Master."""
    assert cardapio.contar_produtos_da_subcategoria(podrao.id) == 0

    cardapio.criar_produto("X Podrão", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id)
    cardapio.criar_produto("X Tudo", Decimal("16.00"), lanches.id, subcategoria_id=podrao.id)

    assert cardapio.contar_produtos_da_subcategoria(podrao.id) == 2
