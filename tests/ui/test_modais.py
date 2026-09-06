"""`executar_modal()` — abrir, ler o resultado e liberar. Ver §3.2.

Um modal é criado com a view como parent, e quem detém a posse é o parent, em
C++. Como as dez telas vivem o processo inteiro, todo diálogo que não for
liberado explicitamente corre o risco de ficar pendurado até o app fechar.

A armadilha que estes testes protegem é a correção ERRADA: `WA_DeleteOnClose`
destruiria o objeto antes de o código de produção ler `modal.resultado()`,
`modal.comanda_fechada` ou `caixa.clickedButton()` — e o app quebraria com
`RuntimeError` em vez de vazar. Por isso existe
`test_o_resultado_continua_legivel_depois_de_executar`: ele é o teste que
proíbe a "otimização" mais tentadora deste módulo.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QWidget

from gestor_comercial.ui.views.cancelamento_dialog import CancelamentoDialog
from gestor_comercial.ui.widgets.modais import descartar_modal, executar_modal

ABERTURAS = 30


class _ModalFalso(QDialog):
    """Um modal que responde sem abrir janela nem laço de eventos.

    Existe para os testes de contrato: `exec()` de verdade bloqueia até alguém
    fechar o diálogo, e o que se quer verificar aqui é o que `executar_modal`
    faz **em volta** do `exec()`, não o `exec()` do Qt.
    """

    def __init__(self, pai: QWidget, codigo: int = QDialog.DialogCode.Accepted) -> None:
        super().__init__(pai)
        self._codigo = codigo
        self.vezes_executado = 0
        self.resultado = "motivo digitado pelo gerente"

    def exec(self) -> int:  # noqa: A003 (o nome é da API do Qt)
        self.vezes_executado += 1
        return self._codigo


def test_devolve_o_codigo_de_saida_do_exec(qapp):
    pai = QWidget()

    assert executar_modal(_ModalFalso(pai)) == QDialog.DialogCode.Accepted
    assert executar_modal(_ModalFalso(pai, QDialog.DialogCode.Rejected)) == (
        QDialog.DialogCode.Rejected
    )


def test_o_resultado_continua_legivel_depois_de_executar(qapp):
    """O padrão do código de produção: executa, e só então lê o que o usuário
    digitou. `deleteLater()` só age quando o controle volta ao laço de eventos,
    então esta leitura é segura — é justamente o que `WA_DeleteOnClose` quebraria.
    """
    view = QWidget()  # a view do app, que vive o processo inteiro
    modal = _ModalFalso(view)

    codigo = executar_modal(modal)

    assert codigo == QDialog.DialogCode.Accepted
    assert modal.resultado == "motivo digitado pelo gerente"


def test_nao_estoura_quando_o_modal_ja_foi_destruido(qapp, assentar):
    """Liberar duas vezes, ou liberar um modal que já morreu junto com o parent,
    não pode derrubar o app: `deleteLater()` sobre um objeto cujo lado C++ já
    se foi levanta `RuntimeError`.

    Como o descarte mora num `finally`, esse erro substituiria a exceção
    original — o operador veria um estouro de shiboken no lugar da mensagem de
    verdade. Cai direto no RNF "zero travamentos".
    """
    modal = _ModalFalso(QWidget())  # parent temporário: morre já no fim da linha
    assentar()

    descartar_modal(modal)  # não pode levantar


def test_libera_o_modal_mesmo_quando_o_exec_estoura(qapp, assentar):
    """O `finally` não é decoração: uma exceção de regra de negócio subindo de
    dentro do diálogo não pode deixar o objeto pendurado na view."""

    class _ModalQueEstoura(_ModalFalso):
        def exec(self) -> int:  # noqa: A003
            raise RuntimeError("falha no meio do diálogo")

    pai = QWidget()
    modal = _ModalQueEstoura(pai)

    try:
        executar_modal(modal)
    except RuntimeError:
        pass
    del modal
    assentar()

    assert pai.findChildren(_ModalQueEstoura) == []


def test_trinta_aberturas_nao_deixam_nada_no_parent(qapp, assentar):
    """A view é o parent e vive o processo inteiro. Depois de trinta idas e
    voltas não pode sobrar um único diálogo pendurado nela."""
    pai = QWidget()

    for _ in range(ABERTURAS):
        executar_modal(_ModalFalso(pai))
    assentar()

    vivos = pai.findChildren(QDialog)
    assert vivos == [], f"{len(vivos)} de {ABERTURAS} modais continuam presos ao parent"


def test_com_exec_de_verdade_o_dialogo_tambem_e_liberado(qapp, assentar):
    """O caminho completo, com o diálogo real do app e um laço de eventos de
    verdade: `CancelamentoDialog` aberto e fechado pelo Cancelar (`reject`),
    como o usuário faz.

    O `singleShot` é o teste fazendo o papel do dedo do usuário — o app não usa
    `QTimer` em lugar nenhum.
    """
    pai = QWidget()

    for _ in range(ABERTURAS):
        modal = CancelamentoDialog("Cancelar item", pai)
        QTimer.singleShot(0, modal.reject)
        executar_modal(modal)
        del modal
    assentar()

    assert pai.findChildren(CancelamentoDialog) == []


def test_descartar_modal_serve_ao_modal_reaproveitado(qapp, assentar):
    """`cardapio_view` usa `while modal.exec() == Accepted:` com a MESMA
    instância em todas as voltas. Ali `executar_modal` destruiria o diálogo na
    primeira iteração; o descarte tem que ficar fora do laço."""
    pai = QWidget()
    modal = _ModalFalso(pai)

    for _ in range(3):
        assert modal.exec() == QDialog.DialogCode.Accepted
    descartar_modal(modal)
    del modal
    assentar()

    assert pai.findChildren(_ModalFalso) == []
