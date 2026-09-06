"""Nenhum modal pode sobreviver ao próprio fechamento.

Ver `REMASTERIZACAO-V1.md` §3.2 — este é o teste que trava o vazamento
dominante de memória do app.

## Por que estes testes começam marcados `xfail`

Eles descrevem o comportamento que a **Fase 4** vai implementar, e foram
escritos **antes** da correção de propósito: um teste de vazamento que já nasce
verde não prova nada. Hoje eles falham, e o `xfail` mantém a suíte verde sem
esconder o problema.

O marcador é `strict=True`. Isso significa que, quando a Fase 4 corrigir o
ciclo de vida dos modais, estes testes vão passar — e o `strict` transforma o
"passou inesperadamente" em **falha**. Ou seja: a suíte avisa na hora de tirar
o marcador. Não tem como a correção entrar e o teste continuar mentindo.

## O que o app faz hoje

    modal = CancelamentoDialog(titulo, self)   # parent = uma view que nunca morre
    if modal.exec() != QDialog.DialogCode.Accepted:
        return                                  # ninguém destrói o modal

Soltar o nome Python não destrói nada: a posse do objeto é do parent, em C++.
E as 10 views são montadas no boot e vivem o processo inteiro
(`main_window.py:138-182`), então cada modal aberto fica pendurado para sempre.
"""

from __future__ import annotations

import gc

import pytest
from PySide6.QtWidgets import QDialog, QWidget

from gestor_comercial.ui.views.cancelamento_dialog import CancelamentoDialog
from gestor_comercial.ui.widgets.gerente_pin_dialog import GerentePinDialog
from gestor_comercial.ui.widgets.loja_pin_dialog import LojaPinDialog

# Motivo único, para o relatório do pytest dizer o que está pendente.
PENDENTE_FASE_4 = "Fase 4 da Remasterização: modais ainda não são destruídos (§3.2)"

ABERTURAS = 30


def _assentar(qapp) -> None:
    """Dá ao Qt e ao Python toda chance de liberar o que puder ser liberado.

    Sem isso um `deleteLater()` legítimo ainda estaria pendente na fila de
    eventos e o teste acusaria vazamento onde não há. Com isso, o que sobrar
    sobrou de verdade.
    """
    gc.collect()
    qapp.processEvents()
    gc.collect()
    qapp.processEvents()


def _abrir_e_fechar(fabrica, pai: QWidget, vezes: int = ABERTURAS) -> None:
    """Repete o ciclo exato do código de produção: cria com parent, fecha pelo
    caminho do usuário (`reject()`, o mesmo que o botão Cancelar e o Esc) e
    solta a referência Python."""
    for _ in range(vezes):
        modal = fabrica(pai)
        modal.reject()
        del modal


@pytest.mark.xfail(strict=True, reason=PENDENTE_FASE_4)
def test_cancelamento_dialog_nao_acumula(qapp):
    pai = QWidget()

    _abrir_e_fechar(lambda p: CancelamentoDialog("Cancelar item", p), pai)
    _assentar(qapp)

    vivos = pai.findChildren(CancelamentoDialog)
    assert vivos == [], (
        f"{len(vivos)} de {ABERTURAS} modais de cancelamento continuam presos ao parent. "
        "Cada cancelamento de item na comanda deixa um para trás."
    )


@pytest.mark.xfail(strict=True, reason=PENDENTE_FASE_4)
def test_gerente_pin_dialog_nao_acumula(qapp, auth):
    """O modal de PIN de gerente é aberto a cada cancelamento autorizado."""
    pai = QWidget()

    _abrir_e_fechar(lambda p: GerentePinDialog(auth, p), pai)
    _assentar(qapp)

    assert pai.findChildren(GerentePinDialog) == []


@pytest.mark.xfail(strict=True, reason=PENDENTE_FASE_4)
def test_loja_pin_dialog_nao_acumula(qapp, auth):
    """Este é o pior caso de frequência: `main_window.py:327-329` exige o PIN a
    cada acesso à Central de Loja, e `_trancar_loja()` roda em toda navegação
    para fora. Um modal por ida e volta."""
    pai = QWidget()

    _abrir_e_fechar(lambda p: LojaPinDialog(auth, p), pai)
    _assentar(qapp)

    assert pai.findChildren(LojaPinDialog) == []


@pytest.mark.xfail(strict=True, reason=PENDENTE_FASE_4)
def test_nenhum_qdialog_sobrevive_ao_fechamento(qapp, auth):
    """Rede larga: qualquer `QDialog` pendurado no parent, de qualquer tipo.

    Existe para pegar modal novo que alguém adicione depois sem lembrar de
    liberar — inclusive `QMessageBox`, que também é `QDialog` e aparece em
    `cardapio_view.py:489`, `comanda_view.py:710` e `caixa_view.py:740`.
    """
    pai = QWidget()

    _abrir_e_fechar(lambda p: CancelamentoDialog("Cancelar comanda", p), pai, vezes=10)
    _abrir_e_fechar(lambda p: GerentePinDialog(auth, p), pai, vezes=10)
    _abrir_e_fechar(lambda p: LojaPinDialog(auth, p), pai, vezes=10)
    _assentar(qapp)

    vivos = pai.findChildren(QDialog)
    assert vivos == [], f"{len(vivos)} diálogos de 30 aberturas continuam na memória"


def test_o_vazamento_de_hoje_esta_documentado(qapp):
    """Trava o comportamento ATUAL, para a Fase 4 ter um "antes" verificável.

    Diferente dos testes acima, este passa hoje. Quando a Fase 4 corrigir o
    ciclo de vida, ele vai falhar — e é para falhar mesmo: é o par do `xfail`,
    e sai junto com eles. Enquanto existir, é a prova de que o vazamento é real
    e não teoria.
    """
    pai = QWidget()

    _abrir_e_fechar(lambda p: CancelamentoDialog("Cancelar item", p), pai)
    _assentar(qapp)

    assert len(pai.findChildren(CancelamentoDialog)) == ABERTURAS, (
        "O vazamento descrito no §3.2 não reproduziu. Se a correção da Fase 4 já "
        "entrou, remova este teste e o marcador xfail dos testes acima."
    )
