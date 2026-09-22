"""A tela da mesa em duas colunas (§9.27).

Pedido do Vitor, com o mockup no padrão "Solvix POS": a `ComandaView` (uma
fileira de seis pílulas no cabeçalho, duas tabelas e a barra de TOTAL solta no
pé) virou a `MesaDetalheView` — cabeçalho com o "aberta há", o garçom e a
esteira de status, os itens à esquerda e o resumo com as ações à direita.

O que esta suíte cobra:

1. **o mockup** — cada frase da tela, e o total sendo a soma dos itens, sem
   vestígio da taxa de serviço (§9.26);
2. **cada botão chama o backend certo** — o pedido explícito: Adicionar item,
   Enviar à produção (e os atalhos), Remover, Cancelar item, Gerar
   Conta, Fechar Mesa, Reabrir, Cancelar comanda e a troca
   de garçom, cada um conferido no BANCO e não só na tela;
3. **a saída da mesa** — o aviso de pendências, com o "Enviar e Sair" que a
   tela antiga não deixava sair;
4. **quando cada botão liga** — as regras da tela antiga, estado a estado, e a
   esteira;
5. **o ciclo de vida** — linhas recicladas, as que sobram destruídas na troca
   de mesa, widgets estáveis em muitas trocas, um clique = uma chamada, e
   consultas fixas por recarga;
6. **o desenho** — nada espremido a 1366x738 nos dois temas, a coluna das
   ações sem rolagem, os glifos e os tokens.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QPushButton, QScrollArea, QWidget
from shiboken6 import isValid
from sqlalchemy import event

import gestor_comercial
from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import FormaPagamento, StatusComanda
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.comanda_service import EtapaDaComanda
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.rotulo_identidade import rotulo_do_operador
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.qss_app import construir_qss_app
from gestor_comercial.ui.theme.tokens import TEMA_CLARO, TEMA_ESCURO
from gestor_comercial.ui.views.cancelamento_dialog import CancelamentoDialog
from gestor_comercial.ui.views.mesa_detalhe_view import MesaDetalheView, tempo_desde, texto_de_abertura
from gestor_comercial.ui.widgets.adicionar_item_dialog import AdicionarItemDialog
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_CADEADO_ABERTO,
    GLIFO_ENVIAR,
    GLIFO_PANELA,
    GLIFO_RELOGIO,
    BotaoComGlifo,
    RotuloComReticencias,
    _caminho_do_glifo,
)
from gestor_comercial.ui.widgets.esteira_de_status import EstadoDaEtapa, estado_da_etapa
from gestor_comercial.ui.widgets.itens_da_comanda import CartaoDeItens, LinhaDeItem
from tests.conftest import PIN_GERENTE


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
def garcom(funcionarios, gerente):
    return funcionarios.criar("Lucas Prado", "Garçom")


@pytest.fixture
def mesa_12(uow, comandas, gerente, caixa_aberto, cardapio_do_mockup, impressao, garcom):
    """A mesa do mockup, aberta há 42 minutos: três produtos na chapa (6
    unidades, R$ 119,50) e um Anel de Cebola aguardando envio (R$ 12,00)."""
    mesa = uow.mesas.salvar(Mesa(numero=12))
    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.definir_atendente(comanda.id, garcom.id)
    comandas.lancar_item(comanda.id, cardapio_do_mockup["batata"].id, 1)
    comandas.lancar_item(comanda.id, cardapio_do_mockup["yakisoba"].id, 2)
    comandas.lancar_item(comanda.id, cardapio_do_mockup["coca"].id, 3)
    impressao.imprimir_comanda(comanda.id)
    comandas.lancar_item(comanda.id, cardapio_do_mockup["anel"].id, 1)
    uow.session.get(Comanda, comanda.id).aberta_em = datetime.now() - timedelta(minutes=42, seconds=10)
    uow.commit()
    return comanda


@pytest.fixture
def tela(qapp, comandas, cardapio, impressao, funcionarios, mesa_12):
    view = MesaDetalheView(comandas, cardapio, impressao, funcionarios)
    view.carregar_comanda(mesa_12)
    yield view
    view.deleteLater()


@contextmanager
def respondendo(tipo: type[QDialog], acao: Callable[[QDialog], None]) -> Iterator[list[QDialog]]:
    """Responde ao primeiro diálogo `tipo` que abrir dentro do bloco.

    Devolve a lista dos diálogos respondidos, para o teste conferir QUAL janela
    o botão abriu. O relógio tem teto (esperar um diálogo que nunca vem TRAVA a
    suíte dentro do `exec()`, a lição do §9.14) e é parado no `finally` (o
    `QTimer` de 0ms esquecido do §9.25 roubava o foco dos testes seguintes).
    """
    relogio = QTimer()
    respondidos: list[QDialog] = []
    voltas = {"n": 0}

    def procurar() -> None:
        voltas["n"] += 1
        modal = QApplication.activeModalWidget()
        if isinstance(modal, tipo):
            relogio.stop()
            respondidos.append(modal)
            acao(modal)
        elif voltas["n"] > 300:
            relogio.stop()

    relogio.timeout.connect(procurar)
    relogio.start(0)
    try:
        yield respondidos
    finally:
        relogio.stop()
        relogio.deleteLater()


def _autorizar(motivo: str = "cliente desistiu", pin: str = PIN_GERENTE) -> Callable[[QDialog], None]:
    def _acao(modal: QDialog) -> None:
        modal._campo_motivo.setText(motivo)
        modal._campo_pin_gerente.setText(pin)
        modal.accept()

    return _acao


def _clicar_na_caixa(texto: str) -> Callable[[QDialog], None]:
    def _acao(caixa: QDialog) -> None:
        next(botao for botao in caixa.buttons() if botao.text() == texto).click()

    return _acao


def _linhas(cartao: CartaoDeItens) -> list[tuple[str, int]]:
    return [(linha.linha.nome, linha.linha.quantidade) for linha in cartao.linhas]


def _textos(tela: QWidget) -> list[str]:
    textos = []
    for rotulo in tela.findChildren(QLabel):
        textos.append(rotulo.texto_completo() if isinstance(rotulo, RotuloComReticencias) else rotulo.text())
    for botao in tela.findChildren(QPushButton):
        textos += [botao.text(), botao.toolTip()]
    return textos


def _sinais(sinal) -> list:
    """O que o sinal emitiu: o valor, ou `()` para sinal sem argumento."""
    recebidos: list = []
    sinal.connect(lambda *valores: recebidos.append(valores[0] if valores else ()))
    return recebidos


# ---------------------------------------------------------------------------
# 1. O mockup
# ---------------------------------------------------------------------------


def test_o_mockup_frase_por_frase(tela, mesa_12, auth):
    assert tela._titulo.text() == "Mesa 12"
    assert tela._subtitulo.text() == f"Comanda #{mesa_12.id} · aberta há 42 min"
    assert tela._sobrescrito.text() == "GERENTE · GERENTE"
    assert tela._sobrescrito.text() == rotulo_do_operador(auth.usuario_logado), "o mesmo da tela de pagamento"
    assert tela._seletor_garcom.combo.currentText() == "Lucas Prado"
    assert tela._seletor_garcom._cargo.text() == "Garçom responsável"

    assert _linhas(tela._cartao_pendentes) == [("Anel de Cebola", 1)]
    assert _linhas(tela._cartao_enviados) == [
        ("Batata G Cheddar/Bacon", 1),
        ("Yakisoba Frango", 2),
        ("Coca-Cola 600ml", 3),
    ]
    assert tela._pilula_unidades.text() == "6 un."
    assert tela._resumo._valor_enviado.text() == "R$ 119,50"
    assert tela._resumo._valor_pendente.text() == "R$ 12,00"
    assert tela._resumo.texto_total == "R$ 131,50"
    assert tela._resumo._rotulo_total.text() == "TOTAL ESTIMADO"
    for frase in ("Aguardando envio", "Itens em produção", "RESUMO DA COMANDA", "PRÓXIMA AÇÃO"):
        assert frase in _textos(tela), frase


def test_a_linha_mostra_preco_quantidade_e_total(tela):
    yakisoba = tela._cartao_enviados.linhas[1]

    assert yakisoba._preco.text() == "R$ 32,00"
    assert yakisoba._quantidade.text() == "2"
    assert yakisoba._total.text() == "R$ 64,00"
    assert yakisoba.botao.text() == "Cancelar"
    assert tela._cartao_pendentes.linhas[0].botao.text() == "Remover"


def test_o_total_da_tela_e_o_do_service(tela, comandas, mesa_12):
    """O TOTAL ESTIMADO não é conta da tela: é `calcular_total`, a soma dos
    itens — sem taxa de serviço nenhuma desde o §9.26."""
    assert tela._resumo.texto_total == formatar_reais(comandas.calcular_total(mesa_12.id))
    assert tela._resumo.texto_total == formatar_reais(comandas.calcular_total_a_pagar(mesa_12.id))


def test_nao_ha_vestigio_da_taxa_de_servico(tela):
    """Nem o "Não inclui taxa de serviço" do mockup: a nota diz o que o total
    É, porque falar de uma taxa que o sistema não tem mais confundiria."""
    proibidas = ("taxa", "serviço", "servico", "comissão", "10%")
    achadas = [texto for texto in _textos(tela) for palavra in proibidas if palavra in texto.lower()]

    assert not achadas, achadas
    assert "Soma dos itens da comanda" in _textos(tela)


def test_o_balcao_nao_fala_em_mesa(qapp, comandas, cardapio, impressao, funcionarios, gerente, caixa_aberto, produto):
    comanda = comandas.abrir_balcao()
    comandas.lancar_item(comanda.id, produto.id, 1)
    view = MesaDetalheView(comandas, cardapio, impressao, funcionarios)
    try:
        view.carregar_comanda(comanda)

        assert view._titulo.text() == "Balcão"
        assert view._seletor_garcom.combo.currentText() == "Sem garçom"
        assert view._seletor_garcom._cargo.text() == "Clique para escolher"
    finally:
        view.deleteLater()


@pytest.mark.parametrize(
    ("passado", "esperado"),
    [
        (timedelta(seconds=20), "aberta agora"),
        (timedelta(minutes=42, seconds=59), "aberta há 42 min"),
        (timedelta(minutes=65), "aberta há 1h05"),
        (timedelta(hours=23, minutes=59), "aberta há 23h59"),
        (timedelta(days=1), "aberta desde 01/09 às 09:00"),
        (timedelta(days=1, hours=2), "aberta desde 01/09 às 09:00"),
        # Relógio do Windows voltando: nada de tempo negativo.
        (timedelta(minutes=-5), "aberta agora"),
    ],
)
def test_o_tempo_de_abertura(passado, esperado):
    aberta = datetime(2026, 9, 1, 9, 0)

    assert texto_de_abertura(aberta, aberta + passado) == esperado


def test_o_tempo_e_contado_em_minutos_inteiros():
    inicio = datetime(2026, 9, 1, 9, 0)

    assert tempo_desde(inicio, inicio + timedelta(seconds=59)) == "agora"
    assert tempo_desde(inicio, inicio + timedelta(minutes=1)) == "1 min"
    assert tempo_desde(inicio, inicio + timedelta(minutes=60)) == "1h00"


# ---------------------------------------------------------------------------
# 2. Cada botão chama o backend certo
# ---------------------------------------------------------------------------


def test_adicionar_item_abre_o_cartao_de_lancamento(tela):
    with respondendo(AdicionarItemDialog, lambda modal: modal.reject()) as abertos:
        tela._botao_add_item.click()

    assert len(abertos) == 1


def test_o_item_lancado_pelo_cartao_aparece_na_tela(tela, uow, mesa_12, cardapio_do_mockup):
    tela._lancar_item_do_modal(cardapio_do_mockup["coca"].id, 2, "com gelo")

    assert _linhas(tela._cartao_pendentes) == [("Anel de Cebola", 1), ("Coca-Cola 600ml", 2)]
    assert tela._cartao_pendentes.linhas[1]._observacao.texto_completo() == "com gelo"
    assert tela._resumo.texto_total == "R$ 150,50"
    uow.session.rollback()
    assert len(uow.itens.listar_por_comanda(mesa_12.id)) == 5, "o item foi gravado no banco"


def test_enviar_a_producao_marca_os_itens_e_move_para_producao(tela, uow, mesa_12):
    tela._botao_enviar.click()

    uow.session.rollback()
    assert all(item.impresso_em is not None for item in uow.itens.listar_por_comanda(mesa_12.id))
    assert _linhas(tela._cartao_pendentes) == []
    assert ("Anel de Cebola", 1) in _linhas(tela._cartao_enviados)
    assert tela._label_erro.property("tom") == "sucesso"
    assert tela._aviso_impressao.text(), "o aviso conta o que saiu (ou não) no papel"
    assert not tela._botao_enviar.isEnabled(), "sem pendência, o envio desliga"


@pytest.mark.parametrize("atalho", ["_atalho_enviar_f5", "_atalho_enviar_ctrl_enter"])
def test_os_atalhos_de_envio_continuam_ligados(tela, uow, mesa_12, atalho):
    getattr(tela, atalho).activated.emit()

    uow.session.rollback()
    assert all(item.impresso_em is not None for item in uow.itens.listar_por_comanda(mesa_12.id))


def test_remover_apaga_o_item_pendente_do_banco(tela, uow, mesa_12):
    item_id = tela._cartao_pendentes.linhas[0].linha.item_ids[0]

    tela._cartao_pendentes.linhas[0].botao.click()

    uow.session.rollback()
    assert uow.itens.buscar_por_id(item_id) is None
    assert _linhas(tela._cartao_pendentes) == []
    assert tela._label_erro.text() == "Anel de Cebola removido com sucesso."
    assert tela._resumo.texto_total == "R$ 119,50"


def test_cancelar_a_linha_pede_o_pin_e_cancela_cada_item_do_grupo(tela, uow, comandas, mesa_12, cardapio_do_mockup, impressao):
    """A linha da Coca soma dois lançamentos: o Cancelar grava o cancelamento
    nos DOIS `ItemComanda` por baixo, com o gerente que autorizou."""
    comandas.lancar_item(mesa_12.id, cardapio_do_mockup["coca"].id, 1)
    impressao.imprimir_comanda(mesa_12.id)
    tela.atualizar()
    coca = next(linha for linha in tela._cartao_enviados.linhas if linha.linha.nome == "Coca-Cola 600ml")
    ids = coca.linha.item_ids
    assert len(ids) == 2

    with respondendo(CancelamentoDialog, _autorizar()) as abertos:
        coca.botao.click()

    assert abertos and abertos[0].windowTitle() == "Cancelar 2x Coca-Cola 600ml"
    uow.session.rollback()
    for item_id in ids:
        item = uow.itens.buscar_por_id(item_id)
        assert item.cancelado and item.motivo_cancelamento == "cliente desistiu"
    assert "autorizado por Gerente" in tela._label_erro.text()
    assert "Coca-Cola 600ml" not in [nome for nome, _ in _linhas(tela._cartao_enviados)]


def test_cancelar_com_pin_errado_nao_cancela(tela, uow):
    batata = tela._cartao_enviados.linhas[0]
    item_id = batata.linha.item_ids[0]

    with respondendo(CancelamentoDialog, _autorizar(pin="0000")):
        batata.botao.click()

    uow.session.rollback()
    assert not uow.itens.buscar_por_id(item_id).cancelado
    assert tela._label_erro.property("tom") == "erro"
    assert tela._label_erro.text()


def test_desistir_do_cancelamento_nao_mexe_em_nada(tela, uow):
    batata = tela._cartao_enviados.linhas[0]
    item_id = batata.linha.item_ids[0]

    with respondendo(CancelamentoDialog, lambda modal: modal.reject()):
        batata.botao.click()

    uow.session.rollback()
    assert not uow.itens.buscar_por_id(item_id).cancelado


def test_gerar_conta_imprime_a_pre_conta_sem_modal(tela, uow, impressao, mesa_12, monkeypatch):
    """Um clique: trava a conta e manda a pré-conta à impressora, sem cartão."""
    chamadas: list[int] = []
    original = impressao.imprimir_pre_conta

    def espiao(comanda_id: int):
        chamadas.append(comanda_id)
        return original(comanda_id)

    monkeypatch.setattr(impressao, "imprimir_pre_conta", espiao)

    assert tela._acoes.botao_fechar.text() == "Gerar Conta"
    tela._acoes.botao_fechar.click()  # um modal aqui travaria o teste no exec()

    assert chamadas == [mesa_12.id]
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(mesa_12.id).status is StatusComanda.EM_CONFERENCIA
    assert tela._esteira.estado(EtapaDaComanda.CONFERENCIA) is EstadoDaEtapa.ATUAL
    assert tela._resumo._rotulo_total.text() == "TOTAL DA CONTA"
    assert tela._aviso_impressao.text()


def test_fechar_mesa_em_conferencia_vai_direto_ao_pagamento(tela, comandas, mesa_12):
    comandas.fechar_para_conferencia(mesa_12.id)
    tela.atualizar()
    pedidos = _sinais(tela.pagamento_solicitado)

    tela._acoes.botao_receber.click()

    assert pedidos == [mesa_12.id]


def test_fechar_mesa_sem_gerar_conta_vai_ao_pagamento(tela, uow, impressao, mesa_12, monkeypatch):
    """Não depende da pré-conta: a tela põe a conta em conferência por baixo,
    sem imprimir nada."""
    impressao.imprimir_comanda(mesa_12.id)
    tela.atualizar()
    pre_contas: list[int] = []
    monkeypatch.setattr(impressao, "imprimir_pre_conta", pre_contas.append)
    pedidos = _sinais(tela.pagamento_solicitado)

    assert tela._acoes.botao_receber.text() == "Fechar Mesa"
    assert tela._acoes.botao_receber.isEnabled()
    tela._acoes.botao_receber.click()

    assert pedidos == [mesa_12.id]
    assert pre_contas == []
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(mesa_12.id).status is StatusComanda.EM_CONFERENCIA


def test_fechar_mesa_com_pendencia_passa_pelo_aviso(tela, uow, mesa_12):
    """O Anel de Cebola ainda não foi à cozinha: travar a conta sem perguntar
    o deixaria preso fora da chapa."""
    pedidos = _sinais(tela.pagamento_solicitado)

    with respondendo(QMessageBox, _clicar_na_caixa("Continuar Editando")) as abertos:
        tela._acoes.botao_receber.click()

    assert len(abertos) == 1
    assert pedidos == []
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(mesa_12.id).status is StatusComanda.ABERTA


def test_reabrir_pede_o_pin_e_devolve_a_conta(tela, uow, comandas, mesa_12):
    comandas.fechar_para_conferencia(mesa_12.id)
    tela.atualizar()

    with respondendo(CancelamentoDialog, _autorizar(motivo="")) as abertos:
        tela._acoes.botao_reabrir.click()

    assert abertos and abertos[0].windowTitle() == f"Reabrir comanda {mesa_12.id}"
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(mesa_12.id).status is StatusComanda.ABERTA
    assert tela._label_erro.text() == "Comanda reaberta. Itens liberados novamente."
    assert tela._botao_add_item.isEnabled()


def test_cancelar_a_comanda_pede_o_pin_e_avisa_a_navegacao(tela, uow, mesa_12):
    canceladas = _sinais(tela.comanda_cancelada)

    with respondendo(CancelamentoDialog, _autorizar()) as abertos:
        tela._acoes.botao_cancelar.click()

    assert abertos and abertos[0].windowTitle() == f"Cancelar comanda {mesa_12.id}"
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(mesa_12.id).status is StatusComanda.CANCELADA
    assert canceladas == [mesa_12.id]


def test_trocar_o_garcom_grava_no_banco(tela, uow, funcionarios, mesa_12):
    ana = funcionarios.criar("Ana Souza", "Garçom")
    combo = tela._seletor_garcom.combo
    combo.carregar_opcoes()
    indice = combo.findData(ana.id)

    combo.setCurrentIndex(indice)
    combo.activated.emit(indice)

    uow.session.rollback()
    assert uow.comandas.buscar_por_id(mesa_12.id).atendente_id == ana.id
    assert combo.count() == 1, "depois de escolher, o cartão volta ao nome só"
    assert combo.currentText() == "Ana Souza"


def test_tirar_o_garcom_grava_ninguem(tela, uow, mesa_12):
    combo = tela._seletor_garcom.combo
    combo.carregar_opcoes()
    indice = combo.findData(None)

    combo.setCurrentIndex(indice)
    combo.activated.emit(indice)

    uow.session.rollback()
    assert uow.comandas.buscar_por_id(mesa_12.id).atendente_id is None
    assert tela._seletor_garcom._cargo.text() == "Clique para escolher"


def test_escolher_o_mesmo_garcom_nao_grava(tela, comandas, garcom, monkeypatch):
    gravacoes: list = []
    monkeypatch.setattr(comandas, "definir_atendente", lambda *args: gravacoes.append(args))
    combo = tela._seletor_garcom.combo
    combo.carregar_opcoes()
    indice = combo.findData(garcom.id)

    combo.activated.emit(indice)

    assert gravacoes == []
    assert combo.count() == 1


def test_o_garcom_desativado_continua_na_lista_da_comanda_dele(tela, funcionarios, garcom):
    funcionarios.desativar(garcom.id)
    combo = tela._seletor_garcom.combo

    combo.carregar_opcoes()

    assert combo.findData(garcom.id) >= 0, "abrir a lista não pode sumir com quem atendeu"


def test_abrir_o_combo_carrega_a_lista(tela, funcionarios):
    funcionarios.criar("Ana Souza", "Garçom")
    combo = tela._seletor_garcom.combo
    assert combo.count() == 1

    combo.showPopup()
    try:
        nomes = [combo.itemText(indice) for indice in range(combo.count())]
    finally:
        combo.hidePopup()

    assert nomes == ["Sem garçom", "Ana Souza", "Lucas Prado"], "ninguém primeiro, depois em ordem alfabética"
    assert combo.currentText() == "Lucas Prado", "abrir a lista não troca quem está escolhido"


def test_a_lista_de_garcons_so_e_lida_ao_abrir(tela, funcionarios, monkeypatch):
    """A tela antiga relia TODOS os funcionários a cada item lançado."""
    leituras: list[int] = []
    original = funcionarios.listar_ativos
    monkeypatch.setattr(funcionarios, "listar_ativos", lambda: leituras.append(1) or original())

    for _ in range(5):
        tela.atualizar()
    assert leituras == []

    tela._seletor_garcom.combo.carregar_opcoes()
    assert leituras == [1]


# ---------------------------------------------------------------------------
# 3. A saída da mesa
# ---------------------------------------------------------------------------


def test_sem_pendencia_o_voltar_sai_direto(tela):
    tela._cartao_pendentes.linhas[0].botao.click()
    saidas = _sinais(tela.voltar)

    tela._botao_voltar.click()

    assert len(saidas) == 1


def test_enviar_e_sair_envia_e_sai(tela, uow, mesa_12):
    """O defeito que a tela antiga tinha (§9.27): ela decidia sair pela linha
    de mensagem VAZIA, e o envio que dá certo escreve "Pedido enviado… com
    sucesso!" nela — o pedido ia para a cozinha e o operador ficava na mesa."""
    saidas = _sinais(tela.voltar)

    with respondendo(QMessageBox, _clicar_na_caixa("Enviar e Sair")):
        tela._botao_voltar.click()

    assert len(saidas) == 1, "o pedido foi enviado e o operador tem que sair"
    uow.session.rollback()
    assert all(item.impresso_em is not None for item in uow.itens.listar_por_comanda(mesa_12.id))


def test_descartar_e_sair_apaga_os_pendentes_e_sai(tela, uow, mesa_12):
    saidas = _sinais(tela.voltar)

    with respondendo(QMessageBox, _clicar_na_caixa("Descartar Pendências e Sair")):
        tela._botao_voltar.click()

    assert len(saidas) == 1
    uow.session.rollback()
    nomes = [item.produto.nome for item in uow.itens.listar_por_comanda(mesa_12.id)]
    assert "Anel de Cebola" not in nomes
    assert len(nomes) == 3, "os enviados ficam"


def test_continuar_editando_fica_na_mesa(tela, uow, mesa_12):
    saidas = _sinais(tela.voltar)

    with respondendo(QMessageBox, _clicar_na_caixa("Continuar Editando")):
        tela._botao_voltar.click()

    assert saidas == []
    assert tela.possui_itens_pendentes()


def test_a_navegacao_de_fora_passa_pelo_mesmo_aviso(tela):
    """Sidebar e logout chamam `tentar_sair`: a pendência não escapa por lá."""
    destinos: list[str] = []

    with respondendo(QMessageBox, _clicar_na_caixa("Continuar Editando")) as abertos:
        tela.tentar_sair(lambda: destinos.append("Caixa"))

    assert len(abertos) == 1
    assert destinos == []


# ---------------------------------------------------------------------------
# 4. Quando cada botão liga
# ---------------------------------------------------------------------------


def _estado_dos_botoes(tela: MesaDetalheView) -> dict[str, str]:
    def estado(botao: QPushButton) -> str:
        if botao.isHidden():
            return "some"
        return "liga" if botao.isEnabled() else "apaga"

    acoes = tela._acoes
    return {
        "adicionar": estado(tela._botao_add_item),
        "enviar": estado(tela._botao_enviar),
        "fechar": estado(acoes.botao_fechar),
        "receber": estado(acoes.botao_receber),
        "reabrir": estado(acoes.botao_reabrir),
        "cancelar": estado(acoes.botao_cancelar),
    }


def test_a_mesa_aberta_com_itens(tela):
    assert _estado_dos_botoes(tela) == {
        "adicionar": "liga",
        "enviar": "liga",
        "fechar": "liga",
        "receber": "liga",
        "reabrir": "some",
        "cancelar": "liga",
    }
    assert all(linha.botao.isEnabled() for linha in tela._cartao_enviados.linhas)


def test_a_mesa_aberta_sem_item(qapp, uow, comandas, cardapio, impressao, funcionarios, gerente, caixa_aberto):
    comanda = comandas.abrir_por_mesa(uow.mesas.salvar(Mesa(numero=7)).id)
    view = MesaDetalheView(comandas, cardapio, impressao, funcionarios)
    try:
        view.carregar_comanda(comanda)

        assert _estado_dos_botoes(view) == {
            "adicionar": "liga",
            "enviar": "apaga",
            "fechar": "apaga",
            "receber": "liga",
            "reabrir": "some",
            "cancelar": "liga",
        }
        assert view._cartao_pendentes._vazio.isVisibleTo(view)
        assert not view._pilula_unidades.isVisibleTo(view)
    finally:
        view.deleteLater()


def test_a_conta_em_conferencia_troca_o_fechar_pelo_reabrir(tela, comandas, mesa_12, impressao):
    """Decisão do Vitor: o Reabrir é botão próprio, só em conferência. E o
    Fechar, que ali nunca poderia ser usado, sai do lugar — o painel tem sempre
    três botões, e a coluna cabe nos 738px (ver o teste de desenho)."""
    impressao.imprimir_comanda(mesa_12.id)
    comandas.fechar_para_conferencia(mesa_12.id)
    tela.atualizar()

    assert _estado_dos_botoes(tela) == {
        "adicionar": "apaga",
        "enviar": "apaga",
        "fechar": "some",
        "receber": "liga",
        "reabrir": "liga",
        "cancelar": "apaga",
    }
    assert not any(linha.botao.isEnabled() for linha in tela._cartao_enviados.linhas)


def test_o_pagamento_parcial_aparece_no_resumo(tela, uow, auth, comandas, funcionarios, mesa_12, impressao):
    from gestor_comercial.services.pagamento_service import PagamentoService

    impressao.imprimir_comanda(mesa_12.id)
    comandas.fechar_para_conferencia(mesa_12.id)
    assert not tela._resumo._linha_recebido.isVisibleTo(tela)
    PagamentoService(uow, auth, comandas, funcionarios).registrar(mesa_12.id, FormaPagamento.PIX, Decimal("31.50"))

    tela.atualizar()

    assert tela._resumo._linha_recebido.isVisibleTo(tela)
    assert tela._resumo._valor_recebido.text() == "R$ 31,50"
    assert tela._esteira.estado(EtapaDaComanda.PAGAMENTO) is EstadoDaEtapa.ATUAL


def test_a_esteira_da_mesa_do_mockup(tela):
    assert [tela._esteira.estado(etapa) for etapa in EtapaDaComanda] == [
        EstadoDaEtapa.FEITA,
        EstadoDaEtapa.ATUAL,
        EstadoDaEtapa.A_CAMINHO,
        EstadoDaEtapa.A_CAMINHO,
    ]
    rotulo = tela._esteira._rotulos[EtapaDaComanda.PRODUCAO]
    assert rotulo.property("estado") == "atual", "o rótulo acende junto com a marca"


@pytest.mark.parametrize("atual", [*EtapaDaComanda, None])
def test_a_regra_da_esteira(atual):
    estados = [estado_da_etapa(etapa, atual) for etapa in EtapaDaComanda]

    if atual is None:
        assert set(estados) == {EstadoDaEtapa.A_CAMINHO}
        return
    posicao = list(EtapaDaComanda).index(atual)
    assert estados[:posicao] == [EstadoDaEtapa.FEITA] * posicao
    assert estados[posicao] is EstadoDaEtapa.ATUAL
    assert set(estados[posicao + 1 :]) <= {EstadoDaEtapa.A_CAMINHO}


def test_a_moldura_de_aguardando_so_acende_com_item(tela):
    assert tela._cartao_pendentes.destacado

    tela._cartao_pendentes.linhas[0].botao.click()

    assert not tela._cartao_pendentes.destacado
    assert not tela._cartao_enviados.destacado, "o cartão de produção nunca acende"


# ---------------------------------------------------------------------------
# 5. O ciclo de vida
# ---------------------------------------------------------------------------


def test_as_linhas_sao_recicladas_a_cada_lancamento(tela, cardapio_do_mockup):
    """Lançar pelo cartão recarrega a tela a cada item: as linhas que já
    existem são as MESMAS, e só a nova nasce."""
    enviadas_antes = tela._cartao_enviados.linhas
    pendente_antes = tela._cartao_pendentes.linhas[0]

    tela._lancar_item_do_modal(cardapio_do_mockup["coca"].id, 1, None)
    tela._lancar_item_do_modal(cardapio_do_mockup["batata"].id, 1, None)

    assert tela._cartao_enviados.linhas == enviadas_antes
    assert tela._cartao_pendentes.linhas[0] is pendente_antes
    assert len(tela._cartao_pendentes.linhas) == 3


def test_trocar_para_uma_mesa_menor_destroi_as_linhas_que_sobram(tela, assentar, uow, comandas, produto):
    enviadas = tela._cartao_enviados.linhas
    assert len(enviadas) == 3
    menor = comandas.abrir_por_mesa(uow.mesas.salvar(Mesa(numero=13)).id)
    comandas.lancar_item(menor.id, produto.id, 1)

    tela.carregar_comanda(menor)
    assentar()

    assert tela._cartao_enviados.linhas == []
    assert not any(isValid(linha) for linha in enviadas), "a linha que sai da tela sai da memória"
    assert len(tela.findChildren(LinhaDeItem)) == 1


def test_trocar_de_mesa_muitas_vezes_nao_acumula_widgets(tela, assentar, uow, comandas, produto, mesa_12):
    outra = comandas.abrir_por_mesa(uow.mesas.salvar(Mesa(numero=13)).id)
    comandas.lancar_item(outra.id, produto.id, 1)

    def ciclos(vezes: int) -> int:
        for _ in range(vezes):
            tela.carregar_comanda(outra)
            tela.carregar_comanda(mesa_12)
        assentar()
        return len(QApplication.allWidgets())

    depois_de_aquecer = ciclos(5)

    assert ciclos(40) == depois_de_aquecer


def test_um_clique_e_uma_chamada_depois_de_muitas_recargas(tela, comandas, monkeypatch):
    """A tela antiga ligava um `lambda` novo a cada recarga; aqui a linha liga
    o botão UMA vez. Vinte recargas depois, um clique continua sendo um só."""
    for _ in range(20):
        tela.atualizar()
    chamadas: list[int] = []
    original = comandas.remover_item
    monkeypatch.setattr(comandas, "remover_item", lambda item_id: chamadas.append(item_id) or original(item_id))

    tela._cartao_pendentes.linhas[0].botao.click()

    assert len(chamadas) == 1


def _consultas(uow, acao: Callable[[], None]) -> int:
    uow.session.expunge_all()
    contagem = {"n": 0}

    def _contar(*_argumentos, **_nomeados) -> None:
        contagem["n"] += 1

    event.listen(uow.session.bind, "before_cursor_execute", _contar)
    try:
        acao()
    finally:
        event.remove(uow.session.bind, "before_cursor_execute", _contar)
    return contagem["n"]


def test_a_recarga_nao_cresce_em_consultas_com_a_conta(tela, uow, comandas, categoria, impressao, mesa_12):
    categoria_id = categoria.id
    antes = _consultas(uow, tela.atualizar)
    for i in range(10):
        novo = uow.produtos.salvar(Produto(nome=f"Extra {i}", preco=Decimal("4.00"), categoria_id=categoria_id))
        comandas.lancar_item(mesa_12.id, novo.id, 1)
    impressao.imprimir_comanda(mesa_12.id)

    depois = _consultas(uow, tela.atualizar)

    assert depois == antes, f"{antes} consultas com 4 itens, {depois} com 14"


def test_o_relogio_so_corre_com_a_tela_visivel_e_nao_vai_ao_banco(tela, uow, mesa_12):
    assert not tela._relogio.isActive()
    tela.show()
    assert tela._relogio.isActive()
    tela._subtitulo.setText("")

    assert _consultas(uow, tela._relogio.timeout.emit) == 0
    assert tela._subtitulo.text() == f"Comanda #{mesa_12.id} · aberta há 42 min"

    tela.hide()
    assert not tela._relogio.isActive()


# ---------------------------------------------------------------------------
# 6. O desenho
# ---------------------------------------------------------------------------


@pytest.fixture(params=[False, True], ids=["escuro", "claro"])
def com_fonte_e_tema(qapp, request):
    caminho = Path(gestor_comercial.__file__).resolve().parents[2] / "resources" / "fonts" / "ArchivoBlack-Regular.ttf"
    if not caminho.exists():  # pragma: no cover - só num checkout incompleto
        pytest.skip(f"fonte da marca ausente em {caminho}")
    identificador = QFontDatabase.addApplicationFont(str(caminho))
    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    controlador.alternar_para(request.param)
    try:
        yield
    finally:
        controlador.alternar_para(False)
        QFontDatabase.removeApplicationFont(identificador)


# A página da tela dentro do shell a 1366x738: tira a sidebar (212) e as margens
# da coluna (24 + 24) da largura; as margens (20 + 20) e a barra de usuário da
# altura. Medido na renderização da MainWindow.
PAGINA_1366x738 = (1106, 682)


def test_a_1366x738_nada_e_espremido_e_as_acoes_cabem_sem_rolagem(
    qapp, com_fonte_e_tema, tela, assentar, uow, auth, comandas, funcionarios, mesa_12, impressao
):
    """O pior caso da coluna direita: conta em conferência com pagamento
    parcial — entram o "Reabrir" e a linha "Já recebido". Foi esse estado que a
    renderização pegou com rolagem e o "Cancelar comanda" escondido embaixo,
    antes de o "Fechar" sair do lugar em conferência."""
    from gestor_comercial.services.pagamento_service import PagamentoService

    impressao.imprimir_comanda(mesa_12.id)
    comandas.fechar_para_conferencia(mesa_12.id)
    PagamentoService(uow, auth, comandas, funcionarios).registrar(mesa_12.id, FormaPagamento.PIX, Decimal("10.00"))
    tela.atualizar()

    janela = QWidget()
    janela.resize(*PAGINA_1366x738)
    tela.setParent(janela)
    tela.resize(*PAGINA_1366x738)
    janela.show()
    qapp.processEvents()

    espremidos = {}
    for peca in tela.findChildren(QWidget):
        if not isinstance(peca, (QLabel, QPushButton)) or not peca.isVisible():
            continue
        if isinstance(peca, RotuloComReticencias):
            continue  # encurta com reticências por construção (§9.8)
        if isinstance(peca, QLabel) and peca.wordWrap():
            if peca.height() < peca.heightForWidth(peca.width()):
                espremidos[peca.objectName()] = ("altura", peca.height(), peca.heightForWidth(peca.width()))
            continue
        if peca.width() < peca.sizeHint().width():
            espremidos[peca.objectName()] = ("largura", peca.width(), peca.sizeHint().width())
        if peca.height() < peca.sizeHint().height():
            espremidos[peca.objectName()] = ("altura", peca.height(), peca.sizeHint().height())
    coluna_das_acoes = tela._acoes.parentWidget().parentWidget().parentWidget()
    assert isinstance(coluna_das_acoes, QScrollArea)
    rolagem = coluna_das_acoes.verticalScrollBar().maximum()

    tela.setParent(None)
    janela.close()
    janela.deleteLater()
    assentar()
    assert not espremidos, f"peças espremidas (eixo, tem, pede): {espremidos}"
    assert rolagem == 0, f"a coluna das ações rolou {rolagem}px a 1366x738"


def test_as_pilulas_do_cabecalho_tem_altura_para_o_raio(tela):
    """O Qt ignora raio maior que meia altura e desenha o botão quadrado (§9.15):
    as duas pílulas do cabeçalho têm raio de 18px."""
    for botao in (tela._botao_voltar, tela._botao_add_item):
        assert botao.minimumHeight() >= 2 * 18, botao.text()


def _padding(qss: str, seletor: str) -> tuple[int, int]:
    bloco = re.search(re.escape(seletor) + r"\s*\{([^}]*)\}", qss)
    assert bloco, seletor
    topo, direita, baixo, esquerda = (int(v.rstrip("px")) for v in re.search(r"padding:\s*([^;]+);", bloco.group(1)).group(1).split())
    return esquerda, direita


@pytest.mark.parametrize(
    "seletor",
    [
        "QPushButton#mesaDetBotaoAdicionar",
        "QPushButton#mesaDetBotaoEnviar",
        "QPushButton#mesaDetAcaoItem",
        "QPushButton#mesaDetBotaoFechar",
        "QPushButton#mesaDetBotaoReceber",
        "QPushButton#mesaDetBotaoNeutro",
        "QPushButton#mesaDetBotaoCancelar",
    ],
)
def test_o_botao_de_glifo_centrado_tem_o_padding_do_deslocamento(seletor):
    """O par glifo+texto só fica no meio do botão se o QSS der, na esquerda, o
    `DESLOCAMENTO_CENTRADO_PX` a mais — é o que empurra o texto meia-folga."""
    esquerda, direita = _padding(construir_qss_app(TEMA_ESCURO), seletor)

    assert esquerda - direita == BotaoComGlifo.DESLOCAMENTO_CENTRADO_PX


def test_o_glifo_centrado_fica_colado_ao_texto(qapp):
    botao = BotaoComGlifo("Receber pagamento", GLIFO_ENVIAR, "texto", "texto", centrado=True)
    botao.resize(300, 40)
    # Mede DEPOIS de polido, como o botão: o QSS troca a fonte (§9.8), e medir
    # antes dá a largura de outra letra.
    botao.ensurePolished()
    largura_texto = botao.fontMetrics().horizontalAdvance(botao.text())

    assert botao._x_do_glifo() == (300 - largura_texto - BotaoComGlifo.DESLOCAMENTO_CENTRADO_PX) / 2
    assert BotaoComGlifo("x", GLIFO_ENVIAR, "texto", "texto")._x_do_glifo() == BotaoComGlifo.X_GLIFO_PX


@pytest.mark.parametrize("glifo", [GLIFO_RELOGIO, GLIFO_ENVIAR, GLIFO_PANELA, GLIFO_CADEADO_ABERTO])
def test_os_glifos_novos_tem_desenho(glifo):
    """Nome de glifo sem ramo no `_caminho_do_glifo` desenha NADA, calado."""
    assert _caminho_do_glifo(glifo).elementCount() > 0


def test_os_tokens_da_tela_existem_nos_dois_temas():
    familia = {chave for chave in TEMA_ESCURO if chave.startswith("mesa_detalhe_")}

    assert len(familia) > 30
    assert familia == {chave for chave in TEMA_CLARO if chave.startswith("mesa_detalhe_")}


def test_a_tela_antiga_saiu_por_inteiro():
    """Nem o módulo, nem os seletores que só ela usava, nem as cores deles."""
    with pytest.raises(ModuleNotFoundError):
        __import__("gestor_comercial.ui.views.comanda_view")
    qss = construir_qss_app(TEMA_ESCURO)
    for seletor in ("tabela-comanda", "secao-pendentes", "secao-lancados", "barra-total", "combo-atendente",
                    "comandaTitulo", "comandaHorario", "remover-tabela", "perigo-tabela"):
        assert seletor not in qss, seletor
    for chave in ("tabela_comanda_texto", "secao_pendentes_bg", "combo_atendente_bg", "remover_tabela_bg"):
        assert chave not in TEMA_ESCURO, chave
