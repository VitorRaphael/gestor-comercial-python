"""Os dois diálogos de PIN largam o segredo ao fechar. Ver §3.9.

O código já declarava a intenção de limpar o PIN do campo, mas pendurada no
hook errado:

    def closeEvent(self, event):
        self._campo_pin.clear()

`closeEvent` só dispara no X da janela. O botão Entrar (`accept()`), o Cancelar
(`reject()`) e o Esc passam todos por `QDialog::done()`, que faz `hide()` — não
`close()`. Medido pelo caminho real de `main_window._abrir_caixa`, com laço de
eventos rodando e um espião no hook:

    Cancelar : PIN no campo logo após exec() = '1234' | closeEvent disparou? False
    Entrar   : PIN no campo logo após exec() = '1234' | closeEvent disparou? False

Ou seja, o `clear()` era código morto nos três caminhos que o operador usa.

## O tamanho honesto do ganho

Isto é higiene, não blindagem criptográfica. Nem `clear()` nem a destruição do
widget **zeram** a memória: as duas só soltam a referência, e o `str` do PIN
ainda passa por `_confirmar()` e por `validar_pin_gerente()` como objeto Python
comum. O que estes testes garantem é que o segredo não fica pendurado num campo
de um widget vivo — o "para sempre" do §3.9 original dependia do §3.2, que a
Fase 3 derrubou.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QWidget

from gestor_comercial.ui.widgets.gerente_pin_dialog import GerentePinDialog
from gestor_comercial.ui.widgets.loja_pin_dialog import LojaPinDialog

PIN_DIGITADO = "1234"


@pytest.fixture(params=["gerente", "loja"])
def dialogo(request, qapp, auth):
    """Os dois diálogos, testados pela mesma bateria.

    Eles são cópia um do outro em tudo que interessa aqui (campo de PIN, botões
    Entrar/Cancelar, `done()`), e o §3.9 pedia a correção nos dois. Parametrizar
    é o que impede um deles de ser corrigido e o outro ficar para trás.
    """
    pai = QWidget()
    classe = GerentePinDialog if request.param == "gerente" else LojaPinDialog
    modal = classe(auth, pai)
    modal._pai_de_teste = pai  # segura o parent vivo pelo tempo do teste
    return modal


def test_o_cancelar_limpa_o_pin_digitado(dialogo):
    """O caminho mais comum: o operador abre por engano e desiste."""
    dialogo._campo_pin.setText(PIN_DIGITADO)

    dialogo.reject()

    assert dialogo._campo_pin.text() == ""


def test_o_entrar_limpa_o_pin_digitado(dialogo):
    """`accept()` também passa por `done()` — o PIN certo não pode ficar no
    campo só porque foi aceito."""
    dialogo._campo_pin.setText(PIN_DIGITADO)

    dialogo.accept()

    assert dialogo._campo_pin.text() == ""


def test_o_esc_limpa_o_pin_digitado(dialogo, qapp):
    """O Esc é `reject()` por baixo, mas por um caminho diferente do botão:
    vem do `keyPressEvent` padrão do `QDialog`. Vale um teste próprio porque é
    o atalho que o operador com pressa usa."""
    dialogo._campo_pin.setText(PIN_DIGITADO)

    dialogo.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    )

    assert dialogo._campo_pin.text() == ""


def test_o_codigo_de_saida_continua_chegando_a_quem_chamou(dialogo):
    """A armadilha da correção: sobrescrever `done()` e esquecer do
    `super().done(resultado)` faria o diálogo nunca fechar, e
    `main_window._abrir_caixa` ficaria preso esperando um `exec()` que não
    volta. Trancar o PIN não pode custar a tela do Caixa."""
    dialogo._campo_pin.setText(PIN_DIGITADO)

    dialogo.done(QDialog.DialogCode.Accepted)

    assert dialogo.result() == QDialog.DialogCode.Accepted


def test_o_pin_errado_ja_era_limpo_e_continua_sendo(dialogo):
    """Regressão do que já funcionava: PIN recusado limpa o campo e devolve o
    foco, sem fechar o diálogo. Esse `clear()` é outro, dentro de `_confirmar()`,
    e a correção do §3.9 não podia atropelá-lo."""
    dialogo._campo_pin.setText("999999")

    dialogo._confirmar()

    assert dialogo._campo_pin.text() == ""
    assert dialogo.isVisible() is False  # nunca chegou a ser mostrado
    assert dialogo.result() != QDialog.DialogCode.Accepted
