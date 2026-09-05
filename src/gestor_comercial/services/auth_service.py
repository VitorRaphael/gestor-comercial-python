"""Autenticação por PIN, sessão em memória e cadastro de usuários de login.

Porte de PinHashService.java e SessaoService.java. No Java a sessão era um
mapa token -> usuário porque havia HTTP no meio; aqui é um único processo
desktop com um usuário por vez, então a "sessão" é uma variável de instância
deste service (§3.1 da arquitetura).

`Usuario` é só quem loga (ADMIN/GERENTE/OPERADOR_CAIXA) — o CRUD de
`Funcionario` (atendimento, sem login) vive em `FuncionarioService`.
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

TAMANHO_SALT_BYTES = 16
PIN_MIN_DIGITOS = 4
PIN_MAX_DIGITOS = 8

# Perfis que passam em `exigir_gerente()`: ADMIN é superset de GERENTE.
_PERFIS_GERENCIAIS = {PerfilUsuario.ADMIN, PerfilUsuario.GERENTE}


class AuthService:
    """Hash de PIN, sessão do usuário logado e CRUD de usuários de login."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self._usuario_logado: Usuario | None = None
        # Import tardio pra evitar ciclo (loja_config_service não importa
        # auth_service no nível de módulo, só usa os métodos estáticos).
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

    def login(self, pin: str) -> Usuario:
        usuario = self.autenticar_por_pin(pin)
        self._usuario_logado = usuario
        return usuario

    def login_como(self, usuario_id: int, pin: str) -> Usuario:
        """Login quando a tela já sabe QUEM está tentando entrar (dropdown de
        operador escolhido antes do PIN, ver `LoginView`) — autentica o PIN
        contra esse usuário específico, não contra "qualquer PIN que bata"
        (`login`/`autenticar_por_pin`).

        Necessário desde que operadores de turno passaram a poder
        compartilhar a mesma senha (§ Caixa Turno - Manhã/Noite, decisão do
        Vitor de usar a Senha Operacional como PIN dos dois): com `login()`,
        dois usuários ativos com PIN idêntico faziam a autenticação "resolver"
        sempre para o primeiro da lista, nunca para o que a pessoa realmente
        selecionou — o `aberto_por_id`/`fechado_por_id` gravado no caixa saía
        errado mesmo com PIN certo.
        """
        usuario = self.buscar_usuario(usuario_id)
        if not usuario.ativo:
            raise NaoAutorizadoError("Este usuário está inativo.")
        if not self.confere_pin(pin, usuario.salt, usuario.pin_hash):
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

    def criar_usuario(self, nome: str, pin: str, perfil: PerfilUsuario) -> Usuario:
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
        self._validar_formato_pin(pin)

        # O PIN é a identidade do usuário na tela de login, então dois ativos
        # com o mesmo PIN fariam a venda ser lançada no nome de quem o banco
        # devolvesse primeiro. Inativos podem repetir: o PIN de um usuário que
        # saiu fica livre pro próximo.
        if any(
            self.confere_pin(pin, u.salt, u.pin_hash) for u in self.uow.usuarios.listar_ativos()
        ):
            raise RegraDeNegocioError("Este PIN já está em uso por outro usuário ativo.")

        salt = self.gerar_salt()
        usuario = Usuario(
            nome=nome_limpo,
            salt=salt,
            pin_hash=self.hash_pin(pin, salt),
            perfil=perfil,
            ativo=True,
        )
        self.uow.usuarios.salvar(usuario)
        self.uow.commit()
        return usuario

    def validar_pin_gerente_ou_dono(self, senha: str) -> None:
        """Autoriza uma ação que aceita tanto quem já autoriza ações de
        gerente (`validar_pin_gerente`: PIN pessoal de GERENTE/ADMIN ou Senha
        Operacional da Central de Loja) quanto a Senha Master (Dono) —
        usado por ações mais sensíveis que dívida de consumo, como redefinir
        o PIN de login de um operador de Caixa (§ tela Funcionários)."""
        try:
            self.validar_pin_gerente(senha)
            return
        except (NaoAutorizadoError, AcessoNegadoError):
            pass
        if not self.loja_config.senha_master_confere(senha):
            raise AcessoNegadoError("Senha do Gerente ou do Dono incorreta.")

    def definir_pin_operador_caixa(
        self, nome_operador: str, novo_pin: str, perfil_padrao: PerfilUsuario = PerfilUsuario.GERENTE
    ) -> Usuario:
        """Cria (se ainda não existir) ou redefine o PIN de login do `Usuario`
        correspondente a um operador de Caixa, dado o nome do `Funcionario`
        (tela "Funcionários" > cargo Caixa > Editar senha, ver
        `funcionarios_view._DialogSenhaCaixa`).

        Quem chama este método já validou a Senha do Gerente/Dono
        (`LojaConfigService.senha_operacional_confere`/`senha_master_confere`)
        antes — a autorização acontece na UI, não aqui, mesmo padrão de
        `CaixaService.abrir` aceitando a senha de fechamento cego.

        Não passa pela checagem de "PIN já em uso por outro usuário ativo" de
        `criar_usuario`: aqui a duplicidade é intencional (Vitor, 2026-09-05
        — Caixa Turno - Manhã e Caixa Turno - Noite compartilham a Senha
        Operacional como PIN de login), não um descuido a ser bloqueado.
        """
        self._validar_formato_pin(novo_pin)
        usuario = self.uow.usuarios.buscar_por_nome(nome_operador)
        salt = self.gerar_salt()
        if usuario is None:
            usuario = Usuario(
                nome=nome_operador,
                salt=salt,
                pin_hash=self.hash_pin(novo_pin, salt),
                perfil=perfil_padrao,
                ativo=True,
            )
        else:
            usuario.salt = salt
            usuario.pin_hash = self.hash_pin(novo_pin, salt)
            usuario.ativo = True
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

    def autenticar_por_pin(self, pin: str) -> Usuario:
        """Descobre de quem é o PIN, sem mexer na sessão."""
        if not isinstance(pin, str) or not pin:
            raise NaoAutorizadoError("Digite o PIN para continuar.")
        for usuario in self.uow.usuarios.listar_ativos():
            if self.confere_pin(pin, usuario.salt, usuario.pin_hash):
                return usuario
        raise NaoAutorizadoError("PIN inválido.")

    def validar_pin_gerente(self, pin: str) -> Usuario:
        """Reautenticação para ação crítica: confere o PIN e devolve quem autorizou,
        mantendo na sessão o usuário que estava operando (§3.1).

        Aceita duas credenciais equivalentes (§3.13, decisão de substituir o
        PIN pessoal pela Senha Operacional compartilhada):
        1. O PIN pessoal de um usuário GERENTE/ADMIN (comportamento original).
        2. A Senha Operacional (Gerente) da Central de Loja — não é PIN de
           ninguém específico, então quem "autorizou" para efeito de
           auditoria (`cancelado_por_id`/`autorizado_por_id`) é quem estava
           logado operando o turno, não um gerente pessoal.
        """
        try:
            usuario = self.autenticar_por_pin(pin)
        except NaoAutorizadoError:
            usuario = None

        if usuario is not None:
            if usuario.perfil not in _PERFIS_GERENCIAIS:
                raise AcessoNegadoError("O PIN informado não é de um gerente.")
            return usuario

        if self.loja_config.senha_operacional_confere(pin):
            return self.usuario_atual()

        raise NaoAutorizadoError("PIN inválido.")

    # ------------------------------------------------------------------

    @staticmethod
    def _validar_formato_pin(pin: str) -> None:
        # Só dígito ASCII: o teclado da tela de login é numérico, então um PIN
        # com letra (ou com dígito unicode colado de fora) nunca mais poderia
        # ser digitado de volta pelo usuário.
        if not isinstance(pin, str) or not pin.isascii() or not pin.isdigit():
            raise RegraDeNegocioError("O PIN deve conter apenas números.")
        if not PIN_MIN_DIGITOS <= len(pin) <= PIN_MAX_DIGITOS:
            raise RegraDeNegocioError(
                f"O PIN deve ter de {PIN_MIN_DIGITOS} a {PIN_MAX_DIGITOS} dígitos."
            )
