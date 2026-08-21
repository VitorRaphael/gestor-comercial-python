from sqlalchemy import exists, select

from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.repository.base import Repository


class ItemComandaRepository(Repository[ItemComanda]):
    modelo = ItemComanda

    def listar_por_comanda(self, comanda_id: int) -> list[ItemComanda]:
        stmt = select(ItemComanda).where(ItemComanda.comanda_id == comanda_id).order_by(ItemComanda.id)
        return list(self.session.scalars(stmt))

    def existe_na_comanda(self, comanda_id: int) -> bool:
        return bool(self.session.scalar(select(exists().where(ItemComanda.comanda_id == comanda_id))))

    def existe_com_produto(self, produto_id: int) -> bool:
        return bool(self.session.scalar(select(exists().where(ItemComanda.produto_id == produto_id))))
