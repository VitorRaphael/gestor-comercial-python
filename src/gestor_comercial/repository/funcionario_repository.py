from sqlalchemy import select

from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.repository.base import Repository


class FuncionarioRepository(Repository[Funcionario]):
    modelo = Funcionario

    def listar_ativos(self) -> list[Funcionario]:
        stmt = select(Funcionario).where(Funcionario.ativo.is_(True)).order_by(Funcionario.nome)
        return list(self.session.scalars(stmt))
