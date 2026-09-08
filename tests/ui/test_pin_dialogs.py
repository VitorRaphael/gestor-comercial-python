"""O modal de PIN: numpad, cascata de acesso intacta e saída limpa. Ver §3.9.

Este arquivo nasceu medindo um defeito de higiene nos DOIS diálogos de PIN que
o app tinha (`GerentePinDialog` e `LojaPinDialog`, cópia um do outro): eles
declaravam a intenção de limpar o PIN do campo, mas pendurada no hook errado.

    def closeEvent(self, event):
        self._campo_pin.clear()

`closeEvent` só dispara no X da janela. O botão Entrar (`accept()`), o Cancelar
(`reject()`) e o Esc passam todos por `QDialog::done()`, que faz `hide()` — não
`close()`. Medido pelo caminho real de `main_window._abrir_caixa`, com laço de
eventos rodando e um espião no hook:

    Cancelar : PIN no campo logo após exec() = '1234' | closeEvent disparou? False
    Entrar   : PIN no campo logo após exec() = '1234' | closeEvent disparou? False

Ou seja, o `clear()` era código morto nos três caminhos que o operador usa.

Os dois diálogos viraram um só (`PinPadDialog`), com teclado numérico na tela,
e a bateria acompanhou: a metade de cima é a mesma prova de §3.9 refeita sobre
o componente novo — inclusive nos dois usos, porque parametrizar continua sendo
o que impede um deles de ser corrigido e o outro ficar para trás. A metade de
baixo cobre o que o componente ganhou: numpad, teclado físico, aviso de PIN
recusado e o descarte do escurecedor e do timer.

## O tamanho honesto do ganho

Isto é higiene, não blindagem criptográfica. Nem soltar a string nem destruir o
widget **zeram** a memória: as duas só largam a referência, e o PIN ainda passa
por `_confirmar()` e por `validar_pin_*()` como objeto Python comum. O que estes
testes garantem é que o segredo não fica pendurado num atributo de um widget
vivo — o "para sempre" do §3.9 original dependia do §3.2, que a Fase 3 derrubou.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QWidget

from gestor_comercial.services.exceptions import NaoAutorizadoError
from gestor_comercial.ui.widgets.pin_pad_dialog import PinPadDialog
from tests.conftest import PIN_MASTER, PIN_OPERACIONAL

PIN_DIGITADO = "1234"


def _teclar(dialogo: PinPadDialog, tecla: Qt.Key, texto: str = "") -> None:
    """Um toque no teclado FÍSICO, como o Qt entregaria ao diálogo."""
    dialogo.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier, texto)
    )


def _tecla_do_numpad(dialogo: PinPadDialog, rotulo: str):
    """O botão da tela com aquele rótulo — o caminho do dedo, não do teclado."""
    from PySide6.QtWidgets import QPushButton

    return next(b for b in dialogo.findChildren(QPushButton) if b.text() == rotulo)


@pytest.fixture(params=["caixa", "loja"])
def dialogo(request, qapp, auth):
    """O mesmo componente nos seus dois usos, testado pela mesma bateria."""
    pai = QWidget()
    fabrica = PinPadDialog.para_caixa if request.param == "caixa" else PinPadDialog.para_loja
    modal = fabrica(auth, pai)
    modal._pai_de_teste = pai  # segura o parent vivo pelo tempo do teste
    return modal


# ---------------------------------------------------------------------------
# §3.9 — o segredo não sobrevive ao fechamento, por nenhum dos caminhos
# ---------------------------------------------------------------------------


def test_o_cancelar_limpa_o_pin_digitado(dialogo):
    """O caminho mais comum: o operador abre por engano e desiste."""
    dialogo._pin = PIN_DIGITADO

    dialogo.reject()

    assert dialogo._pin == ""


def test_o_entrar_limpa_o_pin_digitado(dialogo):
    """`accept()` também passa por `done()` — o PIN certo não pode ficar
    guardado no diálogo só porque foi aceito."""
    dialogo._pin = PIN_DIGITADO

    dialogo.accept()

    assert dialogo._pin == ""


def test_o_esc_limpa_o_pin_digitado(dialogo, qapp):
    """O Esc é `reject()` por baixo, mas por um caminho diferente do botão:
    vem do `keyPressEvent` padrão do `QDialog`. Vale um teste próprio porque é
    o atalho que o operador com pressa usa."""
    dialogo._pin = PIN_DIGITADO

    _teclar(dialogo, Qt.Key.Key_Escape)

    assert dialogo._pin == ""


def test_o_botao_de_fechar_limpa_o_pin_digitado(dialogo):
    """O ✕ do cabeçalho é novo — a moldura de janela do sistema sumiu junto com
    o `QFormLayout`, então ele é agora o único X da tela."""
    dialogo._pin = PIN_DIGITADO

    dialogo._botao_fechar.click()

    assert dialogo._pin == ""
    assert dialogo.result() != QDialog.DialogCode.Accepted


def test_o_codigo_de_saida_continua_chegando_a_quem_chamou(dialogo):
    """A armadilha da correção: sobrescrever `done()` e esquecer do
    `super().done(resultado)` faria o diálogo nunca fechar, e
    `main_window._abrir_caixa` ficaria preso esperando um `exec()` que não
    volta. Trancar o PIN não pode custar a tela do Caixa."""
    dialogo._pin = PIN_DIGITADO

    dialogo.done(QDialog.DialogCode.Accepted)

    assert dialogo.result() == QDialog.DialogCode.Accepted


def test_o_pin_errado_e_limpo_sem_fechar_o_dialogo(dialogo):
    """PIN recusado limpa os dígitos e deixa o operador tentar de novo na mesma
    tela — travar ou fechar no meio do atendimento é o que não pode acontecer."""
    dialogo._pin = "999999"

    dialogo._confirmar()

    assert dialogo._pin == ""
    assert dialogo.isVisible() is False  # nunca chegou a ser mostrado
    assert dialogo.result() != QDialog.DialogCode.Accepted


# ---------------------------------------------------------------------------
# A cascata de acesso (§3.13) não foi tocada pela troca de interface
# ---------------------------------------------------------------------------


def test_o_caixa_aceita_a_senha_operacional(qapp, auth, gerente):
    """Nível 2: a Operacional basta, e a Master também (herança em cascata)."""
    modal = PinPadDialog.para_caixa(auth)

    modal._pin = PIN_OPERACIONAL
    modal._confirmar()

    assert modal.result() == QDialog.DialogCode.Accepted


def test_a_loja_recusa_a_senha_operacional_e_aceita_a_master(qapp, auth, gerente):
    """Nível 3: o inverso da cascata não existe — a Operacional NÃO abre a
    Central de Loja. É a regra de negócio que a refatoração visual não podia
    afrouxar, e o único jeito de provar isso é pelos dois lados."""
    modal = PinPadDialog.para_loja(auth)

    modal._pin = PIN_OPERACIONAL
    modal._confirmar()
    assert modal.result() != QDialog.DialogCode.Accepted, (
        "a Senha Operacional abriu a Central de Loja — a cascata do §3.13 foi invertida"
    )

    modal._pin = PIN_MASTER
    modal._confirmar()
    assert modal.result() == QDialog.DialogCode.Accepted


def test_o_dialogo_nao_sabe_de_nivel_de_acesso(qapp):
    """O componente é parametrizável de verdade: quem decide é o validador que
    chega de fora, não um `if` escondido na tela."""
    chamadas: list[str] = []

    def validador(pin: str) -> None:
        chamadas.append(pin)

    modal = PinPadDialog("Título", "SUBTÍTULO", validador)
    modal._pin = "4321"

    modal._confirmar()

    assert chamadas == ["4321"]
    assert modal.result() == QDialog.DialogCode.Accepted


# ---------------------------------------------------------------------------
# Entrada híbrida: o dedo na tela e o teclado físico fazem a mesma coisa
# ---------------------------------------------------------------------------


def test_o_numpad_da_tela_digita(dialogo):
    """O caminho do food truck: operador de pé, teclado atrás do monitor."""
    for rotulo in ("0", "5", "0", "7"):
        _tecla_do_numpad(dialogo, rotulo).click()

    assert dialogo._pin == "0507"


def test_o_teclado_fisico_digita_o_mesmo(dialogo):
    """O teclado numérico USB entra por aqui — é o mesmo `keyPressEvent`."""
    for digito in "0507":
        _teclar(dialogo, getattr(Qt.Key, f"Key_{digito}"), digito)

    assert dialogo._pin == "0507"


def test_o_backspace_e_a_tecla_de_apagar_tiram_um_digito_cada(dialogo):
    dialogo._pin = "1234"

    _teclar(dialogo, Qt.Key.Key_Backspace)
    _tecla_do_numpad(dialogo, "⌫").click()

    assert dialogo._pin == "12"


def test_o_enter_confirma_igual_ao_botao(dialogo):
    """Enter e ENTRAR percorrem o mesmo `_confirmar()`: quem digita rápido não
    pode cair num caminho diferente de quem clica."""
    dialogo._pin = "999999"

    _teclar(dialogo, Qt.Key.Key_Return)

    assert dialogo._pin == "", "o Enter não chegou ao _confirmar()"


def test_tecla_que_nao_e_digito_nao_entra_no_pin(dialogo):
    """Letra, vírgula ou seta no meio da digitação não podem virar dígito — o
    PIN é comparado como string, e um caractere a mais reprova em silêncio."""
    _teclar(dialogo, Qt.Key.Key_A, "a")
    _teclar(dialogo, Qt.Key.Key_Comma, ",")
    _teclar(dialogo, Qt.Key.Key_Left)

    assert dialogo._pin == ""


def test_o_pin_nao_cresce_sem_fim(dialogo):
    """Dedo preso na tecla não pode fazer a string crescer sem teto na memória
    do Celeron. O limite é do widget, não da regra de senha."""
    for _ in range(dialogo.LIMITE_DE_DIGITOS + 20):
        dialogo._digitar("7")

    assert len(dialogo._pin) == dialogo.LIMITE_DE_DIGITOS


# ---------------------------------------------------------------------------
# Marcadores (dots) e aviso de PIN recusado
# ---------------------------------------------------------------------------


def _estados(dialogo: PinPadDialog) -> list[str]:
    return [dot.property("estado") for dot in dialogo._dots if dot.isVisible()]


def test_os_marcadores_acendem_um_por_digito(dialogo, qapp):
    dialogo.show()
    qapp.processEvents()

    for digito in "123":
        dialogo._digitar(digito)

    assert _estados(dialogo) == ["cheio"] * 3 + ["vazio"] * 3


def test_a_fileira_cresce_para_a_senha_de_oito_digitos(dialogo, qapp):
    """A Operacional de fábrica tem oito caracteres e a Master seis: uma fileira
    fixa de seis não mostraria os dois últimos toques da mais longa."""
    dialogo.show()
    qapp.processEvents()

    for digito in PIN_OPERACIONAL:
        dialogo._digitar(digito)

    assert len(_estados(dialogo)) == len(PIN_OPERACIONAL) == 8
    assert set(_estados(dialogo)) == {"cheio"}


def test_o_pin_recusado_pinta_os_marcadores_e_avisa(dialogo, qapp):
    dialogo.show()
    qapp.processEvents()
    dialogo._pin = "999999"

    dialogo._confirmar()

    assert set(_estados(dialogo)) == {"erro"}
    assert dialogo._label_instrucao.property("estado") == "erro"
    assert dialogo._label_instrucao.text() != dialogo.INSTRUCAO


def test_o_aviso_some_quando_o_operador_volta_a_digitar(dialogo, qapp):
    dialogo.show()
    qapp.processEvents()
    dialogo._pin = "999999"
    dialogo._confirmar()

    dialogo._digitar("1")

    assert dialogo._label_instrucao.property("estado") == "normal"
    assert dialogo._label_instrucao.text() == dialogo.INSTRUCAO
    assert _estados(dialogo) == ["cheio"] + ["vazio"] * 5


def test_a_cor_do_aviso_vem_do_qss_global_e_nao_do_widget(dialogo):
    """§3.15: cor pintada no próprio widget congela na paleta do boot e a tela
    para de acompanhar o alternador Claro/Escuro. Aqui só a propriedade muda."""
    dialogo._pin = "999999"
    dialogo._confirmar()

    assert dialogo._label_instrucao.styleSheet() == ""
    assert all(dot.styleSheet() == "" for dot in dialogo._dots)


# ---------------------------------------------------------------------------
# Ciclo de vida: nada agendado nem pendurado sobrevive ao fechamento
# ---------------------------------------------------------------------------


def test_o_timer_do_aviso_e_parado_ao_fechar(dialogo):
    """Um `QTimer` de 2,5s disparando depois do `exec()` mexeria em widgets de
    um diálogo já a caminho do descarte — é a classe de falha que o
    `nao_deixa_escapar` só consegue registrar depois de acontecida."""
    dialogo._pin = "999999"
    dialogo._confirmar()
    assert dialogo._timer_erro.isActive()

    dialogo.reject()

    assert not dialogo._timer_erro.isActive()


def test_o_escurecedor_aparece_ao_abrir_e_some_ao_fechar(qapp, assentar):
    """O escurecedor é filho da JANELA, não do diálogo: se ele não for solto no
    `done()`, cada ida à Central de Loja deixa um véu invisível pendurado no
    `MainWindow`, que vive o processo inteiro."""
    from gestor_comercial.ui.widgets.cartao_modal import Backdrop

    janela = QWidget()
    janela.resize(800, 600)

    def validador(_pin: str) -> None:
        raise NaoAutorizadoError("PIN inválido.")

    for _ in range(10):
        modal = PinPadDialog("Caixa", "PIN", validador, janela)
        modal.show()
        qapp.processEvents()
        assert len(janela.findChildren(Backdrop)) == 1
        modal.reject()
        modal.deleteLater()
    assentar()

    assert janela.findChildren(Backdrop) == [], (
        "escurecedor(es) continuam pendurados na janela depois de 10 aberturas"
    )


def test_sem_parent_o_dialogo_abre_sozinho_sem_escurecedor(qapp):
    """Nem todo uso tem janela atrás (a suíte é um deles). Sem parent não há o
    que escurecer, e isso não pode virar exceção no meio do `showEvent`."""
    modal = PinPadDialog("Caixa", "PIN", lambda _pin: None)

    modal.show()
    qapp.processEvents()

    assert modal._backdrop is None
    modal.reject()
    modal.deleteLater()


# ---------------------------------------------------------------------------
# O padding generico nao pode comer o rotulo de uma tecla de tamanho fixo
# ---------------------------------------------------------------------------
#
# Defeito pego na verificacao visual desta refatoracao: o botao de fechar saia
# como um circulo VAZIO. Nao era glifo faltando na fonte nem cor errada -- a
# regra generica `QPushButton {{ padding: 10px 16px }}` do QSS global se aplica
# a ele tambem, e num botao de 32px fixos os 16px de cada lado zeram a largura
# util. Sem espaco, o Qt simplesmente nao desenha o texto.
#
# A medida abaixo nao depende de fonte, e por isso vale na plataforma
# `offscreen` (que sobe sem banco de fontes): pergunta ao proprio estilo quanto
# do botao sobrou para o conteudo depois do padding.


@pytest.fixture
def tema_aplicado(qapp):
    """QSS global aplicado — é ele que traz o padding genérico para a conta."""
    from gestor_comercial.ui.theme.controller import ThemeController

    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    try:
        yield controlador
    finally:
        controlador.alternar_para(False)


def _largura_util(botao) -> int:
    from PySide6.QtWidgets import QStyle, QStyleOptionButton

    opcao = QStyleOptionButton()
    opcao.initFrom(botao)
    opcao.rect = botao.rect()
    return botao.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, opcao, botao).width()


def test_premissa_o_padding_generico_zera_um_botao_de_32px(qapp, tema_aplicado):
    """O mecanismo do defeito, isolado. Enquanto este teste passar, o `padding: 0`
    das teclas do PinPad tem razão de existir — e não é enfeite."""
    from PySide6.QtWidgets import QPushButton

    pai = QWidget()
    cru = QPushButton("✕", pai)
    cru.setFixedSize(32, 32)
    cru.ensurePolished()

    assert _largura_util(cru) == 0, (
        "a premissa mudou: o padding genérico deixou de engolir o botão pequeno"
    )


def test_nenhuma_tecla_do_pinpad_perde_o_rotulo_para_o_padding(qapp, tema_aplicado):
    """A adoção: no cartão de verdade, todo botão mantém a maior parte da
    largura para o rótulo.

    Metade é o corte por ser folgado o bastante para não reprovar por um pixel
    de arredondamento e apertado o bastante para pegar o defeito real, que
    levava a largura útil a **zero**.
    """
    from PySide6.QtWidgets import QPushButton

    janela = QWidget()
    janela.resize(1000, 700)
    janela.show()
    modal = PinPadDialog("Área da Loja", "PIN DE SUPERVISOR", lambda _pin: None, janela)
    modal.show()
    qapp.processEvents()

    espremidos = [
        f"{b.objectName()}({b.text()!r}): {_largura_util(b)} de {b.width()}px"
        for b in modal.findChildren(QPushButton)
        if _largura_util(b) < b.width() // 2
    ]
    modal.reject()
    modal.deleteLater()

    assert not espremidos, "tecla(s) sem largura útil para o rótulo:\n  " + "\n  ".join(espremidos)
