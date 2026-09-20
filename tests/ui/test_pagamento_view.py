"""A tela "Receber Pagamento". §9.25.

Pedido do Vitor, com o mockup: o último diálogo de fábrica do fluxo de venda
(combo de forma, campo de texto, resumo em três linhas) virou tela, com o
consumo à esquerda, as formas em cards, o troco ao vivo e o card da comissão do
garçom.

O que esta suíte cobra:

1. **o mockup** — cabeçalho, itens, subtotal, serviço, total e "por pessoa";
2. **dividir por** — só mostra quanto dá por pessoa, sem mexer no que é lançado;
3. **as formas** — o card escolhido acende, "Consumo" abre o seletor de
   funcionário, e só dinheiro mostra troco;
4. **o recebimento** — fecha a conta, avisa no parcial e leva a comissão junto;
5. **a comissão** — abre como "não paga", e o clique em "Comissão paga" é o que
   tira o dinheiro da gaveta;
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
from gestor_comercial.domain.enums import FormaPagamento, StatusComanda, TipoMovimento
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.comanda_service import TAXA_SERVICO_PADRAO
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.views.pagamento_view import COMISSAO_PAGA_PADRAO, PagamentoView
from gestor_comercial.ui.widgets.pin_pad_dialog import PinPadDialog
from tests.conftest import PIN_GERENTE


@pytest.fixture
def garcom(funcionarios, gerente):
    return funcionarios.criar("Lucas Prado", "Garçom")


@pytest.fixture
def conta(uow, comandas, gerente, caixa_aberto, categoria, garcom):
    """A mesa 12 do mockup, em conferência: R$ 131,50 + 10% = R$ 144,65."""
    lanche = uow.produtos.salvar(
        Produto(nome="Artesanal", preco=Decimal("65.75"), categoria_id=categoria.id)
    )
    mesa = uow.mesas.salvar(Mesa(numero=12))
    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.lancar_item(comanda.id, lanche.id, 2)
    comandas.definir_atendente(comanda.id, garcom.id)
    comandas.fechar_para_conferencia(comanda.id, TAXA_SERVICO_PADRAO)
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
    for frase in ("2×", "Artesanal", "Subtotal", "Serviço 10%", "Total da conta", "TROCO"):
        assert frase in textos, frase
    assert tela._valor_subtotal.text() == "R$ 131,50"
    assert tela._valor_taxa.text() == "R$ 13,15"
    assert tela._valor_total.text() == "R$ 144,65"
    assert tela._campo_valor.valor() == Decimal("144.65"), "o campo já vem com o que falta"
    assert tela._valor_troco.text() == "R$ 0,00"


def test_a_conta_sem_taxa_nao_mostra_a_linha_de_servico(qapp, auth, comandas, pagamentos, impressao, uow, gerente, caixa_aberto, categoria):
    auth.loja_config.definir_aceita_taxa_servico(False)
    produto = uow.produtos.salvar(Produto(nome="Suco", preco=Decimal("10.00"), categoria_id=categoria.id))
    comanda = comandas.abrir_balcao()
    comandas.lancar_item(comanda.id, produto.id, 1)
    comandas.fechar_para_conferencia(comanda.id, None)

    view = PagamentoView(pagamentos, impressao)
    try:
        view.carregar(comanda.id)

        assert view._titulo.text() == "Receber Pagamento · Balcão"
        assert view._titulo_consumo.text() == "Consumo da comanda"
        assert view._valor_taxa.isHidden() is True
        assert view._valor_total.text() == "R$ 10,00"
        assert view._cartao_comissao.isHidden() is True, "sem taxa não há comissão"
    finally:
        view.deleteLater()


# ---------------------------------------------------------------------------
# 2. Dividir por
# ---------------------------------------------------------------------------


def test_dividir_por_so_mostra_o_valor_por_pessoa(tela):
    """Decisão do Vitor: o pagamento continua sendo lançado por valor recebido."""
    tela._dividir_por(2)

    assert tela._rotulo_por_pessoa.text() == "Por pessoa (2)"
    assert tela._valor_por_pessoa.text() == "R$ 72,33"
    assert tela._campo_valor.valor() == Decimal("144.65"), "o valor a receber não muda"
    assert [p.text() for p in tela._pilulas if p.property("ativa")] == ["2"]


# ---------------------------------------------------------------------------
# 3. As formas
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
    assert tela._valor_troco.text() == "R$ 55,35"

    tela._escolher_forma(FormaPagamento.DEBITO)
    assert tela._valor_troco.text() == "R$ 0,00"


# ---------------------------------------------------------------------------
# 4. O recebimento
# ---------------------------------------------------------------------------


def test_registrar_fecha_a_conta_e_avisa_a_navegacao(uow, tela, conta):
    recebidos = _recebidos(tela)

    tela._botao_registrar.click()

    assert recebidos == [conta.id]
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).status is StatusComanda.FECHADA


def test_o_parcial_mantem_a_tela_e_diz_o_que_falta(uow, tela, conta):
    recebidos = _recebidos(tela)
    tela._campo_valor.definir_valor(Decimal("100.00"))

    tela._botao_registrar.click()

    assert recebidos == []
    assert "Falta R$ 44,65" in tela._label_erro.text()
    assert tela._campo_valor.valor() == Decimal("44.65"), "o campo recarrega com o que falta"
    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).status is StatusComanda.EM_CONFERENCIA


def test_o_erro_do_service_aparece_na_tela(tela, comandas, conta):
    """A conta reaberta por outra ponta não aceita pagamento — e quem diz isso
    é o service, na linha da tela."""
    comandas.reabrir(conta.id, PIN_GERENTE)

    tela._botao_registrar.click()

    assert "ainda está aberta" in tela._label_erro.text()


def test_o_consumo_pede_o_pin_e_entra_no_saldo_do_funcionario(qapp, uow, tela, garcom, pagamentos, gerente):
    """O fluxo restrito: PIN do gerente, funcionário escolhido, valor no saldo
    devedor dele — e nada disso entra no dinheiro do caixa."""
    tela._escolher_forma(FormaPagamento.CONSUMO_INTERNO)
    indice = tela._combo_funcionario.findData(garcom.id)
    tela._combo_funcionario.setCurrentIndex(indice)

    with _respondendo_ao_pin(PIN_GERENTE):
        tela._botao_registrar.click()

    assert tela._label_erro.text() == ""
    assert pagamentos.calcular_saldo_devedor(garcom.id) == Decimal("144.65")


@contextmanager
def _respondendo_ao_pin(pin: str | None):
    """Responde ao cartão de PIN que abrir dentro do bloco.

    `pin` de verdade digita e confirma; `None` desiste pelo ✕. O relógio tem
    teto (um teste que espera um diálogo que nunca vem TRAVA a suíte dentro do
    `exec()`, a lição do §9.14) e é **sempre parado no fim do bloco**: um
    `QTimer` de 0ms esquecido continua disparando pelo resto da sessão, rouba o
    foco de outros diálogos e queima CPU — foi exatamente o que fez a suíte de
    UI ficar lenta e o teste de foco do cartão de impressora piscar.
    """
    relogio = QTimer()
    voltas = {"n": 0}

    def procurar() -> None:
        voltas["n"] += 1
        modal = QApplication.activeModalWidget()
        if isinstance(modal, PinPadDialog):
            relogio.stop()
            if pin is None:
                modal.reject()
            else:
                modal._pin = pin
                modal._confirmar()
        elif voltas["n"] > 200:
            relogio.stop()

    relogio.timeout.connect(procurar)
    relogio.start(0)
    try:
        yield
    finally:
        relogio.stop()
        relogio.deleteLater()


def test_o_consumo_sem_pin_nao_registra(qapp, uow, tela, garcom, conta):
    """Desistir do PIN volta para a tela com a conta intacta."""
    tela._escolher_forma(FormaPagamento.CONSUMO_INTERNO)

    with _respondendo_ao_pin(None):
        tela._botao_registrar.click()

    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).status is StatusComanda.EM_CONFERENCIA


# ---------------------------------------------------------------------------
# 5. A comissão
# ---------------------------------------------------------------------------


def test_a_comissao_abre_como_nao_paga(tela, garcom):
    textos = _textos(tela._cartao_comissao)

    assert "Comissão de Lucas Prado" in textos
    assert "Referente ao serviço · R$ 13,15" in textos
    assert tela._cartao_comissao.botao_nao_paga.property("ativa") is True
    assert tela._cartao_comissao.botao_paga.property("ativa") is False
    assert tela._comissao_paga is COMISSAO_PAGA_PADRAO is False


def test_cada_conta_comeca_do_padrao_de_novo(tela, conta):
    """Sem o reset, a comissão marcada como paga numa mesa seguiria marcada na
    próxima que o operador abrisse — e o dinheiro sairia da gaveta sozinho."""
    tela._cartao_comissao.botao_paga.click()
    assert tela._comissao_paga is True

    tela.carregar(conta.id)

    assert tela._comissao_paga is COMISSAO_PAGA_PADRAO is False
    assert tela._cartao_comissao.botao_nao_paga.property("ativa") is True


def test_marcar_paga_tira_o_dinheiro_da_gaveta(uow, tela, conta, caixa_aberto):
    tela._cartao_comissao.botao_paga.click()
    assert tela._cartao_comissao.botao_paga.property("ativa") is True

    tela._botao_registrar.click()

    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).comissao_paga is True
    movimentos = [
        m for m in uow.movimentos.listar_por_caixa(caixa_aberto.id) if m.tipo is TipoMovimento.COMISSAO
    ]
    assert [m.valor for m in movimentos] == [Decimal("13.15")]


def test_nao_paga_deixa_o_dinheiro_na_gaveta_e_a_conta_na_lista(uow, tela, conta, pagamentos, caixa_aberto):
    tela._cartao_comissao.botao_paga.click()
    tela._cartao_comissao.botao_nao_paga.click()

    tela._botao_registrar.click()

    uow.session.rollback()
    assert uow.comandas.buscar_por_id(conta.id).comissao_paga is False
    assert [p.nome for p in pagamentos.listar_comissoes_pendentes()] == ["Lucas Prado"]
    assert [m for m in uow.movimentos.listar_por_caixa(caixa_aberto.id) if m.tipo is TipoMovimento.COMISSAO] == []


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
    assert len(familia) > 20
    assert familia == {chave for chave in TEMA_CLARO if chave.startswith("pagamento_")}
