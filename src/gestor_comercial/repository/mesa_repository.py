from sqlalchemy import select

from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.repository.base import Repository


class MesaRepository(Repository[Mesa]):
    modelo = Mesa

    def buscar_por_numero(self, numero: int) -> Mesa | None:
        return self.session.scalars(select(Mesa).where(Mesa.numero == numero)).first()

    def listar_todos(self) -> list[Mesa]:
        return list(self.session.scalars(select(Mesa).order_by(Mesa.numero)))
