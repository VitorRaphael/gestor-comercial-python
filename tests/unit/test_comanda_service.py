from datetime import datetime
from decimal import Decimal

import pytest

from gestor_comercial.domain.enums import FormaPagamento, StatusComanda, StatusMesa
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.pagamento import Pagamento
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from tests.conftest import PIN_ATENDENTE, PIN_GERENTE

PIN_INEXISTENTE = "999999"


@pytest.fixture
def comandas(uow, auth):
    return ComandaService(uow, auth)


@pytest.fixture
def comanda(comandas, gerente, caixa_aberto, mesa):
    """Comanda aberta na mesa 1, com gerente logado e caixa aberto."""
    return comandas.abrir_por_mesa(mesa.id)


@pytest.fixture
def refri(uow, categoria):
    return uow.produtos.salvar(
        Produto(nome="Refrigerante", preco=Decimal("6.50"), categoria_id=categoria.id)
    )


# ----------------------------------------------------------------------
# abrir_por_mesa
# ----------------------------------------------------------------------


def test_abrir_por_mesa_cria_comanda_aberta(comandas, gerente, caixa_aberto, mesa):
    comanda = comandas.abrir_por_mesa(mesa.id)

    assert comanda.id is not None
    assert comanda.status is StatusComanda.ABERTA
    assert comanda.mesa_id == mesa.id
    assert comanda.funcionario_id == gerente.id
    assert comanda.caixa_id == caixa_aberto.id
    assert isinstance(comanda.aberta_em, datetime)


def test_abrir_por_mesa_e_idempotente(comandas, gerente, caixa_aberto, mesa):
    primeira = comandas.abrir_por_mesa(mesa.id)
    segunda = comandas.abrir_por_mesa(mesa.id)

    assert segunda.id == primeira.id
    assert len(comandas.uow.comandas.listar_todos()) == 1


def test_abrir_por_mesa_cria_nova_apos_fechar_a_anterior(comandas, gerente, caixa_aberto, mesa):
    primeira = comandas.abrir_por_mesa(mesa.id)
    comandas.fechar(primeira.id)

    segunda = comandas.abrir_por_mesa(mesa.id)

    assert segunda.id != primeira.id
    assert segunda.status is StatusComanda.ABERTA


def test_abrir_por_mesa_com_mesa_inexistente(comandas, gerente, caixa_aberto):
    with pytest.raises(RecursoNaoEncontradoError):
        comandas.abrir_por_mesa(4242)


def test_abrir_por_mesa_sem_caixa_aberto(comandas, gerente, mesa):
    with pytest.raises(RegraDeNegocioError):
        comandas.abrir_por_mesa(mesa.id)


def test_abrir_por_mesa_sem_ninguem_logado(comandas, caixa_aberto, mesa):
    with pytest.raises(NaoAutorizadoError):
        comandas.abrir_por_mesa(mesa.id)


# ----------------------------------------------------------------------
# abrir_balcao
# ----------------------------------------------------------------------


def test_abrir_balcao_cria_comanda_sem_mesa(comandas, gerente, caixa_aberto):
    comanda = comandas.abrir_balcao()

    assert comanda.mesa_id is None
    assert comanda.status is StatusComanda.ABERTA
    assert comanda.caixa_id == caixa_aberto.id


def test_abrir_balcao_reaproveita_comanda_vazia(comandas, gerente, caixa_aberto):
    primeira = comandas.abrir_balcao()
    segunda = comandas.abrir_balcao()

    assert segunda.id == primeira.id


def test_abrir_balcao_cria_outra_se_a_anterior_ja_tem_item(
    comandas, gerente, caixa_aberto, produto
):
    primeira = comandas.abrir_balcao()
    comandas.lancar_item(primeira.id, produto.id, 1)

    segunda = comandas.abrir_balcao()

    assert segunda.id != primeira.id


def test_abrir_balcao_sem_caixa_aberto(comandas, gerente):
    with pytest.raises(RegraDeNegocioError):
        comandas.abrir_balcao()


def test_abrir_balcao_sem_ninguem_logado(comandas, caixa_aberto):
    with pytest.raises(NaoAutorizadoError):
        comandas.abrir_balcao()


# ----------------------------------------------------------------------
# buscar / listar_abertas / listar_itens
# ----------------------------------------------------------------------


def test_buscar_devolve_a_comanda(comandas, comanda):
    assert comandas.buscar(comanda.id).id == comanda.id


def test_buscar_comanda_inexistente(comandas, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        comandas.buscar(4242)


def test_listar_abertas_ignora_comanda_sem_item(comandas, comanda, produto):
    assert comandas.listar_abertas() == []

    comandas.lancar_item(comanda.id, produto.id, 1)

    assert [c.id for c in comandas.listar_abertas()] == [comanda.id]


def test_listar_abertas_ignora_fechadas_e_canceladas(comandas, comanda, produto):
    comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.fechar(comanda.id, pin_gerente=PIN_GERENTE)

    assert comandas.listar_abertas() == []


def test_listar_itens_devolve_os_lancados(comandas, comanda, produto, refri):
    primeiro = comandas.lancar_item(comanda.id, produto.id, 1)
    segundo = comandas.lancar_item(comanda.id, refri.id, 2)

    assert [i.id for i in comandas.listar_itens(comanda.id)] == [primeiro.id, segundo.id]


def test_listar_itens_de_comanda_inexistente(comandas, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        comandas.listar_itens(4242)


# ----------------------------------------------------------------------
# lancar_item
# ----------------------------------------------------------------------


def test_lancar_item_congela_o_preco_do_momento(comandas, uow, comanda, produto):
    item = comandas.lancar_item(comanda.id, produto.id, 3, "sem cebola")

    assert item.quantidade == 3
    assert item.preco_unit_congelado == Decimal("10.00")
    assert item.observacao == "sem cebola"
    assert item.cancelado is False

    produto.preco = Decimal("20.00")
    uow.produtos.salvar(produto)

    assert comandas.listar_itens(comanda.id)[0].preco_unit_congelado == Decimal("10.00")
    assert comandas.calcular_total(comanda.id) == Decimal("30.00")


def test_lancar_item_ocupa_a_mesa(comandas, uow, comanda, mesa, produto):
    assert mesa.status is StatusMesa.LIVRE

    comandas.lancar_item(comanda.id, produto.id, 1)

    assert uow.mesas.buscar_por_id(mesa.id).status is StatusMesa.OCUPADA


def test_lancar_item_no_balcao_nao_quebra_sem_mesa(comandas, gerente, caixa_aberto, produto):
    balcao = comandas.abrir_balcao()

    item = comandas.lancar_item(balcao.id, produto.id, 1)

    assert item.comanda_id == balcao.id


def test_lancar_item_observacao_vazia_vira_nulo(comandas, comanda, produto):
    item = comandas.lancar_item(comanda.id, produto.id, 1, "   ")

    assert item.observacao is None


def test_lancar_item_em_comanda_fechada(comandas, comanda, produto):
    comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.fechar(comanda.id, pin_gerente=PIN_GERENTE)

    with pytest.raises(RegraDeNegocioError):
        comandas.lancar_item(comanda.id, produto.id, 1)


def test_lancar_item_em_comanda_cancelada(comandas, comanda, produto):
    comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.cancelar(comanda.id, "cliente desistiu", PIN_GERENTE)

    with pytest.raises(RegraDeNegocioError):
        comandas.lancar_item(comanda.id, produto.id, 1)


def test_lancar_item_de_produto_inativo(comandas, uow, comanda, produto):
    produto.ativo = False
    uow.produtos.salvar(produto)

    with pytest.raises(RegraDeNegocioError):
        comandas.lancar_item(comanda.id, produto.id, 1)


def test_lancar_item_de_produto_inexistente(comandas, comanda):
    with pytest.raises(RecursoNaoEncontradoError):
        comandas.lancar_item(comanda.id, 4242, 1)


def test_lancar_item_em_comanda_inexistente(comandas, gerente, produto):
    with pytest.raises(RecursoNaoEncontradoError):
        comandas.lancar_item(4242, produto.id, 1)


@pytest.mark.parametrize("quantidade", [0, -1])
def test_lancar_item_com_quantidade_nao_positiva(comandas, comanda, produto, quantidade):
    with pytest.raises(RegraDeNegocioError):
        comandas.lancar_item(comanda.id, produto.id, quantidade)


@pytest.mark.parametrize("quantidade", ["2", 1.5, True, None])
def test_lancar_item_com_quantidade_nao_inteira(comandas, comanda, produto, quantidade):
    with pytest.raises(RegraDeNegocioError):
        comandas.lancar_item(comanda.id, produto.id, quantidade)


# ----------------------------------------------------------------------
# remover_item
# ----------------------------------------------------------------------


def test_remover_item_apaga_de_vez(comandas, comanda, produto, refri):
    item = comandas.lancar_item(comanda.id, produto.id, 1)
    mantido = comandas.lancar_item(comanda.id, refri.id, 1)

    comandas.remover_item(item.id)

    assert [i.id for i in comandas.listar_itens(comanda.id)] == [mantido.id]


def test_remover_item_de_comanda_fechada(comandas, comanda, produto):
    item = comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.fechar(comanda.id, pin_gerente=PIN_GERENTE)

    with pytest.raises(RegraDeNegocioError):
        comandas.remover_item(item.id)


def test_remover_item_ja_cancelado(comandas, comanda, produto):
    item = comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.cancelar_item(item.id, "veio errado", PIN_GERENTE)

    with pytest.raises(RegraDeNegocioError):
        comandas.remover_item(item.id)


def test_remover_item_ja_impresso_exige_cancelamento(comandas, comanda, produto, uow):
    """Item que já foi pra chapa não pode sumir do banco sem PIN, sem motivo e
    sem quem autorizou — seria desviar comida sem deixar rastro. A partir daí só
    `cancelar_item`, que registra tudo."""
    item = comandas.lancar_item(comanda.id, produto.id, 1)
    item.impresso_em = datetime.now()
    uow.itens.salvar(item)
    uow.commit()

    with pytest.raises(RegraDeNegocioError, match="produção"):
        comandas.remover_item(item.id)

    assert [i.id for i in comandas.listar_itens(comanda.id)] == [item.id]


def test_remover_item_inexistente(comandas, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        comandas.remover_item(4242)


# ----------------------------------------------------------------------
# cancelar_item
# ----------------------------------------------------------------------


def test_cancelar_item_registra_motivo_e_gerente(comandas, comanda, produto, gerente):
    item = comandas.lancar_item(comanda.id, produto.id, 2)

    cancelado = comandas.cancelar_item(item.id, "  cliente desistiu  ", PIN_GERENTE)

    assert cancelado.cancelado is True
    assert cancelado.motivo_cancelamento == "cliente desistiu"
    assert cancelado.cancelado_por_id == gerente.id
    assert isinstance(cancelado.cancelado_em, datetime)


def test_cancelar_item_sai_do_total(comandas, comanda, produto, refri):
    cancelavel = comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.lancar_item(comanda.id, refri.id, 2)

    comandas.cancelar_item(cancelavel.id, "veio errado", PIN_GERENTE)

    assert comandas.calcular_total(comanda.id) == Decimal("13.00")


def test_cancelar_item_nao_troca_o_usuario_da_sessao(comandas, auth, comanda, produto, atendente):
    auth.login(PIN_ATENDENTE)
    item = comandas.lancar_item(comanda.id, produto.id, 1)

    comandas.cancelar_item(item.id, "veio errado", PIN_GERENTE)

    assert auth.usuario_logado.id == atendente.id


def test_cancelar_item_ja_cancelado(comandas, comanda, produto):
    item = comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.cancelar_item(item.id, "veio errado", PIN_GERENTE)

    with pytest.raises(RegraDeNegocioError):
        comandas.cancelar_item(item.id, "de novo", PIN_GERENTE)


def test_cancelar_item_de_comanda_fechada(comandas, comanda, produto):
    item = comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.fechar(comanda.id, pin_gerente=PIN_GERENTE)

    with pytest.raises(RegraDeNegocioError):
        comandas.cancelar_item(item.id, "veio errado", PIN_GERENTE)


@pytest.mark.parametrize("motivo", ["", "   ", None])
def test_cancelar_item_sem_motivo(comandas, comanda, produto, motivo):
    item = comandas.lancar_item(comanda.id, produto.id, 1)

    with pytest.raises(RegraDeNegocioError):
        comandas.cancelar_item(item.id, motivo, PIN_GERENTE)


def test_cancelar_item_com_pin_de_atendente(comandas, comanda, produto, atendente):
    item = comandas.lancar_item(comanda.id, produto.id, 1)

    with pytest.raises(AcessoNegadoError):
        comandas.cancelar_item(item.id, "veio errado", PIN_ATENDENTE)

    assert comandas.listar_itens(comanda.id)[0].cancelado is False


def test_cancelar_item_com_pin_invalido(comandas, comanda, produto):
    item = comandas.lancar_item(comanda.id, produto.id, 1)

    with pytest.raises(NaoAutorizadoError):
        comandas.cancelar_item(item.id, "veio errado", PIN_INEXISTENTE)


def test_cancelar_item_inexistente(comandas, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        comandas.cancelar_item(4242, "veio errado", PIN_GERENTE)


# ----------------------------------------------------------------------
# calcular_total
# ----------------------------------------------------------------------


def test_calcular_total_soma_os_itens(comandas, comanda, produto, refri):
    comandas.lancar_item(comanda.id, produto.id, 3)
    comandas.lancar_item(comanda.id, refri.id, 2)

    assert comandas.calcular_total(comanda.id) == Decimal("43.00")


def test_calcular_total_sem_itens_e_zero(comandas, comanda):
    total = comandas.calcular_total(comanda.id)

    assert total == Decimal("0.00")
    assert total.as_tuple().exponent == -2


def test_calcular_total_de_comanda_inexistente(comandas, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        comandas.calcular_total(4242)


# ----------------------------------------------------------------------
# fechar
# ----------------------------------------------------------------------


def test_fechar_libera_a_mesa(comandas, uow, comanda, mesa, produto):
    comandas.lancar_item(comanda.id, produto.id, 1)

    fechada = comandas.fechar(comanda.id, pin_gerente=PIN_GERENTE)

    assert fechada.status is StatusComanda.FECHADA
    assert isinstance(fechada.fechada_em, datetime)
    assert uow.mesas.buscar_por_id(mesa.id).status is StatusMesa.LIVRE


def test_fechar_comanda_de_balcao(comandas, gerente, caixa_aberto, produto):
    balcao = comandas.abrir_balcao()
    comandas.lancar_item(balcao.id, produto.id, 1)

    assert comandas.fechar(balcao.id, pin_gerente=PIN_GERENTE).status is StatusComanda.FECHADA


def test_fechar_comanda_ja_fechada(comandas, comanda):
    comandas.fechar(comanda.id)

    with pytest.raises(RegraDeNegocioError):
        comandas.fechar(comanda.id)


def test_fechar_com_saldo_em_aberto_e_bloqueado_sem_gerente(comandas, comanda, produto):
    comandas.lancar_item(comanda.id, produto.id, 1)

    with pytest.raises(RegraDeNegocioError, match="a receber"):
        comandas.fechar(comanda.id)
    assert comandas.buscar(comanda.id).status is StatusComanda.ABERTA


def test_fechar_com_saldo_em_aberto_e_liberado_com_pin_de_gerente(comandas, comanda, produto):
    comandas.lancar_item(comanda.id, produto.id, 1)

    fechada = comandas.fechar(comanda.id, pin_gerente=PIN_GERENTE)
    assert fechada.status is StatusComanda.FECHADA


def test_fechar_com_pin_de_atendente_e_bloqueado(comandas, comanda, produto, atendente):
    comandas.lancar_item(comanda.id, produto.id, 1)

    with pytest.raises(AcessoNegadoError):
        comandas.fechar(comanda.id, pin_gerente=PIN_ATENDENTE)


def test_fechar_sem_ninguem_logado_e_bloqueado(auth, comandas, comanda, produto):
    auth.logout()

    with pytest.raises(NaoAutorizadoError):
        comandas.fechar(comanda.id)


def test_fechar_quando_restante_zera_so_por_cancelamento_de_item(comandas, comanda, produto):
    # Antes da correção: uma comanda que fica quitada por cancelamento de item
    # (em vez de pagamento) ficava presa — sem forma de fechar nem cancelar.
    # Com todo item cancelado o restante é zero, então fechar() nem precisa
    # de PIN de gerente aqui — é a mesma regra de uma comanda que nunca teve item.
    item = comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.cancelar_item(item.id, "não vai levar", PIN_GERENTE)

    fechada = comandas.fechar(comanda.id)
    assert fechada.status is StatusComanda.FECHADA


def test_fechar_comanda_cancelada(comandas, comanda, produto):
    comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.cancelar(comanda.id, "cliente desistiu", PIN_GERENTE)

    with pytest.raises(RegraDeNegocioError):
        comandas.fechar(comanda.id)


def test_fechar_comanda_inexistente(comandas, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        comandas.fechar(4242)


# ----------------------------------------------------------------------
# cancelar
# ----------------------------------------------------------------------


def test_cancelar_derruba_os_itens_em_cascata(
    comandas, uow, comanda, mesa, produto, refri, gerente
):
    comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.lancar_item(comanda.id, refri.id, 2)

    cancelada = comandas.cancelar(comanda.id, "  cliente desistiu  ", PIN_GERENTE)

    assert cancelada.status is StatusComanda.CANCELADA
    assert cancelada.motivo_cancelamento == "cliente desistiu"
    assert cancelada.cancelado_por_id == gerente.id
    assert isinstance(cancelada.cancelada_em, datetime)

    itens = comandas.listar_itens(comanda.id)
    assert all(i.cancelado for i in itens)
    assert {i.motivo_cancelamento for i in itens} == {"cliente desistiu"}
    assert {i.cancelado_em for i in itens} == {cancelada.cancelada_em}

    assert comandas.calcular_total(comanda.id) == Decimal("0.00")
    assert uow.mesas.buscar_por_id(mesa.id).status is StatusMesa.LIVRE


def test_cancelar_preserva_o_motivo_do_item_ja_cancelado(comandas, uow, comanda, produto, refri):
    ja_cancelado = comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.lancar_item(comanda.id, refri.id, 1)
    comandas.cancelar_item(ja_cancelado.id, "veio errado", PIN_GERENTE)

    comandas.cancelar(comanda.id, "cliente desistiu", PIN_GERENTE)

    assert uow.itens.buscar_por_id(ja_cancelado.id).motivo_cancelamento == "veio errado"


def test_cancelar_comanda_com_pagamento_registrado(comandas, uow, comanda, produto):
    comandas.lancar_item(comanda.id, produto.id, 1)
    uow.pagamentos.salvar(
        Pagamento(
            forma=FormaPagamento.DINHEIRO,
            valor=Decimal("10.00"),
            registrado_em=datetime(2026, 8, 20, 12, 0),
            comanda_id=comanda.id,
        )
    )

    with pytest.raises(RegraDeNegocioError):
        comandas.cancelar(comanda.id, "cliente desistiu", PIN_GERENTE)

    assert comandas.buscar(comanda.id).status is StatusComanda.ABERTA


def test_cancelar_comanda_ja_fechada(comandas, comanda, produto):
    comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.fechar(comanda.id, pin_gerente=PIN_GERENTE)

    with pytest.raises(RegraDeNegocioError):
        comandas.cancelar(comanda.id, "cliente desistiu", PIN_GERENTE)


def test_cancelar_comanda_ja_cancelada(comandas, comanda, produto):
    comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.cancelar(comanda.id, "cliente desistiu", PIN_GERENTE)

    with pytest.raises(RegraDeNegocioError):
        comandas.cancelar(comanda.id, "de novo", PIN_GERENTE)


@pytest.mark.parametrize("motivo", ["", "   ", None])
def test_cancelar_comanda_sem_motivo(comandas, comanda, produto, motivo):
    comandas.lancar_item(comanda.id, produto.id, 1)

    with pytest.raises(RegraDeNegocioError):
        comandas.cancelar(comanda.id, motivo, PIN_GERENTE)


def test_cancelar_comanda_com_pin_de_atendente(comandas, comanda, produto, atendente):
    comandas.lancar_item(comanda.id, produto.id, 1)

    with pytest.raises(AcessoNegadoError):
        comandas.cancelar(comanda.id, "cliente desistiu", PIN_ATENDENTE)

    assert comandas.buscar(comanda.id).status is StatusComanda.ABERTA


def test_cancelar_comanda_com_pin_invalido(comandas, comanda, produto):
    comandas.lancar_item(comanda.id, produto.id, 1)

    with pytest.raises(NaoAutorizadoError):
        comandas.cancelar(comanda.id, "cliente desistiu", PIN_INEXISTENTE)


def test_cancelar_comanda_inexistente(comandas, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        comandas.cancelar(4242, "cliente desistiu", PIN_GERENTE)


# ----------------------------------------------------------------------
# Mesas independentes não interferem entre si
# ----------------------------------------------------------------------


def test_mesas_diferentes_tem_comandas_diferentes(comandas, uow, gerente, caixa_aberto, mesa):
    outra_mesa = uow.mesas.salvar(Mesa(numero=2))

    primeira = comandas.abrir_por_mesa(mesa.id)
    segunda = comandas.abrir_por_mesa(outra_mesa.id)

    assert primeira.id != segunda.id
    assert segunda.mesa_id == outra_mesa.id
