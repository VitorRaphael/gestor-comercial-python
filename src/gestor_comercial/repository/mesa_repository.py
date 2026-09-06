from sqlalchemy import select

from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.repository.base import Repository


class MesaRepository(Repository[Mesa]):
    modelo = Mesa

    def listar_todos(self) -> list[Mesa]:
        return list(self.session.scalars(select(Mesa).order_by(Mesa.numero)))
