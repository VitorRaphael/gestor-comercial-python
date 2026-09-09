"""O modal de abertura do caixa: visor, pílulas, contexto, teclado e limpeza.

Esta é a tela onde o **fundo de troco** é declarado — o número contra o qual a
gaveta vai ser conferida no fim da noite. Declarar 100 e ter posto 150 vira uma
sobra inexplicável no fechamento; o contrário vira uma falta. Os testes cobrem,
nessa ordem:

1. **o visor conta centavos, não texto** — o ganho do §9.7, herdado do §9.6:
   nunca mais "valor inválido, informe um valor em reais";
2. **as pílulas DEFINEM, e não somam** — uma pílula que diz "R$ 100" e produz
   R$ 150 mente para quem apertou;
3. **o valor que sai é o valor que a view grava** — com a `CaixaView` de
   verdade, o service de verdade e o banco de verdade, porque a promessa do
   §9.7 é "nenhuma regra financeira mudou" e essa promessa se prova gravando;
4. **a observação grava de verdade** — campo que o operador preenche e o
   sistema descarta é pior que campo nenhum;
5. **o teclado do balcão faz o mesmo que o dedo**;
6. **nada sobra na memória** — e, o oposto: o valor digitado NÃO pode ser
   apagado no fechamento do modal, senão toda abertura vira R$ 0,00.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QWidget

from gestor_comercial.services.dinheiro import LIMITE
from gestor_comercial.ui.views.caixa_view import CaixaView
from gestor_comercial.ui.widgets.abertura_caixa_dialog import (
    ATALHOS_EM_REAIS,
    AberturaCaixaDialog,
)
from gestor_comercial.ui.widgets.cartao_de_turno import PAPEL_ABERTURA
from gestor_comercial.ui.widgets.cartao_modal import Backdrop

ALTURA_UTIL_PX = 728


@pytest.fixture
def abrir(qapp):
    """Monta o modal sem `exec()` — e o descarta no fim do teste."""
    criados: list[AberturaCaixaDialog] = []

    def _abrir(turno="Turno da Noite", operador="Vitor Raphael", pai=None):
        modal = AberturaCaixaDialog(turno, operador, pai)
        criados.append(modal)
        return modal

    yield _abrir
    for modal in criados:
        modal.deleteLater()


@pytest.fixture
def caixa_fechado_na_tela(qapp, caixas_service, impressao, gerente):
    """A tela de Caixa sem turno aberto — o estado em que o botão "Abrir caixa" vive."""
    view = CaixaView(caixas_service, impressao)
    yield view
    view.deleteLater()


def _tecla(modal: QDialog, tecla: Qt.Key, texto: str = "") -> None:
    """Manda a tecla pelo mesmo caminho do teclado físico: o `keyPressEvent`."""
    modal.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier, texto)
    )


def _digitar(modal: QDialog, digitos: str) -> None:
    for digito in digitos:
        _tecla(modal, Qt.Key(Qt.Key.Key_0 + int(digito)), digito)


def _clicar(modal: AberturaCaixaDialog, rotulo: str) -> None:
    """Clica numa tecla do numpad como o dedo clica — pelo sinal, não pelo estado."""
    modal._teclado.teclas[rotulo].click()


# ---------------------------------------------------------------------------
# O cartão
# ---------------------------------------------------------------------------


def test_o_cartao_veste_o_papel_de_abertura(abrir):
    """`papel` é a chave que o QSS lê, e ela chega a exatamente dois widgets: o
    badge do cabeçalho e o botão que grava. Sem ela, os dois saem sem cor —
    abrir o caixa ficaria com a mesma cara de fechar."""
    modal = abrir()

    assert modal.windowTitle() == "Abrir caixa"
    assert modal._botao_confirmar.text() == "Abrir caixa"
    assert modal._botao_confirmar.property("papel") == PAPEL_ABERTURA


def test_o_contexto_diz_qual_turno_e_quem_responde(abrir):
    """Abertura exige gerente e o fundo declarado aqui é conferido no fim da
    noite: quem está com o terminal na mão precisa ver o próprio nome antes de
    declarar o valor."""
    modal = abrir(turno="Turno da Tarde", operador="Vitor Raphael")

    assert modal._label_turno.text() == "Turno da Tarde"
    assert "Vitor Raphael" in modal._label_operador.text()
    assert "fundo de troco" in modal._label_operador.text()


def test_sem_ninguem_logado_o_contexto_mostra_travessao(abrir):
    """A view lê `usuario_logado` (que pode ser `None`) e não `usuario_atual()`
    (que levantaria): quem barra a ação sem login é o service, na hora de
    gravar — o rótulo da tela não pode impedir o modal de abrir."""
    assert "Operador — ·" in abrir(operador=None)._label_operador.text()
    assert "Operador — ·" in abrir(operador="   ")._label_operador.text()


# ---------------------------------------------------------------------------
# O visor
# ---------------------------------------------------------------------------


def test_o_visor_comeca_zerado(abrir):
    assert abrir()._label_valor.text() == "R$ 0,00"


def test_o_visor_conta_centavos_pela_direita(abrir):
    modal = abrir()

    _digitar(modal, "10000")

    assert modal._label_valor.text() == "R$ 100,00"
    assert modal.resultado().valor == Decimal("100.00")


def test_o_teto_do_visor_e_o_teto_do_banco(abrir):
    modal = abrir()

    _digitar(modal, "9" * 10)
    no_teto = modal.resultado().valor
    _digitar(modal, "9")

    assert no_teto == LIMITE
    assert modal.resultado().valor == no_teto


@pytest.mark.parametrize("reais", ATALHOS_EM_REAIS)
def test_a_pilula_define_o_valor_em_vez_de_somar(abrir, reais):
    """O teste que separa esta tela do modal de movimentação: lá as pílulas
    dizem `+50` e somam; aqui dizem `R$ 50` e trocam. Fundo de troco é uma
    escolha entre valores redondos, não uma apuração."""
    modal = abrir()
    _digitar(modal, "550")  # R$ 5,50 já no visor

    modal._atalhos[reais].click()

    assert modal.resultado().valor == Decimal(reais)


def test_uma_pilula_substitui_a_outra(abrir):
    """Errar a pílula é normal com o dedo. Se elas somassem, corrigir exigiria
    apagar dígito por dígito o que a soma produziu."""
    modal = abrir()

    modal._atalhos[50].click()
    modal._atalhos[200].click()

    assert modal.resultado().valor == Decimal("200.00")


def test_a_pilula_diz_no_rotulo_o_valor_que_produz(abrir):
    modal = abrir()

    for reais in ATALHOS_EM_REAIS:
        assert modal._atalhos[reais].text() == f"R$ {reais}"


def test_zero_e_valor_legitimo_e_o_botao_nasce_aceso(abrir):
    """Diferente do modal de movimentação, onde o service recusa zero e o botão
    nasce desligado: `abrir` só recusa valor NEGATIVO, e existe turno que começa
    sem fundo de troco na gaveta. Desligar o botão aqui esconderia um caminho
    legítimo."""
    modal = abrir()

    assert modal._botao_confirmar.isEnabled() is True
    assert modal.resultado().valor == Decimal("0.00")


# ---------------------------------------------------------------------------
# Observação
# ---------------------------------------------------------------------------


def test_a_observacao_sai_sem_espaco_sobrando(abrir):
    modal = abrir()

    modal._campo_observacao.setText("  fundo recebido do cofre  ")

    assert modal.resultado().observacao == "fundo recebido do cofre"


def test_observacao_vazia_vira_none(abrir):
    """Gravar `""` faria o relatório impresso ganhar uma linha "Obs. abertura:"
    em branco, que parece anotação perdida em vez de campo não preenchido."""
    modal = abrir()

    modal._campo_observacao.setText("   ")

    assert modal.resultado().observacao is None


# ---------------------------------------------------------------------------
# Teclado
# ---------------------------------------------------------------------------


def test_enter_confirma_a_abertura(qapp, abrir):
    modal = abrir()
    _digitar(modal, "10000")

    QTimer.singleShot(0, lambda: _tecla(modal, Qt.Key.Key_Return))

    assert modal.exec() == QDialog.DialogCode.Accepted
    assert modal.resultado().valor == Decimal("100.00")


def test_esc_fecha_sem_abrir(qapp, abrir):
    modal = abrir()
    _digitar(modal, "10000")

    QTimer.singleShot(0, lambda: _tecla(modal, Qt.Key.Key_Escape))

    assert modal.exec() == QDialog.DialogCode.Rejected


def test_backspace_do_teclado_fisico_apaga_no_visor(abrir):
    """O balcão tem teclado numérico USB, e ele tem que fazer o mesmo que o dedo
    na tela — inclusive apagar."""
    modal = abrir()
    _digitar(modal, "10000")

    _tecla(modal, Qt.Key.Key_Backspace)

    assert modal.resultado().valor == Decimal("10.00")


def test_o_numpad_da_tela_e_o_teclado_fisico_chegam_no_mesmo_visor(abrir):
    modal = abrir()

    _clicar(modal, "5")
    _tecla(modal, Qt.Key.Key_0, "0")
    _clicar(modal, "00")

    assert modal.resultado().valor == Decimal("50.00")


def test_tab_leva_o_foco_para_a_observacao_e_o_traz_de_volta(qapp, abrir):
    """O diálogo tem `FocusPolicy.NoFocus` (como todo modal em cartão daqui),
    então a navegação natural do Qt pularia o cartão e o `Tab` não faria nada:
    quem manda o foco para o campo é o `keyPressEvent`, e quem o traz de volta é
    o `eventFilter` instalado no campo."""
    modal = abrir()
    modal.show()
    qapp.processEvents()

    _tecla(modal, Qt.Key.Key_Tab)
    assert modal._campo_observacao.hasFocus() is True

    modal.eventFilter(
        modal._campo_observacao,
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier),
    )
    assert modal.hasFocus() is True

    modal.reject()


def test_o_anel_do_visor_diz_para_onde_o_digito_vai(qapp, abrir):
    """Com o cursor na observação, dígito é texto de observação — e é assim que
    tem que ser. O anel é o único sinal disso: sem ele, o operador só descobre a
    diferença depois de ler o que saiu."""
    modal = abrir()
    modal.show()
    qapp.processEvents()
    assert modal._visor.property("ativa") is True

    _tecla(modal, Qt.Key.Key_Tab)

    assert modal._visor.property("ativa") is False
    modal.reject()


def test_o_dialogo_ignora_digito_unicode_que_nao_e_algarismo(abrir):
    """`"²".isdigit()` é `True` em Python, e `int("²")` estoura."""
    modal = abrir()

    _tecla(modal, Qt.Key.Key_unknown, "²")

    assert modal.resultado().valor == Decimal("0.00")


# ---------------------------------------------------------------------------
# O caminho real — a view, o service e o banco
# ---------------------------------------------------------------------------


def _abrir_pela_tela(qapp, view, digitos, observacao=None, confirmar=True):
    """Aperta "Abrir caixa" na tela e opera o modal que abrir, de verdade.

    É a única forma de provar a promessa do §9.7 ("nenhuma regra financeira
    mudou"): o `executar_modal` roda, o `exec()` roda, `abrir` grava e o banco
    responde. Um dublê do diálogo provaria só que o teste sabe chamar o service.
    """

    def operar() -> None:
        modal = view.findChildren(AberturaCaixaDialog)[0]
        _digitar(modal, digitos)
        if observacao is not None:
            modal._campo_observacao.setText(observacao)
        modal.accept() if confirmar else modal.reject()

    QTimer.singleShot(0, operar)
    view._botao_abrir.click()
    qapp.processEvents()


def test_a_tela_abre_o_caixa_com_o_valor_do_numpad(
    qapp, caixa_fechado_na_tela, caixas_service
):
    _abrir_pela_tela(qapp, caixa_fechado_na_tela, "15000")

    caixa = caixas_service.buscar_aberto()

    assert caixa.valor_abertura == Decimal("150.00")
    assert caixa_fechado_na_tela._label_erro.text() == ""


def test_a_observacao_da_abertura_e_gravada(qapp, caixa_fechado_na_tela, caixas_service):
    """O campo do mockup grava de verdade: sem a coluna `observacao_abertura`
    (migração `d9b4c7e21f30`) ele seria uma caixa de texto que o sistema joga
    fora, e ninguém descobriria até procurar a anotação."""
    _abrir_pela_tela(qapp, caixa_fechado_na_tela, "10000", "fundo recebido do cofre")

    assert caixas_service.buscar_aberto().observacao_abertura == "fundo recebido do cofre"


def test_abrir_sem_observacao_grava_nulo(qapp, caixa_fechado_na_tela, caixas_service):
    _abrir_pela_tela(qapp, caixa_fechado_na_tela, "10000")

    assert caixas_service.buscar_aberto().observacao_abertura is None


def test_cancelar_no_modal_nao_abre_caixa_nenhum(
    qapp, caixa_fechado_na_tela, caixas_service
):
    from gestor_comercial.services.exceptions import RegraDeNegocioError

    _abrir_pela_tela(qapp, caixa_fechado_na_tela, "10000", confirmar=False)

    with pytest.raises(RegraDeNegocioError):
        caixas_service.buscar_aberto()


def test_o_erro_do_service_continua_aparecendo_na_tela_de_tras(
    qapp, caixa_fechado_na_tela, caixas_service, auth
):
    """Quem barra a abertura continua sendo o service, e a mensagem dele continua
    saindo na linha vermelha da tela — o modal não passou a decidir nada."""
    auth.logout()

    _abrir_pela_tela(qapp, caixa_fechado_na_tela, "10000")

    assert caixa_fechado_na_tela._label_erro.text() != ""


def test_o_turno_do_cartao_sai_da_mesma_regra_de_periodo_do_service(
    qapp, caixa_fechado_na_tela
):
    """"Turno da Noite" deriva de `periodo_do_turno`, a mesma heurística de hora
    que `identificacao_turno` usa para nomear um turno já existente. Não dá para
    chamar `identificacao_turno` aqui porque ela recebe um `Caixa` — e neste
    ponto ele ainda não existe."""
    from datetime import datetime

    from gestor_comercial.services.caixa_service import periodo_do_turno

    assert caixa_fechado_na_tela._turno_a_abrir() == (
        f"Turno da {periodo_do_turno(datetime.now())}"
    )


# ---------------------------------------------------------------------------
# Ciclo de vida — o RNF do Celeron
# ---------------------------------------------------------------------------


def test_o_valor_sobrevive_ao_fechamento_para_a_view_ler(abrir):
    """O contrário da limpeza do modal de PIN, e de propósito: lá o segredo tem
    que sumir da memória em `done()` e ninguém o lê de volta. Aqui `resultado()`
    é lido DEPOIS do `exec()` (§3.2), e zerar faria toda abertura ser gravada
    como R$ 0,00 — sem erro, sem aviso, com o turno começando errado."""
    modal = abrir()
    _digitar(modal, "10000")
    modal._campo_observacao.setText("fundo recebido do cofre")

    modal.accept()

    assert modal.resultado().valor == Decimal("100.00")
    assert modal.resultado().observacao == "fundo recebido do cofre"


def test_fechar_solta_as_tabelas_de_widget(qapp, abrir):
    modal = abrir()
    assert modal._atalhos and modal._teclado.teclas

    modal.reject()

    assert modal._atalhos == {}
    assert modal._teclado.teclas == {}


def test_fechar_remove_o_filtro_do_campo_de_observacao(qapp, abrir):
    """O `unbind` que o briefing pediu. O filtro guarda uma referência do
    diálogo dentro do campo: deixá-lo instalado é o tipo de nó que sobrevive ao
    `deleteLater()` do lado Python."""
    modal = abrir()
    removidos: list[object] = []
    modal._campo_observacao.removeEventFilter = removidos.append

    modal.reject()

    assert removidos == [modal]


def test_o_filtro_do_campo_so_engole_o_tab(qapp, abrir):
    """Consumir mais que o `Tab` faria o campo parar de aceitar letra — e a
    observação é justamente o que o operador digita ali."""
    from PySide6.QtCore import QEvent

    modal = abrir()
    letra = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a")

    assert modal.eventFilter(modal._campo_observacao, letra) is False
    assert modal.eventFilter(modal._campo_observacao, QEvent(QEvent.Type.Paint)) is False


def test_fechar_solta_o_escurecedor_da_janela(qapp, assentar):
    """O escurecedor é filho da JANELA, não do diálogo: `deleteLater()` do
    diálogo não o levaria junto. Uma semana de aberturas deixaria uma pilha de
    retângulos pretos invisíveis pendurada no `MainWindow`, que vive o processo
    inteiro."""
    pai = QWidget()
    pai.show()

    for _ in range(10):
        modal = AberturaCaixaDialog("Turno da Noite", "Gerente", pai)
        modal.show()
        qapp.processEvents()
        modal.reject()
        modal.deleteLater()
    assentar()

    assert pai.window().findChildren(Backdrop) == []


def test_trinta_aberturas_nao_deixam_nada_preso_a_view(qapp, assentar, caixa_fechado_na_tela):
    """O caminho real: a tela de Caixa como parent, `exec()` de verdade e
    fechamento pelo Cancelar. Se alguém trocar `executar_modal()` por um
    `.exec()` cru em `_abrir_caixa`, é aqui que aparece."""
    for _ in range(30):
        modal = AberturaCaixaDialog("Turno da Noite", "Gerente", caixa_fechado_na_tela)
        QTimer.singleShot(0, modal.reject)
        modal.exec()
        modal.deleteLater()
        del modal
    assentar()

    assert caixa_fechado_na_tela.findChildren(AberturaCaixaDialog) == []


def test_o_cartao_cabe_na_tela_do_food_truck(qapp, abrir):
    """1366x768 é a máquina do balcão, e o Windows come uma barra de tarefas.

    A moldura é 728px de altura útil, e a suíte roda `offscreen` — que sobe sem
    banco de fontes e mede TUDO maior que a máquina real. Ou seja, o teste é
    pessimista de propósito: se passa aqui, passa lá.
    """
    modal = abrir()
    modal.show()
    qapp.processEvents()
    modal.adjustSize()
    altura = modal.height()
    modal.reject()

    assert altura <= ALTURA_UTIL_PX, (
        f"o cartão de abertura pediu {altura}px de altura — num monitor de 768px "
        "ele sairia da tela pela borda de baixo"
    )
