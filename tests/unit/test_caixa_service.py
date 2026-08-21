from datetime import datetime
from decimal import Decimal

import pytest

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import (
    FormaPagamento,
    StatusCaixa,
    StatusComanda,
    TipoMovimento,
)
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.domain.movimento_caixa import MovimentoCaixa
from gestor_comercial.domain.pagamento import Pagamento
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.dinheiro import dinheiro
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from tests.conftest import PIN_ATENDENTE


@pytest.fixture
def caixas(uow, auth):
    return CaixaService(uow, auth)


def _nova_comanda(uow, caixa, funcionario, status=StatusComanda.ABERTA):
    return uow.comandas.salvar(
        Comanda(
            status=status,
            aberta_em=datetime(2026, 8, 20, 12, 0),
            funcionario_id=funcionario.id,
            caixa_id=caixa.id,
        )
    )


def _novo_item(uow, comanda, produto, quantidade=1):
    return uow.itens.salvar(
        ItemComanda(
            quantidade=quantidade,
            preco_unit_congelado=produto.preco,
            comanda_id=comanda.id,
            produto_id=produto.id,
        )
    )


def _novo_pagamento(uow, comanda, forma, valor, troco=None):
    """Pagamento gravado direto pelo repository — o pagamento_service não é o alvo deste teste."""
    return uow.pagamentos.salvar(
        Pagamento(
            forma=forma,
            valor=dinheiro(valor),
            troco=None if troco is None else dinheiro(troco),
            registrado_em=datetime(2026, 8, 20, 12, 30),
            comanda_id=comanda.id,
        )
    )


def _caixa_fechado(uow, valor_abertura="50.00", fechado_em=datetime(2026, 8, 19, 23, 0)):
    return uow.caixas.salvar(
        Caixa(
            status=StatusCaixa.FECHADO,
            valor_abertura=dinheiro(valor_abertura),
            valor_contado=dinheiro(valor_abertura),
            aberto_em=datetime(2026, 8, 19, 8, 0),
            fechado_em=fechado_em,
        )
    )


# ----------------------------------------------------------------------
# abrir
# ----------------------------------------------------------------------


def test_abrir_cria_caixa_aberto_com_fundo_de_troco(uow, caixas, gerente):
    caixa = caixas.abrir(Decimal("150.00"))

    assert caixa.id is not None
    assert caixa.status is StatusCaixa.ABERTO
    assert caixa.valor_abertura == Decimal("150.00")
    assert caixa.aberto_em is not None
    assert caixa.fechado_em is None
    assert uow.caixas.buscar_aberto().id == caixa.id


def test_abrir_arredonda_o_valor_para_centavos(caixas, gerente):
    assert caixas.abrir(Decimal("150.005")).valor_abertura == Decimal("150.01")


def test_abrir_aceita_gaveta_zerada(caixas, gerente):
    assert caixas.abrir(Decimal("0")).valor_abertura == Decimal("0.00")


def test_abrir_bloqueia_se_ja_existe_caixa_aberto(caixas, gerente, caixa_aberto):
    with pytest.raises(RegraDeNegocioError):
        caixas.abrir(Decimal("100.00"))


def test_abrir_recusa_valor_negativo_e_nao_grava(uow, caixas, gerente):
    with pytest.raises(RegraDeNegocioError):
        caixas.abrir(Decimal("-1.00"))
    assert uow.caixas.listar_todos() == []


def test_abrir_recusa_valor_em_texto_invalido(caixas, gerente):
    with pytest.raises(RegraDeNegocioError):
        caixas.abrir("cem reais")


def test_abrir_recusa_valor_ausente(caixas, gerente):
    with pytest.raises(RegraDeNegocioError):
        caixas.abrir(None)


def test_abrir_recusa_float(caixas, gerente):
    # Dinheiro em float é erro de programação da tela, não do operador: estoura
    # TypeError em vez de virar mensagem amigável e passar despercebido.
    with pytest.raises(TypeError):
        caixas.abrir(150.0)


def test_abrir_negado_para_atendente(caixas, auth, gerente, atendente):
    auth.login(PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        caixas.abrir(Decimal("100.00"))


def test_abrir_exige_alguem_logado(caixas):
    with pytest.raises(NaoAutorizadoError):
        caixas.abrir(Decimal("100.00"))


# ----------------------------------------------------------------------
# fechar
# ----------------------------------------------------------------------


def test_fechar_grava_contagem_e_observacao(caixas, gerente, caixa_aberto):
    caixa = caixas.fechar(caixa_aberto.id, Decimal("180.00"), "Faltou trocado de 2 reais")

    assert caixa.status is StatusCaixa.FECHADO
    assert caixa.valor_contado == Decimal("180.00")
    assert caixa.observacao_fechamento == "Faltou trocado de 2 reais"
    assert caixa.fechado_em is not None


def test_fechar_sem_observacao_deixa_o_campo_nulo(caixas, gerente, caixa_aberto):
    assert caixas.fechar(caixa_aberto.id, Decimal("100.00"), "   ").observacao_fechamento is None


def test_fechar_bloqueia_caixa_ja_fechado(caixas, gerente, caixa_aberto):
    caixas.fechar(caixa_aberto.id, Decimal("100.00"))
    with pytest.raises(RegraDeNegocioError):
        caixas.fechar(caixa_aberto.id, Decimal("100.00"))


def test_fechar_recusa_valor_contado_negativo(caixas, gerente, caixa_aberto):
    with pytest.raises(RegraDeNegocioError):
        caixas.fechar(caixa_aberto.id, Decimal("-0.01"))
    assert caixa_aberto.status is StatusCaixa.ABERTO


def test_fechar_bloqueia_com_comanda_aberta_e_diz_quantas(
    uow, caixas, gerente, caixa_aberto, produto
):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_item(uow, comanda, produto)

    with pytest.raises(RegraDeNegocioError, match="1 comanda aberta"):
        caixas.fechar(caixa_aberto.id, Decimal("100.00"))
    assert caixa_aberto.status is StatusCaixa.ABERTO


def test_fechar_pluraliza_a_contagem_de_comandas_abertas(
    uow, caixas, gerente, caixa_aberto, produto
):
    for _ in range(2):
        comanda = _nova_comanda(uow, caixa_aberto, gerente)
        _novo_item(uow, comanda, produto)

    with pytest.raises(RegraDeNegocioError, match="2 comandas abertas"):
        caixas.fechar(caixa_aberto.id, Decimal("100.00"))


def test_fechar_ignora_comanda_aberta_sem_item(uow, caixas, gerente, caixa_aberto):
    # Rascunho: nasce quando o atendente toca na mesa e desiste antes de
    # lançar qualquer item. Invisível em ComandaService.listar_abertas(), então
    # bloquear o fechamento por causa dela deixaria o caixa impossível de
    # fechar (o gerente não teria como achá-la em tela nenhuma).
    _nova_comanda(uow, caixa_aberto, gerente)

    assert caixas.fechar(caixa_aberto.id, Decimal("100.00")).status is StatusCaixa.FECHADO


def test_fechar_ignora_comandas_fechadas_e_canceladas(uow, caixas, gerente, caixa_aberto):
    _nova_comanda(uow, caixa_aberto, gerente, status=StatusComanda.FECHADA)
    _nova_comanda(uow, caixa_aberto, gerente, status=StatusComanda.CANCELADA)

    assert caixas.fechar(caixa_aberto.id, Decimal("100.00")).status is StatusCaixa.FECHADO


def test_fechar_ignora_comanda_aberta_de_outro_caixa(uow, caixas, gerente, caixa_aberto):
    outro = _caixa_fechado(uow)
    _nova_comanda(uow, outro, gerente)

    assert caixas.fechar(caixa_aberto.id, Decimal("100.00")).status is StatusCaixa.FECHADO


def test_fechar_caixa_inexistente(caixas, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.fechar(999, Decimal("100.00"))


def test_fechar_negado_para_atendente(caixas, auth, gerente, atendente, caixa_aberto):
    auth.login(PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        caixas.fechar(caixa_aberto.id, Decimal("100.00"))


# ----------------------------------------------------------------------
# buscar / buscar_aberto / buscar_ultimo_fechado
# ----------------------------------------------------------------------


def test_buscar_devolve_o_caixa(caixas, caixa_aberto):
    assert caixas.buscar(caixa_aberto.id).id == caixa_aberto.id


def test_buscar_caixa_inexistente(caixas):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.buscar(999)


def test_buscar_aberto_devolve_o_caixa_do_dia(caixas, caixa_aberto):
    assert caixas.buscar_aberto().id == caixa_aberto.id


def test_buscar_aberto_sem_caixa_aberto(caixas):
    with pytest.raises(RegraDeNegocioError):
        caixas.buscar_aberto()


def test_buscar_ultimo_fechado_devolve_o_mais_recente(uow, caixas):
    _caixa_fechado(uow, fechado_em=datetime(2026, 8, 18, 23, 0))
    recente = _caixa_fechado(uow, fechado_em=datetime(2026, 8, 19, 23, 0))

    assert caixas.buscar_ultimo_fechado().id == recente.id


def test_buscar_ultimo_fechado_sem_nenhum_fechamento(caixas, caixa_aberto):
    with pytest.raises(RegraDeNegocioError):
        caixas.buscar_ultimo_fechado()


# ----------------------------------------------------------------------
# registrar_movimento
# ----------------------------------------------------------------------


def test_registrar_reforco_vincula_caixa_aberto_e_quem_registrou(caixas, gerente, caixa_aberto):
    movimento = caixas.registrar_movimento(TipoMovimento.REFORCO, Decimal("50.00"), "Troco extra")

    assert movimento.id is not None
    assert movimento.tipo is TipoMovimento.REFORCO
    assert movimento.valor == Decimal("50.00")
    assert movimento.descricao == "Troco extra"
    assert movimento.caixa_id == caixa_aberto.id
    assert movimento.funcionario_id == gerente.id
    assert movimento.registrado_em is not None


def test_registrar_reforco_liberado_para_atendente(caixas, auth, gerente, atendente, caixa_aberto):
    auth.login(PIN_ATENDENTE)
    movimento = caixas.registrar_movimento(TipoMovimento.REFORCO, Decimal("20.00"))

    assert movimento.funcionario_id == atendente.id
    assert movimento.descricao is None


def test_registrar_consumo_funcionario_e_sempre_bloqueado(
    caixas, auth, gerente, atendente, caixa_aberto
):
    # Consumo interno é registrado por PagamentoService.registrar (forma
    # CONSUMO_INTERNO), nunca como MovimentoCaixa — senão a mesma dívida
    # desconta da gaveta duas vezes. Bloqueado tanto pro gerente quanto pro
    # atendente: não é questão de permissão, é tipo de movimento inexistente
    # nesta operação.
    with pytest.raises(RegraDeNegocioError):
        caixas.registrar_movimento(TipoMovimento.CONSUMO_FUNCIONARIO, Decimal("12.50"))

    auth.login(PIN_ATENDENTE)
    with pytest.raises(RegraDeNegocioError):
        caixas.registrar_movimento(TipoMovimento.CONSUMO_FUNCIONARIO, Decimal("12.50"))


def test_registrar_sangria_e_despesa_pelo_gerente(caixas, gerente, caixa_aberto):
    assert caixas.registrar_movimento(TipoMovimento.SANGRIA, Decimal("30.00")).valor == Decimal(
        "30.00"
    )
    assert caixas.registrar_movimento(
        TipoMovimento.DESPESA, Decimal("15.00"), "Gelo"
    ).valor == Decimal("15.00")


def test_registrar_sangria_negada_para_atendente(caixas, auth, gerente, atendente, caixa_aberto):
    auth.login(PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        caixas.registrar_movimento(TipoMovimento.SANGRIA, Decimal("30.00"))


def test_registrar_despesa_negada_para_atendente(caixas, auth, gerente, atendente, caixa_aberto):
    auth.login(PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        caixas.registrar_movimento(TipoMovimento.DESPESA, Decimal("30.00"))


def test_registrar_movimento_recusa_valor_zero(caixas, gerente, caixa_aberto):
    with pytest.raises(RegraDeNegocioError):
        caixas.registrar_movimento(TipoMovimento.REFORCO, Decimal("0.00"))


def test_registrar_movimento_recusa_valor_negativo_e_nao_grava(
    uow, caixas, gerente, caixa_aberto
):
    with pytest.raises(RegraDeNegocioError):
        caixas.registrar_movimento(TipoMovimento.REFORCO, Decimal("-5.00"))
    assert uow.movimentos.listar_por_caixa(caixa_aberto.id) == []


def test_registrar_movimento_recusa_tipo_invalido(caixas, gerente, caixa_aberto):
    with pytest.raises(RegraDeNegocioError):
        caixas.registrar_movimento("SANGRIA", Decimal("10.00"))


def test_registrar_movimento_sem_caixa_aberto(caixas, gerente):
    with pytest.raises(RegraDeNegocioError):
        caixas.registrar_movimento(TipoMovimento.REFORCO, Decimal("10.00"))


def test_registrar_movimento_exige_alguem_logado(caixas, auth, gerente, caixa_aberto):
    auth.logout()
    with pytest.raises(NaoAutorizadoError):
        caixas.registrar_movimento(TipoMovimento.REFORCO, Decimal("10.00"))


# ----------------------------------------------------------------------
# listar_movimentos
# ----------------------------------------------------------------------


def test_listar_movimentos_traz_so_os_do_caixa(uow, caixas, gerente, caixa_aberto):
    caixas.registrar_movimento(TipoMovimento.REFORCO, Decimal("50.00"))
    caixas.registrar_movimento(TipoMovimento.SANGRIA, Decimal("30.00"))
    outro = _caixa_fechado(uow)
    uow.movimentos.salvar(
        MovimentoCaixa(
            tipo=TipoMovimento.REFORCO,
            valor=Decimal("99.00"),
            registrado_em=datetime(2026, 8, 19, 10, 0),
            caixa_id=outro.id,
            funcionario_id=gerente.id,
        )
    )

    movimentos = caixas.listar_movimentos(caixa_aberto.id)

    assert [m.tipo for m in movimentos] == [TipoMovimento.REFORCO, TipoMovimento.SANGRIA]


def test_listar_movimentos_de_caixa_inexistente(caixas):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.listar_movimentos(999)


# ----------------------------------------------------------------------
# calcular_saldo_esperado
# ----------------------------------------------------------------------


def test_saldo_esperado_soma_abertura_movimentos_e_dinheiro(uow, caixas, gerente, caixa_aberto):
    caixas.registrar_movimento(TipoMovimento.REFORCO, Decimal("50.00"))
    caixas.registrar_movimento(TipoMovimento.SANGRIA, Decimal("30.00"))
    caixas.registrar_movimento(TipoMovimento.DESPESA, Decimal("20.00"))
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_pagamento(uow, comanda, FormaPagamento.DINHEIRO, "36.00")

    # 100 + 50 − 30 − 20 + 36
    assert caixas.calcular_saldo_esperado(caixa_aberto.id) == Decimal("136.00")


def test_saldo_esperado_nao_desconta_troco_de_novo(uow, caixas, gerente, caixa_aberto):
    # Conta de 36 paga com nota de 50: a gaveta recebeu 50 e devolveu 14 de troco,
    # ou seja, ficou 36 a mais — que é exatamente `Pagamento.valor`.
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_pagamento(uow, comanda, FormaPagamento.DINHEIRO, "36.00", troco="14.00")

    assert caixas.calcular_saldo_esperado(caixa_aberto.id) == Decimal("136.00")


def test_saldo_esperado_ignora_maquininha_e_consumo_interno(uow, caixas, gerente, caixa_aberto):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_pagamento(uow, comanda, FormaPagamento.CREDITO, "40.00")
    _novo_pagamento(uow, comanda, FormaPagamento.PIX, "25.00")
    _novo_pagamento(uow, comanda, FormaPagamento.CONSUMO_INTERNO, "18.00")

    assert caixas.calcular_saldo_esperado(caixa_aberto.id) == Decimal("100.00")


def test_saldo_esperado_ignora_pagamento_de_outro_caixa(uow, caixas, gerente, caixa_aberto):
    outro = _caixa_fechado(uow)
    comanda_alheia = _nova_comanda(uow, outro, gerente, status=StatusComanda.FECHADA)
    _novo_pagamento(uow, comanda_alheia, FormaPagamento.DINHEIRO, "70.00")

    assert caixas.calcular_saldo_esperado(caixa_aberto.id) == Decimal("100.00")


def test_saldo_esperado_de_caixa_inexistente(caixas):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.calcular_saldo_esperado(999)


# ----------------------------------------------------------------------
# calcular_vendas_maquininha
# ----------------------------------------------------------------------


def test_vendas_maquininha_soma_credito_debito_e_pix(uow, caixas, gerente, caixa_aberto):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_pagamento(uow, comanda, FormaPagamento.CREDITO, "40.00")
    _novo_pagamento(uow, comanda, FormaPagamento.DEBITO, "15.50")
    _novo_pagamento(uow, comanda, FormaPagamento.PIX, "25.00")
    _novo_pagamento(uow, comanda, FormaPagamento.DINHEIRO, "10.00")
    _novo_pagamento(uow, comanda, FormaPagamento.CONSUMO_INTERNO, "12.00")

    assert caixas.calcular_vendas_maquininha(caixa_aberto.id) == Decimal("80.50")


def test_vendas_maquininha_zerada_quando_nao_houve_venda(caixas, caixa_aberto):
    assert caixas.calcular_vendas_maquininha(caixa_aberto.id) == Decimal("0.00")


def test_vendas_maquininha_ignora_outro_caixa(uow, caixas, gerente, caixa_aberto):
    outro = _caixa_fechado(uow)
    comanda_alheia = _nova_comanda(uow, outro, gerente, status=StatusComanda.FECHADA)
    _novo_pagamento(uow, comanda_alheia, FormaPagamento.CREDITO, "99.00")

    assert caixas.calcular_vendas_maquininha(caixa_aberto.id) == Decimal("0.00")


def test_vendas_maquininha_de_caixa_inexistente(caixas):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.calcular_vendas_maquininha(999)


# ----------------------------------------------------------------------
# resumo
# ----------------------------------------------------------------------


def test_resumo_de_caixa_aberto_nao_tem_diferenca(uow, caixas, gerente, caixa_aberto):
    caixas.registrar_movimento(TipoMovimento.REFORCO, Decimal("50.00"))
    caixas.registrar_movimento(TipoMovimento.SANGRIA, Decimal("30.00"))
    caixas.registrar_movimento(TipoMovimento.DESPESA, Decimal("20.00"))
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_pagamento(uow, comanda, FormaPagamento.DINHEIRO, "36.00", troco="14.00")
    _novo_pagamento(uow, comanda, FormaPagamento.CREDITO, "40.00")
    _novo_pagamento(uow, comanda, FormaPagamento.CONSUMO_INTERNO, "18.00")

    resumo = caixas.resumo(caixa_aberto.id)

    assert resumo.caixa_id == caixa_aberto.id
    assert resumo.valor_abertura == Decimal("100.00")
    assert resumo.total_dinheiro == Decimal("36.00")
    assert resumo.total_maquininha == Decimal("40.00")
    assert resumo.total_consumo_interno == Decimal("18.00")
    assert resumo.reforcos == Decimal("50.00")
    assert resumo.sangrias == Decimal("30.00")
    assert resumo.despesas == Decimal("20.00")
    assert resumo.saldo_esperado == Decimal("136.00")
    assert resumo.valor_contado is None
    assert resumo.diferenca is None


def test_resumo_zerado_logo_apos_a_abertura(caixas, caixa_aberto):
    resumo = caixas.resumo(caixa_aberto.id)

    assert resumo.total_dinheiro == Decimal("0.00")
    assert resumo.total_maquininha == Decimal("0.00")
    assert resumo.total_consumo_interno == Decimal("0.00")
    assert resumo.reforcos == Decimal("0.00")
    assert resumo.sangrias == Decimal("0.00")
    assert resumo.despesas == Decimal("0.00")
    assert resumo.saldo_esperado == Decimal("100.00")


def test_resumo_acusa_falta_na_gaveta(uow, caixas, gerente, caixa_aberto):
    comanda = _nova_comanda(uow, caixa_aberto, gerente, status=StatusComanda.FECHADA)
    _novo_pagamento(uow, comanda, FormaPagamento.DINHEIRO, "36.00")
    caixas.fechar(caixa_aberto.id, Decimal("130.00"))

    resumo = caixas.resumo(caixa_aberto.id)

    assert resumo.saldo_esperado == Decimal("136.00")
    assert resumo.valor_contado == Decimal("130.00")
    assert resumo.diferenca == Decimal("-6.00")


def test_resumo_acusa_sobra_na_gaveta(caixas, gerente, caixa_aberto):
    caixas.fechar(caixa_aberto.id, Decimal("102.50"))

    assert caixas.resumo(caixa_aberto.id).diferenca == Decimal("2.50")


def test_resumo_de_caixa_inexistente(caixas):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.resumo(999)
