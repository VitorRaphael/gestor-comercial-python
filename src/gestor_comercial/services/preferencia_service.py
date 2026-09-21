"""Preferências de tela que sobrevivem ao fechamento do programa.

Hoje é uma só: o tema. Até aqui o `ThemeController` guardava o tema só em
memória — o Vitor escolhia o Modo Claro em Configurações, fechava o programa e
ele reabria no Escuro, porque não existia gravação nenhuma para ler de volta.

A preferência mora na tabela `preferencias` (uma linha, chave `tema`), e não
num arquivo de configuração ao lado do `.exe`: o banco já tem `journal_mode=WAL`
com `synchronous=FULL` (§8), então a gravação é atômica e sobrevive a queda de
energia do mesmo jeito que uma venda; e a preferência viaja junto com a cópia
de segurança, que é uma cópia do `.db`. Um arquivo à parte seria um segundo
lugar para corromper e para esquecer no backup.

O service não conhece Qt (camada `services/` não importa `ui/`): quem aplica o
tema é o `ThemeController`, que recebe este service no boot como o lugar onde
ler e gravar (ver `ThemeController.restaurar`).
"""

from __future__ import annotations

from gestor_comercial.core.resilience import logger_do_app
from gestor_comercial.repository.preferencia_repository import TEMA, TEMA_CLARO, TEMA_ESCURO
from gestor_comercial.repository.unit_of_work import UnitOfWork

_TEMA_POR_VALOR = {TEMA_CLARO: True, TEMA_ESCURO: False}


class PreferenciaService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def tema_claro_gravado(self) -> bool | None:
        """`True` para claro, `False` para escuro, `None` se nunca foi escolhido.

        Valor que não seja um dos dois (só existe por edição manual do banco)
        também é `None`: o certo é o programa abrir no tema padrão, não
        estourar no boot por causa de uma preferência de tela.
        """
        return _TEMA_POR_VALOR.get(self.uow.preferencias.obter(TEMA) or "")

    def gravar_tema(self, claro: bool) -> None:
        """Grava o tema escolhido, com `commit` próprio — na hora do clique.

        O tema já mudou na tela quando isto roda, e uma falha aqui não pode
        desfazer a troca nem derrubar o clique: degrada para "na próxima
        abertura volta o tema anterior", com o motivo no `gestor.log`. É o
        mesmo contrato de `AuthService._lembrar_ultimo_operador`.
        """
        try:
            self.uow.preferencias.definir(TEMA, TEMA_CLARO if claro else TEMA_ESCURO)
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            logger_do_app().exception("Não foi possível gravar a preferência de tema")
