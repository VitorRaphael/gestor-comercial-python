"""Excluir um produto que tem histórico: arquivar, com a Senha Master. §9.18.

Até o §9.17 a exclusão de um produto vendido (ou preso a um combo) só era
RECUSADA, com "Desative-o" — e o desativado fica no Cardápio para sempre, com
selo. Decisão do Vitor, perguntada antes de começar:

* **sem histórico** → `excluir_produto`, DELETE físico, depois da confirmação
  simples do cartão (não mudou, e esta suíte não o repete);
* **com histórico** → `arquivar_produto`, depois da Senha Master conferida pela
  TELA: o produto some de todas as telas e do balcão, e a venda passada continua
  apontando para a linha dele;
* **preso a combo** → a amarração sai ANTES de arquivar, dos dois lados, "para
  não deixar referências ativas quebradas".

A última é onde este caminho difere das cascatas do §9.13/§9.14, que arquivam o
componente sem desfazer a composição — e o teste que diz isso em voz alta está
no fim do arquivo.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.services.cardapio_service import (
    CardapioService,
    VinculosDoProduto,
    conteudo_da_categoria,
    quantidades_do_conteudo,
)
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
def lanches(cardapio):
    return cardapio.criar_categoria("Lanches")


@pytest.fixture
def batata(cardapio, lanches):
    return cardapio.criar_produto("Batata", Decimal("12.00"), lanches.id)


def _vender(uow, gerente, caixa_aberto, produto):
    comanda = uow.comandas.salvar(
        Comanda(
            aberta_em=datetime(2026, 9, 14, 12, 0),
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
# A pergunta que a tela faz antes
# ---------------------------------------------------------------------------


def test_produto_sem_vinculo_nenhum_nao_tem_historico(cardapio, batata):
    vinculos = cardapio.vinculos_do_produto(batata.id)

    assert vinculos == VinculosDoProduto(vendido=False, combos_que_o_contem=0, componentes=0)
    assert vinculos.tem_historico is False


def test_a_venda_conta_como_historico(cardapio, batata, uow, gerente, caixa_aberto):
    _vender(uow, gerente, caixa_aberto, batata)

    vinculos = cardapio.vinculos_do_produto(batata.id)

    assert (vinculos.vendido, vinculos.tem_historico) == (True, True)


def test_os_dois_lados_do_combo_sao_contados_separados(cardapio, lanches, batata):
    """O cartão diz coisas diferentes para "ele entra em 2 combos" e "ele é um
    combo de 1 componente" — e um mesmo produto pode ser só um dos dois."""
    combo_a = cardapio.criar_produto("Combo A", Decimal("30.00"), lanches.id)
    combo_b = cardapio.criar_produto("Combo B", Decimal("32.00"), lanches.id)
    refri = cardapio.criar_produto("Refri", Decimal("6.00"), lanches.id)
    cardapio.associar_componente(combo_a.id, batata.id, 1)
    cardapio.associar_componente(combo_b.id, batata.id, 2)
    cardapio.associar_componente(combo_a.id, refri.id, 1)

    assert cardapio.vinculos_do_produto(batata.id) == VinculosDoProduto(False, 2, 0)
    assert cardapio.vinculos_do_produto(combo_a.id) == VinculosDoProduto(False, 0, 2)
    assert cardapio.vinculos_do_produto(combo_a.id).tem_historico is True


def test_a_pergunta_de_um_produto_inexistente_e_recusada(cardapio):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.vinculos_do_produto(9999)


@pytest.mark.parametrize(
    ("vinculos", "esperado"),
    [
        (VinculosDoProduto(True, 0, 0), True),
        (VinculosDoProduto(False, 1, 0), True),
        (VinculosDoProduto(False, 0, 1), True),
        (VinculosDoProduto(False, 0, 0), False),
    ],
)
def test_cada_vinculo_sozinho_ja_e_historico(vinculos, esperado):
    assert vinculos.tem_historico is esperado


def test_a_cascata_e_a_tela_usam_a_mesma_definicao_de_historico(cardapio, lanches):
    """`_tem_historico` (a cascata) passou a ler `_vinculos` (a tela): o combo e
    o componente, nenhum dos dois vendido, são guardados pela cascata pelo mesmo
    motivo que fariam o cartão pedir a Senha Master — e o produto solto sai."""
    combo = cardapio.criar_produto("Combo", Decimal("30.00"), lanches.id)
    componente = cardapio.criar_produto("Batata", Decimal("12.00"), lanches.id)
    solto = cardapio.criar_produto("X Egg", Decimal("15.00"), lanches.id)
    cardapio.associar_componente(combo.id, componente.id, 1)
    protegidos = {
        p.id for p in (combo, componente, solto) if cardapio.vinculos_do_produto(p.id).tem_historico
    }

    resultado = cardapio.excluir_categoria_em_cascata(lanches.id)

    assert protegidos == {combo.id, componente.id}
    assert (resultado.excluidos, resultado.arquivados) == (1, 2)


# ---------------------------------------------------------------------------
# O arquivamento
# ---------------------------------------------------------------------------


def test_o_produto_vendido_e_arquivado_e_a_venda_continua_inteira(
    cardapio, batata, uow, gerente, caixa_aberto
):
    item = _vender(uow, gerente, caixa_aberto, batata)

    cardapio.arquivar_produto(batata.id)

    guardado = uow.produtos.buscar_por_id(batata.id)
    # `ativo` desce junto: é o que `lancar_item` confere.
    assert (guardado.arquivado, guardado.ativo) == (True, False)
    assert uow.itens.buscar_por_id(item.id).produto_id == batata.id
    assert cardapio.listar_produtos() == []
    assert cardapio.listar_produtos_ativos() == []
    assert cardapio.listar_produtos_para_lancamento() == []


def test_o_arquivado_sai_dos_kpis(cardapio, batata, lanches, uow, gerente, caixa_aberto):
    cardapio.criar_produto("X Egg", Decimal("15.00"), lanches.id)
    _vender(uow, gerente, caixa_aberto, batata)

    cardapio.arquivar_produto(batata.id)

    assert cardapio.resumo_do_cardapio().produtos == 1


def test_o_arquivado_nao_pode_ser_vendido(
    cardapio, batata, uow, auth, gerente, caixa_aberto, mesa
):
    _vender(uow, gerente, caixa_aberto, batata)
    cardapio.arquivar_produto(batata.id)
    comandas = ComandaService(uow, auth)
    comanda = comandas.abrir_por_mesa(mesa.id)

    with pytest.raises(RegraDeNegocioError, match="foi excluído do cardápio"):
        comandas.lancar_item(comanda.id, batata.id, 1)


def test_o_arquivado_nao_volta(cardapio, batata, uow, gerente, caixa_aberto):
    _vender(uow, gerente, caixa_aberto, batata)
    cardapio.arquivar_produto(batata.id)

    with pytest.raises(RegraDeNegocioError, match="não pode ser reativado"):
        cardapio.ativar_produto(batata.id)


def test_arquivar_duas_vezes_e_recusado(cardapio, batata, uow, gerente, caixa_aberto):
    """O instantâneo de uma tela aberta antes da primeira exclusão."""
    _vender(uow, gerente, caixa_aberto, batata)
    cardapio.arquivar_produto(batata.id)

    with pytest.raises(RegraDeNegocioError, match="já foi excluído do cardápio"):
        cardapio.arquivar_produto(batata.id)


def test_arquivar_exige_gerente(cardapio, batata, auth, atendente):
    """A Senha Master é barreira de TELA (§9.10); o perfil continua no service."""
    auth.login_como(atendente.id, PIN_ATENDENTE)

    with pytest.raises(AcessoNegadoError):
        cardapio.arquivar_produto(batata.id)


def test_arquivar_produto_inexistente(cardapio):
    with pytest.raises(RecursoNaoEncontradoError):
        cardapio.arquivar_produto(9999)


def test_o_arquivamento_e_gravado_de_verdade(cardapio, batata, uow, gerente, caixa_aberto):
    """Sem o commit, a leitura na mesma Session ainda veria a marca — e o
    rollback da próxima operação recusada a desfaria calado (a lição do §9.15)."""
    _vender(uow, gerente, caixa_aberto, batata)

    cardapio.arquivar_produto(batata.id)
    uow.rollback()
    uow.session.expire_all()

    assert uow.produtos.buscar_por_id(batata.id).arquivado is True


# ---------------------------------------------------------------------------
# A amarração com combo sai antes
# ---------------------------------------------------------------------------


def test_o_componente_sai_da_composicao_dos_combos(cardapio, lanches, batata, uow):
    combo = cardapio.criar_produto("Combo", Decimal("30.00"), lanches.id)
    refri = cardapio.criar_produto("Refri", Decimal("6.00"), lanches.id)
    cardapio.associar_componente(combo.id, batata.id, 1)
    cardapio.associar_componente(combo.id, refri.id, 1)

    cardapio.arquivar_produto(batata.id)

    assert [c.produto.nome for c in cardapio.listar_componentes(combo.id)] == ["Refri"]
    # O combo que ainda tem componente continua sendo combo.
    assert uow.produtos.buscar_por_id(combo.id).is_combo is True
    assert uow.produtos.buscar_por_id(batata.id).arquivado is True


def test_o_combo_que_perde_o_ultimo_componente_volta_a_ser_produto(
    cardapio, lanches, batata, uow
):
    """A regra de `remover_componente`, pelo mesmo helper."""
    combo = cardapio.criar_produto("Combo", Decimal("30.00"), lanches.id)
    cardapio.associar_componente(combo.id, batata.id, 1)

    cardapio.arquivar_produto(batata.id)

    assert cardapio.listar_componentes(combo.id) == []
    assert uow.produtos.buscar_por_id(combo.id).is_combo is False


def test_o_combo_arquivado_desfaz_a_propria_composicao(cardapio, lanches, batata, uow):
    """Os componentes continuam no cardápio, e ficam livres para entrar noutro
    combo: `associar_componente` recusaria quem ainda estivesse preso a um."""
    combo = cardapio.criar_produto("Combo", Decimal("30.00"), lanches.id)
    cardapio.associar_componente(combo.id, batata.id, 1)

    cardapio.arquivar_produto(combo.id)

    guardado = uow.produtos.buscar_por_id(combo.id)
    assert (guardado.arquivado, guardado.is_combo) == (True, False)
    assert uow.combo_itens.listar_vinculos_do_produto(batata.id) == []
    assert [p.nome for p in cardapio.listar_produtos()] == ["Batata"]
    outro = cardapio.criar_produto("Outro combo", Decimal("28.00"), lanches.id)
    cardapio.associar_componente(outro.id, batata.id, 1)


def test_os_outros_combos_nao_sao_tocados(cardapio, lanches, batata, uow):
    combo = cardapio.criar_produto("Combo", Decimal("30.00"), lanches.id)
    alheio = cardapio.criar_produto("Combo alheio", Decimal("25.00"), lanches.id)
    refri = cardapio.criar_produto("Refri", Decimal("6.00"), lanches.id)
    cardapio.associar_componente(combo.id, batata.id, 1)
    cardapio.associar_componente(alheio.id, refri.id, 3)

    cardapio.arquivar_produto(batata.id)

    componentes = cardapio.listar_componentes(alheio.id)
    assert [(c.produto.nome, c.quantidade) for c in componentes] == [("Refri", 3)]
    assert uow.produtos.buscar_por_id(alheio.id).is_combo is True


def test_desamarrar_e_arquivar_sao_uma_transacao_so(
    cardapio, lanches, batata, uow, monkeypatch
):
    """Se gravar a marca falha, a composição do combo tem que voltar: o produto
    desamarrado e ainda no cardápio é um estado que ninguém pediu."""
    combo = cardapio.criar_produto("Combo", Decimal("30.00"), lanches.id)
    cardapio.associar_componente(combo.id, batata.id, 1)

    def falhar(_produto):
        raise RegraDeNegocioError("falha simulada ao gravar")

    monkeypatch.setattr(uow.produtos, "salvar", falhar)
    with pytest.raises(RegraDeNegocioError, match="falha simulada"):
        cardapio.arquivar_produto(batata.id)
    monkeypatch.undo()
    uow.session.expire_all()

    assert [c.produto.nome for c in cardapio.listar_componentes(combo.id)] == ["Batata"]
    assert uow.produtos.buscar_por_id(batata.id).arquivado is False


def test_a_cascata_continua_sem_desamarrar(cardapio, lanches, uow):
    """A diferença entre os dois caminhos, dita por um teste.

    O pedido do Vitor foi para a exclusão do PRODUTO. As cascatas do §9.13 e do
    §9.14 continuam arquivando o componente sem mexer na composição — mudar isso
    é outra decisão, e ela está registrada como pendente no §9.18.
    """
    bebidas = cardapio.criar_categoria("Bebidas")
    combo = cardapio.criar_produto("Combo", Decimal("30.00"), bebidas.id)
    refri = cardapio.criar_produto("Refri", Decimal("6.00"), lanches.id)
    cardapio.associar_componente(combo.id, refri.id, 1)

    cardapio.excluir_categoria_em_cascata(lanches.id)

    assert len(uow.combo_itens.listar_por_combo(combo.id)) == 1


# ---------------------------------------------------------------------------
# A contagem dita pelo cartão e pela recusa
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("produtos", "subcategorias", "frase"),
    [
        (1, 0, "1 produto"),
        (5, 0, "5 produtos"),
        (0, 1, "1 subcategoria"),
        (3, 2, "3 produtos e 2 subcategorias"),
    ],
)
def test_a_contagem_do_conteudo(produtos, subcategorias, frase):
    assert quantidades_do_conteudo(produtos, subcategorias) == frase
    assert conteudo_da_categoria(produtos, subcategorias) == f"ela tem {frase}"
