"""O instantâneo da tela da mesa: `ComandaService.painel_da_comanda` (§9.27).

A tela da mesa pinta tudo a partir dele — itens, totais, garçom e a etapa da
esteira —, então é aqui que moram as regras que ela mostra:

1. **o total é a soma dos itens** — o mesmo número de `calcular_total`, sem
   acréscimo nenhum (a taxa de serviço saiu no §9.26);
2. **aguardando × em produção** — os pendentes uma linha por item; os enviados
   somados por produto e preço, com os ids de todos os itens por baixo;
3. **a etapa** — Atendimento, Produção, Conferência, Pagamento;
4. **consultas fixas** — o N+1 da tela antiga (uma consulta por item para ler
   o nome do produto) não pode voltar.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import event

from gestor_comercial.domain.enums import FormaPagamento, StatusComanda
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.comanda_service import ComandaService, EtapaDaComanda, LinhaDoPainel
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.services.pagamento_service import PagamentoService
from tests.conftest import PIN_GERENTE


@pytest.fixture
def comandas(uow, auth):
    return ComandaService(uow, auth)


@pytest.fixture
def impressao(uow, auth):
    return ImpressaoService(uow, auth)


@pytest.fixture
def cardapio_do_mockup(uow, categoria):
    def produto(nome: str, preco: str) -> Produto:
        return uow.produtos.salvar(Produto(nome=nome, preco=Decimal(preco), categoria_id=categoria.id))

    return {
        "anel": produto("Anel de Cebola", "12.00"),
        "batata": produto("Batata G Cheddar/Bacon", "27.00"),
        "yakisoba": produto("Yakisoba Frango", "32.00"),
        "coca": produto("Coca-Cola 600ml", "9.50"),
    }


@pytest.fixture
def mesa_12(uow, comandas, gerente, caixa_aberto, cardapio_do_mockup, impressao, funcionarios):
    """A mesa do mockup: três produtos na chapa e um Anel de Cebola esperando."""
    mesa = uow.mesas.salvar(Mesa(numero=12))
    comanda = comandas.abrir_por_mesa(mesa.id)
    garcom = funcionarios.criar("Lucas Prado", "Garçom")
    comandas.definir_atendente(comanda.id, garcom.id)
    comandas.lancar_item(comanda.id, cardapio_do_mockup["batata"].id, 1)
    comandas.lancar_item(comanda.id, cardapio_do_mockup["yakisoba"].id, 2)
    comandas.lancar_item(comanda.id, cardapio_do_mockup["coca"].id, 3)
    impressao.imprimir_comanda(comanda.id)
    comandas.lancar_item(comanda.id, cardapio_do_mockup["anel"].id, 1)
    return comanda


# ---------------------------------------------------------------------------
# 1. O total é a soma dos itens
# ---------------------------------------------------------------------------


def test_os_numeros_do_mockup(comandas, mesa_12):
    painel = comandas.painel_da_comanda(mesa_12.id)

    assert painel.total_enviado == Decimal("119.50")
    assert painel.total_pendente == Decimal("12.00")
    assert painel.total == Decimal("131.50")
    assert painel.unidades_enviadas == 6
    assert painel.origem == "Mesa 12"
    assert painel.atendente_nome == "Lucas Prado"
    assert painel.atendente_cargo == "Garçom"


def test_o_total_e_o_mesmo_numero_do_service(comandas, mesa_12, cardapio_do_mockup):
    """A tela não soma por conta própria: o total dela é o de `calcular_total`,
    item cancelado fora, e nenhum acréscimo por cima."""
    comandas.lancar_item(mesa_12.id, cardapio_do_mockup["coca"].id, 1, "gelada")
    enviado = comandas.painel_da_comanda(mesa_12.id).enviados[0]
    comandas.cancelar_item(enviado.item_ids[0], "cliente desistiu", PIN_GERENTE)

    painel = comandas.painel_da_comanda(mesa_12.id)

    assert painel.total == comandas.calcular_total(mesa_12.id)
    assert painel.total == comandas.calcular_total_a_pagar(mesa_12.id)
    assert painel.total == Decimal("114.00")


def test_o_preco_e_o_congelado_no_lancamento(uow, comandas, mesa_12, cardapio_do_mockup):
    """Mudar o preço no Cardápio no meio do atendimento não muda a conta."""
    anel = cardapio_do_mockup["anel"]
    anel.preco = Decimal("99.00")
    uow.commit()

    painel = comandas.painel_da_comanda(mesa_12.id)

    assert painel.pendentes[0].preco_unit == Decimal("12.00")
    assert painel.total == Decimal("131.50")


def test_o_que_ja_foi_pago_entra_no_instantaneo(uow, auth, comandas, funcionarios, mesa_12, impressao):
    impressao.imprimir_comanda(mesa_12.id)
    comandas.fechar_para_conferencia(mesa_12.id)
    PagamentoService(uow, auth, comandas, funcionarios).registrar(mesa_12.id, FormaPagamento.PIX, Decimal("31.50"))

    painel = comandas.painel_da_comanda(mesa_12.id)

    assert painel.total_pago == Decimal("31.50")
    assert painel.total == Decimal("131.50"), "o total da conta não desconta o que já foi pago"


# ---------------------------------------------------------------------------
# 2. Aguardando envio × em produção
# ---------------------------------------------------------------------------


def test_os_pendentes_sao_uma_linha_por_item(comandas, mesa_12, cardapio_do_mockup):
    comandas.lancar_item(mesa_12.id, cardapio_do_mockup["anel"].id, 2, "sem sal")

    pendentes = comandas.painel_da_comanda(mesa_12.id).pendentes

    assert [(linha.nome, linha.quantidade, linha.observacao) for linha in pendentes] == [
        ("Anel de Cebola", 1, None),
        ("Anel de Cebola", 2, "sem sal"),
    ]
    assert all(len(linha.item_ids) == 1 for linha in pendentes), "pendente se remove item a item"


def test_os_enviados_sao_somados_por_produto_e_preco(comandas, mesa_12, cardapio_do_mockup, impressao):
    """Três "Coca" lançadas em duas vezes pelo mesmo preço viram UMA linha, com
    os dois ids por baixo — o Cancelar da linha cancela os dois."""
    comandas.lancar_item(mesa_12.id, cardapio_do_mockup["coca"].id, 2)
    impressao.imprimir_comanda(mesa_12.id)

    enviados = comandas.painel_da_comanda(mesa_12.id).enviados

    coca = next(linha for linha in enviados if linha.nome == "Coca-Cola 600ml")
    assert coca.quantidade == 5
    assert len(coca.item_ids) == 2
    assert coca.total == Decimal("47.50")
    assert [linha.nome for linha in enviados] == [
        "Batata G Cheddar/Bacon",
        "Yakisoba Frango",
        "Coca-Cola 600ml",
        "Anel de Cebola",
    ], "a ordem é a do primeiro lançamento de cada grupo"


def test_a_observacao_so_aparece_no_grupo_de_um_item(uow, comandas, mesa_12, cardapio_do_mockup, impressao, categoria):
    """Somar dois lançamentos com observações diferentes e mostrar uma delas
    mentiria sobre o outro."""
    suco = uow.produtos.salvar(Produto(nome="Suco", preco=Decimal("8.00"), categoria_id=categoria.id))
    comandas.lancar_item(mesa_12.id, suco.id, 1, "sem gelo")
    comandas.lancar_item(mesa_12.id, cardapio_do_mockup["batata"].id, 1, "sem bacon")
    comandas.lancar_item(mesa_12.id, cardapio_do_mockup["yakisoba"].id, 1, "sem cebola")
    comandas.lancar_item(mesa_12.id, cardapio_do_mockup["anel"].id, 1, "bem passado")
    impressao.imprimir_comanda(mesa_12.id)

    por_nome = {linha.nome: linha for linha in comandas.painel_da_comanda(mesa_12.id).enviados}

    assert por_nome["Suco"].observacao == "sem gelo", "o grupo de um item mostra a observação dele"
    assert por_nome["Batata G Cheddar/Bacon"].observacao is None
    assert por_nome["Yakisoba Frango"].observacao is None
    # O Anel pendente do mockup (sem observação) foi junto no envio: dois itens.
    assert por_nome["Anel de Cebola"].observacao is None
    assert len(por_nome["Anel de Cebola"].item_ids) == 2


def test_o_grupo_nao_mostra_a_observacao_do_primeiro_item(uow, comandas, mesa_12, impressao, categoria):
    """O caso que a primeira versão do teste acima não separava (a mutação
    sobreviveu): no mockup o PRIMEIRO item de cada grupo não tinha observação,
    então "mostrar a do primeiro" também dava vazio."""
    cha = uow.produtos.salvar(Produto(nome="Chá", preco=Decimal("6.00"), categoria_id=categoria.id))
    comandas.lancar_item(mesa_12.id, cha.id, 1, "sem açúcar")
    comandas.lancar_item(mesa_12.id, cha.id, 1, "com limão")
    impressao.imprimir_comanda(mesa_12.id)

    cha_na_tela = next(linha for linha in comandas.painel_da_comanda(mesa_12.id).enviados if linha.nome == "Chá")

    assert cha_na_tela.quantidade == 2
    assert cha_na_tela.observacao is None


def test_item_cancelado_nao_aparece(comandas, mesa_12):
    batata = comandas.painel_da_comanda(mesa_12.id).enviados[0]
    comandas.cancelar_item(batata.item_ids[0], "errado", PIN_GERENTE)

    nomes = [linha.nome for linha in comandas.painel_da_comanda(mesa_12.id).enviados]

    assert "Batata G Cheddar/Bacon" not in nomes


def test_a_linha_e_imutavel():
    linha = LinhaDoPainel(item_ids=(1,), nome="X", observacao=None, preco_unit=Decimal("1.00"), quantidade=1)

    with pytest.raises(AttributeError):
        linha.quantidade = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. A etapa da esteira
# ---------------------------------------------------------------------------


def test_a_comanda_recem_aberta_esta_no_atendimento(uow, comandas, gerente, caixa_aberto):
    comanda = comandas.abrir_por_mesa(uow.mesas.salvar(Mesa(numero=5)).id)

    painel = comandas.painel_da_comanda(comanda.id)

    assert painel.etapa is EtapaDaComanda.ATENDIMENTO
    assert not painel.tem_itens
    assert painel.total == Decimal("0")


def test_so_pendente_continua_no_atendimento(uow, comandas, gerente, caixa_aberto, produto):
    comanda = comandas.abrir_por_mesa(uow.mesas.salvar(Mesa(numero=5)).id)
    comandas.lancar_item(comanda.id, produto.id, 1)

    assert comandas.painel_da_comanda(comanda.id).etapa is EtapaDaComanda.ATENDIMENTO


def test_o_primeiro_envio_leva_a_producao(comandas, mesa_12):
    assert comandas.painel_da_comanda(mesa_12.id).etapa is EtapaDaComanda.PRODUCAO


def test_a_pre_conta_leva_a_conferencia(comandas, mesa_12):
    comandas.fechar_para_conferencia(mesa_12.id)

    assert comandas.painel_da_comanda(mesa_12.id).etapa is EtapaDaComanda.CONFERENCIA


def test_o_pagamento_parcial_leva_ao_pagamento(uow, auth, comandas, funcionarios, mesa_12):
    comandas.fechar_para_conferencia(mesa_12.id)
    PagamentoService(uow, auth, comandas, funcionarios).registrar(mesa_12.id, FormaPagamento.DINHEIRO, Decimal("10.00"))

    assert comandas.painel_da_comanda(mesa_12.id).etapa is EtapaDaComanda.PAGAMENTO


def test_a_conta_quitada_fica_no_pagamento(uow, auth, comandas, funcionarios, mesa_12):
    comandas.fechar_para_conferencia(mesa_12.id)
    PagamentoService(uow, auth, comandas, funcionarios).registrar(mesa_12.id, FormaPagamento.DINHEIRO, Decimal("131.50"))

    painel = comandas.painel_da_comanda(mesa_12.id)

    assert painel.status is StatusComanda.FECHADA
    assert painel.etapa is EtapaDaComanda.PAGAMENTO


def test_a_comanda_cancelada_nao_anda(uow, comandas, gerente, caixa_aberto, produto):
    comanda = comandas.abrir_por_mesa(uow.mesas.salvar(Mesa(numero=5)).id)
    comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.cancelar(comanda.id, "desistiu", PIN_GERENTE)

    assert comandas.painel_da_comanda(comanda.id).etapa is None


def test_reabrir_volta_para_a_producao(comandas, mesa_12):
    comandas.fechar_para_conferencia(mesa_12.id)
    comandas.reabrir(mesa_12.id, PIN_GERENTE)

    assert comandas.painel_da_comanda(mesa_12.id).etapa is EtapaDaComanda.PRODUCAO


def test_o_balcao_nao_tem_mesa(comandas, gerente, caixa_aberto):
    painel = comandas.painel_da_comanda(comandas.abrir_balcao().id)

    assert painel.origem == "Balcão"
    assert painel.mesa_numero is None
    assert painel.atendente_id is None


def test_aberta_em_e_o_instante_do_primeiro_item(uow, comandas, gerente, caixa_aberto, produto):
    comanda = comandas.abrir_por_mesa(uow.mesas.salvar(Mesa(numero=5)).id)
    antes = datetime.now()
    comandas.lancar_item(comanda.id, produto.id, 1)

    assert comandas.painel_da_comanda(comanda.id).aberta_em >= antes


# ---------------------------------------------------------------------------
# 4. Consultas fixas
# ---------------------------------------------------------------------------


def _consultas_do_painel(uow, comandas, comanda_id: int) -> int:
    # As instâncias saem da sessão: sem isso o nome do produto viria do mapa de
    # identidade, de graça, e o teste passaria sem o `selectinload` existir.
    uow.session.expunge_all()
    contagem = {"n": 0}

    def _contar(*_argumentos, **_nomeados) -> None:
        contagem["n"] += 1

    event.listen(uow.session.bind, "before_cursor_execute", _contar)
    try:
        comandas.painel_da_comanda(comanda_id)
    finally:
        event.remove(uow.session.bind, "before_cursor_execute", _contar)
    return contagem["n"]


def test_o_numero_de_consultas_nao_cresce_com_os_itens(uow, comandas, gerente, caixa_aberto, categoria, impressao):
    """O N+1 da tela antiga: uma consulta por item para ler o nome do produto,
    a cada item lançado. Duas comandas, uma com 2 itens e outra com 12 produtos
    diferentes (metade enviada), têm de custar a mesma coisa."""

    def comanda_com(itens: int, mesa: int) -> int:
        comanda = comandas.abrir_por_mesa(uow.mesas.salvar(Mesa(numero=mesa)).id)
        for i in range(itens):
            novo = uow.produtos.salvar(Produto(nome=f"P{mesa}-{i}", preco=Decimal("5.00"), categoria_id=categoria.id))
            comandas.lancar_item(comanda.id, novo.id, 1)
            if i == itens // 2:
                impressao.imprimir_comanda(comanda.id)
        return comanda.id

    pequena = comanda_com(2, 40)
    grande = comanda_com(12, 41)

    assert _consultas_do_painel(uow, comandas, pequena) == _consultas_do_painel(uow, comandas, grande)
    assert _consultas_do_painel(uow, comandas, grande) <= 7
