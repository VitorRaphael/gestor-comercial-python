"""Fecha a fronteira transacional dos services — `REMASTERIZACAO-V1.md` §3.1.

O `UnitOfWork` sempre prometeu, na própria docstring, que uma operação é
tudo-ou-nada: `commit()` no fim do service, `rollback()` se qualquer regra
estourar. A primeira metade existia; a segunda não. `rollback()` só era chamado
em `UnitOfWork.__exit__`, e `with UnitOfWork(...)` não aparecia em lugar nenhum
do projeto — nem no `main.py`, nem nos testes. Na prática, **nenhum caminho de
produção fazia rollback**.

Sem ele, uma operação recusada por regra de negócio deixava as alterações já
aplicadas penduradas na Session, e o `commit()` da operação **seguinte** —
qualquer uma, sem relação nenhuma — gravava tudo junto. Ver o caso reproduzido
em `tests/unit/test_integridade_transacional.py`.

## Por que "só se houver pendência", e não em toda exceção

A primeira ideia — desfazer em qualquer exceção — quebraria o app, porque este
projeto usa exceção como **fluxo normal** em dois lugares:

1. A cascata de 3 níveis de PIN (§3.13): `senha_master_confere` chama
   `validar_senha_master` e captura `AcessoNegadoError` para devolver `False`.
   Digitar a senha errada é evento rotineiro do balcão, não falha de operação.
2. A blindagem da impressão: `impressao_service` captura `Exception` de
   propósito, para a impressora com defeito nunca derrubar a venda junto.

Por isso a regra aqui é mais estreita e mais precisa: **desfaz apenas se a
operação estiver saindo com alterações não gravadas**. Uma senha errada sai com
a Session limpa (nada foi mutado) e não dispara nada. Uma edição rejeitada no
meio do caminho sai suja — e é exatamente essa que precisa ser descartada.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from sqlalchemy.orm import Session

TipoClasse = TypeVar("TipoClasse", bound=type)


def _tem_alteracao_pendente(session: Session) -> bool:
    """A operação está saindo com trabalho não gravado na Session?

    `dirty` pode acusar objeto que no fim não mudou nada — falso positivo do
    SQLAlchemy. Aqui isso não é problema: só chegamos neste ponto com uma
    exceção em curso, então a operação falhou de todo jeito e não há trabalho
    legítimo a preservar.
    """
    return bool(session.new or session.dirty or session.deleted)


def _com_rollback(metodo: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(metodo)
    def envolvido(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return metodo(self, *args, **kwargs)
        except Exception:
            uow = getattr(self, "uow", None)
            if uow is not None and _tem_alteracao_pendente(uow.session):
                uow.rollback()
            raise

    return envolvido


def transacional(cls: TipoClasse) -> TipoClasse:
    """Faz todo método público da classe devolver a Session limpa ao falhar.

    Aplicado nas classes de service (as que têm `self.uow`). Os métodos
    privados ficam de fora de propósito: eles rodam *dentro* de uma operação
    pública, e desfazer no meio esconderia da operação externa que algo
    aconteceu. A fronteira é a chamada que a UI faz, não cada passo interno.

    Chamadas aninhadas entre services (ex.: `PagamentoService.registrar` chama
    `ComandaService.fechar`) funcionam: se a interna falhar, ela desfaz e a
    exceção sobe; quando a externa a recebe, a Session já está limpa e o
    `rollback()` dela vira um no-op.
    """
    for nome, atributo in list(vars(cls).items()):
        if nome.startswith("_"):
            continue
        # staticmethod/classmethod não recebem `self` e não tocam na Session;
        # `property` não é chamada como método. Nenhum dos três é fronteira de
        # operação.
        if isinstance(atributo, (staticmethod, classmethod, property)):
            continue
        if not callable(atributo):
            continue
        setattr(cls, nome, _com_rollback(atributo))
    return cls
