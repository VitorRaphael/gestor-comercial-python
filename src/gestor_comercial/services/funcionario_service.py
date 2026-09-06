"""CRUD do funcionário de atendimento (garçom, cozinha, ...), sem login (§3.11).

Separado de `AuthService`/`Usuario` de propósito: `Funcionario` não loga, só
serve para vincular quem atendeu a comanda e para consumo interno. Cadastrar,
editar, (des)ativar e excluir são ações administrativas — exigem gerente
logado, mesmo padrão de `AuthService.criar_usuario`.
"""

from __future__ import annotations

from gestor_comercial.domain.enums import CargoFuncionario
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.domain.usuario import Usuario
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.exceptions import (
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.transacao import transacional

CARGOS_VALIDOS = [cargo.value for cargo in CargoFuncionario]


@transacional
class FuncionarioService:
    """Cadastro, edição, (des)ativação e exclusão de funcionários de atendimento."""

    def __init__(self, uow: UnitOfWork, auth: AuthService) -> None:
        self.uow = uow
        self.auth = auth

    def criar(self, nome: str, cargo: str | None = None, telefone: str | None = None) -> Funcionario:
        self.auth.exigir_gerente()
        nome_limpo = self._validar_nome(nome)
        cargo_valido = self._validar_cargo(cargo)

        funcionario = Funcionario(
            nome=nome_limpo,
            cargo=cargo_valido,
            telefone=self._limpar_texto(telefone),
            ativo=True,
        )
        self.uow.funcionarios.salvar(funcionario)
        self.uow.commit()
        return funcionario

    def editar(
        self,
        funcionario_id: int,
        nome: str,
        cargo: str | None = None,
        telefone: str | None = None,
    ) -> Funcionario:
        self.auth.exigir_gerente()
        funcionario = self.buscar(funcionario_id)

        funcionario.nome = self._validar_nome(nome)
        funcionario.cargo = self._validar_cargo(cargo)
        funcionario.telefone = self._limpar_texto(telefone)
        self.uow.funcionarios.salvar(funcionario)
        self.uow.commit()
        return funcionario

    def listar_ativos(self) -> list[Funcionario]:
        return self.uow.funcionarios.listar_ativos()

    def listar_todos(self) -> list[Funcionario]:
        return self.uow.funcionarios.listar_todos()

    def listar_operadores_caixa(self) -> list[Usuario]:
        """`Usuario` de login (§ pills de filtro do Histórico Diário/Dashboard
        Mensal) que correspondem a um `Funcionario` ativo com cargo Caixa —
        casados por nome, já que não há FK entre as duas tabelas (§ decisão
        de manter `Usuario`/`Funcionario` separados, ver `d23a4f888a77`).

        Generaliza pra qualquer Caixa cadastrado no futuro, não só os dois
        turnos de bootstrap: qualquer `Funcionario` com `cargo == "Caixa"` e
        `ativo == True` que tenha um `Usuario` de login com o mesmo nome
        aparece aqui.
        """
        nomes_caixa = {
            f.nome for f in self.listar_ativos() if f.cargo == CargoFuncionario.CAIXA.value
        }
        return [u for u in self.auth.listar_ativos() if u.nome in nomes_caixa]

    def buscar(self, funcionario_id: int) -> Funcionario:
        funcionario = self.uow.funcionarios.buscar_por_id(funcionario_id)
        if funcionario is None:
            raise RecursoNaoEncontradoError(f"Funcionário não encontrado (código {funcionario_id}).")
        return funcionario

    def desativar(self, funcionario_id: int) -> Funcionario:
        self.auth.exigir_gerente()
        funcionario = self.buscar(funcionario_id)
        if not funcionario.ativo:
            raise RegraDeNegocioError(f"O funcionário {funcionario.nome} já está desativado.")
        funcionario.ativo = False
        self.uow.funcionarios.salvar(funcionario)
        self.uow.commit()
        return funcionario

    def ativar(self, funcionario_id: int) -> Funcionario:
        self.auth.exigir_gerente()
        funcionario = self.buscar(funcionario_id)
        if funcionario.ativo:
            raise RegraDeNegocioError(f"O funcionário {funcionario.nome} já está ativo.")
        funcionario.ativo = True
        self.uow.funcionarios.salvar(funcionario)
        self.uow.commit()
        return funcionario

    def excluir(self, funcionario_id: int) -> None:
        """Exclusão física. Se houver histórico vinculado (comanda atendida,
        consumo interno), bloqueia e sugere desativar — apagar destruiria
        registro de venda/dívida já gravado."""
        self.auth.exigir_gerente()
        funcionario = self.buscar(funcionario_id)

        tem_historico = bool(
            funcionario.comandas_atendidas
            or funcionario.quitacoes
            or funcionario.pagamentos_consumo
        )
        if tem_historico:
            raise RegraDeNegocioError(
                f"{funcionario.nome} já tem histórico de atendimento ou consumo interno "
                "e não pode ser excluído. Desative-o em vez de excluir."
            )

        self.uow.funcionarios.remover(funcionario)
        self.uow.commit()

    @staticmethod
    def _validar_nome(nome: str) -> str:
        nome_limpo = nome.strip() if isinstance(nome, str) else ""
        if not nome_limpo:
            raise RegraDeNegocioError("Informe o nome do funcionário.")
        return nome_limpo

    @staticmethod
    def _validar_cargo(cargo: str | None) -> str | None:
        """Cargo é opcional (compatibilidade com cadastros antigos sem
        função definida), mas se informado tem que ser uma das opções fixas
        do dropdown (§3.13) — não é mais texto livre."""
        cargo_limpo = FuncionarioService._limpar_texto(cargo)
        if cargo_limpo is None:
            return None
        if cargo_limpo not in CARGOS_VALIDOS:
            opcoes = ", ".join(CARGOS_VALIDOS)
            raise RegraDeNegocioError(f"Cargo inválido. Escolha uma das opções: {opcoes}.")
        return cargo_limpo

    @staticmethod
    def _limpar_texto(texto: str | None) -> str | None:
        if not isinstance(texto, str):
            return None
        return texto.strip() or None
