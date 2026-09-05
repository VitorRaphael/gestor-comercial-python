from sqlalchemy import func, select

from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.domain.usuario import Usuario
from gestor_comercial.repository.base import Repository


class UsuarioRepository(Repository[Usuario]):
    modelo = Usuario

    def listar_ativos(self) -> list[Usuario]:
        stmt = select(Usuario).where(Usuario.ativo.is_(True)).order_by(Usuario.nome)
        return list(self.session.scalars(stmt))

    def contar_ativos_por_perfil(self, perfil: PerfilUsuario) -> int:
        stmt = (
            select(func.count())
            .select_from(Usuario)
            .where(Usuario.ativo.is_(True), Usuario.perfil == perfil)
        )
        return self.session.scalar(stmt) or 0

    def buscar_por_nome(self, nome: str) -> Usuario | None:
        stmt = select(Usuario).where(Usuario.nome == nome)
        return self.session.scalars(stmt).first()
