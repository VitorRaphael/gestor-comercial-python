from sqlalchemy import func, select

from gestor_comercial.domain.enums import PerfilFuncionario
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.repository.base import Repository


class FuncionarioRepository(Repository[Funcionario]):
    modelo = Funcionario

    def listar_ativos(self) -> list[Funcionario]:
        stmt = select(Funcionario).where(Funcionario.ativo.is_(True)).order_by(Funcionario.nome)
        return list(self.session.scalars(stmt))

    def contar_ativos_por_perfil(self, perfil: PerfilFuncionario) -> int:
        stmt = (
            select(func.count())
            .select_from(Funcionario)
            .where(Funcionario.ativo.is_(True), Funcionario.perfil == perfil)
        )
        return self.session.scalar(stmt) or 0
