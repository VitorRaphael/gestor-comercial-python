"""Nenhum diálogo do app pode sobreviver ao próprio fechamento.

Ver `REMASTERIZACAO-V1.md` §3.2 — **e a correção do §3.2 na Fase 3**.

## O que mudou nestes testes, e por quê

Na Fase 0 este arquivo nasceu com quatro `xfail(strict=True)`: eles descreviam
o vazamento do §3.2 e falhavam de propósito, à espera da Fase 4. A Fase 3
derrubou a premissa. Remedido com um laço de eventos rodando de verdade, em
`offscreen` e em `windows`:

    30 diálogos construídos e fechados com `reject()`, SEM `exec()`: 30 presos
    30 diálogos abertos com `exec()` — o caminho real do app:          0 presos

Os `xfail` mediam o primeiro cenário — `CancelamentoDialog(...)` seguido de
`reject()`, sem abrir — que **nenhum dos 31 sites do app percorre**. Eram
portanto testes que nenhuma correção feita nas views poderia deixar verdes:
mediam a API crua do Qt, não o app. Por isso foram reescritos em vez de
"corrigidos".

## O que eles medem agora

O caminho que o app realmente percorre: diálogo real, com a view como parent,
aberto com `exec()` e fechado pelo botão do usuário. Depois de trinta idas e
voltas, a view — que vive o processo inteiro — não pode ter um único diálogo
pendurado. É regressão de verdade: se alguém trocar o ciclo de vida dos modais
por um que retenha, é aqui que aparece.

`test_construir_sem_abrir_deixa_o_dialogo_presa_view` é o teste de premissa:
enquanto ele passar, `executar_modal()`/`descartar_modal()` (§3.2) têm razão de
existir, porque a armadilha continua a um passo de distância.

O contrato dos utilitários em si é testado em `test_modais.py`. Aqui é o app.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QWidget

from gestor_comercial.ui.views.cancelamento_dialog import CancelamentoDialog
from gestor_comercial.ui.widgets.adicionar_item_dialog import AdicionarItemDialog
from gestor_comercial.ui.widgets.funcionario_dialog import FuncionarioDialog
from gestor_comercial.ui.widgets.pin_pad_dialog import PinPadDialog

ABERTURAS = 30


def _abrir_e_fechar(fabrica, pai: QWidget, vezes: int = ABERTURAS) -> None:
    """Repete o ciclo exato do código de produção.

    Cria com a view como parent, **abre com `exec()`** e fecha pelo caminho do
    usuário (`reject()`, o mesmo do botão Cancelar e do Esc). O `singleShot` é
    o teste fazendo o papel do dedo do operador: `exec()` bloqueia até alguém
    fechar o diálogo, e o app não usa `QTimer` em lugar nenhum.
    """
    for _ in range(vezes):
        modal = fabrica(pai)
        QTimer.singleShot(0, modal.reject)
        modal.exec()
        del modal


def test_cancelamento_dialog_nao_acumula(qapp, assentar):
    """Aberto a cada cancelamento de item ou de comanda inteira."""
    pai = QWidget()

    _abrir_e_fechar(lambda p: CancelamentoDialog("Cancelar item", p), pai)
    assentar()

    vivos = pai.findChildren(CancelamentoDialog)
    assert vivos == [], (
        f"{len(vivos)} de {ABERTURAS} modais de cancelamento continuam presos à view. "
        "Cada cancelamento de item na comanda deixaria um para trás."
    )


def test_pin_do_caixa_nao_acumula(qapp, assentar, auth):
    """O modal de PIN do Caixa é aberto a cada entrada na tela (Nível 2)."""
    pai = QWidget()

    _abrir_e_fechar(lambda p: PinPadDialog.para_caixa(auth, p), pai)
    assentar()

    assert pai.findChildren(PinPadDialog) == []


def test_pin_da_loja_nao_acumula(qapp, assentar, auth):
    """Este é o pior caso de frequência: `main_window._abrir_area_loja` exige o
    PIN a cada acesso à Central de Loja, e `_trancar_loja()` roda em toda
    navegação para fora. Um modal por ida e volta.

    Os dois usos são a MESMA classe desde a unificação em `PinPadDialog`, mas
    continuam com teste próprio: o que se mede aqui é o site de chamada, e é
    dele que sai a frequência."""
    pai = QWidget()

    _abrir_e_fechar(lambda p: PinPadDialog.para_loja(auth, p), pai)
    assentar()

    assert pai.findChildren(PinPadDialog) == []


def test_adicionar_item_nao_acumula(qapp, assentar):
    """Um diálogo por clique em "+ Item" — e numa mesa de oito pessoas o
    operador entra e sai dele o dia inteiro. O comportamento completo do modal
    está em `test_adicionar_item_dialog.py`; aqui ele entra no inventário de
    modais do app, que é o que esta varredura mantém.

    Cardápio vazio de propósito: o que se mede é o ciclo de vida do diálogo, e
    ele não muda com o número de produtos.
    """
    pai = QWidget()

    _abrir_e_fechar(lambda p: AdicionarItemDialog([], "Mesa 1", lambda *_: None, p), pai)
    assentar()

    assert pai.findChildren(AdicionarItemDialog) == []


def test_nenhum_qdialog_sobrevive_ao_fechamento(qapp, assentar, auth):
    """Rede larga: qualquer `QDialog` pendurado na view, de qualquer tipo.

    Existe para pegar modal novo que alguém adicione depois sem lembrar de
    liberar — inclusive `QMessageBox`, que também é `QDialog` e aparece em
    `cardapio_view.py:489`, `comanda_view.py:710` e `caixa_view.py:740`.
    """
    pai = QWidget()

    _abrir_e_fechar(lambda p: CancelamentoDialog("Cancelar comanda", p), pai, vezes=10)
    _abrir_e_fechar(lambda p: PinPadDialog.para_caixa(auth, p), pai, vezes=10)
    _abrir_e_fechar(lambda p: PinPadDialog.para_loja(auth, p), pai, vezes=10)
    _abrir_e_fechar(lambda p: AdicionarItemDialog([], "Mesa 1", lambda *_: None, p), pai, vezes=10)
    assentar()

    vivos = pai.findChildren(QDialog)
    assert vivos == [], f"{len(vivos)} diálogos de 40 aberturas continuam na memória"


def test_construir_sem_abrir_deixa_o_dialogo_preso_a_view(qapp, assentar):
    """A premissa, e a única forma de vazar que sobrou do §3.2.

    Construir com parent e fechar **sem `exec()`** deixa o diálogo pendurado na
    view: não houve laço de eventos dono do `exec()` para recolhê-lo, e a posse
    do objeto é do parent, em C++ — soltar o nome Python não destrói nada.

    Nenhum dos 31 sites do app faz isso hoje (todos abrem com `exec()`), e é
    por isso que o §3.2 foi rebaixado. Mas a armadilha está a um passo: basta
    alguém construir um diálogo para "só configurar" e desistir no meio. É esse
    passo que `executar_modal()`/`descartar_modal()` fecham.

    Se este teste um dia falhar, o Qt passou a recolher sozinho e os
    utilitários do §3.2 viram redundância — remedir antes de removê-los.
    """
    pai = QWidget()

    for _ in range(ABERTURAS):
        modal = CancelamentoDialog("Cancelar item", pai)
        modal.reject()  # sem `exec()`: o caminho que a bancada de medição usava
        del modal
    assentar()

    assert len(pai.findChildren(CancelamentoDialog)) == ABERTURAS, (
        "Diálogo construído sem `exec()` deixou de ficar preso ao parent. O §3.2 "
        "perdeu a última forma de vazar — reavaliar `modais.py` antes da Fase 5."
    )


def test_o_utilitario_fecha_a_armadilha_da_premissa(qapp, assentar):
    """A contraprova do teste acima: o mesmo laço, agora com `descartar_modal()`.

    É o par que dá sentido ao anterior — um mostra o buraco, o outro mostra o
    utilitário tapando. Sem este, a premissa seria só uma curiosidade sobre o Qt.
    """
    from gestor_comercial.ui.widgets.modais import descartar_modal

    pai = QWidget()

    for _ in range(ABERTURAS):
        modal = CancelamentoDialog("Cancelar item", pai)
        modal.reject()
        descartar_modal(modal)
        del modal
    assentar()

    assert pai.findChildren(CancelamentoDialog) == []


@pytest.mark.parametrize("codigo", [QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected])
def test_fechar_pelo_ok_ou_pelo_cancelar_libera_igual(qapp, assentar, codigo):
    """`accept()` e `reject()` passam os dois por `done()`, e nenhum dos dois
    pode reter o diálogo. Vale para o operador que confirma tanto quanto para o
    que desiste — e é o mesmo `done()` que limpa o PIN (§3.9,
    `test_pin_dialogs.py`)."""
    pai = QWidget()

    for _ in range(ABERTURAS):
        modal = CancelamentoDialog("Cancelar item", pai)
        QTimer.singleShot(0, lambda m=modal: m.done(codigo))
        modal.exec()
        del modal
    assentar()

    assert pai.findChildren(CancelamentoDialog) == []


def test_novo_funcionario_nao_acumula(qapp, assentar):
    """Aberto a cada cadastro e a cada edição de funcionário. É o modal menos
    frequente dos quatro — e entra nesta varredura exatamente por isso: o
    inventário só serve enquanto for completo. O comportamento dele está em
    `test_funcionario_dialog.py`.

    Sem funcionário de propósito: o que se mede é o ciclo de vida, e ele é o
    mesmo abrindo em branco ou para editar.
    """
    pai = QWidget()

    _abrir_e_fechar(lambda p: FuncionarioDialog(parent=p), pai)
    assentar()

    assert pai.findChildren(FuncionarioDialog) == []
