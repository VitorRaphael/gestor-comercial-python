"""Identidade mostrada nos cabeçalhos do shell (barra de usuário, breadcrumbs
das telas administrativas): o nome do turno enquanto há um turno aberto — o
rótulo passa a nomear a OPERAÇÃO (§3.1), e o nome do turno é o do operador que
o abriu, como cadastrado em Funcionários (ver `caixa_service.nome_do_turno`).
Sem turno aberto não há turno para nomear, então cai no fallback antigo
(nome de quem está logado · perfil).

`rotulo_identidade` é a regra; `IdentidadeDoTurno` é a fonte única do valor
na tela. Antes cada consumidor recalculava por conta própria, em momentos
próprios (a `MainWindow` a cada navegação, a `FuncionariosView` no próprio
`atualizar()`), e nada avisava ninguém quando o turno abria, fechava ou mudava
de nome no meio da sessão — daí cabeçalhos com nomes diferentes para o mesmo
turno. Agora quem muda o que o rótulo lê avisa a `IdentidadeDoTurno`
(`recalcular`), e ela avisa todo mundo que mostra o rótulo (`rotulo_mudou`).

`rotulo_do_operador` é o outro rótulo de identidade: o sobrescrito das duas
telas de venda ("GERENTE · VITOR RAPHAEL"), que nomeia a PESSOA com a mão no
mouse e não depende de turno.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.domain.usuario import Usuario
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

_ROTULOS_PERFIL = {
    PerfilUsuario.ADMIN: "Admin",
    PerfilUsuario.GERENTE: "Gerente",
    PerfilUsuario.OPERADOR_CAIXA: "Operador de Caixa",
}


def rotulo_identidade(auth: AuthService, caixas: CaixaService) -> str:
    usuario = auth.usuario_logado
    if usuario is None:
        return ""
    try:
        caixa_aberto = caixas.buscar_aberto()
    except _ERROS_SERVICE:
        rotulo_perfil = _ROTULOS_PERFIL.get(usuario.perfil, usuario.perfil.value)
        return f"{usuario.nome} · {rotulo_perfil}"
    return caixas.identificacao_turno(caixa_aberto)


class IdentidadeDoTurno(QObject):
    """O rótulo de identidade vigente, e o aviso de quando ele muda.

    Quem MUDA o que o rótulo lê chama `recalcular`: login e logout (a
    `MainWindow`), abertura e fechamento de turno (`CaixaView.turno_alterado`)
    e cadastro de funcionário, que renomeia o login do par
    (`FuncionariosView.cadastro_alterado`). Quem MOSTRA o rótulo escuta
    `rotulo_mudou` — com método ligado, nunca `lambda` (§3.14).

    `rotulo_mudou` só é emitido quando o texto muda de fato: recalcular sem motivo
    custa uma consulta (`buscar_aberto`) e nenhuma repintura.
    """

    # Não se chama `mudou` de propósito: esse é o nome do sinal do tema, e a
    # varredura de `test_assinantes_do_tema` trata todo `.mudou.connect` como
    # assinante do `ThemeController`.
    rotulo_mudou = Signal(str)

    def __init__(
        self, auth: AuthService, caixas: CaixaService, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._auth = auth
        self._caixas = caixas
        self._rotulo = ""

    @property
    def rotulo(self) -> str:
        return self._rotulo

    def recalcular(self) -> None:
        rotulo = rotulo_identidade(self._auth, self._caixas)
        if rotulo == self._rotulo:
            return
        self._rotulo = rotulo
        self.rotulo_mudou.emit(rotulo)


def rotulo_do_operador(usuario: Usuario | None) -> str:
    """"GERENTE · VITOR RAPHAEL" — o sobrescrito das telas de venda (§9.25, §9.27).

    Morava dentro da tela de pagamento; saiu para cá quando a tela da mesa
    passou a escrever o mesmo sobrescrito, para as duas não divergirem.
    """
    return "" if usuario is None else f"{usuario.perfil.value} · {usuario.nome}".upper()
