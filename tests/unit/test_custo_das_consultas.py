"""O custo das telas quentes não pode crescer com o volume — `REMASTERIZACAO-V1.md` §3.6.

A Fase 2 da Remasterização derrubou o Dashboard Mensal de 2.502 para 217
consultas num banco de 3 meses de operação. O problema é que N+1 é um defeito
que **volta sozinho**: basta alguém, meses adiante, ler `pagamento.comanda`
dentro de um laço, ou trocar uma contagem por um `listar_todos()`. Nada quebra,
nenhum teste fica vermelho, o número simplesmente sobe de novo — e só aparece
como "o sistema ficou lento" depois de meses de vendas acumuladas.

Estes testes existem para isso não passar em silêncio. Nenhum deles afirma um
número mágico de consultas: cada um mede a **mesma operação com o dobro do
volume** e exige que a conta não mude. É a propriedade que interessa — o custo
da tela é função do que ela mostra, não de quanto o food truck já vendeu.

Contam consultas com um listener do próprio SQLAlchemy (`before_cursor_execute`),
sem dependência nova.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import (
    FormaPagamento,
    StatusCaixa,
    StatusComanda,
    StatusMesa,
    TipoMovimento,
)
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.movimento_caixa import MovimentoCaixa
from gestor_comercial.domain.pagamento import Pagamento
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.comanda_service import ComandaService


@pytest.fixture
def caixas(uow, auth):
    return CaixaService(uow, auth)


@pytest.fixture
def comandas(uow, auth):
    return ComandaService(uow, auth)


@contextlib.contextmanager
def contando_consultas(session):
    """Quantas idas ao banco a operação dentro do `with` disparou."""
    contador = {"n": 0}

    def _contar(*_args, **_kwargs) -> None:
        contador["n"] += 1

    event.listen(session.bind, "before_cursor_execute", _contar)
    try:
        yield contador
    finally:
        event.remove(session.bind, "before_cursor_execute", _contar)


def consultas_de(session, operacao) -> int:
    """Roda `operacao` com a Session esvaziada antes, para o cache não mascarar
    consulta nenhuma — é o estado de quem acabou de abrir a tela."""
    session.expire_all()
    with contando_consultas(session) as contador:
        operacao()
    return contador["n"]


# ----------------------------------------------------------------------
# Massa de teste
# ----------------------------------------------------------------------


def _turno(uow, gerente, produto, dia: int, comandas_no_turno: int, mesa=None) -> Caixa:
    """Um turno fechado com vendas, cancelamento e movimento de gaveta."""
    abertura = datetime(2026, 8, dia, 17, 0)
    caixa = uow.caixas.salvar(
        Caixa(
            status=StatusCaixa.FECHADO,
            valor_abertura=Decimal("100.00"),
            valor_contado_dinheiro=Decimal("500.00"),
            valor_contado_maquininha=Decimal("500.00"),
            aberto_em=abertura,
            fechado_em=abertura + timedelta(hours=6),
            numero_sequencial_dia=1,
            aberto_por_id=gerente.id,
            fechado_por_id=gerente.id,
        )
    )
    uow.movimentos.salvar(
        MovimentoCaixa(
            tipo=TipoMovimento.SANGRIA,
            valor=Decimal("20.00"),
            registrado_em=abertura + timedelta(hours=1),
            caixa_id=caixa.id,
            usuario_id=gerente.id,
        )
    )
    formas = list(FormaPagamento)
    for n in range(comandas_no_turno):
        comanda = uow.comandas.salvar(
            Comanda(
                status=StatusComanda.FECHADA,
                aberta_em=abertura + timedelta(minutes=n),
                fechada_em=abertura + timedelta(minutes=n + 30),
                mesa_id=mesa.id if mesa is not None else None,
                usuario_id=gerente.id,
                atendente_id=None,
                caixa_id=caixa.id,
                valor_desconto=Decimal("0"),
            )
        )
        uow.itens.salvar(
            ItemComanda(
                quantidade=2,
                preco_unit_congelado=produto.preco,
                cancelado=False,
                impresso_em=comanda.aberta_em,
                comanda_id=comanda.id,
                produto_id=produto.id,
            )
        )
        # Um item cancelado por comanda: é o que alimenta a auditoria de
        # cancelamentos, o trecho que mais fazia consulta por item (§3.6).
        uow.itens.salvar(
            ItemComanda(
                quantidade=1,
                preco_unit_congelado=produto.preco,
                cancelado=True,
                cancelado_em=comanda.aberta_em + timedelta(minutes=2),
                motivo_cancelamento="cliente desistiu",
                cancelado_por_id=gerente.id,
                comanda_id=comanda.id,
                produto_id=produto.id,
            )
        )
        uow.pagamentos.salvar(
            Pagamento(
                forma=formas[n % len(formas)],
                valor=Decimal("20.00"),
                registrado_em=comanda.fechada_em,
                comanda_id=comanda.id,
            )
        )
    uow.commit()
    return caixa


# ----------------------------------------------------------------------
# Um turno: o custo não cresce com o movimento do turno
# ----------------------------------------------------------------------


def test_resumo_do_turno_nao_cresce_com_o_numero_de_vendas(uow, caixas, gerente, produto):
    pequeno = _turno(uow, gerente, produto, dia=1, comandas_no_turno=2)
    grande = _turno(uow, gerente, produto, dia=2, comandas_no_turno=20)

    barato = consultas_de(uow.session, lambda: caixas.resumo(pequeno.id))
    caro = consultas_de(uow.session, lambda: caixas.resumo(grande.id))

    assert barato == caro, (
        f"10x mais vendas custou {caro} consultas em vez de {barato} — "
        "voltou a ler o banco dentro do laço (§3.6)."
    )


def test_totais_por_forma_lê_os_pagamentos_uma_vez_só(uow, caixas, gerente, produto):
    """Cinco formas de pagamento não podem custar cinco consultas."""
    caixa = _turno(uow, gerente, produto, dia=3, comandas_no_turno=10)

    assert consultas_de(uow.session, lambda: caixas.totais_por_forma(caixa.id)) <= 2


def test_auditoria_de_cancelamentos_nao_cresce_com_os_itens_cancelados(
    uow, caixas, gerente, produto
):
    pequeno = _turno(uow, gerente, produto, dia=4, comandas_no_turno=2)
    grande = _turno(uow, gerente, produto, dia=5, comandas_no_turno=20)

    barato = consultas_de(uow.session, lambda: caixas.resumo_cancelamentos(pequeno.id))
    caro = consultas_de(uow.session, lambda: caixas.resumo_cancelamentos(grande.id))

    assert barato == caro, (
        f"10x mais cancelamentos custou {caro} consultas em vez de {barato} — "
        "produto/comanda/autorizador voltaram a ser buscados item a item (§3.6)."
    )


def test_resumo_cancelamentos_continua_trazendo_o_detalhe_certo(uow, caixas, gerente, produto):
    """O eager loading não pode ter mudado o conteúdo do relatório."""
    caixa = _turno(uow, gerente, produto, dia=6, comandas_no_turno=3)

    resumo = caixas.resumo_cancelamentos(caixa.id)

    assert resumo.quantidade_total == 3
    assert resumo.valor_total == Decimal("30.00")
    assert [linha.produto_nome for linha in resumo.detalhado] == ["X-Burger"] * 3
    assert [linha.autorizado_por for linha in resumo.detalhado] == ["Gerente"] * 3
    assert [linha.origem for linha in resumo.detalhado] == ["Balcão #1", "Balcão #2", "Balcão #3"]


# ----------------------------------------------------------------------
# Vários turnos: o custo do mês não cresce com o número de turnos
# ----------------------------------------------------------------------


def test_ranking_por_atendente_nao_cresce_com_os_turnos_do_periodo(
    uow, caixas, gerente, produto
):
    """Era o pior N+1 do projeto: uma consulta por pagamento do período."""
    poucos = [_turno(uow, gerente, produto, dia=d, comandas_no_turno=5).id for d in (7, 8)]
    muitos = [_turno(uow, gerente, produto, dia=d, comandas_no_turno=5).id for d in range(9, 17)]

    barato = consultas_de(uow.session, lambda: caixas.ranking_por_atendente(poucos))
    caro = consultas_de(uow.session, lambda: caixas.ranking_por_atendente(muitos))

    assert barato == caro, (
        f"4x mais turnos custou {caro} consultas em vez de {barato} — "
        "o ranking voltou a buscar a comanda de cada pagamento (§3.6)."
    )


def test_totais_de_cancelamento_do_periodo_e_uma_consulta_so(uow, caixas, gerente, produto):
    turnos = [_turno(uow, gerente, produto, dia=d, comandas_no_turno=5).id for d in (17, 18, 19)]

    assert consultas_de(uow.session, lambda: caixas.totais_de_cancelamento(turnos)) == 1


def test_totais_de_cancelamento_bate_com_a_auditoria_turno_a_turno(uow, caixas, gerente, produto):
    """O atalho do Dashboard Mensal tem que dar exatamente o mesmo número que a
    auditoria detalhada de cada turno somada — senão é otimização que mente."""
    turnos = [_turno(uow, gerente, produto, dia=d, comandas_no_turno=4).id for d in (20, 21, 22)]

    detalhado_quantidade = sum(caixas.resumo_cancelamentos(t).quantidade_total for t in turnos)
    detalhado_valor = sum(
        (caixas.resumo_cancelamentos(t).valor_total for t in turnos), Decimal("0.00")
    )

    totais = caixas.totais_de_cancelamento(turnos)
    assert totais.quantidade == detalhado_quantidade
    assert totais.valor == detalhado_valor


def test_periodo_sem_turno_nenhum_nao_toca_no_banco(uow, caixas):
    """Mês sem fechamento é normal no food truck (feriado, viagem), não é erro."""
    assert consultas_de(uow.session, lambda: caixas.ranking_por_atendente([])) == 0
    assert consultas_de(uow.session, lambda: caixas.totais_de_cancelamento([])) == 0


# ----------------------------------------------------------------------
# Tela principal: o custo não cresce com o histórico da mesa
# ----------------------------------------------------------------------


def test_grade_de_mesas_nao_cresce_com_o_historico_da_mesa(uow, comandas, gerente, produto):
    """O achado mais insidioso do §3.6: a tela mais usada do PDV lia todo o
    histórico de cada mesa ocupada para achar a comanda em aberto. Não doía no
    primeiro dia; doía no segundo mês."""
    mesa = uow.mesas.salvar(Mesa(numero=7, status=StatusMesa.OCUPADA))
    caixa = _turno(uow, gerente, produto, dia=23, comandas_no_turno=3, mesa=mesa)
    uow.comandas.salvar(
        Comanda(
            status=StatusComanda.ABERTA,
            aberta_em=datetime(2026, 8, 24, 18, 0),
            mesa_id=mesa.id,
            usuario_id=gerente.id,
            caixa_id=caixa.id,
            valor_desconto=Decimal("0"),
        )
    )
    uow.commit()
    com_pouco_historico = consultas_de(uow.session, comandas.comandas_em_uso_por_mesa)

    # Mais dois meses de vendas passadas na MESMA mesa.
    for dia in range(1, 21):
        _turno(uow, gerente, produto, dia=dia, comandas_no_turno=5, mesa=mesa)
    com_muito_historico = consultas_de(uow.session, comandas.comandas_em_uso_por_mesa)

    # Duas consultas: as comandas em uso, e o `selectinload` de quem atende —
    # nenhuma das duas depende de quantas comandas a mesa já teve.
    assert com_pouco_historico == com_muito_historico, (
        f"a grade passou de {com_pouco_historico} para {com_muito_historico} consultas com o "
        "histórico da mesa — voltou a varrer `mesa.comandas` (§3.6)."
    )
    assert com_muito_historico <= 3


def test_grade_de_mesas_acha_a_comanda_em_uso_de_cada_mesa(uow, comandas, gerente, produto, caixa_aberto):
    """A consulta única tem que enxergar o mesmo que `buscar_aberta_por_mesa`."""
    ocupada = uow.mesas.salvar(Mesa(numero=11, status=StatusMesa.OCUPADA))
    conferencia = uow.mesas.salvar(Mesa(numero=12, status=StatusMesa.OCUPADA))
    livre = uow.mesas.salvar(Mesa(numero=13, status=StatusMesa.LIVRE))
    for mesa, status in ((ocupada, StatusComanda.ABERTA), (conferencia, StatusComanda.EM_CONFERENCIA)):
        uow.comandas.salvar(
            Comanda(
                status=status,
                aberta_em=datetime(2026, 8, 25, 19, 0),
                mesa_id=mesa.id,
                usuario_id=gerente.id,
                caixa_id=caixa_aberto.id,
                valor_desconto=Decimal("0"),
            )
        )
    # Comanda de balcão (sem mesa) e comanda já fechada não entram na grade.
    uow.comandas.salvar(
        Comanda(
            status=StatusComanda.ABERTA,
            aberta_em=datetime(2026, 8, 25, 19, 5),
            mesa_id=None,
            usuario_id=gerente.id,
            caixa_id=caixa_aberto.id,
            valor_desconto=Decimal("0"),
        )
    )
    uow.commit()

    em_uso = comandas.comandas_em_uso_por_mesa()

    assert set(em_uso) == {ocupada.id, conferencia.id}
    assert livre.id not in em_uso
    assert em_uso[ocupada.id].status is StatusComanda.ABERTA
    assert em_uso[conferencia.id].status is StatusComanda.EM_CONFERENCIA
    for mesa in (ocupada, conferencia):
        assert em_uso[mesa.id].id == uow.comandas.buscar_aberta_por_mesa(mesa.id).id
