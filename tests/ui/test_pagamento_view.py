"""A tela "Receber Pagamento". §9.25, sem a taxa e sem a comissão desde o §9.26.

Pedido do Vitor, com o mockup: o último diálogo de fábrica do fluxo de venda
(combo de forma, campo de texto, resumo em três linhas) virou tela, com o
consumo à esquerda, as formas em cards e o troco ao vivo.

A linha "Serviço" e o card "Comissão de [garçom]" nasceram aqui no §9.25 e
saíram no §9.26 com a taxa de serviço: a comissão nunca teve valor próprio —
ela ERA a taxa da conta —, e sem a taxa o card só saberia dizer R$ 0,00.

O que esta suíte cobra:

1. **o mockup** — cabeçalho, itens, subtotal, total e "por pessoa";
2. **o total é o consumo** — nenhum acréscimo entre o subtotal e o que se
   recebe, e nenhum vestígio da taxa ou da comissão na tela;
3. **dividir por** — só mostra quanto dá por pessoa, sem mexer no que é lançado;
4. **as formas** — o card escolhido acende, "Consumo" abre o seletor de
   funcionário, e só dinheiro mostra troco;
5. **o recebimento** — fecha a conta e avisa no parcial;
6. **o desenho** — nada espremido a 1366x738, nos dois temas.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

import gestor_comercial
from gestor_comercial.domain.enums import FormaPagamento, StatusComanda
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.assinatura import ler_assinatura
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.views.pagamento_view import PagamentoView
from gestor_comercial.ui.widgets.modal_assinatura_manuscrita import ModalAssinaturaManuscrita
from gestor_comercial.ui.widgets.pin_pad_dialog import PinPadDialog
from tests.conftest import PIN_GERENTE


@pytest.fixture
def garcom(funcionarios, gerente):
    return funcionarios.criar("Lucas Prado", "Garçom")


@pytest.fixture
def conta(uow, comandas, gerente, caixa_aberto, categoria, garcom):
    """A mesa 12 do mockup, em conferência: 2 x R$ 65,75 = R$ 131,50.

    O mockup do §9.25 dizia R$ 144,65, que era o mesmo consumo com os 10% da
    taxa por cima. A taxa saiu no §9.26 e o número da mesa passou a ser o do
    consumo.
    """
    lanche = uow.produtos.salvar(
        Produto(nome="Artesanal", preco=Decimal("65.75"), categoria_id=categoria.id)
    )
    mesa = uow.mesas.salvar(Mesa(numero=12))
    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.lancar_item(comanda.id, lanche.id, 2)
    comandas.definir_atendente(comanda.id, garcom.id)
    comandas.fechar_para_conferencia(comanda.id)
    return comanda


@pytest.fixture
def tela(qapp, pagamentos, impressao, conta):
    view = PagamentoView(pagamentos, impressao)
    view.carregar(conta.id)
    yield view
    view.deleteLater()


def _textos(widget: QWidget) -> list[str]:
    return [rotulo.text() for rotulo in widget.findChildren(QLabel)]


def _recebidos(tela: PagamentoView) -> list[int]:
    recebidos: list[int] = []
    tela.pagamento_concluido.connect(recebidos.append)
    return recebidos


# ---------------------------------------------------------------------------
# 1. O mockup
# ---------------------------------------------------------------------------


def test_o_mockup_frase_por_frase(tela, conta):
    textos = _textos(tela)

    assert tela._titulo.text() == "Receber Pagamento · Mesa 12"
    assert tela._subtitulo.text() == f"Comanda #{conta.id} · Garçom Lucas Prado"
    assert tela._rotulo_comanda.text() == f"COMANDA #{conta.id}"
    assert tela._titulo_consumo.text() == "Consumo da mesa"
    for frase in ("2×", "Artesanal", "Subtotal", "Total da conta", "TROCO"):
        assert frase in textos, frase
    assert tela._valor_subtotal.text() == "R$ 131,50"
    assert tela._valor_total.text() == "R$ 131,50"
    assert tela._campo_valor.valor() == Decimal("131.50"), "o campo já vem com o que falta"
    assert tela._valor_troco.text() == "R$ 0,00"


def test_a_comanda_de_balcao_nao_fala_em_mesa(qapp, comandas, pagamentos, impressao, uow, gerente, caixa_aberto, categoria):
    produto = uow.produtos.salvar(Produto(nome="Suco", preco=Decimal("10.00"), categoria_id=categoria.id))
    comanda = comandas.abrir_balcao()
    comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.fechar_para_conferencia(comanda.id)

    view = PagamentoView(pagamentos, impressao)
    try:
        view.carregar(comanda.id)

        assert view._titulo.text() == "Receber Pagamento · Balcão"
        assert view._titulo_consumo.text() == "Consumo da comanda"
        assert view._valor_total.text() == "R$ 10,00"
    finally:
        view.deleteLater()


# ---------------------------------------------------------------------------
# 2. O total é o consumo, e nada mais
# ---------------------------------------------------------------------------


def test_o_total_e_o_subtotal_sem_acrescimo(tela):
    """§9.26: entre o que o cliente consumiu e o que ele paga não entra nada.

    Até o §9.25 havia a linha "Serviço 10%" no meio, e esta mesa saía por
    R$ 144,65. Qualquer acréscimo que volte reprova aqui.
    """
    assert tela._valor_total.text() == tela._valor_subtotal.text() == "R$ 131,50"
    assert tela._conta.total == tela._conta.subtotal == Decimal("131.50")


def test_nao_sobrou_vestigio_da_taxa_nem_da_comissao(tela):
    """Nem linha, nem card, nem estado guardado na tela."""
    textos = " ".join(_textos(tela)).lower()

    assert "serviço" not in textos
    assert "taxa" not in textos
    assert "comissão" not in textos
    for atributo in ("_valor_taxa", "_rotulo_taxa", "_cartao_comissao", "_comissao_paga"):
        assert not hasattr(tela, atributo), atributo


# ---------------------------------------------------------------------------
# 3. Dividir por
# ---------------------------------------------------------------------------


def test_dividir_por_so_mostra_o_valor_por_pessoa(tela):
    """Decisão do Vitor: o pagamento continua sendo lançado por valor recebido."""
    tela._dividir_por(2)

    assert tela._rotulo_por_pessoa.text() == "Por pessoa (2)"
    # 131,50 / 2 = 65,75 exatos; o arredondamento para cima não tem o que subir.
    assert tela._valor_por_pessoa.text() == "R$ 65,75"
    assert tela._campo_valor.valor() == Decimal("131.50"), "o valor a receber não muda"
    assert [p.text() for p in tela._pilulas if p.property("ativa")] == ["2"]


# ---------------------------------------------------------------------------
# 4. As formas
# ---------------------------------------------------------------------------


def test_a_forma_escolhida_acende_e_as_outras_apagam(tela):
    QTest.mouseClick(tela._cartoes_forma[FormaPagamento.PIX], Qt.MouseButton.LeftButton)

    acesas = [forma for forma, card in tela._cartoes_forma.items() if card.property("ativa")]
    assert acesas == [FormaPagamento.PIX]
    assert tela._forma is FormaPagamento.PIX


def test_o_consumo_abre_o_seletor_de_funcionario(tela):
    assert tela._combo_funcionario.isHidden() is True

    tela._escolher_forma(FormaPagamento.CONSUMO_INTERNO)
    # `isHidden`, e não `isVisible`: a tela do teste não está na janela, e todo
    # filho de widget invisível responde "não estou visível".
    assert tela._combo_funcionario.isHidden() is False
    assert "Lucas Prado" in [
        tela._combo_funcionario.itemText(i) for i in range(tela._combo_funcionario.count())
    ]

    tela._escolher_forma(FormaPagamento.DINHEIRO)
    assert tela._combo_funcionario.isHidden() is True


def test_o_troco_e_ao_vivo_e_so_em_dinheiro(tela):
    """Só dinheiro gera troco (regra do service): mostrar troco no cartão
    prometeria o que o registro vai recusar."""
    tela._campo_valor.definir_valor(Decimal("200.00"))
    assert tela._valor_troco.text() == "R$ 68,50"

    tela._escolher_forma(FormaPagamento.DEBITO)
    assert tela._valor_troco.text() == "R$ 0,00"


# ---------------------------------------------------------------------------
# 5. O recebimento
# ---------------------------------------------------------------------------


def test_registrar_fecha_a_conta_e_avisa_a_navegacao(uow, tela, conta):
    recebidos = _recebidos(tela)

    tela._botao_registrar.click()

    assert recebidos == [conta.id]
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).status is StatusComanda.FECHADA


def test_um_unico_botao_de_registrar(tela):
    """O "Registrar e imprimir comprovante" e o "Imprimir 2ª via" saíram: o
    comprovante é obrigatório, não é escolha do operador."""
    textos = _textos(tela)

    assert tela._botao_registrar.text() == "Registrar Pagamento"
    assert "Registrar e imprimir comprovante" not in textos
    assert "Imprimir 2ª via" not in textos
    assert not hasattr(tela, "_botao_registrar_imprimir")


def test_o_parcial_mantem_a_tela_e_diz_o_que_falta(uow, tela, conta):
    recebidos = _recebidos(tela)
    tela._campo_valor.definir_valor(Decimal("100.00"))

    tela._botao_registrar.click()

    assert recebidos == []
    assert "Falta R$ 31,50" in tela._label_erro.text()
    assert tela._campo_valor.valor() == Decimal("31.50"), "o campo recarrega com o que falta"
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).status is StatusComanda.EM_CONFERENCIA


def test_o_erro_do_service_aparece_na_tela(tela, comandas, conta):
    """A conta reaberta por outra ponta não aceita pagamento — e quem diz isso
    é o service, na linha da tela."""
    comandas.reabrir(conta.id, PIN_GERENTE)

    tela._botao_registrar.click()

    assert "ainda está aberta" in tela._label_erro.text()


def test_o_consumo_pede_a_assinatura_sem_pin_e_entra_no_saldo(qapp, uow, tela, garcom, pagamentos, gerente):
    """O fluxo do consumo: funcionário escolhido, assinatura manuscrita no
    lugar do PIN, valor no saldo devedor dele e o traço gravado."""
    tela._escolher_forma(FormaPagamento.CONSUMO_INTERNO)
    indice = tela._combo_funcionario.findData(garcom.id)
    tela._combo_funcionario.setCurrentIndex(indice)

    vistos = []
    with _respondendo_a_assinatura(assinar=True, vistos=vistos):
        tela._botao_registrar.click()

    assert vistos == [ModalAssinaturaManuscrita], "nenhum cartão de PIN pode abrir"
    assert tela._label_erro.text() == ""
    assert pagamentos.calcular_saldo_devedor(garcom.id) == Decimal("131.50")
    (sessao,) = pagamentos.sessoes_de_retirada(garcom.id)
    assert sessao.traco_json is not None
    assert ler_assinatura(sessao.traco_json).tracos == TRACO_DE_TESTE


TRACO_DE_TESTE = (((20, 100), (60, 80), (100, 120), (140, 90)), ((160, 110), (200, 105)))


@contextmanager
def _respondendo_a_assinatura(*, assinar: bool, vistos: list | None = None):
    """Responde ao modal que abrir dentro do bloco: assina e confirma, ou desiste.

    O relógio tem teto (um teste que espera um diálogo que nunca vem TRAVA a
    suíte dentro do `exec()`, a lição do §9.14) e é **sempre parado no fim do
    bloco** — um `QTimer` de 0ms esquecido rouba o foco de outros diálogos.
    Um cartão de PIN que apareça é anotado e recusado: não pode existir mais.
    """
    relogio = QTimer()
    voltas = {"n": 0}

    def procurar() -> None:
        voltas["n"] += 1
        modal = QApplication.activeModalWidget()
        if modal is not None and vistos is not None:
            vistos.append(type(modal))
        if isinstance(modal, ModalAssinaturaManuscrita):
            relogio.stop()
            if not assinar:
                modal.reject()
                return
            modal.pad._tracos = [list(traco) for traco in TRACO_DE_TESTE]
            modal.pad.assinatura_alterada.emit(True)
            modal.botao_confirmar.click()
        elif isinstance(modal, PinPadDialog):
            relogio.stop()
            modal.reject()
        elif voltas["n"] > 200:
            relogio.stop()

    relogio.timeout.connect(procurar)
    relogio.start(0)
    try:
        yield
    finally:
        relogio.stop()
        relogio.deleteLater()


def test_o_consumo_sem_assinatura_nao_registra(qapp, uow, tela, garcom, conta):
    """Desistir da assinatura volta para a tela com a conta intacta."""
    tela._escolher_forma(FormaPagamento.CONSUMO_INTERNO)

    with _respondendo_a_assinatura(assinar=False):
        tela._botao_registrar.click()

    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).status is StatusComanda.EM_CONFERENCIA


def test_receber_nao_mexe_na_gaveta_alem_do_pagamento(uow, tela, conta, caixa_aberto):
    """§9.26: o recebimento não gera movimento de caixa nenhum.

    Enquanto a comissão existiu, marcar "Comissão paga" tirava o valor da
    gaveta no mesmo commit do fechamento. Sem ela, fechar a conta só grava o
    pagamento — e uma saída que reapareça aqui é dinheiro sumindo do turno sem
    ninguém ter pedido.
    """
    tela._botao_registrar.click()

    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).status is StatusComanda.FECHADA
    assert uow.movimentos.listar_por_caixa(caixa_aberto.id) == []


# ---------------------------------------------------------------------------
# 6. O desenho
# ---------------------------------------------------------------------------


@pytest.fixture(params=[False, True], ids=["escuro", "claro"])
def com_fonte_e_tema(qapp, request):
    caminho = (
        Path(gestor_comercial.__file__).resolve().parents[2]
        / "resources"
        / "fonts"
        / "ArchivoBlack-Regular.ttf"
    )
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


def test_nada_da_tela_e_espremido(qapp, com_fonte_e_tema, tela, assentar):
    """A tela do food truck tem 1366x738 úteis: nenhum rótulo nem botão pode
    ser desenhado menor do que pede."""
    janela = QWidget()
    janela.resize(1366, 738)
    layout_falso = tela.parentWidget()
    assert layout_falso is None
    tela.setParent(janela)
    janela.show()
    qapp.processEvents()

    espremidos = {}
    for peca in tela.findChildren(QWidget):
        if not isinstance(peca, (QLabel, QPushButton)) or not peca.isVisible():
            continue
        # O "R$" do campo de dinheiro não é posicionado por layout: o próprio
        # `CampoMoeda` mede a fonte e o coloca na margem do texto (§9.20), então
        # a regra de "espremido pelo layout" não se aplica a ele.
        if peca.objectName() == "campoMoedaPrefixo":
            continue
        if isinstance(peca, QLabel) and peca.wordWrap():
            if peca.height() < peca.heightForWidth(peca.width()):
                espremidos[peca.objectName()] = ("altura", peca.height(), peca.heightForWidth(peca.width()))
            continue
        if peca.width() < peca.sizeHint().width():
            espremidos[peca.objectName()] = ("largura", peca.width(), peca.sizeHint().width())
        # Altura também: foi assim que a renderização pegou os cards de forma
        # de pagamento espremidos a 20px, com o Qt deixando de desenhar o texto
        # — e a versão anterior deste teste, que só media largura, passou verde.
        if peca.height() < peca.sizeHint().height():
            espremidos[peca.objectName()] = ("altura", peca.height(), peca.sizeHint().height())

    # Fecha a janela DE VERDADE antes de sair: uma janela visível esquecida
    # continua ativa (rouba o foco do próximo diálogo) e continua repintando.
    # Medido: sem este `hide` + drenagem, o teste de foco do cartão de
    # impressora, que roda depois, passava de 0,2s para ~6 minutos e falhava.
    tela.setParent(None)
    janela.close()
    janela.deleteLater()
    # `assentar` drena o descarte adiado do Qt (§ conftest): sem ele a janela
    # continua viva — e ativa — durante o teste seguinte.
    assentar()
    assert not espremidos, f"peças espremidas (eixo, tem, pede): {espremidos}"


def test_os_tokens_da_tela_existem_nos_dois_temas():
    from gestor_comercial.ui.theme.tokens import TEMA_CLARO, TEMA_ESCURO

    familia = {chave for chave in TEMA_ESCURO if chave.startswith("pagamento_")}
    # O piso caiu de 21 para 16 no §9.26, com a saída dos dez tokens do card da
    # comissão e do avatar dele (a família foi de 30 para 20). O que este número segura é a família sumir
    # inteira por um apagamento desatento, não o tamanho dela.
    assert len(familia) > 15
    assert familia == {chave for chave in TEMA_CLARO if chave.startswith("pagamento_")}
