"""A comissão do garçom sobre a taxa de serviço. §9.25.

Pedido do Vitor: a tela de pagamento ganhou o card "Comissão de [garçom]" com
dois botões — "Comissão paga" e "Comissão não paga". Paga grava o repasse e,
quando a conta entrou em dinheiro, tira o valor da gaveta para o fechamento do
turno bater; não paga deixa pendente, numa lista por funcionário para o gerente
acertar no fim do dia.

O que esta suíte cobra:

1. **a conta que a tela mostra** — itens, totais, o que falta e o card da
   comissão, tudo num instantâneo só;
2. **quando existe comissão** — só com atendente vinculado E taxa na conta;
3. **o repasse no recebimento** — marca e saída de gaveta viajam juntas, e a
   saída só acontece com dinheiro;
4. **a lista de pendentes** — agrupada por garçom, e o acerto que zera tudo;
5. **a gaveta** — o saldo esperado desconta o repasse, e o tipo COMISSAO não
   pode ser lançado à mão.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from gestor_comercial.domain.enums import FormaPagamento, StatusComanda, TipoMovimento
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.comanda_service import TAXA_SERVICO_PADRAO, ComandaService
from gestor_comercial.services.exceptions import RegraDeNegocioError
from gestor_comercial.services.pagamento_service import PagamentoService
from tests.conftest import PIN_GERENTE


@pytest.fixture
def comandas(uow, auth):
    return ComandaService(uow, auth)


@pytest.fixture
def caixas(uow, auth):
    return CaixaService(uow, auth)


@pytest.fixture
def pagamentos(uow, auth, comandas, funcionarios, caixas):
    return PagamentoService(uow, auth, comandas, funcionarios, caixas)


@pytest.fixture
def garcom(funcionarios, gerente):
    return funcionarios.criar("Lucas Prado", "Garçom")


@pytest.fixture
def lanche(uow, categoria):
    return uow.produtos.salvar(Produto(nome="Artesanal", preco=Decimal("65.75"), categoria_id=categoria.id))


@pytest.fixture
def mesa_12(uow):
    return uow.mesas.salvar(Mesa(numero=12))


@pytest.fixture
def conta(comandas, gerente, caixa_aberto, mesa_12, lanche, garcom):
    """A mesa 12 em conferência: R$ 131,50 + 10% = R$ 144,65, atendida pelo Lucas."""
    comanda = comandas.abrir_por_mesa(mesa_12.id)
    comandas.lancar_item(comanda.id, lanche.id, 2)
    comandas.definir_atendente(comanda.id, garcom.id)
    comandas.fechar_para_conferencia(comanda.id, TAXA_SERVICO_PADRAO)
    return comanda


def _movimentos_de_comissao(uow, caixa_id: int):
    return [
        movimento
        for movimento in uow.movimentos.listar_por_caixa(caixa_id)
        if movimento.tipo is TipoMovimento.COMISSAO
    ]


# ---------------------------------------------------------------------------
# 1. A conta que a tela mostra
# ---------------------------------------------------------------------------


def test_a_conta_para_a_tela_de_pagamento(pagamentos, conta):
    dados = pagamentos.conta_para_pagamento(conta.id)

    assert dados.origem == "Mesa 12"
    assert dados.atendente_nome == "Lucas Prado"
    assert [(item.quantidade, item.descricao, item.valor) for item in dados.itens] == [
        (2, "Artesanal", Decimal("131.50"))
    ]
    assert dados.subtotal == Decimal("131.50")
    assert dados.taxa_percentual == Decimal("10")
    assert dados.valor_taxa == Decimal("13.15")
    assert dados.total == Decimal("144.65")
    assert (dados.total_pago, dados.restante) == (Decimal("0"), Decimal("144.65"))
    assert dados.comissao.nome == "Lucas Prado"
    assert dados.comissao.valor == Decimal("13.15")
    assert dados.comissao.paga is False


def test_o_item_cancelado_nao_aparece_na_lista(uow, comandas, pagamentos, conta, lanche, gerente):
    """A conta que o cliente confere é a mesma que a tela mostra."""
    comandas.reabrir(conta.id, PIN_GERENTE)
    item = comandas.lancar_item(conta.id, lanche.id, 1)
    comandas.cancelar_item(item.id, "cliente desistiu", PIN_GERENTE)
    comandas.fechar_para_conferencia(conta.id, TAXA_SERVICO_PADRAO)

    dados = pagamentos.conta_para_pagamento(conta.id)

    assert len(dados.itens) == 1
    assert dados.subtotal == Decimal("131.50")


@pytest.mark.parametrize(
    ("pessoas", "esperado"), [(1, "144.65"), (2, "72.33"), (3, "48.22"), (6, "24.11")]
)
def test_dividir_por_pessoa_arredonda_para_cima(pagamentos, conta, pessoas, esperado):
    """Três vezes R$ 48,21 deixariam dois centavos na mesa: a conta que FECHA é
    a que o garçom fala em voz alta."""
    dados = pagamentos.conta_para_pagamento(conta.id)

    assert dados.por_pessoa(pessoas) == Decimal(esperado)
    assert dados.por_pessoa(pessoas) * pessoas >= dados.total


def test_a_divisao_sobe_mesmo_quando_o_meio_centavo_desceria(uow, auth, comandas, pagamentos, gerente, caixa_aberto, categoria, mesa_12):
    """R$ 10,00 entre 3 dá 3,3333: arredondar como dinheiro (meio pra cima)
    daria R$ 3,33 e deixaria um centavo na mesa. Aqui sobe para R$ 3,34."""
    auth.loja_config.definir_aceita_taxa_servico(False)
    produto = uow.produtos.salvar(Produto(nome="Suco", preco=Decimal("10.00"), categoria_id=categoria.id))
    comanda = comandas.abrir_por_mesa(mesa_12.id)
    comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.fechar_para_conferencia(comanda.id, None)

    dados = pagamentos.conta_para_pagamento(comanda.id)

    assert dados.total == Decimal("10.00")
    assert dados.por_pessoa(3) == Decimal("3.34")
    assert dados.por_pessoa(6) == Decimal("1.67")


# ---------------------------------------------------------------------------
# 2. Quando existe comissão
# ---------------------------------------------------------------------------


def test_sem_atendente_nao_ha_comissao(comandas, pagamentos, conta):
    comandas.definir_atendente(conta.id, None)

    assert pagamentos.conta_para_pagamento(conta.id).comissao is None


def test_sem_taxa_nao_ha_comissao(uow, auth, comandas, pagamentos, gerente, caixa_aberto, mesa_12, lanche, garcom):
    auth.loja_config.definir_aceita_taxa_servico(False)
    comanda = comandas.abrir_por_mesa(mesa_12.id)
    comandas.lancar_item(comanda.id, lanche.id, 1)
    comandas.definir_atendente(comanda.id, garcom.id)
    comandas.fechar_para_conferencia(comanda.id, None)

    assert pagamentos.conta_para_pagamento(comanda.id).comissao is None


# ---------------------------------------------------------------------------
# 3. O repasse no recebimento
# ---------------------------------------------------------------------------


def test_comissao_paga_em_dinheiro_sai_da_gaveta(uow, pagamentos, caixas, conta, caixa_aberto):
    pagamentos.registrar(conta.id, FormaPagamento.DINHEIRO, Decimal("144.65"), comissao_paga=True)

    uow.session.rollback()
    gravada = uow.comandas.buscar_por_id(conta.id)
    assert gravada.status is StatusComanda.FECHADA
    assert gravada.comissao_paga is True
    assert gravada.comissao_paga_em is not None

    movimentos = _movimentos_de_comissao(uow, caixa_aberto.id)
    assert [m.valor for m in movimentos] == [Decimal("13.15")]
    assert "Lucas Prado" in movimentos[0].descricao and "Mesa 12" in movimentos[0].descricao
    # A gaveta tem a venda em dinheiro menos o repasse.
    resumo = caixas.resumo(caixa_aberto.id)
    assert resumo.comissoes == Decimal("13.15")
    assert resumo.saldo_esperado == Decimal("100.00") + Decimal("144.65") - Decimal("13.15")


def test_comissao_nao_paga_deixa_o_dinheiro_na_gaveta(uow, pagamentos, caixas, conta, caixa_aberto):
    """O padrão da tela: ninguém tira dinheiro da gaveta sem dizer que tirou."""
    pagamentos.registrar(conta.id, FormaPagamento.DINHEIRO, Decimal("144.65"))

    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).comissao_paga is False
    assert _movimentos_de_comissao(uow, caixa_aberto.id) == []
    assert caixas.resumo(caixa_aberto.id).comissoes == Decimal("0")


def test_conta_paga_no_cartao_marca_a_comissao_sem_mexer_na_gaveta(uow, pagamentos, conta, caixa_aberto):
    """Não há esse dinheiro na gaveta para sair: quem acertou com o garçom
    acertou por fora, e o fechamento do turno não muda."""
    pagamentos.registrar(conta.id, FormaPagamento.CREDITO, Decimal("144.65"), comissao_paga=True)

    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).comissao_paga is True
    assert _movimentos_de_comissao(uow, caixa_aberto.id) == []


def test_pagamento_parcial_nao_mexe_na_comissao(uow, pagamentos, conta, caixa_aberto):
    """A comissão é acertada quando a conta fecha: antes disso a venda ainda
    pode mudar."""
    resumo = pagamentos.registrar(
        conta.id, FormaPagamento.DINHEIRO, Decimal("50.00"), comissao_paga=True
    )

    assert resumo.comanda_fechada is False
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).comissao_paga is False
    assert _movimentos_de_comissao(uow, caixa_aberto.id) == []


def test_o_repasse_e_a_marca_vao_no_mesmo_commit(uow, pagamentos, conta, caixa_aberto):
    """Marca sem saída faz o turno sobrar dinheiro; saída sem marca paga o
    garçom duas vezes. Conferido pelo que está NO BANCO."""
    pagamentos.registrar(conta.id, FormaPagamento.DINHEIRO, Decimal("144.65"), comissao_paga=True)
    uow.session.rollback()

    marcada = uow.comandas.buscar_por_id(conta.id).comissao_paga
    saiu = bool(_movimentos_de_comissao(uow, caixa_aberto.id))
    assert marcada is saiu is True


# ---------------------------------------------------------------------------
# 4. A lista de pendentes e o acerto
# ---------------------------------------------------------------------------


def _outra_conta(uow, comandas, lanche, garcom, numero: int, quantidade: int):
    mesa = uow.mesas.salvar(Mesa(numero=numero))
    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.lancar_item(comanda.id, lanche.id, quantidade)
    comandas.definir_atendente(comanda.id, garcom.id)
    comandas.fechar_para_conferencia(comanda.id, TAXA_SERVICO_PADRAO)
    return comanda


def test_a_lista_de_pendentes_agrupa_por_garcom(uow, comandas, pagamentos, funcionarios, conta, lanche, garcom, gerente):
    outra = _outra_conta(uow, comandas, lanche, garcom, 13, 1)
    maria = funcionarios.criar("Maria", "Garçom")
    dela = _outra_conta(uow, comandas, lanche, maria, 14, 4)
    for comanda_id in (conta.id, outra.id, dela.id):
        pagamentos.registrar(
            comanda_id, FormaPagamento.DINHEIRO, pagamentos.calcular_restante(comanda_id)
        )

    pendentes = pagamentos.listar_comissoes_pendentes()

    assert [(p.nome, p.quantidade, p.valor) for p in pendentes] == [
        ("Maria", 1, Decimal("26.30")),
        ("Lucas Prado", 2, Decimal("19.73")),
    ]
    assert pagamentos.comissao_pendente_de(garcom.id) == Decimal("19.73")


def test_a_conta_em_conferencia_ainda_nao_entra_na_lista(pagamentos, conta):
    """A conta ainda pode ser reaberta — e aí perde a taxa e a comissão junto.
    Pendência só existe depois de a venda estar fechada."""
    assert pagamentos.listar_comissoes_pendentes() == []

    pagamentos.registrar(conta.id, FormaPagamento.DINHEIRO, Decimal("144.65"))

    assert [p.valor for p in pagamentos.listar_comissoes_pendentes()] == [Decimal("13.15")]


def test_a_conta_paga_sai_da_lista(uow, pagamentos, conta):
    pagamentos.registrar(conta.id, FormaPagamento.DINHEIRO, Decimal("144.65"), comissao_paga=True)

    assert pagamentos.listar_comissoes_pendentes() == []


def test_repassar_acerta_tudo_do_garcom_de_uma_vez(uow, comandas, pagamentos, conta, lanche, garcom, caixa_aberto):
    outra = _outra_conta(uow, comandas, lanche, garcom, 13, 1)
    pagamentos.registrar(conta.id, FormaPagamento.DINHEIRO, Decimal("144.65"))
    pagamentos.registrar(outra.id, FormaPagamento.CREDITO, pagamentos.calcular_restante(outra.id))

    total = pagamentos.pagar_comissoes_do_funcionario(garcom.id)

    assert total == Decimal("19.73")
    assert pagamentos.listar_comissoes_pendentes() == []
    # Só a parte que entrou em dinheiro sai da gaveta, num movimento só.
    movimentos = _movimentos_de_comissao(uow, caixa_aberto.id)
    assert [m.valor for m in movimentos] == [Decimal("13.15")]
    assert "2 conta(s)" in movimentos[0].descricao


def test_repassar_sem_nada_pendente_e_recusado(pagamentos, garcom, caixa_aberto, gerente):
    with pytest.raises(RegraDeNegocioError, match="não tem comissão pendente"):
        pagamentos.pagar_comissoes_do_funcionario(garcom.id)


def test_definir_comissao_exige_a_conta_paga(pagamentos, conta):
    with pytest.raises(RegraDeNegocioError, match="ainda não foi paga"):
        pagamentos.definir_comissao(conta.id, True)


def test_desmarcar_devolve_a_conta_para_a_lista(uow, pagamentos, conta):
    """O erro de clique tem volta — o movimento de gaveta que já saiu, não: quem
    precisa desfazer registra um reforço."""
    pagamentos.registrar(conta.id, FormaPagamento.DINHEIRO, Decimal("144.65"), comissao_paga=True)

    pagamentos.definir_comissao(conta.id, False)

    assert [p.valor for p in pagamentos.listar_comissoes_pendentes()] == [Decimal("13.15")]


# ---------------------------------------------------------------------------
# 5. A gaveta
# ---------------------------------------------------------------------------


def test_comissao_nao_pode_ser_lancada_a_mao(caixas, gerente, caixa_aberto):
    """Uma comissão digitada na gaveta não teria comanda do outro lado, e o
    total de comissões do turno deixaria de bater com o das contas."""
    with pytest.raises(RegraDeNegocioError, match="recebimento da conta"):
        caixas.registrar_movimento(TipoMovimento.COMISSAO, Decimal("10.00"), "na mão")


@pytest.mark.parametrize("valor", [Decimal("0"), Decimal("-1.00")])
def test_o_repasse_recusa_valor_que_nao_e_dinheiro_saindo(caixas, gerente, caixa_aberto, valor):
    with pytest.raises(RegraDeNegocioError, match="maior que zero"):
        caixas.registrar_repasse_comissao(valor, "teste")


def test_o_fechamento_impresso_e_o_comprovante_mostram_o_repasse(uow, auth, driver, pagamentos, caixas, conta, caixa_aberto, impressora, gerente):
    """Quem confere a gaveta precisa ver a linha: sem ela, o saldo esperado
    não fecha com o que o papel lista."""
    from datetime import datetime

    from gestor_comercial.services import comprovante_fechamento
    from gestor_comercial.services.impressao_service import ImpressaoService

    pagamentos.registrar(conta.id, FormaPagamento.DINHEIRO, Decimal("144.65"), comissao_paga=True)
    impressao = ImpressaoService(uow, auth, abrir_driver=driver)

    assert impressao.imprimir_fechamento_caixa(caixa_aberto.id).sucesso

    linhas = driver.texto_de(impressora.nome).splitlines()
    assert any(l.startswith("Comissões repassadas") and l.endswith("13,15") for l in linhas)

    caixa = caixas.buscar(caixa_aberto.id)
    texto = comprovante_fechamento.renderizar_texto(
        comprovante_fechamento.montar_documento(
            caixa=caixa,
            titulo_fechamento=None,
            resumo=caixas.resumo(caixa.id),
            conferencia=caixas.conferencia_pagamentos(caixa.id),
            grupos_categoria=caixas.resumo_vendas_por_categoria(caixa.id),
            movimentos=caixas.listar_movimentos(caixa.id),
            conferido_por=gerente.nome,
            agora=datetime(2026, 9, 20, 23, 0),
        )
    )
    assert "Comissão de Lucas Prado" in texto


def test_o_fechamento_do_turno_conta_o_repasse(uow, pagamentos, caixas, conta, caixa_aberto, gerente):
    pagamentos.registrar(conta.id, FormaPagamento.DINHEIRO, Decimal("144.65"), comissao_paga=True)

    resumo = caixas.resumo(caixa_aberto.id)

    # O faturamento não muda: a comissão é repasse, não desconto de venda.
    assert resumo.total_dinheiro == Decimal("144.65")
    assert resumo.comissoes == Decimal("13.15")
    assert resumo.saldo_esperado == Decimal("231.50")
