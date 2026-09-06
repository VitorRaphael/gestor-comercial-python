"""Ciclo de vida dos diálogos modais.

Ver `REMASTERIZACAO-V1.md` §3.2 — **e a correção do §3.2 registrada na Fase 3**.

Um modal é criado com a view como parent, e **quem detém a posse é o parent, em
C++**: soltar o nome Python não destrói nada. Como as dez telas são montadas no
boot e vivem o processo inteiro (`main_window.py:138-182`), um diálogo que fique
pendurado fica até o app fechar.

O §3.2 dizia que os 31 modais do app nunca são destruídos. Remedido na Fase 3
com PySide6 6.11.2 e um laço de eventos rodando de verdade (`app.exec()`), tanto
na plataforma `offscreen` quanto na `windows`:

    30 diálogos construídos e fechados com `reject()`, sem `exec()`: 30 presos
    30 diálogos abertos com `exec()` — o caminho real do app:         0 presos

Ou seja: o vazamento existe, mas no caminho que **só a bancada de medição
percorria**. Abrir de verdade, com `exec()`, já libera o diálogo. O que este
módulo entrega é garantia explícita em vez de dependência de um detalhe de
implementação do Qt — e é barato o bastante para valer como cinto de segurança
numa máquina que vai ficar semanas ligada.

## Por que não `WA_DeleteOnClose`

Vários modais são **lidos depois** do `exec()`: `modal.resultado()`,
`modal.comanda_fechada`, `caixa.clickedButton()`. Com `WA_DeleteOnClose` o
objeto C++ já estaria destruído nessa leitura, e o app quebraria com
`RuntimeError`. Fora que `accept()`/`reject()` passam por `done()`, que faz
`hide()`, não `close()` — o atributo nem dispararia.

A correção certa é liberar **depois** de ler o resultado, e é isso que o
`try/finally` daqui garante. `deleteLater()` só age quando o controle volta ao
laço de eventos, então ler `modal.qualquer_coisa` na linha seguinte continua
sendo seguro.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog
from shiboken6 import isValid


def executar_modal(modal: QDialog) -> int:
    """Abre o modal, devolve o código de saída e descarta a instância.

    Uso:

        if executar_modal(CancelamentoDialog(titulo, self)) != QDialog.DialogCode.Accepted:
            return

    Quando o resultado precisa ser lido, guarde o modal numa variável — a
    leitura depois do `exec()` continua válida:

        modal = CancelamentoDialog(titulo, self)
        if executar_modal(modal) == QDialog.DialogCode.Accepted:
            motivo = modal.resultado()
    """
    try:
        return modal.exec()
    finally:
        descartar_modal(modal)


def descartar_modal(modal: QDialog) -> None:
    """Descarte avulso, para o modal que é **reaproveitado** entre aberturas.

    `cardapio_view` usa `while modal.exec() == Accepted:` com a mesma instância
    em todas as voltas. Ali `executar_modal` destruiria o modal na primeira
    iteração e a segunda estouraria: o descarte tem que ficar **fora** do laço,
    e é para esse caso que esta função existe.
    """
    # `deleteLater()` num objeto cujo lado C++ já morreu levanta RuntimeError.
    # Como esta chamada mora num `finally`, esse erro substituiria a exceção
    # original e o operador veria um estouro de shiboken no lugar da mensagem
    # de verdade — ou, pior, o app cairia no balcão por causa da LIMPEZA. O
    # `isValid` é a diferença entre "não havia o que liberar" e um travamento.
    if isValid(modal):
        modal.deleteLater()
