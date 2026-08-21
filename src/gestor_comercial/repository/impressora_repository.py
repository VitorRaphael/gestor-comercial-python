from sqlalchemy import select

from gestor_comercial.domain.impressora import Impressora
from gestor_comercial.repository.base import Repository


class ImpressoraRepository(Repository[Impressora]):
    modelo = Impressora

    def buscar_por_nome(self, nome: str) -> Impressora | None:
        return self.session.scalars(select(Impressora).where(Impressora.nome == nome)).first()
