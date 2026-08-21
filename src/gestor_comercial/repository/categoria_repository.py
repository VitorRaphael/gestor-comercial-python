from sqlalchemy import select

from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.repository.base import Repository


class CategoriaRepository(Repository[Categoria]):
    modelo = Categoria

    def buscar_por_nome(self, nome: str) -> Categoria | None:
        return self.session.scalars(select(Categoria).where(Categoria.nome == nome)).first()

    def listar_todos(self) -> list[Categoria]:
        return list(self.session.scalars(select(Categoria).order_by(Categoria.nome)))

    def listar_ativas(self) -> list[Categoria]:
        stmt = select(Categoria).where(Categoria.ativo.is_(True)).order_by(Categoria.nome)
        return list(self.session.scalars(stmt))
