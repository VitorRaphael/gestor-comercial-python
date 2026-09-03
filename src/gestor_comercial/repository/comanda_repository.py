from sqlalchemy import select

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import StatusComanda
from gestor_comercial.repository.base import Repository


class ComandaRepository(Repository[Comanda]):
    modelo = Comanda

    def buscar_aberta_por_mesa(self, mesa_id: int) -> Comanda | None:
        """A comanda "em uso" da mesa: ainda lançando itens, ou já em conferência.

        Inclui EM_CONFERENCIA de propósito — sem isso, reabrir a tela de uma
        mesa cuja pré-conta já foi emitida não encontraria "existente" em
        `abrir_por_mesa` e criaria uma segunda comanda por cima da primeira,
        ainda não paga.
        """
        stmt = select(Comanda).where(
            Comanda.mesa_id == mesa_id,
            Comanda.status.in_([StatusComanda.ABERTA, StatusComanda.EM_CONFERENCIA]),
        )
        return self.session.scalars(stmt).first()

    def listar_por_status(self, status: StatusComanda) -> list[Comanda]:
        stmt = select(Comanda).where(Comanda.status == status).order_by(Comanda.id)
        return list(self.session.scalars(stmt))

    def listar_balcao_abertas(self) -> list[Comanda]:
        stmt = (
            select(Comanda)
            .where(Comanda.mesa_id.is_(None), Comanda.status == StatusComanda.ABERTA)
            .order_by(Comanda.id)
        )
        return list(self.session.scalars(stmt))

    def listar_por_caixa(self, caixa_id: int) -> list[Comanda]:
        stmt = select(Comanda).where(Comanda.caixa_id == caixa_id).order_by(Comanda.id)
        return list(self.session.scalars(stmt))
