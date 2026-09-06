"""Autenticação por PIN, sessão em memória e cadastro de usuários de login.

Porte de PinHashService.java e SessaoService.java. No Java a sessão era um
mapa token -> usuário porque havia HTTP no meio; aqui é um único processo
desktop com um usuário por vez, então a "sessão" é uma variável de instância
deste service (§3.1 da arquitetura).

`Usuario` é só quem loga (ADMIN/GERENTE/OPERADOR_CAIXA) — o CRUD de
`Funcionario` (atendimento, sem login) vive em `FuncionarioService`.

PIN pessoal por usuário foi REMOVIDO (§3.13, unificação da cascata de 3
níveis): `Usuario` não guarda mais `pin_hash`/`salt` — quem valida o PIN
agora é sempre `LojaConfigService`, contra os 3 segredos da loja (Senha de
Login, Senha Operacional, Senha Master). `Usuario` só identifica QUEM está
logando (`login_como`, escolhido no dropdown da tela) e o `perfil` usado por
`exigir_gerente()`. Ver `validar_pin_nivel` para a cascata genérica.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.domain.usuario import Usuario
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.transacao import transacional

TAMANHO_SALT_BYTES = 16
PIN_MAX_DIGITOS = 8

# Perfis que passam em `exigir_gerente()`: ADMIN é superset de GERENTE.
_PERFIS_GERENCIAIS = {PerfilUsuario.ADMIN, PerfilUsuario.GERENTE}


@transacional
class AuthService:
    """Hash de PIN, sessão do usuário logado e CRUD de usuários de login."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self._usuario_logado: Usuario | None = None
        # Import tardio, e é obrigatório: `loja_config_service` importa
        # `AuthService` NO NÍVEL DE MÓDULO (linha 29 de lá, para os métodos
        # estáticos de hash), então subir este import para o topo fecha o ciclo
        # e o app não abre — `ImportError: cannot import name 'AuthService'
        # from partially initialized module`. Já houve aqui um comentário
        # dizendo o contrário; ele convidava exatamente a essa "limpeza" (§3.12).
        from gestor_comercial.services.loja_config_service import LojaConfigService

        self.loja_config = LojaConfigService(uow)

    # ------------------------------------------------------------------
    # Hash do PIN (porte de PinHashService.java)
    # ------------------------------------------------------------------
    # O esquema é SHA-256 sobre (salt em bytes + pin em bytes), salt de 16
    # bytes aleatórios, tudo trafegando em Base64. Tem que bater bit a bit
    # com repository/seed.py, senão o "Gerente" criado no primeiro boot não
    # consegue logar. Sem bcrypt de propósito: o mesmo motivo do Java — um PIN
    # de 6 dígitos não ganha nada com KDF lento num app local sem rede.

    @staticmethod
    def gerar_salt() -> str:
        return base64.b64encode(os.urandom(TAMANHO_SALT_BYTES)).decode()

    @staticmethod
    def hash_pin(pin: str, salt: str) -> str:
        salt_bytes = base64.b64decode(salt)
        digest = hashlib.sha256(salt_bytes + pin.encode()).digest()
        return base64.b64encode(digest).decode()

    @staticmethod
    def confere_pin(pin: str, salt: str, hash_esperado: str) -> bool:
        try:
            calculado = AuthService.hash_pin(pin, salt)
        except ValueError:
            # Salt corrompido no banco: este usuário simplesmente não
            # autentica, mas o login dos outros continua funcionando.
            return False
        # compare_digest em vez de == para o tempo da comparação não revelar
        # quantos caracteres do hash já bateram.
        return hmac.compare_digest(calculado, hash_esperado)

    # ------------------------------------------------------------------
    # Sessão em memória (porte de SessaoService.java)
    # ------------------------------------------------------------------

    @property
    def usuario_logado(self) -> Usuario | None:
        return self._usuario_logado

    def login_como(self, usuario_id: int, pin: str) -> Usuario:
        """Login quando a tela já sabe QUEM está tentando entrar (dropdown de
        operador escolhido antes do PIN, ver `LoginView`). O PIN não é mais
        pessoal (§3.13): qualquer um dos 3 níveis da cascata da loja
        (`validar_pin_nivel`, mínimo Nível 1 — Senha de Login) desbloqueia o
        terminal para o operador ESCOLHIDO no dropdown — a identidade vem da
        seleção, não do PIN, então dois operadores (ex.: Caixa Turno -
        Manhã/Noite) compartilhando a mesma senha continuam sendo
        distinguíveis corretamente no `aberto_por_id`/`fechado_por_id`
        gravado no caixa.
        """
        usuario = self.buscar_usuario(usuario_id)
        if not usuario.ativo:
            raise NaoAutorizadoError("Este usuário está inativo.")
        if not self.validar_pin_nivel(pin, nivel_minimo=1):
            raise NaoAutorizadoError("PIN inválido.")
        self._usuario_logado = usuario
        return usuario

    def logout(self) -> None:
        self._usuario_logado = None

    def usuario_atual(self) -> Usuario:
        if self._usuario_logado is None:
            raise NaoAutorizadoError("Nenhum usuário logado. Faça login para continuar.")
        return self._usuario_logado

    def exigir_gerente(self) -> Usuario:
        """Porta de entrada das ações administrativas de §3.1, usada pelos outros services."""
        usuario = self.usuario_atual()
        if usuario.perfil not in _PERFIS_GERENCIAIS:
            raise AcessoNegadoError("Esta ação só pode ser feita por um gerente.")
        return usuario

    # ------------------------------------------------------------------
    # Usuários de login (porte de FuncionarioService.java)
    # ------------------------------------------------------------------

    def criar_usuario(self, nome: str, perfil: PerfilUsuario) -> Usuario:
        # Ação administrativa (§3.1) — exige gerente, com uma exceção: o
        # cadastro do primeiro gerente do sistema (feito pelo seed no boot,
        # ou manualmente se o seed não rodou) não tem quem autorizar ainda.
        # Passado esse bootstrap, todo cadastro exige gerente logado.
        if self.uow.usuarios.contar_ativos_por_perfil(PerfilUsuario.GERENTE) > 0:
            self.exigir_gerente()

        nome_limpo = nome.strip() if isinstance(nome, str) else ""
        if not nome_limpo:
            raise RegraDeNegocioError("Informe o nome do usuário.")
        if not isinstance(perfil, PerfilUsuario):
            raise RegraDeNegocioError("Selecione o perfil do usuário: Admin, Gerente ou Operador de Caixa.")

        # Sem PIN pessoal (§3.13): a identidade de login vem da seleção no
        # dropdown (`login_como`), não de um PIN próprio, então não há mais
        # checagem de "PIN já em uso" aqui.
        usuario = Usuario(
            nome=nome_limpo,
            perfil=perfil,
            ativo=True,
        )
        self.uow.usuarios.salvar(usuario)
        self.uow.commit()
        return usuario

    def listar_ativos(self) -> list[Usuario]:
        return self.uow.usuarios.listar_ativos()

    def listar_todos(self) -> list[Usuario]:
        return self.uow.usuarios.listar_todos()

    def buscar_usuario(self, usuario_id: int) -> Usuario:
        usuario = self.uow.usuarios.buscar_por_id(usuario_id)
        if usuario is None:
            raise RecursoNaoEncontradoError(f"Usuário não encontrado (código {usuario_id}).")
        return usuario

    def desativar_usuario(self, usuario_id: int) -> Usuario:
        self.exigir_gerente()  # ação administrativa (§3.1)
        usuario = self.buscar_usuario(usuario_id)
        if not usuario.ativo:
            raise RegraDeNegocioError(f"O usuário {usuario.nome} já está desativado.")

        # Sem nenhum gerente ativo ninguém mais autoriza cancelamento nem abre
        # caixa, e não existe tela de recuperação: o sistema trava de vez.
        # Por isso o último gerente não pode ser desativado nem por engano.
        if (
            usuario.perfil is PerfilUsuario.GERENTE
            and self.uow.usuarios.contar_ativos_por_perfil(PerfilUsuario.GERENTE) <= 1
        ):
            raise RegraDeNegocioError(
                "Não é possível desativar o último gerente ativo. "
                "Cadastre outro gerente antes de desativar este."
            )

        usuario.ativo = False
        self.uow.usuarios.salvar(usuario)
        self.uow.commit()
        return usuario

    # ------------------------------------------------------------------
    # Cascata de PIN da loja (§3.13)
    # ------------------------------------------------------------------
    # Nível 3 (Master/Dono) > Nível 2 (Operacional/Caixa) > Nível 1 (Login).
    # Quem digita o PIN de um nível autentica também onde um nível MENOR é
    # pedido — por isso a busca sempre começa no topo (3) e desce até
    # `nivel_minimo`, parando no primeiro que confere.

    _VERIFICADORES_POR_NIVEL = {
        3: "senha_master_confere",
        2: "senha_operacional_confere",
        1: "senha_login_confere",
    }

    def validar_pin_nivel(self, pin: str, nivel_minimo: int) -> bool:
        """`True` se `pin` confere com a Senha Master, Operacional OU de
        Login da loja — na ordem certa para que um nível mais alto sempre
        autentique onde um mais baixo é exigido. `nivel_minimo` é o piso: 1
        aceita qualquer um dos 3, 2 aceita Operacional ou Master, 3 só
        aceita Master."""
        if not isinstance(pin, str) or not pin:
            return False
        for nivel in range(3, nivel_minimo - 1, -1):
            verificador = getattr(self.loja_config, self._VERIFICADORES_POR_NIVEL[nivel])
            if verificador(pin):
                return True
        return False

    def validar_pin_gerente(self, pin: str) -> Usuario:
        """Reautenticação para ação crítica (Nível 2 — Caixa/Autorizações):
        confere o PIN contra a cascata (Operacional ou Master, §3.13) e
        devolve quem autoriza para efeito de auditoria
        (`cancelado_por_id`/`autorizado_por_id`) — como o PIN não é mais
        pessoal de ninguém (removido de `Usuario`), quem "autorizou" é
        sempre o usuário que já estava logado operando o turno, não um
        gerente identificado pelo PIN em si.
        """
        if not self.validar_pin_nivel(pin, nivel_minimo=2):
            raise NaoAutorizadoError("PIN inválido.")
        return self.usuario_atual()

    def validar_pin_dono(self, pin: str) -> Usuario:
        """Reautenticação para a Central de Loja (Nível 3 — Master/Dono, ver
        `LojaPinDialog`): só a Senha Master autentica, sem herdar de baixo
        pra cima (o inverso da cascata normal não existe)."""
        if not self.validar_pin_nivel(pin, nivel_minimo=3):
            raise NaoAutorizadoError("PIN inválido.")
        return self.usuario_atual()
