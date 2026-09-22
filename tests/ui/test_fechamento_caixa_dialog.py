"""O modal de fechamento do caixa: duas contagens às cegas e a gravação.

É a tela mais cara do sistema: o único momento em que a gaveta física e o banco
de dados se encontram. Os testes cobrem, nessa ordem:

1. **o teclado tem um destino só por vez, e ele é dito em voz alta**;
2. **fechamento cego** — o modal não recebe, não mostra e não calcula o
   esperado nem a diferença; não há atalho que preencha o apurado;
3. **as duas contagens chegam ao banco na ordem certa, e a diferença é
   apurada pelo service** na gravação;
4. **nada sobra na memória**, e o valor NÃO é apagado no fechamento do modal.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QWidget

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import FormaPagamento, StatusComanda
from gestor_comercial.domain.pagamento import Pagamento
from gestor_comercial.services.dinheiro import dinheiro
from gestor_comercial.ui.views.caixa_view import CaixaView
from gestor_comercial.ui.widgets.cartao_de_turno import PAPEL_FECHAMENTO
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.fechamento_caixa_dialog import (
    CONTAGENS,
    FechamentoCaixaDialog,
)

ALTURA_UTIL_PX = 728

# O que o service apura para o turno de `turno_com_venda`: R$ 970,00 na gaveta
# e R$ 1.600,00 na maquininha. O modal nunca vê estes números — os testes usam
# para conferir a diferença que o service grava.
ESPERADO_DINHEIRO = Decimal("970.00")
ESPERADO_MAQUININHA = Decimal("1600.00")


@pytest.fixture
def abrir(qapp):
    """Monta o modal sem `exec()` — e o descarta no fim do teste."""
    criados: list[FechamentoCaixaDialog] = []

    def _abrir(pai=None):
        modal = FechamentoCaixaDialog(pai)
        criados.append(modal)
        return modal

    yield _abrir
    for modal in criados:
        modal.deleteLater()


@pytest.fixture
def turno_com_venda(uow, caixas_service, gerente):
    """Um turno aberto com R$ 870 em dinheiro e R$ 1.600 na maquininha.

    Com o fundo de troco de R$ 100, o saldo esperado da gaveta fecha em
    R$ 970,00 — os mesmos números do mockup. Os pagamentos entram pelo
    repository porque o alvo aqui é o fechamento, não o `PagamentoService`.
    """
    caixa = caixas_service.abrir(Decimal("100.00"))
    comanda = uow.comandas.salvar(
        Comanda(
            status=StatusComanda.FECHADA,
            aberta_em=datetime(2026, 9, 9, 19, 0),
            usuario_id=gerente.id,
            caixa_id=caixa.id,
        )
    )
    for forma, valor in (
        (FormaPagamento.DINHEIRO, "870.00"),
        (FormaPagamento.DEBITO, "1600.00"),
    ):
        uow.pagamentos.salvar(
            Pagamento(
                forma=forma,
                valor=dinheiro(valor),
                registrado_em=datetime(2026, 9, 9, 20, 0),
                comanda_id=comanda.id,
            )
        )
    return caixa


@pytest.fixture
def caixa_na_tela(qapp, caixas_service, impressao, turno_com_venda):
    """A tela de Caixa com o turno do mockup aberto."""
    view = CaixaView(caixas_service, impressao)
    yield view
    view.deleteLater()


def _tecla(modal: QDialog, tecla: Qt.Key, texto: str = "") -> None:
    modal.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier, texto)
    )


def _digitar(modal: QDialog, digitos: str) -> None:
    for digito in digitos:
        _tecla(modal, Qt.Key(Qt.Key.Key_0 + int(digito)), digito)


def _tocar(modal: FechamentoCaixaDialog, indice: int) -> None:
    """Toca na linha de conferência pelo caminho do dedo: um clique de verdade."""
    linha = modal._cartoes[indice]
    linha.mousePressEvent(
        QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(10.0, 10.0),
            QPointF(10.0, 10.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )


# ---------------------------------------------------------------------------
# O cartão
# ---------------------------------------------------------------------------


def test_o_cartao_veste_o_papel_de_fechamento(abrir):
    modal = abrir()

    assert modal.windowTitle() == "Fechar caixa"
    assert modal._botao_confirmar.text() == "Confirmar fechamento"
    assert modal._botao_confirmar.property("papel") == PAPEL_FECHAMENTO


def test_o_modal_nao_mostra_nenhum_valor_esperado(abrir):
    """Fechamento cego: o único dinheiro na tela é o que o operador digitou.
    Com as contagens zeradas, todo texto com "R$" tem que ser "R$ 0,00"."""
    modal = abrir()

    textos = [label.text() for label in modal.findChildren(QLabel)]

    assert not any("Esperado" in texto for texto in textos)
    assert not any("diferença" in texto.lower() for texto in textos)
    assert {texto for texto in textos if "R$" in texto} == {"R$ 0,00"}


def test_nao_existe_atalho_para_preencher_o_apurado(abrir):
    modal = abrir()

    textos = [botao.text().upper() for botao in modal.findChildren(QPushButton)]

    assert not any("PREENCHER" in texto for texto in textos)
    assert not hasattr(modal, "_botao_preencher")


def test_o_modal_nao_tem_esperado_nem_previa_de_diferenca(abrir):
    """Não basta esconder: se o número estivesse no objeto, bastaria um
    tooltip ou um log para ele vazar. O modal simplesmente não o recebe."""
    modal = abrir()

    assert not hasattr(modal, "_esperados")
    assert not hasattr(modal, "diferenca")


def test_as_duas_contagens_comecam_zeradas(abrir):
    """Zerado e não pré-preenchido, de propósito: pré-preencher com o esperado
    transformaria a conferência num "Enter" e a gaveta nunca seria contada."""
    modal = abrir()

    assert [label.text() for label in modal._labels_valor] == ["R$ 0,00", "R$ 0,00"]


# ---------------------------------------------------------------------------
# O destino do teclado
# ---------------------------------------------------------------------------


def test_o_teclado_comeca_apontado_para_o_dinheiro(abrir):
    modal = abrir()

    assert modal._rotulo_teclado.text() == CONTAGENS[0].rotulo_teclado
    assert modal._cartoes[0].property("ativa") is True
    assert modal._cartoes[1].property("ativa") is False


def test_tocar_na_linha_aponta_o_teclado_para_ela(abrir):
    """O clique de verdade, pelo `mousePressEvent` da linha: é ele que faz o
    dedo no cartão trocar o destino dos dígitos."""
    modal = abrir()

    _tocar(modal, 1)

    assert modal._rotulo_teclado.text() == "DIGITANDO MAQUININHAS"
    assert modal._cartoes[1].property("ativa") is True
    assert modal._cartoes[0].property("ativa") is False


def test_o_digito_vai_so_para_a_contagem_ativa(abrir):
    """O defeito que este teste segura: sem destino único, digitar o extrato da
    maquininha somaria na contagem da gaveta e o turno fecharia com duas
    diferenças que ninguém consegue explicar."""
    modal = abrir()

    _digitar(modal, "97000")
    _tocar(modal, 1)
    _digitar(modal, "160000")

    assert modal.resultado().dinheiro == Decimal("970.00")
    assert modal.resultado().maquininha == Decimal("1600.00")


def test_o_apagar_tambem_respeita_a_contagem_ativa(abrir):
    modal = abrir()
    _digitar(modal, "97000")
    _tocar(modal, 1)
    _digitar(modal, "160000")

    _tecla(modal, Qt.Key.Key_Backspace)

    assert modal.resultado().dinheiro == Decimal("970.00")
    assert modal.resultado().maquininha == Decimal("160.00")


def test_tab_percorre_dinheiro_maquininha_observacao_e_volta(qapp, abrir):
    """Os três destinos que o briefing pediu, em ordem. O diálogo tem
    `FocusPolicy.NoFocus` (como todo modal em cartão daqui), então quem move o
    foco é o `keyPressEvent`, e quem o devolve do campo é o `eventFilter`."""
    modal = abrir()
    modal.show()
    qapp.processEvents()

    _tecla(modal, Qt.Key.Key_Tab)
    assert modal._rotulo_teclado.text() == "DIGITANDO MAQUININHAS"

    _tecla(modal, Qt.Key.Key_Tab)
    assert modal._campo_observacao.hasFocus() is True

    modal.eventFilter(
        modal._campo_observacao,
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier),
    )
    assert modal._rotulo_teclado.text() == "DIGITANDO DINHEIRO"

    modal.reject()


def test_com_o_cursor_na_observacao_nenhum_cartao_fica_aceso(qapp, abrir):
    """Ali o dígito é texto de observação — e é assim que tem que ser. O anel
    apagado é o único sinal disso."""
    modal = abrir()
    modal.show()
    qapp.processEvents()

    modal._campo_observacao.setFocus(Qt.FocusReason.TabFocusReason)
    modal._pintar()

    assert [cartao.property("ativa") for cartao in modal._cartoes] == [False, False]
    modal.reject()


def test_tocar_num_cartao_traz_o_foco_de_volta_do_campo(qapp, abrir):
    """Se o operador estava na observação e tocou em "Dinheiro", o dígito
    seguinte tem que ir para a contagem — não continuar virando texto."""
    modal = abrir()
    modal.show()
    qapp.processEvents()
    modal._campo_observacao.setFocus(Qt.FocusReason.TabFocusReason)

    _tocar(modal, 0)
    _digitar(modal, "5")

    assert modal.resultado().dinheiro == Decimal("0.05")
    assert modal._campo_observacao.text() == ""
    modal.reject()


# ---------------------------------------------------------------------------
# Teclado e saída
# ---------------------------------------------------------------------------


def test_enter_confirma_o_fechamento(qapp, abrir):
    modal = abrir()
    _digitar(modal, "97000")

    QTimer.singleShot(0, lambda: _tecla(modal, Qt.Key.Key_Return))

    assert modal.exec() == QDialog.DialogCode.Accepted
    assert modal.resultado().dinheiro == Decimal("970.00")


def test_esc_fecha_sem_encerrar_o_turno(qapp, abrir):
    modal = abrir()

    QTimer.singleShot(0, lambda: _tecla(modal, Qt.Key.Key_Escape))

    assert modal.exec() == QDialog.DialogCode.Rejected


def test_a_observacao_sai_sem_espaco_sobrando(abrir):
    modal = abrir()

    modal._campo_observacao.setText("  conferido com o gerente  ")

    assert modal.resultado().observacao == "conferido com o gerente"


def test_observacao_vazia_vira_none(abrir):
    modal = abrir()

    modal._campo_observacao.setText("   ")

    assert modal.resultado().observacao is None


# ---------------------------------------------------------------------------
# O caminho real — a view, o service e o banco
# ---------------------------------------------------------------------------


def _fechar_pela_tela(qapp, view, contado_dinheiro, contado_maquininha, observacao=None):
    """Aperta "Fechar caixa" na tela e opera o modal que abrir, de verdade."""

    def operar() -> None:
        modal = view.findChildren(FechamentoCaixaDialog)[0]
        _digitar(modal, contado_dinheiro)
        _tocar(modal, 1)
        _digitar(modal, contado_maquininha)
        if observacao is not None:
            modal._campo_observacao.setText(observacao)
        modal.accept()

    QTimer.singleShot(0, operar)
    view._botao_fechar.click()
    qapp.processEvents()


def test_a_tela_grava_as_duas_contagens_e_a_observacao(qapp, caixa_na_tela, caixas_service):
    """Cada contagem no seu campo. Trocar as duas produziria duas diferenças
    simétricas que se cancelam no total — e o erro não apareceria em lugar
    nenhum do relatório."""
    caixa_id = caixa_na_tela._caixa_id

    _fechar_pela_tela(qapp, caixa_na_tela, "97000", "160000", "conferido com o gerente")

    caixa = caixas_service.buscar(caixa_id)
    assert caixa.valor_contado_dinheiro == Decimal("970.00")
    assert caixa.valor_contado_maquininha == Decimal("1600.00")
    assert caixa.observacao_fechamento == "conferido com o gerente"


def test_a_diferenca_e_apurada_pelo_service_na_gravacao(qapp, caixa_na_tela, caixas_service):
    """O modal só leva o contado; quem confronta com o apurado é o service.
    Contagens que dão quebra nas duas pontas provam que cada diferença é
    gravada no seu campo — e não se cancelam em silêncio."""
    caixa_id = caixa_na_tela._caixa_id

    _fechar_pela_tela(qapp, caixa_na_tela, "92000", "165000")

    resumo = caixas_service.resumo(caixa_id)
    assert resumo.diferenca_dinheiro == Decimal("920.00") - ESPERADO_DINHEIRO
    assert resumo.diferenca_maquininha == Decimal("1650.00") - ESPERADO_MAQUININHA
    assert resumo.diferenca_total == Decimal("0.00")


def test_cancelar_no_modal_deixa_o_turno_aberto(qapp, caixa_na_tela, caixas_service):
    def desistir() -> None:
        modal = caixa_na_tela.findChildren(FechamentoCaixaDialog)[0]
        _digitar(modal, "97000")
        modal.reject()

    QTimer.singleShot(0, desistir)
    caixa_na_tela._botao_fechar.click()
    qapp.processEvents()

    assert caixas_service.buscar_aberto().id == caixa_na_tela._caixa_id


def test_o_erro_do_service_continua_aparecendo_na_tela_de_tras(
    qapp, caixa_na_tela, caixas_service, uow, gerente, produto
):
    """Comanda em aberto continua barrando o fechamento, e a mensagem continua
    saindo na linha vermelha da tela — o modal não passou a decidir nada."""
    from gestor_comercial.domain.item_comanda import ItemComanda

    comanda = uow.comandas.salvar(
        Comanda(
            status=StatusComanda.ABERTA,
            aberta_em=datetime(2026, 9, 9, 21, 0),
            usuario_id=gerente.id,
            caixa_id=caixa_na_tela._caixa_id,
        )
    )
    uow.itens.salvar(
        ItemComanda(
            quantidade=1,
            preco_unit_congelado=produto.preco,
            comanda_id=comanda.id,
            produto_id=produto.id,
        )
    )

    _fechar_pela_tela(qapp, caixa_na_tela, "97000", "160000")

    assert "comanda aberta" in caixa_na_tela._label_erro.text()
    assert caixas_service.buscar_aberto().id == comanda.caixa_id


# ---------------------------------------------------------------------------
# Ciclo de vida — o RNF do Celeron
# ---------------------------------------------------------------------------


def test_as_contagens_sobrevivem_ao_fechamento_para_a_view_ler(abrir):
    """`resultado()` é lido DEPOIS do `exec()` (§3.2). Zerar em `done()` faria
    todo turno ser gravado como R$ 0,00 contados, com uma quebra do tamanho do
    faturamento da noite."""
    modal = abrir()
    _digitar(modal, "97000")
    _tocar(modal, 1)
    _digitar(modal, "160000")

    modal.accept()

    assert modal.resultado().dinheiro == Decimal("970.00")
    assert modal.resultado().maquininha == Decimal("1600.00")


def test_fechar_solta_as_tabelas_de_widget(qapp, abrir):
    modal = abrir()
    assert modal._cartoes and modal._labels_valor and modal._teclado.teclas

    modal.reject()

    assert modal._cartoes == []
    assert modal._labels_valor == []
    assert modal._teclado.teclas == {}


def test_fechar_remove_o_filtro_do_campo_de_observacao(qapp, abrir):
    modal = abrir()
    removidos: list[object] = []
    modal._campo_observacao.removeEventFilter = removidos.append

    modal.reject()

    assert removidos == [modal]


def test_fechar_solta_o_escurecedor_da_janela(qapp, assentar):
    pai = QWidget()
    pai.show()

    for _ in range(10):
        modal = FechamentoCaixaDialog(pai)
        modal.show()
        qapp.processEvents()
        modal.reject()
        modal.deleteLater()
    assentar()

    assert pai.window().findChildren(Backdrop) == []


def test_trinta_aberturas_nao_deixam_nada_preso_a_view(qapp, assentar, caixa_na_tela):
    for _ in range(30):
        modal = FechamentoCaixaDialog(caixa_na_tela)
        QTimer.singleShot(0, modal.reject)
        modal.exec()
        modal.deleteLater()
        del modal
    assentar()

    assert caixa_na_tela.findChildren(FechamentoCaixaDialog) == []


def test_o_cartao_cabe_na_tela_do_food_truck(qapp, abrir):
    """1366x768 é a máquina do balcão, e o Windows come uma barra de tarefas.

    A suíte roda `offscreen`, que sobe sem banco de fontes e mede TUDO maior que
    a máquina real: o teste é pessimista de propósito.
    """
    modal = abrir()
    modal.show()
    qapp.processEvents()
    modal.adjustSize()
    altura = modal.height()
    modal.reject()

    assert altura <= ALTURA_UTIL_PX, (
        f"o cartão de fechamento pediu {altura}px de altura — num monitor de 768px "
        "ele sairia da tela pela borda de baixo"
    )
