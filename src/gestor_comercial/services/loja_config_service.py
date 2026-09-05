"""Módulo "Senhas e Acesso" da Central de Loja (§3.13).

Três segredos, cada um só podendo ser alterado com o de "nível acima":
- Senha Operacional (Gerente) — usada no dia a dia para cancelamentos,
  estornos e sangrias. Alterá-la exige a Senha Master.
- Senha Master (Dono) — desbloqueia a própria Central de Loja e a troca da
  Senha Operacional. Alterá-la exige o CPF do Dono.
- CPF do Dono — chave mestra. Alterá-lo exige o CPF atual.

Nenhum valor é guardado em texto puro nem é recuperável: só hash+salt, igual
ao PIN de login (`AuthService.hash_pin`). A tela nunca mostra o valor real,
só `••••••••` — "ver o valor" não é uma operação que existe, só "confirmar
que bate" (para o desbloqueio) ou "definir um novo" (para a troca).
"""

from __future__ import annotations

from gestor_comercial.domain.loja_config import LojaConfig
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    RegraDeNegocioError,
)

SENHA_MASTER_PADRAO = "050727"
SENHA_OPERACIONAL_PADRAO = "26407200"

MASCARA = "••••••••"


class LojaConfigService:
    """Bootstrap e regras do módulo "Senhas e Acesso"."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def obter_ou_criar(self) -> LojaConfig:
        """Garante a linha singleton, criando com os padrões de fábrica na
        primeira vez que qualquer tela/serviço tocar no módulo."""
        config = self.uow.loja_config.obter()
        if config is not None:
            return config

        salt_master = AuthService.gerar_salt()
        salt_operacional = AuthService.gerar_salt()
        config = LojaConfig(
            senha_master_hash=AuthService.hash_pin(SENHA_MASTER_PADRAO, salt_master),
            senha_master_salt=salt_master,
            senha_operacional_hash=AuthService.hash_pin(SENHA_OPERACIONAL_PADRAO, salt_operacional),
            senha_operacional_salt=salt_operacional,
            cpf_dono_definido=False,
        )
        self.uow.loja_config.salvar(config)
        self.uow.commit()
        return config

    # ------------------------------------------------------------------
    # Validação (desbloqueio)
    # ------------------------------------------------------------------

    def validar_senha_master(self, senha: str) -> None:
        config = self.obter_ou_criar()
        if not self._confere(senha, config.senha_master_salt, config.senha_master_hash):
            raise AcessoNegadoError("Senha Master (Dono) incorreta.")

    def validar_senha_operacional(self, senha: str) -> None:
        config = self.obter_ou_criar()
        if not self._confere(senha, config.senha_operacional_salt, config.senha_operacional_hash):
            raise AcessoNegadoError("Senha Operacional (Gerente) incorreta.")

    def senha_operacional_confere(self, senha: str) -> bool:
        """Versão que não levanta erro — usada por quem aceita ESSA senha OU
        outra credencial como alternativa (ex.: PIN pessoal de gerente)."""
        try:
            self.validar_senha_operacional(senha)
            return True
        except AcessoNegadoError:
            return False

    def senha_master_confere(self, senha: str) -> bool:
        try:
            self.validar_senha_master(senha)
            return True
        except AcessoNegadoError:
            return False

    def validar_cpf_dono(self, cpf: str) -> None:
        config = self.obter_ou_criar()
        if not config.cpf_dono_definido or config.cpf_dono_hash is None:
            raise RegraDeNegocioError("O CPF do Dono ainda não foi cadastrado.")
        if not self._confere(cpf, config.cpf_dono_salt, config.cpf_dono_hash):
            raise AcessoNegadoError("CPF do Dono incorreto.")

    def cpf_dono_definido(self) -> bool:
        return self.obter_ou_criar().cpf_dono_definido

    # ------------------------------------------------------------------
    # Troca (cada uma exige o segredo de nível acima)
    # ------------------------------------------------------------------

    def alterar_senha_operacional(self, senha_master_atual: str, nova_senha: str) -> None:
        self.validar_senha_master(senha_master_atual)
        self._validar_formato(nova_senha, "Senha Operacional")
        config = self.obter_ou_criar()
        salt = AuthService.gerar_salt()
        config.senha_operacional_salt = salt
        config.senha_operacional_hash = AuthService.hash_pin(nova_senha, salt)
        self.uow.loja_config.salvar(config)
        self.uow.commit()

    def alterar_senha_master(self, cpf_dono_atual: str, nova_senha: str) -> None:
        self.validar_cpf_dono(cpf_dono_atual)
        self._validar_formato(nova_senha, "Senha Master")
        config = self.obter_ou_criar()
        salt = AuthService.gerar_salt()
        config.senha_master_salt = salt
        config.senha_master_hash = AuthService.hash_pin(nova_senha, salt)
        self.uow.loja_config.salvar(config)
        self.uow.commit()

    def definir_ou_alterar_cpf_dono(self, cpf_atual_ou_none: str | None, novo_cpf: str) -> None:
        """Primeiro cadastro (sem CPF ainda definido) não exige nada além de
        estar na tela de Senhas e Acesso — não há como exigir "o CPF atual"
        de algo que nunca existiu. A partir do segundo, exige o CPF atual."""
        config = self.obter_ou_criar()
        if config.cpf_dono_definido:
            if not cpf_atual_ou_none:
                raise RegraDeNegocioError("Informe o CPF atual do Dono para alterá-lo.")
            self.validar_cpf_dono(cpf_atual_ou_none)

        cpf_limpo = self._validar_cpf_formato(novo_cpf)
        salt = AuthService.gerar_salt()
        config.cpf_dono_salt = salt
        config.cpf_dono_hash = AuthService.hash_pin(cpf_limpo, salt)
        config.cpf_dono_definido = True
        self.uow.loja_config.salvar(config)
        self.uow.commit()

    # ------------------------------------------------------------------

    @staticmethod
    def _confere(valor: str, salt: str, hash_esperado: str) -> bool:
        if not isinstance(valor, str) or not valor:
            return False
        return AuthService.confere_pin(valor, salt, hash_esperado)

    @staticmethod
    def _validar_formato(senha: str, rotulo: str) -> None:
        if not isinstance(senha, str) or not senha.strip():
            raise RegraDeNegocioError(f"Informe a nova {rotulo}.")
        if len(senha.strip()) < 4:
            raise RegraDeNegocioError(f"A {rotulo} deve ter pelo menos 4 caracteres.")

    @staticmethod
    def _validar_cpf_formato(cpf: str) -> str:
        digitos = "".join(ch for ch in cpf if ch.isdigit()) if isinstance(cpf, str) else ""
        if len(digitos) != 11:
            raise RegraDeNegocioError("Informe um CPF válido, com 11 dígitos.")
        return digitos

    @staticmethod
    def mascarar(_valor_nunca_usado: str | None = None) -> str:
        return MASCARA
