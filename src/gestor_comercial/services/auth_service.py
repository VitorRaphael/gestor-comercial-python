"""Autenticação por PIN, sessão em memória e cadastro de funcionários.

Porte de PinHashService.java, SessaoService.java e FuncionarioService.java.
No Java a sessão era um mapa token -> funcionário porque havia HTTP no meio;
aqui é um único processo desktop com um usuário por vez, então a "sessão" é
uma variável de instância deste service (§3.1 da arquitetura).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from gestor_comercial.domain.enums import PerfilFuncionario
from gestor_comercial.domain.funcionario import Funcionario
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


class AuthService:
    """Hash de PIN, sessão do funcionário logado e CRUD de funcionários."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self._usuario_logado: Funcionario | None = None

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
            # Salt corrompido no banco: este funcionário simplesmente não
            # autentica, mas o login dos outros continua funcionando.
            return False
        # compare_digest em vez de == para o tempo da comparação não revelar
        # quantos caracteres do hash já bateram.
        return hmac.compare_digest(calculado, hash_esperado)

    # ------------------------------------------------------------------
    # Sessão em memória (porte de SessaoService.java)
    # ------------------------------------------------------------------

    @property
    def usuario_logado(self) -> Funcionario | None:
        return self._usuario_logado

    def login(self, pin: str) -> Funcionario:
        funcionario = self.autenticar_por_pin(pin)
        self._usuario_logado = funcionario
        return funcionario

    def logout(self) -> None:
        self._usuario_logado = None

    def usuario_atual(self) -> Funcionario:
        if self._usuario_logado is None:
            raise NaoAutorizadoError("Nenhum funcionário logado. Faça login para continuar.")
        return self._usuario_logado

    def exigir_gerente(self) -> Funcionario:
        """Porta de entrada das ações administrativas de §3.1, usada pelos outros services."""
        funcionario = self.usuario_atual()
        if funcionario.perfil is not PerfilFuncionario.GERENTE:
            raise AcessoNegadoError("Esta ação só pode ser feita por um gerente.")
        return funcionario

    # ------------------------------------------------------------------
    # Funcionários (porte de FuncionarioService.java)
    # ------------------------------------------------------------------

    def criar_funcionario(self, nome: str, pin: str, perfil: PerfilFuncionario) -> Funcionario:
        # Ação administrativa (§3.1) — exige gerente, com uma exceção: o
        # cadastro do primeiro gerente do sistema (feito pelo seed no boot,
        # ou manualmente se o seed não rodou) não tem quem autorizar ainda.
        # Passado esse bootstrap, todo cadastro exige gerente logado.
        if self.uow.funcionarios.contar_ativos_por_perfil(PerfilFuncionario.GERENTE) > 0:
            self.exigir_gerente()

        nome_limpo = nome.strip() if isinstance(nome, str) else ""
        if not nome_limpo:
            raise RegraDeNegocioError("Informe o nome do funcionário.")
        if not isinstance(perfil, PerfilFuncionario):
            raise RegraDeNegocioError("Selecione o perfil do funcionário: Atendente ou Gerente.")
        self._validar_formato_pin(pin)

        # O PIN é a identidade do funcionário na tela de login (não há usuário),
        # então dois ativos com o mesmo PIN fariam a venda ser lançada no nome
        # de quem o banco devolvesse primeiro. Inativos podem repetir: o PIN de
        # um funcionário que saiu fica livre pro próximo.
        if any(
            self.confere_pin(pin, f.salt, f.pin_hash) for f in self.uow.funcionarios.listar_ativos()
        ):
            raise RegraDeNegocioError("Este PIN já está em uso por outro funcionário ativo.")

        salt = self.gerar_salt()
        funcionario = Funcionario(
            nome=nome_limpo,
            salt=salt,
            pin_hash=self.hash_pin(pin, salt),
            perfil=perfil,
            ativo=True,
        )
        self.uow.funcionarios.salvar(funcionario)
        self.uow.commit()
        return funcionario

    def listar_ativos(self) -> list[Funcionario]:
        return self.uow.funcionarios.listar_ativos()

    def listar_todos(self) -> list[Funcionario]:
        return self.uow.funcionarios.listar_todos()

    def buscar_funcionario(self, funcionario_id: int) -> Funcionario:
        funcionario = self.uow.funcionarios.buscar_por_id(funcionario_id)
        if funcionario is None:
            raise RecursoNaoEncontradoError(f"Funcionário não encontrado (código {funcionario_id}).")
        return funcionario

    def desativar_funcionario(self, funcionario_id: int) -> Funcionario:
        self.exigir_gerente()  # ação administrativa (§3.1)
        funcionario = self.buscar_funcionario(funcionario_id)
        if not funcionario.ativo:
            raise RegraDeNegocioError(f"O funcionário {funcionario.nome} já está desativado.")

        # Sem nenhum gerente ativo ninguém mais autoriza cancelamento nem abre
        # caixa, e não existe tela de recuperação: o sistema trava de vez.
        # Por isso o último gerente não pode ser desativado nem por engano.
        if (
            funcionario.perfil is PerfilFuncionario.GERENTE
            and self.uow.funcionarios.contar_ativos_por_perfil(PerfilFuncionario.GERENTE) <= 1
        ):
            raise RegraDeNegocioError(
                "Não é possível desativar o último gerente ativo. "
                "Cadastre outro gerente antes de desativar este."
            )

        funcionario.ativo = False
        self.uow.funcionarios.salvar(funcionario)
        self.uow.commit()
        return funcionario

    def autenticar_por_pin(self, pin: str) -> Funcionario:
        """Descobre de quem é o PIN, sem mexer na sessão."""
        if not isinstance(pin, str) or not pin:
            raise NaoAutorizadoError("Digite o PIN para continuar.")
        for funcionario in self.uow.funcionarios.listar_ativos():
            if self.confere_pin(pin, funcionario.salt, funcionario.pin_hash):
                return funcionario
        raise NaoAutorizadoError("PIN inválido.")

    def validar_pin_gerente(self, pin: str) -> Funcionario:
        """Reautenticação para ação crítica: confere o PIN e devolve quem autorizou,
        mantendo na sessão o atendente que estava operando (§3.1)."""
        funcionario = self.autenticar_por_pin(pin)
        if funcionario.perfil is not PerfilFuncionario.GERENTE:
            raise AcessoNegadoError("O PIN informado não é de um gerente.")
        return funcionario

    # ------------------------------------------------------------------

    @staticmethod
    def _validar_formato_pin(pin: str) -> None:
        # Só dígito ASCII: o teclado da tela de login é numérico, então um PIN
        # com letra (ou com dígito unicode colado de fora) nunca mais poderia
        # ser digitado de volta pelo funcionário.
        if not isinstance(pin, str) or not pin.isascii() or not pin.isdigit():
            raise RegraDeNegocioError("O PIN deve conter apenas números.")
        if not PIN_MIN_DIGITOS <= len(pin) <= PIN_MAX_DIGITOS:
            raise RegraDeNegocioError(
                f"O PIN deve ter de {PIN_MIN_DIGITOS} a {PIN_MAX_DIGITOS} dígitos."
            )
