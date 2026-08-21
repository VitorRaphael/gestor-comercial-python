from sqlalchemy import select

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.enums import StatusCaixa
from gestor_comercial.repository.base import Repository


class CaixaRepository(Repository[Caixa]):
    modelo = Caixa

    def buscar_aberto(self) -> Caixa | None:
        stmt = select(Caixa).where(Caixa.status == StatusCaixa.ABERTO).order_by(Caixa.id)
        return self.session.scalars(stmt).first()

    def buscar_ultimo_fechado(self) -> Caixa | None:
        stmt = (
            select(Caixa)
            .where(Caixa.status == StatusCaixa.FECHADO)
            .order_by(Caixa.fechado_em.desc(), Caixa.id.desc())
        )
        return self.session.scalars(stmt).first()
