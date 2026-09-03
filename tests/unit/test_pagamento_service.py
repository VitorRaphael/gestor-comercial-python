from datetime import datetime
from decimal import Decimal

import pytest

from gestor_comercial.domain.enums import FormaPagamento, StatusComanda, StatusMesa
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.pagamento_service import PagamentoService
from tests.conftest import PIN_ATENDENTE, PIN_GERENTE

PIN_INEXISTENTE = "999999"


@pytest.fixture
def comandas(uow, auth):
    return ComandaService(uow, auth)


@pytest.fixture
def pagamentos(uow, auth, comandas, funcionarios):
    return PagamentoService(uow, auth, comandas, funcionarios)


@pytest.fixture
def burger(uow, categoria):
    """Produto de 12.00 — três deles fazem uma conta de 36.00 exatos."""
    return uow.produtos.salvar(
        Produto(nome="X-Salada", preco=Decimal("12.00"), categoria_id=categoria.id)
    )


@pytest.fixture
def conta_36(comandas, gerente, caixa_aberto, mesa, burger):
    """Comanda em conferência na mesa 1 com três itens de R$ 12,00 = R$ 36,00.

    São três lançamentos separados (e não um de quantidade 3) para os testes
    conseguirem cancelar parte da conta depois de um pagamento parcial (via
    `reabrir`, já que a comanda sai daqui em EM_CONFERENCIA — pagamento só
    é aceito depois da pré-conta emitida, § Fechamento de Comanda).
    """
    comanda = comandas.abrir_por_mesa(mesa.id)
    for _ in range(3):
        comandas.lancar_item(comanda.id, burger.id, 1)
    comandas.fechar_para_conferencia(comanda.id)
    return comanda


def lancar_consumo(comandas, pagamentos, produto, quantidade, funcionario_id):
    """Abre uma comanda de balcão e paga tudo como consumo interno do funcionário."""
    comanda = comandas.abrir_balcao()
    comandas.lancar_item(comanda.id, produto.id, quantidade)
    comandas.fechar_para_conferencia(comanda.id)
    pagamentos.registrar(
        comanda.id,
        FormaPagamento.CONSUMO_INTERNO,
        Decimal(produto.preco) * quantidade,
        pin_gerente=PIN_GERENTE,
        funcionario_consumo_id=funcionario_id,
    )
    return comanda


# ----------------------------------------------------------------------
# registrar — caminho feliz e troco
# ----------------------------------------------------------------------


def test_registrar_valor_exato_quita_e_fecha_a_comanda(pagamentos, comandas, conta_36, mesa):
    resumo = pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("36.00"))

    assert resumo.comanda_id == conta_36.id
    assert resumo.total_conta == Decimal("36.00")
    assert resumo.total_pago == Decimal("36.00")
    assert resumo.restante == Decimal("0.00")
    assert resumo.troco is None
    assert resumo.comanda_fechada is True
    assert comandas.buscar(conta_36.id).status is StatusComanda.FECHADA
    assert pagamentos.uow.mesas.buscar_por_id(mesa.id).status is StatusMesa.LIVRE


def test_confirmar_pagamento_duas_vezes_seguidas_e_bloqueado(pagamentos, comandas, conta_36):
    """Dupla submissão: clicar 'Confirmar' duas vezes rápido antes de o botão desabilitar.

    A 1ª chamada paga e fecha a comanda (fechamento automático); a 2ª chegada
    da mesma ação, com os mesmos parâmetros, não pode gerar um segundo
    pagamento — tem que ser barrada porque a comanda já está FECHADA.
    """
    pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("36.00"))

    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("36.00"))

    assert len(pagamentos.listar_por_comanda(conta_36.id)) == 1


def test_registrar_dinheiro_acima_do_restante_gera_troco(pagamentos, conta_36):
    resumo = pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("50.00"))

    assert resumo.troco == Decimal("14.00")
    assert resumo.total_pago == Decimal("36.00")
    assert resumo.restante == Decimal("0.00")
    assert resumo.comanda_fechada is True

    # O que entra na conta é só o que faltava — o troco saiu da gaveta de volta.
    (pagamento,) = pagamentos.listar_por_comanda(conta_36.id)
    assert pagamento.valor == Decimal("36.00")
    assert pagamento.troco == Decimal("14.00")


def test_registrar_pagamento_parcial_em_duas_formas_ate_quitar(pagamentos, comandas, conta_36):
    parcial = pagamentos.registrar(conta_36.id, FormaPagamento.DEBITO, Decimal("20.00"))

    assert parcial.total_pago == Decimal("20.00")
    assert parcial.restante == Decimal("16.00")
    assert parcial.comanda_fechada is False
    assert comandas.buscar(conta_36.id).status is StatusComanda.EM_CONFERENCIA

    final = pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("16.00"))

    assert final.total_pago == Decimal("36.00")
    assert final.restante == Decimal("0.00")
    assert final.troco is None
    assert final.comanda_fechada is True
    assert comandas.buscar(conta_36.id).status is StatusComanda.FECHADA
    assert len(pagamentos.listar_por_comanda(conta_36.id)) == 2


def test_registrar_grava_forma_e_data(pagamentos, conta_36):
    pagamentos.registrar(conta_36.id, FormaPagamento.PIX, Decimal("36.00"))

    (pagamento,) = pagamentos.listar_por_comanda(conta_36.id)
    assert pagamento.forma is FormaPagamento.PIX
    assert pagamento.valor_quitado == Decimal("0.00")
    assert isinstance(pagamento.registrado_em, datetime)


def test_registrar_arredonda_para_dois_decimais(pagamentos, conta_36):
    resumo = pagamentos.registrar(conta_36.id, FormaPagamento.DEBITO, Decimal("10.005"))

    assert resumo.total_pago == Decimal("10.01")
    assert resumo.restante == Decimal("25.99")


# ----------------------------------------------------------------------
# registrar — regras de bloqueio
# ----------------------------------------------------------------------


def test_registrar_pix_acima_do_restante_e_bloqueado(pagamentos, conta_36):
    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(conta_36.id, FormaPagamento.PIX, Decimal("36.01"))

    assert pagamentos.listar_por_comanda(conta_36.id) == []


def test_registrar_credito_acima_do_restante_e_bloqueado(pagamentos, conta_36):
    pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("30.00"))

    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(conta_36.id, FormaPagamento.CREDITO, Decimal("10.00"))


def test_registrar_valor_zero_e_bloqueado(pagamentos, conta_36):
    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("0.00"))


def test_registrar_valor_negativo_e_bloqueado(pagamentos, conta_36):
    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("-5.00"))


def test_registrar_valor_invalido_e_bloqueado(pagamentos, conta_36):
    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, "trinta")


def test_registrar_valor_nulo_e_bloqueado(pagamentos, conta_36):
    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, None)


def test_registrar_valor_em_float_e_erro_de_programacao(pagamentos, conta_36):
    # float não vira RegraDeNegocioError de propósito: é bug de tela, tem que
    # estourar no teste em vez de virar diferença de centavo no fechamento.
    with pytest.raises(TypeError):
        pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, 36.00)


def test_registrar_com_forma_invalida_e_bloqueado(pagamentos, conta_36):
    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(conta_36.id, "DINHEIRO", Decimal("36.00"))


def test_registrar_em_comanda_sem_itens_e_bloqueado(pagamentos, comandas, gerente, caixa_aberto, mesa):
    comanda = comandas.abrir_por_mesa(mesa.id)

    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(comanda.id, FormaPagamento.DINHEIRO, Decimal("10.00"))


def test_registrar_em_comanda_ainda_aberta_e_bloqueado(pagamentos, comandas, gerente, caixa_aberto, mesa, burger):
    """§ Fechamento de Comanda: sem pré-conta emitida, não há o que pagar."""
    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.lancar_item(comanda.id, burger.id, 1)

    with pytest.raises(RegraDeNegocioError, match="conferência"):
        pagamentos.registrar(comanda.id, FormaPagamento.DINHEIRO, Decimal("12.00"))


def test_registrar_em_comanda_ja_quitada_e_bloqueado(pagamentos, comandas, conta_36):
    """Conta quitada sem ter fechado: itens cancelados (via reabertura) depois do pagamento."""
    pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("12.00"))
    comandas.reabrir(conta_36.id, PIN_GERENTE)
    itens = comandas.listar_itens(conta_36.id)
    comandas.cancelar_item(itens[0].id, "Cliente desistiu", PIN_GERENTE)
    comandas.cancelar_item(itens[1].id, "Cliente desistiu", PIN_GERENTE)
    comandas.fechar_para_conferencia(conta_36.id)

    assert pagamentos.calcular_restante(conta_36.id) == Decimal("0.00")
    assert comandas.buscar(conta_36.id).status is StatusComanda.EM_CONFERENCIA

    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("5.00"))

    # A comanda não fica presa: como o restante é zero, comandas.fechar()
    # aceita fechar sem PIN de gerente (mesma regra de uma comanda que nunca
    # teve item), e a partir daí o caixa fecha o dia normalmente.
    fechada = comandas.fechar(conta_36.id)
    assert fechada.status is StatusComanda.FECHADA

    from gestor_comercial.services.caixa_service import CaixaService

    caixas = CaixaService(comandas.uow, comandas.auth)
    caixa_aberto = caixas.buscar_aberto()
    assert caixas.fechar(caixa_aberto.id, Decimal("112.00")).status.value == "FECHADO"


def test_registrar_em_comanda_fechada_e_bloqueado(pagamentos, comandas, conta_36):
    comandas.fechar(conta_36.id, pin_gerente=PIN_GERENTE)

    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("36.00"))


def test_registrar_em_comanda_cancelada_e_bloqueado(pagamentos, comandas, gerente, caixa_aberto, mesa, burger):
    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.lancar_item(comanda.id, burger.id, 1)
    comandas.cancelar(comanda.id, "Pedido errado", PIN_GERENTE)

    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(comanda.id, FormaPagamento.DINHEIRO, Decimal("12.00"))


def test_registrar_em_comanda_inexistente(pagamentos, gerente, caixa_aberto):
    with pytest.raises(RecursoNaoEncontradoError):
        pagamentos.registrar(4242, FormaPagamento.DINHEIRO, Decimal("10.00"))


def test_registrar_sem_ninguem_logado(pagamentos, auth, conta_36):
    auth.logout()

    with pytest.raises(NaoAutorizadoError):
        pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("36.00"))


# ----------------------------------------------------------------------
# registrar — consumo interno (§3.7)
# ----------------------------------------------------------------------


def test_registrar_consumo_interno_gera_divida_do_funcionario(pagamentos, conta_36, funcionario):
    resumo = pagamentos.registrar(
        conta_36.id,
        FormaPagamento.CONSUMO_INTERNO,
        Decimal("36.00"),
        pin_gerente=PIN_GERENTE,
        funcionario_consumo_id=funcionario.id,
    )

    assert resumo.comanda_fechada is True
    (pagamento,) = pagamentos.listar_por_comanda(conta_36.id)
    assert pagamento.funcionario_consumo_id == funcionario.id
    assert pagamento.valor == Decimal("36.00")
    assert pagamento.valor_quitado == Decimal("0.00")
    assert pagamentos.calcular_saldo_devedor(funcionario.id) == Decimal("36.00")
    assert funcionario.saldo_devedor == Decimal("36.00")


def test_registrar_consumo_interno_parcial_soma_so_o_lancado(pagamentos, conta_36, funcionario):
    pagamentos.registrar(
        conta_36.id,
        FormaPagamento.CONSUMO_INTERNO,
        Decimal("10.00"),
        pin_gerente=PIN_GERENTE,
        funcionario_consumo_id=funcionario.id,
    )
    resumo = pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("26.00"))

    assert resumo.comanda_fechada is True
    assert pagamentos.calcular_saldo_devedor(funcionario.id) == Decimal("10.00")
    assert funcionario.saldo_devedor == Decimal("10.00")


def test_registrar_consumo_interno_sem_pin_de_gerente(pagamentos, conta_36, funcionario):
    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(
            conta_36.id,
            FormaPagamento.CONSUMO_INTERNO,
            Decimal("36.00"),
            funcionario_consumo_id=funcionario.id,
        )


def test_registrar_consumo_interno_com_pin_de_atendente(pagamentos, conta_36, funcionario, atendente):
    with pytest.raises(AcessoNegadoError):
        pagamentos.registrar(
            conta_36.id,
            FormaPagamento.CONSUMO_INTERNO,
            Decimal("36.00"),
            pin_gerente=PIN_ATENDENTE,
            funcionario_consumo_id=funcionario.id,
        )


def test_registrar_consumo_interno_com_pin_inexistente(pagamentos, conta_36, funcionario):
    with pytest.raises(NaoAutorizadoError):
        pagamentos.registrar(
            conta_36.id,
            FormaPagamento.CONSUMO_INTERNO,
            Decimal("36.00"),
            pin_gerente=PIN_INEXISTENTE,
            funcionario_consumo_id=funcionario.id,
        )


def test_registrar_consumo_interno_sem_funcionario(pagamentos, conta_36, funcionario):
    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(
            conta_36.id,
            FormaPagamento.CONSUMO_INTERNO,
            Decimal("36.00"),
            pin_gerente=PIN_GERENTE,
        )


def test_registrar_consumo_interno_com_funcionario_inexistente(pagamentos, conta_36, funcionario):
    with pytest.raises(RecursoNaoEncontradoError):
        pagamentos.registrar(
            conta_36.id,
            FormaPagamento.CONSUMO_INTERNO,
            Decimal("36.00"),
            pin_gerente=PIN_GERENTE,
            funcionario_consumo_id=4242,
        )


def test_registrar_consumo_interno_com_funcionario_desativado(
    pagamentos, funcionarios, conta_36, funcionario
):
    funcionarios.desativar(funcionario.id)

    with pytest.raises(RegraDeNegocioError):
        pagamentos.registrar(
            conta_36.id,
            FormaPagamento.CONSUMO_INTERNO,
            Decimal("36.00"),
            pin_gerente=PIN_GERENTE,
            funcionario_consumo_id=funcionario.id,
        )


# ----------------------------------------------------------------------
# listar_por_comanda / calcular_total_pago / calcular_restante
# ----------------------------------------------------------------------


def test_listar_por_comanda_sem_pagamento(pagamentos, conta_36):
    assert pagamentos.listar_por_comanda(conta_36.id) == []


def test_listar_por_comanda_inexistente(pagamentos, gerente, caixa_aberto):
    with pytest.raises(RecursoNaoEncontradoError):
        pagamentos.listar_por_comanda(4242)


def test_calcular_total_pago_soma_os_pagamentos(pagamentos, conta_36):
    pagamentos.registrar(conta_36.id, FormaPagamento.PIX, Decimal("11.50"))
    pagamentos.registrar(conta_36.id, FormaPagamento.DEBITO, Decimal("4.50"))

    assert pagamentos.calcular_total_pago(conta_36.id) == Decimal("16.00")
    assert pagamentos.calcular_restante(conta_36.id) == Decimal("20.00")


def test_calcular_total_pago_de_comanda_inexistente(pagamentos, gerente, caixa_aberto):
    with pytest.raises(RecursoNaoEncontradoError):
        pagamentos.calcular_total_pago(4242)


def test_calcular_restante_nunca_fica_negativo(pagamentos, comandas, conta_36):
    pagamentos.registrar(conta_36.id, FormaPagamento.DINHEIRO, Decimal("24.00"))
    comandas.reabrir(conta_36.id, PIN_GERENTE)
    itens = comandas.listar_itens(conta_36.id)
    comandas.cancelar_item(itens[0].id, "Saiu errado", PIN_GERENTE)
    comandas.cancelar_item(itens[1].id, "Saiu errado", PIN_GERENTE)

    assert pagamentos.calcular_restante(conta_36.id) == Decimal("0.00")


# ----------------------------------------------------------------------
# calcular_saldo_devedor (§3.8)
# ----------------------------------------------------------------------


def test_calcular_saldo_devedor_sem_consumo(pagamentos, gerente, funcionario):
    assert pagamentos.calcular_saldo_devedor(funcionario.id) == Decimal("0.00")


def test_calcular_saldo_devedor_soma_varios_consumos(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario
):
    lancar_consumo(comandas, pagamentos, produto, 1, funcionario.id)
    lancar_consumo(comandas, pagamentos, produto, 2, funcionario.id)

    assert pagamentos.calcular_saldo_devedor(funcionario.id) == Decimal("30.00")


def test_calcular_saldo_devedor_de_funcionario_inexistente(pagamentos, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        pagamentos.calcular_saldo_devedor(4242)


def test_consultas_de_divida_sao_bloqueadas_para_atendente(pagamentos, auth, gerente, atendente, funcionario):
    # §3.1/§3.8: dívida de consumo interno não é leitura livre — só gerente.
    auth.login(PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        pagamentos.calcular_saldo_devedor(funcionario.id)
    with pytest.raises(AcessoNegadoError):
        pagamentos.listar_funcionarios_com_saldo()
    with pytest.raises(AcessoNegadoError):
        pagamentos.listar_consumos(funcionario.id)


def test_consultas_de_divida_sao_bloqueadas_sem_sessao(pagamentos, auth, gerente, funcionario):
    auth.logout()
    with pytest.raises(NaoAutorizadoError):
        pagamentos.calcular_saldo_devedor(funcionario.id)
    with pytest.raises(NaoAutorizadoError):
        pagamentos.listar_funcionarios_com_saldo()
    with pytest.raises(NaoAutorizadoError):
        pagamentos.listar_consumos(funcionario.id)


def test_cache_saldo_devedor_bate_com_a_fonte_da_verdade(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario
):
    """O campo denormalizado tem que continuar igual à soma dos pagamentos."""
    lancar_consumo(comandas, pagamentos, produto, 3, funcionario.id)
    pagamentos.quitar(funcionario.id, Decimal("12.50"), PIN_GERENTE)

    fonte_da_verdade = pagamentos.calcular_saldo_devedor(funcionario.id)
    assert fonte_da_verdade == Decimal("17.50")
    assert funcionario.saldo_devedor == fonte_da_verdade


# ----------------------------------------------------------------------
# listar_funcionarios_com_saldo / listar_consumos
# ----------------------------------------------------------------------


def test_listar_funcionarios_com_saldo_traz_so_quem_deve_em_ordem_de_nome(
    pagamentos, comandas, funcionarios, gerente, caixa_aberto, produto, funcionario
):
    bruno = funcionarios.criar("Bruno")
    ana = funcionarios.criar("Ana")
    lancar_consumo(comandas, pagamentos, produto, 2, bruno.id)
    lancar_consumo(comandas, pagamentos, produto, 1, ana.id)

    linhas = pagamentos.listar_funcionarios_com_saldo()

    assert [linha.nome for linha in linhas] == ["Ana", "Bruno"]
    assert linhas[0].funcionario_id == ana.id
    assert linhas[0].saldo == Decimal("10.00")
    assert linhas[1].saldo == Decimal("20.00")


def test_listar_funcionarios_com_saldo_ignora_quem_ja_quitou(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario
):
    lancar_consumo(comandas, pagamentos, produto, 1, funcionario.id)
    pagamentos.quitar(funcionario.id, Decimal("10.00"), PIN_GERENTE)

    assert pagamentos.listar_funcionarios_com_saldo() == []


def test_listar_consumos_monta_o_extrato(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario
):
    lancar_consumo(comandas, pagamentos, produto, 1, funcionario.id)
    lancar_consumo(comandas, pagamentos, produto, 2, funcionario.id)
    pagamentos.quitar(funcionario.id, Decimal("5.00"), PIN_GERENTE)
    pagamentos.quitar(funcionario.id, Decimal("3.00"), PIN_GERENTE)

    extrato = pagamentos.listar_consumos(funcionario.id)

    assert extrato.funcionario_id == funcionario.id
    assert extrato.nome == "Garçom"
    assert extrato.saldo == Decimal("22.00")
    assert [consumo.valor for consumo in extrato.consumos] == [Decimal("10.00"), Decimal("20.00")]
    # Quitações mais recentes primeiro — é a ordem que a tela de extrato mostra.
    assert [quitacao.valor_quitado for quitacao in extrato.quitacoes] == [
        Decimal("3.00"),
        Decimal("5.00"),
    ]


def test_listar_consumos_de_funcionario_inexistente(pagamentos, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        pagamentos.listar_consumos(4242)


# ----------------------------------------------------------------------
# quitar (§3.8)
# ----------------------------------------------------------------------


def test_quitar_abate_fifo_do_consumo_mais_antigo(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario
):
    """Três consumos (10, 20, 30) e uma quitação de 25: abate o 1º inteiro e 15 do 2º."""
    lancar_consumo(comandas, pagamentos, produto, 1, funcionario.id)
    lancar_consumo(comandas, pagamentos, produto, 2, funcionario.id)
    lancar_consumo(comandas, pagamentos, produto, 3, funcionario.id)

    novo_saldo = pagamentos.quitar(funcionario.id, Decimal("25.00"), PIN_GERENTE)

    assert novo_saldo == Decimal("35.00")
    primeiro, segundo, terceiro = pagamentos.listar_consumos(funcionario.id).consumos
    assert primeiro.valor_quitado == Decimal("10.00")
    assert segundo.valor_quitado == Decimal("15.00")
    assert terceiro.valor_quitado == Decimal("0.00")
    assert funcionario.saldo_devedor == Decimal("35.00")


def test_quitar_tudo_zera_o_saldo(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario
):
    lancar_consumo(comandas, pagamentos, produto, 2, funcionario.id)

    novo_saldo = pagamentos.quitar(funcionario.id, Decimal("20.00"), PIN_GERENTE)

    assert novo_saldo == Decimal("0.00")
    assert pagamentos.calcular_saldo_devedor(funcionario.id) == Decimal("0.00")
    assert funcionario.saldo_devedor == Decimal("0.00")


def test_quitar_registra_quem_autorizou(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario
):
    lancar_consumo(comandas, pagamentos, produto, 1, funcionario.id)
    pagamentos.quitar(funcionario.id, Decimal("4.00"), PIN_GERENTE)

    (quitacao,) = pagamentos.listar_consumos(funcionario.id).quitacoes
    assert quitacao.valor_quitado == Decimal("4.00")
    assert quitacao.funcionario_id == funcionario.id
    assert quitacao.autorizado_por_id == gerente.id
    assert isinstance(quitacao.quitado_em, datetime)


def test_quitar_acima_do_saldo_e_bloqueado(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario
):
    lancar_consumo(comandas, pagamentos, produto, 1, funcionario.id)

    with pytest.raises(RegraDeNegocioError):
        pagamentos.quitar(funcionario.id, Decimal("10.01"), PIN_GERENTE)

    assert pagamentos.calcular_saldo_devedor(funcionario.id) == Decimal("10.00")


def test_quitar_valor_zero_e_bloqueado(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario
):
    lancar_consumo(comandas, pagamentos, produto, 1, funcionario.id)

    with pytest.raises(RegraDeNegocioError):
        pagamentos.quitar(funcionario.id, Decimal("0.00"), PIN_GERENTE)


def test_quitar_valor_negativo_e_bloqueado(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario
):
    lancar_consumo(comandas, pagamentos, produto, 1, funcionario.id)

    with pytest.raises(RegraDeNegocioError):
        pagamentos.quitar(funcionario.id, Decimal("-1.00"), PIN_GERENTE)


def test_quitar_sem_divida_e_bloqueado(pagamentos, gerente, funcionario):
    with pytest.raises(RegraDeNegocioError):
        pagamentos.quitar(funcionario.id, Decimal("10.00"), PIN_GERENTE)


def test_quitar_com_pin_de_atendente(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario, atendente
):
    lancar_consumo(comandas, pagamentos, produto, 1, funcionario.id)

    with pytest.raises(AcessoNegadoError):
        pagamentos.quitar(funcionario.id, Decimal("5.00"), PIN_ATENDENTE)

    assert pagamentos.calcular_saldo_devedor(funcionario.id) == Decimal("10.00")


def test_quitar_com_pin_inexistente(
    pagamentos, comandas, gerente, caixa_aberto, produto, funcionario
):
    lancar_consumo(comandas, pagamentos, produto, 1, funcionario.id)

    with pytest.raises(NaoAutorizadoError):
        pagamentos.quitar(funcionario.id, Decimal("5.00"), PIN_INEXISTENTE)


def test_quitar_de_funcionario_inexistente(pagamentos, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        pagamentos.quitar(4242, Decimal("5.00"), PIN_GERENTE)
