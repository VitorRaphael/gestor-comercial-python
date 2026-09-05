import json
from datetime import date, datetime
from decimal import Decimal

import pytest

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import (
    FormaPagamento,
    PerfilUsuario,
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
    TurnoAnteriorPendenteError,
)
from gestor_comercial.services.loja_config_service import (
    SENHA_MASTER_PADRAO,
    SENHA_OPERACIONAL_PADRAO,
)
from tests.conftest import PIN_ATENDENTE


@pytest.fixture
def caixas(uow, auth):
    return CaixaService(uow, auth)


def _nova_comanda(uow, caixa, usuario, status=StatusComanda.ABERTA):
    return uow.comandas.salvar(
        Comanda(
            status=status,
            aberta_em=datetime(2026, 8, 20, 12, 0),
            usuario_id=usuario.id,
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


def _caixa_fechado(
    uow, valor_abertura="50.00", fechado_em=datetime(2026, 8, 19, 23, 0), resumo_produtos=None
):
    """`resumo_produtos`: lista de `(nome, quantidade, valor_total_str)` para simular
    o que `CaixaService.fechar` gravaria em `resumo_produtos_json` de verdade —
    esses testes constroem o `Caixa` direto pelo repository, sem passar por `fechar`."""
    snapshot = None
    if resumo_produtos is not None:
        snapshot = json.dumps(
            [
                {"produto_nome": nome, "quantidade": quantidade, "valor_total": valor_total}
                for nome, quantidade, valor_total in resumo_produtos
            ]
        )
    return uow.caixas.salvar(
        Caixa(
            status=StatusCaixa.FECHADO,
            valor_abertura=dinheiro(valor_abertura),
            valor_contado_dinheiro=dinheiro(valor_abertura),
            valor_contado_maquininha=dinheiro("0.00"),
            aberto_em=datetime(2026, 8, 19, 8, 0),
            fechado_em=fechado_em,
            resumo_produtos_json=snapshot,
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


def test_abrir_bloqueia_com_erro_especifico_de_turno_pendente(caixas, gerente, caixa_aberto):
    with pytest.raises(TurnoAnteriorPendenteError):
        caixas.abrir(Decimal("100.00"))


def test_abrir_recusa_fechamento_cego_com_senha_errada(caixas, gerente, caixa_aberto):
    with pytest.raises(RegraDeNegocioError):
        caixas.abrir(Decimal("100.00"), senha_fechamento_cego="000000")
    assert uow_caixa_ainda_aberto(caixas, caixa_aberto)


def test_abrir_com_senha_operacional_fecha_as_ciegas_e_abre_novo_turno(uow, caixas, gerente, caixa_aberto):
    novo = caixas.abrir(Decimal("100.00"), senha_fechamento_cego=SENHA_OPERACIONAL_PADRAO)

    anterior = uow.caixas.buscar_por_id(caixa_aberto.id)
    assert anterior.status is StatusCaixa.FECHADO
    assert anterior.valor_contado_dinheiro == Decimal("0.00")
    assert "cego" in anterior.observacao_fechamento.lower()

    assert novo.status is StatusCaixa.ABERTO
    assert uow.caixas.buscar_aberto().id == novo.id


def test_abrir_com_senha_master_tambem_autoriza_fechamento_cego(uow, caixas, gerente, caixa_aberto):
    novo = caixas.abrir(Decimal("100.00"), senha_fechamento_cego=SENHA_MASTER_PADRAO)
    assert novo.status is StatusCaixa.ABERTO


def test_abrir_com_fechamento_cego_ignora_comanda_aberta_esquecida(
    uow, caixas, gerente, caixa_aberto, produto
):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    uow.itens.salvar(
        ItemComanda(
            comanda_id=comanda.id,
            produto_id=produto.id,
            quantidade=1,
            preco_unit_congelado=dinheiro("10.00"),
        )
    )
    uow.commit()

    novo = caixas.abrir(Decimal("100.00"), senha_fechamento_cego=SENHA_OPERACIONAL_PADRAO)
    assert novo.status is StatusCaixa.ABERTO


def uow_caixa_ainda_aberto(caixas, caixa) -> bool:
    return caixas.uow.caixas.buscar_por_id(caixa.id).status is StatusCaixa.ABERTO


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
    caixa = caixas.fechar(caixa_aberto.id, Decimal("180.00"), dinheiro("0.00"), "Faltou trocado de 2 reais")

    assert caixa.status is StatusCaixa.FECHADO
    assert caixa.valor_contado_dinheiro == Decimal("180.00")
    assert caixa.observacao_fechamento == "Faltou trocado de 2 reais"
    assert caixa.fechado_em is not None


def test_fechar_sem_observacao_deixa_o_campo_nulo(caixas, gerente, caixa_aberto):
    assert caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00"), "   ").observacao_fechamento is None


def test_fechar_bloqueia_caixa_ja_fechado(caixas, gerente, caixa_aberto):
    caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00"))
    with pytest.raises(RegraDeNegocioError):
        caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00"))


def test_fechar_recusa_valor_contado_negativo(caixas, gerente, caixa_aberto):
    with pytest.raises(RegraDeNegocioError):
        caixas.fechar(caixa_aberto.id, Decimal("-0.01"), dinheiro("0.00"))
    assert caixa_aberto.status is StatusCaixa.ABERTO


def test_fechar_bloqueia_com_comanda_aberta_e_diz_quantas(
    uow, caixas, gerente, caixa_aberto, produto
):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_item(uow, comanda, produto)

    with pytest.raises(RegraDeNegocioError, match="1 comanda aberta"):
        caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00"))
    assert caixa_aberto.status is StatusCaixa.ABERTO


def test_fechar_pluraliza_a_contagem_de_comandas_abertas(
    uow, caixas, gerente, caixa_aberto, produto
):
    for _ in range(2):
        comanda = _nova_comanda(uow, caixa_aberto, gerente)
        _novo_item(uow, comanda, produto)

    with pytest.raises(RegraDeNegocioError, match="2 comandas abertas"):
        caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00"))


def test_fechar_bloqueia_com_comanda_em_conferencia(uow, caixas, gerente, caixa_aberto, produto):
    """Pré-conta emitida não é pagamento recebido — mesma trava de comanda ABERTA."""
    comanda = _nova_comanda(uow, caixa_aberto, gerente, status=StatusComanda.EM_CONFERENCIA)
    _novo_item(uow, comanda, produto)

    with pytest.raises(RegraDeNegocioError, match="1 comanda aberta"):
        caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00"))


def test_fechar_ignora_comanda_aberta_sem_item(uow, caixas, gerente, caixa_aberto):
    # Rascunho: nasce quando o atendente toca na mesa e desiste antes de
    # lançar qualquer item. Invisível em ComandaService.listar_abertas(), então
    # bloquear o fechamento por causa dela deixaria o caixa impossível de
    # fechar (o gerente não teria como achá-la em tela nenhuma).
    _nova_comanda(uow, caixa_aberto, gerente)

    assert caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00")).status is StatusCaixa.FECHADO


def test_fechar_ignora_comandas_fechadas_e_canceladas(uow, caixas, gerente, caixa_aberto):
    _nova_comanda(uow, caixa_aberto, gerente, status=StatusComanda.FECHADA)
    _nova_comanda(uow, caixa_aberto, gerente, status=StatusComanda.CANCELADA)

    assert caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00")).status is StatusCaixa.FECHADO


def test_fechar_ignora_comanda_aberta_de_outro_caixa(uow, caixas, gerente, caixa_aberto):
    outro = _caixa_fechado(uow)
    _nova_comanda(uow, outro, gerente)

    assert caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00")).status is StatusCaixa.FECHADO


def test_fechar_caixa_inexistente(caixas, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.fechar(999, Decimal("100.00"), dinheiro("0.00"))


def test_fechar_negado_para_atendente(caixas, auth, gerente, atendente, caixa_aberto):
    auth.login(PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00"))


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
    assert movimento.usuario_id == gerente.id
    assert movimento.registrado_em is not None


def test_registrar_reforco_liberado_para_atendente(caixas, auth, gerente, atendente, caixa_aberto):
    auth.login(PIN_ATENDENTE)
    movimento = caixas.registrar_movimento(TipoMovimento.REFORCO, Decimal("20.00"))

    assert movimento.usuario_id == atendente.id
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
            usuario_id=gerente.id,
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
    assert resumo.valor_contado_dinheiro is None
    assert resumo.diferenca_dinheiro is None
    assert resumo.valor_contado_maquininha is None
    assert resumo.diferenca_maquininha is None


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
    caixas.fechar(caixa_aberto.id, Decimal("130.00"), dinheiro("0.00"))

    resumo = caixas.resumo(caixa_aberto.id)

    assert resumo.saldo_esperado == Decimal("136.00")
    assert resumo.valor_contado_dinheiro == Decimal("130.00")
    assert resumo.diferenca_dinheiro == Decimal("-6.00")


def test_resumo_acusa_sobra_na_gaveta(caixas, gerente, caixa_aberto):
    caixas.fechar(caixa_aberto.id, Decimal("102.50"), dinheiro("0.00"))

    assert caixas.resumo(caixa_aberto.id).diferenca_dinheiro == Decimal("2.50")


def test_resumo_de_caixa_inexistente(caixas):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.resumo(999)


# ----------------------------------------------------------------------
# abrir/fechar gravam quem operou cada ponta do turno
# ----------------------------------------------------------------------


def test_abrir_grava_quem_abriu(caixas, gerente):
    caixa = caixas.abrir(Decimal("100.00"))
    assert caixa.aberto_por_id == gerente.id


def test_fechar_grava_quem_fechou(caixas, gerente, caixa_aberto):
    caixa = caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00"))
    assert caixa.fechado_por_id == gerente.id


# ----------------------------------------------------------------------
# sequência diária de fechamentos (indexada por fechado_em, não aberto_em)
# ----------------------------------------------------------------------


def test_fechar_numera_o_primeiro_fechamento_do_dia(caixas, gerente, caixa_aberto):
    caixa = caixas.fechar(caixa_aberto.id, Decimal("100.00"), dinheiro("0.00"))
    assert caixa.numero_sequencial_dia == 1


def test_fechar_numera_sequencialmente_dentro_do_mesmo_dia(uow, auth, caixas, gerente):
    primeiro = caixas.abrir(Decimal("100.00"))
    caixas.fechar(primeiro.id, Decimal("100.00"), dinheiro("0.00"))
    segundo = caixas.abrir(Decimal("50.00"))

    fechado = caixas.fechar(segundo.id, Decimal("50.00"), dinheiro("0.00"))

    assert fechado.numero_sequencial_dia == 2


def test_fechar_nao_recalcula_a_sequencia_de_fechamentos_ja_gravados(
    uow, auth, caixas, gerente
):
    primeiro = caixas.fechar(caixas.abrir(Decimal("100.00")).id, Decimal("100.00"), dinheiro("0.00"))
    caixas.fechar(caixas.abrir(Decimal("50.00")).id, Decimal("50.00"), dinheiro("0.00"))

    # O 1º fechamento do dia continua sendo o 1º mesmo depois de um segundo
    # caixa ser aberto e fechado — a numeração é imutável assim que gravada.
    assert uow.caixas.buscar_por_id(primeiro.id).numero_sequencial_dia == 1


def test_contar_fechados_no_dia_conta_pela_data_de_fechado_em_nao_de_aberto_em(uow):
    # Caixa aberto dia 29 às 17h e fechado dia 30 às 01h: é fechamento do dia
    # 30, não do dia 29 — o exato cenário de virada de madrugada da regra.
    virada_de_noite = _caixa_fechado(
        uow,
        fechado_em=datetime(2026, 8, 30, 1, 0),
    )
    _caixa_fechado(uow, fechado_em=datetime(2026, 8, 29, 20, 0))

    assert uow.caixas.contar_fechados_no_dia(date(2026, 8, 30)) == 1
    assert uow.caixas.contar_fechados_no_dia(date(2026, 8, 29)) == 1
    assert virada_de_noite.numero_sequencial_dia is None  # não passou por fechar()


def test_contar_fechados_no_dia_ignora_caixa_aberto(uow, caixa_aberto):
    assert uow.caixas.contar_fechados_no_dia(date.today()) == 0


# ----------------------------------------------------------------------
# titulo_fechamento
# ----------------------------------------------------------------------


def test_titulo_fechamento_monta_a_identificacao_oficial(uow):
    caixa = _caixa_fechado(uow, fechado_em=datetime(2026, 8, 30, 1, 0))
    caixa.numero_sequencial_dia = 1
    uow.caixas.salvar(caixa)
    uow.commit()

    servico = CaixaService(uow, None)
    assert servico.titulo_fechamento(caixa.id) == "1º Fechamento do dia 30/08/2026"


def test_titulo_fechamento_de_caixa_ainda_aberto(caixas, caixa_aberto):
    with pytest.raises(RegraDeNegocioError):
        caixas.titulo_fechamento(caixa_aberto.id)


def test_titulo_fechamento_de_caixa_inexistente(caixas):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.titulo_fechamento(999)


# ----------------------------------------------------------------------
# listar_historico
# ----------------------------------------------------------------------


def test_listar_historico_traz_so_os_fechados_do_mais_recente_pro_mais_antigo(
    uow, caixas, caixa_aberto
):
    antigo = _caixa_fechado(uow, fechado_em=datetime(2026, 8, 18, 23, 0))
    recente = _caixa_fechado(uow, fechado_em=datetime(2026, 8, 19, 23, 0))

    historico = caixas.listar_historico()

    assert [c.id for c in historico] == [recente.id, antigo.id]
    assert caixa_aberto.id not in [c.id for c in historico]


def test_listar_historico_filtra_por_periodo(uow, caixas):
    _caixa_fechado(uow, fechado_em=datetime(2026, 8, 18, 23, 0))
    dentro = _caixa_fechado(uow, fechado_em=datetime(2026, 8, 19, 23, 0))
    _caixa_fechado(uow, fechado_em=datetime(2026, 8, 20, 23, 0))

    historico = caixas.listar_historico(
        inicio=date(2026, 8, 19), fim=date(2026, 8, 19)
    )

    assert [c.id for c in historico] == [dentro.id]


def test_listar_historico_filtra_por_operador_abertura_ou_fechamento(uow, auth, gerente):
    abriu = auth.criar_usuario("Quem Abriu", "444444", PerfilUsuario.OPERADOR_CAIXA)
    fechou = auth.criar_usuario("Quem Fechou", "555555", PerfilUsuario.OPERADOR_CAIXA)
    de_outro = auth.criar_usuario("Outro", "666666", PerfilUsuario.OPERADOR_CAIXA)

    caixa_do_abridor = uow.caixas.salvar(
        Caixa(
            status=StatusCaixa.FECHADO,
            valor_abertura=dinheiro("50.00"),
            valor_contado_dinheiro=dinheiro("50.00"),
            aberto_em=datetime(2026, 8, 19, 8, 0),
            fechado_em=datetime(2026, 8, 19, 23, 0),
            aberto_por_id=abriu.id,
            fechado_por_id=de_outro.id,
        )
    )
    caixa_do_fechador = uow.caixas.salvar(
        Caixa(
            status=StatusCaixa.FECHADO,
            valor_abertura=dinheiro("50.00"),
            valor_contado_dinheiro=dinheiro("50.00"),
            aberto_em=datetime(2026, 8, 19, 8, 0),
            fechado_em=datetime(2026, 8, 19, 23, 0),
            aberto_por_id=de_outro.id,
            fechado_por_id=fechou.id,
        )
    )
    uow.commit()

    servico = CaixaService(uow, auth)
    historico_abridor = servico.listar_historico(usuario_id=abriu.id)
    historico_fechador = servico.listar_historico(usuario_id=fechou.id)

    assert [c.id for c in historico_abridor] == [caixa_do_abridor.id]
    assert [c.id for c in historico_fechador] == [caixa_do_fechador.id]


def test_listar_historico_vazio_sem_nenhum_fechamento(caixas, caixa_aberto):
    assert caixas.listar_historico() == []


# ----------------------------------------------------------------------
# totais_por_forma
# ----------------------------------------------------------------------


def test_totais_por_forma_traz_so_as_formas_com_venda(uow, caixas, gerente, caixa_aberto):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_pagamento(uow, comanda, FormaPagamento.DINHEIRO, "36.00")
    _novo_pagamento(uow, comanda, FormaPagamento.PIX, "25.00")
    _novo_pagamento(uow, comanda, FormaPagamento.CREDITO, "40.00")

    totais = caixas.totais_por_forma(caixa_aberto.id)

    assert totais == {
        FormaPagamento.DINHEIRO: Decimal("36.00"),
        FormaPagamento.PIX: Decimal("25.00"),
        FormaPagamento.CREDITO: Decimal("40.00"),
    }


def test_totais_por_forma_vazio_sem_venda(caixas, caixa_aberto):
    assert caixas.totais_por_forma(caixa_aberto.id) == {}


def test_totais_por_forma_de_caixa_inexistente(caixas):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.totais_por_forma(999)


# ----------------------------------------------------------------------
# resumo_cancelamentos (§ Auditoria de Itens Cancelados)
# ----------------------------------------------------------------------


def _item_cancelado(uow, comanda, produto, gerente, *, quantidade=1, cancelado_em, motivo="Erro de lançamento"):
    return uow.itens.salvar(
        ItemComanda(
            quantidade=quantidade,
            preco_unit_congelado=produto.preco,
            cancelado=True,
            cancelado_em=cancelado_em,
            motivo_cancelamento=motivo,
            cancelado_por_id=gerente.id,
            comanda_id=comanda.id,
            produto_id=produto.id,
        )
    )


def test_resumo_cancelamentos_sem_nenhum_cancelamento(caixas, caixa_aberto):
    resumo = caixas.resumo_cancelamentos(caixa_aberto.id)

    assert resumo.caixa_id == caixa_aberto.id
    assert resumo.quantidade_total == 0
    assert resumo.valor_total == Decimal("0.00")
    assert resumo.por_produto == []
    assert resumo.detalhado == []


def test_resumo_cancelamentos_totaliza_quantidade_e_valor(uow, caixas, gerente, caixa_aberto, produto):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _item_cancelado(uow, comanda, produto, gerente, quantidade=2, cancelado_em=datetime(2026, 8, 20, 19, 0))
    _item_cancelado(uow, comanda, produto, gerente, quantidade=1, cancelado_em=datetime(2026, 8, 20, 19, 5))

    resumo = caixas.resumo_cancelamentos(caixa_aberto.id)

    # produto custa 10.00: 2 + 1 unidades cancelada = 3 un, 30.00 em impacto.
    assert resumo.quantidade_total == 3
    assert resumo.valor_total == Decimal("30.00")


def test_resumo_cancelamentos_consolida_por_produto(uow, caixas, gerente, caixa_aberto, categoria):
    from gestor_comercial.domain.produto import Produto

    x_burger = uow.produtos.salvar(Produto(nome="X-Burger Especial", preco=Decimal("28.00"), categoria_id=categoria.id))
    coca = uow.produtos.salvar(Produto(nome="Coca-Cola Lata", preco=Decimal("7.00"), categoria_id=categoria.id))
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _item_cancelado(uow, comanda, x_burger, gerente, quantidade=2, cancelado_em=datetime(2026, 8, 20, 19, 0))
    _item_cancelado(uow, comanda, coca, gerente, quantidade=4, cancelado_em=datetime(2026, 8, 20, 19, 10))

    resumo = caixas.resumo_cancelamentos(caixa_aberto.id)

    por_nome = {item.produto_nome: item for item in resumo.por_produto}
    assert por_nome["X-Burger Especial"].quantidade == 2
    assert por_nome["X-Burger Especial"].valor == Decimal("56.00")
    assert por_nome["Coca-Cola Lata"].quantidade == 4
    assert por_nome["Coca-Cola Lata"].valor == Decimal("28.00")


def test_resumo_cancelamentos_soma_o_mesmo_produto_cancelado_em_ocorrencias_separadas(
    uow, caixas, gerente, caixa_aberto, produto
):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _item_cancelado(uow, comanda, produto, gerente, cancelado_em=datetime(2026, 8, 20, 19, 0))
    _item_cancelado(uow, comanda, produto, gerente, cancelado_em=datetime(2026, 8, 20, 19, 30))

    resumo = caixas.resumo_cancelamentos(caixa_aberto.id)

    assert len(resumo.por_produto) == 1
    assert resumo.por_produto[0].quantidade == 2


def test_resumo_cancelamentos_detalhado_traz_origem_horario_e_autorizacao(
    uow, caixas, gerente, caixa_aberto, produto, mesa
):
    comanda_mesa = _nova_comanda(uow, caixa_aberto, gerente)
    comanda_mesa.mesa_id = mesa.id
    uow.comandas.salvar(comanda_mesa)
    _item_cancelado(
        uow, comanda_mesa, produto, gerente,
        cancelado_em=datetime(2026, 8, 20, 19, 42),
        motivo="Desistência do cliente",
    )
    comanda_balcao = _nova_comanda(uow, caixa_aberto, gerente)
    _item_cancelado(uow, comanda_balcao, produto, gerente, cancelado_em=datetime(2026, 8, 20, 20, 0))

    resumo = caixas.resumo_cancelamentos(caixa_aberto.id)

    assert len(resumo.detalhado) == 2
    da_mesa = resumo.detalhado[0]
    assert da_mesa.quando == datetime(2026, 8, 20, 19, 42)
    assert da_mesa.origem == "Mesa 01"
    assert da_mesa.produto_nome == produto.nome
    assert da_mesa.autorizado_por == "Gerente"
    assert da_mesa.motivo == "Desistência do cliente"
    assert resumo.detalhado[1].origem == f"Balcão #{comanda_balcao.id}"


def test_resumo_cancelamentos_ordena_cronologicamente(uow, caixas, gerente, caixa_aberto, produto):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _item_cancelado(uow, comanda, produto, gerente, cancelado_em=datetime(2026, 8, 20, 20, 0), motivo="Segundo")
    _item_cancelado(uow, comanda, produto, gerente, cancelado_em=datetime(2026, 8, 20, 19, 0), motivo="Primeiro")

    resumo = caixas.resumo_cancelamentos(caixa_aberto.id)

    assert [item.motivo for item in resumo.detalhado] == ["Primeiro", "Segundo"]


def test_resumo_cancelamentos_ignora_itens_nao_cancelados(uow, caixas, gerente, caixa_aberto, produto):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_item(uow, comanda, produto)

    resumo = caixas.resumo_cancelamentos(caixa_aberto.id)

    assert resumo.quantidade_total == 0


def test_resumo_cancelamentos_ignora_cancelamentos_de_outro_caixa(
    uow, caixas, gerente, caixa_aberto, produto
):
    outro = _caixa_fechado(uow)
    comanda_alheia = _nova_comanda(uow, outro, gerente, status=StatusComanda.FECHADA)
    _item_cancelado(uow, comanda_alheia, produto, gerente, cancelado_em=datetime(2026, 8, 19, 20, 0))

    resumo = caixas.resumo_cancelamentos(caixa_aberto.id)

    assert resumo.quantidade_total == 0


def test_resumo_cancelamentos_de_caixa_inexistente(caixas):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.resumo_cancelamentos(999)


# ----------------------------------------------------------------------
# resumo_vendas (ITENS VENDIDOS NO TURNO)
# ----------------------------------------------------------------------


def test_resumo_vendas_sem_nenhuma_venda(caixas, caixa_aberto):
    assert caixas.resumo_vendas(caixa_aberto.id) == []


def test_resumo_vendas_traz_quantidade_valor_unitario_e_subtotal(
    uow, caixas, gerente, caixa_aberto, produto
):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_item(uow, comanda, produto, quantidade=3)

    resumo = caixas.resumo_vendas(caixa_aberto.id)

    assert len(resumo) == 1
    item = resumo[0]
    assert item.produto_nome == produto.nome
    assert item.quantidade == 3
    assert item.valor_unitario == produto.preco
    assert item.valor_total == dinheiro(produto.preco * 3)


def test_resumo_vendas_consolida_por_produto(uow, caixas, gerente, caixa_aberto, categoria):
    from gestor_comercial.domain.produto import Produto

    x_burger = uow.produtos.salvar(
        Produto(nome="X-Burger Especial", preco=Decimal("28.00"), categoria_id=categoria.id)
    )
    coca = uow.produtos.salvar(
        Produto(nome="Coca-Cola Lata", preco=Decimal("7.00"), categoria_id=categoria.id)
    )
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_item(uow, comanda, x_burger, quantidade=8)
    _novo_item(uow, comanda, coca, quantidade=12)

    resumo = caixas.resumo_vendas(caixa_aberto.id)

    por_nome = {item.produto_nome: item for item in resumo}
    assert por_nome["X-Burger Especial"].quantidade == 8
    assert por_nome["X-Burger Especial"].valor_total == Decimal("224.00")
    assert por_nome["Coca-Cola Lata"].quantidade == 12
    assert por_nome["Coca-Cola Lata"].valor_total == Decimal("84.00")


def test_resumo_vendas_soma_o_mesmo_produto_lancado_em_pedidos_separados(
    uow, caixas, gerente, caixa_aberto, produto
):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _novo_item(uow, comanda, produto, quantidade=1)
    _novo_item(uow, comanda, produto, quantidade=2)

    resumo = caixas.resumo_vendas(caixa_aberto.id)

    assert len(resumo) == 1
    assert resumo[0].quantidade == 3


def test_resumo_vendas_ignora_itens_cancelados(uow, caixas, gerente, caixa_aberto, produto):
    comanda = _nova_comanda(uow, caixa_aberto, gerente)
    _item_cancelado(uow, comanda, produto, gerente, cancelado_em=datetime(2026, 8, 20, 19, 0))

    resumo = caixas.resumo_vendas(caixa_aberto.id)

    assert resumo == []


def test_resumo_vendas_ignora_vendas_de_outro_caixa(uow, caixas, gerente, caixa_aberto, produto):
    outro = _caixa_fechado(uow)
    comanda_alheia = _nova_comanda(uow, outro, gerente, status=StatusComanda.FECHADA)
    _novo_item(uow, comanda_alheia, produto)

    resumo = caixas.resumo_vendas(caixa_aberto.id)

    assert resumo == []


def test_resumo_vendas_de_caixa_inexistente(caixas):
    with pytest.raises(RecursoNaoEncontradoError):
        caixas.resumo_vendas(999)


# ------------------------------------------------------------------
# resumo_mensal (Dashboard Consolidado Mensal)
# ------------------------------------------------------------------


def test_resumo_mensal_sem_nenhum_fechamento_no_mes(caixas):
    resumo = caixas.resumo_mensal(2026, 8)

    assert resumo.ano == 2026
    assert resumo.mes == 8
    assert resumo.faturamento_bruto == Decimal("0")
    assert resumo.formas_pagamento == []
    assert resumo.turnos_fechados == 0
    assert resumo.ticket_medio == Decimal("0")
    assert resumo.cancelamentos_quantidade == 0
    assert resumo.ranking_produtos == []


def test_resumo_mensal_soma_faturamento_e_formas_de_pagamento(uow, caixas, gerente, produto):
    caixa = _caixa_fechado(uow, fechado_em=datetime(2026, 8, 10, 22, 0))
    comanda = _nova_comanda(uow, caixa, gerente, status=StatusComanda.FECHADA)
    _novo_item(uow, comanda, produto, quantidade=2)
    _novo_pagamento(uow, comanda, FormaPagamento.DINHEIRO, "30.00")
    _novo_pagamento(uow, comanda, FormaPagamento.CREDITO, "20.00")

    resumo = caixas.resumo_mensal(2026, 8)

    assert resumo.faturamento_bruto == Decimal("50.00")
    assert resumo.turnos_fechados == 1
    por_forma = {linha.forma: linha for linha in resumo.formas_pagamento}
    assert por_forma[FormaPagamento.DINHEIRO].valor == Decimal("30.00")
    assert por_forma[FormaPagamento.DINHEIRO].percentual == Decimal("60.00")
    assert por_forma[FormaPagamento.CREDITO].valor == Decimal("20.00")
    assert por_forma[FormaPagamento.CREDITO].percentual == Decimal("40.00")


def test_resumo_mensal_ignora_fechamentos_de_outro_mes(uow, caixas, gerente, produto):
    caixa_julho = _caixa_fechado(uow, fechado_em=datetime(2026, 7, 31, 22, 0))
    comanda = _nova_comanda(uow, caixa_julho, gerente, status=StatusComanda.FECHADA)
    _novo_pagamento(uow, comanda, FormaPagamento.DINHEIRO, "99.00")

    resumo = caixas.resumo_mensal(2026, 8)

    assert resumo.turnos_fechados == 0
    assert resumo.faturamento_bruto == Decimal("0")


def test_resumo_mensal_ticket_medio_conta_so_comandas_fechadas(uow, caixas, gerente, produto):
    caixa = _caixa_fechado(uow, fechado_em=datetime(2026, 8, 5, 22, 0))
    comanda_paga = _nova_comanda(uow, caixa, gerente, status=StatusComanda.FECHADA)
    _novo_pagamento(uow, comanda_paga, FormaPagamento.DINHEIRO, "40.00")
    # comanda aberta na mesma sessão não vira transação — não pode inflar o denominador
    _nova_comanda(uow, caixa, gerente, status=StatusComanda.ABERTA)

    resumo = caixas.resumo_mensal(2026, 8)

    assert resumo.ticket_medio == Decimal("40.00")


def test_resumo_mensal_ranking_le_o_snapshot_gravado_no_fechamento(uow, caixas, gerente, categoria):
    """O ranking mensal só soma o que está em `resumo_produtos_json` — não
    reconsulta `item_comanda`. Por isso o snapshot é gravado aqui como
    `fechar()` faria de verdade, e não deduzido a partir dos itens lançados."""
    from gestor_comercial.domain.produto import Produto

    x_burger = uow.produtos.salvar(
        Produto(nome="X-Burger", preco=Decimal("20.00"), categoria_id=categoria.id)
    )
    caixa_1 = _caixa_fechado(
        uow,
        fechado_em=datetime(2026, 8, 5, 22, 0),
        resumo_produtos=[("X-Burger", 3, "60.00")],
    )
    _nova_comanda(uow, caixa_1, gerente, status=StatusComanda.FECHADA)

    caixa_2 = _caixa_fechado(
        uow,
        fechado_em=datetime(2026, 8, 12, 22, 0),
        resumo_produtos=[("X-Burger", 5, "100.00")],
    )
    _nova_comanda(uow, caixa_2, gerente, status=StatusComanda.FECHADA)

    resumo = caixas.resumo_mensal(2026, 8)

    assert len(resumo.ranking_produtos) == 1
    assert resumo.ranking_produtos[0].produto_nome == "X-Burger"
    assert resumo.ranking_produtos[0].quantidade == 8
    assert resumo.ranking_produtos[0].valor_total == Decimal("160.00")


def test_resumo_mensal_ignora_fechamento_sem_snapshot(uow, caixas, gerente, produto):
    """Caixa fechado antes desta coluna existir (`resumo_produtos_json=None`)
    não derruba o ranking do mês — só fica de fora dele."""
    caixa = _caixa_fechado(uow, fechado_em=datetime(2026, 8, 5, 22, 0))
    _nova_comanda(uow, caixa, gerente, status=StatusComanda.FECHADA)

    resumo = caixas.resumo_mensal(2026, 8)

    assert resumo.ranking_produtos == []


def test_fechar_grava_o_snapshot_do_mix_de_vendas(uow, caixas, gerente, caixa_aberto, produto):
    comanda = _nova_comanda(uow, caixa_aberto, gerente, status=StatusComanda.FECHADA)
    _novo_item(uow, comanda, produto, quantidade=4)

    caixa_fechado = caixas.fechar(caixa_aberto.id, "0.00", dinheiro("0.00"))

    assert caixa_fechado.resumo_produtos_json is not None
    dados = json.loads(caixa_fechado.resumo_produtos_json)
    assert len(dados) == 1
    assert dados[0]["produto_nome"] == produto.nome
    assert dados[0]["quantidade"] == 4
    assert Decimal(dados[0]["valor_total"]) == dinheiro(produto.preco * 4)


def test_fechar_sem_nenhuma_venda_grava_snapshot_vazio(caixas, gerente, caixa_aberto):
    caixa_fechado = caixas.fechar(caixa_aberto.id, "0.00", dinheiro("0.00"))

    assert json.loads(caixa_fechado.resumo_produtos_json) == []


def test_resumo_mensal_soma_cancelamentos_entre_turnos(uow, caixas, gerente, produto):
    caixa = _caixa_fechado(uow, fechado_em=datetime(2026, 8, 5, 22, 0))
    comanda = _nova_comanda(uow, caixa, gerente, status=StatusComanda.FECHADA)
    _item_cancelado(uow, comanda, produto, gerente, cancelado_em=datetime(2026, 8, 5, 21, 0))

    resumo = caixas.resumo_mensal(2026, 8)

    assert resumo.cancelamentos_quantidade == 1
    assert resumo.cancelamentos_valor == produto.preco


# ----------------------------------------------------------------------
# fechamento_da_gaveta / ranking_por_atendente (§3.14)
# ----------------------------------------------------------------------


def test_fechamento_da_gaveta_identifica_turno_e_soma_saldo_apurado(uow, caixas, gerente, produto):
    caixa = _caixa_fechado(uow, valor_abertura="50.00", fechado_em=datetime(2026, 8, 5, 22, 0))
    caixa.numero_sequencial_dia = 1
    comanda = _nova_comanda(uow, caixa, gerente, status=StatusComanda.FECHADA)
    _novo_pagamento(uow, comanda, FormaPagamento.DINHEIRO, "30.00")
    uow.commit()

    gaveta = caixas.fechamento_da_gaveta(caixa.id)

    assert "T1" in gaveta.identificacao
    assert gaveta.total_faturado == dinheiro("30.00")
    assert gaveta.saldo_apurado == dinheiro("50.00")  # valor_contado_dinheiro do fixture + 0 maquininha
    assert gaveta.diferenca is not None


def test_ranking_por_atendente_agrupa_por_vendedor_e_calcula_percentual(uow, caixas, gerente, funcionarios):
    caixa = _caixa_fechado(uow, fechado_em=datetime(2026, 8, 5, 22, 0))
    ana = funcionarios.criar("Ana Beatriz", "Garçom")
    lucas = funcionarios.criar("Lucas Prado", "Garçom")

    comanda_ana = _nova_comanda(uow, caixa, gerente, status=StatusComanda.FECHADA)
    comanda_ana.atendente_id = ana.id
    _novo_pagamento(uow, comanda_ana, FormaPagamento.DINHEIRO, "60.00")

    comanda_lucas = _nova_comanda(uow, caixa, gerente, status=StatusComanda.FECHADA)
    comanda_lucas.atendente_id = lucas.id
    _novo_pagamento(uow, comanda_lucas, FormaPagamento.PIX, "20.00")

    comanda_balcao = _nova_comanda(uow, caixa, gerente, status=StatusComanda.FECHADA)
    _novo_pagamento(uow, comanda_balcao, FormaPagamento.DEBITO, "20.00")
    uow.commit()

    ranking = caixas.ranking_por_atendente([caixa.id])

    por_nome = {item.atendente_nome: item for item in ranking}
    assert por_nome["Ana Beatriz"].valor_total == dinheiro("60.00")
    assert por_nome["Ana Beatriz"].percentual == dinheiro("60.00")
    assert por_nome["Lucas Prado"].valor_total == dinheiro("20.00")
    assert por_nome["Balcão"].valor_total == dinheiro("20.00")
    # Ordenado do maior faturamento pro menor.
    assert ranking[0].atendente_nome == "Ana Beatriz"


def test_ranking_por_atendente_sem_vendas_no_periodo_devolve_lista_vazia(caixas, caixa_aberto):
    assert caixas.ranking_por_atendente([caixa_aberto.id]) == []


def test_fechamento_da_gaveta_do_periodo_agrega_varios_turnos(uow, caixas, gerente):
    caixa1 = _caixa_fechado(uow, valor_abertura="50.00", fechado_em=datetime(2026, 8, 5, 22, 0))
    comanda1 = _nova_comanda(uow, caixa1, gerente, status=StatusComanda.FECHADA)
    _novo_pagamento(uow, comanda1, FormaPagamento.DINHEIRO, "30.00")

    caixa2 = _caixa_fechado(uow, valor_abertura="20.00", fechado_em=datetime(2026, 8, 6, 22, 0))
    comanda2 = _nova_comanda(uow, caixa2, gerente, status=StatusComanda.FECHADA)
    _novo_pagamento(uow, comanda2, FormaPagamento.PIX, "10.00")
    uow.commit()

    gaveta = caixas.fechamento_da_gaveta_do_periodo([caixa1.id, caixa2.id])

    assert "2 turnos" in gaveta.identificacao
    assert gaveta.total_faturado == dinheiro("40.00")


def test_fechamento_da_gaveta_do_periodo_sem_turnos(caixas):
    gaveta = caixas.fechamento_da_gaveta_do_periodo([])
    assert gaveta.total_faturado == dinheiro("0.00")
    assert gaveta.diferenca is None
    assert "Nenhum" in gaveta.identificacao


# ----------------------------------------------------------------------
# identificacao_turno (§3.1 -- "Caixa Turno - Noite", não pelo operador)
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "hora, periodo_esperado",
    [(6, "Manhã"), (11, "Manhã"), (12, "Tarde"), (17, "Tarde"), (18, "Noite"), (2, "Noite")],
)
def test_identificacao_turno_deriva_periodo_da_hora_de_abertura(caixas, hora, periodo_esperado):
    caixa = Caixa(status=StatusCaixa.ABERTO, valor_abertura=dinheiro("50.00"), aberto_em=datetime(2026, 8, 20, hora, 0))
    assert caixas.identificacao_turno(caixa) == f"Caixa Turno - {periodo_esperado}"


def test_fechamento_da_gaveta_usa_identificacao_de_turno(uow, caixas, gerente):
    caixa = _caixa_fechado(uow, fechado_em=datetime(2026, 8, 5, 22, 0))
    caixa.aberto_em = datetime(2026, 8, 5, 19, 0)
    caixa.numero_sequencial_dia = 1
    uow.commit()

    gaveta = caixas.fechamento_da_gaveta(caixa.id)
    assert gaveta.identificacao.startswith("Caixa Turno - Noite")
