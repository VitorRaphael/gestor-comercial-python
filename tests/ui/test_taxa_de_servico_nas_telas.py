"""A taxa de serviço nas telas de verdade. §9.23.

`test_conferencia_dialog.py` testa o cartão sozinho; aqui ele é aberto pelo
botão "Fechar conta" da `ComandaView`, com os services e o banco reais, e o que
se confere é o que ficou GRAVADO — é isso que o fechamento do dia vai somar.
Junto: o interruptor da Central de Loja (tela de Configurações), que decide se o
cartão mostra a taxa, e a linha da taxa no card "Recebimentos" do Caixa.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QWidget

from gestor_comercial.domain.enums import FormaPagamento, StatusComanda
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.exceptions import RegraDeNegocioError
from gestor_comercial.ui.views.caixa_view import CaixaView
from gestor_comercial.ui.views.comanda_view import ComandaView
from gestor_comercial.ui.views.configuracoes_view import ConfiguracoesView
from gestor_comercial.ui.widgets.conferencia_dialog import ConferenciaMesaDialog, _CartaoTaxa


@pytest.fixture
def lanche(uow, categoria):
    return uow.produtos.salvar(Produto(nome="Artesanal", preco=Decimal("65.75"), categoria_id=categoria.id))


@pytest.fixture
def tela(qapp, comandas, cardapio, impressao, funcionarios, gerente, caixa_aberto, mesa, lanche):
    """A comanda da mesa com R$ 131,50 lançados — os R$ 131,50 do mockup."""
    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.lancar_item(comanda.id, lanche.id, 2)
    view = ComandaView(comandas, cardapio, impressao, funcionarios)
    view.carregar_comanda(comanda)
    yield view, comanda
    view.deleteLater()


@contextmanager
def _com_o_cartao(tela: QWidget, gesto: Callable[[ConferenciaMesaDialog], None]):
    """Responde ao cartão que abrir dentro do bloco, e diz o que viu nele.

    Um relógio procura o cartão visível e aplica o `gesto` uma vez. O teto é a
    lição do §9.14 (um helper que espera um diálogo que nunca vem TRAVA a suíte
    dentro do `exec()`), e o `finally` é a do §9.25: um `QTimer` de 0ms
    esquecido continua disparando pelo resto da sessão, rouba foco de outros
    diálogos e queima CPU.
    """
    vistos: list[str] = []
    relogio = QTimer()
    voltas = {"n": 0}

    def procurar() -> None:
        voltas["n"] += 1
        abertos = [d for d in tela.findChildren(ConferenciaMesaDialog) if d.isVisible()]
        if abertos:
            relogio.stop()
            cartao = abertos[0]
            vistos.append(cartao._valor_total.text())
            gesto(cartao)
        elif voltas["n"] > 200:
            relogio.stop()

    relogio.timeout.connect(procurar)
    relogio.start(0)
    try:
        yield vistos
    finally:
        relogio.stop()
        relogio.deleteLater()


def _confirmar(cartao: ConferenciaMesaDialog) -> None:
    cartao._botao_confirmar.click()


# ---------------------------------------------------------------------------
# O "Fechar conta" da comanda
# ---------------------------------------------------------------------------


def test_fechar_a_conta_grava_a_taxa_da_loja_e_o_valor_isolado(qapp, uow, tela):
    """§9.25: sem etapa de escolha — o cartão abre com a taxa já na conta, o
    garçom só confirma, e o que fica gravado é o que ele leu."""
    view, comanda = tela

    with _com_o_cartao(view, _confirmar) as vistos:
        view._botao_fechar_conferencia.click()

    assert vistos == ["R$ 144,65"], "o cartão abre com a taxa da loja no total"
    uow.session.rollback()
    gravada = uow.comandas.buscar_por_id(comanda.id)
    assert gravada.status is StatusComanda.EM_CONFERENCIA
    assert gravada.taxa_servico_percentual == Decimal("10")
    assert gravada.valor_taxa_servico == Decimal("13.15")
    # A tela já está travada para item novo: é a conta em conferência.
    assert not view._botao_add_item.isEnabled()
    assert view._botao_reabrir.isEnabled()


def test_com_a_loja_sem_taxa_a_conta_fecha_pelo_subtotal(qapp, uow, auth, tela, comandas):
    view, comanda = tela
    auth.loja_config.definir_aceita_taxa_servico(False)

    with _com_o_cartao(view, _confirmar) as vistos:
        view._botao_fechar_conferencia.click()

    assert vistos == ["R$ 131,50"]
    uow.session.rollback()
    gravada = uow.comandas.buscar_por_id(comanda.id)
    assert gravada.status is StatusComanda.EM_CONFERENCIA
    assert gravada.taxa_servico_percentual is None
    assert gravada.valor_taxa_servico == Decimal("0")
    assert comandas.calcular_total_a_pagar(comanda.id) == Decimal("131.50")


def test_cancelar_o_cartao_nao_fecha_a_conta(qapp, uow, tela):
    view, comanda = tela
    with _com_o_cartao(view, lambda cartao: cartao._botao_cancelar.click()):
        view._botao_fechar_conferencia.click()

    uow.session.rollback()
    assert uow.comandas.buscar_por_id(comanda.id).status is StatusComanda.ABERTA
    assert view._botao_add_item.isEnabled()


def test_loja_sem_taxa_abre_o_cartao_sem_o_bloco(qapp, uow, auth, tela):
    view, comanda = tela
    auth.loja_config.definir_aceita_taxa_servico(False)
    blocos: list[int] = []

    def _olhar_e_fechar(cartao: ConferenciaMesaDialog) -> None:
        blocos.append(len(cartao.findChildren(_CartaoTaxa)))
        cartao._botao_confirmar.click()

    with _com_o_cartao(view, _olhar_e_fechar):
        view._botao_fechar_conferencia.click()

    assert blocos == [0]
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(comanda.id).valor_taxa_servico == Decimal("0")


def test_a_loja_desligada_com_o_cartao_aberto_e_barrada_pelo_service(qapp, uow, auth, tela):
    """O cartão é uma foto tirada na abertura: o dono desliga a taxa enquanto o
    garçom está com ele aberto, e quem barra é o service — com a mensagem na
    linha da tela e a conta ainda aberta."""
    view, comanda = tela

    def _desligar_no_meio(cartao: ConferenciaMesaDialog) -> None:
        auth.loja_config.definir_aceita_taxa_servico(False)
        _confirmar(cartao)

    with _com_o_cartao(view, _desligar_no_meio):
        view._botao_fechar_conferencia.click()

    assert "não cobra taxa de serviço" in view._label_erro.text()
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(comanda.id).status is StatusComanda.ABERTA


# ---------------------------------------------------------------------------
# A Central de Loja
# ---------------------------------------------------------------------------


def test_o_interruptor_da_configuracoes_liga_e_desliga_a_taxa(qapp, uow, auth, gerente):
    tela = ConfiguracoesView(auth)
    cartao = tela._cartao_taxa_servico
    try:
        assert cartao.interruptor.ligado is True

        QTest.mouseClick(cartao, Qt.MouseButton.LeftButton)
        uow.session.rollback()
        assert (cartao.interruptor.ligado, auth.loja_config.aceita_taxa_servico()) == (False, False)

        QTest.mouseClick(cartao, Qt.MouseButton.LeftButton)
        uow.session.rollback()
        assert (cartao.interruptor.ligado, auth.loja_config.aceita_taxa_servico()) == (True, True)
    finally:
        tela.deleteLater()


def test_o_cartao_da_configuracoes_tem_o_texto_pedido(qapp, auth, gerente):
    tela = ConfiguracoesView(auth)
    try:
        textos = [rotulo.text() for rotulo in tela._cartao_taxa_servico.findChildren(QLabel)]
        assert textos == [
            "Cobrar taxa de serviço (10%)",
            "Habilita ou desabilita o cálculo e a exibição da taxa de 10% nas "
            "pré-contas e fechamentos de mesa.",
        ]
    finally:
        tela.deleteLater()


def test_se_a_gravacao_falhar_o_interruptor_mostra_o_que_vale(qapp, auth, gerente, monkeypatch):
    """O interruptor só muda DEPOIS de o service aceitar, relendo o banco: a
    tela nunca mostra "desligado" para uma loja que continua cobrando."""
    tela = ConfiguracoesView(auth)

    def _recusar(_aceita: bool) -> None:
        raise RegraDeNegocioError("Disco cheio.")

    monkeypatch.setattr(auth.loja_config, "definir_aceita_taxa_servico", _recusar)
    try:
        QTest.mouseClick(tela._cartao_taxa_servico, Qt.MouseButton.LeftButton)

        assert tela._cartao_taxa_servico.interruptor.ligado is True
        assert tela._label_erro.text() == "Disco cheio."
    finally:
        tela.deleteLater()


# ---------------------------------------------------------------------------
# O Caixa
# ---------------------------------------------------------------------------


def test_o_card_recebimentos_mostra_a_taxa_do_turno(qapp, comandas, pagamentos, caixas_service, impressao, tela):
    _view, comanda = tela
    comandas.fechar_para_conferencia(comanda.id, Decimal("10"))
    pagamentos.registrar(comanda.id, FormaPagamento.DINHEIRO, Decimal("144.65"))

    caixa = CaixaView(caixas_service, impressao)
    try:
        caixa.atualizar()
        assert caixa._label_taxa_servico.text() == "R$ 13,15"
    finally:
        caixa.deleteLater()
