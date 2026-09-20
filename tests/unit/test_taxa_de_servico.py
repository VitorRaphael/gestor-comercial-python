"""A taxa de serviço de ponta a ponta, do lado do service. §9.23.

Pedido do Vitor em três partes: a chave da Central de Loja que liga e desliga a
taxa, o cartão de conferência que a mostra (testado em
`tests/ui/test_conferencia_dialog.py`) e o valor da taxa gravado à parte, para o
fechamento do dia e os relatórios dizerem quanto da venda foi taxa.

O que esta suíte cobra:

1. **a chave da loja** — nasce ligada, grava num commit só, recusa o que não é
   `bool`;
2. **a regra no service** — com a loja desligada a taxa é recusada ANTES de a
   comanda mudar, e zero/`None` continuam passando;
3. **o valor isolado** — `valor_taxa_servico` é gravado no mesmo commit do
   percentual e do status, e volta a zero no `reabrir`;
4. **uma conta só** — a prévia do cartão, o total a pagar, o cupom e o
   fechamento do dia dão o mesmo número, inclusive no arredondamento;
5. **os relatórios** — o turno soma só o que foi FECHADO, o período soma os
   turnos, e a taxa aparece como fatia do faturamento, nunca por cima dele.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from gestor_comercial.domain.enums import FormaPagamento, StatusComanda
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services import comprovante_fechamento
from gestor_comercial.services import formatador_cupom as cupom
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.comanda_service import (
    TAXA_SERVICO_PADRAO,
    ComandaService,
    PreviaDeConferencia,
    valor_da_taxa_de_servico,
)
from gestor_comercial.services.dinheiro import dinheiro
from gestor_comercial.services.exceptions import RegraDeNegocioError
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.services.pagamento_service import PagamentoService
from tests.conftest import PIN_GERENTE


@pytest.fixture
def comandas(uow, auth):
    return ComandaService(uow, auth)


@pytest.fixture
def caixas(uow, auth):
    return CaixaService(uow, auth)


@pytest.fixture
def pagamentos(uow, auth, comandas, funcionarios):
    return PagamentoService(uow, auth, comandas, funcionarios)


@pytest.fixture
def lanche(uow, categoria):
    """R$ 65,75 — duas unidades dão os R$ 131,50 do mockup."""
    return uow.produtos.salvar(Produto(nome="Artesanal", preco=Decimal("65.75"), categoria_id=categoria.id))


@pytest.fixture
def mesa_12(uow):
    return uow.mesas.salvar(Mesa(numero=12))


@pytest.fixture
def conta(comandas, gerente, caixa_aberto, mesa_12, lanche):
    """A mesa 12 do mockup: subtotal R$ 131,50."""
    comanda = comandas.abrir_por_mesa(mesa_12.id)
    comandas.lancar_item(comanda.id, lanche.id, 2)
    return comanda


def _recarregada(uow, comanda_id: int):
    """A comanda como está no BANCO, e não como está na Session.

    `rollback` joga fora o que não foi commitado e expira as instâncias: a
    leitura seguinte vai ao banco. Sem isto, um valor atribuído e nunca gravado
    ainda apareceria no objeto (a armadilha do stepper do §9.15).
    """
    uow.session.rollback()
    return uow.comandas.buscar_por_id(comanda_id)


# ---------------------------------------------------------------------------
# 1. A chave da loja
# ---------------------------------------------------------------------------


def test_a_loja_nasce_cobrando_a_taxa(auth):
    """É o que a loja sempre fez: o "Fechar conta" já oferecia os 10%."""
    assert auth.loja_config.aceita_taxa_servico() is True


@pytest.mark.parametrize("valor", [False, True])
def test_a_chave_da_loja_e_gravada_no_banco(uow, auth, valor):
    auth.loja_config.definir_aceita_taxa_servico(not valor)
    auth.loja_config.definir_aceita_taxa_servico(valor)
    uow.session.rollback()

    assert uow.loja_config.obter().aceita_taxa_servico is valor
    assert auth.loja_config.aceita_taxa_servico() is valor


@pytest.mark.parametrize("valor", ["0", 0, 1, None, "sim"])
def test_a_chave_da_loja_so_aceita_bool(auth, valor):
    """`"0"` é verdadeiro em Python: aceitá-lo ligaria a taxa com um texto que
    diz o contrário."""
    with pytest.raises(RegraDeNegocioError):
        auth.loja_config.definir_aceita_taxa_servico(valor)
    assert auth.loja_config.aceita_taxa_servico() is True


# ---------------------------------------------------------------------------
# 2. A regra no service
# ---------------------------------------------------------------------------


def test_loja_sem_taxa_recusa_a_taxa_sem_mexer_na_comanda(uow, auth, comandas, conta):
    """A tela é uma foto tirada na abertura do cartão: se o dono desligar a
    taxa com o cartão aberto em outra ponta, quem barra é o service — e barra
    antes de a comanda mudar de status."""
    auth.loja_config.definir_aceita_taxa_servico(False)

    with pytest.raises(RegraDeNegocioError, match="não cobra taxa de serviço"):
        comandas.fechar_para_conferencia(conta.id, TAXA_SERVICO_PADRAO)

    gravada = _recarregada(uow, conta.id)
    assert gravada.status is StatusComanda.ABERTA
    assert gravada.taxa_servico_percentual is None
    assert gravada.valor_taxa_servico == Decimal("0")
    assert gravada.em_conferencia_em is None


@pytest.mark.parametrize("taxa", [None, Decimal("0")])
def test_loja_sem_taxa_fecha_a_conta_sem_ela(uow, auth, comandas, conta, taxa):
    auth.loja_config.definir_aceita_taxa_servico(False)

    comandas.fechar_para_conferencia(conta.id, taxa)

    gravada = _recarregada(uow, conta.id)
    assert gravada.status is StatusComanda.EM_CONFERENCIA
    assert gravada.valor_taxa_servico == Decimal("0")
    assert comandas.calcular_total_a_pagar(conta.id) == Decimal("131.50")


def test_desligar_a_loja_nao_mexe_na_conta_ja_emitida(auth, comandas, conta):
    """O percentual e o valor ficam congelados na comanda, como o preço do item:
    a pré-conta que o cliente tem na mão não pode mudar sozinha."""
    comandas.fechar_para_conferencia(conta.id, TAXA_SERVICO_PADRAO)
    auth.loja_config.definir_aceita_taxa_servico(False)

    assert comandas.calcular_total_a_pagar(conta.id) == Decimal("144.65")


# ---------------------------------------------------------------------------
# 3. O valor isolado
# ---------------------------------------------------------------------------


def test_a_taxa_em_reais_e_gravada_junto_com_o_percentual_e_o_status(uow, comandas, conta):
    comandas.fechar_para_conferencia(conta.id, TAXA_SERVICO_PADRAO)

    gravada = _recarregada(uow, conta.id)
    assert gravada.status is StatusComanda.EM_CONFERENCIA
    assert gravada.taxa_servico_percentual == Decimal("10")
    assert gravada.valor_taxa_servico == Decimal("13.15")
    assert comandas.calcular_total_a_pagar(conta.id) == Decimal("144.65")


def test_sem_taxa_o_valor_gravado_e_zero(uow, comandas, conta):
    comandas.fechar_para_conferencia(conta.id, None)

    gravada = _recarregada(uow, conta.id)
    assert gravada.valor_taxa_servico == Decimal("0")
    assert comandas.calcular_total_a_pagar(conta.id) == Decimal("131.50")


def test_reabrir_zera_a_taxa_em_reais(uow, comandas, conta):
    """Reaberta, a conta pode ganhar item — e a taxa é decidida de novo no
    próximo fechamento, sobre o subtotal novo."""
    comandas.fechar_para_conferencia(conta.id, TAXA_SERVICO_PADRAO)
    comandas.reabrir(conta.id, PIN_GERENTE)

    gravada = _recarregada(uow, conta.id)
    assert gravada.valor_taxa_servico == Decimal("0")
    assert gravada.taxa_servico_percentual is None
    assert comandas.calcular_total_a_pagar(conta.id) == Decimal("131.50")


def test_o_total_a_pagar_le_a_taxa_gravada(uow, comandas, conta):
    """A fonte do acréscimo é o valor gravado, não o percentual refeito: é o
    mesmo número que o cupom imprime e que o fechamento do dia soma."""
    comandas.fechar_para_conferencia(conta.id, TAXA_SERVICO_PADRAO)
    gravada = uow.comandas.buscar_por_id(conta.id)
    gravada.valor_taxa_servico = Decimal("7.00")

    assert comandas.calcular_total_a_pagar(conta.id) == Decimal("138.50")


# ---------------------------------------------------------------------------
# 4. Uma conta só
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subtotal", "percentual", "esperado"),
    [
        ("131.50", "10", "13.15"),
        # Meio centavo sobe: 0,005 vira 0,01 (ROUND_HALF_UP, `services/dinheiro`).
        ("0.05", "10", "0.01"),
        ("0.04", "10", "0.00"),
        ("99.95", "10", "10.00"),
        ("10.00", "12.5", "1.25"),
        ("131.50", None, "0.00"),
        ("131.50", "0", "0.00"),
    ],
)
def test_a_conta_da_taxa(subtotal, percentual, esperado):
    taxa = None if percentual is None else Decimal(percentual)
    assert valor_da_taxa_de_servico(Decimal(subtotal), taxa) == Decimal(esperado)


def test_a_previa_do_mockup(auth, comandas, conta):
    previa = comandas.previa_de_conferencia(conta.id)

    assert previa == PreviaDeConferencia(
        mesa_numero=12, subtotal=Decimal("131.50"), taxa_percentual=Decimal("10")
    )
    assert previa.oferece_taxa is True
    assert previa.valor_da_taxa == Decimal("13.15")
    # Sem "se cobrar" (§9.25): a loja cobra, então a taxa está no total.
    assert previa.total == Decimal("144.65")
    assert previa.percentual_a_gravar == Decimal("10")


def test_a_previa_da_loja_sem_taxa(auth, comandas, conta):
    auth.loja_config.definir_aceita_taxa_servico(False)

    previa = comandas.previa_de_conferencia(conta.id)

    assert previa.oferece_taxa is False
    assert previa.valor_da_taxa == Decimal("0")
    assert previa.total == Decimal("131.50")
    assert previa.percentual_a_gravar is None


def test_a_previa_do_balcao_nao_tem_mesa(comandas, gerente, caixa_aberto, lanche):
    balcao = comandas.abrir_balcao()
    comandas.lancar_item(balcao.id, lanche.id, 1)

    assert comandas.previa_de_conferencia(balcao.id).mesa_numero is None


def test_a_previa_nao_grava_nada(uow, comandas, conta):
    comandas.previa_de_conferencia(conta.id)

    assert not (uow.session.new or uow.session.dirty or uow.session.deleted)
    assert _recarregada(uow, conta.id).status is StatusComanda.ABERTA


@pytest.mark.parametrize(
    ("preco", "quantidade"),
    [("65.75", 2), ("0.05", 1), ("0.15", 3), ("99.95", 1), ("12.35", 7), ("1.05", 1)],
)
@pytest.mark.parametrize("loja_cobra", [True, False])
def test_a_previa_e_o_total_gravado_sao_o_mesmo_numero(
    uow, auth, comandas, gerente, caixa_aberto, categoria, preco, quantidade, loja_cobra
):
    """A trava do §9.7 aplicada aqui: o cartão não pode dizer um total e a conta
    fechada cobrar outro. A prévia é tirada, a conta é fechada DE VERDADE com o
    que o cartão devolveria, e os dois números são comparados — inclusive nos
    subtotais em que o meio centavo decide."""
    auth.loja_config.definir_aceita_taxa_servico(loja_cobra)
    produto = uow.produtos.salvar(Produto(nome=f"P{preco}", preco=Decimal(preco), categoria_id=categoria.id))
    comanda = comandas.abrir_balcao()
    comandas.lancar_item(comanda.id, produto.id, quantidade)

    previa = comandas.previa_de_conferencia(comanda.id)
    comandas.fechar_para_conferencia(comanda.id, previa.percentual_a_gravar)

    assert comandas.calcular_total_a_pagar(comanda.id) == previa.total
    assert _recarregada(uow, comanda.id).valor_taxa_servico == previa.valor_da_taxa


# ---------------------------------------------------------------------------
# 5. O cupom de pré-conta
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "texto"),
    [("10", "10"), ("10.00", "10"), ("12.5", "12,5"), ("7.25", "7,25"), ("100", "100"), ("0", "0")],
)
def test_o_percentual_do_cupom_nao_tem_casas_mortas(valor, texto):
    assert cupom.percentual(Decimal(valor)) == texto


def test_a_pre_conta_imprime_subtotal_taxa_e_total(uow, auth, driver, comandas, conta, impressora):
    """O que o Vitor pediu escrito: o cliente lê no papel os três números que o
    garçom leu no cartão — e a taxa com o mesmo "10%" da tela."""
    impressao = ImpressaoService(uow, auth, abrir_driver=driver)
    comandas.fechar_para_conferencia(conta.id, TAXA_SERVICO_PADRAO)

    assert impressao.imprimir_pre_conta(conta.id).sucesso

    linhas = driver.texto_de(impressora.nome).splitlines()
    assert any(l.startswith("Subtotal") and l.endswith("131,50") for l in linhas)
    assert any(l.startswith("Taxa de serviço (10%)") and l.endswith("13,15") for l in linhas)
    assert any(l.startswith("TOTAL A PAGAR") and l.endswith("R$ 144,65") for l in linhas)
    assert "10,00%" not in "\n".join(linhas)


def test_a_pre_conta_sem_taxa_nao_tem_a_linha(uow, auth, driver, comandas, conta, impressora):
    impressao = ImpressaoService(uow, auth, abrir_driver=driver)
    comandas.fechar_para_conferencia(conta.id, None)

    impressao.imprimir_pre_conta(conta.id)

    texto = driver.texto_de(impressora.nome)
    assert "Taxa de serviço" not in texto
    assert "131,50" in texto


# ---------------------------------------------------------------------------
# 6. O fechamento do dia e os relatórios
# ---------------------------------------------------------------------------


def _vender(comandas, pagamentos, comanda_id: int, cobrar: bool = True) -> None:
    """Fecha para conferência e paga o total — o caminho de toda mesa.

    `cobrar=False` é a loja sem taxa: a chave é desligada antes da prévia, que é
    quem lê a regra.
    """
    previa = comandas.previa_de_conferencia(comanda_id)
    comandas.fechar_para_conferencia(comanda_id, previa.percentual_a_gravar)
    pagamentos.registrar(comanda_id, FormaPagamento.DINHEIRO, comandas.calcular_total_a_pagar(comanda_id))


def test_o_turno_soma_a_taxa_so_das_contas_fechadas(uow, comandas, caixas, pagamentos, conta, lanche, caixa_aberto):
    """Paga com taxa entra; paga sem taxa entra com zero; em conferência (ainda
    pode ser reaberta e perder a taxa) não entra."""
    _vender(comandas, pagamentos, conta.id, cobrar=True)  # 13,15

    sem_taxa = comandas.abrir_balcao()
    comandas.lancar_item(sem_taxa.id, lanche.id, 1)
    comandas.auth.loja_config.definir_aceita_taxa_servico(False)
    _vender(comandas, pagamentos, sem_taxa.id)
    comandas.auth.loja_config.definir_aceita_taxa_servico(True)

    pendente = comandas.abrir_por_mesa(uow.mesas.salvar(Mesa(numero=7)).id)
    comandas.lancar_item(pendente.id, lanche.id, 4)
    comandas.fechar_para_conferencia(pendente.id, TAXA_SERVICO_PADRAO)  # 26,30, não paga

    resumo = caixas.resumo(caixa_aberto.id)
    assert resumo.total_taxa_servico == Decimal("13.15")
    assert resumo.quantidade_comandas == 2


def test_a_taxa_e_fatia_do_faturamento_e_nao_parcela_a_mais(comandas, caixas, pagamentos, conta, caixa_aberto):
    """O cliente pagou R$ 144,65 com a taxa dentro. O faturamento é 144,65 — e
    não 144,65 + 13,15 —, e a taxa é o pedaço dele que foi serviço."""
    _vender(comandas, pagamentos, conta.id, cobrar=True)

    resumo = caixas.resumo(caixa_aberto.id)
    faturado = resumo.total_dinheiro + resumo.total_maquininha + resumo.total_consumo_interno
    assert faturado == Decimal("144.65")
    assert resumo.total_taxa_servico == Decimal("13.15")


def test_o_periodo_soma_a_taxa_dos_turnos(uow, comandas, caixas, pagamentos, conta, caixa_aberto, lanche):
    _vender(comandas, pagamentos, conta.id, cobrar=True)  # 13,15
    caixas.fechar(caixa_aberto.id, Decimal("100.00") + Decimal("144.65"), Decimal("0"))

    segundo = caixas.abrir(Decimal("50.00"))
    outra = comandas.abrir_balcao()
    comandas.lancar_item(outra.id, lanche.id, 1)  # 65,75 → 6,58
    _vender(comandas, pagamentos, outra.id, cobrar=True)

    assert caixas.fechamento_da_gaveta(caixa_aberto.id).total_taxa_servico == Decimal("13.15")
    assert caixas.fechamento_da_gaveta(segundo.id).total_taxa_servico == Decimal("6.58")
    periodo = caixas.fechamento_da_gaveta_do_periodo([caixa_aberto.id, segundo.id])
    assert periodo.total_taxa_servico == Decimal("19.73")
    assert caixas.fechamento_da_gaveta_do_periodo([]).total_taxa_servico == Decimal("0")


def test_o_comprovante_do_fechamento_tem_a_secao_da_taxa(comandas, caixas, pagamentos, conta, caixa_aberto, gerente):
    _vender(comandas, pagamentos, conta.id, cobrar=True)
    caixa = caixas.buscar(caixa_aberto.id)

    documento = comprovante_fechamento.montar_documento(
        caixa=caixa,
        titulo_fechamento=None,
        resumo=caixas.resumo(caixa.id),
        conferencia=caixas.conferencia_pagamentos(caixa.id),
        grupos_categoria=caixas.resumo_vendas_por_categoria(caixa.id),
        movimentos=caixas.listar_movimentos(caixa.id),
        conferido_por=gerente.nome,
        agora=datetime(2026, 9, 19, 23, 0),
    )
    texto = comprovante_fechamento.renderizar_texto(documento)

    assert "TAXA DE SERVIÇO" in texto
    linha = next(l for l in texto.splitlines() if l.startswith("Arrecadada no turno"))
    assert linha.endswith("13,15")
    assert "Já incluída no Total da conferência acima." in texto
    # Depois da conferência e antes dos produtos, como o cabeçalho descreve.
    assert texto.index("CONFERÊNCIA DE PAGAMENTOS") < texto.index("TAXA DE SERVIÇO") < texto.index(
        "PRODUTOS VENDIDOS"
    )


def test_o_fechamento_impresso_tem_a_taxa_inclusa(uow, auth, driver, comandas, caixas, pagamentos, conta, caixa_aberto, impressora):
    _vender(comandas, pagamentos, conta.id, cobrar=True)
    impressao = ImpressaoService(uow, auth, abrir_driver=driver)

    assert impressao.imprimir_fechamento_caixa(caixa_aberto.id).sucesso

    linhas = driver.texto_de(impressora.nome).splitlines()
    total = next(i for i, l in enumerate(linhas) if l.startswith("Total em vendas"))
    assert linhas[total].endswith("144,65")
    assert linhas[total + 1].startswith("Taxa de serviço inclusa")
    assert linhas[total + 1].endswith("13,15")


def test_o_resumo_do_turno_continua_com_uma_consulta_para_as_comandas(uow, caixas, caixa_aberto, gerente):
    """A soma da taxa entrou na MESMA consulta da contagem de comandas: o
    resumo roda uma vez por turno no Dashboard Mensal (§3.6)."""
    from sqlalchemy import event

    consultas: list[str] = []

    def _contar(_conexao, _cursor, sql, *_resto) -> None:
        consultas.append(sql)

    motor = uow.session.get_bind()
    caixas.resumo(caixa_aberto.id)  # aquece o que for de sessão
    event.listen(motor, "before_cursor_execute", _contar)
    try:
        caixas.resumo(caixa_aberto.id)
    finally:
        event.remove(motor, "before_cursor_execute", _contar)

    assert sum(1 for sql in consultas if "FROM comandas" in sql) == 1
    assert dinheiro(caixas.resumo(caixa_aberto.id).total_taxa_servico) == Decimal("0.00")
