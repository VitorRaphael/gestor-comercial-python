"""Identidade mostrada nos cabeçalhos do shell (barra de usuário, breadcrumbs
das telas administrativas): "Caixa Turno - Noite" enquanto há um turno
aberto — o rótulo passa a nomear a OPERAÇÃO, não a pessoa (§3.1), e some a
necessidade de mostrar o nome de quem logou como identificador principal.
Sem turno aberto não há período pra nomear, então cai no fallback antigo
(perfil · nome de quem está logado).

Função pura de UI compartilhada entre `MainWindow` e as views que montam seu
próprio breadcrumb (`FuncionariosView`) — cada uma recalcula isto nos seus
próprios pontos de atualização (login, navegação, `atualizar()`), não há
notificação ao vivo de abertura/fechamento de caixa no meio da sessão.
"""

from __future__ import annotations

from gestor_comercial.domain.enums import PerfilUsuario
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
